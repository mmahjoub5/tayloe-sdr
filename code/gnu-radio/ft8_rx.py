"""Decode FT8 from a WAV recorded off an SSB receiver flowgraph.

In board/ssb_receiver.grc or rtlsdr/ssb_receiver.grc, add a stock WAV File
Sink beside the Audio Sink (same input, same sample rate), record a minute or
so, then:

    conda activate gr
    python ft8_rx.py rx.wav
    python ft8_rx.py rx.wav --dial 7.074e6     also print RF frequency

The recording need not start on a UTC slot boundary: the decoder searches
every time offset, and windows of 30 s every 15 s make sure each 12.64 s
transmission lies wholly inside at least one of them.
"""

import argparse
import sys
from math import gcd

import numpy as np
from radiolib.ft8 import FS, FT8, stft
from scipy.io import wavfile
from scipy.signal import resample_poly

WINDOW_S = 30
HOP_S = 15


def load(path):
    """WAV -> mono float audio at the decoder's rate FS."""
    fs, x = wavfile.read(path)
    if x.ndim > 1:
        x = x[:, 0]
    x = x.astype(float)
    g = gcd(FS, fs)
    return resample_poly(x - x.mean(), FS // g, fs // g)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("wav")
    ap.add_argument("--dial", type=float, default=None,
                    help="receiver dial frequency, Hz, to print RF = dial + audio")
    args = ap.parse_args()

    x = load(args.wav)
    print(f"{args.wav}: {len(x) / FS:.1f} s")
    ft8 = FT8()
    win, hop = WINDOW_S * FS, HOP_S * FS

    seen = []      # (time s, payload) already printed
    for start in range(0, max(1, len(x) - hop), hop):
        chunk = x[start:start + win]
        if len(chunk) < 13 * FS:      # too short to hold a whole transmission
            break
        wf = stft(chunk, fs=FS)
        for t0, f0, score, payload in ft8.decode(wf):
            t = start / FS + float(wf.t[t0])
            hexp = f"{int(''.join(map(str, payload)), 2):020x}"
            # the window overlap finds the same transmission twice
            if any(abs(t - ts) < 1.0 and hexp == p for ts, p in seen):
                continue
            seen.append((t, hexp))
            f = float(wf.f[f0])
            rf = f"  {args.dial + f:12.0f} Hz" if args.dial else ""
            print(f"{t:7.2f} s  {f:7.1f} Hz{rf}  sync {score:5.1f}  {hexp}")

    print(f"{len(seen)} decoded")


if __name__ == "__main__":
    sys.exit(main())
