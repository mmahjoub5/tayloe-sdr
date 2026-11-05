# radio

## radiolib board (`code/radiolib/radiolib/board.py`)

`RadioBoard` talks to the receiver board's serial CLI (firmware in `code/radio_cli/`) on a Seeed XIAO RP2040.

- The port is found automatically: `find_port()` picks the `/dev/cu.*` port with USB vendor ID `0x2E8A` (`RP2040_VID`). macOS names the port after the USB socket it's plugged into (`usbmodem101`, `usbmodem1101`, ...), so don't hardcode it. `DEFAULT_PORT` is `None`, meaning auto-detect.
- Pass `port=` (or `--port` in `apps/rx.py` and `gnu-radio/iq_bridge.py`) only to choose between two RP2040 boards.
- `RadioBoard(decim=2)` (or `board.decim`) picks the `stream()` rate: the firmware's `adc stream [secs] [decim]` sends 48 kHz / decim (`STREAM_DECIM = 2` in `hardware.py`, so 24 kHz by default). 48 kHz works from the Mac but not from the Pi 3B+, which can't read the board faster than ~192 KB/s.
- Only one program can open the port. "Resource busy" usually means the Arduino IDE's Serial Monitor (`serial-monitor`) still has it open.

## radiolib FT8 (`code/radiolib/radiolib/ft8/`)

FT8 encode/decode for the receiver board, built from the QEX 2020 paper (see the `ft8-spec` skill).

- `codec.py`: the `FT8` class (modulate/decode), `crc14`, LDPC matrix loaders, `load_slot` (reads a mono WAV, pads or trims it to 15 s). Uses the `ldpc` package's `BpDecoder`. Audio rate `FS = 12000`.
- `decode()` drops the all-zero payload: it passes LDPC and CRC, so noise can decode to it.
- `pulse.py`: `Pulse` ABC with `RectangularPulse` and `GaussianPulse` (GFSK).
- `waterfall.py`: `stft()` -> `Waterfall`. Defaults: 2x time and 2x frequency oversampling, so 0.08 s rows, 3.125 Hz bins, 184 x 1921 per 15 s slot.
- **Never import gnuradio (or pmt) anywhere in `radiolib/ft8`.** GNU Radio code lives in `code/gnu-radio/` as standalone scripts that import radiolib, never the other way round.
- `generator.dat` and `lpdc-decoder.dat` hold the LDPC generator and parity-check matrices; they ship as package data (`ft8/*.dat` in `pyproject.toml`). The `lpdc` misspelling is the real filename, referenced by `H_FILE` in `codec.py`; rename both together if you fix it.

Run the demo and tests from `code/radiolib/`:

    python -m radiolib.ft8                 # synthetic slot: random messages + noise
    python -m radiolib.ft8 slot.wav        # decode a mono 15 s recording
    python -m pytest tests/test_ft8_waterfall.py

## FT8 TX (`code/gnu-radio/hackrf/ft8_tx.py`)

A standalone script that writes one 15 s FT8 slot (signal starting 0.5 s in) as a mono 16-bit WAV. `ssb_tx.grc` plays it with its stock WAV File Source.

    python ft8_tx.py <77-bit payload hex> -o ft8_48k.wav [--rate 48000 --f0 1500]

`--rate` must equal the flowgraph's `samp_rate`, because WAV File Source does not resample. The payload is hex (the format the decoder prints), since radiolib can't pack message text into a payload yet.

The WAV plays from when the flowgraph starts, not on a UTC slot boundary. That doesn't matter for our own decoder, which searches for the start time. WSJT-X or another station needs the start within about ±2 s of :00/:15/:30/:45.

## GNU Radio flowgraphs

Write and edit `.grc` files with the `grc-maker` skill (house style, chains, headless rules, a renderer that checks
the layout). The board SSB flowgraphs (`board/ssb_receiver.grc`, `ft8_receiver.grc`) demodulate **LSB only**: their
phasing arms are added, which cancels the upper sideband, so FT8 (USB) comes out mirrored. `websdr/sdr/engine.grc`
has a `sideband` sign and does both. See `code/CLAUDE.md` TODOs.

## FT8 RX (`code/gnu-radio/ft8_rx.py`)

A standalone script that works with either receiver. In `board/ssb_receiver.grc` or `rtlsdr/ssb_receiver.grc`, add a stock WAV File Sink beside the Audio Sink (same input and rate) and record. Then:

    python ft8_rx.py rx.wav [--dial 7.074e6]

It resamples to `FS` (12 kHz) and decodes 30 s windows every 15 s, so the recording needn't be slot-aligned. A transmission found by two overlapping windows is printed once (same payload within 1 s). Decoding runs at about 0.3x real time (50 s of audio takes ~15 s).

## FT8 RX, live (`code/gnu-radio/ft8_decoder_block.py`)

Code for an Embedded Python Block in `board/ft8_receiver.grc`; paste the file into the block. It sits inline on the real float SSB audio (DC Blocker -> block -> resampler) at `samp_rate` (24 kHz) and passes the audio through unchanged, with parameters `samp_rate` and `dial_hz`. At each UTC 15 s boundary it decodes the last 30 s in a background thread, so `work()` and the Qt GUI sinks never stall, and prints `FT8 <UTC> <audio Hz> <RF Hz> sync <score> <payload hex>` to the console. There is no message port. If a decode is still running at the next boundary, that boundary is skipped. Messages already reported (same payload within 1 s) aren't repeated. Like `gr_tuner_block.py`, it lives in `gnu-radio/` and imports radiolib, never the reverse.
