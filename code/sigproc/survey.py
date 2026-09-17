"""Wideband noise survey -- decides whether a preselector would help.

A bandpass filter can only reject noise arriving OUT of band. Noise already at
the tuned frequency passes any filter centred there. On this receiver there is
exactly one way out-of-band noise gets in:

    The Tayloe mixer is switched by a square wave, so it responds at every odd
    harmonic of the LO, at 1/n amplitude. The front end is a 21.3 MHz lowpass
    (J1 -> C22 100p -> L1 560n -> C23 100p), so tuned to 810 kHz, harmonics 3
    through 25 all pass -- folding noise from 2.4, 4.0, 5.7 MHz ... onto the
    same baseband.

Whether that matters depends on the noise spectrum, which is what this maps:

    flat noise      -> harmonics add ~0.9 dB, a filter buys nothing
    HF-heavy noise  -> folding dominates, a lowpass is worth building

    python survey.py                     # 0.5 - 20 MHz
    python survey.py --out before.npy    # save, to difference two runs
    python survey.py --compare before.npy
"""

import argparse
import sys

import numpy as np
from radiolib import RadioBoard, modulation_spectrum

# Log-spaced so the MF band is not swamped by the HF end. Avoids exact
# multiples of 10 kHz where broadcast carriers live.
def survey_points(lo=500e3, hi=20e6, n=40):
    pts = np.geomspace(lo, hi, n)
    return [round(p / 1e3) * 1e3 + 5e3 for p in pts]


def measure(board, freqs, frames=8192):
    out = []
    for hz in freqs:
        board.tune(hz)
        iq, rate = board.capture(frames)
        iq = iq - iq.mean()
        out.append(20 * np.log10(np.sqrt(np.mean(np.abs(iq) ** 2))))
    return np.array(out)


def verdict(freqs, db, tune_hz, fmax=21.3e6):
    """How much a preselector could actually buy at this tuning.

    Comparing raw noise means across the band is the wrong test: a square-wave
    mixer responds at harmonic n with amplitude 1/n, so power folds in at
    1/n^2. Noise 18 dB higher at 20 MHz still arrives attenuated by 28 dB if it
    takes the 25th harmonic to get there. Weight before judging.
    """
    lin = lambda d: 10 ** (d / 10.0)
    at = lambda hz: float(np.interp(hz, freqs, db))

    fundamental = lin(at(tune_hz))
    folded, rows = 0.0, []
    n = 3
    while n * tune_hz <= fmax:
        noise_db = at(n * tune_hz)
        contrib_db = noise_db - 20 * np.log10(n)
        folded += lin(contrib_db)
        rows.append((n, n * tune_hz, noise_db, contrib_db))
        n += 2

    penalty = 10 * np.log10((fundamental + folded) / fundamental)

    print(f"\nharmonic folding at {tune_hz/1e6:.3f} MHz "
          f"(front end passes to {fmax/1e6:.1f} MHz)\n")
    print(f"{'n':>3}  {'freq':>9}  {'noise':>7}  {'after 1/n^2':>12}")
    print(f"{1:>3}  {tune_hz/1e6:8.3f}M  {at(tune_hz):+6.1f}  {at(tune_hz):+11.1f}")
    for n, f, nd, cd in rows:
        print(f"{n:>3}  {f/1e6:8.3f}M  {nd:+6.1f}  {cd:+11.1f}")

    print(f"\ntotal folded noise adds {penalty:+.1f} dB")
    if penalty > 3:
        print("-> worth a lowpass ahead of the mixer")
    else:
        print("-> a preselector buys less than the measurement scatter.")
        print("   The noise is arriving in-band; antenna siting, orientation")
        print("   and a common-mode choke are the levers that matter.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lo", type=float, default=500e3)
    ap.add_argument("--hi", type=float, default=20e6)
    ap.add_argument("--points", type=int, default=40)
    ap.add_argument("--out", default=None, help="save readings for later diffing")
    ap.add_argument("--compare", default=None, help="diff against a saved run")
    ap.add_argument("--at", type=float, default=810e3,
                    help="tune frequency to evaluate harmonic folding for")
    ap.add_argument("--fingerprint", type=float, default=None,
                    help="also report envelope lines at this frequency (Hz)")
    args = ap.parse_args()

    freqs = survey_points(args.lo, args.hi, args.points)

    with RadioBoard() as board:
        board.start_adc()
        db = measure(board, freqs)

        lines = []
        if args.fingerprint:
            board.tune(args.fingerprint)
            iq = np.concatenate([x for x, r in board.stream(4)])
            lines = modulation_spectrum(iq, 24000)
        board.stop_adc()

    ref = np.load(args.compare) if args.compare else None
    lo, hi = db.min(), db.max()

    print(f"noise floor, {args.lo/1e6:.1f} - {args.hi/1e6:.1f} MHz\n")
    header = f"{'freq':>10}  {'dBFS':>7}"
    if ref is not None:
        header += f"  {'ref':>7}  {'delta':>7}"
    print(header)

    for i, (f, d) in enumerate(zip(freqs, db)):
        bar = "#" * int((d - lo) / max(hi - lo, 1e-9) * 40)
        row = f"{f/1e6:9.3f}M  {d:+6.1f}"
        if ref is not None and i < len(ref):
            row += f"  {ref[i]:+6.1f}  {d-ref[i]:+6.1f}"
        print(f"{row}  {bar}")

    verdict(freqs, db, args.at)

    if lines:
        print(f"\nenvelope lines at {args.fingerprint/1e6:.3f} MHz:")
        for hz, snr in lines:
            print(f"  {hz:7.1f} Hz  {snr:+5.1f} dB above neighbours")

    if args.out:
        np.save(args.out, db)
        print(f"\nsaved {args.out}")


if __name__ == "__main__":
    sys.exit(main())
