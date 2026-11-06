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
- Shown only while the server's `allow_center_freq_changes` is true. Valid input depends on the selected SDR (the
  `sdr_id` in the server's config): `rtlsdr` 24–1766 MHz, `tayloe` 0.1–30 MHz, anything else unlimited
  (`CENTER_FREQ_LIMITS_MHZ` at the top of `center_freq.js`; add an entry when adding an SDR).
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

Superseded by our own WebSDR (below): `rp2040-rtltcp` is disabled on the Pi. Re-enable it (and stop the Docker
bridge) to use the board in OpenWebRX again.

- Source of truth: `websdr/rp2040_rtltcp_bridge.py` and `websdr/rp2040-rtltcp.service` in this folder. Uses
  `radiolib.RadioBoard` (port found by USB ID, `find_port()`).
- On the Pi: `/opt/rp2040-bridge/` holds the script, a copy of `radiolib/` and a venv (`--system-site-packages`;
  numpy/scipy/pyserial from apt, radiolib installed `--no-deps`). Service `rp2040-rtltcp`, runs as `pi` (in `dialout`),
  board on `/dev/ttyACM0`. Logs: `sudo journalctl -u rp2040-rtltcp -f`.
- Runs at `--decim 2` (24 kHz). The Pi 3B+ can't read the board at 48 kHz (see TODOs).
- rtl_tcp: sends the 12-byte `RTL0` header, then unsigned 8-bit I/Q. Handles `0x01` (frequency: retune, debounced
  0.3 s, ~1 s gap), `0x02` (sample rate: warns on mismatch), `0x03`/`0x04` (gain); ignores ppm, AGC, bias-tee. Accepts one client
  at a time. Reopens the board if it is unplugged.
- Tunes the LO exactly to the profile's `center_freq` (`tune(hz, offset=0)`), since rtl_tcp can't report an offset.
  The +3 kHz (AM) / +5 kHz (SSB) carrier offset lives in the profiles: `center_freq` 3 or 5 kHz below `start_freq`.
- A DC blocker (pole 0.999) removes the board's DC offset; `--no-dc-block` turns it off.
- Digital gain before 8-bit quantizing comes from the profile's `rf_gain` (dB), else `--gain` (default 46). Set it per
  profile: board levels differ by ~40 dB between bands. The log prints the gain, then peak and % clipped every 10 s;
  aim for 0% clipped. Clipping sounds like a mistuned station. To pick a gain, measure with `capture()` at the
  profile's center: gain ≈ 20·log10(0.7 / 99.9th-percentile |iq|).
- Accepts centers 0.1–30 MHz (`--fmin`/`--fmax`); other requests are logged and ignored.
- Profiles must say `samp_rate: 24000`. The `/settings` form rejects rtl_tcp rates under 250 kHz, so add or edit
  Tayloe profiles in `settings.json` directly (service stopped; backup at `settings.json.bak-before-tayloe`).

| profile | `center_freq` | `start_freq` | `start_mod` | `rf_gain` | board rms there |
|---|---|---|---|---|---|
| `am1170` AM 1170 | 1167000 | 1170000 | am | 8 | 0.13 of full scale |
| `40m-ft8` 40m FT8 | 7069000 | 7074000 | usb | 46 | 0.0013 |

- After switching to a Tayloe profile, waterfall and audio take ~10 s to start (connector start + first retune).
- Known issue: rare isolated sample spikes (logged peaks of 50–100× full scale, <0.1% clipped). Probably the
  zero-margin USB link at 24 kHz; see TODOs.

OpenWebRX test client on the Pi: `python3 ~/bin/owrx_ws_test.py "tayloe|am1170" 30` opens a profile over `/ws/` like
a browser and counts FFT/audio frames.

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

### Own WebSDR (`websdr/sdr/`)

Our own web SDR for the Tayloe board, replacing OpenWebRX for it. On the Pi it runs in Docker on port 8090
(`http://10.0.0.216:8090/#key=memagic`, diagnostics at `/diag.html`). `PROTOCOL.md` there is the contract between
the parts; `DOCKER.md` has the build and deploy steps.

```
board ─USB─▶ iq_bridge.py ─ZMQ :5555─▶ engine.grc ─ZMQ :5560 waterfall / :5561 audio─▶ server.py ─WS /ws─▶ page
                  ▲ :5556 tune ◀── Board Tuner     ▲ XML-RPC :8080 (set_/get_ center, offset, mode, volume)
```

- `engine.grc`: headless GNU Radio flowgraph (grc-maker skill). Board Tuner → waterfall (`logpwrfft_x`, ~12 rows/s,
  -120..-20 dB → 0–255) and two demods running side by side: AM (`am_demod_cf`) and SSB phasing (delay 127 /
  Hilbert 255). A selector picks one; audio goes out at 12 kHz int16.
- No AGC: `volume` (dB) is the only level control, and band levels differ (measured on the Pi with the antenna:
  AM 1170 wants -33 dB, 40 m FT8 -22 dB, 40 m SSB -17 dB for ~-20 dBFS audio). Each page preset carries its volume;
  audio above 0 dBFS clips. The engine starts at -22 dB.
- Every mode uses a 5 kHz offset: the page sets center = station - 5 kHz (AM 1170 → center 1165 kHz).
- **USB and LSB are both in `engine.grc`.** The phasing arms meet at an Add, which on its own gives LSB
  (`real + H(imag)` cancels the upper sideband). The Multiply Const before it is `sideband`: -1 in USB (the default,
  so the render shows -1), +1 in LSB. Verified with synthetic I/Q: 63–68 dB opposite-sideband rejection.
- **The older `gnu-radio/board/ssb_receiver.grc` and `ft8_receiver.grc` are LSB only** (Add, no sign flip). Right for
  40 m voice, wrong for FT8 (USB); see TODOs.
- `center` is the LO (middle of the waterfall; setting it retunes the board, ~1 s gap), `offset` is the station
  relative to it (instant). Station = center + offset. The Board Tuner sends `center 0` to the bridge and repeats it
  every 3 s, so a restarted bridge comes back tuned.
- `server.py`: FastAPI, never imports gnuradio. Serves `static/`, relays ZMQ to every WebSocket with a type byte
  (1 waterfall, 2 audio), turns `{"set": ...}` messages into XML-RPC calls (`CONTROLS` allowlist, `--key` /
  `$SDR_KEY` needed to tune), `GET /api/diag` from `diag.py` (CPU, memory, temperature, throttling, Wi-Fi,
  processes; 2 s samples, 30 min kept).
- `static/`: the radio page (`index.html`, `app.js`, `audio-worklet.js`, `style.css`) and `diag.html`.
- `fake_engine.py`: pure-Python stand-in for the engine, for page work without GNU Radio.

Mac (from `websdr/sdr/`, `conda activate gr`; needs fastapi uvicorn websockets pyzmq psutil):

    ./run.sh --key memagic                 # bridge + engine (built from engine.grc) + server, board plugged in
    python fake_engine.py & python server.py --key memagic     # no board, no GNU Radio
    python -m pytest tests/

Pi (Docker; image built on the Pi, code mounted from `~/websdr-src` so updates are copy + restart, see
`DOCKER.md`): `cd ~/websdr && docker compose up -d`, logs with
`docker compose logs -f bridge|engine|server`. `rp2040-rtltcp` is disabled, since only one program can open the
board. OpenWebRX keeps the RTL dongle (it was stopped during the first deploy; still enabled at boot).

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

Not done yet: Wi-Fi power-save off and hardware watchdog, public access via cloudflared, router
DHCP reservation.

## TODOs

- **FT8 in the WebSDR (the last feature before the project is retired):** decode in the WebSDR on the Pi and show
  messages on the page. `engine.grc` gets a 12 kHz audio feed taken before the volume; a separate `ft8_service.py`
  container decodes at each UTC slot, only in USB on a known FT8 frequency; `server.py` relays decodes and keeps recent
  ones; the page gets a table. radiolib needs `unpack77` (payload to text) and the image needs `ldpc`. Measure decode
  time on the Pi first. The board heard almost nothing on 40 m when last checked, so live decodes depend on that too.
- **LSB-only board flowgraphs:** `gnu-radio/board/ssb_receiver.grc` and `ft8_receiver.grc` add the phasing arms, which
  gives LSB, so `ft8_receiver` hears FT8 (USB) mirrored. Fix with a -1 Multiply Const on the Hilbert arm (as in
  `websdr/sdr/engine.grc`) or a Subtract. Their pasted Board Tuner is also an old copy of `gr_tuner_block.py`.
- **WebSDR audio batching:** the engine publishes ~190 small audio messages/s and the server forwards each one to every
  listener; batch to ~50 ms in `server.py` before relying on the Cloudflare link.
- **RTL-SDR in our WebSDR:** a second engine (`engine_rtl.grc`, gr-osmosdr at ~1.024 MS/s, WFM/NBFM), per-device
  relays in the server, a device switch in the page. Measure CPU on the Pi first. Lets OpenWebRX go.

- **Firmware: half-band decimator** (`radio_cli/audio_adc.cpp`). Replace the 2-sample boxcar (`ADC_DECIM`) with a
  half-band FIR decimate-by-2, so the 24 kHz stream is clean to about ±10 kHz instead of aliasing the outer half. Then
  check `adc stats` for overruns and whether the rare sample spikes go away. (Packed 24-bit frames and the ring buffer
  are done: 144 KB/s at 24 kHz, against the ~192 KB/s the Pi 3B+ can read from the board.)
