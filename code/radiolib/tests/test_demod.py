import numpy as np
import pytest

from radiolib import OFFSET_HZ, channel_filter, demod, sideband_filter
from conftest import am_signal, tone_level_db


@pytest.mark.parametrize("mode", ["am", "sam"])
def test_am_recovers_message(mode, t, rate):
    audio = demod(am_signal(t), rate, mode, side=1.0)
    assert tone_level_db(audio, rate, 1000) - tone_level_db(audio, rate, 2000) > 40


@pytest.mark.parametrize("mode,wanted,unwanted", [("usb", 1000, 1500), ("lsb", 1500, 1000)])
def test_ssb_rejects_other_sideband(mode, wanted, unwanted, t, rate):
    # Dial at +OFFSET_HZ: a USB tone 1 kHz above it, an LSB tone 1.5 kHz below.
    iq = (np.exp(2j * np.pi * (OFFSET_HZ + 1000) * t)
          + np.exp(2j * np.pi * (OFFSET_HZ - 1500) * t))
    audio = demod(iq, rate, mode, side=1.0)
    assert tone_level_db(audio, rate, wanted) - tone_level_db(audio, rate, unwanted) > 50


def test_ssb_wrong_side_loses_the_signal(t, rate):
    # The rx.py bug: SSB has no carrier, so a side guessed from noise can be -1.
    iq = np.exp(2j * np.pi * (OFFSET_HZ + 1000) * t)
    right = tone_level_db(demod(iq, rate, "usb", side=1.0), rate, 1000)
    wrong = tone_level_db(demod(iq, rate, "usb", side=-1.0), rate, 1000)
    assert right - wrong > 40


def test_sideband_filter_compensates_group_delay(rate):
    x = np.zeros(4000, complex)
    x[1000] = 1.0
    out = sideband_filter(x, rate)
    assert abs(int(np.argmax(np.abs(out))) - 1000) <= 1


def test_channel_filter_rejects_neighbour(t, rate):
    wanted = np.exp(2j * np.pi * OFFSET_HZ * t)
    neighbour = np.exp(2j * np.pi * (OFFSET_HZ + 10000 - 24000) * t)   # 10 kHz up, aliased
    out = channel_filter(wanted + neighbour, rate)[2000:-2000]
    # Wanted is now DC; anything left over is the neighbour.
    assert 20 * np.log10(np.std(out) / abs(out.mean())) < -40


def test_unknown_mode_raises(t, rate):
    with pytest.raises(ValueError):
        demod(am_signal(t), rate, "fm")
