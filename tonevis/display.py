"""What you see. Everything is drawn with QPainter.

ToneView draws one stream (a Timeline) against the speaker's Reference:
  - the pitch line: height = pitch (up = higher, in semitones from the speaker's middle),
    thickness and brightness = loudness, colour = spectral tilt (the tension proxy);
  - thin joins across short unvoiced gaps, real gaps for pauses, shaded columns for long pauses;
  - one tick per syllable along the bottom, and the pace bar on the right;
  - the speaker's usual pitch range as a faint band around the centre line.
Time runs right to left: the newest sound enters at the right edge.

ToneWindow is the live window built around a ToneView. CompareWindow shows up to four
recordings side by side (the on-camera comparison).
"""

from __future__ import annotations

import math
import os
import time
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QLinearGradient, QPainter,
                           QPen, QPolygonF)
from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from . import config as C
from .features import semitones
from .session import Timeline  # noqa: F401  (drawn by the views below; kept importable here)

HELP_LINES = (
    "Height: pitch. Up = higher than this speaker's middle (dim line).",
    "Faint band: this speaker's usual pitch range.",
    "Thickness and brightness: loudness.",
    "Colour: amber = more pressed, blue = softer or breathier.",
    "Grey line: still learning this speaker's usual voice.",
    "Gaps: pauses. Shaded = 1 s or longer; darker = longer.",
    "Ticks along the bottom: syllables.",
    "Right-hand bar: pace. Up = faster than usual.",
    "Space pause   R learn voice again   T on top   H help   Q quit",
)


def _rgb(hex_colour: str) -> np.ndarray:
    c = QColor(hex_colour)
    return np.array([c.red(), c.green(), c.blue()], dtype=np.float64)


def _runs(indices: np.ndarray, t: np.ndarray) -> list[np.ndarray]:
    """Split frame indices into runs of consecutive frames (no index or time gaps)."""
    if indices.size == 0:
        return []
    breaks = np.flatnonzero((np.diff(indices) != 1)
                            | (np.diff(t[indices]) > 1.5 * C.FRAME_STEP)) + 1
    return np.split(indices, breaks)


def _smooth_runs(y: np.ndarray, runs: list[np.ndarray]) -> np.ndarray:
    """Averages the line over about C.LINE_SMOOTHING seconds (a triangular window) inside each
    voiced run, never across a gap, so it reads as a smooth curve."""
    full = max(1, int(round(C.LINE_SMOOTHING / C.FRAME_STEP / 2)))
    ys = y.copy()
    for run in runs:
        half = min(full, (run.size - 1) // 2)       # a short run gets a shorter window
        if half >= 1:
            kernel = np.concatenate([np.arange(1, half + 2),
                                     np.arange(half, 0, -1)]).astype(np.float64)
            values = y[run]
            weights = np.convolve(np.ones_like(values), kernel, mode="same")
            ys[run] = np.convolve(values, kernel, mode="same") / weights
    return ys


def tension_value(delta_db) -> np.ndarray:
    """Spectral tilt change from baseline (dB) -> -1 (blue) .. 0 (neutral) .. +1 (amber)."""
    d = np.nan_to_num(np.asarray(delta_db, dtype=np.float64), nan=0.0)
    span = C.TILT_FULL_SCALE_DB - C.TILT_DEAD_ZONE_DB
    return np.sign(d) * np.clip((np.abs(d) - C.TILT_DEAD_ZONE_DB) / span, 0.0, 1.0)


@dataclass
class _Layout:
    plot: QRectF   # the pitch line
    lane: QRectF   # syllable ticks
    pace: QRectF   # pace bar
    text: QRectF   # disclaimer


class ToneView(QWidget):
    """Draws one Timeline. Set `now_fn` to say what time the right-hand edge shows."""

    def __init__(self, timeline: Timeline, reference_fn, *, history: float = C.HISTORY_SECONDS,
                 label: str = "", show_disclaimer: bool = True, anchor_left: bool = False,
                 parent=None):
        super().__init__(parent)
        self.timeline = timeline
        self.reference_fn = reference_fn
        self.history = float(history)
        self.label = label
        self.show_disclaimer = show_disclaimer
        # Live views scroll (the newest sound at the right edge). A recording shown whole is
        # drawn from the left edge instead, like a pen writing, with 0 s at the left.
        self.anchor_left = anchor_left
        self.now_fn = lambda: None
        self.frozen_at: float | None = None
        self.show_help = False
        self.show_calibrating = True     # the "learning this voice" ring, until it is learned
        self.learning_banner = False     # also a big "keep talking" banner (the main view only)
        self.axis_words = False          # "higher" / "lower" beside the middle line (main view)
        self.cap_scale = False           # big views: at most C.MAX_PX_PER_SEMITONE per semitone
        self.glow = True                 # soft glow behind the line
        self.help_lines = HELP_LINES
        self.source_finished = False     # a finished file: its trailing silence is not a pause
        self.status_message = ""
        self.debug_line = ""
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setMinimumSize(*C.MIN_WINDOW_SIZE)
        self._bg = QColor(C.BACKGROUND)
        self._bg_rgb = _rgb(C.BACKGROUND)
        self._neutral, self._warm, self._cool = _rgb(C.NEUTRAL), _rgb(C.WARM), _rgb(C.COOL)
        self._grey = _rgb(C.CALIBRATING_LINE)
        self._pens: dict = {}
        red, green, blue, alphas = C.PAUSE_FILL      # pause shades, pre-mixed with the background
        self._pause_colours = [QColor(*(int(round(b + (c - b) * a / 255.0))
                                        for c, b in zip((red, green, blue), self._bg_rgb)))
                               for a in alphas]

    # ---- time -------------------------------------------------------------------------------

    def current_time(self) -> float | None:
        return self.frozen_at if self.frozen_at is not None else self.now_fn()

    def toggle_freeze(self) -> None:
        self.frozen_at = None if self.frozen_at is not None else self.now_fn()
        self.update()

    # ---- geometry ---------------------------------------------------------------------------

    def layout_rects(self) -> _Layout:
        w, h = float(self.width()), float(self.height())
        text_h = QFontMetricsF(self.font()).height() + 6.0 if self.show_disclaimer else 0.0
        right = w - 8.0 - C.PACE_BAR_WIDTH - 8.0
        lane_bottom = h - text_h - 6.0
        lane = QRectF(8.0, lane_bottom - C.RHYTHM_LANE, right - 8.0, C.RHYTHM_LANE)
        plot = QRectF(8.0, 8.0, right - 8.0, max(1.0, lane.top() - 4.0 - 8.0))
        pace = QRectF(right + 8.0, 8.0, C.PACE_BAR_WIDTH, lane.bottom() - 8.0)
        text = QRectF(8.0, h - text_h, w - 16.0, text_h)
        return _Layout(plot, lane, pace, text)

    def y_for(self, st, plot: QRectF):
        """Semitones from the speaker's middle -> screen y (up = higher)."""
        half = plot.height() / 2.0 - C.RIBBON_WIDTH[1] / 2.0 - 1.0
        if self.cap_scale:
            half = min(half, C.MAX_PX_PER_SEMITONE * C.SEMITONE_RANGE)
        return plot.center().y() - np.asarray(st) / C.SEMITONE_RANGE * half

    def x_for(self, t, now: float, plot: QRectF):
        if self.anchor_left:
            return plot.left() + np.asarray(t) / self.history * plot.width()
        return plot.right() - (now - np.asarray(t)) / self.history * plot.width()

    def visible_from(self, now: float) -> float:
        """The earliest time on screen."""
        return 0.0 if self.anchor_left else now - self.history

    # ---- painting ---------------------------------------------------------------------------

    def paintEvent(self, event) -> None:
        now = self.current_time()
        ref = self.reference_fn()
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.fillRect(self.rect(), self._bg)
            r = self.layout_rects()
            # Pause columns first, as solid colours: see-through fills over large areas are
            # the most expensive thing to draw, and this is redrawn up to 60 times a second.
            if now is not None:
                self._draw_pauses(painter, r, now)
            if ref.calibrated and ref.band_st is not None:
                self._draw_band(painter, r.plot, ref.band_st)
            painter.setPen(QPen(QColor(C.CENTRE_LINE), 1.0))
            cy = r.plot.center().y()
            painter.drawLine(QPointF(r.plot.left(), cy), QPointF(r.plot.right(), cy))
            if self.axis_words:
                self._draw_axis_words(painter, r.plot)
            if now is not None:
                if ref.pitch_hz:
                    self._draw_line(painter, r.plot, now, ref)
                self._draw_rhythm(painter, r.lane, now)
            self._draw_pace(painter, r.pace, now, ref)
            self._draw_overlays(painter, r, ref)
        finally:
            painter.end()

    def _draw_band(self, painter: QPainter, plot: QRectF, band) -> None:
        low, high = band
        top, bottom = float(self.y_for(high, plot)), float(self.y_for(low, plot))
        painter.fillRect(QRectF(plot.left(), top, plot.width(), bottom - top),
                         QColor(*C.USUAL_BAND))

    def _draw_pauses(self, painter: QPainter, r: _Layout, now: float) -> None:
        tl = self.timeline
        spans = [(s, min(e, now)) for s, e in tl.pauses
                 if min(e, now) - s >= C.LONG_PAUSE - 1e-6 and e > self.visible_from(now)]
        i = tl.latest(now)
        if i >= 0 and not self.source_finished:
            since = tl.pause_since[i]
            if (not math.isnan(since) and now - since >= C.LONG_PAUSE
                    and all(abs(s - since) > 1e-6 for s, _ in spans)):
                spans.append((since, now))
        top, height = r.plot.top(), r.lane.bottom() - r.plot.top()
        for start, end in spans:
            level = sum(end - start >= step - 1e-6 for step in C.PAUSE_STEPS)
            x0 = max(r.plot.left(), float(self.x_for(start, now, r.plot)))
            x1 = min(r.plot.right(), float(self.x_for(end, now, r.plot)))
            if x1 > x0:
                painter.fillRect(QRectF(x0, top, x1 - x0, height), self._pause_colours[max(level, 1) - 1])

    def _pen(self, rgb, width: float, alpha: int = 255) -> QPen:
        key = (int(rgb[0]), int(rgb[1]), int(rgb[2]), int(round(width * 2)), alpha)
        pen = self._pens.get(key)
        if pen is None:
            if len(self._pens) > 4000:
                self._pens.clear()
            pen = QPen(QColor(key[0], key[1], key[2], alpha))
            pen.setWidthF(key[3] / 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self._pens[key] = pen
        return pen

    def _draw_line(self, painter: QPainter, plot: QRectF, now: float, ref) -> None:
        tl = self.timeline
        lo = bisect_left(tl.t, self.visible_from(now) - 0.3)
        hi = bisect_right(tl.t, now)
        if hi - lo < 2:
            return
        t = np.asarray(tl.t[lo:hi])
        st = semitones(tl.f0[lo:hi], ref.pitch_hz)            # NaN where unvoiced
        voiced = ~np.isnan(st)
        st0 = np.where(voiced, st, 0.0)
        in_range = voiced & (np.abs(st0) <= C.SEMITONE_RANGE)
        x = self.x_for(t, now, plot)
        y = self.y_for(st0, plot)

        # Loudness -> thickness and brightness, relative to the speaker's typical level.
        loud = np.asarray(tl.loud[lo:hi])
        level_ref = ref.level_db if ref.level_db is not None else float(np.nanmedian(loud))
        low_db, high_db = C.LOUDNESS_RANGE_DB
        u = np.nan_to_num(np.clip((loud - level_ref - low_db) / (high_db - low_db), 0.0, 1.0),
                          nan=0.5)
        width = C.RIBBON_WIDTH[0] + u * (C.RIBBON_WIDTH[1] - C.RIBBON_WIDTH[0])
        bright = C.RIBBON_BRIGHTNESS[0] + u * (C.RIBBON_BRIGHTNESS[1] - C.RIBBON_BRIGHTNESS[0])
        bright = bright * self._fade(x, plot)      # the oldest seconds fade into the background

        # Spectral tilt -> colour, once calibrated; grey while calibrating.
        n = t.size
        if ref.calibrated and ref.tilt_db is not None:
            v = tension_value(np.asarray(tl.tilt[lo:hi]) - ref.tilt_db)[:, None]
            base = (self._neutral + np.clip(v, 0, 1) * (self._warm - self._neutral)
                    + np.clip(-v, 0, 1) * (self._cool - self._neutral))
        elif ref.calibrated:
            base = np.tile(self._neutral, (n, 1))
        else:
            base = np.tile(self._grey, (n, 1))
        rgb = self._bg_rgb + (base - self._bg_rgb) * bright[:, None]

        runs = [run for run in _runs(np.flatnonzero(in_range), t)
                if run.size >= C.MIN_VOICED_FRAMES]
        ys = _smooth_runs(y, runs)

        painter.save()
        # Clip to the plot, but let the "now" dot at the right edge show whole (it would
        # otherwise be cut in half); the gap before the pace bar leaves room for it.
        painter.setClipRect(plot.adjusted(0.0, -C.RIBBON_WIDTH[1],
                                          C.NOW_DOT_RADIUS + 1.0, C.RIBBON_WIDTH[1]))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        # Soft glow behind each voiced stretch (helps in peripheral vision, and on camera).
        if self.glow:
            for run in runs:
                painter.setPen(self._pen(rgb[run].mean(axis=0),
                                         float(width[run].mean()) + C.GLOW_EXTRA, alpha=34))
                painter.drawPolyline(QPolygonF([QPointF(a, b) for a, b in
                                                zip(x[run].tolist(), ys[run].tolist())]))
        # Thin joins across short unvoiced gaps inside speech (consonants), so that only real
        # pauses show as gaps.
        for a, b in zip(runs, runs[1:]):
            if t[b[0]] - t[a[-1]] <= C.BRIDGE_MAX + 1e-6:
                colour = self._bg_rgb + ((rgb[a[-1]] + rgb[b[0]]) / 2 - self._bg_rgb) * 0.8
                painter.setPen(self._pen(colour, C.BRIDGE_WIDTH))
                painter.drawLine(QPointF(x[a[-1]], ys[a[-1]]), QPointF(x[b[0]], ys[b[0]]))
        # The line itself, in short pieces (80 ms) so thickness and colour can change along it.
        for run in runs:
            for k in range(0, run.size - 1, 7):
                piece = run[k:k + 8]
                mid = piece[piece.size // 2]
                painter.setPen(self._pen(rgb[mid], float(width[mid])))
                painter.drawPolyline(QPolygonF([QPointF(a, b) for a, b in
                                                zip(x[piece].tolist(), ys[piece].tolist())]))
        # Beyond the scale: a faint dash along the top or bottom edge, not a line pinned there.
        painter.setPen(self._pen(_rgb(C.OFF_SCALE_MARK), 2.0))
        for run in _runs(np.flatnonzero(voiced & ~in_range), t):
            if run.size >= C.MIN_VOICED_FRAMES:
                up = st0[run[0]] > 0
                if self.cap_scale:              # the scale's own edge, inside a tall plot
                    edge = float(self.y_for(C.SEMITONE_RANGE if up else -C.SEMITONE_RANGE, plot))
                else:
                    edge = plot.top() + 1.0 if up else plot.bottom() - 1.0
                painter.drawLine(QPointF(float(x[run[0]]), edge),
                                 QPointF(float(x[run[-1]]), edge))
        # The newest voiced sound: a glowing dot.
        if runs:
            last = int(runs[-1][-1])
            if now - t[last] <= C.NOW_DOT_MAX_AGE:
                centre = QPointF(float(x[last]), float(ys[last]))
                colour = rgb[last]
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(int(colour[0]), int(colour[1]), int(colour[2]), 60))
                painter.drawEllipse(centre, C.NOW_DOT_RADIUS * 2.2, C.NOW_DOT_RADIUS * 2.2)
                painter.setBrush(QColor(int(colour[0]), int(colour[1]), int(colour[2])))
                painter.drawEllipse(centre, C.NOW_DOT_RADIUS, C.NOW_DOT_RADIUS)
        painter.restore()

    def _draw_rhythm(self, painter: QPainter, lane: QRectF, now: float) -> None:
        tl = self.timeline
        lo = bisect_left(tl.nuclei, self.visible_from(now))
        hi = bisect_right(tl.nuclei, now)
        if hi <= lo:
            return
        xs = np.atleast_1d(self.x_for(tl.nuclei[lo:hi], now, lane))
        fade = self._fade(xs, lane)
        tick = _rgb(C.RHYTHM_TICK)
        full = fade >= 1.0
        painter.setPen(self._pen(tick, 2.0))
        painter.drawLines([QLineF(float(v), lane.top() + 1.0, float(v), lane.bottom() - 1.0)
                           for v in xs[full]])
        for v, f in zip(xs[~full], fade[~full]):
            painter.setPen(self._pen(self._bg_rgb + (tick - self._bg_rgb) * f, 2.0))
            painter.drawLine(QPointF(float(v), lane.top() + 1.0), QPointF(float(v), lane.bottom() - 1.0))

    def _fade(self, x, plot: QRectF):
        """1 for most of the window, falling towards the left edge (the oldest seconds), so
        old sound fades out instead of being cut off. None for recordings shown whole."""
        x = np.asarray(x, dtype=np.float64)
        if self.anchor_left:
            return np.ones_like(x)
        return np.clip((x - plot.left()) / max(plot.width() * C.FADE_FRACTION, 1.0), 0.15, 1.0)

    def _draw_pace(self, painter: QPainter, pace: QRectF, now: float | None, ref) -> None:
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C.PACE_TRACK))
        painter.drawRoundedRect(pace, 3.0, 3.0)
        cy = pace.center().y()
        painter.setPen(QPen(QColor(C.PACE_NOTCH), 2.0))
        painter.drawLine(QPointF(pace.left() - 3.0, cy), QPointF(pace.right() + 3.0, cy))
        if not (ref.calibrated and ref.rate and now is not None):
            return
        i = self.timeline.latest(now)
        if i < 0:
            return
        rate = self.timeline.rate[i]
        if not (rate > 0):
            return
        value = float(np.clip(math.log2(rate / ref.rate) / C.PACE_FULL_SCALE, -1.0, 1.0))
        extent = value * (pace.height() / 2.0 - 2.0)
        colour = QColor(C.PACE_FILL)
        if not math.isnan(self.timeline.pause_since[i]):
            colour.setAlpha(110)                # paused: this is the pace before the pause
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(colour)
        top = cy - max(extent, 0.0)
        painter.drawRoundedRect(QRectF(pace.left() + 1.5, top, pace.width() - 3.0,
                                       max(abs(extent), 2.0)), 2.0, 2.0)

    def _draw_overlays(self, painter: QPainter, r: _Layout, ref) -> None:
        dim = QColor(C.DIM_TEXT)
        painter.setPen(dim)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        corner = QPointF(r.plot.left() + 2.0, r.plot.top())
        if self.label:
            font = QFont(self.font())
            font.setBold(True)
            if font.pointSizeF() > 0:          # -1 when the font is sized in pixels
                font.setPointSizeF(font.pointSizeF() * 1.25)
            painter.setFont(font)
            painter.drawText(QRectF(corner.x(), corner.y(), 40.0, 24.0),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.label)
            painter.setFont(self.font())
        elif not ref.calibrated and self.show_calibrating:
            if self.learning_banner:            # the big banner says it all on the main view
                self._draw_learning_banner(painter, r.plot, ref.progress)
            else:
                self._draw_calibrating(painter, corner, ref.progress)
        if self.frozen_at is not None:          # "paused" sign: two bars, top right
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(C.NEUTRAL))
            for dx in (12.0, 6.0):
                painter.drawRect(QRectF(r.plot.right() - dx, r.plot.top() + 2.0, 3.0, 11.0))
            painter.setPen(dim)
        if self.status_message:
            painter.drawText(r.plot, Qt.AlignmentFlag.AlignCenter, self.status_message)
        if self.show_disclaimer:
            text = QFontMetricsF(self.font()).elidedText(C.DISCLAIMER,
                                                         Qt.TextElideMode.ElideRight,
                                                         r.text.width())
            painter.drawText(r.text, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                             text)
        if self.debug_line:
            painter.drawText(r.plot.adjusted(0.0, 18.0 if not ref.calibrated else 0.0, -18.0, 0.0),
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
                             self.debug_line)
        if self.show_help:
            self._draw_help(painter)

    def _draw_calibrating(self, painter: QPainter, corner: QPointF, progress: float) -> None:
        ring = QRectF(corner.x() + 1.0, corner.y() + 2.0, 12.0, 12.0)
        painter.setPen(QPen(QColor(C.PACE_TRACK), 2.5))
        painter.drawEllipse(ring)
        pen = QPen(QColor(C.CALIBRATING_LINE), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(ring, 90 * 16, -int(360 * 16 * max(0.0, min(1.0, progress))))
        painter.setPen(QColor(C.DIM_TEXT))
        painter.drawText(QRectF(ring.right() + 6.0, corner.y(), 200.0, 16.0),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         "learning this voice…")

    def _draw_learning_banner(self, painter: QPainter, plot: QRectF, progress: float) -> None:
        """While the voice is being learned: what is happening and what to do, big enough to
        read across a room, with a bar that fills as it learns."""
        font = QFont(self.font())
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 1.35)
        fm = QFontMetricsF(font)
        lines = ("Learning their usual voice: keep talking normally",
                 "The line is grey until it knows them, then turns white")
        w = min(plot.width() - 24.0, max(fm.horizontalAdvance(s) for s in lines) + 48.0)
        h = fm.height() * 2 + 34.0
        box = QRectF(plot.center().x() - w / 2.0, plot.top() + 10.0, w, h)
        painter.save()
        painter.setPen(QPen(QColor(C.CENTRE_LINE), 1.0))
        painter.setBrush(QColor(8, 10, 14, 215))
        painter.drawRoundedRect(box, 8.0, 8.0)
        painter.setFont(font)
        painter.setPen(QColor(C.NEUTRAL))
        painter.drawText(QRectF(box.left(), box.top() + 8.0, w, fm.height()),
                         Qt.AlignmentFlag.AlignCenter, fm.elidedText(lines[0], Qt.TextElideMode.ElideRight, w - 24.0))
        painter.setFont(self.font())
        painter.setPen(QColor(C.DIM_TEXT))
        painter.drawText(QRectF(box.left(), box.top() + 8.0 + fm.height(), w, fm.height()),
                         Qt.AlignmentFlag.AlignCenter,
                         QFontMetricsF(self.font()).elidedText(lines[1], Qt.TextElideMode.ElideRight, w - 24.0))
        bar = QRectF(box.left() + 24.0, box.bottom() - 12.0, w - 48.0, 4.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(C.PACE_TRACK))
        painter.drawRoundedRect(bar, 2.0, 2.0)
        painter.setBrush(QColor(C.CALIBRATING_LINE))
        painter.drawRoundedRect(QRectF(bar.left(), bar.top(),
                                       bar.width() * max(0.02, min(1.0, progress)), bar.height()),
                                2.0, 2.0)
        painter.restore()

    def _draw_axis_words(self, painter: QPainter, plot: QRectF) -> None:
        """'higher' above the middle line and 'lower' below it, at the faded left edge, so a
        first-time viewer can read the height without the key. The middle line is their usual."""
        if plot.height() < 160:
            return
        painter.save()
        font = QFont(self.font())
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 0.9)
        painter.setFont(font)
        painter.setPen(QColor(C.DIM_TEXT))
        fm = QFontMetricsF(font)
        cy = plot.center().y()
        x = plot.left() + 6.0
        painter.drawText(QPointF(x, cy - 6.0), "↑ higher than usual")
        painter.drawText(QPointF(x, cy + 6.0 + fm.ascent()), "↓ lower than usual")
        painter.restore()

    def help_rect(self) -> QRectF:
        fm = QFontMetricsF(self.font())
        line_h = fm.height() + 2.0
        box_w = min(self.width() - 16.0,
                    max(fm.horizontalAdvance(s) for s in self.help_lines) + 24.0)
        box_h = min(self.height() - 16.0, line_h * len(self.help_lines) + 16.0)
        return QRectF((self.width() - box_w) / 2.0, (self.height() - box_h) / 2.0, box_w, box_h)

    def _draw_help(self, painter: QPainter) -> None:
        fm = QFontMetricsF(self.font())
        line_h = fm.height() + 2.0
        box = self.help_rect()
        painter.setPen(QPen(QColor(C.CENTRE_LINE), 1.0))
        painter.setBrush(QColor(8, 10, 14, 235))
        painter.drawRoundedRect(box, 6.0, 6.0)
        painter.setPen(QColor(C.NEUTRAL))
        for k, line in enumerate(self.help_lines):
            text = fm.elidedText(line, Qt.TextElideMode.ElideRight, box.width() - 24.0)
            painter.drawText(QRectF(box.left() + 12.0, box.top() + 8.0 + k * line_h,
                                    box.width() - 24.0, line_h),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)

    def save_snapshot(self, path: str) -> bool:
        path = os.path.abspath(path)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        ok = self.grab().save(path)
        print(("Saved a picture of the window to " if ok else "Could not save a picture to ")
              + path, flush=True)
        return ok


class ToneWindow(ToneView):
    """The live window: a ToneView fed by an AnalysisWorker."""

    def __init__(self, worker, *, source=None, debug: bool = False,
                 snapshot_path: str | None = None, quit_after: float | None = None,
                 history_seconds: float = C.HISTORY_SECONDS):
        super().__init__(Timeline(), lambda: worker.reference, history=history_seconds)
        self.worker = worker
        self.source = source
        self.debug = debug
        self.snapshot_path = snapshot_path
        self._snapshot_taken = False
        self._stalled = False
        self._quit_after = quit_after
        self._opened_at = time.perf_counter()
        self._closing = False
        self.now_fn = self._stream_now

        self.setWindowTitle("Tone visualiser")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.resize(*C.WINDOW_SIZE)

        # --debug bookkeeping
        if getattr(worker, "live", False):
            self._label = "mic->screen"
        elif source is not None and not getattr(source, "mute", True):
            self._label = "heard->screen"
        else:
            self._label = "file->screen"
        self._latencies: list[float] = []
        self._measured_up_to = -math.inf
        self._last_report = time.perf_counter()
        self._frames_since_report = 0
        self._voiced_since_report = 0
        self._paints_since_report = 0

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._timer.start(max(1, round(1000 / C.FPS)))

    # ---- time -------------------------------------------------------------------------------

    def _stream_now(self) -> float | None:
        """The stream time being heard right now: the right-hand edge of the window."""
        clock = self.worker.clock
        if clock.offset is None:
            return None
        now = clock.stream_now()
        if self.worker.finished and self.worker.end_time is not None:
            now = min(now, self.worker.end_time)   # a finished file freezes on its last moment
        return now

    # ---- per-frame update -------------------------------------------------------------------

    def _tick(self) -> None:
        newest = None
        frames = self.worker.frames
        while frames:
            pf, _ready = frames.popleft()
            self.timeline.add_frame(pf)
            self._frames_since_report += 1
            if not math.isnan(pf.f0):
                self._voiced_since_report += 1
            newest = pf.t
        events = self.worker.events
        while events:
            ev = events.popleft()
            if ev[0] == "calibrated":
                print(f"Calibrated: {ev[1].describe()}", flush=True)
            self.timeline.add_event(ev)
        if newest is not None:
            self.timeline.trim(newest - self.history - 2.0)
        self.source_finished = self.worker.finished
        self.status_message = self._status_message()
        self.update()
        self._check_stall()
        if self.debug:
            self._report()
        self._check_finish()

    def _check_finish(self) -> None:
        if self._closing:
            return
        timed_out = (self._quit_after is not None
                     and time.perf_counter() - self._opened_at >= self._quit_after)
        file_done = False
        if self.snapshot_path and self.worker.finished and self.worker.end_time is not None:
            now = self.now_fn()
            file_done = now is not None and now >= self.worker.end_time
        if timed_out or file_done:
            self.close()

    def _status_message(self) -> str:
        """A problem with the microphone itself, shown in the middle of the window."""
        if not getattr(self.worker, "live", False):
            return ""
        last = getattr(self.worker, "last_block_at", None)
        if last is not None and time.perf_counter() - last > C.STALL_SECONDS:
            return "The microphone stopped sending sound.\nClose the app and start it again."
        if getattr(self.worker, "silent_input", False):
            return "No sound from the microphone"
        return ""

    def _check_stall(self) -> None:
        stalled = self.status_message.startswith("The microphone stopped")
        if stalled != self._stalled:
            self._stalled = stalled
            print("WARNING: the microphone stopped sending sound." if stalled
                  else "The microphone is sending sound again.", flush=True)

    # ---- painting and --debug latency -------------------------------------------------------

    def paintEvent(self, event) -> None:
        self._paints_since_report += 1
        super().paintEvent(event)
        now = self.current_time()
        if self.debug and now is not None and self.frozen_at is None:
            self._measure_latency(now)

    def _measure_latency(self, now: float) -> None:
        """For each frame that just became visible: time from its sound reaching the
        microphone (or the listener, for a file) to the end of this paint."""
        painted = time.perf_counter()
        t = self.timeline.t
        i = bisect_right(t, self._measured_up_to)
        j = bisect_right(t, now)
        if j <= i:
            return
        wall = self.worker.clock.wall
        self._latencies.extend((painted - wall(t[k])) * 1000.0 for k in range(i, j))
        self._measured_up_to = t[j - 1]

    def _report(self) -> None:
        now = time.perf_counter()
        if now - self._last_report < 2.0:
            return
        self._last_report = now
        lat = np.asarray(self._latencies)
        self._latencies = []
        parts = []
        if lat.size:
            med, p95 = float(np.median(lat)), float(np.percentile(lat, 95))
            parts.append(f"{self._label} latency: median {med:.0f} ms, 95th pct {p95:.0f} ms, "
                         f"max {lat.max():.0f} ms (n={lat.size})")
            self.debug_line = f"{med:.0f} ms median / {p95:.0f} ms p95"
        else:
            parts.append(f"{self._label} latency: nothing new drawn")
        parts.append(f"pitch analysis {self.worker.tracker.mean_run_ms:.2f} ms/run")
        parts.append(f"audio in {self.worker.seconds_received:.1f} s, "
                     f"backlog {self.worker.backlog} blocks")
        if self.source is not None:
            parts.append(f"device buffer {self.source.latency * 1000:.0f} ms (reported)")
            drops = getattr(self.source, "overflows", 0) + getattr(self.source, "underflows", 0)
            parts.append(f"dropouts {drops}")
        if self._frames_since_report:
            voiced = 100.0 * self._voiced_since_report / self._frames_since_report
            parts.append(f"voiced {voiced:.0f}% of frames")
        handle = self.windowHandle()
        exposed = handle.isExposed() if handle is not None else False
        state = "minimized" if self.isMinimized() else ("shown" if exposed else "not exposed")
        parts.append(f"redraws {self._paints_since_report} (window {state})")
        self._frames_since_report = self._voiced_since_report = self._paints_since_report = 0
        print("[debug] " + " | ".join(parts), flush=True)

    # ---- keys, closing, pictures ------------------------------------------------------------

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()
        elif key == Qt.Key.Key_T:
            on_top = bool(self.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, not on_top)
            self.show()   # Qt needs this after changing window flags
        elif key == Qt.Key.Key_Space:
            self.toggle_freeze()
            if self.frozen_at is None:       # frames that arrived while frozen are not "new"
                now = self.now_fn()
                if now is not None:
                    self._measured_up_to = now
        elif key == Qt.Key.Key_R:
            self.worker.request_recalibration()
            print("Learning the voice again: the next 15 s or so of speech set their usual voice.", flush=True)
        elif key == Qt.Key.Key_H:
            self.show_help = not self.show_help
            self.update()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._closing = True
        if self.snapshot_path and not self._snapshot_taken:
            self._snapshot_taken = True
            self.save_snapshot(self.snapshot_path)
        self._timer.stop()
        super().closeEvent(event)


class CompareGrid(QWidget):
    """Up to four recordings side by side against one baseline, on one shared time scale:
    the same words, delivered in different ways. With a clock (playback), each panel fills in
    while its recording plays; without one, every panel shows its whole recording at once."""

    LETTERS = "ABCD"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(6)
        self.views: list[ToneView] = []
        self.clock_worker = None
        self.starts: list[float] = []

    def show_recordings(self, recordings, reference, *, clock_worker=None, starts=None,
                        history: float | None = None) -> None:
        for view in self.views:
            self._grid.removeWidget(view)
            view.deleteLater()
        self.views = []
        self.clock_worker = clock_worker
        self.starts = list(starts) if starts else [0.0] * len(recordings)
        if not recordings:
            return
        history = history or max(rec.duration for rec in recordings) + 0.3
        cols = 2 if len(recordings) > 1 else 1
        for i, rec in enumerate(recordings):
            view = ToneView(Timeline.from_recording(rec), lambda: reference, history=history,
                            label=self.LETTERS[i], show_disclaimer=False, anchor_left=True)
            view.source_finished = True
            view.now_fn = self._now_for(i, rec.duration)
            self._grid.addWidget(view, i // cols, i % cols)
            self.views.append(view)
        for row in range(3):
            self._grid.setRowStretch(row, 1 if row < (len(recordings) + cols - 1) // cols else 0)

    def _now_for(self, i: int, duration: float):
        if self.clock_worker is None:
            return lambda: duration
        start = self.starts[i]

        def now():
            clock = self.clock_worker.clock
            if clock.offset is None:
                return None
            local = clock.stream_now() - start
            return None if local < 0 else min(local, duration)
        return now

    def playing_done(self) -> bool:
        worker = self.clock_worker
        return (worker is not None and worker.finished and worker.clock.offset is not None
                and worker.end_time is not None
                and worker.clock.stream_now() >= worker.end_time)

    def tick(self) -> None:
        for view in self.views:
            view.update()

    def toggle_freeze(self) -> None:
        for view in self.views:
            view.toggle_freeze()

    def toggle_help(self) -> None:
        for view in self.views:
            view.show_help = not view.show_help
            view.update()


class CompareWindow(QWidget):
    """The comparison on its own (--compare and run_demo.bat)."""

    def __init__(self, recordings, reference, *, clock_worker=None, starts=None,
                 snapshot_path: str | None = None, history: float | None = None):
        super().__init__()
        self.setWindowTitle("Tone visualiser - comparison")
        self.clock_worker = clock_worker
        self.recordings = recordings
        self.snapshot_path = snapshot_path
        self._done = False
        self.setStyleSheet(f"background-color: {C.BACKGROUND};")
        layout = QGridLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.grid = CompareGrid(self)
        self.grid.show_recordings(recordings, reference, clock_worker=clock_worker,
                                  starts=starts, history=history)
        self.views = self.grid.views
        layout.addWidget(self.grid, 0, 0)
        note = QLabel(C.DISCLAIMER)
        note.setStyleSheet(f"color: {C.DIM_TEXT};")
        note.setFixedHeight(int(QFontMetricsF(note.font()).height()) + 6)
        layout.addWidget(note, 1, 0)
        layout.setRowStretch(0, 1)
        cols = 2 if len(recordings) > 1 else 1
        rows = (len(recordings) + cols - 1) // cols
        self.resize(cols * 600, rows * 320 + 30)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(max(1, round(1000 / C.FPS)))
        if clock_worker is None and snapshot_path:
            QTimer.singleShot(400, self._finish)

    def _tick(self) -> None:
        self.grid.tick()
        if self.snapshot_path and not self._done and self.grid.playing_done():
            self._finish()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        if self.snapshot_path:
            path = os.path.abspath(self.snapshot_path)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            ok = self.grab().save(path)
            print(("Saved a picture of the comparison to " if ok else "Could not save ") + path,
                  flush=True)
        self.close()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Q, Qt.Key.Key_Escape):
            self.close()
        elif key == Qt.Key.Key_Space:
            self.grid.toggle_freeze()
        elif key == Qt.Key.Key_H:
            self.grid.toggle_help()
        else:
            super().keyPressEvent(event)
