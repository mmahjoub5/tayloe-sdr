# radio_cli

Serial CLI for the Tayloe receiver board (Seeed XIAO RP2040, arduino-pico core).
Open a serial monitor at **115200 baud**, one command per line.

Board: Si5351 clock gen on I2C (0x60, SDA=D4/GPIO6, SCL=D5/GPIO7), PCM1808 audio
ADC in master mode reading over PIO I2S (DOUT=D6, BCK=D2, LRCK=D3). SCKI comes
from Si5351 **CLK0** at 256·fs — nothing downstream runs until that clock does.

## Commands

| Command | What it does |
| --- | --- |
| `help` | this list |
| `gpio` | all pins with live levels |
| `gpio <pad\|gpio>` | one pin plus a 2 ms activity scan, e.g. `gpio D4` or `gpio 6` |
| `freq <pad\|gpio>` | hardware edge count in Hz; **odd GPIOs only** (PWM B channel) |
| `pull <pad\|gpio> up\|down\|none` | set the internal pull (tells pickup from a driven line) |
| `probe` | does the Si5351 ACK its address |
| `status` | device status register 0, decoded |
| `reg <addr>` | read a register (`0x..` or decimal) |
| `reg <addr> <val>` | write a register |
| `clk <0\|1\|2> <hz>` | set CLK n frequency in plain hertz |
| `clk <0\|1\|2> on\|off` | enable or disable CLK n |
| `init [pf] [corr]` | re-init the Si5351; `pf` is 0, 6, 8 or 10 (default 8), `corr` in ppb |
| `reset` | reset both PLLs |
| `adc start [rate]` | start SCKI on CLK0, then capture (default 48000 Hz) |
| `adc stop` | stop capture and SCKI |
| `adc read [frames]` | read frames, report min/max per channel (1..4096, default 256) |
| `adc capture [frames]` | binary I/Q dump for the host (1..8192, default 4096) |
| `adc stream [secs] [decim] [bits]` | continuous I/Q (1..120 s, default 5); `decim` 2 = 24 kHz (default), 1 = full 48 kHz; `bits` 32 (default) or 24 (packed, 6 B/frame) |
| `adc stats` | the last stream's frames produced and overruns (frames dropped because the host read too slowly) |
| `bootsel` | reboot into the UF2 bootloader (the `RPI-RP2` drive), to flash a `.uf2` without pressing BOOT |

## Pin map

| Pad | GPIO | Net |
| --- | --- | --- |
| D0 | 26 | SET_FF_N |
| D1 | 27 | RST_FF_N |
| D2 | 28 | BCK |
| D3 | 29 | LRCK |
| D4 | 6 | I2C_SDA |
| D5 | 7 | I2C_SCL |
| D6 | 0 | DOUT |
| D7 | 1 | RE_B_IN |
| D8 | 2 | RE_A_IN |
| D9 | 4 | RE_SW |
| D10 | 3 | AUDIO_PWM |

## Binary output format

Both dump commands print an ASCII header line, then raw bytes — interleaved
little-endian **int32** I/Q pairs (24-bit samples, not scaled down), or for `adc stream ... 24` packed
little-endian signed 24-bit pairs (6 bytes a frame):

```
CAPTURE <frames> <rate>      # adc capture
STREAM  <frames> <rate>      # adc stream, rate is 48000 / decim
STREAM  <frames> <rate> 24   # adc stream ... 24
```

`adc stream` drains the ADC into a 30 KB ring buffer and writes to USB only what it has room for, so a slow
host never stalls the ADC. If the ring fills, whole frames are dropped and counted; `adc stats` shows them.
24-bit frames need 144 KB/s at 24 kHz, which leaves headroom on a Pi 3B+ (it reads ~192 KB/s at most).

## Typical session

```
init            # bring up the Si5351
probe           # 0x60 acked
clk 2 7000000   # LO for the Tayloe mixer
adc start       # SCKI on CLK0, capture running
adc read        # sanity-check levels
adc stream 10   # 10 s of I/Q to the host
adc stop
```
