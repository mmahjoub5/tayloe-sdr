#include "commands.h"

#include <string.h>
#include <stdlib.h>

#include "board_pins.h"
#include "audio_adc.h"

Si5351Board board;
AudioAdc    adc;

static const char *levelName(int level)
{
  return level ? "high" : "low";
}

static void printPinRow(const PinInfo &pin)
{
  char buf[64];
  snprintf(buf, sizeof(buf), "  %-4s gpio %-3u %-10s %s",
           pin.pad, pin.gpio, pin.net, levelName(readPin(pin)));
  Serial.println(buf);
}

static void cmdHelp()
{
  Serial.println("commands:");
  Serial.println("  help                 this list");
  Serial.println("  gpio                 all pins with live levels");
  Serial.println("  gpio <pad|gpio>      one pin, e.g. 'gpio D4' or 'gpio 6'");
  Serial.println("  freq <pad|gpio>      hardware edge count; odd gpios only");
  Serial.println("  pull <pad|gpio> up|down|none   set the internal pull");
  Serial.println("  probe                does the Si5351 answer its address");
  Serial.println("  status               device status register, decoded");
  Serial.println("  reg <addr>           read a register (0x.. or decimal)");
  Serial.println("  reg <addr> <val>     write a register");
  Serial.println("  clk <n> <hz>         set CLK n frequency");
  Serial.println("  clk <n> on|off       enable or disable CLK n");
  Serial.println("  init [pf] [corr]     re-init; pf is 0, 6, 8 or 10");
  Serial.println("  reset                reset both PLLs");
  Serial.println("  adc start [rate]     set scki on clk1, then start capture");
  Serial.println("  adc stop             stop capture and scki");
  Serial.println("  adc read [frames]    read frames, report min/max per channel");
  Serial.println("  adc capture [frames] binary I/Q dump for the host");
  Serial.println("  adc stream [secs] [decim] [bits]  continuous I/Q; decim 1 (48k) or 2 (24k), bits 32 or 24");
  Serial.println("  adc stats                  last stream's frames produced and overruns");
  Serial.println("  bootsel              reboot into the UF2 bootloader (RPI-RP2 drive) to flash");
}

static void cmdGpio(const char *arg)
{
  if (arg == nullptr) {
    for (uint8_t i = 0; i < kPinCount; i++) {
      printPinRow(kPins[i]);
    }
    return;
  }

  const PinInfo *pin = findPin(arg);
  if (pin == nullptr) {
    Serial.print("no such pin: ");
    Serial.println(arg);
    return;
  }
  printPinRow(*pin);

  PinActivity a = scanPin(*pin);
  char buf[80];
  if (a.edges == 0) {
    snprintf(buf, sizeof(buf), "       static over %lu samples in 2ms",
             (unsigned long)a.samples);
  } else {
    snprintf(buf, sizeof(buf), "       toggling: %lu edges, %lu%% high of %lu samples",
             (unsigned long)a.edges,
             (unsigned long)(a.high * 100 / a.samples),
             (unsigned long)a.samples);
  }
  Serial.println(buf);
}

// Pull state changes what a floating pin looks like: capacitive pickup from a
// nearby clock collapses under a 50k pull, a genuinely driven output does not.
static void cmdPull(const char *arg, const char *mode)
{
  if (arg == nullptr || mode == nullptr) {
    Serial.println("usage: pull <pad|gpio> up|down|none");
    return;
  }

  const PinInfo *pin = findPin(arg);
  if (pin == nullptr) {
    Serial.print("no such pin: ");
    Serial.println(arg);
    return;
  }

  if (strcasecmp(mode, "up") == 0) {
    pinMode(pin->gpio, INPUT_PULLUP);
  } else if (strcasecmp(mode, "down") == 0) {
    pinMode(pin->gpio, INPUT_PULLDOWN);
  } else if (strcasecmp(mode, "none") == 0) {
    pinMode(pin->gpio, INPUT);
  } else {
    Serial.println("usage: pull <pad|gpio> up|down|none");
    return;
  }

  Serial.print("  ");
  Serial.print(pin->pad);
  Serial.print(" pull ");
  Serial.println(mode);
}

static void cmdFreq(const char *arg)
{
  if (arg == nullptr) {
    Serial.println("usage: freq <pad|gpio>");
    return;
  }

  const PinInfo *pin = findPin(arg);
  if (pin == nullptr) {
    Serial.print("no such pin: ");
    Serial.println(arg);
    return;
  }

  if (!canCountPin(pin->gpio)) {
    Serial.print("gpio ");
    Serial.print(pin->gpio);
    Serial.println(" is even; hardware counting needs an odd gpio (a PWM B channel)");
    return;
  }

  uint32_t hz = countPinHz(*pin);
  char buf[64];
  if (hz == 0) {
    snprintf(buf, sizeof(buf), "  %s: no edges", pin->pad);
  } else {
    snprintf(buf, sizeof(buf), "  %s: %lu Hz", pin->pad, (unsigned long)hz);
  }
  Serial.println(buf);
}

static void cmdProbe()
{
  Serial.println(board.present() ? "0x60 acked" : "0x60 did not ack");
}

static void cmdStatus()
{
  Si5351BoardStatus s = board.status();

  if (!s.acked) {
    Serial.println("0x60 did not ack; the values below are not from the device");
  }

  char buf[80];
  snprintf(buf, sizeof(buf), "reg0 0x%02X", s.raw);
  Serial.println(buf);
  snprintf(buf, sizeof(buf), "  SYS_INIT %u  LOL_A %u  LOL_B %u  REVID %u",
           s.sysInit, s.lolA, s.lolB, s.revId);
  Serial.println(buf);
  snprintf(buf, sizeof(buf), "  LOS_XTAL %u  LOS_CLKIN %u (no CLKIN pin on the A, always 1)",
           s.losXtal, s.losClkin);
  Serial.println(buf);
}

static bool parseNum(const char *tok, long *out)
{
  char *end;
  long v = strtol(tok, &end, 0);       // base 0 accepts 0x.. and decimal
  if (*tok == '\0' || *end != '\0') {
    return false;
  }
  *out = v;
  return true;
}

static void cmdReg(const char *addrTok, const char *valTok)
{
  long addr;
  if (addrTok == nullptr || !parseNum(addrTok, &addr) || addr < 0 || addr > 255) {
    Serial.println("usage: reg <addr> [val]");
    return;
  }

  char buf[48];

  if (valTok == nullptr) {
    snprintf(buf, sizeof(buf), "reg %ld = 0x%02X", addr, board.readReg(addr));
    Serial.println(buf);
    return;
  }

  long val;
  if (!parseNum(valTok, &val) || val < 0 || val > 255) {
    Serial.println("value must be 0..255");
    return;
  }

  bool ok = board.writeReg(addr, val);
  snprintf(buf, sizeof(buf), "reg %ld <- 0x%02X %s", addr, (unsigned)val,
           ok ? "ok" : "failed");
  Serial.println(buf);
}

static void cmdClk(const char *idxTok, const char *argTok)
{
  long idx;
  if (idxTok == nullptr || !parseNum(idxTok, &idx) || idx < 0 || idx > 2) {
    Serial.println("usage: clk <0|1|2> <hz|on|off>");
    return;
  }

  if (argTok == nullptr) {
    Serial.println("usage: clk <0|1|2> <hz|on|off>");
    return;
  }

  if (strcasecmp(argTok, "on") == 0 || strcasecmp(argTok, "off") == 0) {
    bool on = strcasecmp(argTok, "on") == 0;
    Serial.println(board.enableClk(idx, on) ? (on ? "enabled" : "disabled")
                                            : "failed");
    return;
  }

  char *end;
  unsigned long long hz = strtoull(argTok, &end, 10);
  if (*argTok == '\0' || *end != '\0' || hz == 0) {
    Serial.println("frequency must be a positive number of hertz");
    return;
  }

  if (board.setClk(idx, hz)) {
    Serial.print("clk ");
    Serial.print(idx);
    Serial.print(" = ");
    Serial.print((unsigned long)hz);
    Serial.println(" Hz");
  } else {
    Serial.println("set_freq rejected that frequency");
  }
}

static void cmdInit(const char *pfTok, const char *corrTok)
{
  uint8_t load = SI5351_CRYSTAL_LOAD_8PF;

  if (pfTok != nullptr) {
    long pf;
    if (!parseNum(pfTok, &pf)) {
      Serial.println("load capacitance must be 0, 6, 8 or 10");
      return;
    }
    switch (pf) {
      case 0:  load = SI5351_CRYSTAL_LOAD_0PF;  break;
      case 6:  load = SI5351_CRYSTAL_LOAD_6PF;  break;
      case 8:  load = SI5351_CRYSTAL_LOAD_8PF;  break;
      case 10: load = SI5351_CRYSTAL_LOAD_10PF; break;
      default:
        Serial.println("load capacitance must be 0, 6, 8 or 10");
        return;
    }
  }

  long corr = 0;
  if (corrTok != nullptr && !parseNum(corrTok, &corr)) {
    Serial.println("correction must be a number");
    return;
  }

  Serial.println(board.begin(load, 25000000, corr) ? "init ok" : "init failed");
}

static void cmdAdc(const char *sub, const char *arg, const char *arg2, const char *arg3)
{
  if (sub == nullptr) {
    Serial.println("usage: adc start|stop|read");
    return;
  }

  if (strcasecmp(sub, "start") == 0) {
    long rate = ADC_DEFAULT_RATE;
    if (arg != nullptr && (!parseNum(arg, &rate) || rate <= 0)) {
      Serial.println("rate must be a positive number of samples per second");
      return;
    }

    switch (adc.begin(board, rate)) {
      case AdcStart::ClockNotReady:
        Serial.println("si5351 not initialized; 'init' first");
        return;
      case AdcStart::ClockFailed:
        Serial.println("clk1 rejected the scki frequency");
        return;
      case AdcStart::PioFailed:
        Serial.println("no free pio state machine");
        return;
      case AdcStart::Ok:
        break;
    }

    char buf[80];
    snprintf(buf, sizeof(buf), "capturing at %lu Hz, scki %lu Hz on clk%d",
             (unsigned long)adc.rate(), (unsigned long)adc.sckiHz(), ADC_SCKI_CLK);
    Serial.println(buf);
    return;
  }

  if (strcasecmp(sub, "stop") == 0) {
    adc.end();
    Serial.println("stopped");
    return;
  }

  if (strcasecmp(sub, "capture") == 0) {
    if (!adc.running()) {
      Serial.println("not capturing; 'adc start' first");
      return;
    }

    long frames = 4096;
    if (arg != nullptr &&
        (!parseNum(arg, &frames) || frames <= 0 || frames > ADC_MAX_CAPTURE)) {
      Serial.println("frames must be 1..8192");
      return;
    }

    static int32_t buf[2 * ADC_MAX_CAPTURE];
    uint16_t got = adc.captureRaw(buf, frames);

    // ASCII header then raw little-endian int16 pairs, so the host knows
    // exactly how many bytes to read.
    Serial.print("CAPTURE ");
    Serial.print(got);
    Serial.print(" ");
    Serial.println(adc.rate());
    Serial.flush();
    Serial.write((const uint8_t *)buf, (size_t)got * 2 * sizeof(int32_t));
    Serial.flush();
    return;
  }

  if (strcasecmp(sub, "stream") == 0) {
    if (!adc.running()) {
      Serial.println("not capturing; 'adc start' first");
      return;
    }

    long secs = 5;
    if (arg != nullptr && (!parseNum(arg, &secs) || secs <= 0 || secs > 120)) {
      Serial.println("seconds must be 1..120");
      return;
    }

    long decim = ADC_DECIM;
    if (arg2 != nullptr && (!parseNum(arg2, &decim) || decim < 1 || decim > ADC_DECIM_MAX)) {
      Serial.println("decim must be 1 or 2");
      return;
    }

    long bits = 32;
    if (arg3 != nullptr && (!parseNum(arg3, &bits) || (bits != 32 && bits != 24))) {
      Serial.println("bits must be 32 or 24");
      return;
    }

    // A 24-bit stream says so in a third number; a 32-bit header stays two numbers, as older hosts expect.
    uint32_t frames = (uint32_t)secs * adc.streamRate(decim);
    Serial.print("STREAM ");
    Serial.print(frames);
    Serial.print(" ");
    if (bits == 24) {
      Serial.print(adc.streamRate(decim));
      Serial.println(" 24");
    } else {
      Serial.println(adc.streamRate(decim));
    }
    Serial.flush();

    adc.streamRaw(frames, decim, bits);
    Serial.flush();
    return;
  }

  if (strcasecmp(sub, "stats") == 0) {
    Serial.print("last stream: produced ");
    Serial.print(adc.streamProduced());
    Serial.print(" frames, overruns ");
    Serial.println(adc.streamOverruns());
    return;
  }

  if (strcasecmp(sub, "read") == 0) {
    if (!adc.running()) {
      Serial.println("not capturing; 'adc start' first");
      return;
    }

    long frames = 256;
    if (arg != nullptr && (!parseNum(arg, &frames) || frames <= 0 || frames > 4096)) {
      Serial.println("frames must be 1..4096");
      return;
    }

    AdcCapture c = adc.capture(frames);

    char buf[80];
    snprintf(buf, sizeof(buf), "%u/%ld frames%s%s", c.frames, frames,
             c.timedOut ? ", timed out waiting for clocks" : "", "");
    Serial.println(buf);

    if (c.frames > 0) {
      snprintf(buf, sizeof(buf), "  L %ld .. %ld", (long)c.lMin, (long)c.lMax);
      Serial.println(buf);
      snprintf(buf, sizeof(buf), "  R %ld .. %ld", (long)c.rMin, (long)c.rMax);
      Serial.println(buf);
    }
    return;
  }

  Serial.print("unknown adc subcommand: ");
  Serial.println(sub);
}

void printBanner()
{
  Serial.println();
  Serial.println("radio cli -- 'help' for commands");
}

void handleLine(char *line)
{
  char *cmd = strtok(line, " \t");
  if (cmd == nullptr) {
    return;
  }

  char *a1 = strtok(nullptr, " \t");
  char *a2 = strtok(nullptr, " \t");
  char *a3 = strtok(nullptr, " \t");
  char *a4 = strtok(nullptr, " \t");

  if (strcasecmp(cmd, "help") == 0) {
    cmdHelp();
  } else if (strcasecmp(cmd, "gpio") == 0) {
    cmdGpio(a1);
  } else if (strcasecmp(cmd, "pull") == 0) {
    cmdPull(a1, a2);
  } else if (strcasecmp(cmd, "freq") == 0) {
    cmdFreq(a1);
  } else if (strcasecmp(cmd, "probe") == 0) {
    cmdProbe();
  } else if (strcasecmp(cmd, "status") == 0) {
    cmdStatus();
  } else if (strcasecmp(cmd, "reg") == 0) {
    cmdReg(a1, a2);
  } else if (strcasecmp(cmd, "clk") == 0) {
    cmdClk(a1, a2);
  } else if (strcasecmp(cmd, "init") == 0) {
    cmdInit(a1, a2);
  } else if (strcasecmp(cmd, "adc") == 0) {
    cmdAdc(a1, a2, a3, a4);
  } else if (strcasecmp(cmd, "reset") == 0) {
    board.resetPlls();
    Serial.println("plls reset");
  } else if (strcasecmp(cmd, "bootsel") == 0) {
    // A second remote way into the bootloader, besides opening the port at 1200 baud.
    Serial.println("rebooting into the UF2 bootloader");
    Serial.flush();
    delay(100);
    rp2040.rebootToBootloader();
  } else {
    Serial.print("unknown command: ");
    Serial.println(cmd);
  }
}
