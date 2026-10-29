import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import hilbert, butter, sosfiltfilt

# ==========================================
# Signal Generation & Processing Functions
# ==========================================


def generate_time_vector(duration: float, fs: float) -> np.ndarray:
    """Generate a discrete time vector."""
    num_samples = int(duration * fs)
    return np.arange(num_samples) / fs


def generate_tone(
    t: np.ndarray,
    freq: float,
    amplitude: float = 1.0,
    initial_phase: float = 0.0,
) -> np.ndarray:
    """Generate a cosine tone. Used for both the message m(t) and carrier c(t)."""
    return amplitude * np.cos(2 * np.pi * freq * t + initial_phase)


def modulate_am(
    m_t: np.ndarray, c_t: np.ndarray, ac: float = 1.0, ka: float = 0.5
) -> tuple[np.ndarray, np.ndarray]:
    """Standard AM (DSB-FC) with carrier component:

    s(t) = Ac * [1 + ka * m(t)] * cos(2*pi*fc*t)

    Returns (signal, envelope). The lower envelope is just -envelope.
    """
    envelope = ac * (1.0 + ka * m_t)
    carrier_normalized = c_t / np.max(np.abs(c_t))
    return envelope * carrier_normalized, envelope


def modulate_dsb_sc(
    m_t: np.ndarray, c_t: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Double-Sideband Suppressed-Carrier (DSB-SC):

    s(t) = m(t) * c(t)

    Returns (signal, envelope).
    """
    return m_t * c_t, np.abs(m_t)


def compute_spectrum(signal: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    """Compute normalized single-sided amplitude spectrum."""
    n = len(signal)
    freqs = np.fft.rfftfreq(n, d=1.0 / fs)
    magnitude = np.abs(np.fft.rfft(signal)) / (n / 2.0)
    magnitude[0] /= 2.0
    return freqs, magnitude


# ==========================================
# Demodulation Functions
# ==========================================


def butter_lowpass_filter(
    data: np.ndarray, cutoff_freq: float, fs: float, order: int = 5
) -> np.ndarray:
    """Butterworth low-pass filter.

    Uses second-order sections: the cutoff/nyquist ratio here is tiny (kHz
    baseband vs a MHz sample rate) and a plain b/a filter goes unstable there.
    """
    sos = butter(order, cutoff_freq / (0.5 * fs), btype="low", output="sos")
    return sosfiltfilt(sos, data)


def envelope_detector(
    signal: np.ndarray, fs: float, cutoff_freq: float = 2_000.0
) -> np.ndarray:
    """Demodulate an AM signal using an envelope detector (Hilbert transform),
    then low-pass filter to remove carrier ripple.
    """
    envelope = np.abs(hilbert(signal))
    return butter_lowpass_filter(envelope, cutoff_freq=cutoff_freq, fs=fs)


def coherent_detector(
    signal: np.ndarray,
    t: np.ndarray,
    fc: float,
    fs: float,
    phase_error_deg: float = 0.0,
    cutoff_freq: float = 2_000.0,
    ac_local: float = 1.0,
) -> np.ndarray:
    """Coherent (product) detection of a DSB-SC signal:

    v_o(t) = 0.5 * Ac * Ac_local * cos(phi) * m(t)

    The 0.5 and the cos(phi) fall out of the trig expansion, so multiplying by
    the local oscillator and low-pass filtering is all that is needed.
    """
    phi = np.deg2rad(phase_error_deg)
    local_oscillator = ac_local * np.cos(2 * np.pi * fc * t + phi)
    product = signal * local_oscillator
    return butter_lowpass_filter(product, cutoff_freq=cutoff_freq, fs=fs)


# ==========================================
# Plotting Primitives
# ==========================================


def style_axis(ax, title: str, xlabel: str, ylabel: str) -> None:
    """Apply the shared look: bold title, labels, dashed grid."""
    ax.set_title(title, fontsize=12, fontweight="bold")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(True, linestyle="--", alpha=0.6)


def plot_wave(ax, t, traces, title: str, t_view_ms: float = 1.4) -> None:
    """Plot one or more time-domain traces over a window in milliseconds.

    traces: list of (y, kwargs) pairs passed straight to ax.plot.
    """
    window = t <= (t_view_ms * 1e-3)
    for y, kwargs in traces:
        ax.plot(t[window] * 1e3, y[window], **kwargs)
    ax.set_xlim(0, t_view_ms)
    style_axis(ax, title, "Time (ms)", "Amplitude (V)")
    if any("label" in kwargs for _, kwargs in traces):
        ax.legend(loc="upper right")


def plot_spectrum(ax, freqs, mag, title: str, f_range, color="tab:blue", marks=()):
    """Plot a single-sided spectrum in kHz.

    f_range: (f_min, f_max) in Hz.
    marks: list of (freq_hz, label, height_fraction) annotations.
    """
    ax.stem(
        freqs / 1e3,
        mag,
        linefmt=color,
        markerfmt="o",
        basefmt="k-",
    )
    peak = np.max(mag)
    ax.set_xlim(f_range[0] / 1e3, f_range[1] / 1e3)
    ax.set_ylim(0, peak * 1.25)
    style_axis(ax, title, "Frequency (kHz)", "Magnitude (V)")
    for freq, label, height in marks:
        ax.text(
            freq / 1e3,
            peak * height,
            label,
            ha="center",
            va="bottom",
            fontsize=9,
        )


def sideband_marks(fc: float, fm: float, with_carrier: bool = True):
    """Standard LSB / carrier / USB annotations for a modulated spectrum."""
    marks = [
        (fc - fm, f"LSB\n{(fc - fm) / 1e3:.0f} kHz", 0.35),
        (fc + fm, f"USB\n{(fc + fm) / 1e3:.0f} kHz", 0.35),
    ]
    if with_carrier:
        marks.append((fc, f"Carrier\n{fc / 1e3:.0f} kHz", 1.05))
    return marks


# ==========================================
# Figure Composition
# ==========================================


def plot_modulation_analysis(
    t: np.ndarray,
    m_t: np.ndarray,
    signal: np.ndarray,
    envelope: np.ndarray,
    fs: float,
    fm: float,
    fc: float,
    name: str = "AM",
    with_carrier: bool = True,
    t_view_ms: float = 1.4,
) -> None:
    """2x2 view: message and modulated signal, each in time and frequency."""
    freqs_m, mag_m = compute_spectrum(m_t, fs)
    freqs_s, mag_s = compute_spectrum(signal, fs)

    _, axes = plt.subplots(2, 2, figsize=(13, 8))

    plot_wave(
        axes[0, 0],
        t,
        [(m_t, dict(color="tab:blue", lw=2))],
        r"Modulating Signal $m(t)$ (Time Domain)",
        t_view_ms,
    )
    plot_spectrum(
        axes[0, 1],
        freqs_m,
        mag_m,
        r"Message Spectrum $|M(f)|$",
        f_range=(0, 5 * fm),
    )
    plot_wave(
        axes[1, 0],
        t,
        [
            (signal, dict(color="black", lw=0.5, label=r"$s(t)$")),
            (envelope, dict(color="red", ls="--", lw=1.2, label="Envelope")),
            (-envelope, dict(color="red", ls="--", lw=1.2)),
        ],
        rf"Modulated {name} Signal $s(t)$ (Time Domain)",
        t_view_ms,
    )
    plot_spectrum(
        axes[1, 1],
        freqs_s,
        mag_s,
        rf"{name} Signal Spectrum $|S(f)|$",
        f_range=(fc - 5 * fm, fc + 5 * fm),
        color="tab:red",
        marks=sideband_marks(fc, fm, with_carrier),
    )

    plt.tight_layout()
    plt.show()


# ==========================================
# Execution / Main
# ==========================================

if __name__ == "__main__":
    # Parameters
    fm_hz = 1_000.0  # 1 kHz
    fc_hz = 7_000_000.0  # 7 MHz
    am_v = 1.0  # 1.0 V
    ac_v = 1.0  # 1.0 V
    ka_val = 0.5  # Modulation index factor
    sim_duration = 0.010  # 10 ms (100 Hz FFT resolution)
    sampling_rate = 10 * fc_hz  # 70 MS/s

    t_arr = generate_time_vector(duration=sim_duration, fs=sampling_rate)
    m_t_arr = generate_tone(t_arr, freq=fm_hz, amplitude=am_v)
    c_t_arr = generate_tone(t_arr, freq=fc_hz, amplitude=ac_v)

    dsb_signal, dsb_env = modulate_dsb_sc(m_t_arr, c_t_arr)
    plot_modulation_analysis(
        t=t_arr,
        m_t=m_t_arr,
        signal=dsb_signal,
        envelope=dsb_env,
        fs=sampling_rate,
        fm=fm_hz,
        fc=fc_hz,
        name="DSB-SC",
        with_carrier=False,
    )
