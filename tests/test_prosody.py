"""Loudness, pauses, syllables and pace, tension and calibration, on synthetic input."""

import math

import numpy as np
import pytest

from tonevis import config as C
from tonevis.baseline import BaselineStats, Calibration, pitch_range
from tonevis.features import spectral_tilt_db, tilt_db
from tonevis.prosody import NucleusDetector, ProsodyAnalyser, analyse_samples
from tonevis.tracker import Frame, PitchTracker

NAN = float("nan")
SR = C.ANALYSIS_RATE


def frame(i, f0=150.0, level=-30.0, floor=-70.0, low=1.0, high=0.05):
    return Frame(i * 0.01 + 0.005, f0, level, floor, low, high)


def run(analyser, frame_list):
    out, events = [], []
    for fr in frame_list:
        pf, ev = analyser.process(fr)
        out.append(pf)
        events += ev
    return out, events


def syllabic(i, rate=4.0, f0=150.0):
    """A voiced frame whose level rises and falls `rate` times a second, 10 dB deep."""
    t = i * 0.01
    return frame(i, f0=f0, level=-38.0 + 10.0 * abs(math.sin(math.pi * rate * t)))


def harmonic(freq, seconds, amp=0.3):
    t = np.arange(int(seconds * SR)) / SR
    x = sum(np.sin(2 * np.pi * freq * k * t) / k for k in range(1, 12))
    return amp * x / np.max(np.abs(x))


# ---- loudness --------------------------------------------------------------------------------

def test_loudness_follows_level_steps():
    levels = [-40.0] * 100 + [-30.0] * 100 + [-20.0] * 100
    out, _ = run(ProsodyAnalyser(), [frame(i, level=lv) for i, lv in enumerate(levels)])
    for end, expected in ((99, -40.0), (199, -30.0), (299, -20.0)):
        assert out[end].loud_db == pytest.approx(expected, abs=0.3)


def test_loudness_rises_quickly_and_falls_slowly():
    up = run(ProsodyAnalyser(), [frame(i, level=-40.0 if i < 50 else -20.0)
                                 for i in range(60)])[0]
    assert up[50 + 5].loud_db > -21.0             # within 1 dB of the new level after 50 ms
    down = run(ProsodyAnalyser(), [frame(i, level=-20.0 if i < 50 else -40.0)
                                   for i in range(60)])[0]
    assert down[50 + 5].loud_db > -32.0           # still well above it after 50 ms


def test_loudness_steps_from_real_audio():
    t = np.arange(3 * SR) / SR
    amp = np.where(t < 1, 0.01, np.where(t < 2, 0.0316, 0.1))
    tracker, analyser = PitchTracker(), ProsodyAnalyser()
    out, _ = run(analyser, tracker.push(amp * np.sin(2 * np.pi * 200 * t)))
    times = np.array([pf.t for pf in out])

    def loud(at):
        return out[int(np.argmin(np.abs(times - at)))].loud_db
    assert loud(1.9) - loud(0.9) == pytest.approx(10.0, abs=0.5)
    assert loud(2.8) - loud(1.9) == pytest.approx(10.0, abs=0.5)


# ---- pauses ----------------------------------------------------------------------------------

def silence(i):
    return frame(i, f0=NAN, level=-69.0, low=NAN, high=NAN)


def test_a_silence_of_a_quarter_second_or_more_is_a_pause():
    frames = ([silence(i) for i in range(50)]                    # leading silence: not a pause
              + [frame(i) for i in range(50, 150)]
              + [silence(i) for i in range(150, 300)]            # 1.5 s pause
              + [frame(i) for i in range(300, 400)])
    out, events = run(ProsodyAnalyser(), frames)
    pauses = [ev for ev in events if ev[0] == "pause"]
    assert len(pauses) == 1
    _, start, end = pauses[0]
    onset = (C.SPEECH_MIN_VOICED - 1) * C.FRAME_STEP   # voice counts as speech from its 3rd frame
    assert start == pytest.approx(1.505) and end == pytest.approx(3.005 + onset)
    since = [pf.pause_since for pf in out]
    assert math.isnan(since[170]) and since[175] == pytest.approx(1.505)   # confirmed at 0.25 s
    resumed = 300 + C.SPEECH_MIN_VOICED - 1
    assert all(math.isnan(s) for s in since[:150]) and math.isnan(since[resumed])


def test_a_short_silence_inside_speech_is_not_a_pause_and_counts_as_speaking():
    frames = ([frame(i) for i in range(100)] + [silence(i) for i in range(100, 115)]
              + [frame(i) for i in range(115, 200)])
    analyser = ProsodyAnalyser()
    _, events = run(analyser, frames)
    assert not [ev for ev in events if ev[0] == "pause"]
    onset = (C.SPEECH_MIN_VOICED - 1) * C.FRAME_STEP   # the very first 20 ms of voice
    assert analyser.speech_time == pytest.approx(2.0 - onset, abs=0.011)


def test_noise_without_voice_is_never_speech():
    """A fan, clicks, or a laptop mic's noise bursts: loud, but never voiced."""
    analyser = ProsodyAnalyser(calibration_seconds=5.0)
    out, events = run(analyser, [frame(i, f0=NAN, level=-35.0 + 5 * (i % 7 == 0), low=NAN,
                                       high=NAN) for i in range(2000)])
    assert analyser.speech_time == 0.0
    assert not events
    assert not analyser.reference.calibrated and analyser.reference.progress == 0.0


def test_consonants_right_after_voice_count_as_speech():
    frames = ([frame(i) for i in range(100)]
              + [frame(i, f0=NAN, level=-40.0, low=NAN, high=NAN) for i in range(100, 120)]
              + [frame(i) for i in range(120, 200)])
    out, events = run(ProsodyAnalyser(), frames)
    assert all(pf.sound for pf in out[100:120])
    assert not [ev for ev in events if ev[0] == "pause"]


def test_breath_noise_far_below_the_speaker_counts_as_silence():
    base = BaselineStats(150, 140, 160, -2, 2, -30.0, 4.0, -12.0, 15.0)
    frames = ([frame(i) for i in range(100)]
              + [frame(i, f0=NAN, level=-58.0) for i in range(100, 200)]   # 28 dB down
              + [frame(i) for i in range(200, 300)])
    _, events = run(ProsodyAnalyser(baseline=base), frames)
    assert [ev[0] for ev in events if ev[0] == "pause"] == ["pause"]


# ---- syllables and pace ----------------------------------------------------------------------

@pytest.mark.parametrize("rate", [3.0, 4.0, 6.0])
def test_pace_counts_syllables_per_second(rate):
    out, events = run(ProsodyAnalyser(), [syllabic(i, rate) for i in range(600)])
    assert out[-1].rate == pytest.approx(rate, rel=0.08)
    assert len([ev for ev in events if ev[0] == "nucleus"]) == pytest.approx(6 * rate, abs=2)


def test_pauses_do_not_slow_the_pace_down():
    frames, i = [], 0
    for _ in range(4):                                   # 1 s of speech then a 1 s pause, x4
        frames += [syllabic(k) for k in range(i, i + 100)]
        frames += [silence(k) for k in range(i + 100, i + 200)]
        i += 200
    out, _ = run(ProsodyAnalyser(), frames)
    assert out[-1].rate == pytest.approx(4.0, rel=0.12)  # speaking rate, not overall rate


def test_loud_but_unvoiced_peaks_are_not_syllables():
    frames = [frame(i, f0=NAN, level=syllabic(i).level_db, low=NAN, high=NAN)
              for i in range(300)]
    _, events = run(ProsodyAnalyser(), frames)
    assert not [ev for ev in events if ev[0] == "nucleus"]


def test_nucleus_needs_a_two_decibel_dip_on_both_sides():
    det = NucleusDetector()
    hits = [det.update(k * 0.01, v, True, -100.0)
            for k, v in enumerate([-40, -35, -30, -31, -30.5, -33, -40])]
    assert [h for h in hits if h is not None] == [pytest.approx(0.02)]


def test_pace_from_real_audio():
    t = np.arange(5 * SR) / SR
    envelope = 0.1 + 0.9 * np.sin(np.pi * 4 * t) ** 2    # 4 syllable-like swells a second
    x = harmonic(150, 5.0) * envelope
    out, events = run(ProsodyAnalyser(), PitchTracker().push(x))
    rates = [pf.rate for pf in out if not math.isnan(pf.rate)]
    assert rates[-1] == pytest.approx(4.0, rel=0.1)


# ---- tension proxy ---------------------------------------------------------------------------

def test_tilt_is_the_high_to_low_energy_ratio_and_ignores_volume():
    assert tilt_db(1.0, 0.1) == pytest.approx(-10.0)
    assert tilt_db(100.0, 10.0) == pytest.approx(-10.0)
    assert math.isnan(tilt_db(0.0, 1.0))
    frames = [frame(i, low=2.0, high=0.02) for i in range(200)]
    out, _ = run(ProsodyAnalyser(), frames)
    assert out[-1].tilt_db == pytest.approx(-20.0)


def test_tilt_rises_when_the_upper_harmonics_get_stronger():
    t = np.arange(512) / SR
    soft = sum(np.sin(2 * np.pi * 150 * k * t) / k ** 1.5 for k in range(1, 40))
    bright = sum(np.sin(2 * np.pi * 150 * k * t) / k ** 0.8 for k in range(1, 40))
    assert spectral_tilt_db(bright, SR) > spectral_tilt_db(soft, SR) + 6
    assert spectral_tilt_db(0.1 * soft, SR) == pytest.approx(spectral_tilt_db(soft, SR))


# ---- calibration -----------------------------------------------------------------------------

def speech(i, base_hz=150.0):
    fr = syllabic(i, 4.0, f0=base_hz * 2 ** (2 * math.sin(i / 50) / 12))
    return fr


def test_calibration_learns_the_speaker_then_stays_fixed():
    analyser = ProsodyAnalyser(calibration_seconds=10.0)
    progress = []
    events = []
    for i in range(1500):
        _, ev = analyser.process(speech(i))
        events += ev
        progress.append(analyser.reference.progress)
    done = [ev for ev in events if ev[0] == "calibrated"]
    assert len(done) == 1
    stats = done[0][1]
    assert stats.pitch_hz == pytest.approx(150.0, rel=0.02)
    assert stats.rate == pytest.approx(4.0, rel=0.1)
    assert stats.band_low_st < -1.0 < 1.0 < stats.band_high_st
    assert stats.tilt_db == pytest.approx(tilt_db(1.0, 0.05))
    assert analyser.reference.calibrated
    assert all(b >= a for a, b in zip(progress, progress[1:]))       # never goes backwards
    run(analyser, [speech(i, base_hz=250.0) for i in range(1500, 2500)])
    assert analyser.reference.pitch_hz == pytest.approx(150.0, rel=0.02)   # no drift


def test_recalibrating_starts_again():
    analyser = ProsodyAnalyser(calibration_seconds=5.0)
    run(analyser, [speech(i) for i in range(700)])
    assert analyser.reference.calibrated
    analyser.recalibrate()
    assert not analyser.reference.calibrated and analyser.reference.progress == 0.0
    _, events = run(analyser, [speech(i, base_hz=220.0) for i in range(700, 1400)])
    assert [ev[0] for ev in events if ev[0] == "calibrated"] == ["calibrated"]
    assert analyser.reference.pitch_hz == pytest.approx(220.0, rel=0.02)


def test_after_calibration_much_quieter_voice_is_treated_as_background():
    analyser = ProsodyAnalyser(calibration_seconds=5.0)
    run(analyser, [speech(i) for i in range(700)])
    out, _ = run(analyser, [frame(700 + i, level=-68.0, floor=-90.0) for i in range(10)])
    assert all(math.isnan(pf.f0) for pf in out)


def test_calibration_needs_enough_voice():
    cal = Calibration(10.0)
    cal.add_speech_time(2.0)
    with pytest.raises(ValueError):
        cal.stats()


def test_pitch_range_after_calibration():
    stats = BaselineStats(150.0, 130.0, 170.0, -3, 3, -30, 4.0, -12, 15)
    floor, ceiling = pitch_range(stats)
    assert floor == pytest.approx(97.5) and ceiling == pytest.approx(340.0)
    low_voice = BaselineStats(85.0, 80.0, 95.0, -2, 2, -30, 4.0, -12, 15)
    assert pitch_range(low_voice)[0] == pytest.approx(60.0)       # never below 60 Hz


def test_a_baseline_can_be_learned_from_a_recording():
    t = np.arange(8 * SR) / SR
    x = harmonic(180, 8.0) * (0.1 + 0.9 * np.sin(np.pi * 4 * t) ** 2)
    rec = analyse_samples(x, SR, learn_baseline=True)
    assert rec.stats.pitch_hz == pytest.approx(180.0, rel=0.02)
    assert rec.stats.rate == pytest.approx(4.0, rel=0.15)
    assert rec.frames and rec.duration == pytest.approx(8.0)


# ---- the tracker's side of calibration -------------------------------------------------------

def test_narrower_pitch_range_after_calibration_keeps_frames_on_the_grid():
    tracker = PitchTracker()
    x = harmonic(200, 2.0)
    first = tracker.push(x[: SR])
    tracker.set_pitch_range(150.0, 400.0)
    second = tracker.push(x[SR:])
    t = np.array([fr.t for fr in first + second])
    assert np.allclose(np.diff(t), C.FRAME_STEP)
    voiced = np.array([fr.f0 for fr in second])
    assert np.nanmedian(voiced) == pytest.approx(200.0, rel=0.01)


def test_dc_offset_does_not_read_as_sound():
    t = np.arange(2 * SR) / SR
    x = 0.05 + np.where(t < 1, 0.3 * np.sin(2 * np.pi * 200 * t), 0.0)   # 0.05 offset throughout
    frames = PitchTracker().push(x)
    quiet = [fr.level_db for fr in frames if fr.t > 1.3]
    assert max(quiet) < -80.0
