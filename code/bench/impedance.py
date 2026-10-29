"""Measure the antenna's source impedance, using the receiver itself.

A Tayloe detector integrates onto its sampling capacitors, and they set the
baseband bandwidth:

    BW = 1 / (2*pi * n * Rs * C)        n = 4 phases, C = 100 nF (C40-C43)

So the baseband corner is a direct readout of the source impedance. Sweep a
strong station's carrier across baseband offsets, fit the first-order roll-off,
and invert the formula.

    python impedance.py --tune 1.17e6

Run it after any antenna change: the corner moves with Rs, which means your
audio bandwidth moves with your antenna.
"""

import argparse
import sys

import numpy as np
from radiolib import CSAMP, PHASES, RadioBoard

OFFSETS = [1000, 2000, 3000, 5000, 8000, 11000, 15000, 19000]


def carrier_dbfs(iq, rate, offset, width=400.0):
    seg = int(rate * 0.17)
    nseg = max(1, len(iq) // seg)
    win = np.hanning(seg)
    acc = None
    for i in range(nseg):
        sp = np.abs(np.fft.fftshift(np.fft.fft(iq[i*seg:(i+1)*seg] * win)))
        acc = sp if acc is None else acc + sp
    sp = acc / nseg / (seg / 2)
    f = np.fft.fftshift(np.fft.fftfreq(seg, 1 / rate))
    band = np.abs(np.abs(f) - offset) < width / 2
    return 20 * np.log10(max(np.max(sp[band]), 1e-12))


def fit_pole(offsets, levels):
    """Least-squares fit of a single-pole roll-off to the measured levels."""
    best = (None, 1e30)
    for fc in np.geomspace(300, 40000, 400):
        model = -20 * np.log10(np.sqrt(1 + (np.array(offsets) / fc) ** 2))
        # Both curves are relative, so remove each one's mean before comparing.
        err = np.sum(((model - model.mean()) - (levels - levels.mean())) ** 2)
        if err < best[1]:
            best = (fc, err)
    return best[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", type=float, default=1.17e6,
                    help="a strong station -- the carrier is the test signal")
    ap.add_argument("--rounds", type=int, default=3)
    args = ap.parse_args()

    res = {o: [] for o in OFFSETS}
    with RadioBoard() as board:
        board.start_adc()
        # Interleaved, so a station whose modulation drifts does not tilt the fit.
        for _ in range(args.rounds):
            for off in OFFSETS:
                board.offset = off
                board.tune(args.tune)
                iq, rate = board.capture(8192)
                res[off].append(carrier_dbfs(iq - iq.mean(), rate, off))
        board.stop_adc()

    levels = np.array([np.median(res[o]) for o in OFFSETS])
    ref = levels[0]

    print(f"baseband response at {args.tune/1e6:.3f} MHz\n")
    print(f"{'offset':>7}  {'level':>9}  {'vs 1kHz':>8}  {'spread':>7}")
    for off, lv in zip(OFFSETS, levels):
        v = np.array(res[off])
        print(f"{off:6d}   {lv:+8.1f}  {lv-ref:+7.1f}  {v.max()-v.min():6.1f}")

    fc = fit_pole(OFFSETS, levels)
    rs = 1 / (2 * np.pi * PHASES * CSAMP * fc)

    print(f"\nfitted corner      {fc:8.0f} Hz")
    print(f"implied source Z   {rs:8.0f} ohm   "
          f"(BW = 1/(2*pi*{PHASES}*Rs*{CSAMP*1e9:.0f}nF))")
    print(f"vs 50 ohm          {20*np.log10(rs/50):+8.1f} dB mismatch in Rs")
    print(f"\nAudio bandwidth is this corner. Widening it means lowering Rs")
    print(f"(matching transformer) or smaller sampling caps -- the latter")
    print(f"trades away conversion gain.")


if __name__ == "__main__":
    sys.exit(main())
