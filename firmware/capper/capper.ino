#define BEAM_PIN    4
#define MAGNET_PIN  6

bool magnetState = false;

// -------------------------
// Magnet control function
// -------------------------
void setMagnet(bool on) {
  magnetState = on;

  if (on) {
    digitalWrite(MAGNET_PIN, HIGH);
  } else {
    digitalWrite(MAGNET_PIN, LOW);
  }
}

// -------------------------
// Cap detection function
// -------------------------
bool capDetected() {
  // For the NPN/open-collector break-beam setup
  // we discussed, LOW usually means the beam
  // is interrupted.
  return digitalRead(BEAM_PIN) == LOW;
}

void setup() {

  Serial.begin(115200);

  pinMode(BEAM_PIN, INPUT_PULLUP);
  pinMode(MAGNET_PIN, OUTPUT);

  // Always start with magnet OFF
  setMagnet(false);

  Serial.println("CAP_MODULE_READY");
}

void loop() {

  if (Serial.available() > 0) {

    String command = Serial.readStringUntil('\n');

    command.trim();
    command.toUpperCase();

    // -------------------------
    // Device identification
    // -------------------------
    if (command == "ID?") {

      Serial.println("CAP_MODULE");
    }

    // -------------------------
    // Check cap sensor
    // -------------------------
    else if (command == "CAP?") {

      if (capDetected()) {
        Serial.println("CAP DETECTED");
      } else {
        Serial.println("CAP NOT_DETECTED");
      }
    }

    // -------------------------
    // Magnet ON
    // -------------------------
    else if (command == "MAGNET ON") {

      setMagnet(true);

      Serial.println("OK MAGNET ON");
    }

    // -------------------------
    // Magnet OFF
    // -------------------------
    else if (command == "MAGNET OFF") {

      setMagnet(false);

      Serial.println("OK MAGNET OFF");
    }

    // -------------------------
    // Full module status
    // -------------------------
    else if (command == "STATUS") {

      Serial.print("CAP=");

      if (capDetected()) {
        Serial.print("DETECTED");
      } else {
        Serial.print("NOT_DETECTED");
      }

      Serial.print(" MAGNET=");

      if (magnetState) {
        Serial.println("ON");
      } else {
        Serial.println("OFF");
      }
    }

    // -------------------------
    // Unknown command
    // -------------------------
    else {

      Serial.println("ERROR UNKNOWN_COMMAND");
    }
  }
}