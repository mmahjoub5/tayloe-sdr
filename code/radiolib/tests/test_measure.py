import numpy as np
import pytest

from radiolib import OFFSET_HZ, carrier_power, spectrum, station_score
from conftest import am_signal


@pytest.mark.parametrize("sign", [+1.0, -1.0])
def test_carrier_power_finds_side(sign, t, rate):
    rng = np.random.default_rng(0)
    iq = np.exp(2j * np.pi * sign * OFFSET_HZ * t) + 0.01 * (
        rng.standard_normal(len(t)) + 1j * rng.standard_normal(len(t)))
    cnr, side = carrier_power(iq, rate)
    assert side == sign
    assert cnr > 30


def test_station_score_prefers_syllabic_modulation(t, rate):
    spur = np.exp(2j * np.pi * OFFSET_HZ * t)
    station = am_signal(t, msg_hz=4.0, depth=0.8)
    assert station_score(station, rate, side=1.0)[0] > 10 * station_score(spur, rate, side=1.0)[0] + 1


def test_spectrum_blanks_dc(rate):
    n = 8192
    t = np.arange(n) / rate
    iq = 5.0 + 0.1 * np.exp(2j * np.pi * 2000 * t)     # huge DC, small tone
    (f0, db0), *_ = spectrum(iq, rate)
    assert abs(f0 - 2000) < 10
