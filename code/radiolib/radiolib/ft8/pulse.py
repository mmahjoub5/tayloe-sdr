"""Frequency-pulse shapes for continuous-phase FSK modulators."""

from abc import ABC, abstractmethod

import numpy as np
from scipy.special import erf


class Pulse(ABC):
    """Base class: subclass, set `span` and implement `shape` to add a new pulse."""

    span = 1   # symbols one pulse covers; odd, centred on its own symbol

    @abstractmethod
    def shape(self, nsps: int) -> np.ndarray:
        """
        Frequency-deviation pulse of one symbol, peak 1.

        Args:
            nsps (int): samples per symbol

        Returns:
            np.ndarray: shape [span * nsps]
        """

    def frequency(self, tones, nsps: int, f0_hz: float, spacing_hz: float,
                  fs: float) -> np.ndarray:
        """
        Instantaneous frequency of a tone sequence, sum of one pulse per symbol.

        Args:
            tones (array-like of int): tone index of each symbol
            nsps (int): samples per symbol
            f0_hz (float): frequency of tone 0, Hz
            spacing_hz (float): tone spacing, Hz
            fs (float): sample rate, Hz

        Returns:
            np.ndarray: shape [len(tones) * nsps], rad/sample
        """
        pad = self.span // 2
        tones = list(tones)
        padded = [tones[0]] * pad + tones + [tones[-1]] * pad   # edges hold the end tones
        pulse = self.shape(nsps)
        step = 2 * np.pi * spacing_hz / fs

        dphi = np.full((len(padded) + 2 * pad) * nsps, 2 * np.pi * f0_hz / fs)
        for j, tone in enumerate(padded):
            dphi[j * nsps:(j + self.span) * nsps] += step * tone * pulse
        return dphi[2 * pad * nsps:(2 * pad + len(tones)) * nsps]

    def waveform(self, tones, nsps: int, f0_hz: float, spacing_hz: float,
                 fs: float) -> np.ndarray:
        """
        Continuous-phase sine wave following the tone sequence.

        Args:
            tones (array-like of int): tone index of each symbol
            nsps (int): samples per symbol
            f0_hz (float): frequency of tone 0, Hz
            spacing_hz (float): tone spacing, Hz
            fs (float): sample rate, Hz

        Returns:
            np.ndarray: shape [len(tones) * nsps], amplitude 1
        """
        return np.sin(np.cumsum(self.frequency(tones, nsps, f0_hz, spacing_hz, fs)))


class RectangularPulse(Pulse):
    """Plain FSK: the frequency jumps at each symbol boundary."""

    span = 1

    def shape(self, nsps: int) -> np.ndarray:
        """
        Flat pulse lasting one symbol.

        Args:
            nsps (int): samples per symbol

        Returns:
            np.ndarray: shape [nsps], all ones
        """
        return np.ones(nsps)


class GaussianPulse(Pulse):
    """GFSK: a rectangular pulse smoothed by a Gaussian filter (QEX paper eq. 3)."""

    span = 3

    def __init__(self, bt: float = 2.0):
        """
        Set the smoothing bandwidth.

        Args:
            bt (float): -3 dB bandwidth x symbol time; 2.0 for FT8, 1.0 for FT4
        """
        self.bt = bt

    def shape(self, nsps: int) -> np.ndarray:
        """
        Gaussian-smoothed pulse over 3 symbols.

        Args:
            nsps (int): samples per symbol

        Returns:
            np.ndarray: shape [3 * nsps], peak 1
        """
        k = np.pi * np.sqrt(2 / np.log(2))
        t = (np.arange(self.span * nsps) - self.span * nsps / 2) / nsps   # in symbol times
        return 0.5 * (erf(k * self.bt * (t + 0.5)) - erf(k * self.bt * (t - 0.5)))
