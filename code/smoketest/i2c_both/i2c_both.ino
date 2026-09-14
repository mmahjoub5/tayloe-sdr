// Bit-banged I2C scan run twice, once per possible pin orientation.
// Bit-banged so the RP2040's fixed I2C mux cannot veto either one.
//
// The orientation that prints a short list is the correct wiring.
// The wrong one reads a floating pin and prints ~90 random addresses.

#define DLY 5                      // half bit, us -> ~100 kHz

static uint8_t pinSDA, pinSCL;

static inline void release(uint8_t p) { pinMode(p, INPUT_PULLUP); }
static inline void drive0(uint8_t p)  { pinMode(p, OUTPUT); }

static void startCond()
{
  release(pinSDA); release(pinSCL); delayMicroseconds(DLY);
  drive0(pinSDA);                   delayMicroseconds(DLY);
  drive0(pinSCL);                   delayMicroseconds(DLY);
}

static void stopCond()
{
  drive0(pinSDA);  delayMicroseconds(DLY);
  release(pinSCL); delayMicroseconds(DLY);
  release(pinSDA); delayMicroseconds(DLY);
}

static bool writeByte(uint8_t b)
{
  for (int i = 0; i < 8; i++) {
    if (b & 0x80) release(pinSDA); else drive0(pinSDA);
    b <<= 1;
    delayMicroseconds(DLY);
    release(pinSCL); delayMicroseconds(DLY);
    drive0(pinSCL);  delayMicroseconds(DLY);
  }

  release(pinSDA);                 // hand SDA over for the 9th bit
  delayMicroseconds(DLY);
  release(pinSCL); delayMicroseconds(DLY);
  bool ack = (digitalRead(pinSDA) == LOW);
  drive0(pinSCL);  delayMicroseconds(DLY);
  return ack;
}

static void scanWith(uint8_t sda, uint8_t scl)
{
  pinSDA = sda;
  pinSCL = scl;
  release(pinSDA);
  release(pinSCL);
  delay(2);

  uint8_t hits[10];
  int n = 0;

  for (uint8_t addr = 1; addr < 127; addr++) {
    startCond();
    bool ack = writeByte(addr << 1);
    stopCond();
    if (ack) {
      if (n < 10) hits[n] = addr;
      n++;
    }
  }

  Serial.print("SDA=");
  Serial.print(sda);
  Serial.print(" SCL=");
  Serial.print(scl);
  Serial.print(":");

  if (n == 0) {
    Serial.print(" none");
  } else if (n > 8) {
    Serial.print(" noise, ");
    Serial.print(n);
    Serial.print(" hits");
  } else {
    for (int i = 0; i < n; i++) {
      Serial.print(" ");
      Serial.print(hits[i], HEX);
    }
  }
  Serial.println();
}

void setup()
{
  Serial.begin(115200);
}

void loop()
{
  scanWith(6, 7);
  scanWith(7, 6);
  Serial.println("--");
  delay(2000);
}
