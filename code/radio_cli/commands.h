#pragma once

#include <Arduino.h>
#include "si5351_board.h"

extern Si5351Board board;

// Parses and runs one command line. The line is modified in place.
void handleLine(char *line);

void printBanner();
