"""Getting sound in: the live microphone, or a WAV file played aloud.

Both sources put ``(samples, wall_time_of_first_sample)`` tuples on a queue, and a file
source finishes with ``END``. Samples are mono float32 at the source's own sample rate;
the analysis thread converts them to 16 kHz with ``StreamResampler``. Wall times use
``time.perf_counter()`` and say when that sound reached the microphone (or the listener's
ears, for a file), which is what the latency measurement is based on.

Nothing is written to disk unless a ``Recorder`` is created (the --record flag).
"""

from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from math import gcd

import numpy as np
import sounddevice as sd
import soundfile as sf
from scipy.signal import firwin, resample_poly

from . import config as C

END = object()  # queue marker: the file has finished


class AudioError(RuntimeError):
    """A problem worth showing to the user as a plain message rather than a traceback."""


# ---- Resampling ----------------------------------------------------------------------------

class StreamResampler:
    """Converts audio arriving in blocks from one sample rate to another, keeping state
    between blocks so there are no clicks at block boundaries.

    It uses the same windowed-sinc filter as ``scipy.signal.resample_poly`` (the tests check
    the two agree), applied causally, one block at a time, as a polyphase filter. The output
    lags the input by ``delay_seconds`` (0.6 ms for 48 kHz to 16 kHz).
    """

    def __init__(self, rate_in: int, rate_out: int):
        self.rate_in, self.rate_out = int(rate_in), int(rate_out)
        g = gcd(self.rate_in, self.rate_out)
        self.up, self.down = self.rate_out // g, self.rate_in // g
        self.passthrough = self.up == self.down
        if self.passthrough:
            self.delay_seconds = 0.0
            return
        max_rate = max(self.up, self.down)
        half_len = 10 * max_rate
        h = firwin(2 * half_len + 1, 1.0 / max_rate, window=("kaiser", 5.0)) * self.up
        taps = -(-h.size // self.up)                       # taps per polyphase branch
        h = np.concatenate([h, np.zeros(taps * self.up - h.size)])
        self._poly = h.reshape(taps, self.up).T            # _poly[phase, k] = h[phase + k*up]
        self._taps = taps
        self._hist = np.zeros(taps - 1)                    # the newest taps-1 input samples
        self._n_in = 0                                     # input samples consumed
        self._n_out = 0                                    # output samples produced
        self.delay_seconds = half_len / (self.up * self.rate_in)

    def process(self, x: np.ndarray) -> np.ndarray:
        x = np.asarray(x, dtype=np.float64).ravel()
        if self.passthrough:
            return x.copy()
        buf = np.concatenate([self._hist, x])
        total_in = self._n_in + x.size
        # Output n uses input samples up to floor(n*down/up); produce every output whose
        # newest input sample has arrived.
        n_end = -(-total_in * self.up // self.down)
        n = np.arange(self._n_out, n_end, dtype=np.int64)
        if n.size:
            pos = n * self.down
            newest = pos // self.up
            phase = pos % self.up
            first_in_buf = self._n_in - (self._taps - 1)   # absolute index of buf[0]
            idx = (newest - first_in_buf)[:, None] - np.arange(self._taps)[None, :]
            y = np.einsum("ij,ij->i", buf[idx], self._poly[phase])
        else:
            y = np.zeros(0)
        self._hist = buf[buf.size - (self._taps - 1):]
        self._n_in, self._n_out = total_in, n_end
        return y


# ---- Choosing devices ----------------------------------------------------------------------

# Lower is better. On Windows the default route (MME) adds roughly 90 ms of delay, so the
# same physical device is opened through WASAPI instead.
_API_PREFERENCE = {"Windows WASAPI": 0, "Core Audio": 0, "Windows WDM-KS": 1,
                   "Windows DirectSound": 2, "MME": 3}


def _api_name(index: int) -> str:
    return sd.query_hostapis(sd.query_devices(index)["hostapi"])["name"]


def pick_device(kind: str, spec: str | int | None = None) -> int:
    """Return the device number to use.

    kind: "input" or "output". spec: None for the system default, a device number,
    or part of a device name (as shown by --list-devices).
    """
    channels_key = f"max_{kind}_channels"
    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise AudioError(f"Could not list the sound devices: {exc}") from exc
    if spec is None or str(spec).strip() == "":
        if sys.platform == "win32":
            for api in sd.query_hostapis():
                default = api.get(f"default_{kind}_device", -1)
                if api["name"] == "Windows WASAPI" and default is not None and default >= 0:
                    return int(default)
        default = sd.default.device[0 if kind == "input" else 1]
        if default is None or default < 0:
            raise AudioError(f"This computer has no default {kind} device. "
                             "Plug one in, or choose one with --device (see --list-devices).")
        return int(default)
    text = str(spec).strip()
    if text.isdigit():
        index = int(text)
        if index >= len(devices) or devices[index][channels_key] < 1:
            raise AudioError(f"Device {index} is not an {kind} device. "
                             "Run with --list-devices to see the choices.")
        return index
    matches = [i for i, d in enumerate(devices)
               if d[channels_key] > 0 and text.lower() in d["name"].lower()]
    if not matches:
        raise AudioError(f'No {kind} device has "{text}" in its name. '
                         "Run with --list-devices to see the choices.")
    matches.sort(key=lambda i: _API_PREFERENCE.get(_api_name(i), 9))
    return matches[0]


def describe_devices() -> str:
    """Human-readable list of the inputs, marking the one used by default."""
    try:
        default_in = pick_device("input")
    except AudioError:
        default_in = -1
    rows = []
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            api = _api_name(i)
            rows.append((_API_PREFERENCE.get(api, 9), i, d["name"], api))
    rows.sort()
    lines = ["Microphones and other inputs. Use the number, or part of the name, with --device:"]
    for _, i, name, api in rows:
        mark = "   <- used by default" if i == default_in else ""
        lines.append(f"  {i:3d}  {name}  [{api}]{mark}")
    if sys.platform == "win32":
        lines.append("Tip: entries marked [Windows WASAPI] have the least delay.")
    return "\n".join(lines)


# ---- Sources -------------------------------------------------------------------------------

class MicSource:
    """Live microphone input."""

    kind = "mic"

    def __init__(self, out_queue, device: str | int | None = None):
        self.q = out_queue
        self.device = pick_device("input", device)
        info = sd.query_devices(self.device)
        self.name = info["name"]
        self.api = _api_name(self.device)
        self.samplerate = int(round(info["default_samplerate"]))
        self._max_channels = max(1, int(info["max_input_channels"]))
        self._channels = 1
        self._stream = None
        self.latency = 0.0      # seconds, as reported by the sound system once open
        self.overflows = 0      # times the sound card had to drop audio

    def open(self) -> None:
        """Open the device (reports problems early); sound starts flowing with start()."""
        errors = []
        for channels in dict.fromkeys((1, self._max_channels)):   # mono first, then native
            try:
                stream = sd.InputStream(
                    device=self.device, samplerate=self.samplerate, channels=channels,
                    dtype="float32", blocksize=int(round(self.samplerate * C.BLOCK_SECONDS)),
                    latency=C.INPUT_LATENCY, callback=self._callback)
            except Exception as exc:
                errors.append(f"{channels} channel(s): {exc}")
                continue
            self._stream, self._channels = stream, channels
            break
        else:
            raise AudioError(f'Could not open the microphone "{self.name}" ({self.api}). '
                             + " / ".join(errors))
        self.latency = float(self._stream.latency)

    def start(self) -> None:
        if self._stream is None:
            self.open()
        self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        now = time.perf_counter()
        if status.input_overflow:
            self.overflows += 1
        if self._channels == 1:
            x = indata[:, 0].copy()
        else:
            x = indata.mean(axis=1, dtype=np.float32)
        # The newest sample in this block reached the microphone about `latency` s ago.
        self.q.put((x, now - self.latency - frames / self.samplerate))

    def describe(self) -> str:
        return (f"Listening to: {self.name} [{self.api}, {self.samplerate} Hz, "
                f"buffer {self.latency * 1000:.0f} ms]")

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


def load_mono(path: str) -> tuple[np.ndarray, int]:
    """Read a sound file as mono float32. Returns (samples, sample rate)."""
    path = os.path.abspath(path)
    name = os.path.basename(path)
    if not os.path.isfile(path):
        raise AudioError(f"File not found: {path}")
    try:
        data, rate = sf.read(path, dtype="float32", always_2d=True)
    except Exception as exc:
        raise AudioError(f"Could not read {name} as a sound file: {exc}") from exc
    if data.shape[0] == 0:
        raise AudioError(f"{name} contains no sound.")
    return data.mean(axis=1, dtype=np.float32), int(rate)


class FileSource:
    """Plays a sound file (or samples already in memory) aloud and feeds the same sound to the
    analysis, in step with playback.

    With mute=True it feeds the analysis at real-time speed without making a sound.
    """

    kind = "file"

    def __init__(self, out_queue, path: str | None = None, mute: bool = False, *,
                 samples: np.ndarray | None = None, rate: int | None = None,
                 name: str | None = None):
        self.q = out_queue
        if samples is None:
            mono, rate = load_mono(path)
            self.name = name or os.path.basename(path)
        else:
            mono = np.asarray(samples, dtype=np.float32)
            self.name = name or "sound"
        self.mute = mute
        self.device = None
        self.device_name = ""
        self._channels = 1
        if not mute:
            try:
                self.device = pick_device("output")
                info = sd.query_devices(self.device)
                self.device_name = info["name"]
                self._channels = max(1, min(2, int(info["max_output_channels"])))
                device_rate = int(round(info["default_samplerate"]))
            except AudioError as exc:
                print(f"No speaker available ({exc}); playing silently.")
                self.mute = True
                device_rate = rate
            if device_rate != rate:
                # Convert once, up front, to the rate the speaker runs at.
                g = gcd(device_rate, int(rate))
                mono = resample_poly(mono, device_rate // g, int(rate) // g).astype(np.float32)
                rate = device_rate
        self.samplerate = int(rate)
        self.samples = np.ascontiguousarray(mono, dtype=np.float32)
        self.duration = self.samples.size / self.samplerate
        self.latency = 0.0
        self.underflows = 0
        self.overflows = 0
        self._pos = 0
        self._ended = False
        self._halt = threading.Event()
        self._thread = None
        self._stream = None

    def open(self) -> None:
        """Open the speaker (falls back to silent playback if that fails)."""
        if self.mute or self._stream is not None:
            return
        errors = []
        for channels in dict.fromkeys((self._channels, 2, 1)):
            try:
                stream = sd.OutputStream(
                    device=self.device, samplerate=self.samplerate, channels=channels,
                    dtype="float32", blocksize=int(round(self.samplerate * C.BLOCK_SECONDS)),
                    latency=C.OUTPUT_LATENCY, callback=self._callback)
            except Exception as exc:
                errors.append(f"{channels} channel(s): {exc}")
                continue
            self._stream = stream
            self.latency = float(stream.latency)
            return
        print("Could not play sound (" + " / ".join(errors) + "); playing silently.")
        self.mute = True

    def start(self) -> None:
        self.open()
        if self._stream is not None:
            self._stream.start()
            return
        self._thread = threading.Thread(target=self._feed_silently, name="file-feeder",
                                        daemon=True)
        self._thread.start()

    def _callback(self, outdata, frames, time_info, status) -> None:
        now = time.perf_counter()
        if status.output_underflow:
            self.underflows += 1
        chunk = self.samples[self._pos:self._pos + frames]
        n = chunk.size
        if n:
            outdata[:n] = np.clip(chunk, -1.0, 1.0)[:, None]
            # The first sample of this chunk will be heard about `latency` s from now.
            self.q.put((chunk, now + self.latency))
        if n < frames:
            outdata[n:] = 0.0
        self._pos += n
        if self._pos >= self.samples.size:
            if not self._ended:
                self._ended = True
                self.q.put(END)
            raise sd.CallbackStop

    def _feed_silently(self) -> None:
        block = int(round(self.samplerate * C.BLOCK_SECONDS))
        t0 = time.perf_counter() + 0.05
        pos = 0
        while pos < self.samples.size and not self._halt.is_set():
            chunk = self.samples[pos:pos + block]
            first_wall = t0 + pos / self.samplerate
            # Hand the chunk over only once real time has passed its end, like a microphone.
            wait = first_wall + chunk.size / self.samplerate - time.perf_counter()
            if wait > 0 and self._halt.wait(wait):
                break
            self.q.put((chunk, first_wall))
            pos += chunk.size
        self._ended = True
        self.q.put(END)

    def describe(self) -> str:
        where = "silently" if self.mute else (f"on {self.device_name} "
                                              f"[buffer {self.latency * 1000:.0f} ms]")
        return f"Playing: {self.name} ({self.duration:.1f} s) {where}"

    def stop(self) -> None:
        self._halt.set()
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)


# ---- Recording (only with --record) --------------------------------------------------------

def default_recording_path() -> str:
    return os.path.join("recordings", datetime.now().strftime("rec_%Y-%m-%d_%H-%M-%S.wav"))


class Recorder:
    """Saves the microphone sound to a 16-bit WAV file. Used only when --record is given."""

    def __init__(self, path: str, samplerate: int):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self.samplerate = int(samplerate)
        self._file = sf.SoundFile(self.path, mode="w", samplerate=self.samplerate,
                                  channels=1, subtype="PCM_16")
        self.seconds = 0.0

    def write(self, x: np.ndarray) -> None:
        self._file.write(np.clip(x, -1.0, 1.0))
        self.seconds += x.size / self.samplerate

    def close(self) -> None:
        if not self._file.closed:
            self._file.close()
