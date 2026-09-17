"""Bridge the radio board's I/Q stream into GNU Radio over ZMQ.

The board speaks USB CDC, which GNU Radio has no source block for. This reads
that stream and republishes it on a ZMQ PUB socket, so the flowgraph needs only
a stock "ZMQ SUB Source".

    conda activate gr
    python iq_bridge.py --tune 1.17e6

Then in GNU Radio Companion:
    ZMQ SUB Source   address tcp://127.0.0.1:5555   type complex   vlen 1

Protocol handling lives in radiolib; this file is transport only.
"""

import argparse
import sys
import time

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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    ap.add_argument("--endpoint", default=ENDPOINT)
    ap.add_argument("--tune", type=float, default=1.17e6)
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

    # Tune requests arrive here as a plain frequency in Hz.
    ctrl = ctx.socket(zmq.SUB)
    ctrl.bind(args.control)
    ctrl.setsockopt(zmq.SUBSCRIBE, b"")

    kw = {"port": args.port} if args.port else {}
    with RadioBoard(swap=not args.no_swap, **kw) as board:
        print(board.start_adc())

        if not args.no_tune:
            lo = board.tune(args.tune)
            print(f"tuned {args.tune/1e6:.4f} MHz  (lo {lo/1e6:.4f} MHz), "
                  f"carrier at +{OFFSET_HZ:.0f} Hz")

        print(f"publishing on {args.endpoint}")
        print(f"listening for tune requests on {args.control} -- ctrl-c to stop")

        total, rate = 0, None
        pending_hz, last_request = None, 0.0
        peak_reported = False
        try:
            # seconds=None streams indefinitely, re-issuing as the firmware's
            # 120 s cap expires.
            for iq, rate in board.stream():
                if total == 0:
                    print(f"sample rate {rate} Hz -- set this in the flowgraph")
                block = iq * args.gain
                sock.send(block.astype(np.complex64).tobytes())
                total += len(iq)

                # Report the level once, so the gain can be judged rather than
                # guessed at from the waterfall.
                if peak_reported is False:
                    pk = float(np.abs(block).max())
                    print(f"peak after gain {args.gain:.0f}x: {pk:.3f}"
                          f"   (aim near 1.0 for AM Demod)")
                    peak_reported = True

                # Drain the whole backlog, keeping only the newest. Processing
                # one per block would turn a single drag into dozens of
                # sequential retunes, which is exactly as bad as it sounds.
                while True:
                    try:
                        raw = ctrl.recv(zmq.NOBLOCK).decode()
                    except zmq.Again:
                        break
                    try:
                        pending_hz = float(raw)
                        last_request = time.time()
                    except ValueError:
                        print(f"\nignoring malformed tune request: {raw!r}")

                # Queue rather than retune here: the generator is suspended
                # mid-transfer and must apply it itself, at a clean boundary.
                if pending_hz is not None and time.time() - last_request > DEBOUNCE_S:
                    if board.request_tune(pending_hz):
                        print(f"\nretuning to {pending_hz/1e6:.4f} MHz")
                    pending_hz = None

                print(f"\r{total/rate:8.1f} s streamed", end="", flush=True)
        except KeyboardInterrupt:
            print("\nstopping")
        finally:
            board.stop_adc()
            ctrl.close()
            sock.close()
            ctx.term()


if __name__ == "__main__":
    sys.exit(main())
