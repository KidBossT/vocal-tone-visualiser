"""From per-frame measurements to what the display shows.

For every 10 ms frame from the PitchTracker, the ProsodyAnalyser works out:
  - loudness, smoothed so that each syllable reads as one shape;
  - sound or silence, and so the pauses (silence lasting PAUSE_MIN or more);
  - syllables (voiced loudness peaks) and from them the pace: syllables per second of speaking
    time, with pauses left out so that they are not counted twice;
  - the tension proxy: spectral tilt pooled over the last 1.5 s of voice;
  - and, over the first seconds of speech, the speaker's baseline (baseline.py).

Everything here is plain computation, so the tests can drive it with synthetic input.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from . import config as C
from .audio import StreamResampler
from .baseline import BaselineStats, Calibration, pitch_range
from .features import tilt_db

NAN = float("nan")
_EPS = 1e-6


@dataclass(frozen=True, slots=True)
class ProsodyFrame:
    t: float             # stream time of the frame centre (s)
    f0: float            # pitch in Hz; NaN when unvoiced (or background, after calibration)
    loud_db: float       # smoothed loudness, dB below full scale
    sound: bool          # False during silence
    pause_since: float   # start of the confirmed pause this frame is in; NaN otherwise
    tilt_db: float       # spectral tilt of the recent voice (dB); NaN until there is enough
    rate: float          # syllables per second of speaking time; NaN until there is enough
    tilt_low: float = NAN   # this frame's own spectral energy below / above 1 kHz, when it
    tilt_high: float = NAN  # counts towards voice quality (so stretches can be pooled exactly)


@dataclass(frozen=True)
class Reference:
    """What the display measures against: the calibrated baseline, or before that, a
    provisional middle pitch and level from the recent speech."""
    calibrated: bool
    progress: float                        # calibration progress, 0..1
    pitch_hz: float | None
    level_db: float | None
    tilt_db: float | None                  # None until calibrated
    rate: float | None                     # None until calibrated
    band_st: tuple[float, float] | None    # usual pitch range; None until calibrated

    @staticmethod
    def from_stats(stats: BaselineStats) -> "Reference":
        return Reference(True, 1.0, stats.pitch_hz, stats.level_db,
                         stats.tilt_db if math.isfinite(stats.tilt_db) else None,
                         stats.rate if math.isfinite(stats.rate) else None,
                         (stats.band_low_st, stats.band_high_st))


class NucleusDetector:
    """Finds syllable nuclei as they happen, after de Jong & Wempe (2009): a syllable is a peak
    in (lightly smoothed) loudness that stands at least NUCLEUS_DIP_DB above the dip before it
    and the dip after it, is loud enough, and has voice at the peak. A peak is confirmed once the
    loudness has fallen NUCLEUS_DIP_DB below it, typically 30-80 ms later."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._dip = math.inf
        self._peak: tuple[float, float, bool] | None = None

    def update(self, t: float, value: float, voiced: bool, min_peak: float) -> float | None:
        """Feed one loudness value; returns the time of a newly confirmed syllable, or None."""
        if self._peak is None:
            if value - self._dip >= C.NUCLEUS_DIP_DB:
                self._peak = (t, value, voiced)
            else:
                self._dip = min(self._dip, value)
            return None
        peak_t, peak_v, peak_voiced = self._peak
        if value >= peak_v:
            self._peak = (t, value, voiced)
            return None
        if peak_v - value >= C.NUCLEUS_DIP_DB:
            self._peak = None
            self._dip = value
            if peak_v >= min_peak and peak_voiced:
                return peak_t
        return None


class ProsodyAnalyser:
    def __init__(self, baseline: BaselineStats | None = None,
                 calibration_seconds: float = C.CALIBRATION_SPEECH_SECONDS):
        self.calibration_seconds = calibration_seconds
        self.stats = baseline
        self.calibration = None if baseline is not None else Calibration(calibration_seconds)
        self._recent: deque = deque()          # (t, f0, level) of voiced frames, last 20 s
        self._ref_hz: float | None = None
        self._ref_level: float | None = None
        self._ref_due = -math.inf
        self._loud: float | None = None
        self._attack = 1.0 - math.exp(-C.FRAME_STEP / C.LOUDNESS_ATTACK)
        self._release = 1.0 - math.exp(-C.FRAME_STEP / C.LOUDNESS_RELEASE)
        self._started = False                  # has there been any speech yet?
        self._voiced_run = 0                   # consecutive voiced frames so far
        self._last_voicing = -math.inf         # time of the latest real (30 ms+) voicing
        self._silence_start: float | None = None
        self._silence_leading = False          # silence before the first sound is not a pause
        self.speech_time = 0.0                 # seconds of speaking so far, pauses excluded
        self._rate_origin = 0.0
        self._last3: deque = deque(maxlen=3)   # (t, level, voiced) for the syllable finder
        self._nuclei = NucleusDetector()
        self._nucleus_clock: deque = deque()   # speaking time at each recent syllable
        self._tilt: deque = deque(maxlen=C.TILT_FRAMES)
        self._tilt_now = NAN
        self._progress_shown = -1.0
        self.reference = self._make_reference()

    # ---- baseline -------------------------------------------------------------------------

    def recalibrate(self) -> None:
        """Forget the current speaker; the next CALIBRATION_SPEECH_SECONDS of speech set a new
        baseline."""
        self.stats = None
        self.calibration = Calibration(self.calibration_seconds)
        self._nucleus_clock.clear()
        self._rate_origin = self.speech_time
        self._tilt.clear()
        self._tilt_now = NAN
        self._progress_shown = -1.0
        self.reference = self._make_reference()

    def use_baseline(self, stats: BaselineStats) -> None:
        """Measure against a baseline from elsewhere (a file, or a saved one) from now on."""
        self.stats = stats
        self.calibration = None
        self.reference = self._make_reference()

    def typical_level(self) -> float | None:
        return self.stats.level_db if self.stats is not None else self._ref_level

    def _make_reference(self) -> Reference:
        if self.stats is not None:
            return Reference.from_stats(self.stats)
        progress = self.calibration.progress if self.calibration is not None else 0.0
        return Reference(False, progress, self._ref_hz, self._ref_level, None, None, None)

    def _update_running_reference(self, t: float) -> None:
        recent = self._recent
        while recent and recent[0][0] < t - C.REFERENCE_SECONDS:
            recent.popleft()
        if t < self._ref_due:
            return
        self._ref_due = t + 0.25
        if len(recent) >= 20:
            self._ref_hz = float(np.median([f for _, f, _ in recent]))
            self._ref_level = float(np.median([lv for _, _, lv in recent]))
            if self.stats is None:
                self.reference = self._make_reference()

    # ---- per frame ------------------------------------------------------------------------

    def process(self, fr) -> tuple[ProsodyFrame, list]:
        """Take one tracker Frame; return the ProsodyFrame and any events: ("nucleus", t),
        ("pause", start, end) or ("calibrated", BaselineStats)."""
        events: list = []
        f0 = fr.f0
        voiced = not math.isnan(f0)
        if (voiced and self.stats is not None
                and fr.level_db < self.stats.level_db - C.TARGET_GATE_DB):
            f0, voiced = NAN, False            # far quieter than this speaker: background
        self._voiced_run = self._voiced_run + 1 if voiced else 0
        voicing = self._voiced_run >= C.SPEECH_MIN_VOICED   # a real voiced stretch, not a blip
        if voicing:
            self._last_voicing = fr.t
            self._recent.append((fr.t, f0, fr.level_db))
        self._update_running_reference(fr.t)
        typical = self.typical_level()

        # Speech or silence? Speech is anchored to voicing: unvoiced sound only counts as speech
        # right after voice (consonants), never on its own (fans, clicks, a noisy laptop mic).
        threshold = fr.floor_db + C.SPEECH_DB_ABOVE_FLOOR
        if typical is not None:
            threshold = max(threshold, typical - C.SPEECH_DB_BELOW_TYPICAL)
        sound = voicing or (fr.level_db > threshold
                            and fr.t - self._last_voicing <= C.SPEECH_HANGOVER + _EPS)

        # Loudness: quick to rise, slower to fall.
        if self._loud is None:
            self._loud = fr.level_db
        else:
            k = self._attack if fr.level_db > self._loud else self._release
            self._loud += (fr.level_db - self._loud) * k

        # Pauses and speaking time (a short silence inside speech counts as speaking).
        spoke = 0.0
        if sound:
            if self._silence_start is not None:
                gap = fr.t - self._silence_start
                if not self._silence_leading:
                    if gap >= C.PAUSE_MIN - _EPS:
                        events.append(("pause", self._silence_start, fr.t))
                    else:
                        spoke += gap
                self._silence_start = None
            self._started = True
            spoke += C.FRAME_STEP
        elif self._silence_start is None:
            self._silence_start = fr.t
            self._silence_leading = not self._started
        pause_since = NAN
        if (self._silence_start is not None and not self._silence_leading
                and fr.t - self._silence_start + C.FRAME_STEP >= C.PAUSE_MIN - _EPS):
            pause_since = self._silence_start
        self.speech_time += spoke

        # Syllables and pace.
        self._last3.append((fr.t, fr.level_db, voiced))
        if not math.isnan(pause_since):
            self._nuclei.reset()
        elif len(self._last3) == 3:
            t_mid, _, voiced_mid = self._last3[1]
            value = (self._last3[0][1] + self._last3[1][1] + self._last3[2][1]) / 3.0
            min_peak = (typical - C.NUCLEUS_MAX_DB_BELOW_TYPICAL if typical is not None
                        else fr.floor_db + 12.0)
            hit = self._nuclei.update(t_mid, value, voiced_mid, min_peak)
            if hit is not None:
                events.append(("nucleus", hit))
                self._nucleus_clock.append(self.speech_time)
                if self.calibration is not None:
                    self.calibration.add_nucleus()
        while self._nucleus_clock and self._nucleus_clock[0] < self.speech_time - C.RATE_WINDOW:
            self._nucleus_clock.popleft()
        span = min(C.RATE_WINDOW, self.speech_time - self._rate_origin)
        rate = len(self._nucleus_clock) / span if span >= C.RATE_MIN_SPEECH - _EPS else NAN

        # Tension proxy: spectral tilt pooled over the last TILT_FRAMES voiced frames
        # (ignoring much quieter voiced frames, where background noise would dominate).
        low = high = NAN
        if (voiced and not math.isnan(fr.tilt_low)
                and (typical is None or fr.level_db >= typical - 20.0)):
            low, high = fr.tilt_low, fr.tilt_high
            self._tilt.append((low, high))
            if len(self._tilt) >= C.TILT_MIN_FRAMES:
                self._tilt_now = tilt_db(sum(a for a, _ in self._tilt),
                                         sum(b for _, b in self._tilt))

        # Calibration.
        if self.calibration is not None and self._started:
            cal = self.calibration
            cal.add_speech_time(spoke)
            if voicing:
                cal.add_voiced(f0, fr.level_db, fr.tilt_low, fr.tilt_high)
            if cal.done():
                self.stats = cal.stats()
                self.calibration = None
                events.append(("calibrated", self.stats))
                self.reference = self._make_reference()
            elif cal.progress - self._progress_shown >= 0.02:
                self._progress_shown = cal.progress
                self.reference = self._make_reference()

        return (ProsodyFrame(fr.t, f0, self._loud, sound, pause_since, self._tilt_now, rate,
                             low, high), events)


# ---- whole recordings (the --baseline and --compare modes, and the tests) ------------------

@dataclass
class Recording:
    name: str
    duration: float
    frames: list = field(default_factory=list)   # ProsodyFrames
    events: list = field(default_factory=list)
    stats: BaselineStats | None = None           # the baseline used, or learned from it

    def summary(self, baseline: BaselineStats) -> str:
        """Numbers for the team (never shown in the window): this recording against a baseline."""
        f0 = np.array([f.f0 for f in self.frames])
        voiced = f0[~np.isnan(f0)]
        loud = np.array([f.loud_db for f, v in zip(self.frames, ~np.isnan(f0)) if v])
        rates = np.array([f.rate for f in self.frames if not math.isnan(f.rate)])
        tilts = np.array([f.tilt_db for f in self.frames if not math.isnan(f.tilt_db)])
        pauses = [ev[2] - ev[1] for ev in self.events if ev[0] == "pause"]
        syllables = sum(1 for ev in self.events if ev[0] == "nucleus")
        parts = []
        if voiced.size:
            st = 12 * np.log2(voiced / baseline.pitch_hz)
            parts.append(f"pitch {np.median(st):+.1f} st (spread {np.percentile(st, 90) - np.percentile(st, 10):.1f} st)")
        if loud.size:
            parts.append(f"loudness {np.median(loud) - baseline.level_db:+.1f} dB")
        if rates.size and math.isfinite(baseline.rate):
            parts.append(f"pace x{rates[-1] / baseline.rate:.2f}")
        if tilts.size and math.isfinite(baseline.tilt_db):
            parts.append(f"tilt {np.median(tilts) - baseline.tilt_db:+.1f} dB")
        parts.append(f"{syllables} syllables")
        long_pauses = [p for p in pauses if p >= C.LONG_PAUSE]
        parts.append(f"{len(pauses)} pauses ({len(long_pauses)} of 1 s or more"
                     + (f", longest {max(pauses):.1f} s)" if pauses else ")"))
        return ", ".join(parts)


def analyse_samples(x: np.ndarray, rate: int, *, baseline: BaselineStats | None = None,
                    learn_baseline: bool = False, name: str = "") -> Recording:
    """Run the whole analysis over a recording, as fast as possible (not in real time).

    With learn_baseline=True, all of the recording's speech becomes the baseline (rec.stats)."""
    from .tracker import PitchTracker
    resampler = StreamResampler(int(rate), C.ANALYSIS_RATE)
    tracker = PitchTracker(time_offset=-resampler.delay_seconds)
    analyser = ProsodyAnalyser(baseline=baseline,
                               calibration_seconds=math.inf if learn_baseline
                               else C.CALIBRATION_SPEECH_SECONDS)
    if baseline is not None:
        tracker.set_pitch_range(*pitch_range(baseline))
    rec = Recording(name=name, duration=x.size / rate, stats=baseline)
    block = int(rate)                    # one-second blocks, so a calibration that completes
    chunks = [x[i:i + block] for i in range(0, x.size, block)]   # part-way takes effect
    for chunk in chunks + [None]:
        frames = tracker.flush() if chunk is None else tracker.push(resampler.process(chunk))
        for fr in frames:
            pf, events = analyser.process(fr)
            rec.frames.append(pf)
            for ev in events:
                if ev[0] == "calibrated":
                    tracker.set_pitch_range(*pitch_range(ev[1]))
                rec.events.append(ev)
    if learn_baseline:
        rec.stats = analyser.calibration.stats()
    elif analyser.stats is not None:
        rec.stats = analyser.stats
    return rec


def baseline_from_file(path: str) -> BaselineStats:
    from .audio import load_mono
    x, rate = load_mono(path)
    return analyse_samples(x, rate, learn_baseline=True).stats
