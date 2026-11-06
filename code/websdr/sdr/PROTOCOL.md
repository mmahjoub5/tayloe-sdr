# WebSDR protocol

```
iq_bridge.py ─ZMQ :5555─▶ engine (GRC flowgraph) ─ZMQ PUB :5560/:5561─▶ server.py ─WS /ws─▶ browsers
                  ▲           ▲ XML-RPC :8080 (set_/get_)  │                 │  ▲
                  └─ :5556 ◀──┘ Board Tuner                │                 │  └─ ZMQ :5563 ◀─ ft8_service.py
                                                           └ ZMQ :5562 ──────┼──────────────────────▲
                                                                             └── commands ◀── browsers
```

Everything listens on 127.0.0.1 except `server.py`'s web port (8090), which cloudflared fronts.

## Engine (the flowgraph)

- `xmlrpc_server` block, `127.0.0.1:8080`.
- Variables the server may set (`CONTROLS` in `server.py`):

| variable | unit | meaning |
|---|---|---|
| `center` | Hz | the LO, middle of the waterfall; the Board Tuner sends it to the bridge (~1 s retune) |
| `mode` | 0/1/2 | AM / USB / LSB (`blocks_selector` input index) |
| `offset` | Hz | station relative to `center`, about ±11 kHz; the Frequency Xlating filter's `center_freq` (instant) |
| `volume` | dB | audio gain, applied as `10**(volume/20)` |

- The station (dial) frequency is `center + offset`. Waterfall bin k is RF `center + (k - 512) * 24000/1024`.
- `zeromq_pub_sink` outputs, `bind: True`:

| port | type | content |
|---|---|---|
| 5560 | byte, vlen 1024 | waterfall rows, ~10/s, averaged; -120..-20 dBFS mapped to 0–255 (the page's S-meter assumes 100 dB span), FFT-shifted with bin 512 at `center` |
| 5561 | short | audio, 12 kHz mono, in chunks of ≤ ~50 ms (bigger bursts overflow the page's jitter buffer) |
| 5562 | float | the same audio before the volume, for `ft8_service.py`; it isn't limited to ±1 |

A ZMQ message holds whatever one `work()` call produced: one or more 1024-byte rows, or any number of samples.

## FT8 (`ft8_service.py`)

A separate process, so a slow decode can't touch the radio. It keeps the last 15 s from :5562. Just after each UTC
slot (:00, :15, :30, :45) it runs ft8_lib's `decode_ft8` on that audio at low priority, if the radio was in USB on an
FT8 frequency (`FT8_DIALS`) at both the start and the end of the slot. It publishes each decoded slot as JSON on :5563:

    {"slot": <unix start>, "dial": <Hz>, "seconds": <decode time>,
     "decodes": [{"hz": <audio Hz>, "dt": <s>, "score": <sync score>, "text": "CQ K1ABC FN42"}]}

An empty `decodes` means it ran and found nothing; no message means it didn't run. RF frequency is `dial + hz`.
`score` is the decoder's sync score; ft8_lib doesn't compute an SNR.

## Browser ↔ server (`/ws`)

Server → browser:
- binary: first byte is the stream (`1` waterfall, `2` audio), the rest is the ZMQ message unchanged.
- text: `{"state": {"center": …, "mode": …, "offset": …, "volume": …}}` on connect and after every
  set (to everyone) and when the engine comes back after being down, or `{"error": "…"}` (to the sender only, or on connect if the engine is down).
- text: `{"ft8": <slot as above>}`, to everyone as each slot is decoded, and the last 40 slots on connect. The message
  text comes off the air, so the page must never treat it as HTML.

Browser → server:
- text: `{"set": "<variable>", "value": <number>, "key": "<key>"}`, or several at once with
  `{"set": {"center": …, "offset": …}, "key": "<key>"}` (applied in order, then one state broadcast).
  Without the right key the server answers with an error, so a listener without it is listen-only.

`GET /` serves `static/` (the radio at `/`, diagnostics at `/diag.html`).

## Diagnostics (`GET /api/diag?since=<unix time>`)

`{"interval_s": 2, "samples": [...]}`: samples newer than `since` (0 for all), one every 2 s, last 30 min
(`diag.py`). Each has host figures (`cpu`, `load1`, `mem_pct`, `disk_pct`, `temp_c`, `throttled`,
`wifi_dbm`, `uptime_s`), `procs` (bridge, engine, server: pid, cpu, rss_mb, or null when not running) and the
server's own (`listeners`, `engine_ok`, `waterfall_rows_s`, `audio_sps`, `dropped`). `temp_c`, `throttled`
and `wifi_dbm` are null where the OS doesn't report them (macOS).

## Run (Mac)

    conda activate gr                        # needs fastapi uvicorn websockets pyzmq psutil
    python server.py --key memagic           # http://127.0.0.1:8090
    python -m pytest tests/                  # fake engine and fake ZMQ publishers
