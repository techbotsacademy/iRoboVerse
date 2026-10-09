#include <WiFi.h>
#include <WebServer.h>
#include <Audio.h>

const char* WIFI_SSID = "SSID";
const char* WIFI_PASSWORD = "87654321";

WebServer server(80);
Audio audio;

void connectESP32() {
  WiFi.mode(WIFI_STA);
  WiFi.disconnect(true);
  delay(1000);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  Serial.print("[WiFi] Connecting");

  unsigned long start = millis();

  while (WiFi.status() != WL_CONNECTED &&
         millis() - start < 30000) {

    delay(500);

    Serial.print(".");
    Serial.print(" status=");
    Serial.println(WiFi.status());
  }

  Serial.println();

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("[WiFi] Connected!");
    Serial.print("[WiFi] IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("[WiFi] RSSI: ");
    Serial.println(WiFi.RSSI());
  } else {
    Serial.println("[WiFi] Connection failed");
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println();
  Serial.println("=== TALKING BOT STEP 1 ===");

  Serial.print("Free heap: ");
  Serial.println(ESP.getFreeHeap());

  connectESP32();

  if (WiFi.status() == WL_CONNECTED) {

    Serial.println("[Test] Starting WebServer...");

    server.begin();

    Serial.println("[Test] WebServer started");

    Serial.println("[Test] Initializing Audio...");

    audio.setPinout(26, 25, 22);
    audio.setVolume(14);

    Serial.println("[Test] Audio initialized");

    Serial.print("[Test] Free heap: ");
    Serial.println(ESP.getFreeHeap());
  }
}

void loop() {
  server.handleClient();
  audio.loop();
}