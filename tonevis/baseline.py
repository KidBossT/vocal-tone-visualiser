"""The speaker's own baseline, which everything on screen is measured against.

During the first CALIBRATION_SPEECH_SECONDS of someone speaking (pauses do not count), the
analyser collects their pitch, loudness, pace and spectral balance. The result, BaselineStats,
stays fixed until you recalibrate (R), so a slow drift over a session (a client getting
steadily quieter, say) stays visible instead of being absorbed into a moving baseline.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, fields

import numpy as np

from . import config as C
from .features import tilt_db


@dataclass(frozen=True)
class BaselineStats:
    pitch_hz: float        # median pitch
    q1_hz: float           # lower and upper quartiles of pitch
    q3_hz: float
    band_low_st: float     # the "usual range" band: 10th and 90th percentile of pitch,
    band_high_st: float    # in semitones from the median
    level_db: float        # typical loudness of their voiced sound (dB below full scale)
    rate: float            # usual pace, syllables per second of speaking time (NaN if unknown)
    tilt_db: float         # usual spectral tilt (NaN if unknown)
    speech_seconds: float  # how much speech this was based on

    def to_json(self) -> str:
        """Numbers only (no sound), so a client's baseline can be kept between sessions."""
        data = {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                for k, v in asdict(self).items()}
        return json.dumps({"format": "tonevis-baseline", "version": 1, **data}, indent=2)

    @classmethod
    def from_json(cls, text: str) -> "BaselineStats":
        data = json.loads(text)
        if data.get("format") != "tonevis-baseline":
            raise ValueError("this is not a tone visualiser baseline file")
        values = {}
        for f in fields(cls):
            if f.name not in data:
                raise ValueError(f"the baseline file is missing '{f.name}'")
            v = data[f.name]
            values[f.name] = float("nan") if v is None else float(v)
        return cls(**values)

    def describe(self) -> str:
        rate = f"{self.rate:.1f} syllables/s" if np.isfinite(self.rate) else "pace unknown"
        tilt = f"{self.tilt_db:.1f} dB" if np.isfinite(self.tilt_db) else "unknown"
        return (f"middle pitch {self.pitch_hz:.0f} Hz (usual range {self.band_low_st:+.1f} to "
                f"{self.band_high_st:+.1f} semitones), typical level {self.level_db:.0f} dBFS, "
                f"{rate}, spectral tilt {tilt}; from {self.speech_seconds:.0f} s of speech")


class Calibration:
    """Collects one speaker's measurements until there is enough speech."""

    def __init__(self, needed_seconds: float = C.CALIBRATION_SPEECH_SECONDS):
        self.needed = float(needed_seconds)
        self.speech_seconds = 0.0
        self.nuclei = 0
        self._f0: list[float] = []
        self._levels: list[float] = []
        self._low = 0.0
        self._high = 0.0

    @property
    def progress(self) -> float:
        if not np.isfinite(self.needed) or self.needed <= 0:
            return 0.0
        return min(1.0, self.speech_seconds / self.needed)

    def add_speech_time(self, seconds: float) -> None:
        self.speech_seconds += seconds

    def add_voiced(self, f0: float, level_db: float, low: float, high: float) -> None:
        self._f0.append(f0)
        self._levels.append(level_db)
        if low == low and high == high:        # not NaN
            self._low += low
            self._high += high

    def add_nucleus(self) -> None:
        self.nuclei += 1

    def enough_data(self) -> bool:
        return len(self._f0) >= 100 and self.speech_seconds >= 3.0

    def done(self) -> bool:
        return self.speech_seconds >= self.needed and self.enough_data()

    def stats(self) -> BaselineStats:
        if not self.enough_data():
            raise ValueError("not enough voiced speech to calibrate on (need about 3 s)")
        f0 = np.asarray(self._f0)
        median = float(np.median(f0))
        q1, q3 = (float(v) for v in np.percentile(f0, [25, 75]))
        low, high = (float(v) for v in np.percentile(f0, C.USUAL_RANGE_PERCENTILES))
        rate = self.nuclei / self.speech_seconds if self.nuclei >= 8 else float("nan")
        return BaselineStats(
            pitch_hz=median, q1_hz=q1, q3_hz=q3,
            band_low_st=12.0 * np.log2(low / median), band_high_st=12.0 * np.log2(high / median),
            level_db=float(np.median(self._levels)), rate=rate,
            tilt_db=tilt_db(self._low, self._high), speech_seconds=self.speech_seconds)


def pitch_range(stats: BaselineStats) -> tuple[float, float]:
    """Where to look for this speaker's pitch after calibration (after Hirst's two-pass method:
    from 0.75 x the lower quartile to 2 x the upper quartile), never narrower than a range
    comfortable for expressive speech."""
    floor = min(C.PITCH_FLOOR_FACTOR * stats.q1_hz, 0.7 * stats.pitch_hz)
    ceiling = max(C.PITCH_CEILING_FACTOR * stats.q3_hz, 1.6 * stats.pitch_hz)
    floor = min(max(floor, 60.0), 400.0)
    ceiling = min(max(ceiling, 2.0 * floor), 600.0)
    return floor, ceiling
