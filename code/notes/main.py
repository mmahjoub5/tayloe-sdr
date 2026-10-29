import matplotlib.pyplot as plt
from mixer import (
    generate_time_vector, generate_tone, modulate_am, modulate_dsb_sc, compute_spectrum, plot_spectrum,
    envelope_detector, plot_wave, coherent_detector
)

fs = 70e6
carrier_freq = 7e6
t = generate_time_vector(0.01, fs)
m_t = generate_tone(t, 1_000.0)
#s_t, _ = modulate_am(m_t, generate_tone(t, 7e6))
s_t, _ = modulate_dsb_sc(m_t, generate_tone(t, carrier_freq))
fc = 69e6

_, ax = plt.subplots()
# plot_wave(ax, t, [
#     (m_t,                          dict(color="tab:blue", lw=2, label="sent")),
#     (envelope_detector(s_t, fs) - 1, dict(color="tab:red", ls="--", label="recovered")),
# ], "Envelope detection", t_view_ms=3.0)

demodulated_signal = coherent_detector(s_t, t, fs=fs, fc=carrier_freq)
plot_wave(ax, t, [
    (m_t,                          dict(color="tab:blue", lw=2, label="sent")),
    (demodulated_signal, dict(color="tab:red", ls="--", label="recovered")),
], "Coherent detection", t_view_ms=3.0)

demodulated_signal_specturm = compute_spectrum(demodulated_signal, fc)

# _, ax_specturm = plt.subplots()
# plot_spectrum(mag=demodulated_signal_specturm[1], freqs=demodulated_signal_specturm[0], ax=ax_specturm, title="Specturm", f_range=(0,80e6))
_, ax_specturm = plt.subplots()
s_t_specturm = compute_spectrum(s_t, carrier_freq)
plot_spectrum(mag=s_t_specturm[1], freqs=s_t_specturm[0], ax=ax_specturm, title="Specturm", f_range=(0,carrier_freq))

# _, ax_ = plt.subplots()
# plot_wave(ax2, t, [
#     (s_t,                          dict(color="tab:blue", lw=2, label="sent")),
# ], "AM Signal", t_view_ms=3.0)

_, ax1 = plt.subplots()
plot_wave(ax1, t, [
    (s_t,                          dict(color="tab:blue", lw=2, label="sent")),
], "AM Signal", t_view_ms=3.0)


plt.show()

