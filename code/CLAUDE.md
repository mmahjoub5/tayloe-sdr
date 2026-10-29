# CLAUDE.md

## WebSDR Raspberry Pi

Raspberry Pi 3B+ running OpenWebRX+ (Raspberry Pi OS Lite 64-bit, Debian trixie), serving a web SDR on the LAN.

### System architecture

```
                         Raspberry Pi 3B+  (hostname websdr, 10.0.0.216, Wi-Fi)
antenna ── RTL-SDR ─USB─▶ ┌───────────────────────────────────────────────────────────┐
           (R820T)        │ rtl_connector  (started by OpenWebRX; tunes the dongle)   │
                          │      │ I/Q                                                │
                          │      ▼                                                    │
                          │ OpenWebRX+ (systemd: openwebrx, :8073)                    │
                          │   owrx/ (Python): SDR sources, profiles, DSP, decoders    │
                          │   htdocs/ (JS):   receiver page, waterfall, audio         │
                          │     └ plugins/receiver/init.js → center_freq plugin       │
                          └───────────────┬───────────────────────────────────────────┘
                                          │ HTTP + WebSocket /ws/ (config, FFT, audio)
                                          ▼
                          browsers on the LAN: http://10.0.0.216:8073/#key=<magic key>

antenna ── Tayloe board ─USB serial─▶ rp2040_rtltcp_bridge.py ─rtl_tcp 127.0.0.1:1234─▶ rtl_tcp_connector ─▶ OpenWebRX
           (RP2040 + PCM1808)        (systemd: rp2040-rtltcp)                              (device "tayloe")
```

- The SDR is one shared tuner. Every listener sees the same center frequency; a profile switch or center retune by
  one user moves everyone.
- Each profile is a fixed window: center frequency ± sample rate / 2 (2.4 MHz wide at 2.4 MS/s). Tuning outside
  the window needs a profile switch or a center retune (the Center MHz box below).
- Server → browser messages are JSON `config` updates (full on connect, then only changed keys) plus binary frames:
  type 1 = FFT, 2 = audio, 4 = HD audio (WFM).

### SSH

```bash
ssh pi@10.0.0.216
```

- Hostname `websdr` (`ssh pi@websdr.local` also works when mDNS resolves; the IP is more reliable).
- User `pi`, key auth with `~/.ssh/id_ed25519`, passwordless sudo. The `pi` console password is not stored here.
- IP comes from DHCP; reserve `10.0.0.216` for MAC `b8:27:eb:7e:bd:15` in the router so it doesn't change.

### OpenWebRX+

- Web UI: http://10.0.0.216:8073 (settings: `/settings`, admin user `amin`)
- Service: `sudo systemctl {start|stop|restart|status} openwebrx`
- Logs: `sudo journalctl -u openwebrx -f`
- Config: `/var/lib/openwebrx/settings.json` (edit through `/settings`; edit the file only with the service stopped)
- Package repo: `https://luarvique.github.io/ppa/trixie`
- Settings → General: "Allow users to change center frequency" is on, magic key `memagic`. Retunes are only accepted
  from pages opened with `#key=memagic`; the server silently ignores the rest.
- Profiles (RTL-SDR): 70cm Repeaters, 2m, 10m + CB, 40m, 80m, 160m, AM Broadcast, 1090MHz ADSB, FM Broadcast 98.5.
  The HF ones (40m and below, AM Broadcast) only show noise on this dongle.
- Profiles (Tayloe board, device id `tayloe`): AM 1170, 40m FT8. See the bridge section below.
- The default Airspy/SDRplay device entries log "source type not available" at startup; harmless, no hardware.

### Receiver plugin: Center MHz box

Adds a "Center MHz" input + Go button under the profile dropdown. It sends the same message as the core
`jumpBySteps()`: `{type: "setfrequency", params: {frequency: <Hz int>, key: <magic key from #key=>}}`.

- Source of truth: `websdr/plugins/receiver/` in this folder (`init.js`, `center_freq/center_freq.{js,css}`).
- Installed on the Pi under `/usr/lib/python3/dist-packages/htdocs/plugins/receiver/`. These files are not owned by
  the `openwebrx` package, so `apt upgrade` leaves them alone. Static files: no restart needed after copying.
- Shown only while the server's `allow_center_freq_changes` is true. Valid input 24–1766 MHz
  (`CENTER_FREQ_MIN_MHZ` / `CENTER_FREQ_MAX_MHZ` at the top of `center_freq.js`).
- Tracks the shared center (profile switches, other users' retunes). Shows "Not retuned: the server refused it" if no
  matching `center_freq` update arrives within 3 s (usually a missing or wrong `#key`).
- Hooks the global `on_ws_recv` (observe only). It must load before the page opens its WebSocket to see the allow
  flag; with the current loader it does. If upstream renames `on_ws_recv`, `getMagicKey` or
  `#openwebrx-sdr-profiles-listbox`, the box quietly doesn't appear and the rest of the page keeps working.
- If an `openwebrx` upgrade ever ships its own `plugins/receiver/init.js`, re-add `Plugins.load('center_freq');`.

Install / reinstall:

```bash
cd websdr/plugins/receiver
scp -r init.js center_freq pi@10.0.0.216:/tmp/
ssh pi@10.0.0.216 'P=/usr/lib/python3/dist-packages/htdocs/plugins/receiver; sudo install -d $P/center_freq && sudo install -m644 /tmp/init.js $P/ && sudo install -m644 /tmp/center_freq/* $P/center_freq/ && rm -rf /tmp/init.js /tmp/center_freq'
```

Remove (then reload the page):

```bash
ssh pi@10.0.0.216 'sudo rm -rf /usr/lib/python3/dist-packages/htdocs/plugins/receiver/center_freq /usr/lib/python3/dist-packages/htdocs/plugins/receiver/init.js'
```

### Tayloe board bridge (rtl_tcp)

The RP2040 Tayloe board shows up in OpenWebRX as device "Tayloe board (RP2040)", type "RTL-SDR device (via rtl_tcp)",
`remote: 127.0.0.1:1234`. A bridge pretends to be an rtl_tcp server, so OpenWebRX needs no changes.

- Source of truth: `websdr/rp2040_rtltcp_bridge.py` and `websdr/rp2040-rtltcp.service` in this folder. Uses
  `radiolib.RadioBoard` (port found by USB ID, `find_port()`).
- On the Pi: `/opt/rp2040-bridge/` holds the script, a copy of `radiolib/` and a venv (`--system-site-packages`;
  numpy/scipy/pyserial from apt, radiolib installed `--no-deps`). Service `rp2040-rtltcp`, runs as `pi` (in `dialout`),
  board on `/dev/ttyACM0`. Logs: `sudo journalctl -u rp2040-rtltcp -f`.
- Runs at `--decim 2` (24 kHz). The Pi 3B+ can't read the board at 48 kHz (see TODOs).
- rtl_tcp: sends the 12-byte `RTL0` header, then unsigned 8-bit I/Q. Handles `0x01` (frequency: retune, debounced
  0.3 s, ~1 s gap) and `0x02` (sample rate: warns on mismatch); ignores gain, ppm, AGC, bias-tee. Accepts one client
  at a time. Reopens the board if it is unplugged.
- Tunes the LO exactly to the profile's `center_freq` (`tune(hz, offset=0)`), since rtl_tcp can't report an offset.
  The +3 kHz (AM) / +5 kHz (SSB) carrier offset lives in the profiles: `center_freq` 3 or 5 kHz below `start_freq`.
- A DC blocker (pole 0.999) removes the board's DC offset; `--no-dc-block` turns it off.
- Digital gain `--gain` (dB, default 46) before 8-bit quantizing. The log prints the peak and % clipped every 10 s.
- Accepts centers 0.1–30 MHz (`--fmin`/`--fmax`); other requests are logged and ignored.
- Profiles must say `samp_rate: 24000`. The `/settings` form rejects rtl_tcp rates under 250 kHz, so add or edit
  Tayloe profiles in `settings.json` directly (service stopped; backup at `settings.json.bak-before-tayloe`).

| profile | `center_freq` | `start_freq` | `start_mod` |
|---|---|---|---|
| `am1170` AM 1170 | 1167000 | 1170000 | am |
| `40m-ft8` 40m FT8 | 7069000 | 7074000 | usb |

- After switching to a Tayloe profile, waterfall and audio take ~10 s to start (connector start + first retune).
- Known issue: rare isolated sample spikes (logged peaks of 50–100× full scale, <0.1% clipped). Probably the
  zero-margin USB link at 24 kHz; see TODOs.
- The Center MHz box rejects HF (`CENTER_FREQ_MIN_MHZ` is 24), so it can't retune this device yet.

Test on the Mac against the board (no OpenWebRX needed): `python websdr/rp2040_rtltcp_bridge.py`, then point any
rtl_tcp client (SDR++, GQRX) at `127.0.0.1:1234` with the sample rate set to the stream rate.

Install / update on the Pi:

```bash
ssh pi@10.0.0.216 'mkdir -p /tmp/rb'
rsync -a --exclude __pycache__ --exclude '*.egg-info' --exclude tests radiolib websdr/rp2040_rtltcp_bridge.py websdr/rp2040-rtltcp.service pi@10.0.0.216:/tmp/rb/
ssh pi@10.0.0.216 'cd /opt/rp2040-bridge && rm -rf radiolib && cp -r /tmp/rb/radiolib /tmp/rb/rp2040_rtltcp_bridge.py . && venv/bin/pip install -q --no-deps ./radiolib && sudo install -m644 /tmp/rb/rp2040-rtltcp.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart rp2040-rtltcp && rm -rf /tmp/rb'
```

First install also needs `sudo apt install python3-numpy python3-scipy`, `sudo install -d -o pi -g pi
/opt/rp2040-bridge`, `python3 -m venv --system-site-packages /opt/rp2040-bridge/venv` and
`sudo systemctl enable rp2040-rtltcp`.

### SDR hardware

- RTL-SDR dongle: generic RTL2832U + R820T tuner (~24 MHz–1.7 GHz, no HF without an upconverter or a V3/V4 dongle).
- Tayloe board: Seeed XIAO RP2040 (USB `2e8a:000a`, full speed, `cdc_acm`), HF. Firmware in `radio_cli/`.
- DVB-T kernel driver is blacklisted in `/etc/modprobe.d/blacklist-rtlsdr.conf` so OpenWebRX can claim the dongle.
- Usable sample rate: 2.4 MHz max. 3.2 MHz drops samples and loads the Pi 3B+.
- Strong FM broadcast stations can overload the R820T at the default 29 dB gain and show up on 2m/70cm. Fix with lower
  RF gain or an FM band-stop filter.
- `[R82XX] PLL not locked!` in the logs at startup is normal for this tuner.
- Health check: `vcgencmd measure_temp; vcgencmd get_throttled` (throttling starts at 80 °C; idle is ~45–50 °C).

### Setup recap (2026-10-28)

1. The SD card had a 2020 Raspberry Pi OS (buster) image. The OpenWebRX+ repo has no buster packages, so the card was
   reflashed with Raspberry Pi OS Lite 64-bit 2026-10-06 (trixie). First boot was configured with cloud-init files on
   the boot partition (`user-data`: hostname, `pi` user, SSH key, timezone; `network-config`: Wi-Fi, country US).
2. `apt full-upgrade`, then OpenWebRX+ 1.2.128 from the luarvique trixie repo. Admin user `amin` created.
3. RTL-SDR plugged in; DVB-T driver blacklisted; `rtl-sdr` tools installed (`rtl_test -t` finds the R820T).
4. FM Broadcast 98.5 profile added (WFM, 2.4 MS/s); center frequency changes enabled with magic key.
5. Center MHz plugin written and installed. Acceptance-tested in Chrome against the live receiver: right message,
   real retune, shared-tuner updates, profile tracking, input validation, magic-key refusal, no console errors,
   survives restart, fits the 259 px receiver panel.
6. Tayloe board added through the rtl_tcp bridge (24 kHz). Tested on the Mac (AM 1170 carrier at +2999 Hz, 58 dB
   over the floor) and through OpenWebRX on the Pi (profile loads, FFT and audio frames flow).

Not done yet: Center MHz box for HF, Wi-Fi power-save off and hardware watchdog, public access via cloudflared, router
DHCP reservation.

## TODOs

- **Center MHz box for HF**: lower `CENTER_FREQ_MIN_MHZ` (24) in `websdr/plugins/receiver/center_freq/center_freq.js`,
  or make the limits per device, so the Tayloe board can be retuned from it.

- **Firmware: packed 24-bit stream + half-band decimator** (`radio_cli/audio_adc.cpp`, `radiolib/radiolib/board.py`).
  On the Pi 3B+ the board (USB full speed, behind the built-in hub on `dwc_otg`) reads at most ~192 KB/s, measured with
  raw `os.read` (1500 reads/s × 128 B). `adc stream` at 48 kHz needs 384 KB/s and at 24 kHz exactly 192 KB/s, so
  48 kHz stalls the firmware (half the frames, corrupt data) and 24 kHz has no margin. The Mac reads 48 kHz fine.
  - Send each sample as 3 bytes instead of an int32 (6 B/frame): 24 kHz becomes 144 KB/s, ~25% headroom, lossless.
    Needs a new header or flag so `to_complex` knows the format.
  - Replace the 2-sample boxcar (`ADC_DECIM`) with a half-band FIR decimate-by-2, so the 24 kHz stream is clean to
    about ±10 kHz instead of aliasing the outer half.
  - Then check whether the bridge's rare sample spikes go away.
