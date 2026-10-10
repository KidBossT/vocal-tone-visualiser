"""Draws synthetic data into an off-screen view and checks the pixels: every visual mapping in
the README (up = higher, thicker = louder, amber = pressed, shaded = long pause...) is tested."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # no window pops up during tests

import math

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QColor  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tonevis import config as C  # noqa: E402
from tonevis.display import CompareWindow, Timeline, ToneView, tension_value  # noqa: E402
from tonevis.prosody import ProsodyFrame, Recording, Reference  # noqa: E402

NAN = float("nan")
REF_HZ, REF_DB, REF_TILT, REF_RATE = 150.0, -30.0, -12.0, 5.0
CALIBRATED = Reference(True, 1.0, REF_HZ, REF_DB, REF_TILT, REF_RATE, (-3.0, 3.0))
CALIBRATING = Reference(False, 0.4, REF_HZ, REF_DB, None, None, None)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def frames(n=400, f0=REF_HZ, loud=REF_DB, tilt=REF_TILT, rate=REF_RATE, pause_since=NAN):
    """n frames 10 ms apart. Each argument is a constant or a function of the frame index."""
    def get(v, i):
        return v(i) if callable(v) else v
    return [ProsodyFrame(i * 0.01, get(f0, i), get(loud, i), True, get(pause_since, i),
                         get(tilt, i), get(rate, i)) for i in range(n)]


def render(frame_list, now=4.0, ref=CALIBRATED, size=C.WINDOW_SIZE, events=(), **view_args):
    tl = Timeline()
    for pf in frame_list:
        tl.add_frame(pf)
    for ev in events:
        tl.add_event(ev)
    finished = view_args.pop("source_finished", False)
    view = ToneView(tl, lambda: ref, **view_args)
    view.source_finished = finished
    view.resize(*size)
    view.now_fn = lambda: now
    return view, view.grab().toImage()


def x_of(view, t, now=4.0):
    return int(round(float(view.x_for(t, now, view.layout_rects().plot))))


def column(image, x, top, bottom):
    return [image.pixelColor(int(x), y) for y in range(int(top), int(bottom))]


def plot_column(view, image, t, now=4.0):
    plot = view.layout_rects().plot
    return column(image, x_of(view, t, now), plot.top(), plot.bottom())


def brightest_row(view, image, t, now=4.0):
    plot = view.layout_rects().plot
    col = plot_column(view, image, t, now)
    return int(plot.top()) + max(range(len(col)), key=lambda k: col[k].lightness())


def line_thickness(view, image, t, threshold=90):
    return sum(c.lightness() > threshold for c in plot_column(view, image, t))


def drawn_max(view, image, t, now=4.0):
    """Brightest pixel in the plot column at time t, ignoring the dim centre line itself."""
    plot = view.layout_rects().plot
    centre = int(round(plot.center().y()))
    x = x_of(view, t, now)
    return max(image.pixelColor(x, y).lightness() for y in range(int(plot.top()), int(plot.bottom()))
               if abs(y - centre) > 2)


ABOVE = REF_HZ * 2 ** (4 / 12)    # a pitch clear of the centre line


# ---- pitch -----------------------------------------------------------------------------------

@pytest.mark.parametrize("size", [C.WINDOW_SIZE, (800, 450)])
def test_higher_pitch_is_drawn_higher(app, size):
    view, image = render(frames(f0=lambda i: REF_HZ * 2 ** ((5 if i < 200 else -5) / 12)),
                         size=size)
    centre = view.layout_rects().plot.center().y()
    assert brightest_row(view, image, 1.0) < centre - 10     # screen rows count downwards
    assert brightest_row(view, image, 3.0) > centre + 10


def test_a_deep_and_a_high_voice_draw_the_same_shape(app):
    """Speaker-relative: the same melody an octave apart, each against its own baseline."""
    def melody(base):
        return frames(f0=lambda i: base * 2 ** (3 * math.sin(i / 30) / 12))
    deep_view, deep = render(melody(100.0), ref=Reference(True, 1, 100.0, REF_DB, REF_TILT,
                                                          REF_RATE, (-3, 3)))
    high_view, high = render(melody(200.0), ref=Reference(True, 1, 200.0, REF_DB, REF_TILT,
                                                          REF_RATE, (-3, 3)))
    for t in (0.5, 1.5, 2.5, 3.5):
        assert abs(brightest_row(deep_view, deep, t) - brightest_row(high_view, high, t)) <= 1


def test_off_scale_pitch_is_a_faint_edge_mark_not_a_bright_stroke(app):
    view, image = render(frames(f0=lambda i: REF_HZ * 2 ** (15 / 12) if 150 <= i < 250
                                else REF_HZ))
    col = plot_column(view, image, 2.0)
    assert max(c.lightness() for c in col) < 140             # no bright stroke in that column
    assert max(c.lightness() for c in col[:4]) > 40          # but a faint mark at the top edge
    assert max(c.lightness() for c in plot_column(view, image, 3.5)) > 180


def test_blips_shorter_than_50ms_are_not_drawn(app):
    view, image = render(frames(f0=lambda i: ABOVE if (200 <= i < 203 or i >= 300) else NAN))
    for t in (1.95, 2.0, 2.05):
        assert drawn_max(view, image, t) < 40
    assert drawn_max(view, image, 3.5) > 180


def test_the_usual_range_band_shows_once_calibrated(app):
    view, image = render([], now=4.0)
    plot = view.layout_rects().plot
    x = int(plot.center().x())
    inside = image.pixelColor(x, int(view.y_for(1.5, plot))).lightness()     # band is -3..+3 st
    outside = image.pixelColor(x, int(view.y_for(6.0, plot))).lightness()
    assert inside > outside + 3
    view, image = render([], now=4.0, ref=CALIBRATING)
    assert abs(image.pixelColor(x, int(view.y_for(1.5, plot))).lightness()
               - image.pixelColor(x, int(view.y_for(6.0, plot))).lightness()) <= 1


def test_a_dot_marks_voice_happening_now(app):
    quiet = REF_DB - 15                                     # thinnest line, so the dot stands out
    view, image = render(frames(loud=quiet), now=4.0)
    assert line_thickness(view, image, 3.97) >= 7           # the dot (9 px across), not cut off
    assert line_thickness(view, image, 3.0) <= 5            # the line itself is thin
    view, image = render(frames(loud=quiet, f0=lambda i: REF_HZ if i <= 300 else NAN), now=4.0)
    assert line_thickness(view, image, 3.0) <= 5            # voice stopped 1 s ago: no dot


# ---- loudness --------------------------------------------------------------------------------

def test_louder_is_thicker_and_brighter(app):
    view, image = render(frames(loud=lambda i: REF_DB - 10 if i < 200 else REF_DB + 10))
    assert line_thickness(view, image, 3.0) >= line_thickness(view, image, 1.0) + 4
    quiet = max(c.lightness() for c in plot_column(view, image, 1.0))
    loud = max(c.lightness() for c in plot_column(view, image, 3.0))
    assert loud > quiet + 30


# ---- pauses and gaps -------------------------------------------------------------------------

def test_a_short_gap_is_joined_but_a_pause_is_not(app):
    # voiced except a 120 ms gap at 1.5 s (a consonant) and a 600 ms gap at 2.5 s (a pause)
    view, image = render(frames(f0=lambda i: NAN if (150 <= i < 162 or 250 <= i < 310)
                                else ABOVE))
    assert drawn_max(view, image, 1.56) > 60    # thin join
    assert drawn_max(view, image, 2.8) < 40     # a real gap


def _background_lightness(view, image, t):
    plot = view.layout_rects().plot
    return image.pixelColor(x_of(view, t), int(plot.top()) + 3).lightness()


def test_long_pauses_are_shaded_and_longer_is_darker(app):
    voiced_outside = lambda i: NAN if 100 <= i < 350 else REF_HZ   # noqa: E731
    base = _background_lightness(*render(frames(f0=voiced_outside)), 2.0)
    short_view, short_image = render(frames(f0=voiced_outside), events=[("pause", 1.0, 2.2)])
    long_view, long_image = render(frames(f0=voiced_outside), events=[("pause", 1.0, 3.5)])
    shaded_short = _background_lightness(short_view, short_image, 1.5)
    shaded_long = _background_lightness(long_view, long_image, 1.5)
    assert shaded_short > base + 3
    assert shaded_long > shaded_short + 3                      # 2.5 s is shaded more than 1.2 s
    half_view, half_image = render(frames(f0=voiced_outside), events=[("pause", 1.0, 1.6)])
    assert abs(_background_lightness(half_view, half_image, 1.3) - base) <= 1  # < 1 s: no shade


def test_an_ongoing_pause_grows_but_not_after_a_file_has_ended(app):
    # silence from 2.0 s; confirmed as a pause 0.25 s later; now = 3.6 s
    data = frames(n=360, f0=lambda i: NAN if i >= 200 else REF_HZ,
                  pause_since=lambda i: 2.0 if i >= 225 else NAN)
    live_view, live = render(data, now=3.6)
    assert _background_lightness(live_view, live, 3.0) > _background_lightness(live_view, live, 1.0) + 3
    done_view, done = render(data, now=3.6, source_finished=True)
    assert abs(_background_lightness(done_view, done, 3.0)
               - _background_lightness(done_view, done, 1.0)) <= 1


def test_each_syllable_is_a_tick_along_the_bottom(app):
    view, image = render(frames(), events=[("nucleus", t) for t in (1.0, 2.0, 3.0)])
    lane = view.layout_rects().lane
    y = int(lane.center().y())
    for t in (1.0, 2.0, 3.0):
        assert image.pixelColor(x_of(view, t), y).lightness() > 90
    assert image.pixelColor(x_of(view, 1.5), y).lightness() < 40


# ---- pace ------------------------------------------------------------------------------------

def _pace_fill(view, image):
    """Lit pixels in the pace bar above and below its centre notch."""
    pace = view.layout_rects().pace
    x, cy = int(pace.center().x()), pace.center().y()
    col = column(image, x, pace.top() + 2, pace.bottom() - 2)
    ys = range(int(pace.top() + 2), int(pace.bottom() - 2))
    above = sum(c.lightness() > 120 for y, c in zip(ys, col) if y < cy - 3)
    below = sum(c.lightness() > 120 for y, c in zip(ys, col) if y > cy + 3)
    return above, below


def test_pace_bar_goes_up_when_faster_than_usual_and_down_when_slower(app):
    above, below = _pace_fill(*render(frames(rate=REF_RATE * 1.4)))
    assert above > 10 and below == 0
    above, below = _pace_fill(*render(frames(rate=REF_RATE / 1.4)))
    assert below > 10 and above == 0
    assert _pace_fill(*render(frames(rate=REF_RATE * 1.4), ref=CALIBRATING)) == (0, 0)


# ---- tension colour --------------------------------------------------------------------------

def _line_colour(view, image, t):
    col = plot_column(view, image, t)
    return max(col, key=lambda c: c.lightness())


def test_tension_colour_amber_when_pressed_blue_when_breathy(app):
    view, image = render(frames(tilt=lambda i: REF_TILT + 5 if i < 200 else REF_TILT - 5))
    warm, cool = _line_colour(view, image, 1.0), _line_colour(view, image, 3.0)
    assert warm.red() > warm.blue() + 60
    assert cool.blue() > cool.red() + 60
    view, image = render(frames())
    neutral = _line_colour(view, image, 2.0)
    assert abs(neutral.red() - neutral.blue()) < 25


def test_tension_value_mapping():
    assert tension_value([0.0, 0.5, -0.9])[0] == 0.0
    assert list(tension_value([0.5, -0.9])) == [0.0, 0.0]          # inside the dead zone
    assert tension_value([C.TILT_FULL_SCALE_DB])[0] == pytest.approx(1.0)
    assert tension_value([-2 * C.TILT_FULL_SCALE_DB])[0] == pytest.approx(-1.0)
    assert tension_value([NAN])[0] == 0.0


def test_while_calibrating_the_line_is_grey_and_the_progress_ring_shows(app):
    view, image = render(frames(tilt=REF_TILT + 5), ref=CALIBRATING)
    grey = _line_colour(view, image, 2.0)
    assert abs(grey.red() - grey.blue()) < 25                  # no tension colour yet
    plot = view.layout_rects().plot
    ring = [image.pixelColor(int(plot.left()) + dx, int(plot.top()) + dy).lightness()
            for dx in range(2, 16) for dy in range(2, 16)]
    assert max(ring) > 60


# ---- other views -----------------------------------------------------------------------------

def test_help_overlay_covers_the_view_and_freeze_shows_its_sign(app):
    view, _ = render(frames(), show_disclaimer=True)
    view.show_help = True
    view.toggle_freeze()
    assert view.frozen_at == 4.0
    image = view.grab().toImage()
    box = view.help_rect()
    assert box.width() <= view.width() and box.height() <= view.height()
    corner = image.pixelColor(int(box.left()) + 4, int(box.top()) + 4)
    assert corner.lightness() < 30                               # the dark help panel
    view.show_help = False
    image = view.grab().toImage()
    plot = view.layout_rects().plot
    sign = [image.pixelColor(int(plot.right()) - dx, int(plot.top()) + 7).lightness()
            for dx in (11, 5)]
    assert min(sign) > 150                                       # the two "paused" bars


def test_a_recording_shown_whole_starts_at_the_left_edge(app):
    view, image = render(frames(n=200), now=2.0, anchor_left=True)
    plot = view.layout_rects().plot
    left = column(image, int(plot.left() + plot.width() * 0.1), plot.top(), plot.bottom())
    right = column(image, int(plot.right() - 5), plot.top(), plot.bottom())
    assert max(c.lightness() for c in left) > 150
    # Nothing drawn at the right-hand end except the dim centre line, which is about as light
    # as 63 when it falls exactly on a pixel row (how it falls depends on the font's height).
    centre = plot.center().y() - int(plot.top())
    off_centre = [c for k, c in enumerate(right) if abs(k - centre) > 1.5]
    assert max(c.lightness() for c in off_centre) < 60
    assert max(c.lightness() for c in right) <= QColor(C.CENTRE_LINE).lightness() + 2


def test_comparison_window_shows_each_recording(app):
    recs = [Recording(name=f"take {k}", duration=4.0, frames=frames(), events=[])
            for k in range(3)]
    window = CompareWindow(recs, CALIBRATED)
    assert len(window.views) == 3
    image = window.grab().toImage()
    assert image.width() > 0
    window.close()


def test_empty_views_draw_without_errors(app):
    render([], now=0.0)
    render([ProsodyFrame(0.0, NAN, -90.0, False, NAN, NAN, NAN)], now=0.5, ref=CALIBRATING)
    view, _ = render(frames(), ref=Reference(False, 0.0, None, None, None, None, None))
    view.now_fn = lambda: None
    view.grab()



# ---- easier to read (session 6) --------------------------------------------------------------

def test_the_big_view_caps_its_vertical_scale(app):
    view, _ = render(frames(), size=(1000, 800))
    plot = view.layout_rects().plot
    free = plot.center().y() - float(view.y_for(C.SEMITONE_RANGE, plot))
    view.cap_scale = True
    capped = plot.center().y() - float(view.y_for(C.SEMITONE_RANGE, plot))
    assert free > 300 and capped <= C.MAX_PX_PER_SEMITONE * C.SEMITONE_RANGE + 0.5


def test_short_voiced_runs_are_smoothed_without_errors(app):
    # runs of 5, 6 and 7 frames: shorter than the smoothing window
    voiced = lambda i: REF_HZ if (100 <= i < 105 or 200 <= i < 206 or 300 <= i < 307) else NAN  # noqa: E731
    render(frames(f0=voiced))


def test_the_learning_banner_and_axis_words_draw(app):
    view, image = render(frames(), ref=CALIBRATING, size=(900, 500))
    before = image
    view.learning_banner = True
    view.axis_words = True
    after = view.grab().toImage()
    plot = view.layout_rects().plot
    x, y = int(plot.center().x()), int(plot.top()) + 30
    assert after.pixelColor(x, y) != before.pixelColor(x, y)     # the banner is there
