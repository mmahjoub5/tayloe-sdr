"""Signal processing on what the board sends back."""

import wave

import numpy as np
from scipy.signal import butter, resample_poly, sosfiltfilt

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

    # Fixed noise reference band, not scaled to Nyquist: 10.8 kHz is the widest
    # both the 48 kHz and 24 kHz paths share.
    hi = min(10800.0, 0.9 * rate / 2)
    noise = (np.abs(freqs) > offset + 1500) & (np.abs(freqs) < hi)
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


def demod(iq, rate, mode="am", side=1.0, bw=5000.0, audio_band=(200, 3000)):
    """Demodulate one channel of complex baseband.

    mode "am"  envelope detection -- simple, and fine on a strong station
    mode "sam" synchronous detection -- worth about 3 dB on a weak one
    mode "usb"/"lsb" single sideband

    bw narrows the channel filter; audio_band narrows the output. Both trade
    top-end audio for noise, which is the right trade on a marginal signal.
    """
    # Strip the board's DC offset first. Envelope detection is shift-invariant
    # in theory, but a DC term beats against an offset carrier and lands a tone
    # at exactly the tuning offset -- loud enough to bury the programme audio.
    iq = iq - iq.mean()
    iq = channel_filter(iq, rate, side, bw=bw)

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
        # One sideband is the real part once the unwanted half is discarded;
        # conjugating swaps which half that is.
        audio = np.real(iq if mode == "usb" else np.conj(iq))
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
