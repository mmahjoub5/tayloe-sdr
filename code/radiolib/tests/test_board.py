import numpy as np
import pytest

pytest.importorskip("serial")
from radiolib import FULL_SCALE, to_complex


def frames(*pairs):
    return np.array(pairs, dtype="<i4").tobytes()


def test_to_complex_keeps_partial_sample():
    raw = frames((FULL_SCALE, 0), (0, FULL_SCALE))
    iq, left = to_complex(raw[:13], swap=False)
    assert len(iq) == 1 and left == raw[8:13]
    iq2, left2 = to_complex(left + raw[13:], swap=False)
    np.testing.assert_allclose(iq2, [1j])
    assert left2 == b""


def test_swap_conjugates():
    raw = frames((0, FULL_SCALE))
    np.testing.assert_allclose(to_complex(raw, swap=True)[0], [-1j])


class FakeSerial:
    """Records writes; answers `adc stream` with a header and `frames` of payload."""

    def __init__(self, frames=4096, rate=24000):
        self.frames, self.rate = frames, rate
        self.writes = []
        self.rx = b""
        self.is_open = True
        self.in_waiting = 0

    def write(self, data):
        self.writes.append(data)
        if data.startswith(b"adc stream"):
            self.rx = f"STREAM {self.frames} {self.rate}\n".encode() + bytes(self.frames * 8)

    def read(self, n):
        out, self.rx = self.rx[:n], self.rx[n:]
        return out

    def reset_input_buffer(self):
        pass

    def close(self):
        self.is_open = False


@pytest.fixture
def board(monkeypatch):
    import radiolib.board as rb
    monkeypatch.setattr(rb.time, "sleep", lambda s: None)
    monkeypatch.setattr(rb.serial, "Serial", lambda *a, **k: FakeSerial())
    return rb.RadioBoard(port="/dev/fake")


def test_stream_closed_early_aborts(board):
    from contextlib import closing
    with closing(board.stream()) as s:
        next(s)
    assert board.ser.writes[-1] == b"\n"


def test_stream_finished_sends_no_abort(board):
    blocks = list(board.stream(seconds=1))
    assert sum(len(b) for b, _ in blocks) == board.ser.frames
    assert b"\n" not in board.ser.writes


def test_stream_sends_decim(board):
    list(board.stream(seconds=1))
    assert board.ser.writes[0] == b"adc stream 1 2\n"
    board.decim = 1
    list(board.stream(seconds=1))
    assert board.ser.writes[-1] == b"adc stream 1 1\n"


def test_tune_offset_persists(board):
    board.tune(7.2e6, 6000)
    assert board.ser.writes[-1] == f"clk 1 {int((7.2e6 - 6000) * 4)}\n".encode()
    assert board.offset == 6000
    board.tune(7.1e6)
    assert board.ser.writes[-1] == f"clk 1 {int((7.1e6 - 6000) * 4)}\n".encode()
