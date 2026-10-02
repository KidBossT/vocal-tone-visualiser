"""Command line entry point:  python -m tonevis [options]   (run.bat does this for you)."""

from __future__ import annotations

import argparse
import os
import queue
import signal
import sys

KEYS = "Keys in the window: Space freeze, R recalibrate, T always-on-top, H help, Q quit."


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tonevis",
        description="Shows how someone is speaking, live: pitch, loudness, pauses, pace and a "
                    "tension proxy, each measured against the speaker's own usual voice. With "
                    "no options it opens the dashboard. Shows vocal features only; "
                    "interpretation is yours.",
        epilog=KEYS)
    p.add_argument("--corner", action="store_true",
                   help="just the small always-on-top window on the microphone, no dashboard")
    p.add_argument("--listen", action="store_true",
                   help="dashboard: start listening straight away")
    p.add_argument("--file", metavar="WAV",
                   help="play a recording through the small window instead of the microphone")
    p.add_argument("--compare", nargs="+", metavar="WAV",
                   help="show up to four recordings side by side, playing each in turn "
                        "(the demo comparison)")
    p.add_argument("--baseline", metavar="WAV",
                   help="measure against a baseline taken from this recording of the same "
                        "speaker instead of calibrating live (with --compare, the default is "
                        "the first recording)")
    p.add_argument("--calibrate", type=float, default=None, metavar="SECONDS",
                   help="seconds of speech the live calibration uses (default 15)")
    p.add_argument("--mute", action="store_true",
                   help="with --file: analyse at normal speed without playing the sound; with "
                        "--compare: show everything at once, silently")
    p.add_argument("--device", metavar="NUMBER_OR_NAME",
                   help="which microphone to use: its number from --list-devices, or part of "
                        "its name")
    p.add_argument("--list-devices", action="store_true",
                   help="list the microphones and exit")
    p.add_argument("--record", nargs="?", const="", metavar="WAV",
                   help="also save what the microphone hears to a WAV file (default: "
                        "recordings/rec_<date>_<time>.wav). Without this flag nothing is saved.")
    p.add_argument("--seconds", type=float, default=None, metavar="S",
                   help="how many seconds of speech the window shows (default 10)")
    p.add_argument("--debug", action="store_true",
                   help="print the measured latency every 2 seconds")
    p.add_argument("--snapshot", metavar="PNG",
                   help="save a picture of the window when it closes (with --file or "
                        "--compare: when the playing ends, then close)")
    p.add_argument("--quit-after", type=float, metavar="SECONDS",
                   help="close automatically after this many seconds")
    return p


def main(argv: list[str] | None = None) -> int:
    try:   # never crash on a device name the console cannot print
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass
    args = build_parser().parse_args(argv)

    from . import audio   # imported here so --help works even if a package is missing
    from . import config

    if args.list_devices:
        try:
            print(audio.describe_devices())
        except audio.AudioError as exc:
            print(f"Error: {exc}")
            return 1
        return 0
    if args.record is not None and (args.file or args.compare):
        print("--record saves what the microphone hears, so it cannot be combined with "
              "--file or --compare.")
        return 2
    if args.file and args.compare:
        print("Use either --file or --compare, not both.")
        return 2
    if args.compare and len(args.compare) > 4:
        print("--compare shows at most four recordings.")
        return 2
    if args.corner and (args.file or args.compare):
        print("--corner listens to the microphone, so it cannot be combined with --file or "
              "--compare.")
        return 2
    if args.mute and not (args.file or args.compare):
        print("Note: --mute only affects --file and --compare; ignoring it.")
    if args.seconds is not None and not 2.0 <= args.seconds <= 60.0:
        print("--seconds must be between 2 and 60.")
        return 2
    calibration = config.CALIBRATION_SPEECH_SECONDS if args.calibrate is None else args.calibrate
    if not 5.0 <= calibration <= 120.0:
        print("--calibrate must be between 5 and 120 seconds.")
        return 2

    baseline = None
    if args.baseline:
        from .prosody import baseline_from_file
        try:
            baseline = baseline_from_file(args.baseline)
        except (audio.AudioError, ValueError) as exc:
            print(f"Error: could not take a baseline from {args.baseline}: {exc}")
            return 1
        print(f"Baseline from {os.path.basename(args.baseline)}: {baseline.describe()}")

    if args.compare:
        return _run_compare(args, baseline)
    if args.file or args.corner:
        return _run_live(args, baseline, calibration)
    return _run_dashboard(args, baseline, args.calibrate)


def _run_dashboard(args, baseline, calibration: float | None) -> int:
    from PySide6.QtCore import QTimer

    from . import audio, theme
    from .dashboard import SETTINGS_PATH, Dashboard, apply_dark_theme

    app = _qt_app()
    apply_dark_theme(app)
    app.setFont(theme.ui_font(10.0))
    app.setWindowIcon(theme.app_icon())
    # Settings given on the command line win over the remembered ones (settings.ini).
    window = Dashboard(calibration_seconds=calibration, live_seconds=args.seconds,
                       debug=args.debug, settings_path=SETTINGS_PATH)
    if baseline is not None:
        window.engine.use_baseline(baseline)
        window._refresh_baseline_text()
    if args.device is not None:
        try:
            index = audio.pick_device("input", args.device)
        except audio.AudioError as exc:
            print(f"Error: {exc}")
            return 1
        found = window.mic_combo.findData(index)
        if found < 0:                        # a device the list leaves out: add it
            import sounddevice as sd
            window.mic_combo.addItem(sd.query_devices(index)["name"], index)
            window.setup_mic_combo.addItem(sd.query_devices(index)["name"], index)
            found = window.mic_combo.count() - 1
        window.mic_combo.setCurrentIndex(found)
    if args.record:                          # --record FILE: the first listening run goes there
        window.pending_record_path = os.path.abspath(args.record)
        print(f"The first time you press Start listening, the sound is saved to "
              f"{window.pending_record_path}. Press Stop to finish.", flush=True)
    elif args.record is not None:            # --record alone: save every run (the Setup box)
        window.record_check.setChecked(True)
    print("Opening the dashboard. Keys: Space freeze, M mark, N mark with a note, H key, "
          "F1 how it works, F11 full screen.", flush=True)
    window.show()
    if args.listen:
        QTimer.singleShot(300, lambda: window.start_listening(window.mic_combo.currentData()))
    if args.quit_after:
        window.confirm_close = False

        def finish():
            if args.snapshot:
                path = os.path.abspath(args.snapshot)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                ok = window.grab().save(path)
                print(("Saved a picture of the dashboard to " if ok else "Could not save ") + path,
                      flush=True)
            window.close()
        QTimer.singleShot(int(args.quit_after * 1000), finish)
    signal.signal(signal.SIGINT, lambda *_: window.close())
    return app.exec()


def _qt_app():
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv[:1])
    if sys.platform == "win32":
        app.setFont(QFont("Segoe UI", 9))   # Windows' own UI font, also in saved pictures
    return app


def _run_live(args, baseline, calibration: float) -> int:
    from . import audio, config

    source_queue: queue.SimpleQueue = queue.SimpleQueue()
    try:
        if args.file:
            source = audio.FileSource(source_queue, args.file, mute=args.mute)
        else:
            source = audio.MicSource(source_queue, device=args.device)
        source.open()
    except audio.AudioError as exc:
        print(f"Error: {exc}")
        return 1
    except Exception as exc:          # anything unexpected from the sound system
        print(f"Error: could not set up the sound ({type(exc).__name__}: {exc}). "
              "Try --list-devices, or restart the computer's audio.")
        return 1

    recorder = None
    if args.record is not None:
        try:
            recorder = audio.Recorder(args.record or audio.default_recording_path(),
                                      source.samplerate)
        except Exception as exc:
            print(f"Error: could not create the recording file: {exc}")
            return 1

    from PySide6.QtCore import QTimer

    from .display import ToneWindow
    from .tracker import AnalysisWorker

    app = _qt_app()
    worker = AnalysisWorker(source_queue, source.samplerate, live=(source.kind == "mic"),
                            recorder=recorder, baseline=baseline,
                            calibration_seconds=calibration)
    history = config.HISTORY_SECONDS if args.seconds is None else args.seconds
    window = ToneWindow(worker, source=source, debug=args.debug,
                        snapshot_path=args.snapshot, quit_after=args.quit_after,
                        history_seconds=history)
    worker.start()
    print(source.describe())
    if recorder is not None:
        print(f"Recording to {recorder.path}")
    if baseline is None:
        print(f"Calibrating on the first {calibration:.0f} s of speech (the grey line turns "
              "white when done; R starts again).")
    print("Press Q in the window (or close it) to stop. " + KEYS, flush=True)
    window.show()

    def start_sound() -> None:
        try:
            source.start()
        except Exception as exc:
            print(f"Error: could not start the sound: {exc}", flush=True)
            app.exit(1)

    # Start the sound only once the window is up: creating the window keeps Python busy for
    # a moment, and a microphone that was already running would drop audio meanwhile.
    QTimer.singleShot(200, start_sound)
    signal.signal(signal.SIGINT, lambda *_: window.close())   # Ctrl+C in the terminal
    try:
        exit_code = app.exec()
    finally:
        source.stop()
        worker.finish()              # handle what is already queued (so a recording is complete)
        worker.join(timeout=2.0)
        if recorder is not None:
            recorder.close()
            print(f"Saved {recorder.seconds:.1f} s of sound to {recorder.path}")
    return exit_code


def _run_compare(args, baseline) -> int:
    from math import gcd

    import numpy as np
    from scipy.signal import resample_poly

    from . import audio
    from .prosody import Reference, analyse_samples

    try:
        loaded = [(path, *audio.load_mono(path)) for path in args.compare]
    except audio.AudioError as exc:
        print(f"Error: {exc}")
        return 1
    if baseline is None:
        path, x, rate = loaded[0]
        try:
            baseline = analyse_samples(x, rate, learn_baseline=True).stats
        except ValueError as exc:
            print(f"Error: could not take a baseline from {os.path.basename(path)}: {exc}")
            return 1
        print(f"Baseline from the first recording ({os.path.basename(path)}): "
              f"{baseline.describe()}")
    recordings = []
    for letter, (path, x, rate) in zip("ABCD", loaded):
        rec = analyse_samples(x, rate, baseline=baseline, name=os.path.basename(path))
        recordings.append(rec)
        print(f"{letter} = {rec.name}: {rec.summary(baseline)}")

    from PySide6.QtCore import QTimer

    from .display import CompareWindow
    from .tracker import AnalysisWorker

    app = _qt_app()
    source = clock_worker = starts = None
    if not args.mute:
        common, gap = 48_000, 1.0          # play the recordings one after another
        pieces, starts, position = [], [], 0.0
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
        print(source.describe())
    window = CompareWindow(recordings, Reference.from_stats(baseline), clock_worker=clock_worker,
                           starts=starts, snapshot_path=args.snapshot, history=args.seconds)
    window.show()
    if source is not None:
        QTimer.singleShot(300, source.start)
    if args.quit_after:
        QTimer.singleShot(int(args.quit_after * 1000), window.close)
    signal.signal(signal.SIGINT, lambda *_: window.close())
    try:
        exit_code = app.exec()
    finally:
        if source is not None:
            source.stop()
        if clock_worker is not None:
            clock_worker.finish()
            clock_worker.join(timeout=2.0)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
