"""--record saves exactly what the microphone delivered (tested with synthetic blocks)."""

import queue

import numpy as np
import pytest
import soundfile as sf

from tonevis.audio import Recorder
from tonevis.tracker import AnalysisWorker

RATE = 48_000


def test_recording_matches_the_input_and_analysis_still_runs(tmp_path):
    t = np.arange(RATE) / RATE
    x = (0.5 * np.sin(2 * np.pi * 150 * t)).astype(np.float32)
    x[1000:1010] = 1.7                                    # a few samples beyond full scale
    path = tmp_path / "take.wav"
    recorder = Recorder(str(path), RATE)
    q = queue.SimpleQueue()
    worker = AnalysisWorker(q, RATE, live=True, recorder=recorder)
    worker.start()
    for i in range(0, x.size, 480):
        q.put((x[i:i + 480], 100.0 + i / RATE))
    worker.finish()
    worker.join(timeout=10)
    recorder.close()

    y, rate = sf.read(str(path), dtype="float32")
    assert rate == RATE
    assert y.size == x.size
    expected = np.clip(x, -1.0, 1.0)                    # clipped, never wrapped around
    assert np.max(np.abs(y - expected)) < 1e-4          # 16-bit rounding only
    assert recorder.seconds == pytest.approx(1.0)
    f0 = np.array([fr.f0 for fr, _ in worker.frames])
    assert np.nanmedian(f0) == pytest.approx(150.0, rel=0.01)
