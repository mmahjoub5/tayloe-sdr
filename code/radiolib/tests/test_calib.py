import numpy as np
import pytest

from radiolib import OFFSET_HZ, equalize, iq_correct_carrier


def image_db(iq, rate):
    spec = np.abs(np.fft.fft(iq))
    f = np.fft.fftfreq(len(iq), 1 / rate)
    pos = spec[np.argmin(np.abs(f - OFFSET_HZ))]
    neg = spec[np.argmin(np.abs(f + OFFSET_HZ))]
    return 20 * np.log10(neg / pos)


def test_iq_correct_carrier_cancels_image(t, rate):
    s = np.exp(2j * np.pi * OFFSET_HZ * t)
    y = s + 0.1 * np.conj(s)                     # image 20 dB down
    assert image_db(y, rate) > -21
    fixed, _ = iq_correct_carrier(y, rate)
    assert image_db(fixed, rate) < -60


def test_equalize_boost_is_capped(rate):
    x = np.zeros(4096, complex)
    x[0] = 1.0                                   # flat spectrum
    gain = np.abs(np.fft.fft(equalize(x, rate)))
    assert gain[0] == pytest.approx(1.0)
    assert 20 * np.log10(gain.max()) <= 18.0 + 1e-9
