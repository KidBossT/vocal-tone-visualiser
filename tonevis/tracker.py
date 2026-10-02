"""Streaming analysis: continuous audio in, one timestamped frame every 10 ms out.

``PitchTracker`` measures each 10 ms frame (pitch, level, spectral balance). ``ProsodyAnalyser``
(prosody.py) turns frames into what the display shows. ``AnalysisWorker`` is the background
thread that connects them to a sound source and to the display.
"""

from __future__ import annotations

import math
import queue
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass

import numpy as np
from scipy.signal import butter, sosfilt

from . import config as C
from .audio import END, StreamResampler
from .features import DB_FLOOR, praat_pitch, rms_db, tilt_bands

STOP = object()  # queue marker: finish what is queued, then exit


@dataclass(frozen=True, slots=True)
class Frame:
    t: float          # stream time of the frame centre: seconds since the audio started
    f0: float         # pitch in Hz; NaN when there is no voiced sound
    level_db: float   # level of the 25 ms around the centre, dB below full scale
    floor_db: float   # background level estimate at this moment
    tilt_low: float   # spectral energy below 1 kHz (voiced frames only, else NaN)
    tilt_high: float  # spectral energy between 1 and 5 kHz (voiced frames only, else NaN)


class PitchTracker:
    """Turns a 16 kHz sample stream into one Frame every 10 ms.

    Every HOP (20 ms) it gives the newest ANALYSIS_WINDOW (200 ms) of audio to Praat and keeps
    the frames it has not reported yet. Windows always start on the 20 ms grid and frames are
    numbered by the 10 ms slot their centre falls in, so the output is the same whatever size
    the incoming blocks are, and stays on the grid when the pitch range changes.
    """

    def __init__(self, sr: int = C.ANALYSIS_RATE, time_offset: float = 0.0):
        self.sr = int(sr)
        self.time_offset = float(time_offset)
        self.hop = int(round(C.HOP * self.sr))
        self.win = int(round(C.ANALYSIS_WINDOW * self.sr))
        self.step = int(round(C.FRAME_STEP * self.sr))
        if self.win % self.hop or self.hop % self.step:
            raise ValueError("ANALYSIS_WINDOW must be whole HOPs, and HOP whole FRAME_STEPs")
        self.level_half = int(round(C.LEVEL_WINDOW * self.sr / 2))
        self.tilt_len = int(C.TILT_FRAME)
        self.floor, self.ceiling = C.PITCH_FLOOR, C.PITCH_CEILING
        # High-pass first: DC offset and rumble would otherwise read as sound in silence.
        self._hp = butter(2, C.HIGH_PASS_HZ, btype="highpass", fs=self.sr, output="sos")
        self._hp_state = np.zeros((self._hp.shape[0], 2))
        self._buf = np.zeros(0)
        self._buf_start = 0          # absolute sample index of _buf[0]
        self._next_end = self.win    # absolute sample index where the next window ends
        self._last_index = -1        # 10 ms slot of the newest frame reported
        self._floor_db = None        # running estimate of the background level
        self.runs = 0
        self.run_seconds = 0.0
        self.errors = 0

    @property
    def mean_run_ms(self) -> float:
        return 1000.0 * self.run_seconds / self.runs if self.runs else 0.0

    def set_pitch_range(self, floor: float, ceiling: float) -> None:
        """Where to look for pitch (Hz). Narrowed to the speaker after calibration."""
        self.floor, self.ceiling = float(floor), float(ceiling)

    def push(self, samples) -> list[Frame]:
        x = np.asarray(samples, dtype=np.float64).ravel()
        if x.size:
            x, self._hp_state = sosfilt(self._hp, x, zi=self._hp_state)
            self._buf = np.concatenate((self._buf, x))
        out: list[Frame] = []
        while self._buf_start + self._buf.size >= self._next_end:
            try:
                out.extend(self._analyse(self._next_end))
            except Exception as exc:    # never let one bad window stall the stream
                self.errors += 1
                if self.errors <= 3:
                    print(f"Pitch analysis failed for one window: {exc}", flush=True)
            self._next_end += self.hop
        drop = (self._next_end - self.win) - self._buf_start   # no future window needs these
        if drop > 0:
            self._buf = self._buf[drop:]
            self._buf_start += drop
        return out

    def flush(self) -> list[Frame]:
        """Finish a stream that has ended: pad with silence so its last moments get analysed."""
        return self.push(np.zeros(self.win))

    def _analyse(self, end: int) -> list[Frame]:
        start = end - self.win
        seg = self._buf[start - self._buf_start:end - self._buf_start]
        t0 = time.perf_counter()
        times, f0 = praat_pitch(seg, self.sr, time_step=C.FRAME_STEP, floor=self.floor,
                                ceiling=self.ceiling, voicing_threshold=C.VOICING_THRESHOLD,
                                silence_threshold=C.SILENCE_THRESHOLD)
        self.run_seconds += time.perf_counter() - t0
        self.runs += 1
        frames = []
        for t_local, hz in zip(times.tolist(), f0.tolist()):
            centre = start + int(round(t_local * self.sr))
            index = centre // self.step
            if index <= self._last_index:
                continue                 # already reported by an earlier, overlapping run
            self._last_index = index
            c = centre - start
            level = rms_db(seg[max(0, c - self.level_half):c + self.level_half])
            floor = self._update_floor(level)
            if level < max(floor + C.GATE_DB_ABOVE_FLOOR, C.ABSOLUTE_GATE_DB):
                hz = math.nan
            low = high = math.nan
            if not math.isnan(hz):
                a = min(max(c - self.tilt_len // 2, 0), seg.size - self.tilt_len)
                low, high = tilt_bands(seg[a:a + self.tilt_len], self.sr,
                                       C.TILT_LOW_BAND, C.TILT_HIGH_BAND)
            t = (index + 0.5) * self.step / self.sr + self.time_offset
            frames.append(Frame(t, float(hz), level, floor, low, high))
        return frames

    def _update_floor(self, level: float) -> float:
        if level <= DB_FLOOR + 1.0:
            # Exact digital silence (some laptop mics switch to zeros between sounds) says
            # nothing about the room's background level, so leave the estimate alone.
            return C.NOISE_FLOOR_START_DB if self._floor_db is None else self._floor_db
        if self._floor_db is None:
            self._floor_db = min(level, C.NOISE_FLOOR_START_DB)
        else:
            rise = C.NOISE_FLOOR_RISE_DB_PER_S * C.FRAME_STEP
            self._floor_db = min(level, self._floor_db + rise)
        return self._floor_db


class StreamClock:
    """Maps stream time (seconds of audio since the start) to wall-clock time
    (``time.perf_counter()``), from the timestamps the sound source attaches to each block.

    Callbacks run a little late or early at random, so each block gives a slightly wrong
    estimate of the offset between the two clocks. For a microphone, lateness only ever makes
    the estimate too big, so the smallest recent estimate is the best one ("min"). For
    playback, the error goes the other way ("max"). Using only the last ~1 s of blocks
    follows slow drift between the sound card's clock and the computer's, and recovers
    within a second if the sound system ever drops audio.
    """

    def __init__(self, pick: str = "min"):
        if pick not in ("min", "max"):
            raise ValueError("pick must be 'min' or 'max'")
        self._pick = min if pick == "min" else max
        self._recent = deque(maxlen=100)
        self.offset: float | None = None   # wall time minus stream time

    def add(self, wall_first: float, stream_first: float) -> None:
        self._recent.append(wall_first - stream_first)
        self.offset = self._pick(self._recent)

    def wall(self, stream_t: float) -> float:
        return stream_t + self.offset

    def stream_now(self, wall_t: float | None = None) -> float:
        return (time.perf_counter() if wall_t is None else wall_t) - self.offset


class AnalysisWorker(threading.Thread):
    """Background thread: takes blocks off the source queue, converts them to 16 kHz,
    analyses them, and (only with --record) saves them. The display drains ``frames`` and
    ``events``; ``reference`` is the speaker baseline it measures against.

    With analyse=False it only keeps the clock (used to animate --compare playback)."""

    def __init__(self, source_queue, source_rate: int, *, live: bool, recorder=None,
                 baseline=None, calibration_seconds: float = C.CALIBRATION_SPEECH_SECONDS,
                 analyse: bool = True):
        from .baseline import pitch_range
        from .prosody import ProsodyAnalyser
        super().__init__(name="analysis", daemon=True)
        self.q = source_queue
        self.source_rate = int(source_rate)
        self.live = live
        self.recorder = recorder
        self.analyse = analyse
        self.resampler = StreamResampler(self.source_rate, C.ANALYSIS_RATE)
        self.tracker = PitchTracker(time_offset=-self.resampler.delay_seconds)
        self.analyser = ProsodyAnalyser(baseline=baseline,
                                        calibration_seconds=calibration_seconds)
        self._pitch_range = pitch_range
        if baseline is not None:
            self.tracker.set_pitch_range(*pitch_range(baseline))
        self.clock = StreamClock("min" if live else "max")
        self.frames: deque = deque()   # (ProsodyFrame, perf_counter() when it became available)
        self.events: deque = deque()   # ("nucleus", t) / ("pause", start, end) / ("calibrated", stats)
        self.finished = False          # a file has played to its end
        self.end_time: float | None = None
        self.silent_input = False      # the microphone is sending exact zeros
        self.last_block_at: float | None = None   # perf_counter() when sound last arrived
        self._zero_run = 0.0
        self._heard_sound = False
        self._warned_silence = False
        self._n = 0                    # source samples handled so far
        self._halt = threading.Event()
        self._commands: queue.SimpleQueue = queue.SimpleQueue()   # applied on this thread
        self._errors = 0

    @property
    def reference(self):
        return self.analyser.reference

    @property
    def seconds_received(self) -> float:
        return self._n / self.source_rate

    @property
    def backlog(self) -> int:
        """Blocks waiting to be analysed (should stay near zero)."""
        try:
            return self.q.qsize()
        except (AttributeError, NotImplementedError):
            return -1

    def request_recalibration(self) -> None:
        """Forget the current speaker and calibrate again (the R key)."""
        self._commands.put(("recalibrate", None))

    def set_baseline(self, stats) -> None:
        """Measure against this baseline from now on (e.g. one loaded from a file)."""
        self._commands.put(("baseline", stats))

    def _apply_commands(self) -> None:
        while True:
            try:
                kind, stats = self._commands.get_nowait()
            except queue.Empty:
                return
            if kind == "recalibrate":
                self.analyser.recalibrate()
                self.tracker.set_pitch_range(C.PITCH_FLOOR, C.PITCH_CEILING)
            elif kind == "baseline":
                self.analyser.use_baseline(stats)
                self.tracker.set_pitch_range(*self._pitch_range(stats))

    def finish(self) -> None:
        """Handle whatever is already queued, then stop."""
        self.q.put(STOP)

    def stop(self) -> None:
        """Stop straight away."""
        self._halt.set()

    def run(self) -> None:
        while not self._halt.is_set():
            try:
                item = self.q.get(timeout=0.1)
            except queue.Empty:
                continue
            if item is STOP:
                break
            try:
                self._handle(item)
            except Exception:
                self._errors += 1
                if self._errors <= 5:
                    traceback.print_exc()

    def _handle(self, item) -> None:
        self._apply_commands()
        if item is END:
            self.end_time = self._n / self.source_rate
            if self.analyse:
                self._publish(self.tracker.flush())
            self.finished = True
            return
        samples, first_wall = item
        self.last_block_at = time.perf_counter()
        self.clock.add(first_wall, self._n / self.source_rate)
        self._n += samples.size
        if self.recorder is not None:
            try:
                self.recorder.write(samples)
            except Exception as exc:     # e.g. disk full: stop recording, keep the display going
                print(f"WARNING: recording stopped ({exc}). The display carries on.", flush=True)
                self.recorder = None
        if self.live:
            self._watch_for_digital_silence(samples)
        if self.analyse:
            self._publish(self.tracker.push(self.resampler.process(samples)))

    def _publish(self, frames: list[Frame]) -> None:
        now = time.perf_counter()
        for fr in frames:
            pf, events = self.analyser.process(fr)
            self.frames.append((pf, now))
            for ev in events:
                if ev[0] == "calibrated":
                    self.tracker.set_pitch_range(*self._pitch_range(ev[1]))
                self.events.append(ev)

    def _watch_for_digital_silence(self, samples: np.ndarray) -> None:
        """Exact zeros from the very start usually mean the microphone is muted or blocked by
        privacy settings. Some laptop mics also send zeros between sounds, so once real sound
        has been heard only a long stretch of zeros counts."""
        if samples.size and not np.any(samples):
            self._zero_run += samples.size / self.source_rate
            if self._zero_run > (15.0 if self._heard_sound else 3.0):
                self.silent_input = True
                if not self._heard_sound and not self._warned_silence:
                    self._warned_silence = True
                    print("WARNING: the microphone is sending pure silence. It may be muted, "
                          "or the app may not be allowed to use it (Windows: Settings > "
                          "Privacy & security > Microphone; Mac: System Settings > Privacy & "
                          "Security > Microphone).", flush=True)
        else:
            self._heard_sound = True
            self._zero_run = 0.0
            self.silent_input = False
