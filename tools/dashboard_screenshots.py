"""Makes the dashboard pictures used in the README and the portfolio, off-screen.

    .venv\\Scripts\\python.exe tools\\dashboard_screenshots.py [output folder]

Everything in the pictures is drawn by the app itself from demo/wavs/session_demo.wav (the
synthetic voices), so the pictures can be remade whenever the look changes. The default output
folder is docs/img. Nothing is played aloud and the microphone is not used.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # no windows pop up
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")   # real fonts off-screen

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QEventLoop, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tonevis import audio, theme  # noqa: E402
from tonevis.dashboard import (COMPARE, GUIDE, LIVE, REVIEW, SETUP, Dashboard,  # noqa: E402
                               apply_dark_theme)
from tonevis.prosody import analyse_samples  # noqa: E402
from tonevis.session import Session, Timeline  # noqa: E402

DEMO = os.path.join(ROOT, "demo", "wavs", "session_demo.wav")
LIVE_END = 50.4          # seconds into session_demo.wav: the end of take B and all of take C


def settle(ms: int = 150) -> None:
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def up_to(rec, end: float):
    """The session and live timeline as they were `end` seconds in."""
    session, timeline = Session(), Timeline()
    for pf in rec.frames:
        if pf.t <= end:
            session.add_frame(pf)
            timeline.add_frame(pf)
    for ev in rec.events:
        if ev[0] == "calibrated":
            continue
        last = ev[2] if ev[0] == "pause" else ev[1]
        if last <= end:
            session.add_event(ev)
            timeline.add_event(ev)
    session.set_baseline(rec.stats, 0.0)
    session.sources.append("session_demo.wav")
    return session, timeline


def main() -> int:
    out = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "img"))
    os.makedirs(out, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    apply_dark_theme(app)
    app.setFont(theme.ui_font(10.0))

    def save(widget, name: str) -> None:
        settle()
        path = os.path.join(out, name)
        widget.grab().save(path)
        print("wrote", os.path.relpath(path, ROOT))

    d = Dashboard(calibration_seconds=15.0, live_seconds=15.0)
    d.confirm_close = False
    d.resize(1440, 900)
    d.show()
    settle(300)
    save(d, "dashboard_start.png")

    x, rate = audio.load_mono(DEMO)
    rec = analyse_samples(x, rate, name="session_demo.wav")

    # Live: part-way through the demo, with two marks.
    session, timeline = up_to(rec, LIVE_END)
    session.add_marker(37.4, "long pause after 'sleeping'")
    session.add_marker(46.6)
    d.engine.session, d.engine.live, d.engine.baseline = session, timeline, rec.stats
    d._attach_views()
    d._refresh_baseline_text()
    d._refresh_review(force=True)
    d._update_chips()
    d.tabs.setCurrentIndex(LIVE)
    save(d, "dashboard_live.png")
    d.set_side_panel(False)
    save(d, "dashboard_live_no_key.png")
    d.set_side_panel(True)

    d.corner_button.setChecked(True)
    d.corner.resize(640, 400)
    save(d.corner, "corner_view.png")
    d.corner.resize(400, 250)                 # the H legend, at the smallest usual size
    d.corner.show_help = True
    save(d.corner, "help.png")
    d.corner.show_help = False
    d.corner_button.setChecked(False)

    # Review: the whole demo session.
    whole = Session.from_recording(rec, "session_demo.wav")
    whole.add_marker(37.4, "long pause after 'sleeping'")
    whole.add_marker(47.2, "faster and louder from here")
    d.engine.session, d.engine.live = whole, Timeline.from_recording(rec)
    d._attach_views()
    d.review_live_session()
    d.tabs.setCurrentIndex(REVIEW)
    d.review_map.select(31.0, 44.6)
    save(d, "dashboard_review.png")
    d.set_show_numbers(True)
    save(d, "dashboard_review_numbers.png")
    d.set_show_numbers(False)
    d.review_map.select(24.0, 30.0)
    d._set_a()
    d.review_map.select(45.4, 50.2)
    d._set_b()
    dialog = d.compare_ranges()
    dialog.resize(1000, 540)
    save(dialog, "dashboard_compare_stretches.png")
    dialog.close()

    d.tabs.setCurrentIndex(COMPARE)
    d._use_demo_takes()
    d.run_comparison(play=False)
    save(d, "dashboard_compare.png")

    recorder = d.open_take_recorder(os.path.join(out, "_takes_preview"))
    recorder.resize(860, 660)
    save(recorder, "record_takes.png")
    recorder.close()

    d.tabs.setCurrentIndex(GUIDE)
    save(d, "dashboard_guide.png")
    d.tabs.setCurrentIndex(SETUP)
    save(d, "dashboard_setup.png")
    d.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
