"""
Embedded Python Block: FT8 decoder.

Paste into an Embedded Python Block in board/ft8_receiver.grc, inline on the
real SSB audio (DC Blocker -> this -> resampler); audio passes through. At every
UTC 15 s boundary it decodes the last 30 s in a background thread, so the
flowgraph never stalls, and prints each new message to the console.

Decoding lives in radiolib; this file is buffering and output only.
"""

import threading
import time
from math import gcd

import numpy as np
from gnuradio import gr
from radiolib.ft8 import FS, FT8, stft
from scipy.signal import resample_poly

SLOT_S = 15
WINDOW_S = 30   # two slots, so a transmission off the slot boundaries still fits whole


class blk(gr.sync_block):
    """Decode FT8 from real SSB audio, passing the audio through."""

    def __init__(self, samp_rate=24000, dial_hz=7.074e6):
        """
        Set up the audio buffer.

        Args:
            samp_rate (int): input sample rate, Hz
            dial_hz (float): receiver dial frequency, Hz, added to audio frequency for RF
        """
        gr.sync_block.__init__(self, name="FT8 Decoder", in_sig=[np.float32],
                               out_sig=[np.float32])
        self.samp_rate = int(samp_rate)
        # same name as the parameter, so GRC updates it when the dial moves
        self.dial_hz = dial_hz
        self._ft8 = FT8()
        self._chunks, self._n = [], 0
        self._slot = None
        self._busy = threading.Lock()
        self._seen = []

    def work(self, input_items, output_items):
        """
        Pass the audio through, keeping the last 30 s and starting a decode at each UTC slot boundary.

        Args:
            input_items (list of np.ndarray): one float32 audio stream
            output_items (list of np.ndarray): the same audio, unchanged

        Returns:
            int: number of samples produced
        """
        x = input_items[0]
        output_items[0][:] = x
        now = time.time()
        self._chunks.append(x.copy())
        self._n += len(x)
        while self._n - len(self._chunks[0]) >= WINDOW_S * self.samp_rate:
            self._n -= len(self._chunks.pop(0))

        slot = int(now // SLOT_S)
        if slot != self._slot:
            first = self._slot is None
            self._slot = slot
            enough = self._n >= 13 * self.samp_rate
            # skip this boundary if the previous decode is still running
            if not first and enough and self._busy.acquire(blocking=False):
                audio = np.concatenate(self._chunks)
                threading.Thread(target=self._decode, args=(audio, now), daemon=True).start()
        return len(output_items[0])

    def _decode(self, audio, t_end):
        """
        Decode one window and print each message not already reported.

        Args:
            audio (np.ndarray): up to 30 s of audio at samp_rate
            t_end (float): UNIX time of the last sample, s
        """
        try:
            g = gcd(FS, self.samp_rate)
            y = resample_poly(audio - audio.mean(), FS // g, self.samp_rate // g)
            wf = stft(y, fs=FS)
            t_start = t_end - len(audio) / self.samp_rate
            for t0, f0, score, payload in self._ft8.decode(wf):
                t = t_start + float(wf.t[t0])
                hexp = f"{int(''.join(map(str, payload)), 2):020x}"
                # consecutive windows overlap by 15 s, so most messages turn up twice
                if any(abs(t - ts) < 1.0 and hexp == p for ts, p in self._seen):
                    continue
                self._seen.append((t, hexp))
                f = float(wf.f[f0])
                stamp = time.strftime("%H:%M:%S", time.gmtime(t)) + f"{t % 1:.1f}"[1:]
                print(f"FT8 {stamp} UTC  {f:7.1f} Hz  {self.dial_hz + f:10.0f} Hz  "
                      f"sync {score:5.1f}  {hexp}", flush=True)
            self._seen = [(ts, p) for ts, p in self._seen if ts > t_end - 2 * WINDOW_S]
        finally:
            self._busy.release()
