"""Tune the board while iq_bridge.py is streaming, without touching GRC.

    python tune.py 1170e3            # one-shot
    python tune.py                   # interactive; blank line or ctrl-d quits

Useful on its own, and a fallback if the Embedded Python Block is awkward.
"""

import sys
import time

import zmq

CONTROL = "tcp://127.0.0.1:5556"


def main():
    ctx = zmq.Context()
    sock = ctx.socket(zmq.PUB)
    sock.connect(CONTROL)

    # PUB drops anything sent before the subscriber connects, so the first
    # request would vanish without this pause.
    time.sleep(0.3)

    def send(text):
        try:
            hz = float(text)
        except ValueError:
            print(f"  not a frequency: {text!r}")
            return
        sock.send(str(hz).encode())
        print(f"  -> {hz/1e6:.4f} MHz")

    if len(sys.argv) > 1:
        send(sys.argv[1])
    else:
        print(f"tuning via {CONTROL}; enter Hz (e.g. 1170e3), blank to quit")
        try:
            while True:
                line = input("freq> ").strip()
                if not line:
                    break
                send(line)
        except EOFError:
            pass

    sock.close()
    ctx.term()


if __name__ == "__main__":
    sys.exit(main())
