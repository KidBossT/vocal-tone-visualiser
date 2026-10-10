"""Recording your own takes for the comparison, without typing any commands.

One person, one microphone: first about 30 seconds of their ordinary talk (the baseline), then
the same sentence four ways (A to D). Each recording is saved in demo/takes, where the Compare
tab and run_demo.bat pick it up. While recording, the display shows the take against the
baseline, so a take that did not come out as planned can be spotted and recorded again at once.

The directions describe how to speak (slow, loud, flat...), never a feeling to act.
"""

from __future__ import annotations

import math
import os
import time

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QComboBox, QDialog, QGridLayout, QHBoxLayout, QMessageBox,
                               QVBoxLayout)

from . import theme as T
from .display import ToneView
from .session import Timeline

SENTENCE = "I've been sleeping better, and work has been fine this week."

TAKES = (
    ("baseline", "Usual voice", "About 30 seconds of their ordinary talk: their week, travel, food, "
                             "the weekend. Everything else is compared with this."),
    ("a", "A", "The sentence, even and steady."),
    ("b", "B", "The sentence slowly, with long pauses (count to two in your head); let the ends "
               "of phrases rise."),
    ("c", "C", "The sentence fast and loud, pushing the words out."),
    ("d", "D", "The sentence flat and quiet, with very little up and down."),
)


def take_seconds(path: str) -> float | None:
    """Length of a recorded take, or None if there is none."""
    if not os.path.isfile(path):
        return None
    try:
        import soundfile as sf
        return float(sf.info(path).duration)
    except Exception:
        return None


class TakeRecorder(QDialog):
    def __init__(self, dashboard, takes_dir: str):
        super().__init__(dashboard)
        self.dashboard = dashboard
        self.takes_dir = takes_dir
        self.current: str | None = None
        self.started_at = 0.0
        self.setWindowTitle("Record your own takes")
        self.setModal(False)
        engine = dashboard.engine

        v = QVBoxLayout(self)
        v.setContentsMargins(18, 16, 18, 14)
        v.setSpacing(10)
        v.addWidget(T.label("Record your own takes", "pageTitle"))
        v.addWidget(T.label(
            "One person, one microphone about 50 cm away, a quiet room. Record their usual "
            "voice first: the app learns the voice from it, then shows each take against it. For A to "
            f"D the person says: “{SENTENCE}”", "pageText", wrap=True))

        mic_row = QHBoxLayout()
        mic_row.addWidget(T.label("Microphone", "secondary"))
        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(260)
        source = dashboard.mic_combo
        for k in range(source.count()):
            self.mic_combo.addItem(source.itemText(k), source.itemData(k))
        self.mic_combo.setCurrentIndex(source.currentIndex())
        self.mic_combo.currentIndexChanged.connect(source.setCurrentIndex)
        mic_row.addWidget(self.mic_combo, 1)
        self.meter = T.LevelMeter()
        self.meter.setFixedWidth(120)
        mic_row.addWidget(self.meter)
        v.addLayout(mic_row)

        self._empty = Timeline()           # shown until a take is being recorded
        self.view = ToneView(self._empty, lambda: engine.reference, history=10.0,
                             show_disclaimer=False)
        self.view.now_fn = engine.now
        self.view.setMinimumHeight(150)
        self.view.status_message = "Press Record next to a take"
        v.addWidget(self.view, 1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(8)
        self.status_labels = {}
        self.record_buttons = {}
        for row, (key, name, direction) in enumerate(TAKES):
            grid.addWidget(T.label(name, "cardTitle"), row, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(T.label(direction, "secondary", wrap=True), row, 1)
            status = T.label("", "dim")
            status.setMinimumWidth(150)
            grid.addWidget(status, row, 2)
            record = T.button("Record", f"Record {name}", icon_name="record")
            record.setMinimumWidth(96)
            record.clicked.connect(lambda _=False, k=key: self.toggle(k))
            grid.addWidget(record, row, 3)
            self.status_labels[key] = status
            self.record_buttons[key] = record
        grid.setColumnStretch(1, 1)
        v.addLayout(grid)
        v.addWidget(T.label("Files are saved in demo/takes. Recording again replaces that take. "
                            "Nothing else is saved.", "dim", wrap=True))

        bottom = QHBoxLayout()
        folder = T.button("Open the folder", icon_name="open")
        folder.clicked.connect(self.open_folder)
        bottom.addWidget(folder)
        bottom.addStretch(1)
        close = T.button("Close")
        close.clicked.connect(self.close)
        bottom.addWidget(close)
        self.compare_button = T.button("Compare them now", primary=True, icon_name="compare")
        self.compare_button.clicked.connect(self.compare_now)
        bottom.addWidget(self.compare_button)
        v.addLayout(bottom)

        self.resize(820, 640)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(50)
        self.refresh()

    def path(self, key: str) -> str:
        return os.path.join(self.takes_dir, f"{key}.wav")

    # ---- recording --------------------------------------------------------------------------

    def toggle(self, key: str) -> bool:
        if self.current == key:
            self.stop()
            return True
        if self.current is not None:
            self.stop()
        return self.record(key)

    def record(self, key: str) -> bool:
        name = dict((k, n) for k, n, _ in TAKES)[key]
        path = self.path(key)
        if os.path.isfile(path) and self.dashboard.confirm_close:
            answer = QMessageBox.question(self, "Record again?",
                                          f"There is already a recording of {name}. Replace it?")
            if answer != QMessageBox.StandardButton.Yes:
                return False
        if key == "baseline":
            # A new baseline means a new voice to learn: start fresh.
            if not self.dashboard.prepare_fresh_session("record a new baseline",
                                                        clear_baseline=True):
                return False
        elif self.dashboard.engine.baseline is None and os.path.isfile(self.path("baseline")):
            try:
                self.dashboard.baseline_from_recording(self.path("baseline"))
            except Exception:
                pass                            # the take still records; it just calibrates live
        os.makedirs(self.takes_dir, exist_ok=True)
        if not self.dashboard.start_listening(device=self.mic_combo.currentData(),
                                              record_path=path):
            return False
        self.current = key
        self.started_at = time.perf_counter()
        self.view.timeline = self.dashboard.engine.live
        self.view.status_message = ""
        self.refresh()
        return True

    def stop(self) -> None:
        key, self.current = self.current, None
        if key is not None:
            self.dashboard.stop_listening()
            seconds = take_seconds(self.path(key))
            if seconds is not None and seconds < 1.5:
                self.status_labels[key].setText("Very short: record again?")
        self.refresh(keep=key)

    def refresh(self, keep: str | None = None) -> None:
        for key, _, _ in TAKES:
            button = self.record_buttons[key]
            recording = key == self.current
            button.setText("Stop" if recording else "Record")
            button.setIcon(T.icon("stop" if recording else "record"))
            if recording:
                continue
            if key == keep and self.status_labels[key].text().startswith("Very short"):
                continue
            seconds = take_seconds(self.path(key))
            self.status_labels[key].setText("Not recorded yet" if seconds is None
                                            else f"Recorded ({seconds:.0f} s)")

    def _tick(self) -> None:
        engine = self.dashboard.engine
        self.view.timeline = engine.live if self.current is not None else self._empty
        self.view.status_message = "" if self.current is not None else "Press Record next to a take"
        self.meter.set_level(engine.last_level_db if engine.running else math.nan)
        if self.current is not None:
            if not engine.running:              # stopped elsewhere (the Stop button, or a fault)
                self.stop()
            else:
                seconds = time.perf_counter() - self.started_at
                self.status_labels[self.current].setText(f"Recording… {seconds:.0f} s")
        self.view.update()

    # ---- after ------------------------------------------------------------------------------

    def open_folder(self) -> None:
        os.makedirs(self.takes_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.takes_dir))

    def compare_now(self) -> None:
        if self.current is not None:
            self.stop()
        self.dashboard.use_takes_from(self.takes_dir)
        self.dashboard.tabs.setCurrentIndex(2)
        self.dashboard.run_comparison(play=False)
        self.close()

    def closeEvent(self, event) -> None:
        if self.current is not None:
            self.stop()
        self._timer.stop()
        super().closeEvent(event)
