"""Stand in for the GNU Radio engine (XML-RPC :8080, ZMQ PUB :5560/:5561) with synthetic signals; run: python fake_engine.py."""

import math
import random
import threading
import time
from xmlrpc.server import SimpleXMLRPCServer

import numpy as np
import zmq

RPC = ("127.0.0.1", 8080)
WATERFALL = "tcp://127.0.0.1:5560"
AUDIO = "tcp://127.0.0.1:5561"

SPAN = 24000                    # Hz of I/Q around center
BINS = 1024
ROW_RATE = 10                   # waterfall rows per second
AUDIO_RATE = 12000
CHUNK = AUDIO_RATE // 50        # 20 ms
RETUNE_GAP = 1.0                # s of silence after a center change, like the real board
DB_MIN, DB_MAX = -120.0, -20.0  # dB mapped to 0..255
FT8_BANDS = (3573000, 7074000, 14074000, 21074000, 28074000)

state = {"center": 7069000.0, "mode": 1, "offset": 5000.0, "volume": -6.0}
lock = threading.Lock()
retuned_at = 0.0


class Engine:
    """The get_/set_ methods GRC's XML-RPC Server block would expose."""

    def __getattr__(self, method: str):
        """
        Answer get_<name> and set_<name> for every name in state.

        Args:
            method (str): e.g. "get_mode"

        Returns:
            callable: the getter or setter
        """
        verb, _, name = method.partition("_")
        if name not in state or verb not in ("get", "set"):
            raise AttributeError(method)
        if verb == "get":
            return lambda: state[name]
        return lambda value: set_value(name, value)


def set_value(name: str, value: float):
    """
    Set one control, noting a retune when center changes.

    Args:
        name (str): a key of state
        value (float): the new value
    """
    global retuned_at
    with lock:
        if name == "center" and float(value) != state["center"]:
            retuned_at = time.monotonic()
        state[name] = int(value) if name == "mode" else float(value)


def stations(lo: float, hi: float) -> list[tuple[float, str, float]]:
    """
    List the fixed-in-RF stations between two frequencies, seeded by 5 kHz bucket so they never move.

    Args:
        lo (float): lowest RF, Hz
        hi (float): highest RF, Hz

    Returns:
        list[tuple[float, str, float]]: (carrier Hz, "am" | "usb" | "lsb" | "cw", level dB)
    """
    out = []
    for b in range(int(lo // 5000) - 1, int(hi // 5000) + 2):
        rng = random.Random(b)
        if rng.random() < 0.45:
            kind = "am" if b * 5000 < 2e6 else rng.choice(("usb", "lsb", "cw"))
            out.append((b * 5000 + rng.uniform(0, 5000), kind, rng.uniform(-95, -50)))
    for f in (1170000.0, 1160000.0, 1180000.0):
        out.append((f, "am", -45.0))
    return out


def ft8_tones(t: float, lo: float, hi: float) -> list[tuple[float, float]]:
    """
    List the FT8-like tones on the air now: random signals per 15 s slot, 12.6 s long.

    Args:
        t (float): UTC seconds
        lo (float): lowest RF, Hz
        hi (float): highest RF, Hz

    Returns:
        list[tuple[float, float]]: (tone Hz, level dB)
    """
    slot, into = divmod(t, 15)
    if not 0.5 <= into < 13.1:
        return []
    out = []
    for dial in FT8_BANDS:
        if dial + 3000 < lo or dial > hi:
            continue
        rng = random.Random(int(slot) * 7 + dial)
        for _ in range(rng.randint(4, 12)):
            base, level = dial + rng.uniform(200, 2800), rng.uniform(-100, -60)
            symbol = int((into - 0.5) / 0.16)
            tone = random.Random(hash((slot, base, symbol))).randrange(8)
            out.append((base + tone * 6.25, level))
    return out


def spectrum(t: float, center: float) -> np.ndarray:
    """
    Make one waterfall row in dB.

    Args:
        t (float): UTC seconds
        center (float): LO, Hz

    Returns:
        np.ndarray: float dB, BINS long, lowest frequency first
    """
    rf = center + (np.arange(BINS) - BINS / 2) * SPAN / BINS
    lin = 10 ** (-110 / 10) * np.random.gamma(6.0, 1 / 6.0, BINS)   # a few averaged FFTs
    # The anti-alias roll-off near the edges of the span.
    lin *= 0.3 + 0.7 / (1 + ((rf - center) / (SPAN * 0.46)) ** 16)

    def add(f: float, width: float, db: float):
        lin[:] += 10 ** (db / 10) * np.exp(-0.5 * ((rf - f) / width) ** 2)

    for f, kind, db in stations(rf[0], rf[-1]):
        wobble = 0.5 + 0.5 * math.sin(t * 2.3 + f) * math.sin(t * 0.7 + f / 3)
        if kind == "cw":
            if math.sin(t * 6 + f) > 0:
                add(f, 8, db)
        elif kind == "am":
            add(f, 6, db)
            for side in (-1, 1):
                for a in np.linspace(200, 4000, 8):
                    add(f + side * a, 150, db - 22 - a / 400 + 6 * wobble)
        else:
            side = 1 if kind == "usb" else -1
            if wobble > 0.15:
                for a in np.linspace(300, 2700, 10):
                    add(f + side * a, 160, db - 8 - a / 500 + 8 * np.random.rand() * wobble)
    for f, db in ft8_tones(t, rf[0], rf[-1]):
        add(f, 4, db)
    return 10 * np.log10(lin)


def to_row(db: np.ndarray) -> bytes:
    """
    Map dB to the 0-255 bytes the engine publishes.

    Args:
        db (np.ndarray): one row in dB

    Returns:
        bytes: BINS uint8
    """
    return np.clip((db - DB_MIN) / (DB_MAX - DB_MIN) * 255, 0, 255).astype(np.uint8).tobytes()


def waterfall(sock: zmq.Socket):
    """
    Publish ROW_RATE rows per second forever.

    Args:
        sock (zmq.Socket): bound PUB socket
    """
    next_t = time.monotonic()
    while True:
        with lock:
            center = state["center"]
        sock.send(to_row(spectrum(time.time(), center)))
        next_t += 1 / ROW_RATE
        time.sleep(max(0.0, next_t - time.monotonic()))


def audio(sock: zmq.Socket):
    """
    Publish 20 ms int16 chunks in real time: a tone whose pitch follows offset, its timbre the mode, plus noise.

    Args:
        sock (zmq.Socket): bound PUB socket
    """
    phase, n = 0.0, np.arange(CHUNK)
    next_t = time.monotonic()
    while True:
        with lock:
            mode, offset, volume = state["mode"], state["offset"], state["volume"]
            quiet = time.monotonic() - retuned_at < RETUNE_GAP
        pitch = 300 + abs(offset) % 2400 if mode else 440.0
        w = 2 * np.pi * pitch / AUDIO_RATE
        ph = phase + w * n
        phase = (phase + w * CHUNK) % (2 * np.pi)
        if mode == 0:
            t = time.monotonic() + n / AUDIO_RATE
            x = np.sin(ph) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))
        elif mode == 1:
            x = np.sin(ph)
        else:
            x = 0.6 * np.sin(ph) + 0.4 * np.sin(1.5 * ph)
        x = 0.25 * x + 0.05 * np.random.randn(CHUNK)
        x *= 0.0 if quiet else 10 ** (volume / 20)
        sock.send((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
        next_t += CHUNK / AUDIO_RATE
        time.sleep(max(0.0, next_t - time.monotonic()))


def main():
    """Bind the sockets, start the streams and serve XML-RPC until interrupted."""
    ctx = zmq.Context()
    for endpoint, target in ((WATERFALL, waterfall), (AUDIO, audio)):
        sock = ctx.socket(zmq.PUB)
        sock.bind(endpoint)
        threading.Thread(target=target, args=(sock,), daemon=True).start()
    rpc = SimpleXMLRPCServer(RPC, allow_none=True, logRequests=False)
    rpc.register_instance(Engine(), allow_dotted_names=False)
    print(f"fake engine: XML-RPC {RPC[0]}:{RPC[1]}, waterfall {WATERFALL}, audio {AUDIO}")
    try:
        rpc.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
