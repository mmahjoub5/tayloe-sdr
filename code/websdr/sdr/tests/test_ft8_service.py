"""Tests for ft8_service.py with a stand-in for the decode_ft8 executable."""

import stat
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ft8_service as svc  # noqa: E402

OUTPUT = """000000 +12.5 +0.48 1200 ~  CQ K1ABC FN42
000000 -03.0 -1.20  612 ~  W9XYZ K1ABC -12
000000 +05.5 +0.50  900 ~  Error [3] while unpacking!
something else
"""


def test_parse_output():
    assert svc.parse_output(OUTPUT) == [
        {"hz": 1200, "dt": 0.48, "score": 25, "text": "CQ K1ABC FN42"},
        {"hz": 612, "dt": -1.2, "score": -6, "text": "W9XYZ K1ABC -12"},
    ]


@pytest.mark.parametrize("before,now,expected", [
    ((7074000, 1), (7074000, 1), True),
    ((7195000, 1), (7074000, 1), False),        # retuned during the slot
    ((7074000, 2), (7074000, 2), False),        # LSB
    ((7074500, 1), (7074500, 1), False),        # not an FT8 frequency
    (None, (7074000, 1), False),
    ((7074000, 1), None, False),
])
def test_should_decode(before, now, expected):
    assert svc.should_decode(before, now) is expected


def test_audio_buffer_keeps_the_latest():
    buf = svc.AudioBuffer(seconds=1)
    assert len(buf.latest()) == 0
    for i in range(30):
        buf.add(np.full(1000, i, dtype=np.float32))
    latest = buf.latest()
    assert len(latest) == svc.FS
    assert latest[-1] == 29 and latest[0] == 18


def fake_decoder(tmp_path, body):
    path = tmp_path / "decode_ft8"
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return str(path)


def test_decode_slot_writes_a_wav_and_parses(tmp_path):
    decoder = fake_decoder(tmp_path, f'cp "$1" {tmp_path}/seen.wav\necho "000000 +10.0 +0.50 1500 ~  CQ K1ABC FN42"')
    audio = np.random.default_rng(0).normal(0, 50.0, svc.SLOT_S * svc.FS).astype(np.float32)
    assert svc.decode_slot(audio, decoder)[0]["text"] == "CQ K1ABC FN42"
    rate, pcm = svc.wavfile.read(tmp_path / "seen.wav")
    assert rate == svc.FS and pcm.dtype == np.int16 and len(pcm) == len(audio)
    assert 2000 < pcm.std() < 4000               # the level no longer depends on the band


def test_decode_slot_reports_failure(tmp_path):
    audio = np.ones(1000, dtype=np.float32) + np.arange(1000)
    assert svc.decode_slot(audio, fake_decoder(tmp_path, "exit 3")) is None
    assert svc.decode_slot(audio, str(tmp_path / "missing")) is None


def test_decode_slot_silence_is_empty(tmp_path):
    assert svc.decode_slot(np.zeros(1000, dtype=np.float32), fake_decoder(tmp_path, "exit 3")) == []


def test_tuned_state():
    class Engine:
        def get_center(self): return 7069000.0
        def get_offset(self): return 5000.0
        def get_mode(self): return 1

    class Down:
        def get_center(self): raise ConnectionRefusedError("refused")

    assert svc.tuned_state(Engine()) == (7074000, 1)
    assert svc.tuned_state(Down()) is None
