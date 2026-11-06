"""Decode FT8 from the engine's audio with ft8_lib's decode_ft8, one UTC slot at a time, and publish the messages (see PROTOCOL.md)."""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
from collections import deque
from xmlrpc.client import ServerProxy

import numpy as np
import zmq
from scipy.io import wavfile

AUDIO = "tcp://127.0.0.1:5562"              # the engine's audio before the volume, float32, 12 kHz
PUBLISH = "tcp://127.0.0.1:5563"
ENGINE = "http://127.0.0.1:8080"
DECODER = "decode_ft8"

FS = 12000
SLOT_S = 15
LATENCY_S = 0.5                             # the audio of a slot has reached us this long after it ends
MIN_AUDIO_S = 14                            # less than this in the buffer means a gap, e.g. the engine restarted
DECODE_TIMEOUT_S = 10
USB = 1
FT8_DIALS = (1840000, 3573000, 5357000, 7074000, 10136000, 14074000, 18100000, 21074000, 24915000, 28074000)
WAV_DIR = "/dev/shm" if os.path.isdir("/dev/shm") else None     # RAM, so no SD card wear

# 234500 +12.5 +0.48 1200 ~  CQ K1ABC FN42   (the second field is the sync score / 2, not an SNR)
LINE = re.compile(r"^\d{6} ([+-]\d+\.\d) ([+-]\d+\.\d+) +(\d+) ~\s+(.+?)\s*$")


def parse_output(text: str) -> list[dict]:
    """
    Pick the messages out of decode_ft8's output.

    Args:
        text (str): what it printed

    Returns:
        list[dict]: {"hz", "dt", "score", "text"} per message; ones it couldn't unpack are left out
    """
    decodes = []
    for line in text.splitlines():
        m = LINE.match(line)
        if m and not m[4].startswith("Error ["):
            decodes.append({"hz": int(m[3]), "dt": float(m[2]), "score": round(float(m[1]) * 2), "text": m[4]})
    return decodes


def decode_slot(audio: np.ndarray, decoder: str = DECODER) -> list[dict] | None:
    """
    Run the decoder on one slot of audio, at low priority so it can't disturb the radio.

    Args:
        audio (np.ndarray): float audio at FS, any level
        decoder (str): the decode_ft8 executable

    Returns:
        list[dict] | None: the messages, or None if the decoder failed
    """
    audio = audio - audio.mean()
    rms = np.sqrt(np.mean(audio ** 2))
    if rms == 0:
        return []
    # Scaled on rms, not peak, so one sample spike can't push the signal down into the 16-bit quantizing noise.
    pcm = np.clip(audio / rms * 3000, -32767, 32767).astype(np.int16)
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=WAV_DIR) as f:
        wavfile.write(f.name, FS, pcm)
        try:
            done = subprocess.run(["nice", "-n", "10", decoder, f.name], capture_output=True, text=True,
                                  timeout=DECODE_TIMEOUT_S)
        except (OSError, subprocess.TimeoutExpired) as e:
            print(f"decoder failed: {e}", flush=True)
            return None
    if done.returncode != 0:
        print(f"decoder exited {done.returncode}: {done.stderr.strip()}", flush=True)
        return None
    return parse_output(done.stdout)


def tuned_state(engine) -> tuple | None:
    """
    Read what the radio is tuned to.

    Args:
        engine (object): has get_center, get_offset and get_mode, e.g. a ServerProxy

    Returns:
        tuple | None: (dial Hz, mode), or None if the engine isn't reachable
    """
    try:
        return round(engine.get_center() + engine.get_offset()), engine.get_mode()
    except Exception as e:                  # network errors or an XML-RPC fault
        print(f"engine not reachable: {e}", flush=True)
        return None


def should_decode(before: tuple | None, now: tuple | None) -> bool:
    """
    Decide whether a slot is worth decoding: in USB on an FT8 frequency from its start to its end.

    Args:
        before (tuple | None): tuned_state at the start of the slot
        now (tuple | None): tuned_state at the end of the slot

    Returns:
        bool: True to decode
    """
    return before == now and now is not None and now[1] == USB and now[0] in FT8_DIALS


class AudioBuffer:
    """The latest audio, as it arrived."""

    def __init__(self, seconds: int = SLOT_S):
        """
        Start empty.

        Args:
            seconds (int): how much to keep
        """
        self.keep = seconds * FS
        self.chunks = deque()
        self.count = 0

    def add(self, samples: np.ndarray):
        """
        Append samples and drop what's no longer needed.

        Args:
            samples (np.ndarray): float audio
        """
        self.chunks.append(samples)
        self.count += len(samples)
        while self.count - len(self.chunks[0]) >= self.keep:
            self.count -= len(self.chunks.popleft())

    def latest(self) -> np.ndarray:
        """
        Get the kept audio.

        Returns:
            np.ndarray: up to the last `seconds` of audio
        """
        if not self.chunks:
            return np.empty(0, dtype=np.float32)
        return np.concatenate(self.chunks)[-self.keep:]


def run(audio_addr: str, publish_addr: str, engine, decoder: str):
    """
    Decode every slot until interrupted.

    Args:
        audio_addr (str): the engine's audio PUB address
        publish_addr (str): where to publish decodes
        engine (object): has get_center, get_offset and get_mode
        decoder (str): the decode_ft8 executable
    """
    ctx = zmq.Context()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.RCVHWM, 0)           # audio queued during a decode must wait, not be dropped
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    sub.connect(audio_addr)
    pub = ctx.socket(zmq.PUB)
    pub.bind(publish_addr)

    buffer = AudioBuffer()
    boundary = (int(time.time()) // SLOT_S + 1) * SLOT_S
    before = tuned_state(engine)
    while True:
        if sub.poll(100):
            buffer.add(np.frombuffer(sub.recv(), dtype=np.float32))
        if time.time() < boundary + LATENCY_S:
            continue
        now = tuned_state(engine)
        audio = buffer.latest()
        if should_decode(before, now) and len(audio) >= MIN_AUDIO_S * FS:
            t0 = time.time()
            decodes = decode_slot(audio, decoder)
            if decodes is not None:
                pub.send_string(json.dumps({"slot": boundary - SLOT_S, "dial": now[0],
                                            "seconds": round(time.time() - t0, 2), "decodes": decodes}))
        before = now
        boundary = (int(time.time()) // SLOT_S + 1) * SLOT_S


def main():
    """Parse options and run."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", default=AUDIO, help="the engine's audio PUB address")
    ap.add_argument("--publish", default=PUBLISH, help="where to publish decodes")
    ap.add_argument("--engine", default=ENGINE, help="the flowgraph's XML-RPC address")
    ap.add_argument("--decoder", default=DECODER, help="the decode_ft8 executable")
    args = ap.parse_args()
    socket.setdefaulttimeout(3)             # a stuck engine must not stall the audio buffer
    run(args.audio, args.publish, ServerProxy(args.engine, allow_none=True), args.decoder)


if __name__ == "__main__":
    sys.exit(main())
