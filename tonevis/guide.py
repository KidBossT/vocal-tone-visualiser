"""Explaining the display: the key beside the live view, and the "How it works" page.

The example pictures on the How it works page are drawn by the display's own code from
made-up measurements, so they always match what the app really shows. (Screenshots would drift
out of date the moment a colour or a thickness changed.)
"""

from __future__ import annotations

import math
import os

from PySide6.QtCore import QPointF, QRectF, Qt, QUrl
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QApplication, QGridLayout, QTextBrowser, QWidget

from . import config as C
from . import theme as T
from .display import ToneView
from .prosody import ProsodyFrame, Reference
from .session import Timeline

NAN = float("nan")
DOCS_IMG = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, "docs", "img"))

# ---- the key beside the live view ------------------------------------------------------------

KEY_ROWS = (
    ("pitch", "Higher line = higher voice"),
    ("band", "Faint band = their usual range"),
    ("loud", "Thicker, brighter = louder"),
    ("quality", "Amber = more pressed, blue = softer"),
    ("grey", "Grey = still learning this voice"),
    ("pause", "Gap = pause, shaded = 1 s or more"),
    ("ticks", "Ticks = syllables (close = fast)"),
    ("pace", "Bar = pace: up = faster than usual"),
    ("now", "Dot = their voice right now"),
)


class KeyGlyph(QWidget):
    """A tiny drawing of one part of the display, in the display's own colours."""

    W, H = 48, 24

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(self.W, self.H)

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        draw_glyph(p, self.kind, QRectF(0, 0, self.W, self.H))
        p.end()


def _line_pen(colour, width: float) -> QPen:
    pen = QPen(QColor(colour), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _mix(a: str, b: str, k: float) -> QColor:
    ca, cb = QColor(a), QColor(b)
    return QColor(int(ca.red() + (cb.red() - ca.red()) * k),
                  int(ca.green() + (cb.green() - ca.green()) * k),
                  int(ca.blue() + (cb.blue() - ca.blue()) * k))


def draw_glyph(p: QPainter, kind: str, r: QRectF) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(C.BACKGROUND))
    p.drawRoundedRect(r, 5, 5)
    x0, x1, cy = r.left() + 6, r.right() - 6, r.center().y()
    centre = _line_pen(C.CENTRE_LINE, 1.0)
    if kind in ("pitch", "band"):
        if kind == "band":
            p.fillRect(QRectF(r.left() + 2, cy - 6, r.width() - 4, 12), QColor(255, 255, 255, 20))
        p.setPen(centre)
        p.drawLine(QPointF(r.left() + 2, cy), QPointF(r.right() - 2, cy))
        p.setPen(_line_pen(C.NEUTRAL, 3.0))
        if kind == "pitch":
            pts = [QPointF(x0 + (x1 - x0) * u, cy + 1 - 13 * u ** 1.6) for u in
                   (0, 0.2, 0.4, 0.6, 0.8, 1.0)]
        else:
            pts = [QPointF(x0 + (x1 - x0) * u, cy - 3.5 * math.sin(u * 2 * math.pi * 1.5))
                   for u in [k / 12 for k in range(13)]]
        p.drawPolyline(QPolygonF(pts))
    elif kind == "loud":
        n = 6
        for k in range(n):
            u = k / (n - 1)
            width = C.RIBBON_WIDTH[0] + u * (C.RIBBON_WIDTH[1] - C.RIBBON_WIDTH[0]) * 0.75
            bright = C.RIBBON_BRIGHTNESS[0] + u * (C.RIBBON_BRIGHTNESS[1] - C.RIBBON_BRIGHTNESS[0])
            p.setPen(_line_pen(_mix(C.BACKGROUND, C.NEUTRAL, bright), width))
            xa = x0 + (x1 - x0) * k / n
            xb = x0 + (x1 - x0) * (k + 1) / n
            p.drawLine(QPointF(xa, cy), QPointF(xb, cy))
    elif kind == "quality":
        span = (x1 - x0) / 3
        for k, colour in enumerate((C.COOL, C.NEUTRAL, C.WARM)):
            p.setPen(_line_pen(colour, 5.0))
            p.drawLine(QPointF(x0 + k * span + 2, cy), QPointF(x0 + (k + 1) * span - 3, cy))
    elif kind == "grey":
        p.setPen(_line_pen(C.CALIBRATING_LINE, 3.0))
        p.drawLine(QPointF(x0 + 12, cy + 3), QPointF(x1, cy - 2))
        p.setPen(_line_pen(C.PACE_TRACK, 2.0))
        ring = QRectF(r.left() + 4, r.top() + 4, 9, 9)
        p.drawEllipse(ring)
        p.setPen(_line_pen(C.CALIBRATING_LINE, 2.0))
        p.drawArc(ring, 90 * 16, -200 * 16)
    elif kind == "pause":
        shade = _mix(C.BACKGROUND, "#FFFFFF", 28 / 255)
        p.fillRect(QRectF(r.left() + 21, r.top() + 1, 15, r.height() - 2), shade)
        p.setPen(_line_pen(C.NEUTRAL, 3.0))
        p.drawLine(QPointF(x0, cy), QPointF(r.left() + 17, cy - 2))
        p.drawLine(QPointF(r.left() + 40, cy + 1), QPointF(x1, cy - 1))
    elif kind == "ticks":
        p.setPen(_line_pen(C.RHYTHM_TICK, 2.0))
        for x in (8, 14, 20, 26, 38, 49):
            p.drawLine(QPointF(r.left() + x, r.bottom() - 10), QPointF(r.left() + x, r.bottom() - 4))
    elif kind == "pace":
        track = QRectF(r.center().x() - 4, r.top() + 2, 8, r.height() - 4)
        p.setBrush(QColor(C.PACE_TRACK))
        p.drawRoundedRect(track, 2, 2)
        p.setBrush(QColor(C.PACE_FILL))
        p.drawRoundedRect(QRectF(track.left() + 1.5, track.top() + 2, track.width() - 3,
                                 track.height() / 2 - 2), 1.5, 1.5)
        p.setPen(_line_pen(C.PACE_NOTCH, 2.0))
        p.drawLine(QPointF(track.left() - 3, cy), QPointF(track.right() + 3, cy))
    elif kind == "now":
        p.setPen(_line_pen(C.NEUTRAL, 3.0))
        p.drawLine(QPointF(x0, cy + 3), QPointF(x1 - 8, cy - 2))
        p.setPen(Qt.PenStyle.NoPen)
        glow = QColor(C.NEUTRAL)
        glow.setAlpha(60)
        p.setBrush(glow)
        p.drawEllipse(QPointF(x1 - 8, cy - 2), 7, 7)
        p.setBrush(QColor(C.NEUTRAL))
        p.drawEllipse(QPointF(x1 - 8, cy - 2), 3.5, 3.5)
    elif kind == "mark":
        pen = QPen(QColor(T.ACCENT), 1.2, Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.drawLine(QPointF(r.center().x(), r.top() + 3), QPointF(r.center().x(), r.bottom() - 2))


class KeyPanel(QWidget):
    """Every part of the display, with a one-line meaning."""

    def __init__(self, parent=None):
        super().__init__(parent)
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)
        for row, (kind, text) in enumerate(KEY_ROWS):
            grid.addWidget(KeyGlyph(kind), row, 0, Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(T.label(text, "secondary"), row, 1)   # one line each: see below
        grid.setColumnStretch(1, 1)
        # (No wrapped lines: a wrapped label in this column makes Qt share the height out
        # evenly and squash the key; every line here fits the side panel's minimum width.)


# ---- example pictures, drawn by the display itself -------------------------------------------

EXAMPLE_REF = Reference(True, 1.0, 150.0, -30.0, -12.0, 4.0, (-3.0, 3.0))
LEARNING_REF = Reference(False, 0.45, 150.0, -30.0, None, None, None)


def _wobble(centre: float, depth: float = 1.6, cycles: float = 2.0):
    return lambda u: centre + depth * math.sin(u * 2 * math.pi * cycles)


def example_timeline(segments, ref: Reference = EXAMPLE_REF) -> tuple[Timeline, float]:
    """Made-up measurements. Each segment is a dict: s (seconds), and for voice: st (semitones
    from the usual middle, a number or a function of 0..1), loud (dB from usual), tilt (dB from
    usual), pace (times usual), syl (syllables per second); or voice=False for silence."""
    tl = Timeline()
    t = 0.0
    for seg in segments:
        seconds = seg["s"]
        n = int(round(seconds / C.FRAME_STEP))
        start = t
        if seg.get("voice", True):
            shape = seg.get("st", 0.0)
            tilt = ref.tilt_db + seg.get("tilt", 0.0) if ref.tilt_db is not None else NAN
            rate = ref.rate * seg.get("pace", 1.0) if ref.rate else NAN
            for k in range(n):
                u = k / max(n - 1, 1)
                st = shape(u) if callable(shape) else shape
                tl.add_frame(ProsodyFrame(start + k * C.FRAME_STEP,
                                          ref.pitch_hz * 2.0 ** (st / 12.0),
                                          ref.level_db + seg.get("loud", 0.0), True, NAN,
                                          tilt, rate))
            syl = seg.get("syl", 0.0)
            for j in range(int(seconds * syl)):
                tl.add_event(("nucleus", start + (j + 0.5) / syl))
        else:
            for k in range(n):
                ft = start + k * C.FRAME_STEP
                since = start if ft - start >= C.PAUSE_MIN - 1e-9 else NAN
                tl.add_frame(ProsodyFrame(ft, NAN, -70.0, False, since, NAN, NAN))
            if seconds >= C.PAUSE_MIN:
                tl.add_event(("pause", start, start + seconds))
        t += seconds
    return tl, t


def _silence(s: float) -> dict:
    return {"s": s, "voice": False}


EXAMPLES = {
    "pitch": dict(segments=[{"s": 1.1, "st": _wobble(0.0, 1.2), "syl": 4},
                            _silence(0.45),
                            {"s": 1.3, "st": lambda u: 0.5 + 7.0 * math.sin(u * math.pi * 0.62),
                             "syl": 4}]),
    "band": dict(segments=[{"s": 1.2, "st": _wobble(0.0, 2.0), "syl": 4},
                           _silence(0.45),
                           {"s": 1.2, "st": _wobble(5.6, 1.2), "syl": 4}]),
    "loudness": dict(segments=[{"s": 1.2, "st": _wobble(0.5, 1.5), "loud": -12.0, "syl": 4},
                               _silence(0.45),
                               {"s": 1.2, "st": _wobble(0.5, 1.5), "loud": 10.0, "syl": 4}]),
    "quality": dict(segments=[{"s": 0.85, "st": _wobble(0.0, 1.4, 1.5), "tilt": -5.0, "syl": 4},
                              _silence(0.3),
                              {"s": 0.85, "st": _wobble(0.0, 1.4, 1.5), "syl": 4},
                              _silence(0.3),
                              {"s": 0.85, "st": _wobble(0.0, 1.4, 1.5), "tilt": 5.0, "syl": 4}]),
    "pauses": dict(segments=[{"s": 0.7, "st": _wobble(0.5, 1.5, 1.2), "syl": 4},
                             _silence(0.12),
                             {"s": 0.55, "st": _wobble(-0.5, 1.2, 1.0), "syl": 4},
                             _silence(0.6),
                             {"s": 0.55, "st": _wobble(0.8, 1.2, 1.0), "syl": 4},
                             _silence(2.3),
                             {"s": 0.6, "st": _wobble(0.0, 1.2, 1.0), "syl": 4}]),
    "faster": dict(segments=[{"s": 2.8, "st": _wobble(0.8, 2.2, 3.5), "syl": 7.0, "pace": 1.45}]),
    "slower": dict(segments=[{"s": 2.8, "st": _wobble(-0.5, 1.4, 1.2), "syl": 2.6, "pace": 0.68}]),
    "learning": dict(segments=[{"s": 1.2, "st": _wobble(0.0, 1.8), "syl": 4}, _silence(0.4),
                               {"s": 1.3, "st": _wobble(1.0, 2.0), "syl": 4}],
                     ref=LEARNING_REF),
    "now": dict(segments=[{"s": 1.0, "st": _wobble(0.0, 1.5), "syl": 4}, _silence(0.5),
                          {"s": 1.5, "st": lambda u: 1.5 * math.sin(u * 5) + 2.5 * u, "syl": 4}],
                live=True),
}


def render_example(kind: str, width: int = 300, height: int = 100) -> QImage:
    """One example, drawn by the real display code."""
    spec = EXAMPLES[kind]
    ref = spec.get("ref", EXAMPLE_REF)
    tl, duration = example_timeline(spec["segments"], ref)
    live = spec.get("live", False)
    view = ToneView(tl, lambda: ref, history=duration + (0.4 if live else 0.05),
                    show_disclaimer=False, anchor_left=not live)
    view.setMinimumSize(1, 1)
    view.resize(width, height)
    view.source_finished = True
    view.now_fn = lambda: duration - C.FRAME_STEP
    image = view.grab().toImage()
    view.deleteLater()
    return image


def pipeline_image(width: int = 900, height: int = 150) -> QImage:
    """Microphone -> measures -> compares -> draws."""
    scale = 2.0
    image = QImage(int(width * scale), int(height * scale), QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(QColor(T.APP_BG))
    image.setDotsPerMeterX(3780)          # 96 dots per inch, as on screen (the default is 72,
    image.setDotsPerMeterY(3780)          # which would draw the text a quarter too small)
    image.setDevicePixelRatio(scale)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    steps = (("mic", "Hears", "the person talking, through the microphone"),
             ("live", "Measures", "pitch, loudness, pauses, pace and voice quality, 100 times a second"),
             ("review", "Compares", "each measure with this person's own usual voice, learned in about 20 seconds"),
             ("compare", "Draws", "the line you see, well under a tenth of a second after the sound"))
    gap, n = 34.0, len(steps)
    box_w = (width - gap * (n - 1) - 4) / n
    base = QApplication.font()
    title_font = QFont(base)
    title_font.setBold(True)
    title_font.setPointSizeF(base.pointSizeF() * 1.1 if base.pointSizeF() > 0 else 11)
    for k, (icon_name, title, text) in enumerate(steps):
        x = 2 + k * (box_w + gap)
        box = QRectF(x, 8, box_w, height - 16)
        p.setPen(QPen(QColor(T.CARD_BORDER), 1.0))
        p.setBrush(QColor(T.CARD_BG))
        p.drawRoundedRect(box, 10, 10)
        T.icon(icon_name, T.ACCENT, 20).paint(p, int(box.left() + 14), int(box.top() + 14), 20, 20)
        p.setPen(QColor(T.TEXT))
        p.setFont(title_font)
        p.drawText(QRectF(box.left() + 42, box.top() + 10, box.width() - 52, 28),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, title)
        p.setFont(base)
        p.setPen(QColor(T.TEXT_2))
        p.drawText(QRectF(box.left() + 14, box.top() + 44, box.width() - 26, box.height() - 50),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                   text)
        if k < n - 1:
            cx, cy = box.right() + gap / 2, box.center().y()
            p.setPen(_line_pen(T.ACCENT, 2.0))
            p.drawLine(QPointF(cx - 9, cy), QPointF(cx + 8, cy))
            p.drawPolyline(QPolygonF([QPointF(cx + 3, cy - 5), QPointF(cx + 8, cy),
                                      QPointF(cx + 3, cy + 5)]))
    p.end()
    return image


# ---- the How it works page -------------------------------------------------------------------

GUIDE_CSS = f"""
h1 {{ font-size: 21pt; font-weight: 600; color: {T.TEXT}; }}
h2 {{ font-size: 14pt; font-weight: 600; color: {T.TEXT}; }}
h3 {{ font-size: 11pt; font-weight: 600; color: {T.TEXT}; }}
p, li, td {{ color: #C9D1DD; }}
p.lead {{ font-size: 11.5pt; color: {T.TEXT}; }}
p.dim, span.dim {{ color: {T.DIM}; }}
a {{ color: {T.ACCENT}; text-decoration: none; }}
td.key {{ color: {T.TEXT}; font-weight: 600; }}
"""

def _example_row(names: tuple[str, ...], text: str) -> str:
    pictures = "&nbsp;&nbsp;".join(f'<img src="example:{n}" width="{300 if len(names) == 1 else 146}">'
                                   for n in names)
    return f'<tr><td valign="middle" width="312">{pictures}</td><td valign="middle">{text}</td></tr>'


GUIDE_HTML = f"""
<a name="top"></a>
<table width="900" align="center" cellpadding="0" cellspacing="0"><tr><td>
<h1>How it works</h1>
<p class="lead">The tone visualiser shows <b>how</b> someone is speaking: how high or low their
voice is, how loud, where they pause, how fast they talk, and whether their voice sounds more
pressed or softer than usual. Everything is measured against <b>that person's own usual
voice</b>.</p>
<p class="lead">It never says what anyone feels. It shows evidence about the voice; what that
evidence means is yours to judge, together with their words, face, posture and the situation.</p>
<p><a href="#reading">Reading the display</a> &nbsp;·&nbsp; <a href="#session">A session, start to
finish</a> &nbsp;·&nbsp; <a href="#tabs">The five tabs</a> &nbsp;·&nbsp; <a href="#change">Reading a
change</a> &nbsp;·&nbsp; <a href="#keys">Keys</a> &nbsp;·&nbsp; <a href="#privacy">Privacy</a>
&nbsp;·&nbsp; <a href="#limits">What it cannot do</a> &nbsp;·&nbsp; <a href="#words">Words used
here</a></p>
<p><img src="example:pipeline" width="900"></p>

<a name="reading"></a><h2>Reading the display</h2>
<p>New sound appears at the right-hand edge and slides left, so the latest seconds are always on
the right. Every rule works the same way: <b>more is up, thicker, brighter or further from
white</b>. That makes it possible to learn by sight alone, without any memory of how voices
sound. The pictures below are drawn by the app itself.</p>
<table cellspacing="0" cellpadding="8">
{_example_row(("pitch",), "<b>Height is pitch.</b> The higher the line, the higher the voice. The dim line across the middle is this speaker's usual middle pitch. Here the voice starts near its usual middle, then rises well above it.")}
{_example_row(("band",), "<b>The faint band is their usual range.</b> Eight out of ten moments of this person's ordinary speech fall inside it. The second phrase here goes above the band: unusually high for them.")}
{_example_row(("loudness",), "<b>Thickness and brightness are loudness.</b> A thin, dim line is quieter than their usual; a thick, bright line is louder. Loudness is shown twice on purpose: the corner of the eye picks up brightness better than detail.")}
{_example_row(("quality",), "<b>Colour is voice quality.</b> White is their usual. <b>Amber</b> means more energy in the higher frequencies than usual, which happens when the vocal folds press together harder (a pressed, effortful voice). <b>Blue</b> means less, as in a softer or breathier voice. There is no red, and blue and amber stay distinct for the common kinds of colour blindness.")}
{_example_row(("pauses",), "<b>Gaps are pauses.</b> A thin, dim join bridges tiny gaps inside words (sounds such as s, t and k have no pitch). A real gap is a pause of a quarter of a second or more. Pauses of 1 second or longer are shaded, darker at 2 and at 3 seconds. While a pause is happening, its shading grows at the right-hand edge.")}
{_example_row(("faster", "slower"), "<b>Ticks and the bar show pace.</b> Each tick along the bottom is one syllable, so close ticks mean fast talking. The bar on the right compares their pace with their usual (the notch): it grows <b>up</b> when they are faster than usual (left picture) and <b>down</b> when slower (right). Pauses are left out of the pace, so a long silence does not pull the bar down; the bar fades instead.")}
{_example_row(("learning",), "<b>Grey means still learning.</b> For about the first 20 seconds of someone talking, the app learns their usual voice. Until then the line is grey, the ring fills up, and there is no colour and no pace bar, because there is nothing yet to compare with.")}
{_example_row(("now",), "<b>The dot is now.</b> A glowing dot marks their voice at this moment, at the right-hand edge.")}
</table>
<p>Faint dashes along the very top or bottom edge mean the measured pitch went past the edge of
the scale. Usually that is a measuring slip (see <a href="#limits">What it cannot do</a>), now and
then a real extreme.</p>

<a name="session"></a><h2>A session, start to finish</h2>
<p><b>Before.</b> In <b>Setup</b>, choose the microphone and check that the level bar reaches the
lighter zone when someone talks. If you saved a baseline for this person last time, load it and
the app starts already knowing their voice.</p>
<p><b>During.</b> On the <b>Live</b> tab press <b>Start listening</b>. In a role-play, press
<b>Recalibrate</b> as soon as the client starts talking, so that the app learns their voice
rather than yours. Open the <b>Corner view</b> for the small window that stays on top of other
windows. Press <b>M</b> to mark a moment you want to come back to, or <b>N</b> to mark it and
type a short note. <b>Space</b> freezes the picture.</p>
<p><b>After.</b> In <b>Review</b>, the session map and the <b>What changed</b> list show where the
voice stayed clearly away from the usual for a few seconds. Drag across the map to look at any
stretch, compare two stretches, add notes to your marks, then save the session (numbers only,
never sound) or export a summary for supervision notes.</p>

<a name="tabs"></a><h2>The five tabs</h2>
<table cellspacing="0" cellpadding="6">
<tr><td class="key" width="130">Live</td><td>Watch a voice as it happens: the big display, the key, each
signal on its own row for the last minute, and the whole session in one strip.</td></tr>
<tr><td class="key">Review</td><td>Look back over a session: what changed, when, and your notes.
You can also analyse a recording here.</td></tr>
<tr><td class="key">Compare</td><td>The same words spoken different ways, side by side, all
measured against one baseline. This is also where you record your own takes.</td></tr>
<tr><td class="key">How it works</td><td>This page.</td></tr>
<tr><td class="key">Setup</td><td>Microphone, calibration and baselines, display options,
privacy.</td></tr>
</table>

<a name="change"></a><h2>Reading a change: a checklist</h2>
<ol>
<li><b>Is it different from <i>their</i> usual?</b> Only changes from this person's own baseline
matter. A naturally quiet or fast speaker is not a finding.</li>
<li><b>When did it start?</b> What was being talked about just before? Mark it (M) so you can come
back to it.</li>
<li><b>Does it fit what you can see?</b> Face, posture, the words. When the voice and the words
point different ways, that mismatch is worth noticing.</li>
<li><b>Is there another explanation?</b> The microphone moved, someone else spoke, a cough, a
noisy room, a voice coming out of a speaker (see below).</li>
<li><b>Would it help to check with them?</b> For example: <i>"I noticed you paused there. What was
going on for you just then?"</i></li>
</ol>

<a name="keys"></a><h2>Keys</h2>
<table cellspacing="0" cellpadding="5">
<tr><td class="key" width="130">Space</td><td>Freeze the live picture, and again to go live</td></tr>
<tr><td class="key">M</td><td>Mark this moment</td></tr>
<tr><td class="key">N</td><td>Mark this moment and type a note (Enter saves it)</td></tr>
<tr><td class="key">H</td><td>Show or hide the key and marks beside the live view</td></tr>
<tr><td class="key">F11</td><td>Full screen</td></tr>
<tr><td class="key">F1</td><td>This page</td></tr>
<tr><td class="key">Ctrl+1 to Ctrl+5</td><td>Go to a tab</td></tr>
<tr><td class="key">Ctrl+S, Ctrl+O</td><td>Save the session, open a session</td></tr>
</table>
<p>In the corner view: Space freeze, M mark, R recalibrate, T keep on top (or not), H key, Esc
hide.</p>

<a name="privacy"></a><h2>Privacy</h2>
<p>Everything runs on this computer. The app has no internet features and sends nothing anywhere.
Sound is never saved unless you choose to: the box in Setup, or recording takes on purpose in
Compare. The measurements stay in memory until you save a session, and a saved session holds
numbers only, never sound. Your display choices are remembered in a small file, settings.ini, in
the app's folder.</p>

<a name="limits"></a><h2>What it cannot do</h2>
<ul>
<li>It cannot tell <i>why</i> a voice changed. The voice mostly carries how activated or effortful
someone is; what that means comes from the context.</li>
<li>Two people talking at once: loudness and pace mix both voices.</li>
<li>A voice coming out of a small speaker (a video call on laptop speakers) looks amber when it
is not: calibrate through the same sound path you will use.</li>
<li>Whispering has no pitch. Creaky voice at the ends of sentences drops out. Very fast speech is
counted as a little slower than it is.</li>
<li>It hears everyone in the room, including you.</li>
</ul>
<p><img src="comparison.png" width="620"></p>
<p class="dim">The same sentence spoken four ways (synthetic voices): even; slow with long pauses;
fast and loud; flat and quiet.</p>
<p><img src="failures.png" width="620"></p>
<p class="dim">A clean recording next to three known failures: two voices at once, a voice through
a tiny speaker, and a whisper.</p>

<a name="words"></a><h2>Words used here</h2>
<table cellspacing="0" cellpadding="5">
<tr><td class="key" width="130">Pitch</td><td>How fast the vocal folds vibrate. Faster vibration
sounds higher.</td></tr>
<tr><td class="key">Semitone</td><td>One step on a piano. Measuring in semitones means a deep voice
and a high voice move the same distance for the same tune.</td></tr>
<tr><td class="key">Loudness</td><td>How strong the sound is, compared with their usual.</td></tr>
<tr><td class="key">Pause</td><td>A silence of a quarter of a second or more.</td></tr>
<tr><td class="key">Syllable</td><td>One beat of speech, found as a peak in loudness while the
voice is sounding.</td></tr>
<tr><td class="key">Pace</td><td>Syllables per second while actually talking, with pauses left
out.</td></tr>
<tr><td class="key">Voice quality</td><td>How the voice's energy is shared between low and high
frequencies (the "spectral tilt").</td></tr>
<tr><td class="key">Baseline</td><td>This person's usual pitch, range, loudness, pace and voice
quality.</td></tr>
<tr><td class="key">Calibration</td><td>The first 15 seconds or so of speech, while the app learns
the baseline. The baseline then stays fixed until you recalibrate, so slow changes across a
session stay visible.</td></tr>
</table>
<p class="dim"><a href="#top">Back to the top</a></p>
</td></tr></table>
"""


class GuideBrowser(QTextBrowser):
    """The How it works page. Pictures named example:... are drawn on first use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._images: dict[str, QImage] = {}
        self.setOpenExternalLinks(False)
        self.setSearchPaths([DOCS_IMG])
        self.document().setDefaultStyleSheet(GUIDE_CSS)
        self.document().setDocumentMargin(18)
        self.setHtml(GUIDE_HTML)

    def image(self, name: str) -> QImage:
        if name not in self._images:
            if name == "pipeline":
                self._images[name] = pipeline_image()
            else:
                self._images[name] = render_example(name, 300 if name not in ("faster", "slower")
                                                     else 146, 100)
        return self._images[name]

    def loadResource(self, kind, url: QUrl):
        if url.scheme() == "example":
            return self.image(url.path())
        return super().loadResource(kind, url)
