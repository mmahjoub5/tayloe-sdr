"""Antenna report card -- one command, comparable numbers.

Antenna comparisons on this receiver kept going wrong because conditions drift
between measurements. This takes everything in one pass so a before/after is
meaningful:

  noise floor vs frequency   how much the antenna adds over the board's own
                             -76.4 dBFS -- that gap is your headroom
  source impedance           from the Tayloe corner, BW = 1/(2*pi*4*Rs*C).
                             It also sets your audio bandwidth.
  reference carriers         KLOK for MW, WWV for HF. WWV is the useful one:
                             NIST time stations on exact frequencies, 24/7,
                             so silence there is the receiver, not the band.

    python antenna.py --save loop.npz
    python antenna.py --compare loop.npz
"""

import argparse
import sys

import numpy as np
from radiolib import BOARD_FLOOR_DBFS as BOARD_FLOOR, CSAMP, PHASES, RadioBoard, carrier_power


# Off-channel, so no broadcast carrier lands in a noise measurement.
NOISE_FREQS = [0.635e6, 1.035e6, 1.435e6, 2.505e6, 3.805e6,
               5.505e6, 7.205e6, 9.605e6, 14.255e6, 18.105e6]

# Known transmitters. WWV/WWVH are on air continuously on exact frequencies.
REFS = [(1.170e6, "KLOK   MW local"), (2.5e6, "WWV    2.5 MHz"),
        (5.0e6, "WWV    5 MHz"), (10.0e6, "WWV    10 MHz"),
        (15.0e6, "WWV    15 MHz"), (20.0e6, "WWV    20 MHz")]

OFFSETS = [1000, 2000, 3000, 5000, 8000, 11000, 15000]


def noise_floor(b, hz, frames=8192):
    b.tune(hz)
    iq, _ = b.capture(frames)
    iq = iq - iq.mean()
    return 20 * np.log10(np.sqrt(np.mean(np.abs(iq) ** 2)))


def carrier_level(b, hz, offset, width=400.0):
    seg_s = 0.17
    b.tune(hz)
    iq, rate = b.capture(8192)
    iq = iq - iq.mean()
    seg = int(rate * seg_s)
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


def source_impedance(b, ref_hz):
    """Fit the baseband roll-off; the Tayloe corner gives Rs."""
    levels = []
    for off in OFFSETS:
        b.offset = off
        levels.append(carrier_level(b, ref_hz, off))
    b.offset = 3000.0
    levels = np.array(levels)

    best = (None, 1e30)
    for fc in np.geomspace(300, 40000, 400):
        model = -20 * np.log10(np.sqrt(1 + (np.array(OFFSETS) / fc) ** 2))
        err = np.sum(((model - model.mean()) - (levels - levels.mean())) ** 2)
        if err < best[1]:
            best = (fc, err)
    fc = best[0]
    return fc, 1 / (2 * np.pi * PHASES * CSAMP * fc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", default=None)
    ap.add_argument("--compare", default=None)
    ap.add_argument("--skip-impedance", action="store_true")
    args = ap.parse_args()

    ref = np.load(args.compare) if args.compare else None

    with RadioBoard() as b:
        b.start_adc()
        floors = np.array([noise_floor(b, hz) for hz in NOISE_FREQS])
        cnrs = []
        for hz, _ in REFS:
            b.tune(hz)
            iq, rate = b.capture(8192)
            cnrs.append(carrier_power(iq, rate, b.offset)[0])
        cnrs = np.array(cnrs)
        fc, rs = (0.0, 0.0) if args.skip_impedance else source_impedance(b, REFS[0][0])
        b.stop_adc()

    print(f"\nnoise floor (board alone is {BOARD_FLOOR:+.1f} dBFS)")
    print(f"{'freq':>9} {'dBFS':>8} {'over board':>11}" +
          (f" {'was':>8} {'delta':>7}" if ref is not None else ""))
    for i, hz in enumerate(NOISE_FREQS):
        row = f"{hz/1e6:8.3f}M {floors[i]:+7.1f} {floors[i]-BOARD_FLOOR:+10.1f}"
        if ref is not None:
            row += f" {ref['floors'][i]:+7.1f} {floors[i]-ref['floors'][i]:+6.1f}"
        print(row)

    mw = floors[NOISE_FREQS.index(1.435e6)]
    hf = np.mean([f for h, f in zip(NOISE_FREQS, floors) if h > 5e6])
    print(f"\n  MW  {mw:+.1f} dBFS ({mw-BOARD_FLOOR:+.1f} over board)")
    print(f"  HF  {hf:+.1f} dBFS ({hf-BOARD_FLOOR:+.1f} over board)")

    print(f"\nreference carriers (C/N dB; >45 is intelligible AM)")
    for i, (hz, name) in enumerate(REFS):
        row = f"  {name:<16} {cnrs[i]:+6.1f}"
        if ref is not None:
            row += f"   was {ref['cnrs'][i]:+6.1f}   {cnrs[i]-ref['cnrs'][i]:+6.1f}"
        print(row + ("  <-- heard" if cnrs[i] > 25 else ""))

    if not args.skip_impedance:
        print(f"\nsource impedance  {rs:.0f} ohm   "
              f"(baseband corner {fc:.0f} Hz = your audio bandwidth)")
        if ref is not None:
            print(f"  was {float(ref['rs']):.0f} ohm, corner {float(ref['fc']):.0f} Hz")

    heard = [n for c, (_, n) in zip(cnrs, REFS) if c > 25 and "WWV" in n]
    print(f"\n-> {len(heard)} WWV frequencies heard" +
          (f": {', '.join(h.split()[1] for h in heard)}" if heard else
           "  (no HF reception)"))

    if args.save:
        np.savez(args.save, floors=floors, cnrs=cnrs, fc=fc, rs=rs)
        print(f"saved {args.save}")


if __name__ == "__main__":
    sys.exit(main())
