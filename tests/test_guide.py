"""The key beside the live view and the How it works page: every picture is drawn by the
display's own code, and every part of the display has a row in the key."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QUrl  # noqa: E402
from PySide6.QtGui import QImage, QPainter  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tonevis import guide as G  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def brightest(image: QImage) -> int:
    step = 3
    return max(image.pixelColor(x, y).lightness()
               for x in range(0, image.width(), step) for y in range(0, image.height(), step))


@pytest.mark.parametrize("name", list(G.EXAMPLES))
def test_each_example_is_drawn_by_the_display(app, name):
    image = G.render_example(name, 300, 100)
    assert image.width() >= 300 and brightest(image) > 150


def test_the_examples_show_what_they_say(app):
    tl, _ = G.example_timeline(G.EXAMPLES["pauses"]["segments"])
    assert any(e - s >= 2.0 for s, e in tl.pauses)                 # a long, shaded pause
    tl, _ = G.example_timeline(G.EXAMPLES["faster"]["segments"])
    fast = len(tl.nuclei)
    tl, _ = G.example_timeline(G.EXAMPLES["slower"]["segments"])
    assert fast > 2 * len(tl.nuclei)                               # more ticks when faster


def test_the_pipeline_picture(app):
    image = G.pipeline_image(900, 150)
    assert image.width() == 1800 and brightest(image) > 150


def test_the_key_has_a_glyph_for_every_part(app):
    panel = G.KeyPanel()
    assert len(panel.findChildren(G.KeyGlyph)) == len(G.KEY_ROWS) == 9
    image = QImage(60, 30, QImage.Format.Format_ARGB32)
    for kind, _ in G.KEY_ROWS + (("mark", ""),):
        p = QPainter(image)
        G.draw_glyph(p, kind, image.rect().toRectF())
        p.end()


def test_the_page_loads_its_pictures(app):
    page = G.GuideBrowser()
    assert isinstance(page.loadResource(2, QUrl("example:pitch")), QImage)
    assert "How it works" in page.toPlainText()
    assert "Reading a change" in page.toPlainText()
