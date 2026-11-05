// 12 kHz audio jitter buffer + linear-interpolation resampler to the output rate.
// Loaded twice: as an AudioWorklet module, and as a plain <script> so app.js can fall back to a
// ScriptProcessorNode where AudioWorklet is missing (it needs https or localhost).

const IN_RATE = 12000;

class JitterBuffer {
  constructor(outRate, targetMs = 250, maxMs = 600) {
    this.step = IN_RATE / outRate;          // input samples per output sample
    this.target = IN_RATE * targetMs / 1000;
    this.max = IN_RATE * maxMs / 1000;
    this.buf = new Float32Array(IN_RATE * 4);
    this.w = 0;                               // write index (total samples written)
    this.r = 0;                               // fractional read position (total)
    this.playing = false;
    this.underruns = 0;
  }

  get level() { return this.w - this.r; }

  push(samples) {
    const n = this.buf.length;
    for (let i = 0; i < samples.length; i++) this.buf[(this.w + i) % n] = samples[i];
    this.w += samples.length;
    if (this.level > n - 1) this.r = this.w - this.target;   // overflowed the ring: resync
  }

  fill(out) {
    if (!this.playing) {
      if (this.level >= this.target) this.playing = true;
      else { out.fill(0); return; }
    }
    // Grown too large (network burst, tab was throttled): drop back to the target delay.
    if (this.level > this.max) this.r = this.w - this.target;
    const n = this.buf.length;
    for (let i = 0; i < out.length; i++) {
      if (this.w - this.r < 2) {              // ran dry: silence and prebuffer again
        out.fill(0, i);
        this.playing = false;
        this.underruns++;
        return;
      }
      const i0 = Math.floor(this.r), f = this.r - i0;
      const a = this.buf[i0 % n], b = this.buf[(i0 + 1) % n];
      out[i] = a + (b - a) * f;
      this.r += this.step;
    }
  }
}

if (typeof AudioWorkletProcessor !== "undefined") {
  class SdrPlayer extends AudioWorkletProcessor {
    constructor() {
      super();
      this.jb = new JitterBuffer(sampleRate);
      this.ticks = 0;
      this.port.onmessage = (e) => this.jb.push(e.data);
    }

    process(inputs, outputs) {
      const out = outputs[0];
      this.jb.fill(out[0]);
      for (let c = 1; c < out.length; c++) out[c].set(out[0]);
      if (++this.ticks % 40 === 0) {
        this.port.postMessage({ ms: Math.round(this.jb.level / IN_RATE * 1000), underruns: this.jb.underruns });
      }
      return true;
    }
  }
  registerProcessor("sdr-player", SdrPlayer);
}
