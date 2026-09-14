// Pin identifier. No I2C at all, just two distinguishable square waves:
//   GPIO6  ->  1 kHz
//   GPIO7  -> 10 kHz
// Probe anywhere on the board. The frequency tells you which GPIO you are on.

void setup()
{
  pinMode(6, OUTPUT);
  pinMode(7, OUTPUT);
}

static void burst()
{
  for (int i = 0; i < 5; i++) {
    digitalWrite(7, HIGH);
    delayMicroseconds(50);
    digitalWrite(7, LOW);
    delayMicroseconds(50);
  }
}

void loop()
{
  digitalWrite(6, HIGH);
  burst();
  digitalWrite(6, LOW);
  burst();
}
