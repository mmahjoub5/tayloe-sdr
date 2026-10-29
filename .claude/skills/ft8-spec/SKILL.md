---
name: ft8-spec
description: FT8/FT4 protocol reference from the Franke/Somerville/Taylor QEX 2020 paper (FT4_FT8_QEX.pdf, kept in this folder). Use when writing, checking or debugging the FT8 decoder/encoder in code/radiolib/radiolib/ft8 — message packing (77-bit payloads, i3.n3, c28/g15 fields), CRC-14, the (174,91) LDPC code, Gray map, Costas sync, GFSK waveform, soft-decision LLRs, BP/OSD decoding, signal subtraction, decode thresholds — or when asked "what does the paper say about X".
---

# FT8 / FT4 protocol (QEX July/Aug 2020)

Source: `FT4_FT8_QEX.pdf` in this folder. The facts below are condensed from it. For
anything not covered here, read the PDF with the `pages` parameter. The PDF is 11 pages:
PDF page 1 is QEX page 7.

| PDF page | Content |
|---|---|
| 1 | Intro; Table 1 (message types `i3.n3`) |
| 2 | Table 2 (bit-field tags); §3 CRC + LDPC; §4 channel symbols; Table 3 (Gray map) |
| 3 | FT4 Costas/ramp symbols; §5 CPFSK/GFSK equations; Table 4 (mode parameters) |
| 4 | GFSK pulse plots; FT8 raised-cosine ramp |
| 5 | §6 block detection, soft metric L_j, BP + OSD, AP decoding; Table 5 (thresholds) |
| 6 | Signal subtraction, multi-pass decoding; §7 QSO sequencing |
| 7 | Auto-sequencing state charts |
| 8 | §8 channel simulations; Table 6 (thresholds with AP) |
| 9 | Late-start/AP results; §9 licence rules; Appendix A starts |
| 10 | Appendix A: bit-field definitions, Table 7 (c28 values), FT4 XOR sequence |
| 11 | References ([14] = ft4_ft8_protocols.tgz: generator.dat, parity.dat, Fortran tools) |

## Frame
- 15 s slot, nominal start 0.5 s after the slot boundary. WSJT-X "DT" is relative to that.
- 79 symbols: `S, M_A(29), S, M_B(29), S`, where S = Costas `[3, 1, 4, 0, 6, 5, 2]` at
  symbols 0–6, 36–42 and 72–78. Data symbols are 7–35 and 43–71 (58 symbols).
- Symbol period T = 0.160 s, tone spacing 6.25 Hz (h = 1), 8 tones, ~50 Hz wide.
- Reported frequency = tone 0 (the lowest tone), not the centre.

## Bits
- 77-bit payload + 14-bit CRC = 91 bits, + 83 LDPC parity bits = 174-bit codeword
  (systematic: bits 0–90 are message+CRC, 91–173 are parity).
- 174 bits → 58 symbols, 3 bits each, MSB first, through the Gray map (Table 3):

  | symbol | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
  |---|---|---|---|---|---|---|---|---|
  | bits | 000 | 001 | 011 | 010 | 110 | 100 | 101 | 111 |

  In code: `GRAY = [0, 1, 3, 2, 6, 4, 5, 7]` (symbol → 3-bit value).

## CRC-14
- Polynomial 0x6757 (15 bits including x^14). In a 14-bit register that runs MSB first,
  the constant is `0x2757` and the mask is `0x3FFF`.
- Initial value 0, no reflection, no final XOR.
- Computed over the 77 payload bits **zero-extended to 82 bits**; the result is stored in
  codeword bits 77–90, MSB first.
- The direct (non-augmented) bitwise loop over 82 bits equals long division of
  (msg82 · x^14) by 0x6757. That has been verified in this project.

## LDPC (174, 91)
- Generator matrix: 83 × 91 (`generator.dat`). Parity-check matrix: sparse 83 × 174
  (`parity.dat`), 3 ones per column, 6–7 per row. A word is valid if all 83 checks sum to 0.
- WSJT-X decodes with BP first, then OSD if BP fails. Accept a decode only if the CRC matches.

## Soft decisions (§6)
- `L_j = K · (max |C_i| over symbols with bit j = 1 − max |C_i| over symbols with bit j = 0)`.
  K is tuned empirically.
- WSJT-X also uses block detection over N = 1, 2 and 3 symbols (8^N correlations) for
  about 0.7 dB of extra sensitivity.

## Waveform (§5)
- CPFSK with Gaussian-smoothed frequency pulses (GFSK), BT = 2 for FT8 (BT = 1 for FT4).
- `p(t) = 1/(2T) · [erf(kBT(t/T + 0.5)) − erf(kBT(t/T − 0.5))]`, with `k = π·sqrt(2/ln 2)`.
- The amplitude ramps over T/8 (20 ms) at the start and end with a raised cosine:
  `A(t) = 0.5·[1 − cos(8πt/T)]`.

## Decoding procedure (WSJT-X, §6)
1. Sync: find candidates (frequency offset, time offset).
2. Soft decisions for N = 1, 2, 3; try BP, then BP+OSD.
3. On a decode, subtract the reconstructed signal: `s'(t) = s(t) − 2·Re[g(t)·r(t)]`,
   where `g = LPF[s·r*]`.
4. Repeat for up to 3 passes while new signals keep decoding.

## Thresholds (SNR in 2500 Hz, 50% decode probability)
- FT8, AWGN: −19.6 dB (N = 1, BP), −20.3 dB (N = 1, 2, 3, BP), −20.8 dB (+OSD),
  −22.7 dB with maximum AP information.
- Mid-latitude disturbed channel: −16.5 / −17.0 / −18.6 dB.

## Message types (Table 1, Appendix A)
- `i3` (3 bits) selects the type; `i3 = 0` uses `n3` as a subtype.
- Standard message `i3 = 1`: `c28 r1 c28 r1 R1 g15 i3`.
- c28 special values (Table 7): DE = 0, QRZ = 1, CQ = 2, CQ nnn = 3–1002, CQ A–ZZZZ =
  1004–532443, 22-bit hashes from 2063592, standard calls from 6257896.
- g15: 4-character grid (32,400 values); spare values encode reports −30…+99, RRR,
  RR73, 73 and blank.
- f71 free text: up to 13 characters from
  ` 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ+-./?`.
- FT4 only: the 77 bits are XORed with a fixed pseudo-random sequence (page 10) before CRC/FEC.

## This project
- Code: `code/radiolib/radiolib/ft8/` (`from radiolib.ft8 import FT8, stft`):
  - `waterfall.py`: the STFT, on a 3.125 Hz × 0.08 s grid.
  - `codec.py`: decoding runs sync → `extract_data` → `soft_bits` → `ldpc_decode` (the
    `ldpc` package) → `crc_ok`. Encoding runs `encode` → `symbols` → `modulate`.
  - `pulse.py`: `Pulse` base class with `GaussianPulse` and `RectangularPulse`.
  - No gnuradio imports anywhere in `ft8/`. GNU Radio code lives in `code/gnu-radio/`
    (e.g. `hackrf/ft8_tx.py`).
  - Matrices: `lpdc-decoder.dat` (parity check) and `generator.dat`.
  - Demo: `python -m radiolib.ft8 [slot.wav]`.
- In `soft_bits`, linear tone power decodes weak signals better than dB.
  Positive LLR = bit 1.
- Real-signal test recordings with expected decodes are in ft8_lib `test/wav/` (12 kHz WAV
  + `.txt`).
- Licence (§9): the names "FT8"/"FT4" may be used only by implementations that follow these
  definitions; robotic/unattended QSOs must be disallowed.
