"""The session store: evidence in words, what changed, files, and the no-verdict rule."""

import ast
import math
import os
import re
import time

import numpy as np
import pytest
import soundfile as sf

import tonevis
from tonevis import config as C
from tonevis.baseline import BaselineStats
from tonevis.engine import Engine
from tonevis.prosody import ProsodyFrame
from tonevis.session import Session, clock, speaking_mask

NAN = float("nan")
BASE = BaselineStats(pitch_hz=150.0, q1_hz=140.0, q3_hz=160.0, band_low_st=-3.0,
                     band_high_st=3.0, level_db=-30.0, rate=4.0,
                     tilt_db=10 * math.log10(0.05), speech_seconds=15.0)


def build_session(parts, pause_every=None):
    """parts: list of (seconds, pitch_st, loud_db, syllables_per_s, high_energy, silent).
    Voiced speech, with a syllable event at the given rate; silent parts are pauses."""
    s = Session()
    s.set_baseline(BASE, 0.0)
    t = 0.0
    for seconds, st, loud, rate, high, silent in parts:
        n = int(round(seconds / C.FRAME_STEP))
        start = t
        for k in range(n):
            ft = t + k * C.FRAME_STEP
            if silent:
                since = start if ft - start + C.FRAME_STEP >= C.PAUSE_MIN else NAN
                pf = ProsodyFrame(ft, NAN, -70.0, False, since, NAN, NAN)
            else:
                # pitch moves about as much as the baseline's usual range (-3..+3 semitones)
                f0 = 150.0 * 2 ** ((st + 3.15 * math.sin(ft * 7)) / 12)
                pf = ProsodyFrame(ft, f0, BASE.level_db + loud, True, NAN, NAN, NAN, 1.0, high)
            s.add_frame(pf)
        if silent:
            s.add_event(("pause", start, start + seconds))
        else:
            for k in range(int(seconds * rate)):
                s.add_event(("nucleus", start + (k + 0.5) / rate))
        t += seconds
    return s


USUAL = (30.0, 0.0, 0.0, 4.0, 0.05, False)
CHANGED = (20.0, 3.0, 8.0, 6.0, 0.12, False)      # higher, louder, faster, more pressed
PAUSE = (3.5, 0, 0, 0, 0, True)


def test_speaking_time_counts_short_gaps_but_not_pauses_or_the_edges():
    # silence 0-29 | speech 30-79 | 0.1 s gap 80-89 | speech 90-139 | 0.4 s pause 140-179 |
    # speech 180-199 | silence 200-204
    sound = np.array([0] * 30 + [1] * 50 + [0] * 10 + [1] * 50 + [0] * 40 + [1] * 20 + [0] * 5,
                     dtype=bool)
    mask = speaking_mask(sound)
    assert mask[30:140].all()                   # the 10-frame gap inside speech counts
    assert not mask[:30].any() and not mask[200:].any()     # the edges do not
    assert not mask[140:180].any()              # a 0.4 s pause does not
    assert mask[180:200].all()


def test_a_stretch_is_described_in_words_about_the_voice():
    s = build_session([USUAL, PAUSE, CHANGED])
    usual = s.summarise(0.0, 30.0)
    assert usual.phrases(BASE) == ["voice much as usual"]
    changed = s.summarise(33.5, 53.5)
    assert changed.pitch_st == pytest.approx(3.0, abs=0.2)
    assert changed.loud_db == pytest.approx(8.0, abs=0.1)
    assert changed.pace == pytest.approx(1.5, rel=0.05)
    assert changed.tilt_db == pytest.approx(10 * math.log10(0.12 / 0.05), abs=0.05)
    words = changed.sentence(BASE)
    for expected in ("Pitch higher than usual", "louder than usual", "faster than usual",
                     "voice more pressed than usual"):
        assert expected in words
    whole = s.summarise(0.0, 53.5)
    assert whole.long_pauses == 1 and whole.longest_pause == pytest.approx(3.5)


def test_too_little_speech_is_not_compared():
    s = build_session([(1.0, 5.0, 10.0, 4.0, 0.2, False)])
    assert s.summarise(0.0, 1.0).phrases(BASE) == ["too little speech here to compare"]


def test_what_changed_finds_the_changed_stretch_and_nothing_else():
    s = build_session([USUAL, PAUSE, CHANGED])
    changes = s.find_changes()
    kinds = {(c.signal, c.direction) for c in changes}
    assert kinds == {("pitch", 1), ("loudness", 1), ("pace", 1), ("voice quality", 1),
                     ("pause", 1)}
    for c in changes:
        if c.signal != "pause":
            assert c.start >= 33.0, c           # nothing reported in the usual stretch
            assert c.end <= 53.6
    pause = next(c for c in changes if c.signal == "pause")
    assert pause.text == "Pause of 3.5 s"


def test_a_quieter_softer_stretch_is_reported_as_such():
    quiet = (20.0, 0.0, -9.0, 4.0, 0.02, False)
    changes = build_session([USUAL, quiet]).find_changes()
    texts = " ".join(c.text for c in changes)
    assert "Quieter than usual" in texts and "Voice softer or breathier" in texts


def test_no_baseline_means_no_evidence():
    s = build_session([USUAL])
    s.set_baseline(None)
    assert s.summarise(0, 10) is None
    assert s.find_changes() == []
    assert "No baseline yet" in s.report()


def test_saved_sessions_hold_numbers_only_and_come_back_the_same(tmp_path):
    s = build_session([USUAL, PAUSE, CHANGED])
    s.add_marker(40.0, "talked about work")
    path = tmp_path / "session.tonevis"
    s.save(str(path))
    with np.load(path, allow_pickle=False) as z:
        assert "audio" not in z.files and "samples" not in z.files
    back = Session.load(str(path))
    assert back.frame_count == s.frame_count
    assert back.end_time == pytest.approx(s.end_time)
    assert back.baseline == BASE
    assert [(m.t, m.note) for m in back.markers] == [(40.0, "talked about work")]
    assert len(back.nuclei) == len(s.nuclei) and back.pauses == s.pauses
    assert [c.text for c in back.find_changes()] == [c.text for c in s.find_changes()]


def test_loading_something_else_fails_clearly(tmp_path):
    bad = tmp_path / "not_a_session.tonevis"
    bad.write_bytes(b"hello")
    with pytest.raises(ValueError):
        Session.load(str(bad))


def test_baselines_round_trip_as_json():
    assert BaselineStats.from_json(BASE.to_json()) == BASE
    nan_rate = BaselineStats(150, 140, 160, -3, 3, -30, NAN, NAN, 15)
    back = BaselineStats.from_json(nan_rate.to_json())
    assert math.isnan(back.rate) and math.isnan(back.tilt_db)
    with pytest.raises(ValueError):
        BaselineStats.from_json('{"format": "something else"}')


def test_report_lists_changes_and_marks():
    s = build_session([USUAL, PAUSE, CHANGED])
    s.add_marker(45.0, "a note")
    report = s.report()
    assert "What changed:" in report and "Pitch higher than usual" in report
    assert "0:45  a note" in report and C.DISCLAIMER in report


def test_clock_format():
    assert clock(0) == "0:00" and clock(65.4) == "1:05" and clock(3725) == "1:02:05"


# ---- the rule the whole project rests on ---------------------------------------------------

FEELING_WORDS = ("anxious", "anxiety", "angry", "anger", "sad", "sadness", "happy",
                 "happiness", "afraid", "scared", "fear", "fearful", "nervous", "stressed",
                 "stress", "depressed", "depression", "upset", "frustrated", "frustration",
                 "irritated", "calm", "excited", "excitement", "bored", "lying", "deceptive",
                 "deception", "hostile", "emotional", "mood", "edgy", "tense", "worried",
                 "agitated", "distressed", "uneasy", "panic", "panicked", "joy", "joyful",
                 "tired", "relaxed", "confident", "insecure", "guilty", "ashamed", "hesitant",
                 "defensive", "overwhelmed", "embarrassed")


def _app_strings():
    """Every string the app itself contains (not docstrings or comments)."""
    folder = os.path.dirname(tonevis.__file__)
    for name in sorted(os.listdir(folder)):
        if not name.endswith(".py"):
            continue
        tree = ast.parse(open(os.path.join(folder, name), encoding="utf-8").read())
        docstrings = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                body = getattr(node, "body", [])
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    docstrings.add(id(body[0].value))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                    and id(node) not in docstrings):
                yield name, node.value


def _feeling_words_in(text):
    return [w for w in FEELING_WORDS if re.search(rf"\b{w}\b", text, re.IGNORECASE)]


def test_the_app_never_names_a_feeling():
    found = [(name, s[:60], _feeling_words_in(s)) for name, s in _app_strings()
             if _feeling_words_in(s)]
    assert not found, found


def test_generated_evidence_never_names_a_feeling():
    rng = np.random.default_rng(0)
    for _ in range(40):
        part = (10.0, float(rng.uniform(-6, 6)), float(rng.uniform(-12, 12)),
                float(rng.uniform(2, 7)), float(rng.uniform(0.01, 0.3)), False)
        s = build_session([USUAL, PAUSE, part])
        texts = [s.report()] + [c.text for c in s.find_changes()]
        texts += s.summarise(33.5, 43.5).phrases(BASE)
        for text in texts:
            assert not _feeling_words_in(text), text


# ---- the engine, without any window ----------------------------------------------------------

def test_engine_runs_a_file_into_a_session(tmp_path):
    t = np.arange(3 * 16_000) / 16_000
    x = 0.3 * np.sin(2 * np.pi * 180 * t) * (0.2 + 0.8 * np.sin(np.pi * 4 * t) ** 2)
    path = tmp_path / "voice.wav"
    sf.write(str(path), x, 16_000)
    engine = Engine(calibration_seconds=5.0)
    engine.start(file_path=str(path), mute=True)
    deadline = time.perf_counter() + 8.0
    while time.perf_counter() < deadline and not engine.worker.finished:
        engine.drain()
        time.sleep(0.05)
    engine.stop()
    session = engine.session
    assert session.frame_count > 200
    f0 = np.array(session._cols["f0"])
    assert np.nanmedian(f0) == pytest.approx(180, rel=0.02)
    assert engine.now() == pytest.approx(session.end_time)
    # a second run is laid after the first, with a gap
    engine.start(file_path=str(path), mute=True)
    assert engine.offset == pytest.approx(session.end_time + 1.0)
    engine.stop()
