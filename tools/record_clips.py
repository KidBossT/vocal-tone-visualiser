"""Records the app's own scenes for the Stage 1 video as MP4 clips, off-screen.

    .venv\\Scripts\\python.exe tools\\record_clips.py [--takes demo\\takes] [--only NAME ...]

(or double-click make_clips.bat). It needs ffmpeg, which `pip install imageio-ffmpeg` brings
along; make_clips.bat installs it the first time.

The app runs exactly as it does on screen (the same analysis, in real time), but in an
invisible window, so nothing pops up and nothing is played aloud. Every frame is drawn by the
app itself, and the sound in each clip is the sound the app was analysing, so the two line up.
The app runs in slow motion while filming, so making the clips takes about three times as
long as they last (about 8 minutes in all).

Clips, written to video/clips (1920 x 1080, 30 fps, except the corner view at 1440 x 810):
- scene3_demo_live.mp4    the Start here card, then the demo recording on the Live tab
- scene7_corner_view.mp4  the corner view during the same demo
- scene4_compare.mp4      the Compare tab playing the four takes, with sound
- scene7_guide.mp4        a slow scroll through How it works (no sound)

With --takes FOLDER the Compare clip uses real recordings (baseline.wav, a.wav ... d.wav, as
saved by "Record your own takes") instead of the synthetic voices.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")      # no windows pop up
os.environ["QT_SCALE_FACTOR"] = "1.5"      # drawn as on a laptop at 150%: big, sharp text
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_FONTDIR", r"C:\Windows\Fonts")   # real fonts off-screen

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, os.pardir))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from PySide6.QtCore import QEventLoop  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from tonevis import audio, theme  # noqa: E402
from tonevis import config as C  # noqa: E402
from tonevis.dashboard import COMPARE, GUIDE, LIVE, Dashboard, apply_dark_theme  # noqa: E402

FPS = 30
SCALE = 1.5
FULL = (1920, 1080)         # pixels in the clip; the window itself is 1280 x 720 at 150%
CORNER = (1440, 810)
LEAD = 3.0          # seconds of the still window before anything plays
TAIL = 3.0          # seconds held after it finishes
CLIPS = ("scene3_demo_live", "scene7_corner_view", "scene4_compare", "scene7_guide")

played: list[tuple[np.ndarray, int]] = []     # the sound each playback fed to the analysis


class SlowClock:
    """The app's clock (time.perf_counter), slowed down while filming.

    Grabbing a whole 1080p window takes longer than a 30th of a second, so the app is run in
    slow motion: its sound, analysis and drawing all follow this clock, and frames are taken
    every 30th of a second of *its* time. The clip then plays back at normal speed, smoothly."""

    def __init__(self):
        self.real = time.perf_counter
        self.speed = 1.0
        self.r0 = self.v0 = self.real()

    def __call__(self) -> float:
        return self.v0 + (self.real() - self.r0) * self.speed

    def set_speed(self, speed: float) -> None:
        self.v0, self.r0 = self(), self.real()
        self.speed = speed


clock = SlowClock()
time.perf_counter = clock            # every module reads time.perf_counter() when it needs it


class SilentFileSource(audio.FileSource):
    """The app's own file player, always silent, keeping a copy of what it played."""

    def __init__(self, out_queue, path=None, mute=False, **kw):
        super().__init__(out_queue, path, True, **kw)
        played.append((self.samples, self.samplerate))

    def _feed_silently(self) -> None:
        # As the app's own, but waiting on the slowed clock rather than for real seconds.
        block = int(round(self.samplerate * C.BLOCK_SECONDS))
        t0 = clock() + 0.05
        pos = 0
        while pos < self.samples.size and not self._halt.is_set():
            chunk = self.samples[pos:pos + block]
            first_wall = t0 + pos / self.samplerate
            while clock() < first_wall + chunk.size / self.samplerate:
                if self._halt.wait(0.002):
                    break
            self.q.put((chunk, first_wall))
            pos += chunk.size
        self._ended = True
        self.q.put(audio.END)


audio.FileSource = SilentFileSource


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
    except ImportError:
        sys.exit("ffmpeg is missing. Run:  .venv\\Scripts\\python.exe -m pip install imageio-ffmpeg")
    return imageio_ffmpeg.get_ffmpeg_exe()


class Clip:
    """Frames of one widget, piped to ffmpeg at a steady 30 fps.

    The position (in seconds from the start of the clip) decides how many frames should exist
    by now; a slow grab is covered by repeating the last frame, so the picture never drifts
    away from the sound."""

    def __init__(self, widget, path: str, size: tuple[int, int]):
        self.widget, self.path, self.size = widget, path, size
        self.tmp = path + ".video.mp4"
        w, h = size
        self.proc = subprocess.Popen(
            [ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
             "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset",
             "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", self.tmp],
            stdin=subprocess.PIPE)
        self.written = 0
        self.grabs = 0

    def frame(self) -> bytes:
        image = self.widget.grab().toImage().convertToFormat(QImage.Format.Format_RGB888)
        w, h = self.size
        if (image.width(), image.height()) != (w, h):
            image = image.scaled(w, h)
        data = bytes(image.constBits())
        stride = image.bytesPerLine()
        if stride != w * 3:                        # drop Qt's row padding
            data = b"".join(data[r * stride:r * stride + w * 3] for r in range(h))
        self.grabs += 1
        return data

    def advance(self, position: float) -> None:
        target = int(position * FPS)
        if target <= self.written:
            return
        data = self.frame()
        for _ in range(target - self.written):
            self.proc.stdin.write(data)
        self.written = target

    def finish(self, sound: np.ndarray | None = None, rate: int = 0, sound_at: float = 0.0) -> None:
        self.proc.stdin.close()
        self.proc.wait()
        if sound is None:
            os.replace(self.tmp, self.path)
        else:
            wav = self.path + ".sound.wav"
            pad = np.zeros(int(round(sound_at * rate)), np.float32)
            sf.write(wav, np.concatenate([pad, sound.astype(np.float32)]), rate)
            subprocess.run([ffmpeg_exe(), "-y", "-loglevel", "error", "-i", self.tmp, "-i", wav,
                            "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
                            "-b:a", "192k", self.path], check=True)
            os.remove(self.tmp)
            os.remove(wav)
        seconds = self.written / FPS
        print(f"wrote {os.path.relpath(self.path, ROOT)}  ({seconds:.0f} s, "
              f"{self.grabs / max(seconds, 1e-9):.0f} fresh frames a second)")


def film(app, clips: list[Clip], position, done, tail: float = TAIL) -> None:
    """Let the app run, feeding frames to the clips, until done() and then `tail` seconds."""
    next_grab = time.perf_counter()
    ended_at = ended_pos = None
    last_pos = 0.0
    while True:
        app.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 5)
        now = time.perf_counter()
        if ended_at is None:
            pos = max(last_pos, position())
            if done():
                ended_at, ended_pos = now, pos
        else:
            pos = ended_pos + (now - ended_at)
            if now - ended_at >= tail:
                break
        last_pos = pos
        if now >= next_grab:
            for clip in clips:
                clip.advance(pos)
            next_grab = now + 1.0 / FPS
        time.sleep(0.001)


def hold(app, clips: list[Clip], seconds: float, start: float = 0.0) -> float:
    t0 = time.perf_counter()
    film(app, clips, lambda: start + time.perf_counter() - t0,
         lambda: time.perf_counter() - t0 >= seconds, tail=0.0)
    return start + seconds


def new_dashboard() -> Dashboard:
    d = Dashboard(calibration_seconds=15.0, live_seconds=15.0,
                  settings_path=os.path.join(ROOT, "video", "clips", "_clips_settings.ini"))
    d.confirm_close = False
    d.setMinimumSize(0, 0)
    d.resize(round(FULL[0] / SCALE), round(FULL[1] / SCALE))
    d.show()
    return d


def demo_clips(app, out: str, wanted: set[str]) -> None:
    d = new_dashboard()
    d.tabs.setCurrentIndex(LIVE)
    clips = []
    if "scene3_demo_live" in wanted:
        clips.append(Clip(d, os.path.join(out, "scene3_demo_live.mp4"), FULL))
    if "scene7_corner_view" in wanted:
        d.corner_button.setChecked(True)
        d.corner.resize(round(CORNER[0] / SCALE), round(CORNER[1] / SCALE))
        clips.append(Clip(d.corner, os.path.join(out, "scene7_corner_view.mp4"), CORNER))
    lead = hold(app, clips, LEAD)
    played.clear()
    d.try_demo(mute=True)
    engine = d.engine
    film(app, clips, lambda: lead + max(0.0, engine.now() or 0.0),
         lambda: not engine.running)
    sound, rate = played[0]
    for clip in clips:
        clip.finish(sound, rate, lead)
    if d.corner is not None:
        d.corner.close()
    d.close()


def compare_clip(app, out: str, takes: str | None) -> None:
    d = new_dashboard()
    d.tabs.setCurrentIndex(COMPARE)
    if takes:
        if not d.use_takes_from(takes):
            sys.exit(f"No takes in {takes}: it needs baseline.wav and at least one of a.wav ... d.wav")
    else:
        d._use_demo_takes()
    clip = Clip(d, os.path.join(out, "scene4_compare.mp4"), FULL)
    lead = hold(app, [clip], LEAD)
    played.clear()
    d.run_comparison(play=True)
    clock = d.compare_clock.clock

    def position() -> float:
        return lead + (max(0.0, clock.stream_now()) if clock.offset is not None else 0.0)

    film(app, [clip], position, d.compare_grid.playing_done)
    sound, rate = played[0]
    clip.finish(sound, rate, lead)
    d._stop_comparison()
    d.close()


def guide_clip(app, out: str) -> None:
    d = new_dashboard()
    d.tabs.setCurrentIndex(GUIDE)
    clip = Clip(d, os.path.join(out, "scene7_guide.mp4"), FULL)
    bar = d.guide.verticalScrollBar()
    bar.setValue(0)
    at = hold(app, [clip], LEAD)
    scroll = 40.0
    t0 = time.perf_counter()

    def position() -> float:
        k = min(1.0, (time.perf_counter() - t0) / scroll)
        bar.setValue(round(bar.maximum() * (0.5 - 0.5 * np.cos(np.pi * k))))   # ease in and out
        return at + time.perf_counter() - t0

    film(app, [clip], position, lambda: time.perf_counter() - t0 >= scroll)
    clip.finish()
    d.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--takes", help="folder of real takes for the Compare clip "
                                        "(for example demo\\takes)")
    parser.add_argument("--only", nargs="+", choices=CLIPS, help="make only these clips")
    parser.add_argument("--out", default=os.path.join(ROOT, "video", "clips"))
    parser.add_argument("--speed", type=float, default=0.33,
                        help="how fast the app runs while filming (lower is smoother but slower "
                             "to make; the clips always play at normal speed)")
    args = parser.parse_args()
    wanted = set(args.only or CLIPS)
    out = os.path.abspath(args.out)
    os.makedirs(out, exist_ok=True)
    ffmpeg_exe()
    clock.set_speed(args.speed)

    app = QApplication.instance() or QApplication([])
    apply_dark_theme(app)
    app.setFont(theme.ui_font(10.0))
    if wanted & {"scene3_demo_live", "scene7_corner_view"}:
        demo_clips(app, out, wanted)
    if "scene4_compare" in wanted:
        compare_clip(app, out, args.takes)
    if "scene7_guide" in wanted:
        guide_clip(app, out)
    settings = os.path.join(out, "_clips_settings.ini")
    if os.path.exists(settings):
        os.remove(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
