import wave

import numpy as np

from radiolib import write_wav


def test_write_wav_resamples_and_normalises(tmp_path, rate):
    path = tmp_path / "x.wav"
    write_wav(str(path), np.sin(np.arange(rate) / 10), rate)
    with wave.open(str(path)) as w:
        assert w.getframerate() == 48000
        assert w.getnframes() == 48000
        pcm = np.frombuffer(w.readframes(w.getnframes()), "<i2")
    assert abs(np.abs(pcm).max() - int(0.9 * 32767)) <= 2
