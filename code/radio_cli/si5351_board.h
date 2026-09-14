#pragma once

#include <Arduino.h>
#include <si5351.h>

#define BOARD_I2C_SDA   6      // D4
#define BOARD_I2C_SCL   7      // D5

// How long begin() will wait for SYS_INIT to clear before giving up. The
// library's own wait has no bound; see begin() in the .cpp.
#define SYS_INIT_TIMEOUT_MS 250

struct Si5351BoardStatus {
  bool    acked;        // the device answered its address
  uint8_t raw;          // register 0 as read
  uint8_t sysInit;
  uint8_t lolA;
  uint8_t lolB;
  uint8_t losXtal;      // reg0[3] -- the crystal reference
  uint8_t losClkin;     // reg0[4] -- CLKIN, which the Si5351A does not have
  uint8_t revId;
};

class Si5351Board {
public:
  // xtalLoad takes an SI5351_CRYSTAL_LOAD_* constant, not a pF number.
  bool begin(uint8_t xtalLoad = SI5351_CRYSTAL_LOAD_8PF,
             uint32_t xtalHz = 25000000, int32_t corr = 0);

  bool ready() const { return initOk; }

  // Whether the device ACKs its address. Deliberately not a register-value
  // check: 0x00 is a legitimate reading of register 0 on a healthy part.
  bool present();

  Si5351BoardStatus status();

  // Frequency in plain Hz. Always leaves the output enabled.
  bool setClk(uint8_t idx, uint64_t hz);
  bool enableClk(uint8_t idx, bool on);

  uint8_t readReg(uint8_t reg);
  bool    writeReg(uint8_t reg, uint8_t val);

  void resetPlls();

private:
  Si5351 si;
  bool   initOk = false;
};
