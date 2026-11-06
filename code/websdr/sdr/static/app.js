"use strict";

const SPAN = 24000;                 // Hz of I/Q, centered on `center`
const BINS = 1024;
const BIN_HZ = SPAN / BINS;
const MAX_OFFSET = 11000;           // keep the station this far inside the span
const DB_PER_UNIT = 100 / 255;      // waterfall byte -> dB (assumes the engine maps 100 dB to 0..255)
const MODES = ["AM", "USB", "LSB"];
const PASSBAND = [[-4500, 4500], [300, 2700], [-2700, -300]];   // Hz around the station, per mode
const DEFAULT_OFFSET = [5000, 5000, 5000];
// volume (dB) per preset: the engine has no AGC, so band levels differ; measured for ~-20 dBFS rms audio.
const PRESETS = [
  { name: "AM 1170", center: 1165000, offset: 5000, mode: 0, volume: -33 },
  { name: "40m FT8", center: 7069000, offset: 5000, mode: 1, volume: -22 },
  { name: "40m SSB", center: 7195000, offset: 5000, mode: 2, volume: -17 },
  { name: "20m FT8", center: 14069000, offset: 5000, mode: 1, volume: -22 },
];

const $ = (id) => document.getElementById(id);
const clamp = (x, lo, hi) => Math.min(hi, Math.max(lo, x));

let state = null;                   // last {center, mode, offset, volume} from the server
let pendingStation = null;          // where the readout points while a tune is in flight
let key = null;
let ws = null;

// ---------- key / listen-only ----------

function readKey() {
  const m = location.hash.match(/key=([^&]+)/);
  key = m ? decodeURIComponent(m[1]) : null;
  $("listen-only").hidden = !!key;
  document.querySelectorAll("#modes button, #presets button, #goto input, #goto button, #volume")
    .forEach((el) => (el.disabled = !key));
  $("readout").classList.toggle("locked", !key);
}

function send(name, value) {
  sendMany({ [name]: value });
}

// Several controls in one message, so listeners never see a half-applied change.
function sendMany(values) {
  if (!key) { toast("Listen-only: add #key=… to the URL to tune"); return; }
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ set: values, key }));
}

// ---------- toast / status ----------

let toastTimer;
function toast(text) {
  const t = $("toast");
  t.textContent = text;
  t.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove("show"), 3500);
}

function setStatus(kind, text) {
  const s = $("status");
  s.dataset.state = kind;
  s.lastElementChild.textContent = text;
  const msg = $("wf-msg");
  if (kind === "engine" || kind === "down") {
    msg.hidden = false;
    msg.className = "wf-msg bad";
    msg.textContent = kind === "engine" ? "Radio engine not reachable — retrying…" : "Disconnected from server — reconnecting…";
  } else if (kind === "live" && rowsSeen) {
    msg.hidden = true;
  }
}

// ---------- WebSocket ----------

let backoff = 1000, lastFrame = 0, rowsSeen = 0;

function connect() {
  setStatus("connecting", "connecting…");
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onopen = () => { backoff = 1000; };
  ws.onmessage = (e) => {
    if (typeof e.data === "string") return onText(JSON.parse(e.data));
    lastFrame = performance.now();
    const kind = new Uint8Array(e.data, 0, 1)[0];
    if (kind === 1) onRows(new Uint8Array(e.data, 1));
    else if (kind === 2) onAudio(e.data);
  };
  ws.onclose = () => {
    setStatus("down", "disconnected");
    setTimeout(connect, backoff);
    backoff = Math.min(backoff * 2, 15000);
  };
}

function onText(msg) {
  if (msg.state) {
    applyState(msg.state);
    setStatus("live", "live");
  } else if (msg.error) {
    if (msg.error.startsWith("engine not reachable")) {
      setStatus("engine", "engine down");
      // The server only sends state on connect or after a set, so reconnect to fetch it.
      if (!state) setTimeout(() => ws && ws.close(), 3000);
    } else {
      toast(msg.error);
    }
  }
}

// No frames for a while on an open socket means the flowgraph stopped publishing.
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN && state && performance.now() - lastFrame > 4000) {
    setStatus("engine", "no engine data");
  } else if (ws && ws.readyState === WebSocket.OPEN && state && $("status").dataset.state === "engine") {
    setStatus("live", "live");
  }
}, 1000);

// ---------- state -> UI ----------

function station() { return state ? state.center + state.offset : 0; }

function applyState(s) {
  const old = state;
  state = { center: +s.center, mode: +s.mode, offset: +s.offset, volume: +s.volume };
  if (old && old.center !== state.center) {
    shiftWaterfall(state.center - old.center);
    $("retune-tag").hidden = false;
    setTimeout(() => ($("retune-tag").hidden = true), 1200);
  }
  if (pendingStation !== null && Math.abs(pendingStation - station()) < 1) pendingStation = null;
  if (!dragging) previewOffset = null;
  render();
}

function render() {
  if (!state) return;
  renderReadout(pendingStation ?? station());
  $("mode-tag").textContent = MODES[state.mode] ?? "?";
  $("center-val").textContent = (state.center / 1000).toFixed(3);
  $("offset-val").textContent = Math.round(state.offset);
  document.querySelectorAll("#modes button").forEach((b) => b.classList.toggle("on", +b.dataset.mode === state.mode));
  if (!volDragging) $("volume").value = state.volume;
  $("vol-val").textContent = `${Math.round(state.volume)} dB`;
  document.querySelectorAll("#presets button").forEach((b, i) => {
    const p = PRESETS[i];
    b.classList.toggle("on", p.center === state.center && p.offset === state.offset && p.mode === state.mode);
  });
  drawScale();
  placePassband();
}

// ---------- frequency readout ----------

// Digits for 10 MHz down to 1 Hz; each carries its tuning step.
function renderReadout(hz) {
  const r = $("readout");
  if (!r.children.length) {
    for (let p = 7; p >= 0; p--) {
      const d = document.createElement("span");
      d.className = "d";
      d.dataset.step = 10 ** p;
      r.appendChild(d);
      if (p === 6 || p === 3) {
        const s = document.createElement("span");
        s.className = "sep";
        s.textContent = ".";
        r.appendChild(s);
      }
    }
    const u = document.createElement("span");
    u.className = "unit";
    u.textContent = "MHz";
    r.appendChild(u);
  }
  const text = hz === null ? "--------" : String(Math.round(hz)).padStart(8, "0");
  let lead = true;
  r.querySelectorAll(".d").forEach((d, i) => {
    d.textContent = text[i];
    if (text[i] !== "0" || i >= 1) lead = false;   // keep the 1 MHz digit lit
    d.classList.toggle("lead", lead);
  });
}

// Out of the window: move center and park the station at the mode's default offset.
let tuneTimer;
function tuneTo(hz) {
  if (!state) return;
  hz = clamp(Math.round(hz), 100000, 30000000);
  pendingStation = hz;
  renderReadout(hz);
  clearTimeout(tuneTimer);
  const inWindow = Math.abs(hz - state.center) <= MAX_OFFSET;
  tuneTimer = setTimeout(() => {
    if (inWindow) {
      send("offset", hz - state.center);
    } else {
      const off = DEFAULT_OFFSET[state.mode] ?? 5000;
      sendMany({ center: hz - off, offset: off });
    }
    setTimeout(() => { if (pendingStation === hz) { pendingStation = null; render(); } }, 2500);
  }, inWindow ? 120 : 450);   // a center change costs ~1 s of audio, so wait for the wheel to settle
}

function stepDigit(el, dir) {
  if (!key) return toast("Listen-only: add #key=… to the URL to tune");
  const step = +el.dataset.step;
  tuneTo((pendingStation ?? station()) + dir * step);
}

$("readout").addEventListener("wheel", (e) => {
  const d = e.target.closest(".d");
  if (!d) return;
  e.preventDefault();
  stepDigit(d, e.deltaY < 0 ? 1 : -1);
}, { passive: false });

$("readout").addEventListener("click", (e) => {
  const d = e.target.closest(".d");
  if (!d) return;
  const r = d.getBoundingClientRect();
  stepDigit(d, e.clientY < r.top + r.height / 2 ? 1 : -1);
});

$("goto").addEventListener("submit", (e) => {
  e.preventDefault();
  const khz = parseFloat($("goto-khz").value.replace(",", "."));
  if (!isFinite(khz) || khz < 100 || khz > 30000) return toast("Enter a frequency between 100 and 30000 kHz");
  if (!key) return toast("Listen-only: add #key=… to the URL to tune");
  const hz = Math.round(khz * 1000), off = DEFAULT_OFFSET[state?.mode ?? 1];
  pendingStation = hz;
  renderReadout(hz);
  sendMany({ center: hz - off, offset: off });
  $("goto-khz").blur();
});

// ---------- controls ----------

document.querySelectorAll("#modes button").forEach((b) => b.addEventListener("click", () => send("mode", +b.dataset.mode)));

let volDragging = false, volTimer;
$("volume").addEventListener("input", (e) => {
  volDragging = true;
  $("vol-val").textContent = `${e.target.value} dB`;
  clearTimeout(volTimer);
  volTimer = setTimeout(() => send("volume", +e.target.value), 80);
});
$("volume").addEventListener("change", () => { volDragging = false; });

PRESETS.forEach((p) => {
  const b = document.createElement("button");
  b.textContent = p.name;
  b.addEventListener("click", () => {
    if (!key) return toast("Listen-only: add #key=… to the URL to tune");
    sendMany({ center: p.center, offset: p.offset, mode: p.mode, volume: p.volume });
  });
  $("presets").appendChild(b);
});

// ---------- waterfall ----------

const wf = $("waterfall");
const wctx = wf.getContext("2d");
const ROWS = wf.height;
const rowImg = wctx.createImageData(BINS, 1);

// Smooth colormap: deep blue -> purple -> orange -> yellow -> white.
const LUT = (() => {
  const stops = [[0, 0x02, 0x03, 0x12], [0.18, 0x0b, 0x1e, 0x6e], [0.38, 0x55, 0x1b, 0x8f], [0.55, 0xb0, 0x2a, 0x7d],
    [0.72, 0xf2, 0x6a, 0x2a], [0.88, 0xfd, 0xc8, 0x3c], [1, 0xff, 0xfb, 0xe8]];
  const lut = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i++) {
    const x = i / 255;
    let k = 0;
    while (k < stops.length - 2 && x > stops[k + 1][0]) k++;
    const [x0, ...a] = stops[k], [x1, ...b] = stops[k + 1];
    const f = (x - x0) / (x1 - x0);
    for (let c = 0; c < 3; c++) lut[i * 3 + c] = Math.round(a[c] + (b[c] - a[c]) * f);
  }
  return lut;
})();

// Auto contrast: track the noise floor and the strong-signal level of the rows.
let floor = null, peakLvl = null;

function onRows(bytes) {
  for (let o = 0; o + BINS <= bytes.length; o += BINS) drawRow(bytes.subarray(o, o + BINS));
}

function drawRow(row) {
  const sorted = Uint8Array.from(row).sort();
  const nf = sorted[BINS >> 2], pk = sorted[BINS - 4];
  floor = floor === null ? nf : floor + 0.05 * (nf - floor);
  peakLvl = peakLvl === null ? pk : peakLvl + (pk > peakLvl ? 0.2 : 0.02) * (pk - peakLvl);
  const lo = floor - 10, hi = Math.max(peakLvl + 4, lo + 45);
  const scale = 255 / (hi - lo);
  const px = rowImg.data;
  for (let k = 0; k < BINS; k++) {
    const v = clamp(Math.round((row[k] - lo) * scale), 0, 255) * 3;
    px[k * 4] = LUT[v]; px[k * 4 + 1] = LUT[v + 1]; px[k * 4 + 2] = LUT[v + 2]; px[k * 4 + 3] = 255;
  }
  wctx.drawImage(wf, 0, 0, BINS, ROWS - 1, 0, 1, BINS, ROWS - 1);   // scroll down one row
  wctx.putImageData(rowImg, 0, 0);
  updateMeter(row);
  if (!rowsSeen++) { $("wf-msg").hidden = true; }
}

// After a retune, slide the history so old signals stay at their RF.
function shiftWaterfall(dHz) {
  const dx = -dHz / BIN_HZ;
  if (Math.abs(dx) >= BINS) { wctx.fillStyle = "#020312"; wctx.fillRect(0, 0, BINS, ROWS); return; }
  wctx.drawImage(wf, dx, 0);
  wctx.fillStyle = "#020312";
  if (dx > 0) wctx.fillRect(0, 0, dx, ROWS); else wctx.fillRect(BINS + dx, 0, -dx, ROWS);
}

// ---------- S/N meter ----------

let meterPeak = 0, meterAvg = 0;

function updateMeter(row) {
  if (!state) return;
  const [a, b] = PASSBAND[state.mode] ?? PASSBAND[1];
  const off = previewOffset ?? state.offset;
  const k0 = clamp(Math.round((off + a) / BIN_HZ + BINS / 2), 0, BINS - 1);
  const k1 = clamp(Math.round((off + b) / BIN_HZ + BINS / 2), k0 + 1, BINS);
  let sum = 0;
  for (let k = k0; k < k1; k++) sum += 10 ** (row[k] * DB_PER_UNIT / 10);
  const noise = 10 ** ((floor ?? 0) * DB_PER_UNIT / 10) * (k1 - k0);
  const snr = Math.max(0, 10 * Math.log10(sum / noise));
  meterAvg += 0.35 * (snr - meterAvg);
  meterPeak = Math.max(meterAvg, meterPeak - 0.6);
  $("meter-bar").style.width = `${clamp(meterAvg / 60 * 100, 0, 100)}%`;
  $("meter-peak").style.left = `${clamp(meterPeak / 60 * 100, 0, 99.5)}%`;
  $("meter-val").textContent = `${meterAvg.toFixed(0)} dB S/N`;
}

// ---------- scale + passband ----------

const scaleCv = $("scale");

function drawScale() {
  if (!state) return;
  const dpr = window.devicePixelRatio || 1;
  const w = scaleCv.clientWidth, h = scaleCv.clientHeight;
  if (scaleCv.width !== Math.round(w * dpr)) { scaleCv.width = Math.round(w * dpr); scaleCv.height = Math.round(h * dpr); }
  const c = scaleCv.getContext("2d");
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);
  const lo = state.center - SPAN / 2;
  const xOf = (hz) => (hz - lo) / SPAN * w;
  const major = w < 500 ? 5000 : w < 900 ? 2000 : 1000;
  const minor = major / (major === 2000 ? 4 : 5);
  c.font = "11px 'Share Tech Mono', ui-monospace, monospace";
  c.textAlign = "center";
  c.textBaseline = "top";
  for (let f = Math.ceil(lo / minor) * minor; f <= lo + SPAN; f += minor) {
    const x = Math.round(xOf(f)) + 0.5, isMajor = f % major === 0;
    c.strokeStyle = isMajor ? "#8a96b4" : "#3a4560";
    c.beginPath(); c.moveTo(x, h); c.lineTo(x, h - (isMajor ? 9 : 5)); c.stroke();
    if (isMajor && x > 18 && x < w - 18) {
      c.fillStyle = "#b7c0d6";
      c.fillText((f / 1000).toFixed(f % 1000 ? 1 : 0), x, 3);
    }
  }
  // Station marker.
  const sx = xOf(state.center + (previewOffset ?? state.offset));
  c.fillStyle = "#ffb347";
  c.beginPath(); c.moveTo(sx - 5, h - 7); c.lineTo(sx + 5, h - 7); c.lineTo(sx, h); c.fill();
}

let previewOffset = null, dragging = false;

function placePassband() {
  if (!state) return;
  const off = previewOffset ?? state.offset;
  const [a, b] = PASSBAND[state.mode] ?? PASSBAND[1];
  const pct = (hz) => (hz / SPAN + 0.5) * 100;
  const pb = $("passband");
  pb.hidden = false;
  pb.style.left = `${pct(off + a)}%`;
  pb.style.width = `${(b - a) / SPAN * 100}%`;
  pb.firstElementChild.style.left = `${(-a) / (b - a) * 100}%`;
}

// ---------- click / drag to tune ----------

const wrap = $("wf-wrap");
const hzAt = (clientX) => {
  const r = wrap.getBoundingClientRect();
  return ((clientX - r.left) / r.width - 0.5) * SPAN;
};
let grab = 0, lastSent = 0;

function sendOffset(off) {
  off = clamp(Math.round(off / 10) * 10, -MAX_OFFSET, MAX_OFFSET);
  send("offset", off);
}

wrap.addEventListener("pointerdown", (e) => {
  if (!state) return;
  if (!key) return toast("Listen-only: add #key=… to the URL to tune");
  const hz = hzAt(e.clientX);
  const [a, b] = PASSBAND[state.mode];
  // Grabbing inside the passband drags it; anywhere else jumps the station to the pointer.
  grab = hz >= state.offset + a && hz <= state.offset + b ? hz - state.offset : 0;
  dragging = true;
  previewOffset = clamp(hz - grab, -MAX_OFFSET, MAX_OFFSET);
  wrap.setPointerCapture(e.pointerId);
  placePassband(); drawScale();
});

wrap.addEventListener("pointermove", (e) => {
  const hz = hzAt(e.clientX);
  if (state && e.pointerType === "mouse") {
    const cur = $("cursor"), r = wrap.getBoundingClientRect(), x = e.clientX - r.left;
    cur.hidden = false;
    cur.style.left = `${x}px`;
    cur.classList.toggle("flip", x > r.width - 110);
    cur.firstElementChild.textContent = `${((state.center + hz) / 1000).toFixed(2)} kHz`;
  }
  if (!dragging) return;
  previewOffset = clamp(hz - grab, -MAX_OFFSET, MAX_OFFSET);
  placePassband(); drawScale();
  renderReadout(state.center + previewOffset);
  if (performance.now() - lastSent > 150) { lastSent = performance.now(); sendOffset(previewOffset); }
});

const endDrag = () => {
  if (!dragging) return;
  dragging = false;
  sendOffset(previewOffset);
};
wrap.addEventListener("pointerup", endDrag);
wrap.addEventListener("pointercancel", endDrag);
wrap.addEventListener("pointerleave", () => ($("cursor").hidden = true));

window.addEventListener("resize", () => { drawScale(); });

// ---------- audio ----------

let audioCtx = null, player = null, fallbackJb = null;

async function startAudio() {
  audioCtx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" });
  if (audioCtx.audioWorklet) {
    await audioCtx.audioWorklet.addModule("audio-worklet.js");
    player = new AudioWorkletNode(audioCtx, "sdr-player", { outputChannelCount: [1] });
    player.port.onmessage = (e) => ($("buf-val").textContent = `${e.data.ms} ms buffered`);
  } else {
    // Plain-http LAN pages have no AudioWorklet; same buffer on the main thread.
    fallbackJb = new JitterBuffer(audioCtx.sampleRate);
    player = audioCtx.createScriptProcessor(2048, 0, 1);
    player.onaudioprocess = (e) => fallbackJb.fill(e.outputBuffer.getChannelData(0));
    setInterval(() => ($("buf-val").textContent = `${Math.round(fallbackJb.level / 12)} ms buffered`), 500);
  }
  player.connect(audioCtx.destination);
  await audioCtx.resume();
}

function onAudio(buf) {
  if (!audioCtx || audioCtx.state !== "running") return;
  const n = (buf.byteLength - 1) >> 1;
  const view = new DataView(buf, 1);
  const f = new Float32Array(n);
  for (let i = 0; i < n; i++) f[i] = view.getInt16(i * 2, true) / 32768;
  if (fallbackJb) fallbackJb.push(f);
  else player.port.postMessage(f, [f.buffer]);
}

$("audio-btn").addEventListener("click", async () => {
  const btn = $("audio-btn");
  try {
    if (!audioCtx) await startAudio();
    else if (audioCtx.state === "running") await audioCtx.suspend();
    else await audioCtx.resume();
  } catch (err) {
    toast(`Audio failed: ${err.message}`);
    audioCtx = null;
    return;
  }
  const on = audioCtx.state === "running";
  btn.classList.toggle("on", on);
  btn.textContent = on ? "■ Mute audio" : "▶ Start audio";
  if (!on) $("buf-val").textContent = "";
});

// ---------- go ----------

window.addEventListener("hashchange", readKey);
readKey();
renderReadout(null);
connect();
