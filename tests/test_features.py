"""Feature extractors on synthetic signals with known answers."""

import math

import numpy as np
import pytest

from tonevis import config as C
from tonevis.audio import StreamResampler
from tonevis.features import rms_db, semitones
from tonevis.tracker import PitchTracker

SR = C.ANALYSIS_RATE


def sine(freq, seconds, sr=SR, amp=0.5):
    t = np.arange(int(round(seconds * sr))) / sr
    return amp * np.sin(2 * np.pi * freq * t)


def track(x, chunk=160):
    tracker = PitchTracker()
    frames = []
    for i in range(0, len(x), chunk):
        frames += tracker.push(x[i:i + chunk])
    return frames


def f0_of(frames):
    return np.array([fr.f0 for fr in frames])


# ---- pitch ---------------------------------------------------------------------------------

@pytest.mark.parametrize("freq", [85.0, 120.0, 196.0, 262.0, 440.0])
def test_sine_gives_its_own_frequency(freq):
    f0 = f0_of(track(sine(freq, 1.5)))
    voiced = f0[~np.isnan(f0)]
    assert voiced.size >= 0.9 * f0.size
    assert np.max(np.abs(voiced / freq - 1.0)) < 0.01       # every frame within 1 %


def test_silence_has_no_pitch():
    frames = track(np.zeros(SR))
    assert len(frames) > 50
    assert np.all(np.isnan(f0_of(frames)))


def test_quiet_noise_has_no_pitch():
    rng = np.random.default_rng(1)
    f0 = f0_of(track(0.01 * rng.standard_normal(2 * SR)))
    assert np.mean(~np.isnan(f0)) < 0.02


def test_steady_hum_is_gated_out_but_a_louder_voice_is_not():
    """Mains hum is perfectly periodic, so only the level gate can stop it being drawn.
    Starts with exact digital zeros, as some laptop mics send, which must not break the gate."""
    t = np.arange(3 * SR) / SR
    wobble = 1 + 0.3 * np.sin(2 * np.pi * 0.7 * t)                   # hum level drifts +-3 dB
    hum = 10 ** (-55 / 20) * np.sqrt(2) * wobble * np.sin(2 * np.pi * 100 * t)   # -55 dBFS
    x = np.concatenate([np.zeros(SR // 2), hum, sine(200, 1.0, amp=0.1)])       # voice -23 dBFS
    frames = track(x)
    ft = np.array([fr.t for fr in frames])
    f0 = f0_of(frames)
    hum_part = (ft > 0.6) & (ft < 3.4)
    assert np.mean(~np.isnan(f0[hum_part])) < 0.02
    voice = f0[ft > 3.6]
    assert np.mean(~np.isnan(voice)) > 0.9
    assert np.nanmedian(voice) == pytest.approx(200, rel=0.01)


def test_pitch_stops_during_a_gap_and_returns_after():
    x = np.concatenate([sine(150, 0.8), np.zeros(int(0.6 * SR)), sine(150, 0.8)])
    frames = track(x)
    t = np.array([fr.t for fr in frames])
    f0 = f0_of(frames)
    in_gap = (t > 0.85) & (t < 1.35)
    assert np.all(np.isnan(f0[in_gap]))
    after = t > 1.5
    assert np.nanmedian(f0[after]) == pytest.approx(150, rel=0.01)


def test_frames_are_every_10_ms_and_recent():
    x = sine(150, 1.0)
    frames = PitchTracker().push(x)
    t = np.array([fr.t for fr in frames])
    assert np.allclose(np.diff(t), C.FRAME_STEP)
    # the newest frame is at most one hop plus Praat's half-window behind the input
    assert len(x) / SR - t[-1] <= C.HOP + 0.030


@pytest.mark.parametrize("chunk", [1, 37, 441, 1600])
def test_block_size_does_not_change_the_result(chunk):
    x = np.concatenate([sine(150, 0.5), np.zeros(SR // 4), sine(210, 0.5)])
    reference = track(x, chunk=160)
    got = track(x, chunk=chunk)
    assert [fr.t for fr in got] == [fr.t for fr in reference]
    np.testing.assert_array_equal(f0_of(got), f0_of(reference))


def test_pitch_survives_the_48k_microphone_path():
    x = sine(180, 1.2, sr=48_000)
    resampler = StreamResampler(48_000, SR)
    tracker = PitchTracker(time_offset=-resampler.delay_seconds)
    frames = []
    for i in range(0, len(x), 480):                   # 10 ms blocks, like the sound card
        frames += tracker.push(resampler.process(x[i:i + 480]))
    voiced = f0_of(frames)[~np.isnan(f0_of(frames))]
    assert voiced.size >= 0.9 * len(frames)
    assert np.max(np.abs(voiced / 180 - 1.0)) < 0.01


def test_flush_reports_the_end_of_a_stream():
    tracker = PitchTracker()
    x = sine(150, 1.0)
    frames = tracker.push(x) + tracker.flush()
    assert frames[-1].t >= 1.0                         # nothing at the end is lost


# ---- helpers -------------------------------------------------------------------------------

def test_rms_db_of_known_signals():
    assert rms_db(np.ones(1000)) == pytest.approx(0.0, abs=1e-9)
    assert rms_db(sine(1000, 1.0, amp=1.0)) == pytest.approx(-3.01, abs=0.01)
    assert rms_db(0.5 * np.ones(100)) == pytest.approx(-6.02, abs=0.01)
    assert rms_db(np.zeros(100)) == -120.0
    assert rms_db(np.zeros(0)) == -120.0


def test_semitones():
    assert semitones(220.0, 110.0) == pytest.approx(12.0)
    assert semitones(110.0, 220.0) == pytest.approx(-12.0)
    assert semitones(110.0 * 2 ** (3 / 12), 110.0) == pytest.approx(3.0)
    assert math.isnan(semitones(math.nan, 110.0))
