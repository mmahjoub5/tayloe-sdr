from pathlib import Path

import numpy as np
from ldpc import BpDecoder
from scipy.io import wavfile

from .pulse import GaussianPulse, Pulse
from .waterfall import Waterfall

COSTAS = [3, 1, 4, 0, 6, 5, 2]
BLOCK = [0, 36, 72]
NUM_SYMBOLS = 79
DATA_SYMBOLS = list(range(7, 36)) + list(range(43, 72))   # 58 symbols between the Costas blocks
GRAY = [0, 1, 3, 2, 6, 4, 5, 7]   # channel symbol -> 3 FT8 bits (Table 3)
H_FILE = Path(__file__).with_name("lpdc-decoder.dat")
G_FILE = Path(__file__).with_name("generator.dat")
CRC_POLY = 0x2757   # 0x6757 from the spec, x^14 term implied
FS = 12000


def load_parity_check(path=H_FILE) -> np.ndarray:
    """The 83x174 LDPC parity-check matrix. Each data line is one column: its 3 rows (1-83)."""
    H = np.zeros((83, 174), dtype=np.uint8)
    col = 0
    for line in open(path):
        rows = line.split()
        if len(rows) == 3 and all(r.isdigit() for r in rows):
            for r in rows:
                H[int(r) - 1, col] = 1
            col += 1
    return H


def crc14(bits) -> int:
    """CRC-14 of a 0/1 sequence, MSB first, initial value 0."""
    reg = 0
    for b in bits:
        top = (reg >> 13) & 1
        reg = (reg << 1) & 0x3FFF
        if top ^ b:
            reg ^= CRC_POLY
    return reg


def load_generator(path=G_FILE) -> np.ndarray:
    """
    Read the LDPC generator matrix, one 91-character row of 0/1 per parity bit.

    Args:
        path (str or Path): generator file

    Returns:
        np.ndarray: shape [83, 91], parity = G @ (message + CRC) mod 2
    """
    rows = [line.strip() for line in open(path)]
    rows = [r for r in rows if len(r) == 91 and set(r) <= {"0", "1"}]
    return np.array([[int(c) for c in r] for r in rows], dtype=np.uint8)


def load_slot(path: str) -> tuple:
    """
    Read a mono WAV and pad or trim it to one 15 s slot.

    Args:
        path (str): WAV file

    Returns:
        tuple: (np.ndarray audio of shape [15 * fs], int sample rate)
    """
    fs, x = wavfile.read(path)
    if x.ndim > 1:
        x = x[:, 0]
    x = x.astype(float)
    n = 15 * fs
    return np.pad(x, (0, max(0, n - len(x))))[:n], fs


class FT8:
    def __init__(self, dial_hz=7.074e6):
        self.dial_hz = dial_hz
        H = load_parity_check()
        self.ldpc = BpDecoder(H, error_rate=0.1, max_iter=30, bp_method="product_sum")
        self.G = load_generator()

    def decode(self, input_signal: Waterfall):
        results = []
        found = set()
        for t0, f0, score in self.find_candidates(input_signal):
            energies = self.extract_data(input_signal, t0, f0)
            llrs = self.soft_bits(energies)
            bits = self.ldpc_decode(llrs)
            if bits is None or not self.crc_ok(bits):
                continue
            payload = bits[:77]
            # the all-zero codeword passes LDPC and CRC, so noise can decode to it
            if not payload.any():
                continue
            # neighbouring candidates of one signal decode to the same message
            if payload.tobytes() in found:
                continue
            found.add(payload.tobytes())
            # TODO: unpack the 77-bit payload into text
            results.append((t0, f0, score, payload))
        return results

    def crc_ok(self, bits) -> bool:
        """CRC over the 77 message bits zero-extended to 82, against bits 77-90."""
        return crc14(list(bits[:77]) + [0] * 5) == int("".join(map(str, bits[77:91])), 2)

    def sync_score(self, wf: Waterfall, t0: int, f0: int) -> float:
        """Expected-tone energy / average of the other 7, over the 21 Costas symbols."""
        expected = 0.0
        others = 0.0
        for block in BLOCK:
            for k, tone in enumerate(COSTAS):
                p = wf.tone_bins(t0 + (block + k) * wf.steps_per_symbol, f0)
                expected += p[tone]
                others += (p.sum() - p[tone]) / 7
        return expected / others

    def extract_data(self, wf: Waterfall, t0: int, f0: int) -> np.ndarray:
        """The 8 tone energies of each of the 58 data symbols, shape [58, 8]."""
        return np.array([wf.tone_bins(t0 + k * wf.steps_per_symbol, f0)
                         for k in DATA_SYMBOLS])

    def soft_bits(self, energies: np.ndarray, k: float = 1.0) -> np.ndarray:
        """
        174 LLRs from the [58, 8] tone energies, 3 bits per symbol, MSB first.

        L_j = K * (max C_i over tones with bit j = 1 - max C_i over tones with bit j = 0),
        C_i = tone power (linear; dB decodes weak signals worse). Positive means 1,
        negative means 0, and the size is the confidence.
        """
        llrs = []
        for row in energies:
            for bit in (2, 1, 0):
                zero = max(row[t] for t in range(8) if not (GRAY[t] >> bit) & 1)
                one = max(row[t] for t in range(8) if (GRAY[t] >> bit) & 1)
                llrs.append(k * (one - zero))
        return np.array(llrs)

    def ldpc_decode(self, llrs: np.ndarray):
        """174 LLRs (positive = 1) -> the 174 corrected bits, or None if parity never checks."""
        llrs = llrs * np.sqrt(24 / np.var(llrs))    # same scaling as ft8_lib, into natural-log units
        self.ldpc.update_channel_probs(1 / (1 + np.exp(np.abs(llrs))))   # chance each hard bit is wrong
        bits = self.ldpc.decode((llrs > 0).astype(np.uint8))
        return bits if self.ldpc.converge else None

    def find_candidates(self, wf: Waterfall, max_candidates=50, min_score=2.0):
        """Best (t0, f0, score) candidates, with neighbours of a better one dropped."""
        n_rows, n_cols = wf.power.shape
        last_t0 = n_rows - (NUM_SYMBOLS - 1) * wf.steps_per_symbol
        last_f0 = n_cols - 8 * wf.bins_per_tone

        scores = []
        for t0 in range(last_t0):
            for f0 in range(last_f0):
                scores.append((self.sync_score(wf, t0, f0), t0, f0))
        scores.sort(reverse=True)

        candidates = []
        for score, t0, f0 in scores:
            if score < min_score or len(candidates) == max_candidates:
                break
            # a signal also scores 1 symbol / 1 tone either side of itself
            near = any(abs(t0 - t) <= wf.steps_per_symbol and abs(f0 - f) <= wf.bins_per_tone
                       for t, f, _ in candidates)
            if not near:
                candidates.append((t0, f0, score))
        return candidates

    def encode(self, payload) -> np.ndarray:
        """77 payload bits -> 174-bit codeword: payload, CRC-14, 83 parity bits."""
        payload = np.asarray(payload, dtype=np.uint8)
        crc = crc14(list(payload) + [0] * 5)
        m91 = np.concatenate([payload, [(crc >> (13 - i)) & 1 for i in range(14)]]).astype(np.uint8)
        return np.concatenate([m91, self.G @ m91 % 2]).astype(np.uint8)

    def symbols(self, payload) -> np.ndarray:
        """77 payload bits -> the 79 channel tones (0-7), Costas blocks included."""
        cw = self.encode(payload)
        tones = np.zeros(NUM_SYMBOLS, dtype=int)
        for block in BLOCK:
            tones[block:block + 7] = COSTAS
        for i, k in enumerate(DATA_SYMBOLS):
            tones[k] = GRAY.index(cw[3 * i] * 4 + cw[3 * i + 1] * 2 + cw[3 * i + 2])
        return tones

    def modulate(self, payload, f0_hz: float = 1500.0, fs: float = FS,
                 pulse: Pulse = None) -> np.ndarray:
        """
        Turn 77 payload bits into 12.64 s of FT8 audio, to be placed 0.5 s into the slot.

        Args:
            payload (array-like of int): 77 message bits
            f0_hz (float): frequency of tone 0, Hz
            fs (float): sample rate, Hz
            pulse (Pulse): frequency pulse shape; GaussianPulse(bt=2.0) if None

        Returns:
            np.ndarray: shape [79 * 0.16 * fs], peak amplitude 1
        """
        pulse = pulse or GaussianPulse(bt=2.0)
        nsps = int(fs * 0.16)
        x = pulse.waveform(self.symbols(payload), nsps, f0_hz, 6.25, fs)

        # raised-cosine ramp over T/8 at both ends (paper section 5)
        n = nsps // 8
        ramp = 0.5 * (1 - np.cos(np.pi * np.arange(n) / n))
        x[:n] *= ramp
        x[-n:] *= ramp[::-1]
        return x
