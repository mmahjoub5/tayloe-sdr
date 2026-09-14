#include <Wire.h>

void setup()
{
  Serial.begin(115200);
  Wire.setSDA(6);
  Wire.setSCL(7);
  Wire.begin();
}

void loop()
{
  for (uint8_t addr = 1; addr < 127; addr++) {
    Wire.beginTransmission(addr);
    if (Wire.endTransmission() == 0) {
      Serial.println(addr, HEX);
    }
  }
  Serial.println("--");
  delay(2000);
}
