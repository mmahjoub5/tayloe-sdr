"""Moving one channel to DC and isolating it."""

import numpy as np
from scipy.signal import butter, sosfiltfilt

from ..hardware import OFFSET_HZ


def channel_filter(iq, rate, side=1.0, offset=OFFSET_HZ, bw=5000.0):
    """Move the wanted carrier to DC and keep only its channel.

    Without this, envelope detection sees every station in the passband at once
    and mixes them into one audio stream -- broadcast channels are only 9-10 kHz
    apart, so a neighbour is never far away.
    """
    t = np.arange(len(iq)) / rate
    shifted = iq * np.exp(-2j * np.pi * (side * offset) * t)

    # Sharp, because the job is rejecting a neighbour 10 kHz away while keeping
    # 5 kHz of audio. sosfiltfilt is real-only, so filter the parts separately.
    sos = butter(10, bw, btype="low", fs=rate, output="sos")
    return sosfiltfilt(sos, shifted.real) + 1j * sosfiltfilt(sos, shifted.imag)
