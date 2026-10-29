"""
FT8 demo: build a 15 s slot (or load a WAV), decode it, print what was found.

    python -m radiolib.ft8                   synthetic slot: random messages + noise
    python -m radiolib.ft8 slot.wav          decode a recording (mono, one 15 s slot)
    python -m radiolib.ft8 --save out.wav    also write the synthetic slot to a WAV
"""

import argparse

import numpy as np
from scipy.io import wavfile

from .codec import FS, FT8, load_slot
from .pulse import GaussianPulse
from .waterfall import stft

SLOT = 15 * FS
START = int(0.5 * FS)   # WSJT-X transmits 0.5 s into the slot

# (tone-0 frequency Hz, SNR in 2500 Hz dB) of each synthetic signal
SIGNALS = [(600.0, -5), (1200.0, -12), (1500.0, 0), (2100.0, -17)]


def synthetic_slot(ft8: FT8, rng: np.random.Generator):
    """
    Build one slot of random FT8 messages in white noise.

    Args:
        ft8 (FT8): modulator
        rng (np.random.Generator): source of payloads and noise

    Returns:
        tuple: (np.ndarray audio of shape [SLOT], dict of tone-0 Hz -> 77-bit payload)
    """
    noise_sigma = 1.0
    noise_2500 = noise_sigma ** 2 * 2500 / (FS / 2)   # noise power in 2500 Hz
    x = rng.normal(0, noise_sigma, SLOT)
    sent = {}
    for f0_hz, snr_db in SIGNALS:
        payload = rng.integers(0, 2, 77)
        amp = np.sqrt(2 * noise_2500 * 10 ** (snr_db / 10))   # sine power = amp^2 / 2
        wave = ft8.modulate(payload, f0_hz, pulse=GaussianPulse(bt=2.0))
        x[START:START + len(wave)] += amp * wave
        sent[f0_hz] = payload
    return x, sent


def main():
    """Parse arguments, run the encoder and/or decoder, print the results."""
    parser = argparse.ArgumentParser(description="FT8 encode/decode demo")
    parser.add_argument("wav", nargs="?", help="recording to decode; synthetic slot if omitted")
    parser.add_argument("--save", help="write the synthetic slot to this WAV")
    parser.add_argument("--seed", type=int, default=0, help="random seed for the synthetic slot")
    args = parser.parse_args()

    ft8 = FT8()
    sent = {}
    if args.wav:
        x, fs = load_slot(args.wav)
    else:
        x, sent = synthetic_slot(ft8, np.random.default_rng(args.seed))
        fs = FS
        if args.save:
            wavfile.write(args.save, fs, (x / np.abs(x).max() * 32767).astype(np.int16))
            print(f"wrote {args.save}")

    wf = stft(x, fs=fs)
    decodes = ft8.decode(wf)

    print(f"{len(decodes)} decoded")
    print(f"{'time s':>7} {'freq Hz':>9} {'RF Hz':>12} {'sync':>6}  payload")
    for t0, f0, score, payload in sorted(decodes, key=lambda d: d[1]):
        f_hz = wf.f[f0]
        bits = "".join(map(str, payload))
        check = ""
        if sent:
            check = "  ok" if f_hz in sent and np.array_equal(payload, sent[f_hz]) else "  ??"
        print(f"{wf.t[t0]:7.2f} {f_hz:9.2f} {ft8.dial_hz + f_hz:12.0f} {score:6.1f}  "
              f"{int(bits, 2):020x}{check}")

    if sent:
        missed = [f for f, p in sent.items()
                  if not any(np.array_equal(d[3], p) for d in decodes)]
        snr = dict(SIGNALS)
        for f in missed:
            print(f"missed {f:.1f} Hz ({snr[f]} dB)")


if __name__ == "__main__":
    main()
