"""A whole session's measurements, kept for review. Numbers only: never any sound.

The live views keep just the last few seconds. Session keeps everything, so that during or after
a role-play you can:
  - summarise any stretch against the speaker's baseline, in plain words about the voice;
  - find the stretches where a signal stayed clearly away from the baseline ("what changed");
  - mark moments and add notes;
  - save it to a .tonevis file (numbers only) and open it again later.

The wording describes the voice (higher, faster, quieter, more pressed). It never names a
feeling: what a change means is for the person reading it to decide.

Timeline (the few seconds a live view draws) lives here too, so none of this needs Qt.
"""

from __future__ import annotations

import json
import math
import re
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass
from datetime import datetime

import numpy as np

from . import __version__
from . import config as C
from .baseline import BaselineStats

NAN = float("nan")
_COLUMNS = ("t", "f0", "loud", "sound", "pause_since", "tilt", "rate", "tilt_low", "tilt_high")


class Timeline:
    """Everything one view draws: frames, syllables and pauses, oldest first."""

    def __init__(self) -> None:
        self.t: list[float] = []
        self.f0: list[float] = []
        self.loud: list[float] = []
        self.pause_since: list[float] = []
        self.tilt: list[float] = []
        self.rate: list[float] = []
        self.nuclei: list[float] = []
        self.pauses: list[tuple[float, float]] = []

    @classmethod
    def from_recording(cls, rec) -> "Timeline":
        tl = cls()
        for pf in rec.frames:
            tl.add_frame(pf)
        for ev in rec.events:
            tl.add_event(ev)
        return tl

    def add_frame(self, pf, offset: float = 0.0) -> None:
        self.t.append(pf.t + offset)
        self.f0.append(pf.f0)
        self.loud.append(pf.loud_db)
        self.pause_since.append(pf.pause_since + offset)
        self.tilt.append(pf.tilt_db)
        self.rate.append(pf.rate)

    def add_event(self, ev, offset: float = 0.0) -> None:
        if ev[0] == "nucleus":
            self.nuclei.append(ev[1] + offset)
        elif ev[0] == "pause":
            self.pauses.append((ev[1] + offset, ev[2] + offset))

    def trim(self, before: float) -> None:
        k = bisect_left(self.t, before)
        if k:
            for column in (self.t, self.f0, self.loud, self.pause_since, self.tilt, self.rate):
                del column[:k]
        k = bisect_left(self.nuclei, before)
        if k:
            del self.nuclei[:k]
        if self.pauses and self.pauses[0][1] < before:
            self.pauses = [p for p in self.pauses if p[1] >= before]

    def latest(self, now: float) -> int:
        """Index of the newest frame at or before `now`, or -1."""
        return bisect_right(self.t, now) - 1


@dataclass
class Marker:
    t: float
    note: str = ""


@dataclass
class Summary:
    """One stretch of a session, measured against the speaker's baseline."""
    start: float
    end: float
    speech_seconds: float
    syllables: int
    pitch_st: float          # median pitch, semitones from the usual middle
    spread_st: float         # pitch movement: 10th to 90th percentile, in semitones
    loud_db: float           # median loudness of the voiced sound, dB from the usual
    pace: float              # syllables per second of speaking, as a multiple of the usual
    tilt_db: float           # voice quality: spectral tilt of the stretch, dB from the usual
    long_pauses: int         # pauses of 1 s or more that start in the stretch
    longest_pause: float
    pause_seconds: float     # time spent in pauses (0.25 s or more)

    def phrases(self, base: BaselineStats, numbers: bool = True) -> list[str]:
        """Plain words about how the voice differs from the usual. Never about feelings.
        With numbers=False the measurements in brackets are left out."""
        def n(text: str) -> str:
            return f" ({text})" if numbers else ""
        out = []
        if self.speech_seconds < C.EVIDENCE_MIN_SPEECH:
            out.append("too little speech here to compare")
        else:
            p = self.pitch_st
            if p >= C.EVIDENCE_PITCH_ST:
                out.append("pitch higher than usual" + n(f"+{p:.1f} semitones"))
            elif p <= -C.EVIDENCE_PITCH_ST:
                out.append("pitch lower than usual" + n(f"{p:.1f} semitones"))
            usual = base.band_high_st - base.band_low_st
            if usual > 0 and math.isfinite(self.spread_st):
                ratio = self.spread_st / usual
                if ratio >= C.EVIDENCE_SPREAD_RATIO[1]:
                    out.append("more up-and-down than usual")
                elif ratio <= C.EVIDENCE_SPREAD_RATIO[0]:
                    out.append("flatter than usual")
            if self.loud_db >= C.EVIDENCE_LOUDNESS_DB:
                out.append("louder than usual" + n(f"+{self.loud_db:.0f} dB"))
            elif self.loud_db <= -C.EVIDENCE_LOUDNESS_DB:
                out.append("quieter than usual" + n(f"{self.loud_db:.0f} dB"))
            if self.pace >= C.EVIDENCE_PACE_RATIO[1]:
                out.append("faster than usual" + n(f"×{self.pace:.2f}"))
            elif self.pace <= C.EVIDENCE_PACE_RATIO[0]:
                out.append("slower than usual" + n(f"×{self.pace:.2f}"))
            if self.tilt_db >= C.EVIDENCE_TILT_DB:
                out.append("voice more pressed than usual"
                           + n(f"+{self.tilt_db:.1f} dB upper harmonics"))
            elif self.tilt_db <= -C.EVIDENCE_TILT_DB:
                out.append("voice softer or breathier than usual"
                           + n(f"{self.tilt_db:.1f} dB upper harmonics"))
            if not out:
                out.append("voice much as usual")
        if self.long_pauses:
            s = "s" if self.long_pauses > 1 else ""
            out.append(f"{self.long_pauses} pause{s} of 1 s or more"
                       + n(f"longest {self.longest_pause:.1f} s"))
        return out

    def sentence(self, base: BaselineStats, numbers: bool = True) -> str:
        text = "; ".join(self.phrases(base, numbers))
        return text[:1].upper() + text[1:] + "."


@dataclass
class Change:
    """A stretch where one signal stayed clearly away from the baseline."""
    start: float
    end: float
    signal: str       # "pitch", "loudness", "pace", "voice quality" or "pause"
    direction: int    # +1 above the usual, -1 below
    text: str

    def words(self, numbers: bool = True) -> str:
        """The description, with or without the measurements in brackets."""
        if numbers:
            return self.text
        if self.signal == "pause":
            return "Long pause"
        return re.sub(r"\s*\([^)]*\)", "", self.text)


def speaking_mask(sound: np.ndarray) -> np.ndarray:
    """Frames that count as speaking time: sound, plus the short silences inside speech
    (consonants). Silence before the first sound, after the last, and pauses do not count."""
    s = np.asarray(sound, dtype=bool).copy()
    n = s.size
    if n == 0:
        return s
    padded = np.concatenate(([True], s, [True]))
    starts = np.flatnonzero(~padded[1:-1] & padded[:-2])
    ends = np.flatnonzero(~padded[1:-1] & padded[2:]) + 1
    for a, b in zip(starts, ends):
        if a > 0 and b < n and (b - a) * C.FRAME_STEP < C.PAUSE_MIN - 1e-9:
            s[a:b] = True
    return s


def _pooled_tilt(low_sum, high_sum, base_tilt: float):
    """Spectral tilt of pooled energies, in dB from the baseline (NaN where empty)."""
    low_sum, high_sum = np.asarray(low_sum, float), np.asarray(high_sum, float)
    ok = (low_sum > 0) & (high_sum > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(ok, 10.0 * np.log10(np.where(ok, high_sum, 1.0) / np.where(ok, low_sum, 1.0))
                        - base_tilt, np.nan)


class Session:
    def __init__(self) -> None:
        self._cols: dict[str, list] = {name: [] for name in _COLUMNS}
        self.nuclei: list[float] = []
        self.pauses: list[tuple[float, float]] = []
        self.markers: list[Marker] = []
        self.baseline: BaselineStats | None = None
        self.baseline_set_at: float | None = None
        self.sources: list[str] = []
        self.created = datetime.now()
        self._cache: dict | None = None

    # ---- building ---------------------------------------------------------------------------

    def add_frame(self, pf, offset: float = 0.0) -> None:
        cols = self._cols
        cols["t"].append(pf.t + offset)
        cols["f0"].append(pf.f0)
        cols["loud"].append(pf.loud_db)
        cols["sound"].append(bool(pf.sound))
        cols["pause_since"].append(pf.pause_since + offset)
        cols["tilt"].append(pf.tilt_db)
        cols["rate"].append(pf.rate)
        cols["tilt_low"].append(pf.tilt_low)
        cols["tilt_high"].append(pf.tilt_high)
        self._cache = None

    def add_event(self, ev, offset: float = 0.0) -> None:
        if ev[0] == "nucleus":
            self.nuclei.append(ev[1] + offset)
        elif ev[0] == "pause":
            self.pauses.append((ev[1] + offset, ev[2] + offset))
        elif ev[0] == "calibrated":
            self.set_baseline(ev[1], self.end_time)

    def set_baseline(self, stats: BaselineStats | None, at: float | None = None) -> None:
        self.baseline = stats
        self.baseline_set_at = at

    def add_marker(self, t: float, note: str = "") -> Marker:
        marker = Marker(float(t), note)
        self.markers.append(marker)
        self.markers.sort(key=lambda m: m.t)
        return marker

    @classmethod
    def from_recording(cls, rec, name: str = "") -> "Session":
        session = cls()
        for pf in rec.frames:
            session.add_frame(pf)
        for ev in rec.events:
            if ev[0] != "calibrated":
                session.add_event(ev)
        session.set_baseline(rec.stats, 0.0 if rec.stats is not None else None)
        session.sources.append(name or rec.name)
        return session

    # ---- reading ----------------------------------------------------------------------------

    @property
    def end_time(self) -> float:
        return self._cols["t"][-1] if self._cols["t"] else 0.0

    @property
    def frame_count(self) -> int:
        return len(self._cols["t"])

    def arrays(self) -> dict[str, np.ndarray]:
        """All frames as numpy arrays (cached until the next frame arrives)."""
        if self._cache is None:
            self._cache = {name: np.asarray(values, dtype=bool if name == "sound" else float)
                           for name, values in self._cols.items()}
        return self._cache

    def recent(self, seconds: float, now: float) -> dict[str, np.ndarray]:
        """Just the frames of the last `seconds` before `now` (cheap: for live views)."""
        t = self._cols["t"]
        lo, hi = bisect_left(t, now - seconds), bisect_right(t, now)
        return {name: np.asarray(values[lo:hi], dtype=bool if name == "sound" else float)
                for name, values in self._cols.items()}

    def timeline(self, start: float, end: float) -> Timeline:
        """A Timeline of one stretch, with times starting from 0, for a view drawn whole."""
        tl = Timeline()
        t = self._cols["t"]
        lo, hi = bisect_left(t, start), bisect_right(t, end)
        for k in range(lo, hi):
            tl.t.append(t[k] - start)
            tl.f0.append(self._cols["f0"][k])
            tl.loud.append(self._cols["loud"][k])
            tl.pause_since.append(self._cols["pause_since"][k] - start)
            tl.tilt.append(self._cols["tilt"][k])
            tl.rate.append(self._cols["rate"][k])
        tl.nuclei = [n - start for n in self.nuclei if start <= n <= end]
        tl.pauses = [(max(s, start) - start, min(e, end) - start)
                     for s, e in self.pauses if e > start and s < end]
        return tl

    # ---- evidence ---------------------------------------------------------------------------

    def summarise(self, start: float, end: float) -> Summary | None:
        """Measure one stretch against the baseline. None if there is no baseline yet."""
        base = self.baseline
        if base is None:
            return None
        a = self.arrays()
        lo, hi = np.searchsorted(a["t"], [start, end])
        f0, loud = a["f0"][lo:hi], a["loud"][lo:hi]
        low, high = a["tilt_low"][lo:hi], a["tilt_high"][lo:hi]
        voiced = ~np.isnan(f0)
        speaking = speaking_mask(a["sound"][lo:hi])
        speech_seconds = float(speaking.sum()) * C.FRAME_STEP
        st = 12.0 * np.log2(f0[voiced] / base.pitch_hz)
        syllables = bisect_right(self.nuclei, end) - bisect_left(self.nuclei, start)
        pace = NAN
        if speech_seconds >= C.EVIDENCE_MIN_SPEECH and math.isfinite(base.rate) and syllables >= 3:
            pace = syllables / speech_seconds / base.rate
        has_tilt = ~np.isnan(low) & ~np.isnan(high)
        tilt = NAN
        if has_tilt.sum() >= 10 and math.isfinite(base.tilt_db):
            tilt = float(_pooled_tilt(low[has_tilt].sum(), high[has_tilt].sum(), base.tilt_db))
        in_range = [(max(s, start), min(e, end)) for s, e in self.pauses if e > start and s < end]
        starting = [e - s for s, e in self.pauses if start <= s < end]
        long_pauses = [d for d in starting if d >= C.LONG_PAUSE - 1e-6]
        return Summary(
            start=start, end=end, speech_seconds=speech_seconds, syllables=syllables,
            pitch_st=float(np.median(st)) if st.size >= 10 else NAN,
            spread_st=float(np.percentile(st, 90) - np.percentile(st, 10)) if st.size >= 10 else NAN,
            loud_db=float(np.median(loud[voiced]) - base.level_db) if voiced.sum() >= 10 else NAN,
            pace=pace, tilt_db=tilt,
            long_pauses=len(long_pauses),
            longest_pause=max(long_pauses, default=0.0),
            pause_seconds=float(sum(e - s for s, e in in_range)))

    def binned(self, bin_seconds: float, start: float = 0.0, end: float | None = None) -> dict:
        """Each signal per time bin, against the baseline: for the whole-session map and for
        finding changes. Means per bin (NaN where a bin has too little voice): pitch_st,
        loud_db, tilt_db, pace_log2, pause_fraction; and the raw sums behind them."""
        base = self.baseline
        a = self.arrays()
        end = self.end_time if end is None else end
        n = max(0, int(math.ceil((end - start) / bin_seconds - 1e-9)))
        keys = ("pitch_st", "loud_db", "pace_log2", "tilt_db", "pause_fraction", "speech_seconds",
                "syllables", "pitch_sum", "voiced", "loud_sum", "low_sum", "high_sum")
        out = {"start": start, "bin": bin_seconds}
        if n == 0 or base is None or a["t"].size == 0:
            out.update({key: np.full(n, np.nan) for key in keys})
            return out
        lo, hi = np.searchsorted(a["t"], [start, end])
        t = a["t"][lo:hi]
        idx = np.clip(((t - start) / bin_seconds).astype(int), 0, n - 1)
        f0, loud = a["f0"][lo:hi], a["loud"][lo:hi]
        voiced = ~np.isnan(f0)
        min_frames = max(5, int(0.1 * bin_seconds / C.FRAME_STEP))

        def total(values, mask):
            return np.bincount(idx[mask], weights=values[mask], minlength=n)

        st = np.clip(12.0 * np.log2(np.where(voiced, f0, base.pitch_hz) / base.pitch_hz), -12, 12)
        out["voiced"] = np.bincount(idx[voiced], minlength=n).astype(float)
        out["pitch_sum"] = total(st, voiced)
        out["loud_sum"] = total(loud - base.level_db, voiced)
        enough = out["voiced"] >= min_frames
        with np.errstate(invalid="ignore", divide="ignore"):
            out["pitch_st"] = np.where(enough, out["pitch_sum"] / np.maximum(out["voiced"], 1), np.nan)
            out["loud_db"] = np.where(enough, out["loud_sum"] / np.maximum(out["voiced"], 1), np.nan)
        low, high = a["tilt_low"][lo:hi], a["tilt_high"][lo:hi]
        has_tilt = ~np.isnan(low) & ~np.isnan(high)
        out["low_sum"] = total(low, has_tilt)
        out["high_sum"] = total(high, has_tilt)
        tilt_frames = np.bincount(idx[has_tilt], minlength=n)
        out["tilt_db"] = (np.where(tilt_frames >= min_frames,
                                   _pooled_tilt(out["low_sum"], out["high_sum"], base.tilt_db), np.nan)
                          if math.isfinite(base.tilt_db) else np.full(n, np.nan))
        in_pause = ~np.isnan(a["pause_since"][lo:hi])
        frames = np.maximum(np.bincount(idx, minlength=n), 1)
        out["pause_fraction"] = np.bincount(idx[in_pause], minlength=n) / frames
        speaking = speaking_mask(a["sound"][lo:hi])
        out["speech_seconds"] = np.bincount(idx[speaking], minlength=n) * C.FRAME_STEP
        nuclei = np.asarray(self.nuclei)
        nuclei = nuclei[(nuclei >= start) & (nuclei < end)]
        out["syllables"] = np.bincount(np.clip(((nuclei - start) / bin_seconds).astype(int),
                                               0, n - 1), minlength=n).astype(float)
        if math.isfinite(base.rate):
            with np.errstate(invalid="ignore", divide="ignore"):
                rate = out["syllables"] / out["speech_seconds"] / base.rate
            ok = (out["speech_seconds"] >= 0.5 * bin_seconds) & (out["syllables"] >= 2)
            out["pace_log2"] = np.where(ok, np.log2(np.where(ok, rate, 1.0)), np.nan)
        else:
            out["pace_log2"] = np.full(n, np.nan)
        return out

    def find_changes(self) -> list[Change]:
        """Stretches where one signal stayed clearly away from the usual.

        Every CHANGE_STEP seconds it looks at the last CHANGE_SPEECH seconds of *speaking*
        (reaching back at most CHANGE_MAX_SPAN), so hesitant speech with long pauses is judged
        on enough voice. A change is reported when CHANGE_MIN_WINDOWS windows in a row agree.
        Every pause of CHANGE_LONG_PAUSE seconds or more is listed as well."""
        base = self.baseline
        changes: list[Change] = []
        if base is None or self.frame_count == 0:
            return changes
        b = self.binned(C.CHANGE_STEP)
        n = b["speech_seconds"].size
        if n:
            ends = np.arange(1, n + 1)                       # window = bins [first, end)
            speech = np.concatenate(([0.0], np.cumsum(b["speech_seconds"])))
            max_back = int(round(C.CHANGE_MAX_SPAN / C.CHANGE_STEP))

            def firsts(seconds):
                """For each window end, the latest start giving `seconds` of speech."""
                first = np.searchsorted(speech, speech[ends] - seconds, side="right") - 1
                return np.maximum(np.maximum(first, 0), ends - max_back)

            def window(values, first):
                c = np.concatenate(([0.0], np.cumsum(np.nan_to_num(values))))
                return c[ends] - c[first]

            short, long = firsts(C.CHANGE_SPEECH), firsts(C.CHANGE_SPEECH_PACE)
            spoken_short, spoken_long = speech[ends] - speech[short], speech[ends] - speech[long]
            voiced = window(b["voiced"], short)
            with np.errstate(invalid="ignore", divide="ignore"):
                pitch = np.where(voiced >= 20, window(b["pitch_sum"], short) / voiced, np.nan)
                loud = np.where(voiced >= 20, window(b["loud_sum"], short) / voiced, np.nan)
                syll = window(b["syllables"], long)
                pace = (np.where(syll >= 3, syll / spoken_long, np.nan) / base.rate
                        if math.isfinite(base.rate) else np.full(n, np.nan))
            tilt = (_pooled_tilt(window(b["low_sum"], short), window(b["high_sum"], short),
                                 base.tilt_db)
                    if math.isfinite(base.tilt_db) else np.full(n, np.nan))
            # (window values, upper and lower thresholds, the same signal per 1 s bin and the
            #  deviation a bin needs to count as part of the change -- pace per bin is too noisy
            #  -- and which windows were used)
            signals = {
                "pitch": (pitch, C.EVIDENCE_PITCH_ST, -C.EVIDENCE_PITCH_ST,
                          b["pitch_st"], C.EVIDENCE_PITCH_ST / 2, short, spoken_short),
                "loudness": (loud, C.EVIDENCE_LOUDNESS_DB, -C.EVIDENCE_LOUDNESS_DB,
                             b["loud_db"], C.EVIDENCE_LOUDNESS_DB / 2, short, spoken_short),
                "pace": (pace, C.EVIDENCE_PACE_RATIO[1], C.EVIDENCE_PACE_RATIO[0], None, 0.0,
                         long, spoken_long),
                "voice quality": (tilt, C.EVIDENCE_TILT_DB, -C.EVIDENCE_TILT_DB,
                                  b["tilt_db"], C.EVIDENCE_TILT_DB / 2, short, spoken_short),
            }
            for name, (values, high, low, per_bin, margin, first, spoken) in signals.items():
                enough = spoken >= C.EVIDENCE_MIN_SPEECH
                flags = np.where(enough & (values >= high), 1,
                                 np.where(enough & (values <= low), -1, 0))
                changes += self._episodes(name, flags, first, ends, per_bin, margin)
        for s, e in self.pauses:
            if e - s >= C.CHANGE_LONG_PAUSE - 1e-6:
                changes.append(Change(s, e, "pause", 1, f"Pause of {e - s:.1f} s"))
        changes.sort(key=lambda c: (c.start, c.signal))
        return changes

    def _episodes(self, name: str, flags: np.ndarray, first: np.ndarray, ends: np.ndarray,
                  per_bin, bin_margin: float) -> list[Change]:
        """Turn runs of agreeing windows into reported changes. Each run is split at long
        pauses, narrowed to the bins that really deviate that way (the windows look back several
        seconds, which would otherwise smear a change backwards), trimmed to the speech, and
        confirmed by a summary of exactly that stretch."""
        out = []
        step = C.CHANGE_STEP
        i = 0
        while i < flags.size:
            if flags[i] == 0:
                i += 1
                continue
            j = i
            while j + 1 < flags.size and flags[j + 1] == flags[i]:
                j += 1
            direction = int(flags[i])
            if j - i + 1 >= C.CHANGE_MIN_WINDOWS:
                for start, end in self._split_at_long_pauses(first[i] * step, ends[j] * step):
                    if per_bin is not None:
                        lo = int(start / step)
                        values = np.asarray(per_bin[lo:int(math.ceil(end / step))], dtype=float)
                        with np.errstate(invalid="ignore"):
                            hits = np.flatnonzero(direction * values >= bin_margin)
                        if hits.size == 0:
                            continue
                        start, end = (lo + hits[0]) * step, (lo + hits[-1] + 1) * step
                    start, end = self._trim_to_speech(start, end)
                    summary = self.summarise(start, end)
                    if summary is None or summary.speech_seconds < C.EVIDENCE_MIN_SPEECH:
                        continue
                    phrase = next((p for p in summary.phrases(self.baseline)
                                   if _about(p, name, direction)), None)
                    if phrase:
                        out.append(Change(start, end, name, direction,
                                          phrase[:1].upper() + phrase[1:]))
            i = j + 1
        return out

    def _split_at_long_pauses(self, start: float, end: float) -> list[tuple[float, float]]:
        cuts = sorted((s, e) for s, e in self.pauses
                      if e - s >= C.CHANGE_LONG_PAUSE - 1e-6 and s > start and e < end)
        spans, a = [], start
        for s, e in cuts:
            spans.append((a, s))
            a = e
        spans.append((a, end))
        return [(a, b) for a, b in spans if b - a > 0]

    def _trim_to_speech(self, start: float, end: float) -> tuple[float, float]:
        """Shrink a stretch to its first and last moments of speech."""
        a = self.arrays()
        lo, hi = np.searchsorted(a["t"], [start, end])
        speaking = np.flatnonzero(a["sound"][lo:hi])
        if speaking.size == 0:
            return start, min(end, self.end_time)
        return float(a["t"][lo + speaking[0]]), float(a["t"][lo + speaking[-1]])

    # ---- files ------------------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save as a .tonevis file: the measurements, marks and baseline. No sound at all."""
        a = self.arrays()
        meta = {"format": "tonevis-session", "version": 1, "app": __version__,
                "saved": datetime.now().isoformat(timespec="seconds"),
                "created": self.created.isoformat(timespec="seconds"),
                "note": "Measurements only. This file contains no sound.",
                "markers": [asdict(m) for m in self.markers],
                "baseline": json.loads(self.baseline.to_json()) if self.baseline else None,
                "baseline_set_at": self.baseline_set_at, "sources": self.sources}
        with open(path, "wb") as f:   # a file object stops numpy from adding ".npz"
            np.savez_compressed(
                f, **{name: a[name] for name in _COLUMNS},
                nuclei=np.asarray(self.nuclei, dtype=float),
                pauses=np.asarray(self.pauses, dtype=float).reshape(-1, 2),
                meta=np.array(json.dumps(meta)))

    @classmethod
    def load(cls, path: str) -> "Session":
        try:
            with np.load(path, allow_pickle=False) as z:
                meta = json.loads(str(z["meta"]))
                if meta.get("format") != "tonevis-session":
                    raise ValueError("not a tone visualiser session file")
                session = cls()
                n = z["t"].size
                for name in _COLUMNS:
                    session._cols[name] = (z[name].tolist() if name in z.files
                                           else [NAN] * n)
                session.nuclei = z["nuclei"].tolist()
                session.pauses = [tuple(p) for p in z["pauses"].tolist()]
        except (OSError, KeyError, ValueError) as exc:
            raise ValueError(f"Could not open {path}: {exc}") from exc
        session.markers = [Marker(float(m["t"]), str(m.get("note", "")))
                           for m in meta.get("markers", [])]
        if meta.get("baseline"):
            session.baseline = BaselineStats.from_json(json.dumps(meta["baseline"]))
        session.baseline_set_at = meta.get("baseline_set_at")
        session.sources = list(meta.get("sources", []))
        try:
            session.created = datetime.fromisoformat(meta.get("created", ""))
        except ValueError:
            pass
        return session

    def report(self, numbers: bool = True) -> str:
        """A plain-text summary of the whole session, for supervision notes."""
        lines = ["Tone visualiser session",
                 f"Recorded {self.created:%d %b %Y %H:%M}, length {clock(self.end_time)}.",
                 "Shows vocal features only. Interpretation is yours.", ""]
        if self.baseline is None:
            lines.append("No baseline yet, so nothing can be compared.")
            return "\n".join(lines)
        lines.append("Baseline: " + (self.baseline.describe() if numbers
                                     else describe_plainly(self.baseline)) + ".")
        whole = self.summarise(0.0, self.end_time)
        if whole:
            lines += ["", "Whole session: " + whole.sentence(self.baseline, numbers)]
        changes = self.find_changes()
        lines += ["", "What changed:" if changes else "What changed: nothing held for long "
                  "enough to report."]
        lines += [f"  {clock(c.start)}-{clock(c.end)}  {c.words(numbers)}" for c in changes]
        if self.markers:
            lines += ["", "Marks:"]
            for m in self.markers:
                summary = self.summarise(max(0.0, m.t - 10.0), m.t + 10.0)
                lines.append(f"  {clock(m.t)}  {m.note or '(no note)'}"
                             + (f"  | around it: {summary.sentence(self.baseline, numbers)}"
                                if summary else ""))
        return "\n".join(lines)


def describe_plainly(stats: BaselineStats) -> str:
    """What a baseline holds, without its numbers."""
    return (f"their middle pitch, usual pitch range, typical loudness, pace and voice quality, "
            f"learned from {stats.speech_seconds:.0f} s of speech")


def _about(phrase: str, signal: str, direction: int) -> bool:
    """Is this summary phrase about `signal`, in `direction`?"""
    keys = {("pitch", 1): "pitch higher", ("pitch", -1): "pitch lower",
            ("loudness", 1): "louder", ("loudness", -1): "quieter",
            ("pace", 1): "faster", ("pace", -1): "slower",
            ("voice quality", 1): "voice more pressed", ("voice quality", -1): "voice softer"}
    return phrase.startswith(keys[(signal, direction)])


def clock(seconds: float) -> str:
    """Seconds -> m:ss (or h:mm:ss)."""
    seconds = max(0, int(round(seconds)))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
