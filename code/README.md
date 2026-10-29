# code

```
radio_cli/   firmware (RP2040 CLI: Si5351, PCM1808 capture/stream)
smoketest/   bring-up sketches and datasheets
radiolib/    host library -- everything below imports from here
  radiolib/hardware.py   what the board is: constants, no I/O
  radiolib/board.py      talking to it over serial (only module needing pyserial)
  radiolib/dsp/          channel, measure, calib, demod
  radiolib/io.py         writing results
  tests/                 synthetic-signal tests, no board needed
apps/        receiver tools: rx.py
bench/       measurement scripts: antenna, impedance, noise, peak
notes/       textbook mixer/detector models (no hardware)
gnu-radio/   flowgraphs by radio (board, rtlsdr, hackrf, sim); iq_bridge.py feeds board/
data/        captures (gitignored, except reference measurements)
```

## Setup

```sh
python3 -m venv .venv
.venv/bin/pip install -e "radiolib[test]" matplotlib
.venv/bin/python -m pytest radiolib        # no board needed
```

Run scripts from their own directory, e.g. `cd apps && ../.venv/bin/python rx.py --tune 7.2e6 --mode lsb --stream 30`.
Recordings default to `data/`.

Hardware facts go in `radiolib/hardware.py`, not in scripts. If a number was
measured on the board, it belongs there with a note on how it was measured.

GNU Radio: see `gnu-radio/README.md`.
