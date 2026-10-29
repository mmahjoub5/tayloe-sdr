"""Measurements on raw baseband: what is there, and how strong.

None of these change the signal. They report on it -- and are not control
inputs to demodulation, except carrier_power()'s side for AM, where there is a
carrier to find.
"""

import numpy as np

from ..hardware import OFFSET_HZ
from .channel import channel_filter


def carrier_power(iq, rate, offset=OFFSET_HZ, width=400.0, seg_s=0.17):
    """Carrier-to-noise at the tuning offset, and which side it landed on.

    Checks both +offset and -offset: which side a carrier appears on depends on
    the I/Q sense, and guessing wrong makes a real station look like an empty
    channel. Returns (dB, side) where side is +1.0 or -1.0.

    Measured over fixed-duration segments, averaged. Both of those matter for
    comparability:

    - Fixed *duration* (not a fixed sample count) keeps the bin width the same
      at any sample rate, so a 48 kHz capture and a 24 kHz stream of the same
      signal agree. Tying it to the array length instead gave a coherent
      carrier more processing gain in whichever path happened to be longer --
      several dB, on exactly the strong signals we cared about most.
    - Averaging segments rather than taking one long FFT keeps the result
      stable as capture length changes.
    """
    seg = max(256, int(rate * seg_s))
    if len(iq) < seg:
        seg = len(iq)

    nseg = max(1, len(iq) // seg)
    win = np.hanning(seg)
    acc = None
    for i in range(nseg):
        block = iq[i * seg:(i + 1) * seg]
        spec = np.abs(np.fft.fftshift(np.fft.fft(block * win)))
        acc = spec if acc is None else acc + spec
    spec = acc / nseg
    freqs = np.fft.fftshift(np.fft.fftfreq(seg, 1 / rate))

    # Noise reference: everything that is neither the carrier, its image, nor
    # DC. Defined by exclusion rather than as a fixed band above the offset --
    # that assumed a small offset, and left no valid bins at all once the
    # offset moved out past the cap.
    nyq = 0.9 * rate / 2
    noise = ((np.abs(np.abs(freqs) - offset) > 6000)   # clear of carrier+image
             & (np.abs(freqs) > 2000)                  # clear of DC artifacts
             & (np.abs(freqs) < nyq))
    if not noise.any():
        return 0.0, 1.0
    floor = max(np.mean(spec[noise]), 1e-12)

    best, side = -99.0, 1.0
    for sign in (+1.0, -1.0):
        band = np.abs(freqs - sign * offset) < width / 2
        if band.any():
            cnr = 20 * np.log10(np.max(spec[band]) / floor)
            if cnr > best:
                best, side = cnr, sign

    return best, side


def station_score(iq, rate, offset=OFFSET_HZ, side=None):
    """Evidence that a carrier is a broadcast station rather than a spur.

    `carrier_power()` cannot tell them apart: it measures energy in a narrow
    band at the tuning offset, and an unmodulated tone scores perfectly. That
    ranked a comb of internally generated spurs above real stations.

    Three things have to be separated, and no single number does it:

      spur     envelope does not move at all
      noise    envelope moves, but at every rate -- |complex gaussian| has a
               std/mean of about 0.52, so modulation depth alone rates noise
               as highly as speech
      station  envelope moves mostly at syllabic rates, a few Hz

    So the score is depth *and* concentration: how much the envelope varies,
    times how much of that variation sits in the 1-15 Hz syllabic band.

    Returns (score, depth, syllabic) where depth is the modulation index and
    syllabic is the fraction of envelope energy at speech rates.
    """
    if side is None:
        _, side = carrier_power(iq, rate, offset)

    iq = iq - iq.mean()

    # Carrier to DC, one channel only, so neighbours cannot inflate the result.
    centred = channel_filter(iq, rate, side, offset)
    env = np.abs(centred)
    if len(env) < 64 or env.mean() <= 0:
        return 0.0, 0.0, 0.0

    # Modulation index. NOT smoothed first: a smoothing window long enough to
    # matter averages the audio itself away.
    depth = float(env.std() / env.mean())

    # Where the envelope fluctuates. Speech and music are bunched at a few Hz;
    # noise is spread flat across the channel.
    ac = env - env.mean()
    spec = np.abs(np.fft.rfft(ac * np.hanning(len(ac))))
    freqs = np.fft.rfftfreq(len(ac), 1 / rate)

    syllabic_band = (freqs >= 1) & (freqs <= 15)
    total = spec[freqs >= 1]
    if not syllabic_band.any() or total.size == 0:
        return 0.0, depth, 0.0

    syllabic = float(np.sum(spec[syllabic_band] ** 2) / max(np.sum(total ** 2), 1e-30))

    return depth * syllabic * 100.0, depth, syllabic


def modulation_spectrum(iq, rate, lo=1.0, hi=500.0, top=6):
    """Strongest lines in the envelope of the baseband, 1-500 Hz.

    Interference sources fingerprint themselves here. A monitor writes its
    refresh rate, a switching supply its switching frequency, mains rectifiers
    120 Hz (or 100 Hz at 50 Hz mains). Broadcast programme audio does not
    produce narrow lines -- it spreads across the syllabic range.

    Returns [(hz, dB above neighbouring bins)], strongest first. The comparison
    is local rather than global so a line is judged against its own
    surroundings, which is what makes it a line rather than just loud.
    """
    env = np.abs(iq)
    env = env - env.mean()
    if len(env) < 1024:
        return []

    spec = np.abs(np.fft.rfft(env * np.hanning(len(env))))
    freqs = np.fft.rfftfreq(len(env), 1 / rate)

    band = (freqs >= lo) & (freqs <= hi)
    if not band.any():
        return []

    out = []
    for i in np.argsort(spec * band)[::-1]:
        f = freqs[i]
        if not (lo <= f <= hi):
            continue
        # Skip anything too close to a line already reported.
        if any(abs(f - g) < 3.0 for g, _ in out):
            continue
        near = (np.abs(freqs - f) > 5) & (np.abs(freqs - f) < 25)
        if not near.any():
            continue
        out.append((float(f), float(20 * np.log10(spec[i] / max(np.mean(spec[near]), 1e-15)))))
        if len(out) >= top:
            break

    return out


def spectrum(iq, rate, top=5, blank=2):
    """Strongest bins as offsets from the tuned centre.

    The DC bins are blanked: this board has a real DC offset on I, so DC always
    wins and says nothing about what is on the air.
    """
    mag = np.abs(np.fft.fftshift(np.fft.fft(iq * np.hanning(len(iq)))))
    freqs = np.fft.fftshift(np.fft.fftfreq(len(iq), 1 / rate))

    db = 20 * np.log10(np.maximum(mag, 1e-9))
    db -= db.max()

    centre = len(db) // 2
    db[centre - blank:centre + blank + 1] = -999

    return [(freqs[i], db[i]) for i in np.argsort(db)[-top:][::-1]]
