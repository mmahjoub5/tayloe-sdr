// tayloe_smoke_test.ino
//
// Step 1 of bring-up: I2C scan only. Nothing is clocked, nothing is driven.
// Board: Seeed Xiao RP2040, arduino-pico core (earlephilhower).
//
// Pass condition: a device ACKs at 0x60.

#include <Wire.h>

#define I2C_SDA   6      // D4 on the Xiao
#define I2C_SCL   7      // D5 on the Xiao

// What a bus line looks like with nobody talking.
enum LineState {
  LINE_STUCK_LOW,   // low even against the internal pullup
  LINE_NO_PULLUP,   // only the weak internal pullup is holding it up
  LINE_IDLE_HIGH    // external pullups present, line released
};

// Takes the pin away from the I2C block for the duration; hand it back with
// gpio_set_function() when done probing.
static LineState lineState(uint8_t pin)
{
  // Settle generously: this is a DC test, and it has to outlast the RC of a
  // slow net. The internal pullup into 100nF is a ~5ms time constant, so a
  // short settle would report "stuck low" for a line that is merely sluggish.
  // That distinction is the whole point of this function.
  pinMode(pin, INPUT_PULLUP);
  delay(20);
  if (!digitalRead(pin)) return LINE_STUCK_LOW;

  // A 1k external pullup beats the ~50k internal pulldown.
  pinMode(pin, INPUT_PULLDOWN);
  delay(20);
  LineState state = digitalRead(pin) ? LINE_IDLE_HIGH : LINE_NO_PULLUP;

  pinMode(pin, INPUT_PULLUP);
  return state;
}

static void printLine(const char *name, LineState state)
{
  Serial.print("  ");
  Serial.print(name);
  switch (state) {
    case LINE_STUCK_LOW: Serial.println(" held low");                       break;
    case LINE_NO_PULLUP: Serial.println(" high, internal pullup only");     break;
    case LINE_IDLE_HIGH: Serial.println(" idle high");                      break;
  }
}

// Drive SDA low, release it, and time the climb back to a logic high. A healthy
// 1k-pulled line gets there in well under a microsecond -- faster than this loop
// can see, and "0us" is the passing answer. Tens of microseconds means there is
// capacitance on the net that does not belong there.
static uint32_t sdaRiseTime()
{
  pinMode(I2C_SDA, INPUT_PULLUP);
  digitalWrite(I2C_SDA, LOW);        // dir -> output, pulls the line down
  delayMicroseconds(100);            // let it settle all the way

  noInterrupts();
  uint32_t t0 = micros();
  digitalWrite(I2C_SDA, HIGH);       // dir -> input, released to the pullups
  uint32_t t = t0;
  while (!digitalRead(I2C_SDA) && (t - t0) < 5000) {
    t = micros();
  }
  interrupts();

  gpio_set_function(I2C_SDA, GPIO_FUNC_I2C);
  return t - t0;
}

// A device interrupted mid-byte keeps SDA low until it gets the rest of its
// clocks. Nine of them plus a STOP frees the bus if that is the problem.
// pinMode(INPUT_PULLUP) leaves the output register at 0, so digitalWrite here
// only flips direction: HIGH releases to the pullups, LOW pulls to GND.
static void busRecover()
{
  pinMode(I2C_SDA, INPUT_PULLUP);
  pinMode(I2C_SCL, INPUT_PULLUP);

  for (int i = 0; i < 9 && !digitalRead(I2C_SDA); i++) {
    digitalWrite(I2C_SCL, LOW);
    delayMicroseconds(5);
    digitalWrite(I2C_SCL, HIGH);
    delayMicroseconds(5);
  }

  digitalWrite(I2C_SDA, LOW);     // STOP: SDA rises while SCL is high
  delayMicroseconds(5);
  digitalWrite(I2C_SCL, HIGH);
  delayMicroseconds(5);
  digitalWrite(I2C_SDA, HIGH);
  delayMicroseconds(5);
}

// The ACK bit is just "is SDA low on the 9th clock". A line stuck low reads as
// an ACK from every address on the bus, so check that before believing a scan.
static bool checkBus(int hz)
{
  LineState sda = lineState(I2C_SDA);
  LineState scl = lineState(I2C_SCL);

  if (sda == LINE_STUCK_LOW) {
    busRecover();
    sda = lineState(I2C_SDA);
  }

  printLine("SDA", sda);
  printLine("SCL", scl);

  // Only meaningful once the line can actually get high.
  uint32_t rise = 0, halfBit = (1000000 / hz) / 2;
  if (sda != LINE_STUCK_LOW) {
    rise = sdaRiseTime();
    Serial.print("  SDA rise ");
    Serial.print(rise);
    Serial.print("us vs ");
    Serial.print(halfBit);
    Serial.println("us half-bit");
  }

  gpio_set_function(I2C_SDA, GPIO_FUNC_I2C);
  gpio_set_function(I2C_SCL, GPIO_FUNC_I2C);

  if (rise >= halfBit) {
    Serial.println("  SDA cannot rise inside half a bit -- it still reads low");
    Serial.println("  when the ACK is sampled, so every address looks present");
    Serial.print("  that is roughly ");
    Serial.print((int)(rise * 1.5));    // 1.6V of 3.3V is 0.66 tau, C = tau / 1k
    Serial.println(" nF on the net if the pullup is 1k");
    Serial.println("  check: stray cap on SDA, Tayloe sampling cap on the wrong");
    Serial.println("         net, pullup tied to a rail that is not up");
  }

  if (sda == LINE_STUCK_LOW || scl == LINE_STUCK_LOW) {
    Serial.println("  bus not idle, skipping scan -- every address would ACK");
    Serial.println("  check: SDA/SCL shorted to GND, solder bridge under the");
    Serial.println("         Si5351, Si5351 VDD missing while its pins are driven");
    return false;
  }

  if (sda == LINE_NO_PULLUP || scl == LINE_NO_PULLUP) {
    Serial.println("  warning: external 1k pullups look unpopulated");
  }

  return true;
}

// Cheap between-probe check: SDA must be back at idle before the next address,
// otherwise whatever that probe reports is meaningless.
static bool sdaIdle()
{
  pinMode(I2C_SDA, INPUT_PULLUP);
  delayMicroseconds(50);     // must outlast the measured rise, not race it
  bool high = digitalRead(I2C_SDA);
  gpio_set_function(I2C_SDA, GPIO_FUNC_I2C);
  return high;
}

static void printAddr(uint8_t addr)
{
  Serial.print("0x");
  if (addr < 16) Serial.print("0");
  Serial.print(addr, HEX);
}

// Runs of consecutive hits collapse to a range -- 95 separate lines is noise,
// and the endpoints are the part that tells you anything.
static void printRun(uint8_t start, uint8_t end)
{
  Serial.print("  ");
  printAddr(start);
  if (end != start) {
    Serial.print(" - ");
    printAddr(end);
    Serial.print("   (");
    Serial.print(end - start + 1);
    Serial.print(" addresses)");
  }
  if (start <= 0x60 && end >= 0x60) Serial.print("   <- Si5351 0x60 in here");
  Serial.println();
}

// Line endings are not keypresses.
static bool stopKeyPressed()
{
  while (Serial.available()) {
    char c = Serial.read();
    if (c != '\r' && c != '\n') return true;
  }
  return false;
}

// Scope mode: park a repeating open-drain square wave on one line so the rising
// edge can be measured directly, instead of hunting for the 9th clock inside a
// scan. 200us pulled down, 800us released -- long enough for even a badly
// loaded net to finish its climb.
//
// The release is pinMode(INPUT), pulls disabled, NOT INPUT_PULLUP. The internal
// ~50k would otherwise stand in for a missing external pullup and hide exactly
// the fault we are looking for. With no external pullup this line simply never
// comes back up, which is an unambiguous answer on a scope.
static void scopeMode(uint8_t pin, const char *name)
{
  Serial.print("scope mode on ");
  Serial.println(name);
  Serial.println("  measure 10-90% on the rising edge; t_rise = 2.2 * R * C");
  Serial.println("  a line that never rises has no external pullup at all");
  Serial.println("  use a 10x probe -- a 1x probe adds ~100pF and fakes the fault");
  Serial.println("  any key to stop");

  pinMode(pin, OUTPUT);
  digitalWrite(pin, LOW);      // output register stays 0 for the whole run

  // Only a real character stops this. The serial monitor's trailing newline
  // arrives just behind the keypress, and treating that as a stop request ends
  // scope mode before the scope ever sees an edge.
  uint32_t cycles = 0;
  while (!stopKeyPressed()) {
    pinMode(pin, OUTPUT);      // drives the stored 0
    delayMicroseconds(200);
    pinMode(pin, INPUT);       // released, no internal pull
    delayMicroseconds(800);

    if (++cycles % 2000 == 0) Serial.println("  ...running");
  }

  gpio_set_function(pin, GPIO_FUNC_I2C);
  Serial.println("scope mode off");
}

// Time SDA's climb with the internal pullup DISABLED, so only an external
// pullup can bring it back. This is what the INPUT_PULLDOWN check was reaching
// for, without depending on a guessed settle time.
static uint32_t riseNoPull(bool *held)
{
  pinMode(I2C_SDA, OUTPUT);
  digitalWrite(I2C_SDA, LOW);
  delayMicroseconds(200);

  uint32_t t0 = micros();
  pinMode(I2C_SDA, INPUT);           // released, no pulls at all
  uint32_t t = t0;
  while (!digitalRead(I2C_SDA) && (t - t0) < 50000) {
    t = micros();
  }
  uint32_t rise = t - t0;

  delay(1);                          // a pullup holds it; a floating net wanders
  *held = digitalRead(I2C_SDA);

  gpio_set_function(I2C_SDA, GPIO_FUNC_I2C);
  return rise;
}

// Count how often SDA changes state with nothing driving it and no pulls. A
// connected line never changes. A floating one rattles.
static int sdaRattle()
{
  pinMode(I2C_SDA, INPUT);
  int changes = 0;
  int last = digitalRead(I2C_SDA);
  for (int i = 0; i < 2000; i++) {
    int now = digitalRead(I2C_SDA);
    if (now != last) changes++;
    last = now;
    delayMicroseconds(10);
  }
  gpio_set_function(I2C_SDA, GPIO_FUNC_I2C);
  return changes;
}

// Probe one address repeatedly. A real chip answers every single time; a
// floating line answers at whatever rate the noise happens to favour.
static int probeRepeat(uint8_t addr, int tries)
{
  int acks = 0;
  for (int i = 0; i < tries; i++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) acks++;
    delayMicroseconds(200);
  }
  return acks;
}

// 0x60 against addresses nothing should live at. If the Si5351 answers every
// time while the controls answer at the noise rate, the part is fine and only
// the phantoms are fake -- which is a completely different repair.
static void addressStats()
{
  const uint8_t controls[] = { 0x0B, 0x33, 0x5A, 0x77 };
  const int tries = 100;

  Serial.print("  0x60 answered ");
  Serial.print(probeRepeat(0x60, tries));
  Serial.print("/");
  Serial.println(tries);

  int total = 0;
  for (unsigned i = 0; i < sizeof(controls); i++) {
    total += probeRepeat(controls[i], tries);
  }
  Serial.print("  empty addresses averaged ");
  Serial.print(total / (int)sizeof(controls));
  Serial.print("/");
  Serial.println(tries);
}

static int i2cScan(int hz)
{
  int found = 0;
  int firstStuck = -1;          // where SDA stopped coming back to idle
  int runStart = -1, runEnd = -1;

  Wire.setClock(hz);

  Serial.print("--- scan @ ");
  Serial.print(hz / 1000);
  Serial.println(" kHz ---");

  if (!checkBus(hz)) {
    return -1;
  }

  for (uint8_t addr = 1; addr < 127; addr++) {
    if (!sdaIdle() && firstStuck < 0) {
      firstStuck = addr;
    }

    Wire.beginTransmission(addr);
    bool ack = (Wire.endTransmission() == 0);

    if (ack) {
      found++;
      if (runStart < 0) runStart = addr;
      runEnd = addr;
    } else if (runStart >= 0) {
      printRun(runStart, runEnd);
      runStart = -1;
    }
  }
  if (runStart >= 0) printRun(runStart, runEnd);

  if (found == 0) {
    Serial.println("  nothing responded");
    Serial.println("  check: 1k pullups populated, SDA/SCL not swapped,");
    Serial.println("         Si5351 VDD at 3.3V, part reflowed cleanly");
  } else if (found > 8) {
    Serial.print("  ");
    Serial.print(found);
    Serial.println(" hits -- that is the bus misbehaving, not that many parts");

    if (firstStuck >= 0) {
      Serial.print("  SDA first failed to return to idle at ");
      printAddr(firstStuck);
      Serial.println();
    }

    addressStats();

    bool held = false;
    uint32_t bare = riseNoPull(&held);
    Serial.print("  SDA with no internal pullup: ");
    if (bare >= 50000) {
      Serial.println("never came up -> no external pullup at all");
    } else {
      Serial.print(bare);
      Serial.println(held ? "us, and it held" : "us, then it drifted back down");
    }

    Serial.print("  SDA changed state ");
    Serial.print(sdaRattle());
    Serial.println(" times in 20ms undriven (a connected line: 0)");
  }

  return found;
}

void setup()
{
  Serial.begin(115200);
  while (!Serial && millis() < 4000) { }

  Wire.setSDA(I2C_SDA);
  Wire.setSCL(I2C_SCL);
  Wire.begin();
  Wire.setClock(100000);

  Serial.println();
  Serial.println("=== Tayloe board: I2C scan ===");
  Serial.println("keys: d = square wave on SDA, c = on SCL (for the scope)");
}

void loop()
{
  if (Serial.available()) {
    char key = Serial.read();
    while (key == '\r' || key == '\n') {     // skip past a previous line ending
      key = Serial.available() ? Serial.read() : 0;
    }
    delay(50);                                // let the trailing newline land
    while (Serial.available()) Serial.read();
    if (key == 'd') {
      scopeMode(I2C_SDA, "SDA");
    } else if (key == 'c') {
      scopeMode(I2C_SCL, "SCL");
    }
  }

  int found = i2cScan(100000);

  // A scan that "finds" most of the address space is a bus fault. Re-running it
  // ten times slower stretches the probe's half-bit from 5us to 50us: if the
  // hits go away, the line was just too slow to rise, not held low.
  if (found > 8) {
    Serial.println("  retrying slower to separate rise time from a stuck line");
    i2cScan(10000);
  }

  delay(3000);
}
