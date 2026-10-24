#include <Adafruit_NeoPixel.h>

#define LED_PIN    6
#define LED_COUNT  24

Adafruit_NeoPixel ring(
  LED_COUNT,
  LED_PIN,
  NEO_GRBW + NEO_KHZ800
);

uint8_t brightness = 50;

void setAll(uint8_t r, uint8_t g, uint8_t b, uint8_t w) {
  for (int i = 0; i < LED_COUNT; i++) {
    ring.setPixelColor(
      i,
      ring.Color(r, g, b, w)
    );
  }

  ring.show();
}

void setup() {
  Serial.begin(115200);

  ring.begin();
  ring.setBrightness(brightness);
  ring.clear();
  ring.show();

  Serial.println("LIGHT_MODULE_READY");
}

void loop() {
  if (Serial.available() > 0) {

    String command = Serial.readStringUntil('\n');

    command.trim();
    command.toUpperCase();

    // ----------------------------
    // Device identification
    // ----------------------------
    if (command == "ID?") {
      Serial.println("LIGHT_MODULE");
    }

    // ----------------------------
    // Basic colors
    // ----------------------------
    else if (command == "RED") {
      setAll(255, 0, 0, 0);
      Serial.println("OK RED");
    }

    else if (command == "GREEN") {
      setAll(0, 255, 0, 0);
      Serial.println("OK GREEN");
    }

    else if (command == "BLUE") {
      setAll(0, 0, 255, 0);
      Serial.println("OK BLUE");
    }

    else if (command == "WHITE") {
      setAll(0, 0, 0, 255);
      Serial.println("OK WHITE");
    }

    // ----------------------------
    // Turn light off
    // ----------------------------
    else if (command == "OFF") {
      ring.clear();
      ring.show();

      Serial.println("OK OFF");
    }

    // ----------------------------
    // Brightness control
    // Example:
    // BRIGHTNESS 50
    // ----------------------------
    else if (command.startsWith("BRIGHTNESS ")) {

      int value = command.substring(11).toInt();

      value = constrain(value, 0, 255);

      brightness = (uint8_t)value;

      ring.setBrightness(brightness);
      ring.show();

      Serial.print("OK BRIGHTNESS ");
      Serial.println(brightness);
    }

    // ----------------------------
    // Custom RGBW values
    // Example:
    // RGBW 255 0 0 0
    // ----------------------------
    else if (command.startsWith("RGBW ")) {

      int r;
      int g;
      int b;
      int w;

      int parsed = sscanf(
        command.c_str(),
        "RGBW %d %d %d %d",
        &r,
        &g,
        &b,
        &w
      );

      if (parsed == 4) {

        r = constrain(r, 0, 255);
        g = constrain(g, 0, 255);
        b = constrain(b, 0, 255);
        w = constrain(w, 0, 255);

        setAll(
          (uint8_t)r,
          (uint8_t)g,
          (uint8_t)b,
          (uint8_t)w
        );

        Serial.println("OK RGBW");
      }

      else {
        Serial.println("ERROR RGBW FORMAT");
      }
    }

    // ----------------------------
    // Unknown command
    // ----------------------------
    else {
      Serial.println("ERROR UNKNOWN_COMMAND");
    }
  }
}