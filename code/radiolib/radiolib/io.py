"""Writing results to disk."""

import wave

import numpy as np
from scipy.signal import resample_poly


def write_wav(path, audio, rate, out_rate=48000):
    if out_rate != rate:
        audio = resample_poly(audio, out_rate, rate)

    peak = np.max(np.abs(audio))
    scaled = np.zeros_like(audio) if peak == 0 else audio / peak * 0.9
    pcm = (scaled * 32767).astype("<i2")

    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(out_rate)
        w.writeframes(pcm.tobytes())
