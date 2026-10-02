"""Make the test recordings with the text-to-speech voices built into Windows.

    .venv\\Scripts\\python.exe demo\\make_test_wavs.py

Writes:
  demo/wavs/sample_david.wav, sample_zira.wav   one plain reading each (a lower and a higher voice)
  demo/wavs/baseline_david.wav, baseline_zira.wav  about 25 s of neutral talk, for calibration
  demo/wavs/take_a.wav ... take_d.wav   the same sentence delivered four ways (the on-camera
                                        comparison); see TAKES below for how each is made
  demo/failures/*.wav                   situations where the display is known to go wrong

These voices are synthetic. The takes are made by editing one voice with known changes (speed,
pitch movement, loudness, spectral balance), which makes them good, repeatable test material,
but they sound robotic on camera. Record real people for the video: see the README.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from xml.sax.saxutils import escape

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, os.pardir, "tools"))
import voice_effects as fx  # noqa: E402

SENTENCE = "I've been sleeping better, and work has been fine this week."
BASELINE_TEXT = ("I've been sleeping better, and work has been fine this week. "
                 "I usually take the bus in the morning, and I get to the office around nine. "
                 "Most days I have lunch with two people from my team. "
                 "In the evening I cook something simple and watch a little television. "
                 "At the weekend I visited my sister, and we went for a walk by the river.")
RATE = 22_050          # Hz. Not the analysis rate on purpose, so --file exercises resampling.
LEAD_SECONDS = 0.8     # quiet before the speech
TAIL_SECONDS = 1.0     # quiet after it
SPEECH_LEVEL_DB = -28.0  # level of the speech itself (dB below full scale) before any take's gain
NOISE_DB = -65.0       # faint background hiss, so quiet parts behave like a room, not digital silence

ZIRA, DAVID = "Microsoft Zira Desktop", "Microsoft David Desktop"
B = '<break time="{}ms"/>'.format

# How each take is made. `ssml` is what the voice says; the rest are edits applied afterwards.
TAKES = {
    "take_a.wav": dict(  # calm and even
        ssml=f"I've been sleeping better, {B(350)} and work has been fine this week.",
        speed=1.08, pitch_range=1.0, shift=0.0, quality=None, gain=0.0),
    "take_b.wav": dict(  # rising and hesitant, with long pauses
        ssml=(f"I've been {B(1300)} sleeping <prosody pitch='+25%'>better</prosody> {B(1800)} "
              f"and work {B(900)} um {B(1100)} has been <prosody pitch='+35%'>fine</prosody> "
              f"{B(1500)} <prosody pitch='+30%'>this week?</prosody>"),
        speed=1.1, pitch_range=1.1, shift=2.0, quality=None, gain=-2.0),
    "take_c.wav": dict(  # fast and loud
        ssml=escape(SENTENCE),
        speed=0.72, pitch_range=1.3, shift=2.0, quality="pressed", gain=8.0),
    "take_d.wav": dict(  # flat and quiet
        ssml=escape(SENTENCE),
        speed=1.05, pitch_range=0.25, shift=-1.0, quality="breathy", gain=-10.0),
}

PS_SCRIPT = r"""
param([string]$OutPath, [string]$Voice, [string]$SsmlPath, [int]$Rate)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$bits = [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen
$mono = [System.Speech.AudioFormat.AudioChannel]::Mono
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo($Rate, $bits, $mono)
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $s.SelectVoice($Voice)
  $s.SetOutputToWaveFile($OutPath, $fmt)
  $s.SpeakSsml([System.IO.File]::ReadAllText($SsmlPath))
} finally { $s.Dispose() }
"""


def synthesize(voice: str, ssml_body: str) -> np.ndarray:
    ssml = ("<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' "
            f"xml:lang='en-US'>{ssml_body}</speak>")
    with tempfile.TemporaryDirectory() as tmp:
        ps1, ssml_path, wav = (os.path.join(tmp, n) for n in ("tts.ps1", "in.ssml", "out.wav"))
        with open(ps1, "w", encoding="utf-8") as f:
            f.write(PS_SCRIPT)
        with open(ssml_path, "w", encoding="utf-8") as f:
            f.write(ssml)
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1,
             "-OutPath", wav, "-Voice", voice, "-SsmlPath", ssml_path, "-Rate", str(RATE)],
            capture_output=True, text=True)
        if result.returncode != 0 or not os.path.isfile(wav):
            raise RuntimeError(f"Windows speech failed for {voice}:\n{result.stderr.strip()}")
        x, _ = sf.read(wav, dtype="float64")
    # The voices carry a small DC offset. Praat's resynthesis removes the overall mean, which
    # would leave the silent gaps sitting at a constant offset, so remove it here first.
    return fx.band(x, RATE, 40.0, None)


def trim(x: np.ndarray, threshold_db: float = -50.0) -> np.ndarray:
    """Cut the silence the voice leaves at either end (the lead-in and tail are added later)."""
    env = fx.envelope(x, RATE)
    loud = np.flatnonzero(env > np.max(env) * 10 ** (threshold_db / 20))
    return x[loud[0]:loud[-1] + 1] if loud.size else x


def set_level(x: np.ndarray, level_db: float) -> np.ndarray:
    return x * 10 ** (level_db / 20) / fx.active_rms(x, RATE)


def finish(x: np.ndarray, path: str, seed: int) -> float:
    """Add quiet lead-in and tail, add faint hiss, save as 16-bit WAV. Returns the duration."""
    x = np.concatenate([np.zeros(int(LEAD_SECONDS * RATE)), x, np.zeros(int(TAIL_SECONDS * RATE))])
    x = x + 10 ** (NOISE_DB / 20) * np.random.default_rng(seed).standard_normal(x.size)
    peak = float(np.max(np.abs(x)))
    if peak > 0.99:
        raise RuntimeError(f"{os.path.basename(path)} would clip (peak {peak:.2f})")
    sf.write(path, x, RATE, subtype="PCM_16")
    return x.size / RATE


def make_take(spec: dict) -> np.ndarray:
    x = trim(synthesize(ZIRA, spec["ssml"]))
    if spec["speed"] != 1.0:
        x = fx.change_speed(x, RATE, spec["speed"])
    if spec["pitch_range"] != 1.0 or spec["shift"]:
        x = fx.scale_pitch_range(x, RATE, spec["pitch_range"], spec["shift"])
    x = set_level(x, SPEECH_LEVEL_DB)        # every take starts from the same speech level...
    if spec["quality"] == "pressed":
        x = fx.pressed(x, RATE)
    elif spec["quality"] == "breathy":
        x = fx.breathy(x, RATE)
    x = set_level(x, SPEECH_LEVEL_DB)        # ...so voice-quality edits do not change loudness
    return fx.gain_db(x, spec["gain"])       # and only this line does


def make_session_demo(wav_dir: str) -> float:
    """A ~55 s pretend session from the files above: the neutral reading (the dashboard
    calibrates on it), then the four takes, with short silences between. For trying the
    dashboard's Review tab ("Analyse a recording...")."""
    parts = ["baseline_zira.wav", "take_a.wav", "take_b.wav", "take_c.wav", "take_d.wav"]
    gap = np.zeros(int(1.5 * RATE))
    pieces = []
    for k, name in enumerate(parts):
        x, rate = sf.read(os.path.join(wav_dir, name), dtype="float64")
        if rate != RATE:
            raise RuntimeError(f"{name} is not at {RATE} Hz")
        pieces += ([gap] if k else []) + [x]
    x = np.concatenate(pieces)
    rng = np.random.default_rng(30)             # keep the hiss going through the gaps
    silent = np.abs(x) < 1e-9
    x[silent] = 10 ** (NOISE_DB / 20) * rng.standard_normal(int(silent.sum()))
    sf.write(os.path.join(wav_dir, "session_demo.wav"), x, RATE, subtype="PCM_16")
    return x.size / RATE


def main() -> int:
    if "--session-only" in sys.argv:            # just rebuild session_demo.wav from the others
        seconds = make_session_demo(os.path.join(HERE, "wavs"))
        print(f"made wavs\\session_demo.wav ({seconds:.1f} s)")
        return 0
    if sys.platform != "win32":
        print("This script uses the Windows speech voices. The WAVs it makes are already in "
              "demo/wavs and demo/failures, so there is nothing to do on this computer.")
        return 0
    wav_dir, fail_dir = os.path.join(HERE, "wavs"), os.path.join(HERE, "failures")
    os.makedirs(wav_dir, exist_ok=True)
    os.makedirs(fail_dir, exist_ok=True)
    made = []

    def save(x, folder, name, seed):
        seconds = finish(x, os.path.join(folder, name), seed)
        made.append(f"{os.path.relpath(os.path.join(folder, name), HERE)} ({seconds:.1f} s)")

    plain = {voice: trim(synthesize(voice, escape(SENTENCE))) for voice in (ZIRA, DAVID)}
    save(set_level(plain[DAVID], SPEECH_LEVEL_DB), wav_dir, "sample_david.wav", 1)
    save(set_level(plain[ZIRA], SPEECH_LEVEL_DB), wav_dir, "sample_zira.wav", 2)
    for seed, (voice, name) in enumerate(((ZIRA, "baseline_zira.wav"),
                                          (DAVID, "baseline_david.wav")), start=3):
        save(set_level(trim(synthesize(voice, escape(BASELINE_TEXT))), SPEECH_LEVEL_DB),
             wav_dir, name, seed)
    for seed, (name, spec) in enumerate(TAKES.items(), start=10):
        save(make_take(spec), wav_dir, name, seed)

    # Failure cases, all from the plain sentence.
    zira = set_level(plain[ZIRA], SPEECH_LEVEL_DB)
    david = set_level(plain[DAVID], SPEECH_LEVEL_DB - 3.0)
    offset = int(1.0 * RATE)
    overlap = np.zeros(max(zira.size, david.size + offset))
    overlap[:zira.size] += zira
    overlap[offset:offset + david.size] += david
    save(overlap, fail_dir, "overlap.wav", 20)                        # two people at once
    save(set_level(fx.band(zira, RATE, 350.0, 4000.0), SPEECH_LEVEL_DB),
         fail_dir, "small_speaker.wav", 21)                           # voice via a tiny speaker
    save(set_level(fx.whisper(zira, RATE), SPEECH_LEVEL_DB), fail_dir, "whisper.wav", 22)
    seconds = make_session_demo(wav_dir)
    made.append(f"wavs\\session_demo.wav ({seconds:.1f} s)")

    print("made:\n  " + "\n  ".join(made))
    return 0


if __name__ == "__main__":
    sys.exit(main())
