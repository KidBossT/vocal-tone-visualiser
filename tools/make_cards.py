"""Makes the title, evidence and end cards for the Stage 1 video, plus on-screen labels.

    .venv\\Scripts\\python.exe tools\\make_cards.py [--team "Team name"] [--test1 "5 of 6"]
                                                  [--test2 "11 of 12"] [--repo URL]

(or double-click make_cards.bat, then run it again with the options once you have the
results). Everything is 1920 x 1080 PNG, in the app's own colours and font, written to
video/cards. The labels have see-through backgrounds, to lay over the screen recordings in the
editor. Left out, the test results show as blanks ("__") so a missing number is obvious.

No emotion words anywhere: the labels describe the voice, never the person.
"""

from __future__ import annotations

import argparse
import math
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QLinearGradient,  # noqa: E402
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QApplication  # noqa: E402

from tonevis import config as C, theme as T  # noqa: E402

W, H = 1920, 1080
TAGLINE = "Hackcessible India 2026  ·  Vikram's challenge"
LABELS = {
    "label_acted_roleplay": "Acted role-play",
    "label_synthetic_voice": "Demo recording: a synthetic voice",
    "label_long_pause": "long pause",
    "label_higher": "higher",
    "label_quieter": "quieter",
    "label_flatter": "flatter",
    "label_louder": "louder",
    "label_faster": "faster",
    "label_faster_and_louder": "faster and louder",
    "label_more_pressed": "more pressed",
    "label_softer": "softer, breathier",
    "label_interpretation": "Shows vocal features only. Interpretation is yours.",
}


def font(size: float, weight=QFont.Weight.Normal) -> QFont:
    f = T.ui_font(10.0)
    f.setPixelSize(round(size))
    f.setWeight(weight)
    return f


def canvas(transparent: bool = False) -> tuple[QImage, QPainter]:
    image = QImage(W, H, QImage.Format.Format_ARGB32)
    image.fill(QColor(0, 0, 0, 0) if transparent else QColor(T.APP_BG))
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return image, p


def text(p: QPainter, x: float, y: float, s: str, size: float, colour: str,
         weight=QFont.Weight.Normal, centre: bool = False) -> float:
    """Draws one line with its top at y; returns the y just below it."""
    p.setFont(font(size, weight))
    p.setPen(QColor(colour))
    m = QFontMetricsF(p.font())
    if centre:
        x = (W - m.horizontalAdvance(s)) / 2
    p.drawText(QPointF(x, y + m.ascent()), s)
    return y + m.height()


def voice_line(p: QPainter, y: float, amplitude: float = 70.0) -> None:
    """A stroke like the app's pitch line: thin and white, swelling thick and amber, then
    thin and blue. Decoration only."""
    pts = []
    for i in range(0, 241):
        k = i / 240
        x = 160 + k * (W - 320)
        bend = math.sin(k * math.pi * 3.2) * 0.6 + math.sin(k * math.pi * 7.1 + 1) * 0.25
        pts.append((k, x, y - amplitude * bend))
    stops = [(0.0, C.NEUTRAL), (0.45, C.NEUTRAL), (0.62, C.WARM), (0.78, C.NEUTRAL),
             (0.92, C.COOL), (1.0, C.COOL)]
    for (k0, x0, y0), (k1, x1, y1) in zip(pts, pts[1:]):
        if 0.30 < k0 < 0.36 or 0.84 < k0 < 0.87:
            continue                                       # pauses
        width = 4 + 22 * math.exp(-((k0 - 0.62) / 0.09) ** 2)
        colour = QColor(C.NEUTRAL)
        for (a, ca), (b, cb) in zip(stops, stops[1:]):
            if a <= k0 <= b:
                t = (k0 - a) / (b - a) if b > a else 0
                c0, c1 = QColor(ca), QColor(cb)
                colour = QColor.fromRgbF(c0.redF() + (c1.redF() - c0.redF()) * t,
                                         c0.greenF() + (c1.greenF() - c0.greenF()) * t,
                                         c0.blueF() + (c1.blueF() - c0.blueF()) * t)
        pen = QPen(colour, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawLine(QPointF(x0, y0), QPointF(x1, y1))


def save(image: QImage, p: QPainter, out: str, name: str) -> None:
    p.end()
    path = os.path.join(out, name + ".png")
    image.save(path)
    print("wrote", os.path.relpath(path, ROOT))


def title_card(out: str, team: str | None) -> None:
    image, p = canvas()
    y = text(p, 0, 250, TAGLINE, 34, T.TEXT_2, centre=True)
    y = text(p, 0, y + 20, "Tone visualiser", 128, T.TEXT, QFont.Weight.DemiBold, centre=True)
    text(p, 0, y + 10, "Showing how something is said, for a deaf psychology trainee", 42,
         T.TEXT_2, centre=True)
    voice_line(p, 760, 50)
    if team:
        text(p, 0, 900, team, 40, T.TEXT, QFont.Weight.DemiBold, centre=True)
    save(image, p, out, "01_title")


def captions_cards(out: str) -> None:
    for name, transparent in (("02_captions_not_voice", False),
                              ("02_captions_not_voice_overlay", True)):
        image, p = canvas(transparent)
        if transparent:                       # a dark band so it reads over a face
            band = QLinearGradient(0, 700, 0, H)
            band.setColorAt(0, QColor(0, 0, 0, 0))
            band.setColorAt(0.35, QColor(0, 0, 0, 170))
            band.setColorAt(1, QColor(0, 0, 0, 200))
            p.fillRect(QRectF(0, 700, W, H - 700), band)
            y = 820
        else:
            y = 400
        y = text(p, 0, y, "Captions give the words.", 84, T.TEXT, QFont.Weight.DemiBold,
                 centre=True)
        text(p, 0, y + 6, "Not the voice.", 84, C.WARM, QFont.Weight.DemiBold, centre=True)
        save(image, p, out, name)


def evidence_card(out: str, test1: str | None, test2: str | None) -> None:
    image, p = canvas()
    text(p, 200, 120, "What we measured", 72, T.TEXT, QFont.Weight.DemiBold)
    rows = [
        ("about 70 ms", "from voice to screen"),
        ("4 candidates", "compared on recordings before choosing the voice-quality measure"),
        ("122 tests", "automatic, including one that fails on any emotion word"),
        ("offline", "runs on an ordinary laptop and saves no sound"),
        (test1 or "__ of __", "people matched all four takes with the sound off"),
        (test2 or "__ of __", "planned voice changes noticed from the corner of the eye"),
    ]
    y = 290
    for big, small in rows:
        text(p, 200, y, big, 52, C.WARM if "__" in big else T.TEXT, QFont.Weight.DemiBold)
        p.setFont(font(36))
        p.setPen(QColor(T.TEXT_2))
        p.drawText(QRectF(640, y + 8, W - 840, 110),
                   Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignTop, small)
        y += 118
    save(image, p, out, "03_evidence")


def end_card(out: str, team: str | None, repo: str | None) -> None:
    image, p = canvas()
    voice_line(p, 300, 45)
    y = text(p, 0, 430, "Evidence, not verdict.", 120, T.TEXT, QFont.Weight.DemiBold,
             centre=True)
    y = text(p, 0, y + 20, "Tone visualiser  ·  " + TAGLINE, 36, T.TEXT_2, centre=True)
    if team:
        y = text(p, 0, y + 30, team, 44, T.TEXT, QFont.Weight.DemiBold, centre=True)
    if repo:
        text(p, 0, 940, repo, 30, T.ACCENT, centre=True)
    save(image, p, out, "04_end")


def labels(out: str) -> None:
    """Pill-shaped labels on a see-through 1920 x 1080 frame, centred near the bottom:
    position and scale them in the editor."""
    for name, s in LABELS.items():
        image, p = canvas(transparent=True)
        p.setFont(font(54, QFont.Weight.DemiBold))
        m = QFontMetricsF(p.font())
        w, h = m.horizontalAdvance(s) + 80, m.height() + 36
        box = QRectF((W - w) / 2, H - 140 - h, w, h)
        path = QPainterPath()
        path.addRoundedRect(box, h / 2, h / 2)
        p.fillPath(path, QColor(11, 14, 19, 225))
        p.setPen(QPen(QColor(T.ACCENT), 3))
        p.drawPath(path)
        p.setPen(QColor(T.TEXT))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, s)
        save(image, p, out, name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--team", help="the team's name, for the title and end cards")
    parser.add_argument("--test1", help='sound-off test result, for example "5 of 6"')
    parser.add_argument("--test2", help='corner-of-the-eye test result, for example "11 of 12"')
    parser.add_argument("--repo", help="a link to show on the end card")
    parser.add_argument("--out", default=os.path.join(ROOT, "video", "cards"))
    args = parser.parse_args()
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    QApplication.instance() or QApplication([])
    title_card(out, args.team)
    captions_cards(out)
    evidence_card(out, args.test1, args.test2)
    end_card(out, args.team, args.repo)
    labels(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
