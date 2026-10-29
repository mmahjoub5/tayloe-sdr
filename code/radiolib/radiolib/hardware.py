"""What the board is: measured and designed facts, in one place.

No I/O and no third-party imports, so anything -- DSP, tests, offline analysis
of a saved capture -- can use these without pyserial installed. `board.py`
imports from here, never the other way round.
"""

# ---- tuning ------------------------------------------------------------

TAYLOE_DIV = 4              # the detector divides the LO by four for quadrature
OFFSET_HZ = 3000.0          # park carriers here, clear of the board's DC offset
#
# Why you might want this larger: at 3 kHz a 5 kHz-wide channel spans -2 to
# +8 kHz, so DC sits *inside* it -- amplifier offset, LO self-mixing and 1/f
# noise all land in the passband where no channel filter can remove them. The
# I channel's DC offset on this board is about a quarter of peak amplitude.
# A larger offset moves the channel clear of DC and puts the I/Q image far
# enough away to be filtered.
#
# The ceiling is the streamed bandwidth: offset + bw/2 must stay inside
# rate/2. At ADC_DECIM 2 (24 kHz) that caps the offset near 9 kHz; reaching
# 15 kHz needs ADC_DECIM 1.

# Measured against KLOK's carrier (broadcast carriers hold to a few Hz): the
# 25 MHz crystal reads 3.09 ppm low. Uncorrected that is 44 Hz of error at
# 20 m, enough to pitch SSB voices audibly wrong. Applied at start_adc(),
# since the firmware's own init() defaults to zero and a board reset loses it.
XTAL_CORR_PPB = -3093

# ---- ADC and transfer --------------------------------------------------

FULL_SCALE = 1 << 23        # 24-bit samples -> roughly +/-1.0

# The two paths run at different rates. Prefer the rate capture()/stream()
# hand back; these are for sizing a request before there is one.
CAPTURE_RATE = 48000        # capture(): one burst into board RAM
STREAM_RATE = 24000         # stream(): ADC_DECIM 2 in the firmware
STREAM_DECIM = 2            # stream()'s default; 1 sends the full CAPTURE_RATE

MAX_CAPTURE = 8192          # ADC_MAX_CAPTURE in audio_adc.h
STREAM_CHUNK_S = 120        # the firmware's per-stream limit

# ---- analog front end --------------------------------------------------

PHASES = 4                  # Tayloe sampling phases
CSAMP = 100e-9              # C40-C43 sampling caps

# The sampling caps and the antenna's source impedance set one baseband pole,
# BW = 1/(2*pi*PHASES*Rs*CSAMP) -- so the corner is NOT a board constant, it
# moves with the antenna. impedance.py / antenna.py measure it.
BASEBAND_FC_MLA30 = 3375.0  # measured with the MLA-30+ connected (impedance.py)
BASEBAND_FC_EQ = 2700.0     # equalize()'s fit; antenna at the time unrecorded

BOARD_FLOOR_DBFS = -76.4    # noise floor with the antenna disconnected
