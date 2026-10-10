"""The dashboard: everything around the live display, for setup, the supervisor and review.

Tabs
  Live          one clean screen: the display large, a short key beside it, and three steps
                that say what is happening (start, learning their usual voice, watching). The
                mini window is the small always-on-top copy watched from the corner of the eye.
                Each signal on its own row and the whole session are details, off by default.
  Look back     the whole session: what changed and when, a summary of any stretch you select,
                two stretches compared, marks with notes; save (numbers only) and export.
  Compare       recordings side by side against one baseline (the demo comparison), and
                recording your own takes for it.
  Help          how to read everything, a session start to finish, a checklist for reading a
                change, keys, privacy and limits.
  Settings      microphone, learning the usual voice, display, privacy.

Everything shown is evidence about the voice. Nothing here names a feeling: what a change
means is for the person watching to decide.
"""

from __future__ import annotations

import math
import os
import queue
import time
from bisect import bisect_right

import numpy as np
from PySide6.QtCore import QEvent, QPointF, QRectF, QSettings, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QKeySequence, QPainter, QPen,
                           QPolygonF, QShortcut)
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QInputDialog, QLineEdit,
                               QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTabWidget,
                               QToolTip, QVBoxLayout, QWidget)

from . import __version__, audio
from . import config as C
from . import theme as T
from .baseline import BaselineStats
from .display import HELP_LINES, CompareGrid, ToneView, tension_value
from .engine import Engine
from .guide import GuideBrowser, KeyPanel
from .prosody import Reference, analyse_samples
from .session import Session, clock, describe_plainly
from .takes import TakeRecorder
from .theme import LevelMeter, apply_dark_theme  # noqa: F401  (__main__ and the tests use these)

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DOCS_IMG = os.path.join(ROOT, "docs", "img")
DEMO_WAVS = os.path.join(ROOT, "demo", "wavs")
OWN_TAKES = os.path.join(ROOT, "demo", "takes")
DEMO_SESSION = os.path.join(DEMO_WAVS, "session_demo.wav")
SETTINGS_PATH = os.path.join(ROOT, "settings.ini")

ACCENT = T.ACCENT
TEXT = T.TEXT
DIM = T.DIM
_label = T.label
_button = T.button

LIVE, REVIEW, COMPARE, GUIDE, SETUP = range(5)


def _mix(v: float) -> QColor:
    """Tension value -1..1 -> the display's blue / neutral / amber."""
    neutral, warm, cool = QColor(C.NEUTRAL), QColor(C.WARM), QColor(C.COOL)
    target = warm if v > 0 else cool
    k = min(1.0, abs(v))
    return QColor(int(neutral.red() + (target.red() - neutral.red()) * k),
                  int(neutral.green() + (target.green() - neutral.green()) * k),
                  int(neutral.blue() + (target.blue() - neutral.blue()) * k))


def _small_font(widget: QWidget, factor: float = 0.85) -> QFont:
    font = QFont(widget.font())
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * factor)
    return font


# ---- small widgets -------------------------------------------------------------------------

class SignalStrip(QWidget):
    """The last minute of each signal on its own track, against this speaker's usual (the
    middle line of each track). Up always means more: higher, louder, faster, more pressed.
    Pauses are shaded across all tracks; marks are dashed lines."""

    TRACKS = (("Pitch", "↑ higher  ↓ lower"), ("Loudness", "↑ louder  ↓ quieter"),
              ("Pace", "↑ faster  ↓ slower"), ("Voice quality", "↑ pressed  ↓ softer"))
    SCALES = (10.0, 15.0, C.PACE_FULL_SCALE, 6.0)   # semitones, dB, log2 ratio, dB
    LABEL_W = 132.0

    def __init__(self, session_fn, reference_fn, now_fn, seconds: float = 60.0, parent=None):
        super().__init__(parent)
        self.session_fn, self.reference_fn, self.now_fn = session_fn, reference_fn, now_fn
        self.seconds = float(seconds)
        self.setMinimumHeight(150)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(T.CARD_BG))
        fm = QFontMetricsF(self.font())
        small = _small_font(self)
        label_w = self.LABEL_W
        plot = QRectF(label_w, 2.0, max(10.0, self.width() - label_w - 2.0),
                      max(10.0, self.height() - fm.height() - 8.0))
        gap = 5.0
        track_h = (plot.height() - gap * 3) / 4
        tracks = [QRectF(plot.left(), plot.top() + k * (track_h + gap), plot.width(), track_h)
                  for k in range(4)]
        for (name, hint), r in zip(self.TRACKS, tracks):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(C.BACKGROUND))
            p.drawRoundedRect(r, 5, 5)
            p.setPen(QColor(C.CENTRE_LINE))
            p.drawLine(QPointF(r.left() + 4, r.center().y()), QPointF(r.right() - 4, r.center().y()))
            p.setPen(QColor(TEXT))
            p.setFont(self.font())
            p.drawText(QRectF(0, r.top(), label_w - 10, r.height() / 2 + 1),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom, name)
            p.setPen(QColor(DIM))
            p.setFont(small)
            p.drawText(QRectF(0, r.center().y() + 1, label_w - 10, r.height() / 2),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, hint)
        p.setFont(small)
        p.setPen(QColor(DIM))
        axis = QRectF(plot.left(), plot.bottom() + 3, plot.width(), fm.height() + 4)
        p.drawText(axis, Qt.AlignmentFlag.AlignLeft, f"{self.seconds:.0f} s ago")
        p.drawText(axis, Qt.AlignmentFlag.AlignRight, "now")
        p.setFont(self.font())
        now = self.now_fn()
        ref = self.reference_fn()
        session = self.session_fn()
        if now is None or not ref.pitch_hz or session is None:
            p.setPen(QColor(DIM))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter, "Waiting for speech")
            p.end()
            return
        d = session.recent(self.seconds, now)
        t = d["t"]
        if t.size < 2:
            p.end()
            return
        n = max(2, int(plot.width() / 2))            # one value per 2 px
        col = np.clip(((t - (now - self.seconds)) / self.seconds * n).astype(int), 0, n - 1)
        voiced = ~np.isnan(d["f0"])

        def per_column(values, mask):
            mask = mask & ~np.isnan(values)
            total = np.bincount(col[mask], weights=values[mask], minlength=n)
            count = np.bincount(col[mask], minlength=n)
            with np.errstate(invalid="ignore", divide="ignore"):
                return np.where(count >= 2, total / np.maximum(count, 1), np.nan)

        xs = plot.left() + (np.arange(n) + 0.5) / n * plot.width()
        # pauses: shade across all tracks
        in_pause = per_column(np.ones_like(t), ~np.isnan(d["pause_since"]))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 18))
        for k in np.flatnonzero(~np.isnan(in_pause)):
            p.drawRect(QRectF(xs[k] - plot.width() / n / 2, plot.top(), plot.width() / n,
                              plot.height()))
        st = 12.0 * np.log2(np.where(voiced, d["f0"], ref.pitch_hz) / ref.pitch_hz)
        series = [per_column(np.clip(st, -12, 12), voiced),
                  per_column(d["loud"] - (ref.level_db if ref.level_db is not None else 0.0), voiced)]
        if ref.calibrated and ref.rate:
            with np.errstate(invalid="ignore", divide="ignore"):
                series.append(per_column(np.log2(d["rate"] / ref.rate), np.isfinite(d["rate"])))
        else:
            series.append(np.full(n, np.nan))
        if ref.calibrated and ref.tilt_db is not None:
            series.append(per_column(d["tilt"] - ref.tilt_db, voiced))
        else:
            series.append(np.full(n, np.nan))
        if ref.calibrated and ref.band_st:        # usual pitch range on the pitch track
            r = tracks[0]
            y0 = r.center().y() - ref.band_st[1] / self.SCALES[0] * r.height() / 2
            y1 = r.center().y() - ref.band_st[0] / self.SCALES[0] * r.height() / 2
            p.fillRect(QRectF(r.left(), y0, r.width(), y1 - y0), QColor(*C.USUAL_BAND))
        plain = QPen(QColor(C.NEUTRAL if ref.calibrated else C.CALIBRATING_LINE), 2.0)
        for k, (values, r, scale) in enumerate(zip(series, tracks, self.SCALES)):
            y = r.center().y() - np.clip(values / scale, -1, 1) * (r.height() / 2 - 2)
            ok = ~np.isnan(y)
            # voice quality is coloured like the main line: one polyline per run of equal colour
            level = (np.round(tension_value(values) * 4).astype(int) if k == 3
                     else np.zeros(n, dtype=int))
            start = None
            for i in range(n + 1):
                same = (i < n and ok[i] and start is not None and level[i] == level[start])
                if same:
                    continue
                if start is not None and i - start >= 2:
                    p.setPen(QPen(_mix(level[start] / 4.0), 2.0) if k == 3 else plain)
                    end = min(i + 1, n) if (i < n and ok[i]) else i   # join to the next colour
                    p.drawPolyline(QPolygonF([QPointF(xs[j], y[j]) for j in range(start, end)]))
                start = i if (i < n and ok[i]) else None
        # marks: a dashed line with a small flag
        for m in session.markers:
            if now - self.seconds <= m.t <= now:
                xm = plot.left() + (m.t - (now - self.seconds)) / self.seconds * plot.width()
                p.setPen(QPen(QColor(ACCENT), 1.0, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(xm, plot.top() + 6), QPointF(xm, plot.bottom()))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(ACCENT))
                p.drawPolygon(QPolygonF([QPointF(xm - 4, plot.top()), QPointF(xm + 4, plot.top()),
                                         QPointF(xm, plot.top() + 7)]))
        p.end()


class ChangeMap(QWidget):
    """The whole session at a glance: one row per signal, with bars going up where the voice
    was above this speaker's usual and down where it was below; long pauses; marks; and the
    stretches the review found. Drag to select a stretch; click to select 20 s around a point."""

    ROWS = ("Pitch", "Loudness", "Pace", "Voice quality", "Pauses")
    SHORT_ROWS = ("Pitch", "Loudness", "Pace", "Voice")
    SCALES = (6.0, 10.0, C.PACE_FULL_SCALE, 5.0, 1.0)
    selection_changed = Signal(float, float)

    def __init__(self, compact: bool = False, parent=None):
        super().__init__(parent)
        self.compact = compact
        self.session: Session | None = None
        self.changes: list = []
        self.selection: tuple[float, float] | None = None
        self._bins = None
        self._key = None
        self._drag_from: float | None = None
        self.setMinimumHeight(52 if compact else 150)
        self.setMouseTracking(False)
        self.setCursor(Qt.CursorShape.CrossCursor)

    def set_session(self, session: Session | None) -> None:
        self.session = session
        self._key = None
        self.update()

    def _plot(self) -> QRectF:
        label_w = 64.0 if self.compact else 110.0
        top = 2.0 if self.compact else 14.0
        return QRectF(label_w, top, max(10.0, self.width() - label_w - 4.0),
                      max(10.0, self.height() - top - (2.0 if self.compact else 18.0)))

    def _duration(self) -> float:
        return max(self.session.end_time if self.session else 0.0, 10.0)

    def _t_at(self, x: float) -> float:
        plot = self._plot()
        return min(max((x - plot.left()) / plot.width(), 0.0), 1.0) * self._duration()

    def _x_at(self, t: float) -> float:
        plot = self._plot()
        return plot.left() + t / self._duration() * plot.width()

    def mousePressEvent(self, event) -> None:
        if self.session is None or event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag_from = self._t_at(event.position().x())

    def mouseMoveEvent(self, event) -> None:
        if self._drag_from is not None:
            t = self._t_at(event.position().x())
            self.selection = (min(t, self._drag_from), max(t, self._drag_from))
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag_from is None:
            return
        t = self._t_at(event.position().x())
        a, b = sorted((self._drag_from, t))
        self._drag_from = None
        if b - a < 1.0:                  # a click: 20 s around it
            a, b = max(0.0, t - 10.0), min(self._duration(), t + 10.0)
        self.select(a, b)

    def select(self, a: float, b: float) -> None:
        self.selection = (a, b)
        self.update()
        self.selection_changed.emit(a, b)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.fillRect(self.rect(), QColor(T.CARD_BG))
        plot = self._plot()
        rows = 4 if self.compact else 5
        row_h = plot.height() / rows
        session = self.session
        names = self.SHORT_ROWS if self.compact else self.ROWS
        small = _small_font(self, 0.8 if self.compact else 1.0)
        for k in range(rows):
            r = QRectF(plot.left(), plot.top() + k * row_h, plot.width(), row_h - 2)
            p.fillRect(r, QColor(C.BACKGROUND))
            p.setFont(small)
            p.setPen(QColor(DIM if self.compact else TEXT))
            p.drawText(QRectF(0, r.top(), plot.left() - 8, r.height()),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, names[k])
        p.setFont(self.font())
        if session is None or session.frame_count == 0:
            p.setPen(QColor(DIM))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter,
                       "No session yet: it fills in as someone talks")
            p.end()
            return
        if session.baseline is None:
            p.setPen(QColor(DIM))
            p.drawText(plot, Qt.AlignmentFlag.AlignCenter,
                       "Learning this voice: the map fills in once the app knows their usual")
            p.end()
            return
        bin_s = max(1.0, self._duration() / max(20.0, plot.width() / 3.0))
        key = (session.frame_count, round(bin_s, 3), session.baseline)
        if key != self._key:
            self._bins = session.binned(bin_s, 0.0, self._duration())
            self._key = key
        bins = self._bins
        series = [bins["pitch_st"], bins["loud_db"], bins["pace_log2"], bins["tilt_db"],
                  bins["pause_fraction"]]
        nb = series[0].size
        bw = plot.width() / max(nb, 1)
        for k in range(rows):
            r = QRectF(plot.left(), plot.top() + k * row_h, plot.width(), row_h - 2)
            cy = r.bottom() - 1 if k == 4 else r.center().y()
            p.setPen(QColor(C.CENTRE_LINE))
            p.drawLine(QPointF(r.left(), cy), QPointF(r.right(), cy))
            values = series[k]
            half = (r.height() - 2) if k == 4 else (r.height() / 2 - 1)
            p.setPen(Qt.PenStyle.NoPen)
            for i in np.flatnonzero(~np.isnan(values)):
                v = float(np.clip(values[i] / self.SCALES[k], -1, 1))
                if abs(v) < 0.04:
                    continue
                if k == 3:
                    colour = _mix(float(tension_value(values[i])[()]))
                elif k == 4:
                    colour = QColor(255, 255, 255, 60)
                else:
                    colour = QColor(C.NEUTRAL)
                p.setBrush(colour)
                h = v * half
                p.drawRect(QRectF(r.left() + i * bw, cy - max(h, 0), max(bw - 0.5, 0.8), abs(h)))
        # the review's changes: an outline on their row
        row_of = {"pitch": 0, "loudness": 1, "pace": 2, "voice quality": 3, "pause": 4}
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(ACCENT), 1.2))
        for c in self.changes:
            k = row_of.get(c.signal)
            if k is None or k >= rows:
                continue
            x0, x1 = self._x_at(c.start), self._x_at(c.end)
            p.drawRoundedRect(QRectF(x0, plot.top() + k * row_h, max(x1 - x0, 2.0), row_h - 2), 2, 2)
        # marks
        p.setPen(QPen(QColor(ACCENT), 1.0, Qt.PenStyle.DashLine))
        for m in session.markers:
            x = self._x_at(m.t)
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
            if not self.compact:
                p.setBrush(QColor(ACCENT))
                p.drawPolygon(QPolygonF([QPointF(x - 4, 2), QPointF(x + 4, 2), QPointF(x, 10)]))
                p.setBrush(Qt.BrushStyle.NoBrush)
        # selection
        if self.selection:
            a, b = self.selection
            x0, x1 = self._x_at(a), self._x_at(b)
            p.setPen(QPen(QColor(TEXT), 1.0))
            p.setBrush(QColor(124, 140, 255, 40))
            p.drawRect(QRectF(x0, plot.top(), max(x1 - x0, 2.0), plot.height()))
        if not self.compact:
            p.setPen(QColor(DIM))
            y = plot.bottom() + 2
            p.drawText(QRectF(plot.left(), y, 80, 16), Qt.AlignmentFlag.AlignLeft, "0:00")
            p.drawText(QRectF(plot.right() - 80, y, 80, 16), Qt.AlignmentFlag.AlignRight,
                       clock(self._duration()))
        p.end()


class StartCard(QFrame):
    """What to do first, shown over the empty live view until something is playing."""

    STEPS = ("Press Start listening and let the person talk normally.",
             "For the first 20 seconds or so the app learns their usual voice. The line is grey "
             "until then.",
             "Then watch the line: it shows how their voice moves away from their usual. The "
             "key on the right says what each part means.")

    def __init__(self, dashboard: "Dashboard", parent: QWidget):
        super().__init__(parent)
        self.setObjectName("startCard")
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 20, 24, 18)
        v.setSpacing(11)
        v.addWidget(_label("Start here", "startTitle"))
        for k, text in enumerate(self.STEPS, 1):
            row = QHBoxLayout()
            row.setSpacing(12)
            number = _label(str(k), "stepNumber")
            number.setFixedSize(24, 24)
            number.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)
            row.addWidget(_label(text, wrap=True), 1)
            v.addLayout(row)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        start = _button("Start listening", primary=True, icon_name="play")
        start.clicked.connect(lambda: dashboard.start_button.setChecked(True))
        demo = _button("Try the demo recording", "A recorded voice: about 25 seconds of ordinary "
                       "talk, then one sentence said four different ways", icon_name="demo")
        demo.clicked.connect(lambda: dashboard.try_demo())
        buttons.addWidget(start)
        buttons.addWidget(demo)
        buttons.addStretch(1)
        v.addSpacing(4)
        v.addLayout(buttons)
        v.addWidget(_label("Nothing is recorded or sent anywhere. " + C.DISCLAIMER, "dim",
                           wrap=True))

    def place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        w = int(min(600, max(260, parent.width() - 40)))
        layout = self.layout()
        h = layout.heightForWidth(w) if layout.hasHeightForWidth() else self.sizeHint().height()
        h = int(min(h, max(120, parent.height() - 16)))
        self.setFixedSize(w, h)
        self.move((parent.width() - w) // 2, max(8, (parent.height() - h) // 2 - 6))


class LiveView(ToneView):
    """The main display in the Live tab; also measures its own delay (shown in the status bar)
    and explains itself when you hover over it."""

    def __init__(self, engine: Engine, history: float, parent=None):
        super().__init__(engine.live, lambda: engine.reference, history=history, parent=parent)
        self.engine = engine
        self.now_fn = engine.now
        self.glow = False     # the glow is for the corner view; on this big view it doubles the cost
        self.latencies: list[float] = []
        self.measured_up_to = -math.inf
        self.start_card: StartCard | None = None

    def explain(self, pos) -> str:
        """What the part of the display under the mouse means."""
        r = self.layout_rects()
        x, y = pos.x(), pos.y()
        if r.pace.adjusted(-8, 0, 8, 0).contains(x, y):
            return ("Pace: syllables per second while talking, against their usual pace (the "
                    "notch). Up = faster than usual, down = slower. It fades during a pause.")
        if r.lane.adjusted(0, -2, 0, 2).contains(x, y):
            return "One tick per syllable. Close together = talking fast."
        if r.plot.contains(x, y):
            return ("Height = pitch (up = higher than their usual middle, the dim line). "
                    "Thickness and brightness = loudness. Colour = voice quality: amber more "
                    "pressed, blue softer or breathier, white usual. Gaps = pauses; shaded = "
                    "1 s or longer.")
        return ""

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            text = self.explain(e.pos())
            if text:
                QToolTip.showText(e.globalPos(), text, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.start_card is not None:
            self.start_card.place()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        worker = self.engine.worker
        now = self.current_time()
        if worker is None or now is None or self.frozen_at is not None or worker.clock.offset is None:
            return
        painted = time.perf_counter()
        t = self.timeline.t
        i, j = bisect_right(t, self.measured_up_to), bisect_right(t, now)
        if j > i:
            offset = self.engine.offset
            self.latencies.extend((painted - worker.clock.wall(t[k] - offset)) * 1000.0
                                  for k in range(i, j))
            self.measured_up_to = t[j - 1]
            if len(self.latencies) > 4000:
                del self.latencies[:2000]


class StatusChips(QWidget):
    """Small labels beside the tabs: listening or not, whether the voice is learned yet, and
    the session clock. Each item is (marker, text); the marker is "on", "off", "check",
    "ring:<progress 0..1>" or ""."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[tuple[str, str]] = []
        self.highlight = -1                  # this chip gets an accent outline (the current step)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_items(self, items: list[tuple[str, str]], highlight: int = -1) -> None:
        if items != self.items or highlight != self.highlight:
            self.items, self.highlight = items, highlight
            self.updateGeometry()
            self.update()

    def _widths(self) -> list[float]:
        fm = QFontMetricsF(self.font())
        return [fm.horizontalAdvance(text) + (34.0 if marker else 20.0) for marker, text in self.items]

    def sizeHint(self) -> QSize:
        fm = QFontMetricsF(self.font())
        w = sum(self._widths()) + 8.0 * max(0, len(self.items) - 1) + 14.0
        return QSize(int(math.ceil(w)), int(fm.height() + 20))

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        fm = QFontMetricsF(self.font())
        h = fm.height() + 10.0
        y = (self.height() - h) / 2.0
        x = 2.0
        for k, ((marker, text), w) in enumerate(zip(self.items, self._widths())):
            chip = QRectF(x, y, w, h)
            current = k == self.highlight
            p.setPen(QPen(QColor(ACCENT if current else T.CARD_BORDER), 1.6 if current else 1.0))
            p.setBrush(QColor(T.ACCENT_SOFT if current else T.CARD_BG))
            p.drawRoundedRect(chip, h / 2, h / 2)
            tx = chip.left() + 10.0
            cx, cy = chip.left() + 15.0, chip.center().y()
            if marker == "on":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(ACCENT))
                p.drawEllipse(QPointF(cx, cy), 4.0, 4.0)
            elif marker == "off":
                p.setPen(QPen(QColor(DIM), 1.3))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(cx, cy), 3.8, 3.8)
            elif marker == "check":
                pen = QPen(QColor(ACCENT), 1.8)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawPolyline(QPolygonF([QPointF(cx - 4, cy), QPointF(cx - 1, cy + 3),
                                          QPointF(cx + 4.5, cy - 3.5)]))
            elif marker.startswith("ring:"):
                progress = min(1.0, max(0.0, float(marker[5:])))
                ring = QRectF(cx - 5, cy - 5, 10, 10)
                p.setPen(QPen(QColor(C.PACE_TRACK), 2.2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(ring)
                pen = QPen(QColor(ACCENT), 2.2)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawArc(ring, 90 * 16, -int(360 * 16 * progress))
            if marker:
                tx = chip.left() + 26.0
            p.setPen(QColor(T.TEXT if current else T.TEXT_2))
            p.drawText(QRectF(tx, chip.top(), chip.right() - tx - 8, h),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
            x += w + 8.0
        p.end()


class CornerWindow(ToneView):
    """The small always-on-top window, watched from the corner of the eye during a session."""

    def __init__(self, dashboard: "Dashboard"):
        engine = dashboard.engine
        super().__init__(engine.live, lambda: engine.reference, history=dashboard.live_seconds)
        self.dashboard = dashboard
        self.now_fn = engine.now
        self.help_lines = HELP_LINES[:-1] + (
            "Space pause   M mark   R learn voice again   T on top   H help   Esc hide",)
        self.setWindowTitle("Tone visualiser (mini window)")
        self.setWindowIcon(T.app_icon())
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        font = QFont(self.font())            # the small window's own size (the dashboard uses
        if font.pointSizeF() > 0:            # 10 pt), so its legend fits at 400 x 250
            font.setPointSizeF(9.0)
        self.setFont(font)
        self.resize(*C.WINDOW_SIZE)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.hide()
            self.dashboard.corner_hidden()
        elif key == Qt.Key.Key_Space:
            self.toggle_freeze()
        elif key == Qt.Key.Key_M:
            self.dashboard.add_mark()
        elif key == Qt.Key.Key_R:
            self.dashboard.recalibrate()
        elif key == Qt.Key.Key_H:
            self.show_help = not self.show_help
            self.update()
        elif key == Qt.Key.Key_T:
            on_top = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, not on_top)
            self.show()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.dashboard.corner_hidden()
        super().closeEvent(event)


class RangeCompareDialog(QDialog):
    """Two stretches of one session side by side, with the differences in words."""

    def __init__(self, session: Session, a: tuple[float, float], b: tuple[float, float],
                 parent=None, numbers: bool = True):
        super().__init__(parent)
        self.setWindowTitle("Compare two stretches")
        ref = Reference.from_stats(session.baseline)
        history = max(a[1] - a[0], b[1] - b[0]) + 0.3
        grid = QGridLayout(self)
        grid.setContentsMargins(16, 14, 16, 12)
        grid.setHorizontalSpacing(14)
        grid.addWidget(_label("Two stretches of the same session, measured against the same "
                              "baseline, on one time scale.", "pageText", wrap=True), 0, 0, 1, 2)
        for k, (name, (t0, t1)) in enumerate((("A", a), ("B", b))):
            view = ToneView(session.timeline(t0, t1), lambda: ref, history=history, label=name,
                            show_disclaimer=False, anchor_left=True)
            view.source_finished = True
            view.now_fn = (lambda d=t1 - t0: d)
            grid.addWidget(_label(f"{name}: {clock(t0)} – {clock(t1)}", "heading"), 1, k)
            grid.addWidget(view, 2, k)
            summary = session.summarise(t0, t1)
            grid.addWidget(_label(summary.sentence(session.baseline, numbers) if summary else "",
                                  wrap=True), 3, k)
        grid.addWidget(_label(compare_in_words(session, a, b, numbers), "summaryBox", wrap=True),
                       4, 0, 1, 2)
        grid.addWidget(_label(C.DISCLAIMER, "dim"), 5, 0, 1, 2)
        grid.setRowStretch(2, 1)
        self.resize(940, 520)


def compare_in_words(session: Session, a, b, numbers: bool = True) -> str:
    """How stretch B differs from stretch A, in plain words about the voice."""
    sa, sb = session.summarise(*a), session.summarise(*b)
    if sa is None or sb is None:
        return "Needs a baseline first."
    if min(sa.speech_seconds, sb.speech_seconds) < C.EVIDENCE_MIN_SPEECH:
        return "One of the stretches has too little speech to compare."
    parts = []

    def diff(value, unit, up, down, threshold, fmt="{:.1f}"):
        if not math.isfinite(value) or abs(value) < threshold:
            return
        amount = f" ({'+' if value > 0 else ''}{fmt.format(value)} {unit})" if numbers else ""
        parts.append(f"{up if value > 0 else down}{amount}")

    diff(sb.pitch_st - sa.pitch_st, "semitones", "pitch higher", "pitch lower", 1.0)
    diff(sb.loud_db - sa.loud_db, "dB", "louder", "quieter", 3.0, "{:.0f}")
    if math.isfinite(sa.pace) and math.isfinite(sb.pace) and sa.pace > 0:
        ratio = sb.pace / sa.pace
        if ratio >= 1.12 or ratio <= 0.89:
            parts.append(f"{'faster' if ratio > 1 else 'slower'}"
                         + (f" (×{ratio:.2f})" if numbers else ""))
    diff(sb.tilt_db - sa.tilt_db, "dB", "voice more pressed", "voice softer or breathier", 1.0)
    if sb.long_pauses != sa.long_pauses:
        parts.append(f"pauses of 1 s or more: {sa.long_pauses} in A, {sb.long_pauses} in B")
    if not parts:
        return "B compared with A: much the same."
    return "B compared with A: " + "; ".join(parts) + "."


class Prefs:
    """Remembers display choices between runs, in settings.ini beside the app: which
    microphone, the display lengths, what is shown, the window's size. Never any sound or
    measurements. With no path (as in the tests) nothing is read or written."""

    def __init__(self, path: str | None):
        self._s = None
        if path:
            try:
                self._s = QSettings(path, QSettings.Format.IniFormat)
            except Exception:
                self._s = None

    def get(self, key: str, default):
        if self._s is None or not self._s.contains(key):
            return default
        value = self._s.value(key)
        try:
            if isinstance(default, bool):
                return value if isinstance(value, bool) else str(value).lower() in ("true", "1")
            if isinstance(default, float):
                return float(value)
            if isinstance(default, int):
                return int(value)
        except (TypeError, ValueError):
            return default
        return value

    def set(self, key: str, value) -> None:
        if self._s is not None:
            self._s.setValue(key, value)

    def sync(self) -> None:
        if self._s is not None:
            self._s.sync()


# ---- the window ----------------------------------------------------------------------------

class Dashboard(QMainWindow):
    def __init__(self, *, calibration_seconds: float | None = None,
                 live_seconds: float | None = None, debug: bool = False,
                 settings_path: str | None = None):
        super().__init__()
        self.setWindowTitle("Tone visualiser")
        self.setWindowIcon(T.app_icon())
        self.prefs = Prefs(settings_path)
        if calibration_seconds is None:
            calibration_seconds = self.prefs.get("calibration_seconds",
                                                 float(C.CALIBRATION_SPEECH_SECONDS))
        if live_seconds is None:
            live_seconds = self.prefs.get("live_seconds", 10.0)
        self.engine = Engine(calibration_seconds=calibration_seconds)
        self.live_seconds = float(live_seconds)
        self.debug = debug
        self.confirm_close = True            # ask before discarding measurements (off in tests)
        self.show_numbers = self.prefs.get("show_numbers", False)
        self.pending_record_path: str | None = None   # --record FILE: the next listening run
        self.review_session: Session = self.engine.session
        self.review_is_live = True
        self.range_a: tuple[float, float] | None = None
        self.range_b: tuple[float, float] | None = None
        self.corner: CornerWindow | None = None
        self.take_recorder: TakeRecorder | None = None
        self.compare_source = None
        self.compare_clock = None
        self.compare_files: dict[str, str] = {}
        self._saved_frames = 0
        self._tick_count = 0
        self._changes_key = None
        self._demo_session = False
        self._was_calibrated = False
        self._baseline_shown = None

        page = QWidget()
        page.setObjectName("page")
        outer = QVBoxLayout(page)
        outer.setContentsMargins(10, 2, 10, 4)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        outer.addWidget(self.tabs)
        self.setCentralWidget(page)
        self.tabs.addTab(self._build_live(), T.icon("live", T.TEXT_2), "Live")
        self.tabs.addTab(self._build_review(), T.icon("review", T.TEXT_2), "Look back")
        self.tabs.addTab(self._build_compare(), T.icon("compare", T.TEXT_2), "Compare")
        # Help and Settings are small icon tabs at the end: the three that matter have words.
        self.tabs.addTab(self._build_guide(), T.icon("guide", T.TEXT_2), "")
        self.tabs.addTab(self._build_setup(), T.icon("setup", T.TEXT_2), "")
        self.tabs.setTabToolTip(GUIDE, "Help: how to read the display, and how to use the app (F1)")
        self.tabs.setTabToolTip(SETUP, "Settings: microphone, learning the voice, display, privacy")
        self.chips = StatusChips()
        self.tabs.setCornerWidget(self.chips, Qt.Corner.TopRightCorner)
        self.tabs.currentChanged.connect(lambda _: self._refresh_review(force=True))
        self.delay_label = _label("", "dim")
        self.statusBar().addPermanentWidget(self.delay_label)
        self.statusBar().showMessage("Ready. Press Start listening, or try the demo recording "
                                     "(under More).")

        for keys, slot in (("M", self.add_mark), ("N", self.add_mark_with_note),
                           ("Space", self._space), ("H", self.toggle_side_panel),
                           ("Ctrl+S", self.save_session_dialog),
                           ("Ctrl+O", self.open_session_dialog),
                           ("F1", lambda: self.tabs.setCurrentIndex(GUIDE)),
                           ("F11", self.toggle_full_screen)):
            QShortcut(QKeySequence(keys), self).activated.connect(slot)
        for k in range(5):
            QShortcut(QKeySequence(f"Ctrl+{k + 1}"), self).activated.connect(
                lambda k=k: self.tabs.setCurrentIndex(k))

        self.resize(1280, 820)
        self.setMinimumSize(1140, 700)       # every toolbar label fits from here up
        geometry = self.prefs.get("geometry", None)
        if geometry is not None:
            try:
                self.restoreGeometry(geometry)
            except Exception:
                pass
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(max(1, round(1000 / C.FPS)))
        self._refresh_devices()
        self._restore_mic()
        self.mic_combo.currentIndexChanged.connect(self._mic_chosen)
        self._refresh_baseline_text()
        self._update_chips()

    # ---- building the tabs ------------------------------------------------------------------

    def _build_live(self) -> QWidget:
        """One clean screen: the controls, the steps, the display and a short key. The signal
        rows and the whole-session strip are details, off unless chosen (More, or Settings)."""
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.start_button = _button("Start listening", "Start or stop listening to the microphone",
                                    checkable=True, primary=True, icon_name="play")
        self.start_button.toggled.connect(self._start_toggled)
        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(200)
        self.mic_combo.setMaximumWidth(300)
        self.mic_combo.setToolTip("Which microphone to listen to")
        self.live_meter = LevelMeter()
        self.live_meter.setFixedWidth(90)
        self.live_meter.setToolTip("How loud the microphone hears it")
        for w in (self.start_button, self.mic_combo, self.live_meter):
            bar.addWidget(w)
        bar.addSpacing(10)
        relearn = _button("Learn voice again", "Forget this voice and learn the next speaker's "
                          "usual voice from their first seconds of talking (in a role-play: press "
                          "it when the client starts talking)", icon_name="recal")
        relearn.clicked.connect(self.recalibrate)
        mark = _button("Mark", "Mark this moment, to come back to it afterwards (M; N to add a "
                       "note)", icon_name="mark")
        mark.clicked.connect(self.add_mark)
        self.corner_button = _button("Mini window", "A small window that stays on top of "
                                     "everything, to watch from the corner of your eye",
                                     checkable=True, icon_name="corner")
        self.corner_button.toggled.connect(self._corner_toggled)
        for w in (relearn, mark, self.corner_button):
            bar.addWidget(w)
        bar.addStretch(1)

        more = _button("More", "The demo, sound files, sessions and display options",
                       icon_name="session")
        menu = QMenu(more)
        menu.addAction(T.icon("demo"), "Try the demo recording", lambda: self.try_demo())
        menu.addAction(T.icon("open"), "Play a sound file…", self.play_file_dialog)
        menu.addSeparator()
        menu.addAction(T.icon("new"), "New session", self.new_session_clicked)
        menu.addAction(T.icon("save"), "Save session…   Ctrl+S", self.save_session_dialog)
        menu.addAction(T.icon("open"), "Open session…   Ctrl+O", self.open_session_dialog)
        menu.addAction(T.icon("review"), "Look back at this session", self._review_now)
        menu.addSeparator()
        # Checkable actions stand in for the old toolbar buttons (same signals, same names).
        self.freeze_button = menu.addAction(T.icon("freeze"), "Pause the picture   Space")
        self.freeze_button.setCheckable(True)
        self.freeze_button.toggled.connect(self._freeze_toggled)
        self.panel_button = menu.addAction(T.icon("panel"), "Show the key beside the display   H")
        self.panel_button.setCheckable(True)
        self.panel_button.toggled.connect(self.set_side_panel)
        self.details_action = menu.addAction("Show each signal on its own row")
        self.details_action.setCheckable(True)
        self.details_action.toggled.connect(self.set_details)
        more.setMenu(menu)
        bar.addWidget(more)
        layout.addLayout(bar)

        self.steps = StatusChips()
        self.steps.setToolTip("Where you are: the app first learns the person's usual voice, then "
                              "shows how their voice changes from it")
        layout.addWidget(self.steps)

        self.live_view = LiveView(self.engine, self.live_seconds)
        self.live_view.setMinimumHeight(200)
        self.live_view.learning_banner = True
        self.live_view.axis_words = True
        self.live_view.cap_scale = True
        self.start_card = StartCard(self, self.live_view)
        self.live_view.start_card = self.start_card
        view_card = T.Card()
        view_card.body.setContentsMargins(6, 6, 6, 6)
        view_card.add(self.live_view, 1)

        side_content = QWidget()
        side = QVBoxLayout(side_content)
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(10)
        key_card = T.Card("How to read it")
        key_card.add(KeyPanel(compact=True))
        key_card.add(_label("The middle line is their usual voice. Everything is compared with "
                            "it. The full key is under Help (F1).", "cardHint", wrap=True))
        key_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        side.addWidget(key_card, 0)

        # Marks appear here only once there is one (M, or the Mark button).
        self.marks_card = T.Card("Your marks")
        self.marks_card.add(_label("Double-click one to add a note. They are also in Look back.",
                                   "cardHint", wrap=True))
        self.live_marks = QListWidget()
        self.live_marks.setMinimumHeight(40)
        self.live_marks.itemDoubleClicked.connect(lambda _item: self._focus_note())
        self.marks_card.add(self.live_marks, 1)
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("Note for the latest mark, then Enter")
        self.note_edit.returnPressed.connect(self.save_note)
        QShortcut(QKeySequence("Escape"), self.note_edit,
                  context=Qt.ShortcutContext.WidgetShortcut).activated.connect(self.note_edit.clearFocus)
        self.marks_card.add(self.note_edit)
        self.marks_card.hide()
        side.addWidget(self.marks_card, 1)
        side.addStretch(0)
        side_content.setMinimumWidth(300)
        # On a short window the column scrolls rather than squashing the key.
        self.side_panel = QScrollArea()
        self.side_panel.setWidgetResizable(True)
        self.side_panel.setFrameShape(QFrame.Shape.NoFrame)
        self.side_panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.side_panel.setWidget(side_content)
        self.side_panel.setMinimumWidth(312)
        self.side_panel.setMaximumWidth(380)

        main = QSplitter(Qt.Orientation.Horizontal)
        main.setChildrenCollapsible(False)
        main.setHandleWidth(10)
        main.addWidget(view_card)
        main.addWidget(self.side_panel)
        main.setStretchFactor(0, 1)
        main.setSizes([940, 320])
        layout.addWidget(main, 1)

        # Details for a supervisor who wants them: each signal on its own row over the last
        # minute, and the whole session. Off by default: one display is easier to read.
        self.details = QWidget()
        dl = QVBoxLayout(self.details)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(10)
        self.strip = SignalStrip(lambda: self.engine.session, lambda: self.engine.reference,
                                 self.engine.now, seconds=self.prefs.get("strip_seconds", 60.0))
        strip_card = T.Card("The last minute, one signal per row")
        strip_card.add_action(_label("Middle line = their usual. Shaded = pauses. "
                                     "Dashed = your marks.", "cardHint"))
        strip_card.add(self.strip, 1)
        strip_card.setMinimumHeight(190)
        dl.addWidget(strip_card)
        map_card = T.Card("Whole session")
        map_card.add_action(_label("Click anywhere to look back at that moment.", "cardHint"))
        self.live_map = ChangeMap(compact=True)
        self.live_map.set_session(self.engine.session)
        self.live_map.setFixedHeight(58)
        self.live_map.selection_changed.connect(self._review_at)
        map_card.add(self.live_map)
        dl.addWidget(map_card)
        layout.addWidget(self.details)
        self.set_side_panel(self.prefs.get("side_panel", True))
        self.set_details(self.prefs.get("show_details", False))
        return page

    def _build_review(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)
        header = T.PageHeader("Look back", "Look back over a whole session: where the voice "
                              "stayed away from their usual, when, and your notes.", "review")
        self.review_buttons = {}
        for text, slot, icon_name in (("Back to this session", self.review_live_session, "back"),
                                      ("Analyse a recording…", self.analyse_recording_dialog, "demo"),
                                      ("Open…", self.open_session_dialog, "open"),
                                      ("Save…", self.save_session_dialog, "save")):
            b = _button(text, icon_name=icon_name)
            b.clicked.connect(slot)
            header.add_action(b)
            self.review_buttons[text] = b
        export = _button("Export", "Save a text summary or a picture of this page",
                         icon_name="export")
        menu = QMenu(export)
        menu.addAction("Summary as text…", self.export_summary_dialog)
        menu.addAction("Picture of this page…", self.export_picture_dialog)
        export.setMenu(menu)
        header.add_action(export)
        self.review_numbers_check = QCheckBox("Show numbers")
        self.review_numbers_check.setToolTip("Add the measurements (semitones, decibels...) to "
                                             "the words")
        self.review_numbers_check.toggled.connect(self.set_show_numbers)
        header.add_action(self.review_numbers_check)
        layout.addWidget(header)

        map_card = T.Card("This session", "Each row is one signal. Bars above the middle line: "
                          "more than their usual (higher, louder, faster, more pressed); below: "
                          "less. Outlined bars are listed under What changed. Drag across the "
                          "map to choose a stretch, or click for 20 seconds around a moment.")
        self.review_title = map_card.title
        self.review_map = ChangeMap()
        self.review_map.setMinimumHeight(160)
        self.review_map.selection_changed.connect(self._selection_changed)
        map_card.add(self.review_map)
        layout.addWidget(map_card)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.setChildrenCollapsible(False)
        split.setHandleWidth(10)
        detail = T.Card("Nothing selected yet")
        self.selection_title = detail.title
        self.detail_view = ToneView(self.review_session.timeline(0, 0), lambda: self._review_reference,
                                    history=20.0, show_disclaimer=False, anchor_left=True)
        self.detail_view.source_finished = True
        self.detail_view.setMinimumSize(300, 150)
        self._review_reference = Reference(False, 0.0, None, None, None, None, None)
        detail.add(self.detail_view, 1)
        self.summary_label = _label("Select a stretch on the map to see it here, described in "
                                    "words.", "summaryBox", wrap=True)
        self.summary_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        detail.add(self.summary_label)
        row = QHBoxLayout()
        for text, slot, tip in (("Set as A", self._set_a, "Remember this stretch as A"),
                                ("Set as B", self._set_b, "Remember this stretch as B"),
                                ("Compare A with B", self.compare_ranges,
                                 "Show A and B side by side, with the differences in words"),
                                ("Mark this stretch", self._mark_selection,
                                 "Add a mark in the middle of this stretch")):
            b = _button(text, tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        self.ab_label = _label("A: not set   B: not set", "dim")
        row.addWidget(self.ab_label)
        detail.add_layout(row)
        split.addWidget(detail)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(10)
        changes = T.Card("What changed", "Where one signal stayed clearly away from their usual "
                         "for a few seconds. Click one to look at it.")
        self.changes_list = QListWidget()
        self.changes_list.setWordWrap(True)
        self.changes_list.itemClicked.connect(self._change_clicked)
        changes.add(self.changes_list, 1)
        rv.addWidget(changes, 5)
        marks = T.Card("Marks and notes", "Double-click a mark to write a note.")
        delete = _button("Delete mark", "Delete the selected mark", icon_name="trash", flat=True)
        delete.clicked.connect(self._delete_mark)
        marks.add_action(delete)
        self.marks_list = QListWidget()
        self.marks_list.setWordWrap(True)
        self.marks_list.itemClicked.connect(self._mark_clicked)
        self.marks_list.itemDoubleClicked.connect(self._edit_mark_note)
        marks.add(self.marks_list, 1)
        rv.addWidget(marks, 3)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([760, 440])
        layout.addWidget(split, 1)
        layout.addWidget(_label(C.DISCLAIMER, "dim"))
        self.review_map.set_session(self.review_session)
        return page

    def _build_compare(self) -> QWidget:
        page = QWidget()
        page.setObjectName("page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 10, 0, 0)
        layout.setSpacing(10)
        header = T.PageHeader("Compare", "The same words spoken different ways, side by side. "
                              "Each panel is compared with a recording of the same person's "
                              "usual voice, on one shared time scale.", "compare")
        self.compare_numbers_check = QCheckBox("Show numbers")
        self.compare_numbers_check.setToolTip("Show each recording's measurements under the panels")
        self.compare_numbers_check.toggled.connect(self.set_show_numbers)
        header.add_action(self.compare_numbers_check)
        layout.addWidget(header)

        files = T.Card("Recordings")
        body = QHBoxLayout()
        body.setSpacing(14)
        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        self.compare_paths: dict[str, QLineEdit] = {}
        for row, name in enumerate(("Baseline", "A", "B", "C", "D")):
            edit = QLineEdit()
            edit.setReadOnly(True)
            edit.setPlaceholderText("a recording of the same person talking normally"
                                    if name == "Baseline" else "(none)")
            choose = _button("Choose…")
            choose.clicked.connect(lambda _=False, n=name: self._choose_compare_file(n))
            clear = _button("", "Clear", icon_name="trash", flat=True)
            clear.clicked.connect(lambda _=False, n=name: self._set_compare_file(n, ""))
            form.addWidget(_label("Usual voice" if name == "Baseline" else name, "cardTitle"),
                           row, 0)
            form.addWidget(edit, row, 1)
            form.addWidget(choose, row, 2)
            form.addWidget(clear, row, 3)
            self.compare_paths[name] = edit
        form.setColumnStretch(1, 1)
        body.addLayout(form, 1)
        actions = QVBoxLayout()
        actions.setSpacing(6)
        for text, slot, icon_name, primary in (
                ("Use the demo recordings", self._use_demo_takes, "demo", False),
                ("Use my recordings", self._use_own_takes, "open", False),
                ("Record your own takes…", lambda: self.open_take_recorder(), "record", False),
                ("Show all at once", lambda: self.run_comparison(play=False), "compare", False),
                ("Play with sound", lambda: self.run_comparison(play=True), "play", True)):
            b = _button(text, primary=primary, icon_name=icon_name)
            b.clicked.connect(slot)
            actions.addWidget(b)
        actions.addStretch(1)
        body.addLayout(actions)
        files.add_layout(body)
        layout.addWidget(files)

        grid_card = T.Card()
        grid_card.body.setContentsMargins(6, 6, 6, 6)
        self.compare_grid = CompareGrid()
        grid_card.add(self.compare_grid, 1)
        layout.addWidget(grid_card, 1)
        self.compare_numbers = _label("", "dim", wrap=True)
        self.compare_numbers.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.compare_numbers)
        layout.addWidget(_label(C.DISCLAIMER, "dim"))
        self._use_demo_takes()
        return page

    def _build_guide(self) -> QWidget:
        self.guide = GuideBrowser()
        return self.guide

    def _build_setup(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        page.setObjectName("page")
        scroll.setWidget(page)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 10, 4, 0)
        outer.setSpacing(10)
        outer.addWidget(T.PageHeader("Settings", "Microphone, learning the speaker, what the display "
                                     "shows, and privacy. Your choices are remembered.", "setup"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(10)

        mic = T.Card("Microphone", "Start listening, then speak normally: the bar should reach "
                     "the lighter zone. A plug-in or USB microphone is better than a laptop's "
                     "built-in one.")
        row = QHBoxLayout()
        self.setup_mic_combo = QComboBox()
        self.setup_mic_combo.setMinimumWidth(300)
        refresh = _button("Refresh", "Look for microphones again (after plugging one in)")
        refresh.clicked.connect(self._refresh_devices)
        row.addWidget(self.setup_mic_combo, 1)
        row.addWidget(refresh)
        mic.add_layout(row)
        self.setup_meter = LevelMeter()
        self.setup_meter.setFixedHeight(22)
        mic.add(self.setup_meter)
        mic.body.addStretch(1)
        self.mic_combo.currentIndexChanged.connect(self.setup_mic_combo.setCurrentIndex)
        self.setup_mic_combo.currentIndexChanged.connect(self.mic_combo.setCurrentIndex)
        grid.addWidget(mic, 0, 0)

        cal = T.Card("Their usual voice",
                     "The app learns the usual voice of whoever speaks first. In a role-play, "
                     "press Learn voice again when the client starts talking. Saving it lets a "
                     "later session with the same person start already knowing them.")
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.addWidget(_label("Learn from", "secondary"), 0, 0)
        self.cal_seconds = QSpinBox()
        self.cal_seconds.setMaximumWidth(180)
        self.cal_seconds.setRange(5, 60)
        self.cal_seconds.setValue(int(self.engine.calibration_seconds))
        self.cal_seconds.setSuffix(" s of speech")
        self.cal_seconds.valueChanged.connect(self._set_calibration_seconds)
        form.addWidget(self.cal_seconds, 0, 1, Qt.AlignmentFlag.AlignLeft)
        form.addWidget(_label("Learned so far", "secondary"), 1, 0, Qt.AlignmentFlag.AlignTop)
        self.baseline_text = _label("", wrap=True)
        form.addWidget(self.baseline_text, 1, 1)
        form.setColumnStretch(1, 1)
        cal.add_layout(form)
        row = QHBoxLayout()
        for text, slot in (("Learn voice again", self.recalibrate),
                           ("Save this usual voice…", self.save_baseline_dialog),
                           ("Load a saved one…", self.load_baseline_dialog),
                           ("Learn it from a recording…", self.baseline_from_recording_dialog)):
            b = _button(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        row.addStretch(1)
        cal.add_layout(row)
        cal.body.addStretch(1)
        grid.addWidget(cal, 1, 0)

        disp = T.Card("Display")
        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)
        form.addWidget(_label("The display and the mini window show", "secondary"), 0, 0)
        self.live_seconds_spin = QSpinBox()
        self.live_seconds_spin.setMaximumWidth(140)
        self.live_seconds_spin.setRange(5, 30)
        self.live_seconds_spin.setValue(int(self.live_seconds))
        self.live_seconds_spin.setSuffix(" s")
        self.live_seconds_spin.valueChanged.connect(self._set_live_seconds)
        form.addWidget(self.live_seconds_spin, 0, 1, Qt.AlignmentFlag.AlignLeft)
        form.addWidget(_label("Signal rows show", "secondary"), 1, 0)
        self.strip_seconds_spin = QSpinBox()
        self.strip_seconds_spin.setMaximumWidth(140)
        self.strip_seconds_spin.setRange(20, 300)
        self.strip_seconds_spin.setValue(int(self.strip.seconds))
        self.strip_seconds_spin.setSuffix(" s")
        self.strip_seconds_spin.valueChanged.connect(self._set_strip_seconds)
        form.addWidget(self.strip_seconds_spin, 1, 1, Qt.AlignmentFlag.AlignLeft)
        form.setColumnStretch(1, 1)
        disp.add_layout(form)
        self.side_panel_check = QCheckBox("Show the key beside the display (H)")
        self.side_panel_check.setChecked(self.panel_button.isChecked())
        self.side_panel_check.toggled.connect(self.set_side_panel)
        disp.add(self.side_panel_check)
        self.details_check = QCheckBox("Also show each signal on its own row, and the whole "
                                       "session, under the display")
        self.details_check.setChecked(self.details_action.isChecked())
        self.details_check.toggled.connect(self.set_details)
        disp.add(self.details_check)
        self.setup_numbers_check = QCheckBox("Show numbers in Look back and Compare (the live views "
                                             "never show numbers)")
        self.setup_numbers_check.toggled.connect(self.set_show_numbers)
        disp.add(self.setup_numbers_check)
        disp.body.addStretch(1)
        grid.addWidget(disp, 0, 1)

        priv = T.Card("Privacy")
        self.record_check = QCheckBox("Also save the sound as a WAV file while listening "
                                      "(in the recordings folder)")
        self.record_check.toggled.connect(lambda on: setattr(self.engine, "record_audio", on))
        priv.add(self.record_check)
        priv.add(_label("Everything runs on this computer and nothing is sent anywhere. Sound is "
                        "never saved unless the box above is ticked, or you record takes on "
                        "purpose in Compare. Measurements stay in memory until you save a "
                        "session, and a saved session holds numbers only, no sound. Display "
                        "choices are remembered in settings.ini in this folder.", "cardHint",
                        wrap=True))
        priv.body.addStretch(1)
        grid.addWidget(priv, 1, 1)

        keys = T.Card("Keys")
        key_grid = QGridLayout()
        key_grid.setHorizontalSpacing(14)
        key_grid.setVerticalSpacing(4)
        pairs = (("Space", "pause the picture, or go live again"), ("M", "mark this moment"),
                 ("N", "mark it and type a note"), ("H", "show or hide the key"),
                 ("F11", "full screen"), ("F1", "Help"),
                 ("Ctrl+1 … Ctrl+5", "go to a tab"), ("Ctrl+S / Ctrl+O", "save / open a session"))
        for k, (key, what) in enumerate(pairs):
            key_grid.addWidget(_label(key, "cardTitle"), k // 2, (k % 2) * 2)
            key_grid.addWidget(_label(what, "secondary"), k // 2, (k % 2) * 2 + 1)
        key_grid.setColumnStretch(1, 1)
        key_grid.setColumnStretch(3, 1)
        keys.add_layout(key_grid)
        keys.add(_label("In the mini window: Space pause, M mark, R learn voice again, T keep on top, "
                        "H key, Esc hide.", "cardHint", wrap=True))
        grid.addWidget(keys, 2, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        outer.addLayout(grid)
        outer.addWidget(_label(f"Tone visualiser {__version__}. {C.DISCLAIMER}", "dim"))
        outer.addStretch(1)
        self._sync_numbers_checks()
        return scroll

    # ---- devices ----------------------------------------------------------------------------

    def _refresh_devices(self) -> None:
        entries = [("Default microphone", None)]
        try:
            import sounddevice as sd
            default = audio.pick_device("input")
            rows = []
            for i, d in enumerate(sd.query_devices()):
                if d["max_input_channels"] > 0:
                    api = sd.query_hostapis(d["hostapi"])["name"]
                    rank = audio._API_PREFERENCE.get(api, 9)
                    # WASAPI / Core Audio are the everyday devices; of the low-level driver
                    # entries only Stereo Mix (the computer's own output) is worth offering.
                    if rank == 0 or "stereo mix" in d["name"].lower():
                        mark = "  (default)" if i == default else ""
                        rows.append((rank, f"{d['name']}{mark}", i))
            entries += [(label, i) for _, label, i in sorted(rows)]
        except Exception as exc:            # no sound system at all: keep "Default" only
            self.statusBar().showMessage(f"Could not list microphones: {exc}")
        for combo in (self.mic_combo, getattr(self, "setup_mic_combo", None)):
            if combo is None:
                continue
            combo.blockSignals(True)
            current = combo.currentText()
            combo.clear()
            for label, data in entries:
                combo.addItem(label, data)
            found = combo.findText(current)
            if found >= 0:
                combo.setCurrentIndex(found)
            combo.blockSignals(False)

    @staticmethod
    def _mic_name(text: str) -> str:
        return text.replace("  (default)", "")

    def _restore_mic(self) -> None:
        saved = self.prefs.get("mic", "")
        if not saved:
            return
        for k in range(self.mic_combo.count()):
            if self.mic_combo.itemData(k) is not None and self._mic_name(self.mic_combo.itemText(k)) == saved:
                self.mic_combo.setCurrentIndex(k)
                self.setup_mic_combo.setCurrentIndex(k)
                return

    def _mic_chosen(self, index: int) -> None:
        data = self.mic_combo.itemData(index)
        self.prefs.set("mic", "" if data is None else self._mic_name(self.mic_combo.itemText(index)))

    # ---- listening --------------------------------------------------------------------------

    def start_listening(self, device=None, file_path: str | None = None, mute: bool = False,
                        record_path: str | None = None) -> bool:
        self._leave_demo()
        if record_path is None and not file_path and self.pending_record_path:
            record_path, self.pending_record_path = self.pending_record_path, None
        try:
            description = self.engine.start(device=device, file_path=file_path, mute=mute,
                                            record_path=record_path)
        except audio.AudioError as exc:
            QMessageBox.warning(self, "Could not start", str(exc)) if self.isVisible() else None
            self.statusBar().showMessage(str(exc))
            self._set_start_checked(False)
            return False
        self._attach_views()
        self.live_view.source_finished = False
        self.live_view.measured_up_to = -math.inf
        self._set_start_checked(True)
        learning = "" if self.engine.reference.calibrated else (
            "   Let them talk for about 20 seconds so the app can learn their voice.")
        saving = f"   Recording to {record_path}." if record_path else ""
        self.statusBar().showMessage(description + learning + saving)
        self._update_chips()
        return True

    def stop_listening(self) -> None:
        note = self.engine.stop()
        self._set_start_checked(False)
        self.statusBar().showMessage(note or "Stopped. Everything so far is kept: see Look back.")
        self._update_chips()

    def _attach_views(self) -> None:
        """Point every live view at the engine's current timeline and session."""
        self.live_view.timeline = self.engine.live
        if self.corner is not None:
            self.corner.timeline = self.engine.live
        self.live_map.set_session(self.engine.session)
        if self.review_is_live:
            self.review_session = self.engine.session
            self.review_map.set_session(self.engine.session)
            self._changes_key = None

    def _set_start_checked(self, on: bool) -> None:
        self.start_button.blockSignals(True)
        self.start_button.setChecked(on)
        self.start_button.setText("Stop" if on else "Start listening")
        self.start_button.setIcon(T.icon("stop", T.TEXT) if on else T.icon("play", "#0B0E13"))
        self.start_button.blockSignals(False)

    def _start_toggled(self, on: bool) -> None:
        if on:
            self.start_listening(device=self.mic_combo.currentData())
        else:
            self.stop_listening()

    def play_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Play a recording", DEMO_WAVS,
                                              "Sound files (*.wav *.flac *.ogg)")
        if path:
            self.start_listening(file_path=path)

    def try_demo(self, mute: bool = False) -> bool:
        """Play the demo recording through the live view, in a session of its own (so the
        demo voice is never measured against a real person's baseline, or the other way)."""
        if not os.path.isfile(DEMO_SESSION):
            self.statusBar().showMessage(f"The demo recording is missing: {DEMO_SESSION}")
            return False
        if not self.prepare_fresh_session("play the demo", clear_baseline=True):
            return False
        if not self.start_listening(file_path=DEMO_SESSION, mute=mute):
            return False
        self._demo_session = True
        self.tabs.setCurrentIndex(LIVE)
        self.statusBar().showMessage("Playing the demo: a synthetic voice talks normally for about "
                                     "25 seconds (the app learns it), then says one sentence four "
                                     "ways: even, slow with long pauses, fast and loud, flat and "
                                     "quiet.")
        return True

    def prepare_fresh_session(self, purpose: str, clear_baseline: bool) -> bool:
        """Start a new, empty session, asking first if the current one has unsaved
        measurements. Returns False if the person cancels."""
        session = self.engine.session
        unsaved = session.frame_count > self._saved_frames + 500 and not self._demo_session
        if self.confirm_close and unsaved:
            answer = QMessageBox.question(
                self, "Start a new session?",
                f"To {purpose}, the app starts a new session. Save this session's measurements "
                "first (numbers only, no sound)?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                return False
            if answer == QMessageBox.StandardButton.Save and not self.save_session_dialog():
                return False
        self.engine.new_session(keep_baseline=not (clear_baseline or self._demo_session))
        self._demo_session = False
        self._saved_frames = 0
        self.review_is_live = True
        self.review_title.setText("This session")
        self._attach_views()
        self.live_view.source_finished = False
        self._refresh_baseline_text()
        self._refresh_review(force=True)
        self._update_chips()
        return True

    def _leave_demo(self) -> None:
        """After the demo, anything real starts in a fresh session with no baseline."""
        if self._demo_session:
            self._demo_session = False
            self.engine.new_session(keep_baseline=False)
            self._saved_frames = 0
            self._attach_views()
            self._refresh_baseline_text()
            self._refresh_review(force=True)

    def new_session_clicked(self) -> None:
        if self.prepare_fresh_session("start a new session", clear_baseline=False):
            self.statusBar().showMessage("New session. Their usual voice is kept; press Learn voice again "
                                         "for a different speaker.")

    def recalibrate(self) -> None:
        self.engine.recalibrate()
        self._refresh_baseline_text()
        self._update_chips()
        self.statusBar().showMessage("Learning the voice again: keep the person talking for "
                                     "about 20 seconds.")

    def add_mark(self):
        now = self.engine.now()
        if now is None:
            self.statusBar().showMessage("Nothing to mark yet: start listening first.")
            return None
        marker = self.engine.session.add_marker(now)
        self.statusBar().showMessage(f"Marked {clock(now)}. Press N to mark and type a note; "
                                     "notes can also be added in Look back.")
        self._refresh_review(force=True)
        return marker

    def add_mark_with_note(self) -> None:
        marker = self.add_mark()
        if marker is None:
            return
        if self.side_panel.isHidden():
            self.set_side_panel(True)
        self._refresh_live_marks()
        self._focus_note(marker)

    def _focus_note(self, marker=None) -> None:
        if marker is None:
            item = self.live_marks.currentItem()
            k = item.data(Qt.ItemDataRole.UserRole) if item else None
            markers = self.engine.session.markers
            marker = markers[k] if k is not None and k < len(markers) else (markers[-1] if markers else None)
        if marker is None:
            return
        self._note_target = marker
        self.note_edit.setPlaceholderText(f"Note for {clock(marker.t)}, then Enter")
        self.note_edit.setText(marker.note)
        self.note_edit.setFocus()

    _note_target = None

    def save_note(self) -> None:
        markers = self.engine.session.markers
        marker = self._note_target if self._note_target in markers else (markers[-1] if markers else None)
        if marker is None:
            return
        marker.note = self.note_edit.text().strip()
        self.note_edit.clear()
        self.note_edit.setPlaceholderText("Note for the latest mark, then Enter")
        self.note_edit.clearFocus()
        self._note_target = None
        self._refresh_review(force=True)
        self.statusBar().showMessage(f"Saved the note at {clock(marker.t)}.")

    def _space(self) -> None:
        if self.tabs.currentIndex() == LIVE:
            self.freeze_button.toggle()

    def _freeze_toggled(self, on: bool) -> None:
        if on != (self.live_view.frozen_at is not None):
            self.live_view.toggle_freeze()
        if not on:
            now = self.engine.now()
            self.live_view.measured_up_to = now if now is not None else -math.inf

    def _set_live_seconds(self, value: int) -> None:
        self.live_seconds = float(value)
        self.live_view.history = self.live_seconds
        if self.corner is not None:
            self.corner.history = self.live_seconds
        self.prefs.set("live_seconds", float(value))

    def _set_strip_seconds(self, value: int) -> None:
        self.strip.seconds = float(value)
        self.prefs.set("strip_seconds", float(value))

    def _set_calibration_seconds(self, value: int) -> None:
        self.engine.calibration_seconds = float(value)
        self.prefs.set("calibration_seconds", float(value))

    def set_side_panel(self, on: bool) -> None:
        self.side_panel.setVisible(bool(on))
        for control in (getattr(self, "panel_button", None), getattr(self, "side_panel_check", None)):
            if control is not None and control.isChecked() != bool(on):
                control.blockSignals(True)
                control.setChecked(bool(on))
                control.blockSignals(False)
        self.prefs.set("side_panel", bool(on))

    def set_details(self, on: bool) -> None:
        """Each signal on its own row and the whole-session strip, under the display."""
        self.details.setVisible(bool(on))
        for control in (getattr(self, "details_action", None), getattr(self, "details_check", None)):
            if control is not None and control.isChecked() != bool(on):
                control.blockSignals(True)
                control.setChecked(bool(on))
                control.blockSignals(False)
        self.prefs.set("show_details", bool(on))

    def toggle_side_panel(self) -> None:
        if self.tabs.currentIndex() == LIVE:
            self.set_side_panel(self.side_panel.isHidden())

    def toggle_full_screen(self) -> None:
        self.showNormal() if self.isFullScreen() else self.showFullScreen()

    def set_show_numbers(self, on: bool) -> None:
        self.show_numbers = bool(on)
        self.prefs.set("show_numbers", self.show_numbers)
        self._sync_numbers_checks()
        self._refresh_baseline_text()
        self._changes_key = None
        self._refresh_review(force=True)
        if self.compare_grid.views:
            self._show_compare_numbers()

    def _sync_numbers_checks(self) -> None:
        for check in (getattr(self, "review_numbers_check", None),
                      getattr(self, "compare_numbers_check", None),
                      getattr(self, "setup_numbers_check", None)):
            if check is not None and check.isChecked() != self.show_numbers:
                check.blockSignals(True)
                check.setChecked(self.show_numbers)
                check.blockSignals(False)

    # ---- corner view ------------------------------------------------------------------------

    def _corner_toggled(self, on: bool) -> None:
        if on:
            if self.corner is None:
                self.corner = CornerWindow(self)
            self.corner.timeline = self.engine.live
            self.corner.history = self.live_seconds
            self.corner.show()
            self.corner.raise_()
        elif self.corner is not None:
            self.corner.hide()

    def corner_hidden(self) -> None:
        self.corner_button.blockSignals(True)
        self.corner_button.setChecked(False)
        self.corner_button.blockSignals(False)

    # ---- the regular update -----------------------------------------------------------------

    def _tick(self) -> None:
        self._tick_count += 1
        arrived = self.engine.drain()
        engine = self.engine
        if engine.running and engine.is_file and engine.worker.finished:
            now = engine.now()
            if now is not None and now >= engine.worker.end_time + engine.offset:
                self.stop_listening()
                self.live_view.source_finished = True
                if self._demo_session:
                    self.statusBar().showMessage("The demo has finished. Look back over it in "
                                                 "Look back, or press Start listening to try your "
                                                 "own voice.")
        status = engine.status()
        idle = not engine.running and engine.session.frame_count == 0
        if self.start_card.isHidden() == idle:
            self.start_card.setVisible(idle)
            if idle:
                self.start_card.place()
        self.live_view.status_message = status
        self.live_view.show_calibrating = engine.running
        if self.corner is not None:
            self.corner.show_calibrating = engine.running
        # Redraw rates while listening: the big view and the corner view 30 times a second
        # (smooth for a line scrolling at a few pixels a frame), the tracks 10 times; next to
        # nothing when idle. Drawing competes with the analysis for Python's attention.
        visible_live = self.tabs.currentIndex() == LIVE and not self.isMinimized()
        busy = engine.running or arrived > 0
        if visible_live:
            if self._tick_count % (2 if busy else 30) == 0:
                self.live_view.update()
            if self._tick_count % (6 if busy else 30) == 0 and not self.details.isHidden():
                self.strip.update()
        if self.corner is not None and self.corner.isVisible():
            self.corner.status_message = status
            if self._tick_count % (2 if busy else 30) == 0:
                self.corner.update()
        if self.compare_clock is not None:
            self.compare_grid.tick()
        if self._tick_count % 30 == 0:
            self._half_second(arrived)
        if self._tick_count % 120 == 0:
            self._refresh_review()
            self._report_delay()

    def _half_second(self, arrived: int) -> None:
        level = self.engine.last_level_db if self.engine.running else float("nan")
        self.live_meter.set_level(level)
        self.setup_meter.set_level(level)
        ref = self.engine.reference
        if ref.calibrated and not self._was_calibrated and self.engine.running:
            self.statusBar().showMessage("Learned this voice: the line is now white, and colour "
                                         "and the pace bar are on.", 10000)
        self._was_calibrated = ref.calibrated
        if self.engine.session.baseline is not None and self._baseline_shown is not self.engine.session.baseline:
            self._refresh_baseline_text()
        self._update_chips()
        if self.tabs.currentIndex() == LIVE and not self.details.isHidden():
            self.live_map.update()

    def _update_chips(self) -> None:
        """The status beside the tabs (listening or not, the session clock) and the three steps
        above the display: start, learn their usual voice, watch for changes."""
        engine = self.engine
        ref = engine.reference
        if engine.running and engine.source is not None:
            name = engine.source.name
            name = name if len(name) <= 30 else name[:29] + "…"
            status = [("on", ("Playing " if engine.is_file else "Listening: ") + name)]
        else:
            status = [("off", "Not listening")]
        if engine.session.frame_count:
            status.append(("", f"Session {clock(engine.session.end_time)}"))
        self.chips.set_items(status)

        if ref.calibrated:
            learn = ("check", "2  Knows their usual voice")
        elif engine.running:
            learn = (f"ring:{ref.progress:.2f}",
                     f"2  Learning their usual voice… {ref.progress * 100:.0f}%")
        else:
            learn = ("off", "2  Learn their usual voice")
        steps = [("check" if engine.running or engine.session.frame_count else "off",
                  "1  Start listening"),
                 learn,
                 ("on" if engine.running and ref.calibrated else "off",
                  "3  Watch how their voice changes")]
        if engine.running:
            current = 2 if ref.calibrated else 1
        else:
            current = 0 if not engine.session.frame_count else -1
        self.steps.set_items(steps, highlight=current)

    def _report_delay(self) -> None:
        lat = self.live_view.latencies
        if self.engine.running and not self.engine.is_file and lat:
            median = float(np.median(lat[-400:]))
            self.delay_label.setText(f"Delay {median:.0f} ms (voice to screen)")
            if self.debug:
                print(f"[debug] mic->screen latency median {median:.0f} ms, 95th pct "
                      f"{np.percentile(lat[-400:], 95):.0f} ms", flush=True)
        elif not self.engine.running:
            self.delay_label.setText("")

    def _refresh_baseline_text(self) -> None:
        base = self.engine.baseline
        self._baseline_shown = self.engine.session.baseline
        if base is None:
            self.baseline_text.setText("None yet: it is learned from the first seconds of speech.")
        elif self.show_numbers:
            self.baseline_text.setText(base.describe())
        else:
            text = describe_plainly(base)
            self.baseline_text.setText(text[:1].upper() + text[1:] + ".")

    # ---- review -----------------------------------------------------------------------------

    def _review_at(self, a: float, b: float) -> None:
        """From the live strip: jump to the review of that moment."""
        self.review_live_session()
        self.tabs.setCurrentIndex(REVIEW)
        self.review_map.select(a, b)

    def _review_now(self) -> None:
        self.review_live_session()
        self.tabs.setCurrentIndex(REVIEW)

    def review_live_session(self) -> None:
        self._set_review_session(self.engine.session, live=True, title="This session")

    def _set_review_session(self, session: Session, live: bool, title: str) -> None:
        self.review_session = session
        self.review_is_live = live
        self.review_title.setText(title)
        self.review_map.set_session(session)
        self.review_map.selection = None
        self._changes_key = None
        self.range_a = self.range_b = None
        self.ab_label.setText("A: not set   B: not set")
        self._refresh_review(force=True)
        if session.frame_count and session.baseline is not None:
            end = session.end_time
            self.review_map.select(max(0.0, end - 20.0), end)

    def _refresh_review(self, force: bool = False) -> None:
        self._refresh_live_marks()
        if self.tabs.currentIndex() != REVIEW and not force:
            return
        session = self.review_session
        if self.review_is_live:
            session = self.engine.session
            if session is not self.review_session:
                self.review_session = session
                self.review_map.set_session(session)
        key = (session.frame_count, session.baseline, len(session.markers),
               tuple(m.note for m in session.markers), self.show_numbers)
        if key == self._changes_key:
            return
        self._changes_key = key
        changes = session.find_changes() if session.baseline is not None else []
        self.review_map.changes = changes
        self.live_map.changes = changes if self.review_is_live else []
        self.changes_list.clear()
        for c in changes:
            item = QListWidgetItem(f"{clock(c.start)}–{clock(c.end)}   {c.words(self.show_numbers)}")
            item.setData(Qt.ItemDataRole.UserRole, (c.start, c.end))
            self.changes_list.addItem(item)
        if not changes:
            if session.frame_count == 0:
                text = ("No session yet. Start listening on the Live tab, or press Analyse a "
                        "recording and choose demo/wavs/session_demo.wav.")
            elif session.baseline is None:
                text = "Waiting for a baseline: the app is still learning this voice."
            else:
                text = "Nothing has stayed clearly away from the usual for long enough yet."
            self.changes_list.addItem(text)
        self.marks_list.clear()
        for k, m in enumerate(session.markers):
            item = QListWidgetItem(f"{clock(m.t)}   {m.note or '(no note)'}")
            item.setData(Qt.ItemDataRole.UserRole, k)
            self.marks_list.addItem(item)
        if not session.markers:
            self.marks_list.addItem("No marks yet. Press M during a session to mark a moment.")
        self.review_map.update()
        if self.review_map.selection:
            self._selection_changed(*self.review_map.selection)

    def _refresh_live_marks(self) -> None:
        markers = self.engine.session.markers
        key = (id(self.engine.session), tuple((m.t, m.note) for m in markers))
        if key == getattr(self, "_live_marks_key", None):
            return
        self._live_marks_key = key
        self.live_marks.clear()
        self.marks_card.setVisible(bool(markers))
        for k, m in enumerate(markers):
            item = QListWidgetItem(f"{clock(m.t)}   {m.note or '(no note: double-click to add one)'}")
            item.setData(Qt.ItemDataRole.UserRole, k)
            self.live_marks.addItem(item)
        if markers:
            self.live_marks.scrollToBottom()

    def _selection_changed(self, a: float, b: float) -> None:
        session = self.review_session
        self.selection_title.setText(f"Selected: {clock(a)} – {clock(b)} ({b - a:.0f} s)")
        self.detail_view.timeline = session.timeline(a, b)
        self.detail_view.history = max(b - a, 1.0) + 0.2
        self.detail_view.now_fn = (lambda d=b - a: d)
        if session.baseline is not None:
            self._review_reference = Reference.from_stats(session.baseline)
            summary = session.summarise(a, b)
            self.summary_label.setText(summary.sentence(session.baseline, self.show_numbers)
                                       if summary else "")
        else:
            voiced = [f for f in self.detail_view.timeline.f0 if f == f]
            self._review_reference = Reference(False, 0.0, float(np.median(voiced)) if voiced else None,
                                               None, None, None, None)
            self.summary_label.setText("No baseline yet, so nothing can be compared.")
        self.detail_view.update()

    def _change_clicked(self, item: QListWidgetItem) -> None:
        span = item.data(Qt.ItemDataRole.UserRole)
        if span:
            a, b = span
            pad = max(2.0, 0.2 * (b - a))
            self.review_map.select(max(0.0, a - pad), min(self.review_session.end_time, b + pad))

    def _mark_clicked(self, item: QListWidgetItem) -> None:
        k = item.data(Qt.ItemDataRole.UserRole)
        if k is not None and k < len(self.review_session.markers):
            t = self.review_session.markers[k].t
            self.review_map.select(max(0.0, t - 10.0), min(self.review_session.end_time, t + 10.0))

    def _edit_mark_note(self, item: QListWidgetItem) -> None:
        k = item.data(Qt.ItemDataRole.UserRole)
        if k is None or k >= len(self.review_session.markers):
            return
        marker = self.review_session.markers[k]
        text, ok = QInputDialog.getText(self, "Note", f"Note for {clock(marker.t)}:",
                                        text=marker.note)
        if ok:
            self.set_mark_note(k, text)

    def set_mark_note(self, index: int, text: str) -> None:
        self.review_session.markers[index].note = text.strip()
        self._refresh_review(force=True)

    def _delete_mark(self) -> None:
        item = self.marks_list.currentItem()
        k = item.data(Qt.ItemDataRole.UserRole) if item else None
        if k is not None and k < len(self.review_session.markers):
            del self.review_session.markers[k]
            self._refresh_review(force=True)

    def _mark_selection(self) -> None:
        if self.review_map.selection:
            a, b = self.review_map.selection
            self.review_session.add_marker((a + b) / 2)
            self._refresh_review(force=True)

    def _set_a(self) -> None:
        if self.review_map.selection:
            self.range_a = self.review_map.selection
            self._show_ab()

    def _set_b(self) -> None:
        if self.review_map.selection:
            self.range_b = self.review_map.selection
            self._show_ab()

    def _show_ab(self) -> None:
        def text(r):
            return f"{clock(r[0])}–{clock(r[1])}" if r else "not set"
        self.ab_label.setText(f"A: {text(self.range_a)}   B: {text(self.range_b)}")

    def compare_ranges(self) -> RangeCompareDialog | None:
        if not (self.range_a and self.range_b):
            self.statusBar().showMessage("Select a stretch and press Set as A, then another and "
                                         "press Set as B.")
            return None
        if self.review_session.baseline is None:
            self.statusBar().showMessage("Comparing needs a baseline first.")
            return None
        dialog = RangeCompareDialog(self.review_session, self.range_a, self.range_b, self,
                                    numbers=self.show_numbers)
        dialog.show()
        return dialog

    # ---- files ------------------------------------------------------------------------------

    def save_session(self, path: str) -> None:
        self.review_session.save(path)
        if self.review_is_live:
            self._saved_frames = self.engine.session.frame_count
        self.statusBar().showMessage(f"Saved the session (numbers only, no sound) to {path}")

    def open_session(self, path: str) -> None:
        session = Session.load(path)
        self._set_review_session(session, live=False, title=f"Opened: {os.path.basename(path)}")
        self.tabs.setCurrentIndex(REVIEW)

    def analyse_recording(self, path: str) -> Session:
        x, rate = audio.load_mono(path)
        # Uses the current baseline if there is one; otherwise the recording's own first
        # seconds of speech calibrate, exactly as they would live.
        rec = analyse_samples(x, rate, baseline=None if self._demo_session else self.engine.baseline,
                              name=os.path.basename(path))
        session = Session.from_recording(rec, os.path.basename(path))
        self._set_review_session(session, live=False,
                                 title=f"Recording: {os.path.basename(path)} (analysed)")
        self.tabs.setCurrentIndex(REVIEW)
        return session

    def save_baseline(self, path: str) -> None:
        if self.engine.baseline is None:
            raise ValueError("There is no baseline yet.")
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.engine.baseline.to_json())
        self.statusBar().showMessage(f"Saved the baseline to {path}")

    def load_baseline(self, path: str) -> None:
        with open(path, encoding="utf-8") as f:
            stats = BaselineStats.from_json(f.read())
        self._leave_demo()
        self.engine.use_baseline(stats)
        self._refresh_baseline_text()
        self._update_chips()
        self.statusBar().showMessage(f"Using the baseline from {os.path.basename(path)}")

    def baseline_from_recording(self, path: str) -> None:
        from .prosody import baseline_from_file
        stats = baseline_from_file(path)
        self._leave_demo()
        self.engine.use_baseline(stats)
        self._refresh_baseline_text()
        self._update_chips()
        self.statusBar().showMessage(f"Learned the baseline from {os.path.basename(path)}")

    def _file_action(self, action, path: str) -> bool:
        if not path:
            return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            action(path)
            return True
        except (OSError, ValueError, audio.AudioError) as exc:
            QMessageBox.warning(self, "Tone visualiser", str(exc))
            return False
        finally:
            QApplication.restoreOverrideCursor()

    def save_session_dialog(self) -> bool:
        name = f"session_{self.review_session.created:%Y-%m-%d_%H-%M}.tonevis"
        path, _ = QFileDialog.getSaveFileName(self, "Save session (numbers only, no sound)", name,
                                              "Tone visualiser sessions (*.tonevis)")
        return self._file_action(self.save_session, path)

    def open_session_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open session", "",
                                              "Tone visualiser sessions (*.tonevis)")
        self._file_action(self.open_session, path)

    def analyse_recording_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Analyse a recording", DEMO_WAVS,
                                              "Sound files (*.wav *.flac *.ogg)")
        self._file_action(self.analyse_recording, path)

    def export_summary(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.review_session.report(numbers=self.show_numbers) + "\n")
        self.statusBar().showMessage(f"Exported the summary to {path}")

    def export_summary_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export summary", "session_summary.txt",
                                              "Text (*.txt)")
        self._file_action(self.export_summary, path)

    def export_picture_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export picture", "session_review.png",
                                              "PNG image (*.png)")
        if path:
            self.tabs.widget(REVIEW).grab().save(path)
            self.statusBar().showMessage(f"Exported a picture of the review to {path}")

    def save_baseline_dialog(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save baseline", "baseline.json",
                                              "Baselines (*.json)")
        self._file_action(self.save_baseline, path)

    def load_baseline_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load baseline", "", "Baselines (*.json)")
        self._file_action(self.load_baseline, path)

    def baseline_from_recording_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Learn the baseline from a recording",
                                              DEMO_WAVS, "Sound files (*.wav *.flac *.ogg)")
        self._file_action(self.baseline_from_recording, path)

    # ---- compare ----------------------------------------------------------------------------

    def _set_compare_file(self, name: str, path: str) -> None:
        self.compare_files[name] = path
        edit = self.compare_paths[name]
        edit.setText(os.path.basename(path) if path else "")
        edit.setToolTip(path)

    def _choose_compare_file(self, name: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, f"Choose {name}", DEMO_WAVS,
                                              "Sound files (*.wav *.flac *.ogg)")
        if path:
            self._set_compare_file(name, path)

    def _use_demo_takes(self) -> None:
        self._set_compare_file("Baseline", os.path.join(DEMO_WAVS, "baseline_zira.wav"))
        for k in "ABCD":
            self._set_compare_file(k, os.path.join(DEMO_WAVS, f"take_{k.lower()}.wav"))

    def use_takes_from(self, folder: str) -> bool:
        base = os.path.join(folder, "baseline.wav")
        takes = {k: os.path.join(folder, f"{k.lower()}.wav") for k in "ABCD"}
        if not os.path.isfile(base) or not any(os.path.isfile(p) for p in takes.values()):
            self.statusBar().showMessage("No recordings in demo/takes yet: press Record your own "
                                         "takes to make them.")
            return False
        self._set_compare_file("Baseline", base)
        for k, p in takes.items():
            self._set_compare_file(k, p if os.path.isfile(p) else "")
        return True

    def _use_own_takes(self) -> None:
        self.use_takes_from(OWN_TAKES)

    def open_take_recorder(self, takes_dir: str | None = None) -> TakeRecorder:
        if self.take_recorder is None or not self.take_recorder.isVisible():
            self.take_recorder = TakeRecorder(self, takes_dir or OWN_TAKES)
        self.take_recorder.show()
        self.take_recorder.raise_()
        return self.take_recorder

    def run_comparison(self, play: bool) -> bool:
        from .tracker import AnalysisWorker
        from scipy.signal import resample_poly
        self._stop_comparison()
        names = [k for k in "ABCD" if self.compare_files.get(k)]
        paths = [self.compare_files[k] for k in names]
        if not paths:
            self.statusBar().showMessage("Choose at least one recording to compare.")
            return False
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            loaded = [(p, *audio.load_mono(p)) for p in paths]
            base_path = self.compare_files.get("Baseline", "")
            if base_path:
                from .prosody import baseline_from_file
                baseline = baseline_from_file(base_path)
            else:
                baseline = analyse_samples(loaded[0][1], loaded[0][2], learn_baseline=True).stats
            recordings = [analyse_samples(x, rate, baseline=baseline, name=os.path.basename(p))
                          for p, x, rate in loaded]
        except (audio.AudioError, ValueError) as exc:
            QMessageBox.warning(self, "Tone visualiser", str(exc)) if self.isVisible() else None
            self.statusBar().showMessage(str(exc))
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self._compare_result = (baseline, recordings)
        self._show_compare_numbers()
        clock_worker = starts = None
        if play:
            if self.engine.running:
                self.stop_listening()            # the microphone would hear the playback
            from math import gcd
            common, gap, position, pieces, starts = 48_000, 1.0, 0.0, [], []
            for _, x, rate in loaded:
                g = gcd(common, rate)
                y = x if rate == common else resample_poly(x, common // g, rate // g)
                starts.append(position)
                pieces += [np.asarray(y, dtype=np.float32), np.zeros(int(gap * common), np.float32)]
                position += y.size / common + gap
            q: queue.SimpleQueue = queue.SimpleQueue()
            source = audio.FileSource(q, samples=np.concatenate(pieces), rate=common,
                                      name="comparison")
            source.open()
            clock_worker = AnalysisWorker(q, source.samplerate, live=False, analyse=False)
            clock_worker.start()
            source.start()
            self.compare_source, self.compare_clock = source, clock_worker
        self.compare_grid.show_recordings(recordings, Reference.from_stats(baseline),
                                          clock_worker=clock_worker, starts=starts)
        if not play:
            self.compare_grid.tick()
        return True

    def _show_compare_numbers(self) -> None:
        result = getattr(self, "_compare_result", None)
        if result is None:
            return
        baseline, recordings = result
        if self.show_numbers:
            lines = [f"Baseline: {baseline.describe()}."]
            lines += [f"{letter} = {rec.name}: {rec.summary(baseline)}"
                      for letter, rec in zip("ABCD", recordings)]
            self.compare_numbers.setText("\n".join(lines))
        else:
            self.compare_numbers.setText("   ".join(f"{letter} = {rec.name}" for letter, rec
                                                    in zip("ABCD", recordings))
                                         + "      (tick Show numbers to see the measurements)")

    def _stop_comparison(self) -> None:
        if self.compare_source is not None:
            self.compare_source.stop()
        if self.compare_clock is not None:
            self.compare_clock.finish()
            self.compare_clock.join(timeout=2.0)
        self.compare_source = self.compare_clock = None

    # ---- closing ----------------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        unsaved = (self.engine.session.frame_count > self._saved_frames + 500
                   and not self._demo_session)
        if self.confirm_close and unsaved:
            answer = QMessageBox.question(
                self, "Save the session?",
                "Save this session's measurements (numbers only, no sound) before closing?",
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.StandardButton.Save:
                self.review_live_session()
                self.save_session_dialog()
        if not self.isFullScreen():
            self.prefs.set("geometry", self.saveGeometry())
        self.prefs.sync()
        self._timer.stop()
        if self.take_recorder is not None:
            self.take_recorder.close()
        self.engine.stop()
        self._stop_comparison()
        if self.corner is not None:
            self.corner.close()
        super().closeEvent(event)
