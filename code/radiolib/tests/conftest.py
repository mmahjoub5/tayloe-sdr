"""Synthetic baseband shaped like what the board delivers: carrier at +OFFSET_HZ."""

import numpy as np
import pytest

from radiolib import OFFSET_HZ, STREAM_RATE


@pytest.fixture
def rate():
    return STREAM_RATE


@pytest.fixture
def t(rate):
    return np.arange(2 * rate) / rate


def tone_level_db(audio, rate, hz, trim=2000):
    """Peak of `audio`'s spectrum within 5 Hz of `hz`, in dB."""
    a = audio[trim:-trim]
    spec = np.abs(np.fft.rfft(a * np.hanning(len(a))))
    f = np.fft.rfftfreq(len(a), 1 / rate)
    return 20 * np.log10(spec[np.abs(f - hz) < 5].max() + 1e-30)


def am_signal(t, msg_hz=1000.0, depth=0.5, offset=OFFSET_HZ):
    return (1 + depth * np.cos(2 * np.pi * msg_hz * t)) * np.exp(2j * np.pi * offset * t)
