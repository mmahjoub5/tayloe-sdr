"""
ft8_stft.py - STFT waterfall block for an FT8 decoder.

Input : real audio, 12 kHz, one 15 s slot starting on the UTC boundary.
Output: Waterfall with
          power[t_idx, f_idx]  linear power grid
          t[t_idx]             symbol-start time (s) each row lines up with
          f[f_idx]             bin frequency (Hz)

Grid (defaults time_osr=2, freq_osr=2):
    time step = 0.16 s / 2   = 0.08 s   -> symbol k   is row    t + 2k
    freq bin  = 6.25 Hz / 2  = 3.125 Hz -> tone n     is column f + 2n
"""

from dataclasses import dataclass

import numpy as np
from scipy import signal

FS = 12000              # Hz
SYMBOL_PERIOD = 0.160   # s
TONE_SPACING = 6.25     # Hz  (= 1 / SYMBOL_PERIOD)
NUM_TONES = 8


@dataclass
class Waterfall:
    power: np.ndarray   # [n_frames, n_bins], linear
    t: np.ndarray       # [n_frames] seconds
    f: np.ndarray       # [n_bins]   Hz
    time_osr: int
    freq_osr: int

    @property
    def steps_per_symbol(self) -> int:
        return self.time_osr

    @property
    def bins_per_tone(self) -> int:
        return self.freq_osr

    def db(self) -> np.ndarray:
        return 10.0 * np.log10(self.power + 1e-20)

    def tone_bins(self, t_idx: int, f_idx: int) -> np.ndarray:
        """The 8 tone powers of the symbol at row t_idx, tone 0 at column f_idx."""
        stop = f_idx + NUM_TONES * self.freq_osr
        return self.power[t_idx, f_idx:stop:self.freq_osr]


_WINDOWS = {
    # name   : (scipy window, window length in symbols)
    "hann2": ("hann", 2),
    "hann1": ("hann", 1),
    "rect":  ("boxcar", 1),
}


def stft(x, fs: int = FS, time_osr: int = 2, freq_osr: int = 2,
         window: str = "hann2") -> Waterfall:
    """
    window:
      "hann2" - Hann over 2 symbols (3840 samples). Its first null is exactly
                one tone spacing (6.25 Hz) away, so a tone does not leak into
                its neighbour tone's bin. Same choice as ft8_lib. (default)
      "hann1" - Hann over 1 symbol + zero padding. Neighbour tone leaks at -6 dB.
      "rect"  - rectangular over 1 symbol + zero padding. Null at the neighbour
                tone only when perfectly aligned; -13 dB sidelobes otherwise.
    """
    nsym_f = fs * SYMBOL_PERIOD
    nsym = int(round(nsym_f))
    if abs(nsym - nsym_f) > 1e-9:
        raise ValueError(f"fs={fs} does not give an integer samples-per-symbol")
    if nsym % time_osr:
        raise ValueError("samples-per-symbol must divide evenly by time_osr")

    hop = nsym // time_osr          # 960 samples = 0.08 s
    nfft = nsym * freq_osr          # 3840 points  = 3.125 Hz bins

    if window not in _WINDOWS:
        raise ValueError(f"unknown window {window!r}")
    win_name, win_syms = _WINDOWS[window]
    wlen = nsym * win_syms          # 3840 for hann2, 1920 otherwise

    x = np.asarray(x, dtype=np.float64)
    if x.ndim != 1 or len(x) < wlen:
        raise ValueError("need 1-D audio at least one window long")

    f, t_center, Z = signal.stft(
        x, fs=fs,
        window=win_name,
        nperseg=wlen,
        noverlap=wlen - hop,     # hop = 960 samples = 0.08 s
        nfft=nfft,               # 3.125 Hz bins (zero-pads when wlen < nfft)
        boundary=None,           # no zero padding at the front: row 0 starts at sample 0
        padded=False,
        detrend=False,
        scaling="spectrum",      # Z = FFT / sum(window)
    )

    # scipy returns [freq, time]; we want [time, freq].
    # x2 so a sine of amplitude A centred on a bin reads A**2.
    power = (2.0 * np.abs(Z.T)) ** 2

    # scipy's t is the window centre. That window best captures the symbol
    # centred there, i.e. one that starts half a symbol earlier.
    t = t_center - (nsym / 2) / fs

    return Waterfall(power, t, f, time_osr, freq_osr)

