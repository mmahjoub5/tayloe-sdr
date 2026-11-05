---
name: grc-maker
description: Write or edit GNU Radio Companion flowgraphs (.grc YAML) for this repo in the owner's style, e.g. in code/gnu-radio/ or code/websdr/. Use whenever asked to make, change, fix or review a .grc file, build a receiver/transmitter chain (AM, SSB phasing, FT8, FM, CW) for the Tayloe board, RTL-SDR or HackRF, make a headless (no_gui) flowgraph, or paste an Embedded Python Block into one.
---

# Writing GRC flowgraphs

GNU Radio 3.10.12 in the `gr` conda env (`conda activate gr`). Tools:

    GR=/opt/homebrew/Caskroom/miniforge/base/envs/gr
    $GR/bin/grcc -o <scratch dir> file.grc          # compile check, writes file.py
    $GR/bin/python scripts/grc_render.py file.grc out.png   # picture + overlap check (section 9)
    $GR/share/gnuradio/grc/blocks/<id>.block.yml    # a block's parameter ids and defaults

`scripts/` is relative to this skill's folder (`.claude/skills/grc-maker/`).

Reference: GNU Radio tutorials, https://wiki.gnuradio.org/index.php?title=Tutorials
(Beginner Tutorials for flowgraph basics; Embedded Python Block; Python Block Message Passing; ZMQ and XMLRPC blocks).

The best example of the house style is `code/gnu-radio/board/ft8_receiver.grc` (the newest). Read it before
writing a board flowgraph. `board/ssb_demo.grc` is a copied tutorial (author Barry Duggan); don't copy its style.

## 1. File layout
- Only the `.grc` is committed. GRC writes `<name>.py` and `<name>_<block>.py` beside it; they are gitignored
  (`code/gnu-radio/*/*.py`). Hand-written scripts live at the top of `code/gnu-radio/`.
- Folders by hardware: `board/` (fed by `iq_bridge.py`), `rtlsdr/`, `hackrf/`, `sim/` (no hardware).
- New flowgraph: add a line to `code/gnu-radio/README.md`'s file list.

## 2. Writing the YAML by hand
- Top-level keys in this order: `options`, `blocks`, `connections`, `metadata`
  (`file_format: 1`, `grc_version: 3.10.12.0`).
- `options.parameters`: `author: aminmahjoub`, `id` = file stem, a real `title` (not "Not titled yet"),
  `generate_options: qt_gui` (desktop) or `no_gui` (headless), `output_language: python`, `run_options: prompt`,
  `window_size: (1000,1000)` (1400,1000 for many plots).
- Every block has `name`, `id`, `parameters`, `states` (`coordinate`, `rotation: 0`, `state: enabled`).
- Parameters may be partial: GRC fills defaults on load and writes the full set when the user saves. Only set what
  differs from the default, and look the ids up in the `.block.yml`, never from memory.
- Values are strings of Python expressions: `'24000'`, `samp_rate`, `'10**(volume/20)'`,
  `'firdes.low_pass(1, samp_rate, 3000, 500)'`, enums like `window.WIN_HAMMING`.
- Connections: `- [src_name, '0', dst_name, '0']`.
- Always compile with `grcc` afterwards and fix every error. `grcc` prints "Compilation error" on failure, so
  grep for it, don't rely on the exit code. The "no flow control / add a Throttle" warning is fine when a hardware
  or ZMQ source sets the pace.

## 3. Naming
- Variables: `samp_rate`, `audio_sample` (48000 for the audio sink), `frequency`, `volume`, `rfGain` (HackRF/RTL),
  `input_gain`. One rate variable per rate actually used; don't add unused `samp_rate_0` copies.
- Rename blocks that matter to the reader (`ft8_decoder`, `display_decim`, `audio_level`, `ft8_waterfall`, `views`).
  Plumbing keeps GRC's auto names (`blocks_add_xx_0`, `freq_xlating_fir_filter_xxx_0`).
- Plot `name`s say what is shown, with units: `Board I/Q (RF Hz)`, `FT8 band (audio Hz)`, `Audio level`.
  Spell "spectrum" right (older files say "Specturm").
- Slider `label`s carry units: `Dial frequency (Hz)`, `Volume (dB)`.

## 4. Rates and gains
- Never hardcode a sample rate inside a block: use `samp_rate`, `samp_rate/4`, `audio_sample`. The board streams
  24 kHz by default but 48 kHz exists (`radiolib.STREAM_DECIM`), so a rate must change in one place.
- Volume is a `variable_qtgui_range` in dB (`-100..10`, step 0.1, default -6), applied as
  `blocks_multiply_const_vxx` with `const: 10**(volume/20)`. Older files multiply by the raw value; use dB.
- Audio out: `rational_resampler_xxx` `fff` interp 2 (24 → 48 kHz), then `audio_sink` at `audio_sample` with
  `ok_to_block: 'True'`. For WSJT-X set `device_name: BlackHole 2ch`.

## 5. Board receive chains (`board/`)
Source, always the same:

    zeromq_sub_source  address tcp://127.0.0.1:5555, type complex, bind False, timeout 100
      → epy_block "Board Tuner" (freq: frequency)   # paste gr_tuner_block.py
      → freq_xlating_fir_filter_xxx                 # center_freq = the carrier offset

The carrier sits above DC by the offset: 3000 Hz for AM, 5000 Hz for SSB (radiolib `OFFSET_HZ`). The xlating
filter's `center_freq` must match what the bridge tunes with.

- **SSB (phasing)**, from `board/ssb_receiver.grc` / `ft8_receiver.grc`:
  xlating `ccf`, taps `firdes.low_pass(1, samp_rate, 3000, 500)` → `analog_agc2_xx` complex (attack `7e-2`,
  decay `1e-3`, reference `0.3`, gain `1.0`, max_gain `1e6`) → split:
  `complex_to_real` → `blocks_delay` 127, and `complex_to_imag` → `hilbert_fc` 255 taps Hamming →
  `complex_to_imag`; `blocks_add_xx` float → `dc_blocker_xx` ff length 128 long_form → volume → resampler → sink.
  The delay is `(hilbert taps - 1) / 2`; change both together. **Adding the arms (`real + H(imag)`) gives LSB**; USB needs a -1 on the Hilbert arm (or a Subtract). For both,
  use a `sideband` variable on a Multiply Const before the Add, as `websdr/sdr/engine.grc` does. The older
  `board/ssb_receiver.grc` / `ft8_receiver.grc` are LSB only. Check new chains with a known tone above and below
  the carrier.
- **AM**, from `board/am_receiver.grc`: xlating `ccc` center 3000, taps `firdes.low_pass(1, samp_rate, 5000, 1000)`
  → `analog_am_demod_cf` (chan_rate `samp_rate`, audio_pass 5000, audio_stop 5500) → `high_pass_filter` 200 Hz
  (width 100) → resampler → volume → sink. AM Demod wants a carrier near 1.0; `iq_bridge.py --gain` sets that.
- **FT8**: the SSB chain with `ft8_decoder` (paste `ft8_decoder_block.py`; `samp_rate: samp_rate`,
  `dial_hz: frequency`) inline after the DC blocker, plus `display_decim` (resampler decim 4) feeding the FT8 plots.

## 6. Other hardware
- **RTL-SDR** (`rtlsdr/`): `rtlsdr_source`, `rfGain` slider; WFM via `rational_resampler` → `analog_wfm_rcv`
  (quad_rate `48000*4`, audio_decimation 4).
- **HackRF TX** (`hackrf/`): `soapy_hackrf_sink` (type fc32, samp_rate 2e6, `vga: rfGain` int slider 0–47,
  amp False), with `blocks_conjugate_cc` just before it. Audio from `blocks_wavfile_source`
  (`code/gnu-radio/audio/`, gitignored) through `fft_filter_xxx` low-pass 3 kHz and `hilbert_fc`.

## 7. Plots (qt_gui only)
- I/Q right after the tuner: `qtgui_freq_sink_x` (fftsize 1024, Blackman-Harris, ymin -140, ymax 10),
  `qtgui_time_sink_x` (size 1024), `qtgui_waterfall_sink_x` (fftsize 4096, `fc: frequency-<offset>` so the axis
  is RF Hz, `bw: samp_rate`).
- Audio: freq/waterfall sinks with `type: float`, `freqhalf: 'False'`.
- `grid: 'True'`. With several plots, use a `qtgui_tab_widget` named `views` and `gui_hint`s like
  `'views@0: 0,0,2,2'`; sliders on row 0 (`'0,0,1,2'`, `'0,2,1,2'`), tabs below (`'1,0,10,4'`).

## 8. Headless flowgraphs (`no_gui`, e.g. the WebSDR engine)
- No `qtgui_*` blocks; sliders become plain `variable` blocks.
- Add `xmlrpc_server` with `addr: 127.0.0.1` (never `0.0.0.0`; it has no auth). Every variable then gets
  `set_<name>()`/`get_<name>()` over XML-RPC.
- Outputs go out on `zeromq_pub_sink` (address `tcp://127.0.0.1:<port>`, bind True), one per stream.
- Pick modes with `blocks_selector` (`input_index: mode`), not by enabling or disabling blocks.

## 9. Layout and readability
GRC's default view hides block IDs, so on the canvas a block is known only by its title, its shown parameters,
where it sits and its comment. Two blocks of the same type (two Frequency Xlating filters) look identical unless
their row or comment says which is which. Renaming blocks helps the generated code, not the picture.

- **Rows:** variables along the top (y = 12, a second row at y = 100 if needed), the XML-RPC Server at the end
  of that row. Signal chains start below the variables' comments (y >= 200). One row per branch (e.g. AM above,
  SSB below, waterfall at the bottom), flowing left to right; a merge (Selector, Add) sits between the rows it
  joins.
- **Spacing:** variables 120 px apart in x. Leave at least 40 px between one block's output port and the next
  block's input port, so the wire shows; set x from the previous block's real width (the render report gives
  it), not a fixed step. Coordinates on a 4 px grid.
- **Comments** draw under the block with no wrapping, so a long one runs into neighbours or across wires.
  Keep each to a short phrase (about the width of its block, ~25 characters): `AM, ±5 kHz`,
  `(hilbert taps - 1) / 2`, `6 kHz for the FT8 plots`. Use them to name a branch and to explain a value that
  would look wrong; say a shared fact once (e.g. on the XML-RPC Server: `sets center, offset, mode, volume`),
  not on every variable.
- **Check it:** after every change run `scripts/grc_render.py` and look at the PNG (Read it). It uses GRC's own
  canvas code, so sizes match the GUI, and prints `overlaps` (boxes within 8 px, comments included), `tight`
  (blocks within 40 px) and validation `errors`. Fix until all three say none, then look at the picture for
  wires crossing blocks and rows that are hard to follow.
- Aim for under ~2500 px wide; if a chain runs longer, tighten the spacing before adding a row.

## 10. Embedded Python Blocks
- The source of truth is a file in `code/gnu-radio/` (`gr_tuner_block.py`, `ft8_decoder_block.py`). Put its exact
  text in the block's `_source_code`; after editing the file, re-paste it into every flowgraph that uses it.
  The tuner copies in `board/*.grc` are currently an older version (no `offset` parameter); refresh them when
  touching those files.
- Their docstrings follow the `code-comments` skill. They may import radiolib; radiolib never imports gnuradio.
