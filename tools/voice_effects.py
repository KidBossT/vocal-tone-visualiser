"""Offline voice transformations used to make test material (demo takes, failure cases) and for
the tension-measure comparison. None of this runs inside the visualiser itself.

All functions take and return mono float64 arrays.
"""

from __future__ import annotations

import numpy as np
import parselmouth
from parselmouth.praat import call
from scipy.signal import butter, lfilter, sosfiltfilt


def gain_db(x: np.ndarray, db: float) -> np.ndarray:
    return x * 10 ** (db / 20)


def rms(x: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0


def active_rms(x: np.ndarray, sr: int) -> float:
    """RMS over the louder half of 20 ms frames: a speech level that ignores pauses."""
    n = int(0.02 * sr)
    frames = x[: x.size // n * n].reshape(-1, n)
    levels = np.sqrt(np.mean(frames ** 2, axis=1))
    loud = levels[levels >= np.median(levels)]
    return float(np.sqrt(np.mean(loud ** 2))) if loud.size else rms(x)


def shelf(x: np.ndarray, sr: int, corner_hz: float, db: float) -> np.ndarray:
    """Smooth high-shelf: frequencies above `corner_hz` changed by `db` (zero-phase, offline)."""
    spectrum = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(x.size, 1.0 / sr)
    octaves = np.log2(np.maximum(freqs, 1.0) / corner_hz)
    weight = 1.0 / (1.0 + np.exp(-4.0 * octaves))        # 0 well below, 1 well above the corner
    return np.fft.irfft(spectrum * 10 ** (db * weight / 20), n=x.size)


def band(x: np.ndarray, sr: int, low_hz: float | None, high_hz: float | None) -> np.ndarray:
    if low_hz and high_hz:
        sos = butter(4, [low_hz, high_hz], btype="bandpass", fs=sr, output="sos")
    elif low_hz:
        sos = butter(4, low_hz, btype="highpass", fs=sr, output="sos")
    else:
        sos = butter(4, high_hz, btype="lowpass", fs=sr, output="sos")
    return sosfiltfilt(sos, x)


def envelope(x: np.ndarray, sr: int, smooth_s: float = 0.02) -> np.ndarray:
    n = max(1, int(smooth_s * sr))
    return np.sqrt(np.convolve(x ** 2, np.ones(n) / n, mode="same"))


def breathy(x: np.ndarray, sr: int, seed: int = 0, noise_db: float = -18.0,
            tilt_db: float = -6.0) -> np.ndarray:
    """Softer upper harmonics plus aspiration noise that follows the voice (a crude breathy voice)."""
    rng = np.random.default_rng(seed)
    soft = shelf(x, sr, 1000.0, tilt_db)
    noise = band(rng.standard_normal(x.size), sr, 1500.0, min(7000.0, sr / 2 - 100))
    noise *= envelope(x, sr) / (rms(noise) + 1e-12)
    return soft + gain_db(noise, noise_db)


def pressed(x: np.ndarray, sr: int, tilt_db: float = 6.0) -> np.ndarray:
    """Stronger upper harmonics (a crude pressed, effortful voice)."""
    return shelf(x, sr, 1200.0, tilt_db)


def add_noise(x: np.ndarray, sr: int, snr_db: float, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(x.size)
    return x + noise * active_rms(x, sr) / rms(noise) * 10 ** (-snr_db / 20)


def reverb(x: np.ndarray, sr: int, rt60: float = 0.5, drr_db: float = 0.0,
           seed: int = 3) -> np.ndarray:
    """A plain room: the dry voice plus an exponentially decaying noise tail (reverberation time
    `rt60`), mixed so the direct sound is `drr_db` louder than the reverberation."""
    from scipy.signal import fftconvolve
    rng = np.random.default_rng(seed)
    t = np.arange(int(rt60 * 1.2 * sr)) / sr
    ir = rng.standard_normal(t.size) * np.exp(-6.91 * t / rt60)
    wet = fftconvolve(x, ir)[: x.size]
    wet *= rms(x) / (rms(wet) + 1e-12) * 10 ** (-drr_db / 20)
    return x + wet


def scale_pitch_range(x: np.ndarray, sr: int, factor: float, shift_semitones: float = 0.0,
                      floor: float = 75.0, ceiling: float = 600.0) -> np.ndarray:
    """Stretch (factor > 1) or flatten (factor < 1) the pitch movement around the median, and
    optionally shift it, using Praat's overlap-add resynthesis."""
    snd = parselmouth.Sound(x, sr)
    manipulation = call(snd, "To Manipulation", 0.01, floor, ceiling)
    tier = call(manipulation, "Extract pitch tier")
    n = int(call(tier, "Get number of points"))
    if n == 0:
        return x.copy()
    times = [call(tier, "Get time from index", i) for i in range(1, n + 1)]
    values = np.array([call(tier, "Get value at index", i) for i in range(1, n + 1)])
    median = float(np.median(values))
    new_values = median * (values / median) ** factor * 2 ** (shift_semitones / 12)
    new_tier = call("Create PitchTier", "scaled", snd.xmin, snd.xmax)
    for t, v in zip(times, new_values):
        call(new_tier, "Add point", t, float(v))
    call([manipulation, new_tier], "Replace pitch tier")
    y = call(manipulation, "Get resynthesis (overlap-add)").values[0].astype(np.float64)
    return y[: x.size] if y.size >= x.size else np.pad(y, (0, x.size - y.size))


def change_speed(x: np.ndarray, sr: int, factor: float, floor: float = 75.0,
                 ceiling: float = 600.0) -> np.ndarray:
    """Make speech faster (factor < 1) or slower (factor > 1) without changing its pitch."""
    snd = parselmouth.Sound(x, sr)
    out = call(snd, "Lengthen (overlap-add)", floor, ceiling, factor)
    return out.values[0].astype(np.float64)


def whisper(x: np.ndarray, sr: int, order: int = 18, seed: int = 2) -> np.ndarray:
    """Replace the voice's buzz with noise while keeping its mouth shapes (vowel resonances):
    an approximation of whispering. Frame-wise linear prediction, overlap-added."""
    rng = np.random.default_rng(seed)
    n, hop = int(0.03 * sr), int(0.015 * sr)
    window = np.hanning(n)
    out = np.zeros(x.size + n)
    for start in range(0, x.size - n, hop):
        frame = x[start:start + n] * window
        energy = float(np.sum(frame ** 2))
        if energy < 1e-10:
            continue
        r = np.correlate(frame, frame, mode="full")[n - 1:n + order]
        a = _levinson(r, order)
        excitation = rng.standard_normal(n)
        shaped = lfilter([1.0], a, excitation) * window
        shaped *= np.sqrt(energy / (np.sum(shaped ** 2) + 1e-12))
        out[start:start + n] += shaped
    return out[: x.size]


def _levinson(r: np.ndarray, order: int) -> np.ndarray:
    a = np.zeros(order + 1)
    a[0] = 1.0
    err = r[0] + 1e-12
    for i in range(1, order + 1):
        acc = r[i] + np.dot(a[1:i], r[i - 1:0:-1])
        k = -acc / err
        a[1:i] = a[1:i] + k * a[i - 1:0:-1]
        a[i] = k
        err *= 1.0 - k * k
    return a
