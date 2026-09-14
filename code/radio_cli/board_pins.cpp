#include "board_pins.h"

#include <string.h>

#include <hardware/pwm.h>
#include <hardware/gpio.h>

const PinInfo kPins[] = {
  { 26, "D0",  "SET_FF_N"  },
  { 27, "D1",  "RST_FF_N"  },
  { 28, "D2",  "BCK"       },
  { 29, "D3",  "LRCK"      },
  {  6, "D4",  "I2C_SDA"   },
  {  7, "D5",  "I2C_SCL"   },
  {  0, "D6",  "DOUT"      },
  {  1, "D7",  "RE_B_IN"   },
  {  2, "D8",  "RE_A_IN"   },
  {  4, "D9",  "RE_SW"     },
  {  3, "D10", "AUDIO_PWM" },
};

const uint8_t kPinCount = sizeof(kPins) / sizeof(kPins[0]);

const PinInfo *findPin(const char *token)
{
  for (uint8_t i = 0; i < kPinCount; i++) {
    if (strcasecmp(token, kPins[i].pad) == 0) {
      return &kPins[i];
    }
  }

  // Pads are all "D<n>", so a bare number is unambiguously a GPIO.
  char *end;
  long n = strtol(token, &end, 10);
  if (*token != '\0' && *end == '\0') {
    for (uint8_t i = 0; i < kPinCount; i++) {
      if (kPins[i].gpio == n) {
        return &kPins[i];
      }
    }
  }

  return nullptr;
}

int readPin(const PinInfo &pin)
{
  return digitalRead(pin.gpio);
}

PinActivity scanPin(const PinInfo &pin, uint32_t windowUs)
{
  PinActivity a = {};

  // Sampled as fast as the loop goes rather than at a fixed rate. A 3 MHz BCK
  // will alias, but aliasing still produces a mix of highs and lows -- all we
  // need is to separate "moving" from "not moving".
  uint32_t start = micros();
  int last = digitalRead(pin.gpio);

  while (micros() - start < windowUs) {
    int now = digitalRead(pin.gpio);
    a.samples++;
    if (now) {
      a.high++;
    }
    if (now != last) {
      a.edges++;
    }
    last = now;
  }

  return a;
}

bool canCountPin(uint8_t gpio)
{
  // A PWM slice counts edges on its B channel only, and GPIO n is channel n & 1.
  return (gpio & 1) == 1;
}

static uint16_t gateCount(uint8_t gpio, uint32_t gateMs)
{
  uint slice = pwm_gpio_to_slice_num(gpio);

  gpio_set_function(gpio, GPIO_FUNC_PWM);

  pwm_config cfg = pwm_get_default_config();
  pwm_config_set_clkdiv_mode(&cfg, PWM_DIV_B_RISING);
  pwm_init(slice, &cfg, false);
  pwm_set_counter(slice, 0);

  pwm_set_enabled(slice, true);
  delay(gateMs);
  pwm_set_enabled(slice, false);

  return pwm_get_counter(slice);
}

uint32_t countPinHz(const PinInfo &pin)
{
  if (!canCountPin(pin.gpio)) {
    return 0;
  }

  // 1ms first: the counter is 16 bits, so this tops out around 65 MHz without
  // wrapping. If the pin turns out to be slow, re-gate for resolution.
  uint32_t gateMs = 1;
  uint16_t count = gateCount(pin.gpio, gateMs);

  if (count < 2000) {
    gateMs = 50;
    count  = gateCount(pin.gpio, gateMs);
  }

  pinMode(pin.gpio, INPUT);      // hand the pin back
  return (uint32_t)count * 1000 / gateMs;
}
