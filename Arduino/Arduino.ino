#include <Wire.h>
#include <U8g2lib.h>

U8G2_SSD1306_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

#define SERIAL_BAUD 9600

String receivedName = "";
String lastDisplayedName = "";

// Choose font based on message length
void setFontForMessage(const char* msg) {
  int len = strlen(msg);
  if (len <= 12) {
    u8g2.setFont(u8g2_font_ncenB14_tr);  // Large
  } else if (len <= 20) {
    u8g2.setFont(u8g2_font_6x13_tf);     // Medium
  } else {
    u8g2.setFont(u8g2_font_5x8_tf);      // Small
  }
}

// Centered display with autoscaling
void showMessage(const char* msg) {
  u8g2.clearBuffer();
  setFontForMessage(msg);

  int textWidth = u8g2.getStrWidth(msg);
  int x = (128 - textWidth) / 2;
  int y = 40;

  u8g2.drawStr(x, y, msg);
  u8g2.sendBuffer();
}

void setup() {
  u8g2.begin();
  Serial.begin(SERIAL_BAUD);
  delay(200);
  showMessage("Waiting...");
}

void loop() {
  if (Serial.available()) {
    receivedName = Serial.readStringUntil('\n');
    receivedName.trim();  // remove \r, \n, and spaces

    Serial.print("[Debug] Raw input: '");
    Serial.print(receivedName);
    Serial.println("'");

    if (receivedName.length() == 0) {
      receivedName = "Unknown";
    }


    if (receivedName != lastDisplayedName) {
      showMessage(receivedName.c_str());
      lastDisplayedName = receivedName;
    }
  }

  delay(50);
}
