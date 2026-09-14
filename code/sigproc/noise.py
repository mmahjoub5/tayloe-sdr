"""Live noise floor meter -- for antenna positioning.

Tunes an empty channel and prints the floor a few times a second, so you can
move the antenna, rotate it, or switch things off and watch the number react.

    python noise.py                  # live, 1435 kHz
    python noise.py --once           # single reading
    python noise.py --freq 1035e3    # a different empty channel

Reference points measured on this board:
    -76 dBFS   board only, antenna disconnected  (the floor you cannot beat)
    -60 dBFS   typical with antenna connected    (15 dB of external noise)
"""

import argparse
import sys

import numpy as np
from radiolib import RadioBoard

BOARD_FLOOR = -76.4      # measured with the antenna disconnected
DEFAULT_FREQ = 1435e3    # off the 10 kHz grid: no broadcast carrier here


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--freq", type=float, default=DEFAULT_FREQ)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--frames", type=int, default=4096,
                    help="fewer frames = faster updates, noisier reading")
    args = ap.parse_args()

    with RadioBoard() as board:
        board.start_adc()
        board.tune(args.freq)

        if args.once:
            iq, _ = board.capture(args.frames)
            iq = iq - iq.mean()
            db = 20 * np.log10(np.sqrt(np.mean(np.abs(iq) ** 2)))
            print(f"{db:+.1f} dBFS   ({db - BOARD_FLOOR:+.1f} dB above board floor)")
            return

        print(f"noise floor at {args.freq/1e3:.0f} kHz -- ctrl-c to stop")
        print(f"board-only floor is {BOARD_FLOOR:+.1f} dBFS; "
              f"every dB you remove is a dB of SNR\n")
        best = None
        try:
            while True:
                iq, _ = board.capture(args.frames)
                iq = iq - iq.mean()
                db = 20 * np.log10(np.sqrt(np.mean(np.abs(iq) ** 2)))
                best = db if best is None else min(best, db)

                # Bar spans the board floor to 20 dB above it.
                excess = db - BOARD_FLOOR
                bar = "#" * max(0, min(40, int(excess * 2)))
                print(f"\r{db:+7.1f} dBFS  {excess:+5.1f} over board  "
                      f"best {best:+.1f}  {bar:<40}", end="", flush=True)
        except KeyboardInterrupt:
            print(f"\n\nbest seen: {best:+.1f} dBFS "
                  f"({best - BOARD_FLOOR:+.1f} dB above board floor)")
        finally:
            board.stop_adc()


if __name__ == "__main__":
    sys.exit(main())
