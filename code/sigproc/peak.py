"""Live signal meter -- for peaking a tuned loop antenna.

A tuned loop resonates at one frequency at a time. Its variable capacitor has
to be re-peaked whenever you change station, and a loop left on the wrong
frequency is substantially deaf. This prints carrier-to-noise several times a
second so you can turn the cap and watch it maximise.

    python peak.py --tune 810e3          # peak the loop for KGO
    python peak.py --tune 810e3 --noise  # show the noise floor too

Peak-hold shows the best reading seen, so you can sweep past the peak and know
where it was. Rotating the loop matters as much as the capacitor: it has deep
nulls, so orientation trades one station against another -- and against a noise
source, which is the more useful trade.
"""

import argparse
import sys

import numpy as np
from radiolib import RadioBoard, carrier_power

BOARD_FLOOR = -76.4      # measured with the antenna disconnected


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tune", type=float, default=810e3)
    ap.add_argument("--frames", type=int, default=4096,
                    help="fewer frames = faster updates, noisier reading")
    ap.add_argument("--noise", action="store_true",
                    help="also show the absolute noise floor")
    args = ap.parse_args()

    with RadioBoard() as board:
        board.start_adc()
        board.tune(args.tune)

        print(f"peaking {args.tune/1e3:.0f} kHz -- turn the loop's capacitor "
              f"for maximum, then rotate for the best null on the noise")
        print("ctrl-c to stop\n")

        best = None
        try:
            while True:
                iq, rate = board.capture(args.frames)
                iq = iq - iq.mean()
                cnr, _ = carrier_power(iq, rate, board.offset)
                best = cnr if best is None else max(best, cnr)

                # Bar spans 0-50 dB, which covers useless to excellent here.
                bar = "#" * max(0, min(44, int(cnr * 0.88)))
                line = f"\r{cnr:+6.1f} dB  best {best:+6.1f}"
                if args.noise:
                    nf = 20 * np.log10(np.sqrt(np.mean(np.abs(iq) ** 2)))
                    line += f"  floor {nf:+6.1f} ({nf - BOARD_FLOOR:+.0f} over board)"
                print(f"{line}  {bar:<44}", end="", flush=True)
        except KeyboardInterrupt:
            print(f"\n\nbest: {best:+.1f} dB carrier-to-noise")
        finally:
            board.stop_adc()


if __name__ == "__main__":
    sys.exit(main())
