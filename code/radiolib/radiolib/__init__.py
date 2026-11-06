"""Host-side library for the Tayloe receiver board.

    hardware  what the board is -- constants, no I/O
    board     talking to it over serial (the only module that needs pyserial)
    dsp       processing what comes back
    io        writing results to disk

Everything public is re-exported here, so `from radiolib import demod` keeps
working regardless of which module it lives in. The board names load lazily,
so DSP and tests import cleanly on a machine without pyserial.
"""

from .dsp import (
    carrier_power,
    channel_filter,
    demod,
    equalize,
    iq_correct,
    iq_correct_carrier,
    modulation_spectrum,
    sideband_filter,
    spectrum,
    station_score,
)
from .hardware import (
    BASEBAND_FC_EQ,
    BASEBAND_FC_MLA30,
    BOARD_FLOOR_DBFS,
    CAPTURE_RATE,
    CSAMP,
    FULL_SCALE,
    OFFSET_HZ,
    PHASES,
    STREAM_BITS,
    STREAM_DECIM,
    STREAM_RATE,
    TAYLOE_DIV,
)
from .io import write_wav

_BOARD_NAMES = ("DEFAULT_PORT", "RadioBoard", "find_port", "to_complex")


def __getattr__(name):
    if name in _BOARD_NAMES:
        from . import board
        return getattr(board, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

__all__ = [
    "RadioBoard", "to_complex", "find_port", "DEFAULT_PORT",
    "BASEBAND_FC_EQ", "BASEBAND_FC_MLA30", "BOARD_FLOOR_DBFS", "CAPTURE_RATE",
    "CSAMP", "FULL_SCALE", "OFFSET_HZ", "PHASES", "STREAM_BITS", "STREAM_DECIM", "STREAM_RATE", "TAYLOE_DIV",
    "carrier_power", "channel_filter", "demod", "equalize", "iq_correct",
    "iq_correct_carrier", "modulation_spectrum", "sideband_filter", "spectrum",
    "station_score",
    "write_wav",
]
