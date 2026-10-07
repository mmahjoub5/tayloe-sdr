"""Signal processing on what the board sends back."""

import wave

import numpy as np
from scipy.signal import butter, firwin, lfilter, resample_poly, sosfiltfilt

from .board import OFFSET_HZ


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


def equalize(iq, rate, fc=2700.0, max_boost_db=18.0):
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
