"""Runs one listening session at a time (a microphone, or a file played aloud) and feeds its
measurements into a Session. The dashboard drives it; nothing here needs Qt.

Each run's stream time starts at 0, so runs are laid end to end in the session (with a
one-second gap between them) by adding an offset to every time.
"""

from __future__ import annotations

import os
import queue
import time

from . import audio
from . import config as C
from .prosody import Reference
from .session import Session, Timeline
from .tracker import AnalysisWorker

NO_REFERENCE = Reference(False, 0.0, None, None, None, None, None)


class Engine:
    def __init__(self, session: Session | None = None,
                 calibration_seconds: float = C.CALIBRATION_SPEECH_SECONDS):
        self.session = session or Session()
        self.live = Timeline()               # the last few seconds, for the live views
        self.calibration_seconds = calibration_seconds
        self.baseline = None                 # BaselineStats, once known
        self.record_audio = False
        self.recording_dir = "recordings"
        self.source = None
        self.worker = None
        self.recorder = None
        self.offset = 0.0
        self.description = ""
        self.last_level_db = float("nan")
        self._last_reference = NO_REFERENCE

    # ---- state ------------------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.worker is not None

    @property
    def is_file(self) -> bool:
        return self.source is not None and self.source.kind == "file"

    @property
    def reference(self) -> Reference:
        if self.worker is not None:
            self._last_reference = self.worker.reference
        elif self.baseline is not None:
            self._last_reference = Reference.from_stats(self.baseline)
        return self._last_reference

    def now(self) -> float | None:
        """Session time at the right-hand edge of the live views."""
        worker = self.worker
        if worker is None:
            return self.session.end_time if self.session.frame_count else None
        clock = worker.clock
        if clock.offset is None:
            return None
        t = clock.stream_now()
        if worker.finished and worker.end_time is not None:
            t = min(t, worker.end_time)
        return t + self.offset

    def status(self) -> str:
        """Problems with the sound itself, to show in the window (empty if none)."""
        worker = self.worker
        if worker is None or not worker.live:
            return ""
        last = worker.last_block_at
        if last is not None and time.perf_counter() - last > C.STALL_SECONDS:
            return "The microphone stopped sending sound. Stop and start again."
        if worker.silent_input:
            return "No sound from the microphone"
        return ""

    # ---- control ----------------------------------------------------------------------------

    def start(self, device=None, file_path: str | None = None, mute: bool = False,
              record_path: str | None = None) -> str:
        """Start listening to a microphone (or playing a file). Returns a description;
        raises audio.AudioError with a plain message if the sound cannot be opened.

        The microphone's sound is saved only if record_path is given (a take being recorded
        on purpose) or record_audio is on (the box in Setup)."""
        self.stop()
        q: queue.SimpleQueue = queue.SimpleQueue()
        if file_path:
            source = audio.FileSource(q, file_path, mute=mute)
        else:
            source = audio.MicSource(q, device=device)
        source.open()
        recorder = None
        if not file_path and (record_path or self.record_audio):
            path = record_path or os.path.join(self.recording_dir,
                                               os.path.basename(audio.default_recording_path()))
            try:
                recorder = audio.Recorder(path, source.samplerate)
            except Exception as exc:
                source.stop()
                raise audio.AudioError(f"Could not create the recording file {path}: {exc}") from exc
        worker = AnalysisWorker(q, source.samplerate, live=not file_path, recorder=recorder,
                                baseline=self.baseline,
                                calibration_seconds=self.calibration_seconds)
        end = self.session.end_time
        self.offset = end + 1.0 if self.session.frame_count else 0.0
        worker.start()
        try:
            source.start()
        except Exception as exc:
            worker.stop()
            source.stop()
            if recorder is not None:
                recorder.close()
            raise audio.AudioError(f"Could not start the sound: {exc}") from exc
        self.source, self.worker, self.recorder = source, worker, recorder
        self.session.sources.append(source.name)
        self.description = source.describe()
        return self.description

    def stop(self) -> str:
        """Stop listening. Returns a note about any saved recording (or "")."""
        note = ""
        source, worker, recorder = self.source, self.worker, self.recorder
        self.source = self.worker = self.recorder = None
        if source is not None:
            source.stop()
        if worker is not None:
            worker.finish()
            worker.join(timeout=2.0)
            self._drain(worker)
            self._last_reference = worker.reference
        if recorder is not None:
            recorder.close()
            note = f"Saved {recorder.seconds:.0f} s of sound to {recorder.path}"
        return note

    def drain(self) -> int:
        """Move newly analysed frames into the session and the live timeline. Returns how
        many frames arrived."""
        return self._drain(self.worker) if self.worker is not None else 0

    def _drain(self, worker) -> int:
        n = 0
        frames, events = worker.frames, worker.events
        while frames:
            pf, _ = frames.popleft()
            self.session.add_frame(pf, self.offset)
            self.live.add_frame(pf, self.offset)
            self.last_level_db = pf.loud_db
            n += 1
        while events:
            ev = events.popleft()
            if ev[0] == "calibrated":
                self.baseline = ev[1]
            self.session.add_event(ev, self.offset)
            self.live.add_event(ev, self.offset)
        if n:
            self.live.trim(self.session.end_time - 70.0)
        return n

    def recalibrate(self) -> None:
        self.baseline = None
        self.session.set_baseline(None)
        self._last_reference = NO_REFERENCE
        if self.worker is not None:
            self.worker.request_recalibration()

    def use_baseline(self, stats) -> None:
        self.baseline = stats
        self.session.set_baseline(stats, self.session.end_time)
        self._last_reference = Reference.from_stats(stats)
        if self.worker is not None:
            self.worker.set_baseline(stats)

    def new_session(self, keep_baseline: bool = True) -> Session:
        """Start a fresh session. It keeps the baseline (the same speaker, a new session)
        unless keep_baseline is False (a new speaker, or the demo recording)."""
        self.stop()
        if not keep_baseline:
            self.baseline = None
            self._last_reference = NO_REFERENCE
        self.session = Session()
        self.session.set_baseline(self.baseline, 0.0 if self.baseline else None)
        self.live = Timeline()
        self.offset = 0.0
        return self.session
