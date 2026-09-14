#include "audio_adc.h"

#include "i2s_slave_in.pio.h"

AdcStart AudioAdc::begin(Si5351Board &clk, uint32_t rate)
{
  if (started) {
    end();
  }

  if (!clk.ready()) {
    return AdcStart::ClockNotReady;
  }

  sampleRate = rate;
  clkSrc     = &clk;

  // SCKI first. The PCM1808 derives BCK and LRCK from it, so without this the
  // receiver would come up and wait forever for clocks that never arrive.
  if (!clk.setClk(ADC_SCKI_CLK, sckiHz())) {
    return AdcStart::ClockFailed;
  }

  // Wait out the codec's reset release and DOUT valid delay before anything
  // tries to read; see ADC_SETTLE_FRAMES.
  delay((ADC_SETTLE_FRAMES * 1000UL) / sampleRate + 5);

  // All three pins are inputs; nothing here ever drives the bus.
  pinMode(ADC_I2S_DIN, INPUT);
  pinMode(ADC_I2S_BCLK, INPUT);
  pinMode(ADC_I2S_LRCK, INPUT);

  // pio0 is where the core puts its own peripherals, so start on pio1.
  PIO candidates[] = { pio1, pio0 };
  for (PIO p : candidates) {
    if (!pio_can_add_program(p, &i2s_slave_in_program)) {
      continue;
    }
    int freeSm = pio_claim_unused_sm(p, false);
    if (freeSm < 0) {
      continue;
    }
    pio   = p;
    sm    = freeSm;
    offset = pio_add_program(p, &i2s_slave_in_program);
    break;
  }

  if (pio == nullptr) {
    return AdcStart::PioFailed;
  }

  pio_gpio_init(pio, ADC_I2S_DIN);

  pio_sm_config c = i2s_slave_in_program_get_default_config(offset);
  sm_config_set_in_pins(&c, ADC_I2S_DIN);
  // Shift left (I2S is MSB first) and autopush a word per 24-bit sample.
  sm_config_set_in_shift(&c, false, true, 24);
  sm_config_set_fifo_join(&c, PIO_FIFO_JOIN_RX);

  pio_sm_init(pio, sm, offset, &c);
  pio_sm_set_consecutive_pindirs(pio, sm, ADC_I2S_DIN, 1, false);
  pio_sm_set_enabled(pio, sm, true);

  started = true;
  return AdcStart::Ok;
}

void AudioAdc::end()
{
  if (started) {
    pio_sm_set_enabled(pio, sm, false);
    pio_sm_unclaim(pio, sm);
    pio_remove_program(pio, &i2s_slave_in_program, offset);
    pio     = nullptr;
    sm      = -1;
    started = false;
  }

  // CLK1 feeds nothing but SCKI on this board, so it stops with the ADC.
  if (clkSrc != nullptr) {
    clkSrc->enableClk(ADC_SCKI_CLK, false);
  }
}

AdcCapture AudioAdc::capture(uint16_t frames, uint32_t timeoutMs)
{
  AdcCapture c = {};
  c.lMin = c.rMin = INT32_MAX;
  c.lMax = c.rMax = INT32_MIN;

  if (!started) {
    c.timedOut = true;
    return c;
  }

  // Restart the state machine so the capture begins on a left channel. The
  // program re-syncs from the LRCK falling edge, so the first word pushed is
  // always left; without this a stale or partly drained FIFO could hand back
  // left and right swapped for the whole capture.
  pio_sm_set_enabled(pio, sm, false);
  pio_sm_clear_fifos(pio, sm);
  pio_sm_restart(pio, sm);
  pio_sm_exec(pio, sm, pio_encode_jmp(offset));
  pio_sm_set_enabled(pio, sm, true);

  uint32_t deadline = millis() + timeoutMs;

  while (c.frames < frames) {
    // The program pushes left then right, so a frame is two words.
    if (pio_sm_get_rx_fifo_level(pio, sm) >= 2) {
      // Samples arrive right-aligned in bits 23:0; move the sign bit up to
      // bit 31 and back down so it extends across the top byte.
      int32_t l = (int32_t)(pio_sm_get(pio, sm) << 8) >> 8;
      int32_t r = (int32_t)(pio_sm_get(pio, sm) << 8) >> 8;

      if (l < c.lMin) c.lMin = l;
      if (l > c.lMax) c.lMax = l;
      if (r < c.rMin) c.rMin = r;
      if (r > c.rMax) c.rMax = r;
      c.frames++;
      continue;
    }

    if ((int32_t)(millis() - deadline) >= 0) {
      c.timedOut = true;
      break;
    }
  }

  if (c.frames == 0) {
    c.lMin = c.lMax = c.rMin = c.rMax = 0;
  }

  return c;
}

uint16_t AudioAdc::captureRaw(int32_t *dst, uint16_t frames, uint32_t timeoutMs)
{
  if (!started || dst == nullptr) {
    return 0;
  }

  // Same resync as capture(): guarantees the first word is a left sample.
  pio_sm_set_enabled(pio, sm, false);
  pio_sm_clear_fifos(pio, sm);
  pio_sm_restart(pio, sm);
  pio_sm_exec(pio, sm, pio_encode_jmp(offset));
  pio_sm_set_enabled(pio, sm, true);

  uint32_t deadline = millis() + timeoutMs;
  uint16_t got = 0;

  while (got < frames) {
    if (pio_sm_get_rx_fifo_level(pio, sm) >= 2) {
      int32_t l = (int32_t)(pio_sm_get(pio, sm) << 8) >> 8;
      int32_t r = (int32_t)(pio_sm_get(pio, sm) << 8) >> 8;

      dst[2 * got]     = l;
      dst[2 * got + 1] = r;
      got++;
      continue;
    }

    if ((int32_t)(millis() - deadline) >= 0) {
      break;
    }
  }

  return got;
}

uint32_t AudioAdc::streamRaw(uint32_t frames, uint32_t timeoutMs)
{
  if (!started) {
    return 0;
  }

  pio_sm_set_enabled(pio, sm, false);
  pio_sm_clear_fifos(pio, sm);
  pio_sm_restart(pio, sm);
  pio_sm_exec(pio, sm, pio_encode_jmp(offset));
  pio_sm_set_enabled(pio, sm, true);

  int32_t  accI = 0, accQ = 0;
  uint8_t  n = 0;
  uint32_t sent = 0;
  uint32_t deadline = millis() + timeoutMs;

  while (sent < frames) {
    if (pio_sm_get_rx_fifo_level(pio, sm) >= 2) {
      accI += (int32_t)(pio_sm_get(pio, sm) << 8) >> 8;
      accQ += (int32_t)(pio_sm_get(pio, sm) << 8) >> 8;

      if (++n == ADC_DECIM) {
        int32_t out[2] = { accI / ADC_DECIM, accQ / ADC_DECIM };
        Serial.write((const uint8_t *)out, sizeof(out));
        accI = accQ = 0;
        n = 0;
        sent++;
      }

      // Only the absence of samples is a timeout; a long stream is not.
      deadline = millis() + timeoutMs;

      // Any byte from the host aborts, so the CLI can be reached again without
      // waiting out the whole stream -- that is what makes retuning possible
      // mid-listen. Checked per frame rather than per sample to keep the inner
      // path short.
      if ((sent & 0xFF) == 0 && Serial.available()) {
        break;
      }
      continue;
    }

    if ((int32_t)(millis() - deadline) >= 0) {
      break;
    }
  }

  return sent;
}
