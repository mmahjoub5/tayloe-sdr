"""Turning one channel of complex baseband into audio."""

import numpy as np
from scipy.signal import butter, firwin, lfilter, sosfiltfilt

from ..hardware import OFFSET_HZ
from .calib import equalize, iq_correct_carrier
from .channel import channel_filter


def sideband_filter(iq, rate, upper=True, lo=300.0, hi=2700.0):
    """Keep one sideband of a carrier-at-DC signal, rejecting the other.

    SSB demodulation is "take the real part", but real() folds negative
    frequencies onto positive ones -- so whatever sits on the unwanted side
    lands on top of the audio. A symmetric channel filter leaves it there,
    costing about 3 dB of noise and any interference on that side.

    A complex bandpass fixes it: design a real lowpass at half the sideband
    width, then modulate it up to the sideband's centre. The result passes
    +lo..+hi and rejects -hi..-lo, so real() has nothing to fold in.
    """
    half = (hi - lo) / 2.0
    centre = (hi + lo) / 2.0
    if not upper:
        centre = -centre

    taps = firwin(255, half / (rate / 2))
    n = np.arange(len(taps))
    taps = taps * np.exp(2j * np.pi * centre * n / rate)

    out = lfilter(taps, 1.0, iq)
    return out[len(taps) // 2:]          # strip the filter's group delay


def demod(iq, rate, mode="am", side=1.0, bw=5000.0,
          audio_band=(200, 3000), offset=OFFSET_HZ, eq=False,
          correct_iq=False):
    """Demodulate one channel of complex baseband.

    mode "am"  envelope detection -- simple, and fine on a strong station
    mode "sam" synchronous detection -- worth about 3 dB on a weak one
    mode "usb"/"lsb" single sideband

    bw narrows the channel filter; audio_band narrows the output. Both trade
    top-end audio for noise, which is the right trade on a marginal signal.
    offset must match what the board was tuned with, or the channel filter
    centres on the wrong place and removes the station instead of the noise.
    """
    # Strip the board's DC offset first. Envelope detection is shift-invariant
    # in theory, but a DC term beats against an offset carrier and lands a tone
    # at exactly the tuning offset -- loud enough to bury the programme audio.
    iq = iq - iq.mean()
    if correct_iq:
        iq, _ = iq_correct_carrier(iq, rate, offset)
    if eq:
        iq = equalize(iq, rate)
    iq = channel_filter(iq, rate, side, offset=offset, bw=bw)

    if mode == "sam":
        # Synchronous AM. channel_filter leaves the carrier at DC, so it can
        # serve as its own phase reference: low-pass to recover the carrier
        # phasor, rotate the signal onto the real axis, keep the real part.
        #
        # All the noise in the quadrature component is discarded rather than
        # rectified into the audio, and there is no threshold effect -- so it
        # degrades gracefully where envelope detection falls apart. On a strong
        # station the two sound the same; on a marginal one this is the winner.
        sos = butter(2, 30, btype="low", fs=rate, output="sos")
        carrier = sosfiltfilt(sos, iq.real) + 1j * sosfiltfilt(sos, iq.imag)
        ref = carrier / np.maximum(np.abs(carrier), 1e-12)
        audio = np.real(iq * np.conj(ref))
        audio -= audio.mean()
    elif mode == "am":
        audio = np.abs(iq)
        audio -= audio.mean()          # strip the carrier's DC term
    elif mode in ("usb", "lsb"):
        # Reject the unwanted sideband BEFORE real() folds it in.
        audio = np.real(sideband_filter(iq, rate, upper=(mode == "usb"),
                                        lo=audio_band[0], hi=audio_band[1]))
    else:
        raise ValueError(f"unknown mode {mode}")

    # Communications bandpass, not just a lowpass: AM carries a lot of hum and
    # rumble down low, loud enough on this board to bury the speech entirely.
    sos = butter(4, list(audio_band), btype="band", fs=rate, output="sos")
    return sosfiltfilt(sos, audio)
