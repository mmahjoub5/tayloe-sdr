"""Talking to the board over its serial CLI."""

import time

import numpy as np
import serial
from serial.tools import list_ports

from .hardware import (
    FULL_SCALE,
    MAX_CAPTURE,
    OFFSET_HZ,
    STREAM_CHUNK_S,
    STREAM_DECIM,
    TAYLOE_DIV,
    XTAL_CORR_PPB,
)

# None means find the board by USB ID, since macOS names the port after the
# hub socket it is plugged into (usbmodem101, usbmodem1101, ...).
DEFAULT_PORT = None
RP2040_VID = 0x2E8A


def find_port():
    """Find the serial port of the board's RP2040.

    Returns:
        str: device path, e.g. "/dev/cu.usbmodem101".
    """
    found = [p.device for p in list_ports.comports() if p.vid == RP2040_VID]
    # macOS lists each port twice; the cu. node doesn't wait for carrier detect.
    found = sorted(found, key=lambda d: "/cu." not in d)
    if not found:
        raise serial.SerialException("no RP2040 board found on USB; is it plugged in?")
    return found[0]


def to_complex(raw, swap=True, scale=FULL_SCALE):
    """Interleaved little-endian int32 pairs -> normalised complex samples.

    Returns (samples, leftover). Serial reads do not land on 8-byte boundaries,
    so any partial sample is handed back to be prepended to the next read --
    dropping it would shift I and Q against each other for good.
    """
    usable = (len(raw) // 8) * 8
    leftover = bytes(raw[usable:])

    if not usable:
        return np.empty(0, dtype=np.complex128), leftover

    flat = np.frombuffer(bytes(raw[:usable]), dtype="<i4").astype(np.float64)
    iq = (flat[0::2] + 1j * flat[1::2]) / scale

    # The board's I and Q are swapped relative to the usual sense, so the
    # spectrum arrives mirrored. Conjugating puts it back, which matters for
    # anything sideband-sensitive even though AM does not care.
    return (np.conj(iq) if swap else iq), leftover


class RadioBoard:
    """One serial connection to the board, plus the protocol on top of it."""

    def __init__(self, port=DEFAULT_PORT, baud=115200, timeout=1.0, swap=True,
                 offset=OFFSET_HZ, corr=XTAL_CORR_PPB, decim=STREAM_DECIM):
        self.ser = serial.Serial(port or find_port(), baud, timeout=timeout)
        self.swap = swap
        # stream() sample rate is CAPTURE_RATE / decim: 2 gives 24 kHz (the
        # firmware sums pairs, so the outer half aliases), 1 the full 48 kHz.
        self.decim = int(decim)
        # Kept on the instance so tuning and demodulation cannot disagree about
        # where the carrier was placed.
        self.offset = float(offset)
        self.corr = int(corr)
        self._corr_applied = False
        time.sleep(0.3)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self):
        if self.ser.is_open:
            self.ser.close()

    # ---- CLI ----------------------------------------------------------

    def command(self, line, wait=0.3):
        """Send one command and return whatever ASCII comes back."""
        self.ser.reset_input_buffer()
        self.ser.write((line + "\n").encode())
        time.sleep(wait)
        return self.ser.read(self.ser.in_waiting or 1).decode(errors="replace").strip()

    def start_adc(self, rate=None):
        # The crystal correction has to go in before the ADC starts: init()
        # resets the chip, which would stop SCKI and stall the capture.
        if self.corr and not self._corr_applied:
            self.command(f"init 8 {self.corr}", wait=1.0)
            self._corr_applied = True
        return self.command(f"adc start {int(rate)}" if rate else "adc start",
                            wait=0.6)

    def stop_adc(self):
        return self.command("adc stop")

    def tune(self, hz, offset=None):
        """Place the wanted carrier at +offset rather than at DC.

        The board's DC offset would otherwise sit exactly where the carrier is.
        Giving an offset here changes the board's configured one, so later
        tunes keep it -- the offset is part of where the board is tuned, not a
        one-off. Returns the LO frequency actually requested.

        Not callable while a stream is open: the port is mid-transfer. Close
        the stream generator first; it aborts the transfer on the way out.
        """
        if offset is not None:
            self.offset = float(offset)
        lo = (hz - self.offset) * TAYLOE_DIV
        self.command(f"clk 1 {int(lo)}", wait=0.15)
        return lo

    # ---- bulk transfers -----------------------------------------------

    def _read_header(self, keyword, timeout=5.0):
        """Headers announce their payload size, so we never have to guess."""
        header = b""
        deadline = time.time() + timeout
        while keyword not in header or not header.endswith(b"\n"):
            chunk = self.ser.read(1)
            if chunk:
                header += chunk
            elif time.time() > deadline:
                raise RuntimeError(f"no {keyword.decode()} header, got: {header!r}")
        parts = header.decode(errors="replace").strip().split()
        return int(parts[-2]), int(parts[-1])

    def capture(self, frames=4096):
        """One burst into the board's RAM, then transferred. Returns (iq, rate)."""
        frames = min(frames, MAX_CAPTURE)
        self.ser.reset_input_buffer()
        self.ser.write(f"adc capture {frames}\n".encode())

        got, rate = self._read_header(b"CAPTURE")
        if got == 0:
            raise RuntimeError("board captured 0 frames -- is the ADC started?")

        want = got * 8
        payload = self.ser.read(want)
        if len(payload) != want:
            raise RuntimeError(f"short read: {len(payload)} of {want} bytes")

        iq, _ = to_complex(payload, self.swap)
        return iq, rate

    def abort_stream(self):
        """Stop an in-progress stream so the CLI accepts commands again.

        The firmware aborts on any received byte. stream() calls this itself
        when it is closed early, so callers normally never need to.
        """
        self.ser.write(b"\n")
        time.sleep(0.05)
        self.ser.reset_input_buffer()

    def offset_fits(self, rate, bw=5000.0):
        """Whether the configured offset leaves the channel inside the band."""
        return self.offset + bw / 2 < 0.95 * rate / 2

    def stream(self, seconds=None, block_frames=1024):
        """Yield (iq_block, rate) until `seconds` elapse, or forever if None.

        A generator so both consumers can share it: one accumulates the blocks
        into a recording, the other publishes each as it arrives.

        To stop early -- e.g. to retune -- close it, ideally via
        contextlib.closing(). Closing mid-transfer aborts the firmware's stream
        so the CLI is ready for the next command. Just breaking out of a for
        loop is not enough: the generator then lingers until garbage
        collection, still owning a busy port.
        """
        remaining = seconds
        leftover = b""

        while True:
            chunk = STREAM_CHUNK_S if remaining is None else min(remaining, STREAM_CHUNK_S)
            if chunk <= 0:
                return

            self.ser.reset_input_buffer()
            self.ser.write(f"adc stream {int(max(1, chunk))} {self.decim}\n".encode())
            frames, rate = self._read_header(b"STREAM")

            want = frames * 8
            got = 0
            done = False
            try:
                while got < want:
                    raw = self.ser.read(min(block_frames * 8, want - got))
                    if not raw:
                        break                  # board stopped early
                    got += len(raw)

                    iq, leftover = to_complex(leftover + raw, self.swap)
                    if len(iq):
                        yield iq, rate
                done = True
            finally:
                # Only when closed mid-chunk: a finished chunk has nothing to
                # abort, and a stray byte there would just be noise to the CLI.
                if not done:
                    self.abort_stream()

            if remaining is not None:
                remaining -= chunk
                if remaining <= 0:
                    return
