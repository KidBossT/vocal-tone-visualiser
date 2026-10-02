"""The clock mapping that the latency measurement and the scrolling depend on."""

import numpy as np
import pytest

from tonevis.tracker import StreamClock


def test_microphone_clock_ignores_late_callbacks():
    rng = np.random.default_rng(0)
    clock = StreamClock("min")
    true_offset = 1000.0                           # wall time = stream time + 1000 s
    for k in range(300):
        s = k * 0.01
        late = rng.uniform(0.0, 0.004)             # callbacks run 0-4 ms late
        clock.add(s + true_offset + late, s)
    assert clock.offset == pytest.approx(true_offset, abs=0.0005)
    assert clock.wall(5.0) == pytest.approx(1005.0, abs=0.0005)
    assert clock.stream_now(1005.0) == pytest.approx(5.0, abs=0.0005)


def test_playback_clock_ignores_early_callbacks():
    rng = np.random.default_rng(1)
    clock = StreamClock("max")
    for k in range(300):
        s = k * 0.01
        early = rng.uniform(0.0, 0.004)
        clock.add(s + 50.0 - early, s)
    assert clock.offset == pytest.approx(50.0, abs=0.0005)


def test_clock_follows_slow_drift():
    clock = StreamClock("min")
    for k in range(2000):                          # 20 s with 0.1 % drift
        s = k * 0.01
        clock.add(s * 1.001 + 7.0, s)
    assert clock.offset == pytest.approx(19.99 * 0.001 + 7.0, abs=0.004)
