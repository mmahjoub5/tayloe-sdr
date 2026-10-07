"""Talking to the board over its serial CLI."""

import time

import numpy as np
import serial

DEFAULT_PORT = "/dev/cu.usbmodem1101"

TAYLOE_DIV = 4              # the detector divides the LO by four for quadrature
OFFSET_HZ = 3000.0          # park carriers here, clear of the board's DC offset
#
# Why you might want this larger: at 3 kHz a 5 kHz-wide channel spans -2 to
# +8 kHz, so DC sits *inside* it -- amplifier offset, LO self-mixing and 1/f
# noise all land in the passband where no channel filter can remove them. The
# I channel's DC offset on this board is about a quarter of peak amplitude.
# A larger offset moves the channel clear of DC and puts the I/Q image far
# enough away to be filtered.
#
# The ceiling is the streamed bandwidth: offset + bw/2 must stay inside
# rate/2. At ADC_DECIM 2 (24 kHz) that caps the offset near 9 kHz; reaching
# 15 kHz needs ADC_DECIM 1.
FULL_SCALE = 1 << 23        # 24-bit samples -> roughly +/-1.0

# Measured against KLOK's carrier (broadcast carriers hold to a few Hz): the
# 25 MHz crystal reads 3.09 ppm low. Uncorrected that is 44 Hz of error at
# 20 m, enough to pitch SSB voices audibly wrong. Applied at start_adc(),
# since the firmware's own init() defaults to zero and a board reset loses it.
XTAL_CORR_PPB = -3093
MAX_CAPTURE = 8192          # ADC_MAX_CAPTURE in audio_adc.h
STREAM_CHUNK_S = 120        # the firmware's per-stream limit


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
                 offset=OFFSET_HZ, corr=XTAL_CORR_PPB):
        self.ser = serial.Serial(port, baud, timeout=timeout)
        self.swap = swap
        # Kept on the instance so tuning and demodulation cannot disagree about
        # where the carrier was placed.
        self.offset = float(offset)
        self.corr = int(corr)
        self._corr_applied = False
        self._pending_tune = None
        self._tuned_to = None
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

    def request_tune(self, hz):
        """Queue a retune to be applied at a clean stream boundary.

        Retuning cannot happen from outside the stream loop: the generator is
        suspended mid-transfer and would resume reading the CLI's ASCII reply
        as if it were samples. Queuing lets the generator abort, retune and
        restart while it still owns the port.

        Returns False if already on that frequency -- each retune costs about a
        second of audio, so no-ops are worth skipping.
        """
        if self._tuned_to is not None and float(hz) == self._tuned_to:
            return False
        self._pending_tune = float(hz)
        return True

    def tune(self, hz, offset=None):
        """Place the wanted carrier at +offset rather than at DC.

        The board's DC offset would otherwise sit exactly where the carrier is.
        Uses the board's configured offset unless one is given here. Returns
        the LO frequency actually requested.
        """
        offset = self.offset if offset is None else float(offset)
        lo = (hz - offset) * TAYLOE_DIV
        self.command(f"clk 1 {int(lo)}", wait=0.15)
        self._tuned_to = float(hz)
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

        The firmware aborts on any received byte. Reads then time out, the
        generator's inner loop ends, and the next chunk is re-issued -- which
        is how retuning works without tearing the connection down.
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
        """
        remaining = seconds
        leftover = b""

        while True:
            chunk = STREAM_CHUNK_S if remaining is None else min(remaining, STREAM_CHUNK_S)
            if chunk <= 0:
                return

            self.ser.reset_input_buffer()
            self.ser.write(f"adc stream {int(max(1, chunk))}\n".encode())
            frames, rate = self._read_header(b"STREAM")

            want = frames * 8
            got = 0
            while got < want:
                raw = self.ser.read(min(block_frames * 8, want - got))
                if not raw:
                    break                      # board stopped early
                got += len(raw)

                iq, leftover = to_complex(leftover + raw, self.swap)
                if len(iq):
                    yield iq, rate

                if self._pending_tune is not None:
                    break

            # Applied here, between chunks, where nothing else is mid-read.
            if self._pending_tune is not None:
                self.abort_stream()
                self.tune(self._pending_tune)
                self._pending_tune = None
                leftover = b""
                continue

            if remaining is not None:
                remaining -= chunk
                if remaining <= 0:
                    return
