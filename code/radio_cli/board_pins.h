#pragma once

#include <Arduino.h>

// The board's signal names, so the CLI can label its own output. Pad order is
// not GPIO order on the Xiao, which is the whole reason both are kept here.
struct PinInfo {
  uint8_t     gpio;
  const char *pad;      // silkscreen label, "D4"
  const char *net;      // schematic net, "I2C_SDA"
};

extern const PinInfo kPins[];
extern const uint8_t kPinCount;

// Accepts a pad label ("D4", case insensitive) or a bare GPIO number ("6").
// Returns nullptr if neither matches.
const PinInfo *findPin(const char *token);

// Live level. digitalRead() reads the pad through gpio_get() without touching
// the pin's function, so this is safe on pins the I2C block owns.
int readPin(const PinInfo &pin);

// Result of watching a pin for a couple of milliseconds. A clock shows up as
// roughly half the samples high with many edges; a static line shows zero
// edges. This is how you tell a dead clock from a running one without a scope.
struct PinActivity {
  uint32_t samples;
  uint32_t high;
  uint32_t edges;
};

PinActivity scanPin(const PinInfo &pin, uint32_t windowUs = 2000);

// Hardware edge counting via a PWM slice. Only odd GPIOs work: a slice counts
// edges on its B channel, and GPIO n maps to channel n & 1. Far more accurate
// than scanPin(), which is limited by how fast a software loop can sample.
bool canCountPin(uint8_t gpio);

// Measured frequency in Hz, or 0 if nothing is toggling. Gates automatically:
// a short gate keeps the 16-bit counter from wrapping on fast pins, a long one
// gives resolution on slow ones.
uint32_t countPinHz(const PinInfo &pin);
