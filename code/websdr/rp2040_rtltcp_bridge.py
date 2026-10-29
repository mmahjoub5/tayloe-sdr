"""Serve the RP2040 Tayloe board as an rtl_tcp server, so OpenWebRX can use it as an "RTL-SDR device (via rtl_tcp)"."""

import argparse
import socket
import struct
import sys
import threading
import time
from contextlib import closing

import numpy as np
import serial
from radiolib import CAPTURE_RATE, RadioBoard
from scipy.signal import lfilter

LISTEN = "127.0.0.1:1234"

# rtl_tcp command codes; every other code is accepted and ignored.
CMD_FREQ = 0x01
CMD_RATE = 0x02

TUNER_R820T = 5
GAIN_STEPS = 29

DEFAULT_GAIN_DB = 46.0          # the 200x iq_bridge.py uses; board peaks sit near 0.005
DEBOUNCE_S = 0.3                # connector sends bursts of commands on connect and profile switch
DC_POLE = 0.999                 # DC blocker pole; about 8 Hz wide at 48 kHz
STATS_S = 10.0
RETRY_S = 3.0


class Tuning:
    """Frequency requests from the client, handed over to the streaming loop."""

    def __init__(self):
        """Start with no request pending."""
        self.lock = threading.Lock()
        self.pending = None
        self.stamp = 0.0

    def request(self, hz: int):
        """
        Record a frequency request from the client.

        Args:
            hz (int): requested center frequency, Hz
        """
        with self.lock:
            self.pending = hz
            self.stamp = time.time()

    def take(self) -> int | None:
        """
        Take the pending request once it has been quiet for DEBOUNCE_S.

        Returns:
            int | None: center frequency in Hz, or None if nothing is ready
        """
        with self.lock:
            if self.pending is None or time.time() - self.stamp < DEBOUNCE_S:
                return None
            hz, self.pending = self.pending, None
            return hz


class Levels:
    """Running peak and clip counts, printed every STATS_S."""

    def __init__(self):
        """Start an empty reporting window."""
        self.reset()

    def reset(self):
        """Clear the counters and restart the window."""
        self.peak, self.clipped, self.total = 0.0, 0, 0
        self.t0 = time.time()

    def add(self, x: np.ndarray):
        """
        Count one block of scaled I/Q and print a line when the window is full.

        Args:
            x (np.ndarray): float32, interleaved I/Q after gain, full scale is 1.0
        """
        a = np.abs(x)
        self.peak = max(self.peak, float(a.max()))
        self.clipped += int(np.count_nonzero(a > 1.0))
        self.total += len(x)
        if time.time() - self.t0 >= STATS_S:
            pct = 100.0 * self.clipped / max(self.total, 1)
            print(f"peak {self.peak:.3f} of full scale, {pct:.2f}% clipped")
            self.reset()


def to_u8(iq: np.ndarray, gain: float) -> tuple[bytes, np.ndarray]:
    """
    Scale complex samples and pack them as rtl_tcp's interleaved unsigned 8-bit I/Q.

    Args:
        iq (np.ndarray): complex samples, board full scale is 1.0
        gain (float): linear gain applied before quantizing

    Returns:
        tuple[bytes, np.ndarray]: the packed bytes, and the scaled interleaved floats
    """
    x = np.empty(2 * len(iq), dtype=np.float32)
    x[0::2] = iq.real
    x[1::2] = iq.imag
    x *= gain
    u8 = np.clip(np.rint(x * 127.5 + 127.5), 0, 255).astype(np.uint8)
    return u8.tobytes(), x


def read_commands(conn: socket.socket, tuning: Tuning, rate: int):
    """
    Read 5-byte rtl_tcp commands until the client disconnects.

    Args:
        conn (socket.socket): the client connection
        tuning (Tuning): where frequency requests go
        rate (int): the board's stream rate, Hz
    """
    buf = b""
    while True:
        try:
            data = conn.recv(64)
        except OSError:
            return
        if not data:
            return
        buf += data
        while len(buf) >= 5:
            cmd, value = struct.unpack(">BI", buf[:5])
            buf = buf[5:]
            if cmd == CMD_FREQ:
                tuning.request(value)
            elif cmd == CMD_RATE and value != rate:
                print(f"client asked for {value} Hz; the board streams {rate} Hz, "
                      f"set samp_rate {rate} in the profile")


def serve_client(board: RadioBoard, conn: socket.socket, args, state: dict):
    """
    Stream the board to one client, retuning on its requests, until it disconnects.

    Args:
        board (RadioBoard): an open board with the ADC running
        conn (socket.socket): the client connection
        args (argparse.Namespace): command-line options
        state (dict): survives across clients; "hz" is the current center frequency
    """
    rate = CAPTURE_RATE // board.decim
    conn.sendall(b"RTL0" + struct.pack(">II", TUNER_R820T, GAIN_STEPS))

    tuning = Tuning()
    reader = threading.Thread(target=read_commands, args=(conn, tuning, rate), daemon=True)
    reader.start()

    gain = 10 ** (args.gain / 20)
    levels = Levels()
    zi = None
    while reader.is_alive():
        target = None
        with closing(board.stream()) as stream:
            for iq, rate in stream:
                if args.dc_block:
                    if zi is None:
                        zi = np.array([-iq[0] * DC_POLE], dtype=complex)
                    iq, zi = lfilter([1, -1], [1, -DC_POLE], iq, zi=zi)
                data, x = to_u8(iq, gain)
                try:
                    conn.sendall(data)
                except OSError:
                    return
                levels.add(x)

                hz = tuning.take()
                if hz is not None and hz != state.get("hz"):
                    target = hz
                    break
                if not reader.is_alive():
                    return

        if target is None:
            continue
        if not args.fmin <= target <= args.fmax:
            print(f"ignoring {target/1e6:.4f} MHz: outside {args.fmin/1e6:g}-{args.fmax/1e6:g} MHz")
            continue
        board.tune(target, offset=0)
        state["hz"] = target
        zi = None
        print(f"tuned {target/1e6:.4f} MHz")


def run(args):
    """
    Open the board, then accept clients one at a time, reopening the board if it goes away.

    Args:
        args (argparse.Namespace): command-line options
    """
    host, port = args.listen.rsplit(":", 1)
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, int(port)))
    srv.listen(1)

    state = {}
    while True:
        try:
            kw = {"port": args.port} if args.port else {}
            with RadioBoard(decim=args.decim, **kw) as board:
                print(f"board on {board.ser.port}: {board.start_adc()}")
                if "hz" in state:
                    board.tune(state["hz"], offset=0)
                print(f"listening on {args.listen}, gain {args.gain:g} dB")
                while True:
                    conn, addr = srv.accept()
                    print(f"client {addr[0]}:{addr[1]} connected")
                    conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                    try:
                        serve_client(board, conn, args, state)
                    finally:
                        conn.close()
                        print("client disconnected")
        except (serial.SerialException, OSError, RuntimeError) as e:
            print(f"board error: {e}; retrying in {RETRY_S:g} s")
            time.sleep(RETRY_S)


def main():
    """Parse options and run the bridge until interrupted."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", default=None, help="serial port; found by USB ID if omitted")
    ap.add_argument("--listen", default=LISTEN, help="host:port to serve rtl_tcp on")
    ap.add_argument("--gain", type=float, default=DEFAULT_GAIN_DB,
                    help="dB of digital gain before quantizing to 8 bits")
    ap.add_argument("--decim", type=int, choices=(1, 2), default=1,
                    help="firmware decimation: 1 = 48 kHz, 2 = 24 kHz")
    ap.add_argument("--fmin", type=float, default=100e3, help="lowest center frequency accepted, Hz")
    ap.add_argument("--fmax", type=float, default=30e6, help="highest center frequency accepted, Hz")
    ap.add_argument("--no-dc-block", dest="dc_block", action="store_false",
                    help="leave the board's DC offset in the middle of the waterfall")
    args = ap.parse_args()
    sys.stdout.reconfigure(line_buffering=True)     # journald sees each line as it happens
    try:
        run(args)
    except KeyboardInterrupt:
        print("stopping")


if __name__ == "__main__":
    sys.exit(main())
