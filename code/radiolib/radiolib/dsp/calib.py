"""Undoing the board's own imperfections: I/Q imbalance and baseband roll-off."""

import numpy as np

from ..hardware import BASEBAND_FC_EQ, OFFSET_HZ


def iq_correct(iq):
    """Correct gain and phase imbalance between the I and Q paths.

    A Tayloe with mismatched sampling capacitors produces an image of every
    signal at the mirror frequency. Measured here at only 17-22 dB down, and
    with the carrier parked at +3 kHz its image lands at -3 kHz -- inside the
    channel, where no filter can reach it.

    Gram-Schmidt orthogonalisation: force Q to have the same power as I and to
    be uncorrelated with it. For a signal whose I and Q are independent -- true
    of noise and of anything not already an image -- that is exactly the
    condition the mixer should have produced.

        alpha = <I*Q> / <I*I>        how much of I has leaked into Q
        Q'    = Q - alpha*I          remove it
        Q''   = Q' * sqrt(<I*I>/<Q'*Q'>)   equalise the gain

    Returns (corrected, gain_db, phase_deg) so the correction applied can be
    reported rather than silently assumed.
    """
    i = np.real(iq).astype(np.float64)
    q = np.imag(iq).astype(np.float64)
    i = i - i.mean()
    q = q - q.mean()

    pi = np.mean(i * i)
    if pi <= 0:
        return iq, 0.0, 0.0

    alpha = np.mean(i * q) / pi          # correlation = phase error
    q = q - alpha * i

    pq = np.mean(q * q)
    if pq <= 0:
        return iq, 0.0, 0.0
    beta = np.sqrt(pi / pq)              # amplitude ratio = gain error
    q = q * beta

    return (i + 1j * q,
            float(20 * np.log10(max(beta, 1e-12))),
            float(np.degrees(np.arcsin(np.clip(alpha, -1, 1)))))


def iq_correct_carrier(iq, rate, offset=OFFSET_HZ, width=300.0):
    """Cancel the I/Q image, estimating the imbalance from the carrier.

    An imbalanced mixer delivers  y = a*s + b*conj(s), so every signal appears
    mirrored at -f, at |b/a| relative. Subtracting c*conj(y) with c = b/a*
    cancels it.

    Estimated from the carrier bin rather than whole-band statistics, which is
    where `iq_correct()` fails: the band is dominated by noise added AFTER the
    mixer, independently per channel. That noise is already balanced, so it
    dilutes a whole-band estimate toward zero -- measured 0.01 dB of gain error
    on a signal whose image was only 22 dB down.

    At the carrier the SNR is 20+ dB, so the estimate is dominated by the
    thing we are actually trying to correct.

    Returns (corrected, leakage_db).
    """
    spec = np.fft.fft(iq)
    freqs = np.fft.fftfreq(len(iq), 1 / rate)

    pos = np.abs(freqs - offset) < width
    neg = np.abs(freqs + offset) < width
    if not pos.any() or not neg.any():
        return iq, 0.0

    kp = np.argmax(np.where(pos, np.abs(spec), 0))
    kn = np.argmax(np.where(neg, np.abs(spec), 0))
    if abs(spec[kp]) <= 0:
        return iq, 0.0

    c = spec[kn] / np.conj(spec[kp])
    return iq - c * np.conj(iq), float(20 * np.log10(max(abs(c), 1e-12)))


def equalize(iq, rate, fc=BASEBAND_FC_EQ, max_boost_db=18.0):
    """Undo the analog baseband roll-off.

    The difference amps measure as a single pole at about 2.7 kHz (carrier
    level falls 3.6 dB at 3 kHz, 9.6 at 8 kHz, 16.4 at 19 kHz -- a first-order
    fit within 0.7 dB across the range). That costs treble, and asymmetrically:
    with the carrier at +3 kHz the upper sideband sits further up the slope
    than the lower one, which is audible as muffled and slightly hollow.

    Applied to the RAW baseband, before any frequency shift, because that is
    where the analog filter acted.

    The boost is capped: an exact inverse would lift 20 kHz by 18 dB, and
    there is nothing up there but noise.
    """
    spec = np.fft.fft(iq)
    f = np.fft.fftfreq(len(iq), 1 / rate)
    boost = np.minimum(np.sqrt(1 + (f / fc) ** 2), 10 ** (max_boost_db / 20))
    return np.fft.ifft(spec * boost)
