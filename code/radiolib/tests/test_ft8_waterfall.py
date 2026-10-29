"""
test_waterfall.py - checks for the STFT waterfall block.

Every expected value is a literal worked out by hand from the defaults
(fs=12000, hann2, time_osr=2, freq_osr=2):
    window 3840 samples, hop 960 samples (0.08 s), nfft 3840 (3.125 Hz bins)
    15 s slot = 180000 samples -> (180000 - 3840) // 960 + 1 = 184 rows
    bins = 3840 // 2 + 1 = 1921 columns
    1500 Hz -> column 480, tone n at 1500 Hz -> column 480 + 2n
    row r -> t = 0.08 + 0.08 r

Run: python -m pytest tests/test_ft8_waterfall.py
"""

import numpy as np

from radiolib.ft8.waterfall import stft

n = np.arange(180000)   # 15 s at 12 kHz


def test_shape():
    wf = stft(np.zeros(180000))
    assert wf.power.shape == (184, 1921)


def test_time_axis():
    wf = stft(np.zeros(180000))
    assert np.isclose(wf.t[0], 0.08)
    assert np.isclose(wf.t[1], 0.16)
    assert np.isclose(wf.t[183], 14.72)


def test_freq_axis():
    wf = stft(np.zeros(180000))
    assert wf.f[0] == 0.0
    assert wf.f[1] == 3.125
    assert wf.f[480] == 1500.0


def test_sine_power():
    # amplitude 0.5 at 1500 Hz -> 0.25 in column 480, every row
    wf = stft(0.5 * np.sin(2 * np.pi * 1500 * n / 12000))
    assert np.allclose(wf.power[:, 480], 0.25, rtol=1e-3)


def test_db():
    wf = stft(0.5 * np.sin(2 * np.pi * 1500 * n / 12000))
    assert np.allclose(wf.db()[:, 480], -6.0206, atol=1e-3)


def test_neighbour_tone_is_empty():
    # hann2 nulls 6.25 Hz away: 1506.25 Hz (column 482) sees nothing
    wf = stft(np.sin(2 * np.pi * 1500 * n / 12000))
    assert np.all(wf.power[:, 482] < 1e-6)


def test_tone_bins():
    # 1518.75 Hz is tone 3 above 1500 Hz
    wf = stft(np.sin(2 * np.pi * 1518.75 * n / 12000))
    tones = wf.tone_bins(10, 480)
    assert len(tones) == 8
    assert tones.argmax() == 3


def test_burst_lands_on_its_row():
    # one symbol of 1500 Hz from 0.80 s to 0.96 s (samples 9600..11520)
    x = np.zeros(180000)
    x[9600:11520] = np.sin(2 * np.pi * 1500 * np.arange(1920) / 12000)
    wf = stft(x)
    assert wf.power[:, 480].argmax() == 9      # t[9] = 0.80 s


def test_bad_fs():
    try:
        stft(np.zeros(180000), fs=12345)
    except ValueError:
        return
    raise AssertionError("no ValueError")


def test_bad_time_osr():
    try:
        stft(np.zeros(180000), time_osr=7)
    except ValueError:
        return
    raise AssertionError("no ValueError")


def test_bad_window():
    try:
        stft(np.zeros(180000), window="blackman")
    except ValueError:
        return
    raise AssertionError("no ValueError")


def test_too_short():
    try:
        stft(np.zeros(3839))
    except ValueError:
        return
    raise AssertionError("no ValueError")


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in globals().items() if name.startswith("test_")]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {name}: {e!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(bool(failed))
