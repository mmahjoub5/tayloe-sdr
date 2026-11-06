# gnu-radio

```
iq_bridge.py        board -> ZMQ (tcp://127.0.0.1:5555), tune requests on :5556
tune.py             retune the bridge from a terminal
rpc.py              call a running flowgraph's XML-RPC Server block (set_/get_ a variable)
gr_tuner_block.py   source of the "Board Tuner" Embedded Python Block
board/              flowgraphs fed by iq_bridge.py
  am_receiver.grc
  ssb_receiver.grc  phasing SSB with AGC, waterfall
  ssb_demo.grc      SSB with USB/LSB chooser
  ssb_scope.grc     just scopes on the bridge output
rtlsdr/             flowgraphs for an RTL-SDR dongle
  fm_receiver.grc
  ssb_receiver.grc
hackrf/             transmit through a HackRF
  ssb_tx.grc        plays audio/tidal_48k.wav as SSB
  cw_tx.grc
sim/                no hardware
  ssb_phasing.grc
  wav_scope.grc     WAV -> low-pass -> audio, with spectrum/waterfall/scope/level; cutoff set over XML-RPC
  fast_multiply.grc
audio/              test audio (gitignored)
```

Only the `.grc` files are kept. GRC writes `<name>.py` (and
`<name>_epy_block_0.py`) beside each one when you generate or run it; those are
gitignored. The Board Tuner block is pasted into the flowgraphs, so after
editing `gr_tuner_block.py` paste it back into each `board/` flowgraph.

## Run

```sh
conda activate gr
python iq_bridge.py --tune 1.17e6     # leave running
gnuradio-companion board/am_receiver.grc
```

Retune without GRC: `python tune.py 1170e3`.

RTL-SDR check without GRC:

```sh
rtl_fm -f 92.3M -M wbfm - | play -r 32k -t raw -e signed -b 16 -c 1 -V1 -
```
