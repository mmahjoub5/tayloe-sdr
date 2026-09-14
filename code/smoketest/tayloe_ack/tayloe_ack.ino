// tayloe_ack.ino
//
// One address, one frame, slow. Nothing else.
// Scope SDA and SCL, trigger on TRIG, look at the 9th clock.
//
// 10 kHz -> 50us per half bit, ~900us for the frame, repeated every 100ms.

#include <Wire.h>

#define I2C_SDA   6      // D4 on the Xiao
#define I2C_SCL   7      // D5 on the Xiao
#define TRIG      3      // D10, scope trigger. Ignore it if the pin is in use.
#define ADDR      0x60   // Si5351

void setup()
{
  Serial.begin(115200);

  pinMode(TRIG, OUTPUT);
  digitalWrite(TRIG, LOW);

  Wire.setSDA(I2C_SDA);
  Wire.setSCL(I2C_SCL);
  Wire.begin();
  Wire.setClock(10000);
}

void loop()
{
  digitalWrite(TRIG, HIGH);
  Wire.beginTransmission(ADDR);
  uint8_t r = Wire.endTransmission();
  digitalWrite(TRIG, LOW);

  Serial.println(r == 0 ? "ACK" : "no ACK");
  delay(100);
}
