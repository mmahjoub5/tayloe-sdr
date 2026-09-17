"""Capture I/Q from the radio board and demodulate it.

The Tayloe detector hands us quadrature baseband; tuning happens on the board
(clk 1 = 4 x the wanted frequency), so everything here works at baseband.

    python rx.py --tune 1.17e6 --mode am
    python rx.py --scan                      # sweep the AM broadcast band
    python rx.py --tune 1.17e6 --stream 30   # 30 seconds of audio

Protocol and DSP live in radiolib; this file is argument parsing and output.
"""

import argparse
import sys

import numpy as np
from radiolib import (
    OFFSET_HZ,
    RadioBoard,
    carrier_power,
    demod,
    spectrum,
    write_wav,
)

AM_BAND = (530e3, 1700e3)   # broadcast band
AM_STEP = 10e3              # Americas channel spacing; Europe uses 9 kHz


def demod_opts(args):
    """Filter settings for demod(), from the command line."""
    if args.narrow:
        return dict(bw=2500, audio_band=(300, 2400), offset=args.offset)
    return dict(bw=args.bw, offset=args.offset)


def report_carrier(iq, rate, offset=OFFSET_HZ):
    cnr, side = carrier_power(iq, rate, offset)
    print(f"carrier-to-noise: {cnr:+.1f} dB at "
          f"{'+' if side > 0 else '-'}{offset:.0f} Hz")
    return side


def scan(board, frames, start, stop, step, offset=OFFSET_HZ):
    results = []
    freq = start
    while freq <= stop:
        board.tune(freq)
        try:
            iq, rate = board.capture(frames)
        except RuntimeError as e:
            print(f"  {freq/1e3:7.0f} kHz  capture failed: {e}")
            freq += step
            continue

        cnr, side = carrier_power(iq, rate, offset)
        results.append((freq, cnr))
        mark = "  <--" if cnr > 6 else ""
        print(f"  {freq/1e3:7.0f} kHz   {cnr:+6.1f} dB  "
              f"{'+' if side > 0 else '-'}{mark}")
        freq += step

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    ap.add_argument("--tune", type=float, default=1.17e6, help="Hz to listen on")
    ap.add_argument("--mode", default="am", choices=["am", "sam", "usb", "lsb"],
                    help="sam = synchronous AM, ~3 dB better on a weak station")
    ap.add_argument("--bw", type=float, default=5000,
                    help="channel filter bandwidth in Hz")
    ap.add_argument("--offset", type=float, default=OFFSET_HZ,
                    help="Hz to park the carrier away from DC; larger keeps "
                         "the channel clear of DC artifacts and the I/Q image")
    ap.add_argument("--narrow", action="store_true",
                    help="2.5 kHz channel, 300-2400 Hz audio: trades top end "
                         "for noise, worth it on a marginal signal")
    ap.add_argument("--seconds", type=float, default=0.17, help="burst length")
    ap.add_argument("--stream", type=float, default=0,
                    help="seconds of continuous audio instead of a burst")
    ap.add_argument("--out", default="rx.wav")
    ap.add_argument("--no-tune", action="store_true")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--start", type=float, default=AM_BAND[0])
    ap.add_argument("--stop", type=float, default=AM_BAND[1])
    ap.add_argument("--step", type=float, default=AM_STEP)
    args = ap.parse_args()

    kw = {"port": args.port} if args.port else {}
    with RadioBoard(offset=args.offset, **kw) as board:
        print(board.start_adc())

        if args.scan:
            print(f"scanning {args.start/1e3:.0f}-{args.stop/1e3:.0f} kHz, "
                  f"carrier-to-noise at +/-{args.offset:.0f} Hz:")
            results = scan(board, int(args.seconds * 48000),
                           args.start, args.stop, args.step, args.offset)
            results.sort(key=lambda r: -r[1])
            print("\nstrongest:")
            for f, c in results[:8]:
                print(f"  {f/1e3:7.0f} kHz   {c:+6.1f} dB")
            return

        if not args.no_tune:
            lo = board.tune(args.tune)
            print(f"tuned {args.tune/1e6:.4f} MHz  (lo {lo/1e6:.4f} MHz)")

        if args.stream and not board.offset_fits(24000, args.bw):
            print(f"warning: {args.offset:.0f} Hz offset does not fit the "
                  f"24 kHz stream; use --seconds (48 kHz capture) or set "
                  f"ADC_DECIM 1 in the firmware")

        if args.stream:
            print(f"streaming {args.stream:.0f}s...")
            blocks, rate = [], None
            for iq, rate in board.stream(args.stream):
                blocks.append(iq)
                secs = sum(len(b) for b in blocks) / rate
                print(f"\r  {secs:6.1f} s", end="", flush=True)
            print()
            iq = np.concatenate(blocks)
        else:
            iq, rate = board.capture(int(args.seconds * 48000))

        print(f"got {len(iq)} frames at {rate} Hz ({len(iq)/rate:.2f} s), "
              f"|iq| max {np.abs(iq).max():.4f}")

        side = report_carrier(iq, rate, args.offset)

        if not args.stream:
            print("\nstrongest bins (offset from centre):")
            for f, d in spectrum(iq, rate):
                print(f"  {f:+9.1f} Hz   {d:6.1f} dB")

        np.save(args.out.replace(".wav", "_iq.npy"), iq)
        audio = demod(iq, rate, args.mode, side, **demod_opts(args))
        write_wav(args.out, audio, rate)
        print(f"\nwrote {args.out}  ({args.mode}, {len(audio)/rate:.1f}s)"
              f" and {args.out.replace('.wav', '_iq.npy')}")


if __name__ == "__main__":
    sys.exit(main())
