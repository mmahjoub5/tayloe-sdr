"""Signal processing on what the board sends back.

    channel   move the wanted carrier to DC and isolate it
    measure   report on the signal: carrier level, spectrum, modulation
    calib     undo the board's I/Q imbalance and baseband roll-off
    demod     one channel in, audio out
"""

from .calib import equalize, iq_correct, iq_correct_carrier
from .channel import channel_filter
from .demod import demod, sideband_filter
from .measure import carrier_power, modulation_spectrum, spectrum, station_score
