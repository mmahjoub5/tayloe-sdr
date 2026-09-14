#include "si5351_board.h"

#include <Wire.h>

bool Si5351Board::begin(uint8_t xtalLoad, uint32_t xtalHz, int32_t corr)
{
  initOk = false;

  // The library's init() calls a bare Wire.begin() and never sets pins, so the
  // pin assignment has to happen out here first.
  Wire.setSDA(BOARD_I2C_SDA);
  Wire.setSCL(BOARD_I2C_SCL);
  Wire.begin();

  if (!present()) {
    return false;
  }

  // init() polls SYS_INIT with `while (status_reg >> 7 == 1)` and no timeout,
  // so a read that keeps returning 0xFF spins forever and the CLI needs a
  // reflash to recover. Clear the flag under our own bound first; init()'s
  // loop then passes on its first iteration.
  uint32_t deadline = millis() + SYS_INIT_TIMEOUT_MS;
  while (readReg(SI5351_DEVICE_STATUS) >> 7) {
    if ((int32_t)(millis() - deadline) >= 0) {
      return false;
    }
  }

  initOk = si.init(xtalLoad, xtalHz, corr);
  return initOk;
}

bool Si5351Board::present()
{
  Wire.beginTransmission(SI5351_BUS_BASE_ADDR);
  return Wire.endTransmission() == 0;
}

Si5351BoardStatus Si5351Board::status()
{
  Si5351BoardStatus s = {};

  s.acked = present();
  s.raw   = readReg(SI5351_DEVICE_STATUS);

  // Decoded from the byte we already have rather than via update_status(),
  // which would read the same register a second time -- and which also folds
  // both LOS bits into one field named for the wrong one. Per the datasheet,
  // LOS_XTAL is reg0[3] and LOS_CLKIN is reg0[4]; only the former says
  // anything about this board, since the Si5351A has no CLKIN pin.
  s.sysInit  = (s.raw >> 7) & 0x01;
  s.lolB     = (s.raw >> 6) & 0x01;
  s.lolA     = (s.raw >> 5) & 0x01;
  s.losClkin = (s.raw >> 4) & 0x01;
  s.losXtal  = (s.raw >> 3) & 0x01;
  s.revId    =  s.raw       & 0x03;

  return s;
}

bool Si5351Board::setClk(uint8_t idx, uint64_t hz)
{
  if (idx > 2) {
    return false;
  }
  // set_freq() works in hundredths of a hertz.
  if (si.set_freq(hz * SI5351_FREQ_MULT, (enum si5351_clock)idx) != 0) {
    return false;
  }

  // set_freq() only enables the output the first time a given clock is set --
  // it guards that on clk_first_set[]. So a clock that was explicitly disabled
  // stays dark on every later call, with set_freq still returning success.
  // Enable here so setting a frequency always means the clock is running.
  si.output_enable((enum si5351_clock)idx, 1);
  return true;
}

bool Si5351Board::enableClk(uint8_t idx, bool on)
{
  if (idx > 2) {
    return false;
  }
  si.output_enable((enum si5351_clock)idx, on ? 1 : 0);
  return true;
}

uint8_t Si5351Board::readReg(uint8_t reg)
{
  return si.si5351_read(reg);
}

bool Si5351Board::writeReg(uint8_t reg, uint8_t val)
{
  return si.si5351_write(reg, val) == 0;
}

void Si5351Board::resetPlls()
{
  si.pll_reset(SI5351_PLLA);
  si.pll_reset(SI5351_PLLB);
}
