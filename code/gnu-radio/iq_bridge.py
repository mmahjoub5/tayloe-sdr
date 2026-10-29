"""Bridge the radio board's I/Q stream into GNU Radio over ZMQ.

The board speaks USB CDC, which GNU Radio has no source block for. This reads
that stream and republishes it on a ZMQ PUB socket, so the flowgraph needs only
a stock "ZMQ SUB Source".

    conda activate gr
    python iq_bridge.py --tune 1.17e6

Then in GNU Radio Companion:
    ZMQ SUB Source   address tcp://127.0.0.1:5555   type complex   vlen 1

Tune requests arrive on the control socket as text: "<hz>" retunes and keeps
the current offset, "<hz> <offset>" sets both. The Board Tuner block sends the
second form, so the flowgraph decides where the carrier lands -- the same
number its Frequency Xlating filter shifts by.

Protocol handling lives in radiolib; this file is transport only.
"""

import argparse
import sys
import time
from contextlib import closing

import numpy as np
import zmq
from radiolib import OFFSET_HZ, RadioBoard

ENDPOINT = "tcp://127.0.0.1:5555"      # I/Q out
CONTROL = "tcp://127.0.0.1:5556"       # tune requests in

# A GRC slider emits a request per intermediate value while you drag, and each
# retune costs about a second of audio. Wait for the slider to settle, then act
# on the final value only.
DEBOUNCE_S = 0.35

# radiolib normalises to the ADC's full scale, so samples arrive around 0.005 --
# this board uses only ~15 of 24 bits. GNU Radio blocks assume roughly unity,
# and analog.am_demod_cf is worse than that: it hardcodes add_const_ff(-1.0)
# for carrier removal, so it needs a carrier near 1.0 or its output is
# dominated by DC. Scale on the way out.
DEFAULT_GAIN = 200.0

# The widest channel any flowgraph here uses: SSB's 3 kHz each side of the dial.
CHANNEL_BW = 6000.0


def parse_request(raw):
    """'<hz>' or '<hz> <offset>' -> (hz, offset or None). ValueError otherwise."""
    parts = raw.split()
    if len(parts) not in (1, 2):
        raise ValueError(raw)
    hz = float(parts[0])
    return hz, (float(parts[1]) if len(parts) == 2 else None)


def warn_if_unfit(board, rate):
    if not board.offset_fits(rate, CHANNEL_BW):
        print(f"\nwarning: {board.offset:.0f} Hz offset leaves no room for a "
              f"{CHANNEL_BW/1e3:.0f} kHz channel at {rate} Hz")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    ap.add_argument("--endpoint", default=ENDPOINT)
    ap.add_argument("--tune", type=float, default=1.17e6)
    ap.add_argument("--offset", type=float, default=OFFSET_HZ,
                    help="Hz to park the dial frequency above DC; the "
                         "flowgraph's Frequency Xlating filter must shift by "
                         "the same amount. The Board Tuner block overrides it.")
    ap.add_argument("--no-tune", action="store_true")
    ap.add_argument("--control", default=CONTROL)
    ap.add_argument("--gain", type=float, default=DEFAULT_GAIN,
                    help="scale samples before publishing; GNU Radio's AM "
                         "Demod wants a carrier near 1.0")
    ap.add_argument("--no-swap", action="store_true",
                    help="publish raw I/Q without un-mirroring the spectrum")
    args = ap.parse_args()

    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUB)
    sock.bind(args.endpoint)

    ctrl = ctx.socket(zmq.SUB)
    ctrl.bind(args.control)
    ctrl.setsockopt(zmq.SUBSCRIBE, b"")

    kw = {"port": args.port} if args.port else {}
    with RadioBoard(swap=not args.no_swap, offset=args.offset, **kw) as board:
        print(board.start_adc())

        # Where the board is tuned now, as (hz, offset). None until tuned, so
        # the first request always applies.
        current = None
        if not args.no_tune:
            lo = board.tune(args.tune)
            current = (args.tune, board.offset)
            print(f"tuned {args.tune/1e6:.4f} MHz  (lo {lo/1e6:.4f} MHz), "
                  f"carrier at +{board.offset:.0f} Hz")

        print(f"publishing on {args.endpoint}")
        print(f"listening for tune requests on {args.control} -- ctrl-c to stop")

        total, rate = 0, None
        pending, last_request = None, 0.0
        peak_reported = False
        try:
            while True:
                target = None
                # closing() so an early break aborts the firmware's stream right
                # there, leaving the port free for tune() below.
                with closing(board.stream()) as stream:
                    for iq, rate in stream:
                        if total == 0:
                            print(f"sample rate {rate} Hz, offset "
                                  f"{board.offset:.0f} Hz -- set these in the "
                                  f"flowgraph")
                            warn_if_unfit(board, rate)
                        block = iq * args.gain
                        sock.send(block.astype(np.complex64).tobytes())
                        total += len(iq)

                        # Report the level once, so the gain can be judged
                        # rather than guessed at from the waterfall.
                        if not peak_reported:
                            pk = float(np.abs(block).max())
                            print(f"peak after gain {args.gain:.0f}x: {pk:.3f}"
                                  f"   (aim near 1.0 for AM Demod)")
                            peak_reported = True

                        # Drain the whole backlog, keeping only the newest. One
                        # per block would turn a single drag into dozens of
                        # sequential retunes.
                        while True:
                            try:
                                raw = ctrl.recv(zmq.NOBLOCK).decode()
                            except zmq.Again:
                                break
                            try:
                                pending = parse_request(raw)
                                last_request = time.time()
                            except ValueError:
                                print(f"\nignoring malformed tune request: {raw!r}")

                        if pending is not None and time.time() - last_request > DEBOUNCE_S:
                            hz, off = pending
                            pending = None
                            want = (hz, board.offset if off is None else off)
                            # Each retune costs about a second of audio, so a
                            # request for where we already are is dropped.
                            if want != current:
                                target = want
                                break

                        print(f"\r{total/rate:8.1f} s streamed", end="", flush=True)

                if target is None:
                    continue                   # stream ended on its own; restart

                lo = board.tune(*target)
                current = target
                print(f"\nretuned to {target[0]/1e6:.4f} MHz  (lo {lo/1e6:.4f} MHz), "
                      f"carrier at +{board.offset:.0f} Hz")
                if rate:
                    warn_if_unfit(board, rate)
        except KeyboardInterrupt:
            print("\nstopping")
        finally:
            board.stop_adc()
            ctrl.close()
            sock.close()
            ctx.term()


if __name__ == "__main__":
    sys.exit(main())
