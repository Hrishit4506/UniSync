#include "esp_camera.h"
#include <WiFi.h>
#include <HTTPClient.h>

// Wi-Fi credentials
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// Hosted Flask backend endpoint
const char* serverUrl = "https://unisync-pimy.onrender.com/register_cam";  // Update if needed

void startCameraServer();

void setup() {
  Serial.begin(115200);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected to Wi-Fi");
  Serial.println(WiFi.localIP());

  // Initialize camera
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = 5;
  config.pin_d1 = 18;
  config.pin_d2 = 19;
  config.pin_d3 = 21;
  config.pin_d4 = 36;
  config.pin_d5 = 39;
  config.pin_d6 = 34;
  config.pin_d7 = 35;
  config.pin_xclk = 0;
  config.pin_pclk = 22;
  config.pin_vsync = 25;
  config.pin_href = 23;
  config.pin_sscb_sda = 26;
  config.pin_sscb_scl = 27;
  config.pin_pwdn = 32;
  config.pin_reset = -1;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 10;
  config.fb_count = 1;

  if (esp_camera_init(&config) != ESP_OK) {
    Serial.println("Camera init failed!");
    return;
  }

  // Start camera web server
  startCameraServer();

  // Send stream URL to Flask
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String streamURL = "http://" + WiFi.localIP().toString();
    http.begin(serverUrl);
    http.addHeader("Content-Type", "application/json");

    String json = "{\"ip\": \"" + streamURL + "\"}";
    int httpCode = http.POST(json);

    if (httpCode > 0) {
      Serial.printf("POST sent, code: %d\n", httpCode);
    } else {
      Serial.printf("POST failed: %s\n", http.errorToString(httpCode).c_str());
    }

    http.end();
  }
}

void loop() {
  delay(10000);  // No action in loop
}
