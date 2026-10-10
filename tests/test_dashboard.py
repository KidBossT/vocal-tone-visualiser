"""The dashboard, off-screen: every tab draws, and the review, marks, files, comparison and
corner view work."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tonevis import dashboard as D  # noqa: E402
from tonevis.session import Session  # noqa: E402

from test_session import BASE, CHANGED, PAUSE, USUAL, build_session  # noqa: E402

DEMO = os.path.join(os.path.dirname(__file__), os.pardir, "demo", "wavs")


@pytest.fixture(scope="module")
def app():
    app = QApplication.instance() or QApplication([])
    D.apply_dark_theme(app)
    return app


@pytest.fixture
def dash(app):
    d = D.Dashboard(calibration_seconds=5.0)
    d.confirm_close = False
    d.resize(1200, 800)
    yield d
    d.close()


def with_session(dash, session: Session):
    dash.engine.session = session
    dash.engine.baseline = session.baseline
    dash.review_live_session()
    return session


def test_every_tab_draws(dash):
    for k in range(dash.tabs.count()):
        dash.tabs.setCurrentIndex(k)
        image = dash.grab().toImage()
        assert image.width() > 0


def test_review_finds_changes_and_summarises_a_selection(dash):
    with_session(dash, build_session([USUAL, PAUSE, CHANGED]))
    dash.tabs.setCurrentIndex(1)
    dash._refresh_review(force=True)
    texts = [dash.changes_list.item(k).text() for k in range(dash.changes_list.count())]
    assert any("Pitch higher than usual" in t for t in texts)
    dash.review_map.select(35.0, 50.0)
    assert "louder than usual" in dash.summary_label.text()
    assert dash.detail_view.timeline.t and dash.detail_view.history > 14
    dash.tabs.widget(1).grab()


def test_two_stretches_can_be_compared(dash):
    session = with_session(dash, build_session([USUAL, PAUSE, CHANGED]))
    dash.review_map.select(5.0, 25.0)
    dash._set_a()
    dash.review_map.select(35.0, 50.0)
    dash._set_b()
    dialog = dash.compare_ranges()
    assert dialog is not None
    dialog.grab()
    dialog.close()
    words = D.compare_in_words(session, (5.0, 25.0), (35.0, 50.0))
    assert words.startswith("B compared with A:") and "pitch higher" in words


def test_marks_and_notes(dash):
    session = with_session(dash, build_session([USUAL, PAUSE, CHANGED]))
    dash.add_mark()
    assert len(session.markers) == 1
    dash._refresh_review(force=True)
    dash.set_mark_note(0, "  the question about work  ")
    assert session.markers[0].note == "the question about work"
    assert "the question about work" in dash.marks_list.item(0).text()


def test_save_and_open_a_session(dash, tmp_path):
    with_session(dash, build_session([USUAL, PAUSE, CHANGED]))
    path = str(tmp_path / "s.tonevis")
    dash.save_session(path)
    dash.open_session(path)
    assert not dash.review_is_live
    assert dash.review_session.frame_count == dash.engine.session.frame_count
    summary = tmp_path / "summary.txt"
    dash.export_summary(str(summary))
    assert "What changed" in summary.read_text(encoding="utf-8")


def test_baselines_save_load_and_learn(dash, tmp_path):
    dash.engine.use_baseline(BASE)
    path = str(tmp_path / "b.json")
    dash.save_baseline(path)
    dash.engine.recalibrate()
    assert dash.engine.baseline is None
    dash.load_baseline(path)
    assert dash.engine.baseline == BASE
    dash.baseline_from_recording(os.path.join(DEMO, "baseline_david.wav"))
    assert dash.engine.baseline.pitch_hz == pytest.approx(89, rel=0.05)
    assert "middle pitch" in dash.baseline_text.text()


def test_a_recording_can_be_analysed_for_review(dash):
    session = dash.analyse_recording(os.path.join(DEMO, "session_demo.wav"))
    assert session.baseline is not None                  # calibrated on its own first seconds
    texts = [dash.changes_list.item(k).text() for k in range(dash.changes_list.count())]
    assert any("Pitch higher than usual" in t for t in texts)
    assert any("Louder than usual" in t for t in texts)


def test_comparison_tab_shows_the_takes(dash):
    dash._use_demo_takes()
    assert dash.run_comparison(play=False)
    assert len(dash.compare_grid.views) == 4
    assert "A = take_a.wav" in dash.compare_numbers.text()
    dash.tabs.setCurrentIndex(2)
    dash.grab()


def test_corner_view_opens_and_hides(dash):
    dash.corner_button.setChecked(True)
    assert dash.corner is not None and dash.corner.isVisible()
    dash.corner.grab()
    dash.corner_button.setChecked(False)
    assert not dash.corner.isVisible()


def run_event_loop(ms):
    """Let the app run for a while. (QTest.qWait holds Python's lock the whole time, which
    starves the analysis thread; a real event loop releases it, as the app does.)"""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def test_live_tab_plays_a_file_through_the_whole_pipeline(dash):
    assert dash.start_listening(file_path=os.path.join(DEMO, "take_c.wav"), mute=True)
    run_event_loop(2500)
    assert dash.engine.session.frame_count > 180          # keeps up with real time
    assert dash.live_view.timeline.t
    dash.tabs.setCurrentIndex(0)
    dash.grab()
    dash.stop_listening()
    assert not dash.engine.running


# ---- making it self-explanatory and easier to use ------------------------------------------

def test_start_card_shows_until_something_happens(dash):
    dash._tick()
    assert not dash.start_card.isHidden()                  # an empty dashboard says what to do
    with_session(dash, build_session([USUAL]))
    dash._tick()
    assert dash.start_card.isHidden()


def test_h_hides_and_shows_the_key(dash):
    dash.tabs.setCurrentIndex(D.LIVE)
    assert not dash.side_panel.isHidden()
    dash.toggle_side_panel()
    assert dash.side_panel.isHidden()
    assert not dash.panel_button.isChecked() and not dash.side_panel_check.isChecked()
    dash.toggle_side_panel()
    assert not dash.side_panel.isHidden() and dash.panel_button.isChecked()


def test_numbers_are_left_out_unless_asked_for(dash, tmp_path):
    with_session(dash, build_session([USUAL, PAUSE, CHANGED]))
    dash.set_show_numbers(False)
    dash.tabs.setCurrentIndex(D.REVIEW)
    texts = [dash.changes_list.item(k).text() for k in range(dash.changes_list.count())]
    assert any("Pitch higher than usual" in t for t in texts)
    assert not any("semitones" in t or " dB" in t or "×" in t for t in texts)
    dash.review_map.select(35.0, 50.0)
    assert "louder than usual" in dash.summary_label.text()
    assert "dB" not in dash.summary_label.text()
    path = tmp_path / "plain.txt"
    dash.export_summary(str(path))
    assert "semitones" not in path.read_text(encoding="utf-8")
    dash.set_show_numbers(True)
    texts = [dash.changes_list.item(k).text() for k in range(dash.changes_list.count())]
    assert any("semitones" in t for t in texts)
    assert all(c.isChecked() for c in (dash.review_numbers_check, dash.compare_numbers_check,
                                       dash.setup_numbers_check))


def test_a_mark_with_a_note_from_the_live_tab(dash):
    session = with_session(dash, build_session([USUAL, PAUSE, CHANGED]))
    dash.add_mark_with_note()
    assert len(session.markers) == 1
    dash.note_edit.setText("  asked about work  ")
    dash.save_note()
    assert session.markers[0].note == "asked about work"
    assert "asked about work" in dash.live_marks.item(0).text()
    assert dash.note_edit.text() == ""


def test_new_session_keeps_the_baseline(dash):
    old = with_session(dash, build_session([USUAL]))
    dash.new_session_clicked()
    assert dash.engine.session is not old and dash.engine.session.frame_count == 0
    assert dash.engine.baseline == BASE
    assert dash.live_map.session is dash.engine.session


def test_the_demo_plays_in_its_own_session(dash):
    old = with_session(dash, build_session([USUAL]))
    assert dash.try_demo(mute=True)
    run_event_loop(1200)
    assert dash._demo_session and dash.engine.session is not old
    assert dash.engine.baseline is None                  # the demo voice is learned afresh
    assert dash.engine.session.frame_count > 50
    dash.stop_listening()
    demo = dash.engine.session
    # Anything real afterwards starts in a new session, not measured against the demo voice.
    assert dash.start_listening(file_path=os.path.join(DEMO, "take_a.wav"), mute=True)
    assert dash.engine.session is not demo and not dash._demo_session
    assert dash.engine.baseline is None
    dash.stop_listening()


class FakeMic:
    """Stands in for the microphone: plays take_a.wav silently, in real time."""

    def __new__(cls, q, device=None):
        from tonevis import audio
        source = audio.FileSource(q, os.path.join(DEMO, "take_a.wav"), mute=True)
        source.kind = "mic"
        source.name = "Fake microphone"
        return source


def test_recording_takes_without_typing_commands(dash, tmp_path, monkeypatch):
    from tonevis import audio
    from tonevis.takes import take_seconds
    monkeypatch.setattr(audio, "MicSource", FakeMic)
    recorder = dash.open_take_recorder(str(tmp_path))
    assert recorder.toggle("baseline")                   # Record
    assert dash.engine.running and recorder.current == "baseline"
    run_event_loop(1400)
    recorder.toggle("baseline")                           # Stop
    assert not dash.engine.running
    assert take_seconds(str(tmp_path / "baseline.wav")) > 1.0
    assert recorder.toggle("a")
    run_event_loop(900)
    recorder.stop()
    assert take_seconds(str(tmp_path / "a.wav")) > 0.5
    assert recorder.status_labels["a"].text().startswith("Very short")   # a slip is flagged
    assert recorder.toggle("a")                           # record it again, longer
    run_event_loop(1800)
    recorder.stop()
    assert recorder.status_labels["a"].text().startswith("Recorded")
    assert dash.use_takes_from(str(tmp_path))
    assert dash.compare_files["A"].endswith("a.wav") and dash.compare_files["B"] == ""
    recorder.close()


def test_record_file_from_the_command_line(dash, tmp_path, monkeypatch):
    from tonevis import audio
    monkeypatch.setattr(audio, "MicSource", FakeMic)
    target = tmp_path / "take.wav"
    dash.pending_record_path = str(target)
    assert dash.start_listening()
    run_event_loop(700)
    dash.stop_listening()
    assert target.is_file() and dash.pending_record_path is None


def test_settings_are_remembered(app, tmp_path):
    path = str(tmp_path / "settings.ini")
    first = D.Dashboard(settings_path=path)
    first.confirm_close = False
    first.set_show_numbers(True)
    first.set_side_panel(False)
    first.live_seconds_spin.setValue(20)
    first.cal_seconds.setValue(25)
    first.close()
    second = D.Dashboard(settings_path=path)
    second.confirm_close = False
    assert second.show_numbers and second.side_panel.isHidden()
    assert second.live_seconds == 20 and second.engine.calibration_seconds == 25
    second.close()
    text = open(path, encoding="utf-8").read()
    assert "show_numbers" in text and "wav" not in text      # choices only, never sound


def test_compare_rows_show_file_names(dash):
    dash._use_demo_takes()
    assert dash.compare_paths["A"].text() == "take_a.wav"
    assert dash.compare_paths["A"].toolTip().endswith("take_a.wav")
    assert os.path.isabs(dash.compare_files["A"])


def test_the_live_view_explains_itself(dash):
    from PySide6.QtCore import QPoint
    view = dash.live_view
    view.resize(800, 400)
    r = view.layout_rects()

    def at(rect):
        return view.explain(QPoint(int(rect.center().x()), int(rect.center().y())))
    assert "Pace" in at(r.pace)
    assert "syllable" in at(r.lane)
    assert "pitch" in at(r.plot)



# ---- one clean screen (session 6) ------------------------------------------------------------

def test_live_starts_as_one_clean_screen(dash):
    assert dash.details.isHidden()                       # signal rows and session strip: opt-in
    assert dash.marks_card.isHidden()                    # marks appear once there is one
    dash.set_details(True)
    assert not dash.details.isHidden() and dash.details_action.isChecked()
    assert dash.details_check.isChecked()
    dash.set_details(False)
    assert dash.details.isHidden()


def test_the_steps_say_where_you_are(dash):
    dash._update_chips()
    assert dash.steps.highlight == 0 and "1  Start listening" in dash.steps.items[0][1]
    assert dash.start_listening(file_path=os.path.join(DEMO, "take_a.wav"), mute=True)
    run_event_loop(500)
    dash._update_chips()
    assert dash.steps.highlight == 1 and "Learning their usual voice" in dash.steps.items[1][1]
    dash.stop_listening()


def test_a_mark_shows_the_marks_card(dash):
    with_session(dash, build_session([USUAL, PAUSE, CHANGED]))
    dash.add_mark()
    dash._refresh_review(force=True)
    assert not dash.marks_card.isHidden()


def test_plain_words_in_the_controls(dash):
    texts = {dash.tabs.tabText(k) for k in range(dash.tabs.count())}
    assert "Look back" in texts and "Review" not in texts and "Setup" not in texts
    assert dash.corner_button.text() == "Mini window"
