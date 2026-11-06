#pragma once

#include <Arduino.h>
#include <hardware/pio.h>

#include "si5351_board.h"

// PCM1808 -> RP2040. The codec is strapped MD1=MD0=1: master mode at 256fs.
// It generates BCK and LRCK itself from SCKI, so the RP2040 only ever receives.
// SCKI is not driven by the RP2040 at all -- it comes from the Si5351, so
// starting the ADC means starting that clock first. Nothing downstream runs
// without it.
//
// It is CLK0, established by measurement: at 12.288 MHz, CLK0 produces activity
// on DOUT and CLK1 produces none. Both the schematic's audio sheet (which
// labels it CLK_1) and radio-project.net (which routes Y1.9 to U7.6) say
// otherwise, and both are wrong -- the netlist is two weeks older than the
// schematics, and the schematics disagree with the board.
//
// The pins are not adjacent, so neither the core's I2S library nor the usual
// PIO I2S implementations can be used: they read DIN, DIN+1, DIN+2 as one IN
// group. i2s_slave_in.pio addresses the clocks by absolute GPIO instead.
#define ADC_I2S_DIN        0      // D6, the PCM1808's DOUT
#define ADC_I2S_BCLK      28      // D2   (hardcoded in i2s_slave_in.pio)
#define ADC_I2S_LRCK      29      // D3   (hardcoded in i2s_slave_in.pio)
#define ADC_SCKI_CLK       0      // Si5351 CLK0 feeds SCKI; see above
#define ADC_SCKI_MULT    256      // master mode 256fs: SCKI = 256 * fs
#define ADC_DEFAULT_RATE 48000

// The PCM1808 holds itself in reset whenever SCKI is absent, so starting the
// clock starts a settling sequence: t(RST) = 1024 SCKI periods to release
// reset, then t(REL) = 8960/fs before DOUT is valid. At 48 kHz that is ~187 ms,
// which a 250 ms read would otherwise be racing.
#define ADC_SETTLE_FRAMES 8960

// Streaming decimates by this much before sending, unless `adc stream` asks
// for another factor. 48 kHz / 2 = 24 kHz keeps +/-12 kHz of baseband at about
// 192 KB/s; a factor of 1 sends the full 48 kHz (384 KB/s), which a waterfall
// wants because the boxcar below lets the outer half fold back in.
//
// The decimator is a plain sum of ADC_DECIM samples. A boxcar of length N
// decimated by N nulls the frequencies that fold to DC, but its stopband is
// poor everywhere else -- at /4 it attenuated an adjacent AM channel (10 kHz
// away, so 7 kHz out with a 3 kHz tuning offset) by only 5 dB before folding
// it to -5 kHz, right on top of the wanted station.
//
// Decimating by 2 instead keeps that neighbour inside the passband where a
// sharp filter on the host can actually remove it. Aliasing is irreversible;
// bandwidth is only bandwidth.
#define ADC_DECIM 2
#define ADC_DECIM_MAX 2

enum class AdcStart {
  Ok,
  ClockNotReady,      // the Si5351 never initialized
  ClockFailed,        // CLK1 would not take that frequency
  PioFailed,          // no free state machine or no room for the program
};

// Largest burst `captureRaw` will take, in stereo frames. Samples are kept at
// full 24-bit width in int32: this board's signal occupies only about 14 of
// those bits, so scaling down to int16 to save payload would throw away most
// of the signal rather than spare precision. 8192 frames of interleaved int32
// is 64 KB, about 0.17 s at 48 kHz.
#define ADC_MAX_CAPTURE 8192

// streamRaw's buffer between the ADC and USB: about 0.2 s at 24 kHz packed. A USB stall shorter than this
// costs no samples. A multiple of both frame sizes (6 and 8 bytes), so a frame never wraps.
#define ADC_STREAM_RING 30720

struct AdcCapture {
  uint16_t frames;        // frames actually read
  bool     timedOut;      // gave up waiting for clocks
  int32_t  lMin, lMax;
  int32_t  rMin, rMax;
};

class AudioAdc {
public:
  // Sets and enables SCKI on CLK1 at sampleRate * ADC_SCKI_MULT, then starts
  // the receiver.
  AdcStart begin(Si5351Board &clk, uint32_t sampleRate = ADC_DEFAULT_RATE);

  // Stops capture and the SCKI clock with it.
  void end();

  bool     running() const { return started; }
  uint32_t rate() const { return sampleRate; }
  uint64_t sckiHz() const { return (uint64_t)sampleRate * ADC_SCKI_MULT; }

  // Reads up to `frames` stereo frames. Every FIFO read is gated on the FIFO
  // being non-empty and the whole capture is bounded by timeoutMs, so with no
  // BCK/LRCK arriving this returns empty instead of hanging.
  AdcCapture capture(uint16_t frames, uint32_t timeoutMs = 250);

  // Same read path, but stores samples interleaved L,R at full 24-bit width
  // instead of only tracking min/max. Returns the frames actually stored.
  uint16_t captureRaw(int32_t *dst, uint16_t frames, uint32_t timeoutMs = 500);

  // Decimate by `decim` and send `frames` output frames to Serial, as int32 pairs (bits 32, 8 B/frame) or
  // packed little-endian 24-bit pairs (bits 24, 6 B/frame). The ADC is always drained into a ring buffer and
  // USB only gets what it has room for, so a slow host costs overruns (counted, see streamOverruns) rather
  // than silently dropped ADC samples. Returns frames actually produced.
  uint32_t streamRaw(uint32_t frames, uint8_t decim = ADC_DECIM, uint8_t bits = 32,
                     uint32_t timeoutMs = 2000);

  // Frames the last stream dropped because the ring was full, and frames it produced.
  uint32_t streamOverruns() const { return lastOverruns; }
  uint32_t streamProduced() const { return lastProduced; }

  uint32_t streamRate(uint8_t decim = ADC_DECIM) const { return sampleRate / decim; }

private:
  Si5351Board *clkSrc = nullptr;
  PIO          pio = nullptr;
  int          sm = -1;
  uint         offset = 0;
  bool         started = false;
  uint32_t     sampleRate = ADC_DEFAULT_RATE;
  uint32_t     lastOverruns = 0;
  uint32_t     lastProduced = 0;
};
