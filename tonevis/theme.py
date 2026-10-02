"""The look of the dashboard: colours, font, style sheet, small icons drawn in code, and the
building blocks every page uses (cards, page headers, the level meter).

The display itself (the line, the band, the pause shading) keeps its own colours in config.py.
The interface around it uses quiet greys and one accent colour that the display never uses, so
nothing in the frame around the display can be mistaken for a measurement.

Icons are drawn here rather than loaded from image files or an icon font: nothing extra to
download, the same on Windows and Mac, and sharp at any screen scaling.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPalette, QPen, QPixmap, QPolygonF)
from PySide6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from . import config as C

# ---- colours ---------------------------------------------------------------------------------
APP_BG = "#0B0E13"         # behind everything
CARD_BG = "#11161E"        # the panels
CARD_BORDER = "#1D2531"
INPUT_BG = "#0D1117"
RAISED = "#19212C"         # buttons
RAISED_HOVER = "#222C3A"
BORDER = "#2A3444"
TEXT = "#E6EAF2"
TEXT_2 = "#A9B2C1"         # secondary text
DIM = C.DIM_TEXT           # hints
ACCENT = "#7C8CFF"         # the interface's own colour: the main button, selections, marks
ACCENT_SOFT = "#252D57"

STYLE = f"""
QMainWindow, QDialog {{ background: {APP_BG}; }}
QWidget#page {{ background: {APP_BG}; }}
QFrame#card {{ background: {CARD_BG}; border: 1px solid {CARD_BORDER}; border-radius: 10px; }}
QFrame#startCard {{ background: #141A24; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel {{ color: {TEXT}; background: transparent; }}
QLabel#cardTitle {{ font-weight: 600; color: {TEXT}; }}
QLabel#cardHint, QLabel#dim {{ color: {DIM}; }}
QLabel#secondary {{ color: {TEXT_2}; }}
QLabel#pageTitle {{ font-size: 15pt; font-weight: 600; color: {TEXT}; }}
QLabel#pageText {{ color: {TEXT_2}; }}
QLabel#heading {{ font-size: 11pt; font-weight: 600; color: {TEXT}; }}
QLabel#startTitle {{ font-size: 16pt; font-weight: 600; color: {TEXT}; }}
QLabel#stepNumber {{ background: {ACCENT_SOFT}; color: {TEXT}; border-radius: 12px;
                     font-weight: 600; }}
QLabel#summaryBox {{ background: {INPUT_BG}; border: 1px solid {CARD_BORDER};
                     border-left: 3px solid {ACCENT}; border-radius: 6px; padding: 8px 10px;
                     color: {TEXT}; }}
QLabel#banner {{ background: {ACCENT_SOFT}; border: 1px solid {ACCENT}; border-radius: 8px;
                 padding: 8px 12px; color: {TEXT}; }}
QTabWidget::pane {{ border: 0; }}
QTabWidget::tab-bar {{ left: 10px; }}
QTabBar {{ background: {APP_BG}; }}
QTabBar::tab {{ background: transparent; color: {TEXT_2}; padding: 8px 16px; margin: 8px 4px 6px 0;
               border: 1px solid transparent; border-radius: 8px; }}
QTabBar::tab:hover {{ background: #151B24; color: {TEXT}; }}
QTabBar::tab:selected {{ background: {ACCENT_SOFT}; border-color: #3A4580; color: #FFFFFF; }}
QPushButton {{ background: {RAISED}; border: 1px solid {BORDER}; border-radius: 7px;
               padding: 6px 12px; color: {TEXT}; }}
QPushButton:hover {{ background: {RAISED_HOVER}; border-color: #3A475C; }}
QPushButton:pressed {{ background: #151C26; }}
QPushButton:checked {{ background: {ACCENT_SOFT}; border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #5A6474; border-color: #222A36; }}
QPushButton#primary {{ background: {ACCENT}; border-color: {ACCENT}; color: #0B0E13;
                       font-weight: 600; }}
QPushButton#primary:hover {{ background: #929EFF; border-color: #929EFF; }}
QPushButton#primary:checked {{ background: {RAISED}; border: 1px solid {ACCENT}; color: {TEXT}; }}
QPushButton#flat {{ background: transparent; border: 1px solid transparent; color: {TEXT_2};
                    padding: 4px 8px; }}
QPushButton#flat:hover {{ background: #151B24; color: {TEXT}; }}
QPushButton::menu-indicator {{ subcontrol-position: right center; right: 6px; }}
QComboBox, QLineEdit {{ background: {INPUT_BG}; border: 1px solid {BORDER};
               border-radius: 7px; padding: 5px 8px; color: {TEXT}; }}
QComboBox:hover, QLineEdit:hover {{ border-color: #3A475C; }}
QComboBox:focus, QLineEdit:focus {{ border-color: {ACCENT}; }}
QSpinBox {{ padding: 3px 4px; min-height: 22px; }}
QComboBox QAbstractItemView {{ background: {CARD_BG}; border: 1px solid {BORDER};
               selection-background-color: {ACCENT_SOFT}; color: {TEXT}; }}
QListWidget {{ background: {INPUT_BG}; border: 1px solid {CARD_BORDER}; border-radius: 8px;
               padding: 4px; color: {TEXT}; }}
QListWidget::item {{ padding: 5px 6px; border-radius: 6px; }}
QListWidget::item:hover {{ background: #151B24; }}
QListWidget::item:selected {{ background: {ACCENT_SOFT}; color: #FFFFFF; }}
QTextBrowser {{ background: {APP_BG}; border: 0; color: {TEXT}; }}
QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #2A3444; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #3A475C; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #2A3444; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QToolTip {{ background: #1C2430; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px; }}
QCheckBox {{ color: {TEXT}; spacing: 8px; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #4A5566; border-radius: 4px;
               background: {INPUT_BG}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ background: {APP_BG}; color: {TEXT_2}; border-top: 1px solid {CARD_BORDER}; }}
QStatusBar::item {{ border: 0; }}
QMenu {{ background: {CARD_BG}; border: 1px solid {BORDER}; padding: 4px; color: {TEXT}; }}
QMenu::item {{ padding: 6px 22px 6px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {ACCENT_SOFT}; }}
QMenu::separator {{ height: 1px; background: {CARD_BORDER}; margin: 4px 6px; }}
QMessageBox, QInputDialog {{ background: {CARD_BG}; }}
"""


def apply_dark_theme(app: QApplication) -> None:
    """Colours and style for the whole application (the font is set separately, by
    ui_font(), when the real app starts)."""
    app.setStyle("Fusion")
    pal = QPalette()
    roles = {QPalette.ColorRole.Window: APP_BG, QPalette.ColorRole.WindowText: TEXT,
             QPalette.ColorRole.Base: C.BACKGROUND, QPalette.ColorRole.AlternateBase: CARD_BG,
             QPalette.ColorRole.Text: TEXT, QPalette.ColorRole.Button: RAISED,
             QPalette.ColorRole.ButtonText: TEXT, QPalette.ColorRole.Highlight: ACCENT,
             QPalette.ColorRole.HighlightedText: C.BACKGROUND,
             QPalette.ColorRole.ToolTipBase: "#1C2430", QPalette.ColorRole.ToolTipText: TEXT,
             QPalette.ColorRole.PlaceholderText: DIM, QPalette.ColorRole.Link: ACCENT,
             QPalette.ColorRole.LinkVisited: ACCENT}
    for role, colour in roles.items():
        pal.setColor(role, QColor(colour))
    app.setPalette(pal)
    app.setStyleSheet(STYLE)


def ui_font(point_size: float = 10.0) -> QFont:
    """Windows 11's own interface font where it exists, then Segoe UI, then the system's.
    Picked by name from the installed fonts, because asking Qt for a missing font can land on
    something odd."""
    families = set(QFontDatabase.families())
    for name in ("Segoe UI Variable Text", "Segoe UI", ".AppleSystemUIFont", "Helvetica Neue"):
        if name in families:
            return QFont(name, point_size)
    font = QApplication.font()
    font.setPointSizeF(point_size)
    return font


# ---- icons -----------------------------------------------------------------------------------

def _pen(colour: QColor, width: float = 1.5) -> QPen:
    pen = QPen(colour, width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def _draw_icon(p: QPainter, name: str, c: QColor) -> None:
    """Draws one icon on a 16 x 16 grid."""
    p.setPen(_pen(c))
    p.setBrush(Qt.BrushStyle.NoBrush)
    fill = (lambda: (p.setPen(Qt.PenStyle.NoPen), p.setBrush(c)))
    if name == "play":
        fill()
        p.drawPolygon(QPolygonF([QPointF(5, 3.2), QPointF(13, 8), QPointF(5, 12.8)]))
    elif name == "stop":
        fill()
        p.drawRoundedRect(QRectF(4, 4, 8, 8), 1.6, 1.6)
    elif name == "record":
        fill()
        p.drawEllipse(QPointF(8, 8), 4.6, 4.6)
    elif name == "mark":
        p.drawLine(QPointF(4.5, 2.5), QPointF(4.5, 14))
        fill()
        p.drawPolygon(QPolygonF([QPointF(4.5, 2.8), QPointF(13, 5.6), QPointF(4.5, 8.6)]))
    elif name == "note":
        p.setPen(_pen(c, 2.2))
        p.drawLine(QPointF(4.2, 11.8), QPointF(11.6, 4.4))
        p.setPen(_pen(c, 1.2))
        p.drawLine(QPointF(3, 14), QPointF(13, 14))
    elif name == "freeze":
        fill()
        p.drawRoundedRect(QRectF(4.2, 3.5, 2.8, 9), 1, 1)
        p.drawRoundedRect(QRectF(9, 3.5, 2.8, 9), 1, 1)
    elif name == "corner":
        p.drawRoundedRect(QRectF(2.5, 3.5, 11, 9), 1.6, 1.6)
        fill()
        p.drawRoundedRect(QRectF(8.3, 5, 3.8, 3), 0.8, 0.8)
    elif name == "recal":
        p.drawArc(QRectF(3, 3, 10, 10), 70 * 16, 290 * 16)
        fill()
        p.drawPolygon(QPolygonF([QPointF(9.2, 1.4), QPointF(12.2, 3.6), QPointF(8.6, 5.4)]))
    elif name == "open":
        path = QPainterPath(QPointF(2.5, 12.5))
        for x, y in ((2.5, 4.2), (6.4, 4.2), (7.8, 5.8), (13.5, 5.8), (13.5, 12.5)):
            path.lineTo(x, y)
        path.closeSubpath()
        p.drawPath(path)
    elif name in ("save", "export"):
        p.drawPolyline(QPolygonF([QPointF(3, 10), QPointF(3, 13), QPointF(13, 13), QPointF(13, 10)]))
        if name == "save":
            p.drawLine(QPointF(8, 2.8), QPointF(8, 10))
            p.drawPolyline(QPolygonF([QPointF(5.2, 7.4), QPointF(8, 10.2), QPointF(10.8, 7.4)]))
        else:
            p.drawLine(QPointF(8, 3), QPointF(8, 10))
            p.drawPolyline(QPolygonF([QPointF(5.2, 5.8), QPointF(8, 3), QPointF(10.8, 5.8)]))
    elif name == "demo":
        p.drawEllipse(QPointF(8, 8), 6, 6)
        fill()
        p.drawPolygon(QPolygonF([QPointF(6.6, 5.2), QPointF(11, 8), QPointF(6.6, 10.8)]))
    elif name == "help":
        p.drawEllipse(QPointF(8, 8), 6, 6)
        path = QPainterPath(QPointF(6.1, 6.4))
        path.cubicTo(6.1, 4.3, 9.9, 4.3, 9.9, 6.4)
        path.cubicTo(9.9, 7.9, 8, 7.9, 8, 9.4)
        p.drawPath(path)
        fill()
        p.drawEllipse(QPointF(8, 11.3), 0.9, 0.9)
    elif name == "live":
        p.drawPolyline(QPolygonF([QPointF(x, y) for x, y in (
            (1.5, 8), (4, 8), (5.5, 4.2), (7.6, 11.8), (9.6, 5), (11.2, 10), (12.6, 8), (14.5, 8))]))
    elif name == "review":
        p.drawEllipse(QPointF(8, 8), 6, 6)
        p.drawLine(QPointF(8, 8), QPointF(8, 4.6))
        p.drawLine(QPointF(8, 8), QPointF(10.6, 9.6))
    elif name == "compare":
        for x, y in ((2.5, 2.5), (8.8, 2.5), (2.5, 8.8), (8.8, 8.8)):
            p.drawRoundedRect(QRectF(x, y, 4.7, 4.7), 1.2, 1.2)
    elif name == "guide":
        left = QPainterPath(QPointF(8, 4.2))
        left.lineTo(2.6, 3.2)
        left.lineTo(2.6, 12.6)
        left.lineTo(8, 13.6)
        right = QPainterPath(QPointF(8, 4.2))
        right.lineTo(13.4, 3.2)
        right.lineTo(13.4, 12.6)
        right.lineTo(8, 13.6)
        p.drawPath(left)
        p.drawPath(right)
        p.drawLine(QPointF(8, 4.2), QPointF(8, 13.6))
    elif name == "setup":
        for y, knob in ((4, 10.5), (8, 5.5), (12, 9)):
            p.drawLine(QPointF(2.5, y), QPointF(13.5, y))
        fill()
        for y, knob in ((4, 10.5), (8, 5.5), (12, 9)):
            p.drawEllipse(QPointF(knob, y), 1.9, 1.9)
    elif name == "new":
        p.drawLine(QPointF(8, 3), QPointF(8, 13))
        p.drawLine(QPointF(3, 8), QPointF(13, 8))
    elif name == "trash":
        p.drawLine(QPointF(3, 4.5), QPointF(13, 4.5))
        p.drawPolyline(QPolygonF([QPointF(6.4, 4.5), QPointF(6.4, 2.8), QPointF(9.6, 2.8),
                                  QPointF(9.6, 4.5)]))
        p.drawPolyline(QPolygonF([QPointF(4.4, 4.5), QPointF(5.2, 13.2), QPointF(10.8, 13.2),
                                  QPointF(11.6, 4.5)]))
    elif name == "back":
        p.drawLine(QPointF(12.8, 8), QPointF(3.4, 8))
        p.drawPolyline(QPolygonF([QPointF(7, 4.4), QPointF(3.4, 8), QPointF(7, 11.6)]))
    elif name == "panel":
        p.drawRoundedRect(QRectF(2.5, 3, 11, 10), 1.6, 1.6)
        p.drawLine(QPointF(9.5, 3), QPointF(9.5, 13))
        p.setPen(_pen(c, 1.1))
        for y in (5.8, 8, 10.2):
            p.drawLine(QPointF(10.9, y), QPointF(12.3, y))
    elif name == "session":
        for y in (4.5, 8, 11.5):
            p.drawLine(QPointF(5.5, y), QPointF(13.5, y))
        fill()
        for y in (4.5, 8, 11.5):
            p.drawEllipse(QPointF(3, y), 1.1, 1.1)
    elif name == "mic":
        p.drawRoundedRect(QRectF(6, 2.5, 4, 7.5), 2, 2)
        p.drawArc(QRectF(3.6, 4.8, 8.8, 7.6), 200 * 16, 140 * 16)
        p.drawLine(QPointF(8, 12.4), QPointF(8, 14))


def icon(name: str, colour: str = TEXT, size: int = 16) -> QIcon:
    scale = 3                              # drawn at 3x: sharp on high-resolution screens
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.scale(size * scale / 16.0, size * scale / 16.0)
    _draw_icon(p, name, QColor(colour))
    p.end()
    pm.setDevicePixelRatio(scale)
    return QIcon(pm)


def app_icon() -> QIcon:
    """The window icon: a voice line on a dark tile, white turning amber."""
    ic = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(size / 64.0, size / 64.0)
        p.setPen(QPen(QColor(BORDER), 1.5))
        p.setBrush(QColor(CARD_BG))
        p.drawRoundedRect(QRectF(3, 3, 58, 58), 15, 15)
        path = QPainterPath(QPointF(12, 39))
        path.cubicTo(20, 39, 22, 20, 30, 22)
        path.cubicTo(37, 24, 36, 43, 44, 40)
        path.cubicTo(48, 38.5, 49, 30, 52, 27)
        grad = QLinearGradient(12, 0, 52, 0)
        grad.setColorAt(0.0, QColor(C.NEUTRAL))
        grad.setColorAt(1.0, QColor(C.WARM))
        pen = QPen(grad, 5.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        glow = QColor(C.WARM)
        glow.setAlpha(70)
        p.setBrush(glow)
        p.drawEllipse(QPointF(52, 27), 7, 7)
        p.setBrush(QColor(C.WARM))
        p.drawEllipse(QPointF(52, 27), 4, 4)
        p.end()
        ic.addPixmap(pm)
    return ic


# ---- building blocks -------------------------------------------------------------------------

def label(text: str, name: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def button(text: str, tip: str = "", checkable: bool = False, primary: bool = False,
           icon_name: str | None = None, flat: bool = False) -> QPushButton:
    b = QPushButton(text)
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)      # so Space never "presses" a button
    if primary:
        b.setObjectName("primary")
    elif flat:
        b.setObjectName("flat")
    if icon_name:
        b.setIcon(icon(icon_name, "#0B0E13" if primary else TEXT))
    return b


class Card(QFrame):
    """A rounded panel with a title, an optional one-line explanation, and its content."""

    def __init__(self, title: str = "", hint: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(14, 11, 14, 13)
        self.body.setSpacing(7)
        self.header = QHBoxLayout()
        self.header.setSpacing(6)
        self.title = label(title, "cardTitle")
        self.header.addWidget(self.title)
        self.header.addStretch(1)
        if title:
            self.body.addLayout(self.header)
        self.hint = label(hint, "cardHint", wrap=True) if hint else None
        if self.hint is not None:
            self.body.addWidget(self.hint)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)

    def add_action(self, widget: QWidget) -> QWidget:
        self.header.addWidget(widget)
        return widget


class PageHeader(QWidget):
    """A page's title and one sentence on what the page is for, with its buttons on the right."""

    def __init__(self, title: str, text: str, icon_name: str | None = None, parent=None):
        super().__init__(parent)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(2, 0, 2, 2)
        outer.setSpacing(12)
        if icon_name:
            badge = QLabel()
            badge.setPixmap(icon(icon_name, ACCENT, 22).pixmap(22, 22))
            badge.setFixedSize(26, 26)
            outer.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(1)
        self.title = label(title, "pageTitle")
        self.text = label(text, "pageText", wrap=True)
        words.addWidget(self.title)
        words.addWidget(self.text)
        outer.addLayout(words, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(6)
        outer.addLayout(self.actions)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget)
        return widget


class LevelMeter(QWidget):
    """Microphone level: normal speech should reach the lighter zone."""

    LOW, HIGH = -70.0, -10.0
    ZONE = (-40.0, -20.0)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.level_db = float("nan")
        self.setMinimumSize(80, 14)
        self.setToolTip("Microphone level. Normal speech should reach the lighter zone.")

    def set_level(self, db: float) -> None:
        self.level_db = db
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, max(3.0, (self.height() - 10) / 2), -1,
                                         -max(3.0, (self.height() - 10) / 2))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.PACE_TRACK))
        p.drawRoundedRect(r, 3, 3)

        def x(db):
            return r.left() + (min(max(db, self.LOW), self.HIGH) - self.LOW) / (self.HIGH - self.LOW) * r.width()
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRect(QRectF(x(self.ZONE[0]), r.top(), x(self.ZONE[1]) - x(self.ZONE[0]), r.height()))
        if math.isfinite(self.level_db):
            p.setBrush(QColor(C.PACE_FILL))
            p.drawRoundedRect(QRectF(r.left(), r.top(), x(self.level_db) - r.left(), r.height()), 3, 3)
        p.end()

