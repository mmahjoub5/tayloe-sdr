"""Host-side library for the Tayloe receiver board.

Split so the two consumers share everything but their output stage:
`board` talks to the hardware, `dsp` processes what comes back.
"""

from .board import (
    RadioBoard,
    to_complex,
    DEFAULT_PORT,
    FULL_SCALE,
    OFFSET_HZ,
    TAYLOE_DIV,
)
from .dsp import (
    carrier_power,
    channel_filter,
    demod,
    equalize,
    iq_correct,
    iq_correct_carrier,
    modulation_spectrum,
    spectrum,
    station_score,
    write_wav,
)

__all__ = [
    "RadioBoard", "to_complex", "DEFAULT_PORT", "FULL_SCALE",
    "OFFSET_HZ", "TAYLOE_DIV",
    "carrier_power", "channel_filter", "demod", "equalize", "iq_correct", "iq_correct_carrier", "modulation_spectrum", "spectrum", "station_score",
    "write_wav",
]
