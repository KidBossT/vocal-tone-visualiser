"""The on-camera comparison: the same sentence delivered four ways, side by side.

    .venv\\Scripts\\python.exe demo\\run_demo.py        (or double-click run_demo.bat)

Each panel fills in while its recording plays, measured against one baseline recording of the
same speaker. Uses your own recordings when demo/takes/ holds baseline.wav plus any of a.wav,
b.wav, c.wav and d.wav (see DEMO_SCRIPT.md for what to record); otherwise the synthetic ones.

Extra options are passed on to the visualiser, for example --mute (show everything at once,
silently) or --snapshot comparison.png.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir))

from tonevis.__main__ import main as tonevis_main  # noqa: E402


def choose_files() -> tuple[str, list[str], str]:
    own = os.path.join(HERE, "takes")
    own_takes = [os.path.join(own, f"{k}.wav") for k in "abcd"]
    own_takes = [p for p in own_takes if os.path.isfile(p)]
    if os.path.isfile(os.path.join(own, "baseline.wav")) and own_takes:
        return os.path.join(own, "baseline.wav"), own_takes, "your recordings in demo/takes"
    wavs = os.path.join(HERE, "wavs")
    return (os.path.join(wavs, "baseline_zira.wav"),
            [os.path.join(wavs, f"take_{k}.wav") for k in "abcd"],
            "the synthetic takes (record real ones for the video: see DEMO_SCRIPT.md)")


def main() -> int:
    baseline, takes, which = choose_files()
    print(f"Demo comparison using {which}:")
    for letter, path in zip("ABCD", takes):
        print(f"  {letter} = {os.path.relpath(path, os.path.join(HERE, os.pardir))}")
    return tonevis_main(["--compare", *takes, "--baseline", baseline, *sys.argv[1:]])


if __name__ == "__main__":
    sys.exit(main())
