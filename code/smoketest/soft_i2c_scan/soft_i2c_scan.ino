// Software I2C scan. The RP2040's I2C hardware cannot use this pin pair
// in this role: on i2c1 GPIO6 can only be SDA and GPIO7 only SCL, and this
// board needs them the other way round. setSDA(7) just returns false.

#define SDA_PIN  7      // GPIO7, the board's SDA
#define SCL_PIN  6      // GPIO6, the board's SCL
#define DLY      5      // half bit, us -> ~100 kHz

// pinMode(INPUT_PULLUP) parks the output latch at 0, so OUTPUT drives a clean
// low and INPUT_PULLUP releases to the pullups. Open drain, no glitches.
static inline void release(uint8_t pin) { pinMode(pin, INPUT_PULLUP); }
static inline void drive0(uint8_t pin)  { pinMode(pin, OUTPUT); }

static void startCond()
{
  release(SDA_PIN); release(SCL_PIN); delayMicroseconds(DLY);
  drive0(SDA_PIN);                    delayMicroseconds(DLY);
  drive0(SCL_PIN);                    delayMicroseconds(DLY);
}

static void stopCond()
{
  drive0(SDA_PIN);  delayMicroseconds(DLY);
  release(SCL_PIN); delayMicroseconds(DLY);
  release(SDA_PIN); delayMicroseconds(DLY);
}

static bool writeByte(uint8_t b)
{
  for (int i = 0; i < 8; i++) {
    if (b & 0x80) release(SDA_PIN); else drive0(SDA_PIN);
    b <<= 1;
    delayMicroseconds(DLY);
    release(SCL_PIN); delayMicroseconds(DLY);
    drive0(SCL_PIN);  delayMicroseconds(DLY);
  }

  release(SDA_PIN);                   // hand SDA to the slave for the 9th bit
  delayMicroseconds(DLY);
  release(SCL_PIN); delayMicroseconds(DLY);
  bool ack = (digitalRead(SDA_PIN) == LOW);
  drive0(SCL_PIN);  delayMicroseconds(DLY);
  return ack;
}

void setup()
{
  Serial.begin(115200);
  release(SDA_PIN);
  release(SCL_PIN);
}

void loop()
{
  for (uint8_t addr = 1; addr < 127; addr++) {
    startCond();
    bool ack = writeByte(addr << 1);
    stopCond();
    if (ack) Serial.println(addr, HEX);
  }
  Serial.println("--");
  delay(2000);
}
