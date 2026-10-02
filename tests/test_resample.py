"""The block-by-block resampler must match scipy's one-shot resampler exactly."""

from math import gcd

import numpy as np
import pytest
from scipy.signal import resample_poly

from tonevis.audio import StreamResampler

OUT = 16_000


def in_random_blocks(x, rng):
    i = 0
    while i < len(x):
        n = int(rng.integers(1, 1200))
        yield x[i:i + n]
        i += n


@pytest.mark.parametrize("rate_in", [48_000, 44_100, 32_000, 22_050, 8_000])
def test_streaming_matches_offline(rate_in):
    rng = np.random.default_rng(rate_in)
    x = rng.standard_normal(rate_in)                  # one second of noise
    rs = StreamResampler(rate_in, OUT)
    y = np.concatenate([rs.process(b) for b in in_random_blocks(x, rng)])
    g = gcd(rate_in, OUT)
    ref = resample_poly(x, OUT // g, rate_in // g)
    delay = int(round(rs.delay_seconds * OUT))        # whole output samples for these rates
    assert delay == pytest.approx(rs.delay_seconds * OUT)
    n = len(ref) - 2 * delay                          # the tail of `ref` assumes future zeros
    np.testing.assert_allclose(y[delay:delay + n], ref[:n], rtol=0, atol=1e-9)


def test_same_rate_passes_through():
    rs = StreamResampler(OUT, OUT)
    x = np.arange(10.0)
    np.testing.assert_array_equal(rs.process(x), x)
    assert rs.delay_seconds == 0.0


def test_speech_band_passes_and_aliases_are_removed():
    t = np.arange(48_000) / 48_000
    rs = StreamResampler(48_000, OUT)
    tone = rs.process(np.sin(2 * np.pi * 1000 * t))[200:]      # 1 kHz: keep
    alias = rs.process(np.sin(2 * np.pi * 11_000 * t))[200:]   # 11 kHz: would fold to 5 kHz
    assert np.sqrt(np.mean(tone ** 2)) == pytest.approx(np.sqrt(0.5), rel=0.01)
    assert 20 * np.log10(np.sqrt(np.mean(alias ** 2)) / np.sqrt(0.5)) < -40
