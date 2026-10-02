"""Which vocal-tension measure stays most stable in real time: jitter, shimmer or spectral tilt?

    .venv\\Scripts\\python.exe tools\\tension_bakeoff.py [more.wav ...]

Each candidate is measured over 1-second windows (every 0.25 s), the span the display would
average over, on the neutral baseline readings. The same readings are then changed in ways
that should NOT move a tension measure (10 dB quieter, background noise, a reverberant room,
livelier intonation) and in ways that should (a more pressed or a more breathy voice quality).

For each measure the table shows:
  gaps     share of windows where the measure could not be computed at all
  wobble   how much it varies from window to window while nothing changes (its own units)
  then each change as an effect size d = (median shift) / wobble. A good measure has small |d|
  for the first three changes and large |d| for the last two.
"""

from __future__ import annotations

import os
import sys
from math import gcd

import numpy as np
import parselmouth
import soundfile as sf
from parselmouth.praat import call
from scipy.signal import resample_poly

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import voice_effects as fx  # noqa: E402
from tonevis.features import spectral_tilt_db  # noqa: E402

SR = 16_000
WINDOW, STEP = 1.0, 0.25
MIN_VOICED = 0.4          # s of voicing a window needs to count
FLOOR, CEILING = 75.0, 500.0

CONDITIONS = {
    "quieter": lambda x: fx.gain_db(x, -10.0),
    "noise": lambda x: fx.add_noise(x, SR, 20.0),
    "room": lambda x: fx.reverb(x, SR, rt60=0.5, drr_db=0.0),
    "intonation": lambda x: fx.scale_pitch_range(x, SR, 1.6),
    "pressed": lambda x: fx.pressed(x, SR),
    "breathy": lambda x: fx.breathy(x, SR),
}
NUISANCE = ("quieter", "noise", "room", "intonation")
WANTED = ("pressed", "breathy")


def load(path: str) -> np.ndarray:
    x, rate = sf.read(path, dtype="float64", always_2d=True)
    x = x.mean(axis=1)
    if rate != SR:
        g = gcd(rate, SR)
        x = resample_poly(x, SR // g, rate // g)
    return x


def measure(x: np.ndarray, starts: np.ndarray) -> dict[str, np.ndarray]:
    """Jitter (%), shimmer (%) and median spectral tilt (dB) for each 1 s window."""
    snd = parselmouth.Sound(x, SR)
    points = call(snd, "To PointProcess (periodic, cc)", FLOOR, CEILING)
    pitch = snd.to_pitch_ac(time_step=0.01, pitch_floor=FLOOR, pitch_ceiling=CEILING)
    times = np.array(pitch.xs())
    voiced = pitch.selected_array["frequency"] > 0
    half = 256
    tilt = np.full(times.size, np.nan)
    low = np.full(times.size, np.nan)      # band energies, for the pooled variant
    high = np.full(times.size, np.nan)
    freqs = np.fft.rfftfreq(2 * half, 1.0 / SR)
    lo_mask, hi_mask = (freqs >= 50) & (freqs < 1000), (freqs >= 1000) & (freqs < 5000)
    window = np.hanning(2 * half)
    for i in np.flatnonzero(voiced):
        c = int(round(times[i] * SR))
        if c - half >= 0 and c + half <= x.size:
            frame = x[c - half:c + half]
            tilt[i] = spectral_tilt_db(frame, SR)
            power = np.abs(np.fft.rfft(frame * window)) ** 2
            low[i], high[i] = power[lo_mask].sum(), power[hi_mask].sum()
    out = {"jitter": [], "shimmer": [], "tilt": [], "tilt_pooled": []}
    for s in starts:
        e = s + WINDOW
        jitter = call(points, "Get jitter (local)", s, e, 0.0001, 0.02, 1.3)
        shimmer = call([snd, points], "Get shimmer (local)", s, e, 0.0001, 0.02, 1.3, 1.6)
        inside = (times >= s) & (times < e) & ~np.isnan(tilt)
        out["jitter"].append(100 * jitter if np.isfinite(jitter) else np.nan)
        out["shimmer"].append(100 * shimmer if np.isfinite(shimmer) else np.nan)
        enough = inside.sum() >= 10
        out["tilt"].append(np.median(tilt[inside]) if enough else np.nan)
        out["tilt_pooled"].append(10 * np.log10(high[inside].sum() / low[inside].sum())
                                  if enough else np.nan)
    return {k: np.array(v, dtype=float) for k, v in out.items()}


def windows_with_voice(x: np.ndarray) -> np.ndarray:
    pitch = parselmouth.Sound(x, SR).to_pitch_ac(time_step=0.01, pitch_floor=FLOOR,
                                                 pitch_ceiling=CEILING)
    times = np.array(pitch.xs())
    voiced = pitch.selected_array["frequency"] > 0
    starts = np.arange(0.0, x.size / SR - WINDOW, STEP)
    keep = [s for s in starts if voiced[(times >= s) & (times < s + WINDOW)].sum() * 0.01 >= MIN_VOICED]
    return np.array(keep)


def main(paths: list[str]) -> int:
    rows = {m: {"gaps": [], "wobble": [], **{c: [] for c in CONDITIONS}}
            for m in ("jitter", "shimmer", "tilt", "tilt_pooled")}
    for path in paths:
        x = load(path)
        starts = windows_with_voice(x)
        base = measure(x, starts)
        changed = {name: measure(f(x), starts) for name, f in CONDITIONS.items()}
        print(f"{os.path.basename(path)}: {starts.size} windows")
        for m in rows:
            v = base[m]
            ok = v[~np.isnan(v)]
            wobble = float(np.std(ok)) if ok.size > 2 else np.nan
            rows[m]["gaps"].append(100.0 * np.mean(np.isnan(v)))
            rows[m]["wobble"].append(wobble)
            for name in CONDITIONS:
                w = changed[name][m]
                both = ~np.isnan(v) & ~np.isnan(w)
                shift = float(np.median(w[both] - v[both])) if both.sum() > 2 else np.nan
                rows[m][name].append(shift / wobble if wobble else np.nan)

    units = {"jitter": "%", "shimmer": "%", "tilt": "dB", "tilt_pooled": "dB"}
    header = (f"{'measure':11s} {'gaps':>6s} {'wobble':>9s}  "
              + "  ".join(f"{c:>10s}" for c in CONDITIONS) + "   nuisance  wanted")
    print("\nEffect sizes d = median shift / wobble (averaged over the files)\n" + header)
    print("-" * len(header))
    for m, r in rows.items():
        d = {c: float(np.nanmean(r[c])) for c in CONDITIONS}
        nuisance = np.mean([abs(d[c]) for c in NUISANCE])
        wanted = np.mean([abs(d[c]) for c in WANTED])
        print(f"{m:11s} {np.mean(r['gaps']):5.0f}% {np.nanmean(r['wobble']):7.2f}{units[m]:>2s}  "
              + "  ".join(f"{d[c]:10.2f}" for c in CONDITIONS)
              + f"   {nuisance:8.2f}  {wanted:6.2f}")
    return 0


if __name__ == "__main__":
    default = [os.path.join(ROOT, "demo", "wavs", n) for n in ("baseline_zira.wav",
                                                               "baseline_david.wav")]
    sys.exit(main(sys.argv[1:] or default))
