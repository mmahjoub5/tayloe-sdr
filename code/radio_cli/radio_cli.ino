// Serial CLI for the Tayloe receiver board.
// Seeed XIAO RP2040, arduino-pico core. 115200 baud, one command per line.
//
// Assumes working hardware: it reports what it observed and leaves the
// interpretation to you.

#include "commands.h"

#define LINE_MAX 64

static char lineBuf[LINE_MAX];
static uint8_t lineLen = 0;

void setup()
{
  Serial.begin(115200);
  while (!Serial && millis() < 4000) { }

  printBanner();
  Serial.println(board.begin() ? "si5351 ready" : "si5351 not responding");
}

void loop()
{
  while (Serial.available()) {
    char c = Serial.read();

    // The serial monitor appends line endings; either one ends a line, and an
    // empty line is not a command.
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        lineBuf[lineLen] = '\0';
        handleLine(lineBuf);
        lineLen = 0;
      }
      continue;
    }

    if (lineLen < LINE_MAX - 1) {
      lineBuf[lineLen++] = c;
    }
  }
}
