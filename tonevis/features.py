"""Feature extraction as plain functions: no threads, no sound devices.

Keeping these pure means the tests can feed them synthetic signals with known answers.
"""

from __future__ import annotations

import numpy as np
import parselmouth

DB_FLOOR = -120.0  # what silence reads as, instead of minus infinity


def rms_db(x: np.ndarray) -> float:
    """Level in dB relative to digital full scale (a full-scale sine wave reads about -3 dB)."""
    x = np.asarray(x, dtype=np.float64)
    if x.size == 0:
        return DB_FLOOR
    mean_square = float(np.mean(x * x))
    if mean_square <= 0.0:
        return DB_FLOOR
    return max(DB_FLOOR, 10.0 * np.log10(mean_square))


def praat_pitch(samples: np.ndarray, sr: int, *, time_step: float, floor: float,
                ceiling: float, voicing_threshold: float,
                silence_threshold: float) -> tuple[np.ndarray, np.ndarray]:
    """Run Praat's autocorrelation pitch tracker over one stretch of audio.

    Returns (frame centre times in seconds from the start of `samples`, pitch in Hz),
    with NaN wherever Praat found no voiced sound.
    """
    snd = parselmouth.Sound(np.asarray(samples, dtype=np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch_ac(time_step=time_step, pitch_floor=floor, pitch_ceiling=ceiling,
                            voicing_threshold=voicing_threshold,
                            silence_threshold=silence_threshold)
    f0 = np.array(pitch.selected_array["frequency"], dtype=np.float64)
    f0[f0 <= 0.0] = np.nan
    return np.asarray(pitch.xs(), dtype=np.float64), f0


def semitones(f0_hz, ref_hz: float) -> np.ndarray:
    """Distance from a reference pitch in semitones: +12 is one octave higher, -12 one lower."""
    return 12.0 * np.log2(np.asarray(f0_hz, dtype=np.float64) / ref_hz)


_tilt_cache: dict = {}


def tilt_bands(frame: np.ndarray, sr: int, low=(50.0, 1000.0),
               high=(1000.0, 5000.0)) -> tuple[float, float]:
    """Energy of one short frame below and above 1 kHz (Hann-windowed spectrum)."""
    frame = np.asarray(frame, dtype=np.float64)
    key = (frame.size, sr, low, high)
    cached = _tilt_cache.get(key)
    if cached is None:
        freqs = np.fft.rfftfreq(frame.size, 1.0 / sr)
        cached = (np.hanning(frame.size),
                  (freqs >= low[0]) & (freqs < low[1]),
                  (freqs >= high[0]) & (freqs < high[1]))
        _tilt_cache[key] = cached
    window, low_mask, high_mask = cached
    power = np.abs(np.fft.rfft(frame * window)) ** 2
    return float(power[low_mask].sum()), float(power[high_mask].sum())


def tilt_db(low_energy: float, high_energy: float) -> float:
    """Spectral balance: energy above 1 kHz relative to energy below it, in dB (the "alpha
    ratio" used in voice research, e.g. in the eGeMAPS feature set).

    A pressed, effortful voice puts relatively more energy into the upper harmonics, so the value
    goes up; a soft or breathy voice puts less, so it goes down. A plain volume change does not
    move it, because it is a ratio. NaN when either band is empty.
    """
    if not (low_energy > 0.0 and high_energy > 0.0):
        return float("nan")
    return 10.0 * np.log10(high_energy / low_energy)


def spectral_tilt_db(frame: np.ndarray, sr: int, low=(50.0, 1000.0),
                     high=(1000.0, 5000.0)) -> float:
    """Spectral tilt of a single frame (see tilt_db)."""
    return tilt_db(*tilt_bands(frame, sr, low, high))
