# notes

Signal-processing sandbox for the 7 MHz radio build — a NumPy/SciPy model of the
mixer stage. Generates a baseband message and an RF carrier, modulates them
(AM/DSB-FC and DSB-SC), demodulates them back (envelope and coherent detection),
and plots each stage in both the time and frequency domain.

Everything lives in `mixer.py`. Nothing here talks to the board; for that, see
`../apps/`.

## Setup

Uses the shared environment in `code/.venv` (see `../README.md`).

## Run

```sh
python mixer.py
```

Opens a 2×2 figure for the DSB-SC case: message in time and frequency, modulated
signal in time and frequency. Edit the parameters at the bottom of `mixer.py` to
change the run.

## Parameters

Set in the `__main__` block:

| Name | Default | Meaning |
| --- | --- | --- |
| `fm_hz` | 1 kHz | Message (baseband) frequency |
| `fc_hz` | 7 MHz | Carrier frequency |
| `am_v` / `ac_v` | 1.0 V | Message / carrier amplitude |
| `ka_val` | 0.5 | AM modulation index factor |
| `sim_duration` | 10 ms | Sim length — sets FFT resolution (1/T = 100 Hz) |
| `sampling_rate` | 10 × `fc_hz` | 70 MS/s, well above Nyquist for a clean carrier |

## Module map

**Signal generation**

- `generate_time_vector(duration, fs)` — the timebase every other function takes.
- `generate_tone(t, freq, amplitude, initial_phase)` — a cosine. Used for both
  the message `m(t)` and the carrier `c(t)`.

**Modulation** — each returns `(signal, envelope)`; the lower envelope is
`-envelope`.

- `modulate_am(m_t, c_t, ac, ka)` — standard AM with carrier:
  `s(t) = Ac·[1 + ka·m(t)]·cos(2πfc·t)`. Spectrum has a carrier line plus sidebands.
- `modulate_dsb_sc(m_t, c_t)` — suppressed carrier: `s(t) = m(t)·c(t)`.
  Sidebands only, and the envelope has the phase reversals to prove it.

**Analysis and demodulation**

- `compute_spectrum(signal, fs)` — normalized single-sided amplitude spectrum,
  returns `(freqs, magnitude)` in Hz and volts.
- `butter_lowpass_filter(data, cutoff_freq, fs, order)` — Butterworth low-pass.
  Uses second-order sections (`sosfiltfilt`) on purpose: cutoff/nyquist here is
  about 6e-5, and a plain `b, a` + `lfilter` goes numerically unstable at that
  ratio and diverges. Keep it that way if you lower the cutoff further.
- `envelope_detector(signal, fs, cutoff_freq)` — Hilbert-transform envelope,
  low-passed to strip carrier ripple. Works on AM, not on DSB-SC.
- `coherent_detector(signal, t, fc, fs, phase_error_deg, cutoff_freq, ac_local)` —
  product detector for DSB-SC. Multiplies by a local oscillator and low-passes,
  giving `v_o(t) = 0.5·Ac·Ac_local·cos(φ)·m(t)`. The 0.5 and the `cos(φ)` fall
  out of the trig expansion, so `phase_error_deg=60` really does halve the output.

## Plotting

Three primitives that compose, rather than one function per figure:

- `style_axis(ax, title, xlabel, ylabel)` — the shared look (bold title, dashed grid).
- `plot_wave(ax, t, traces, title, t_view_ms)` — time domain. `traces` is a list
  of `(y, kwargs)` pairs passed straight to `ax.plot`, so one trace or five is
  the same call. Slices to the view window and adds a legend if any trace is labelled.
- `plot_spectrum(ax, freqs, mag, title, f_range, color, marks)` — frequency domain
  in kHz. `marks` is a list of `(freq_hz, label, height_fraction)` annotations;
  `sideband_marks(fc, fm, with_carrier)` builds the usual LSB/carrier/USB set.

`plot_modulation_analysis(t, m_t, signal, envelope, fs, fm, fc, name, with_carrier)`
is just those four calls arranged 2×2. It computes its own spectra, so you pass
signals, not FFTs. Use `name=` for the titles and `with_carrier=False` for DSB-SC.

Composing a one-off panel:

```python
import matplotlib.pyplot as plt
from mixer import (
    generate_time_vector, generate_tone, modulate_am,
    envelope_detector, plot_wave,
)

fs = 70e6
t = generate_time_vector(0.01, fs)
m_t = generate_tone(t, 1_000.0)
s_t, _ = modulate_am(m_t, generate_tone(t, 7e6))

_, ax = plt.subplots()
plot_wave(ax, t, [
    (m_t,                          dict(color="tab:blue", lw=2, label="sent")),
    (envelope_detector(s_t, fs) - 1, dict(color="tab:red", ls="--", label="recovered")),
], "Envelope detection", t_view_ms=3.0)
plt.show()
```

## Notes

- `am_fft.png` and `am_textbook_style.png` are saved output from earlier runs.
- The detectors are verified against theory: the envelope detector recovers
  `1 + 0.5·m(t)` to within ~0.017 V, and coherent detection hits the textbook
  0.5 gain with a `cos(φ)` phase penalty.
- Filter transients settle over the first few ms; ignore the edges when
  comparing a demodulated trace against the original message.
