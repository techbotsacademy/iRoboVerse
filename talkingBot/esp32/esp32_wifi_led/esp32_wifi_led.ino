/*
  ESP32 Talking Bot - WiFi LED Status Indicator
  ==============================================
  Runs its own tiny WiFi web server. server.py (on your laptop, same
  WiFi network) sends it simple HTTP commands to blink/light an LED
  showing what the bot is doing. No USB cable needed once flashed -
  power the board from a battery/power bank and it still works, as
  long as it's on the same WiFi network as your laptop.

  Wiring (optional - most dev boards already have a built-in LED on GPIO 2):
    LED long leg  (anode)   -> 220 ohm resistor -> GPIO 2
    LED short leg (cathode) -> GND

  Library needed: none extra - WiFi.h and WebServer.h ship with the
  "esp32" board package you already installed for the USB version.

  SETUP:
    1. Edit WIFI_SSID / WIFI_PASSWORD below to match your WiFi network.
       (Must be 2.4GHz - ESP32 does not support 5GHz WiFi.)
    2. Upload this sketch over USB like normal (Tools -> Upload).
    3. Open Tools -> Serial Monitor (115200 baud) once, after upload,
       to see the IP address it was given, e.g. 192.168.1.42
    4. Put that IP into ESP32_IP in your .env file (see README).
    5. After that, you can unplug USB and power the board from a
       battery pack / phone charger / power bank via its 5V or USB pin -
       it will reconnect to WiFi automatically and keep working.
*/

#include <WiFi.h>
#include <WebServer.h>
#include <ESPmDNS.h>

// ---------------------------------------------------------------
// EDIT THESE TWO LINES for your own WiFi network
// ---------------------------------------------------------------
const char *WIFI_SSID     = "YOUR_WIFI_NAME";
const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// Optional: also reachable at http://talkingbot.local/ on Mac/Linux
// and on Windows if you have Bonjour/iTunes installed. If mDNS
// doesn't work on your network, just use the IP address instead.
const char *MDNS_NAME = "talkingbot";

#define LED_PIN 2

WebServer server(80);

// ---------------------------------------------------------------
// Bot state - loop() keeps blinking according to whichever state
// was last set by the laptop, so a single HTTP request is enough
// to start a blink pattern that keeps going until the next request.
// ---------------------------------------------------------------
enum BotState { ST_IDLE, ST_LISTENING, ST_THINKING, ST_SPEAKING };
volatile BotState currentState = ST_IDLE;

unsigned long lastToggle = 0;
bool ledOn = false;

void applyLedPattern() {
  unsigned long now = millis();

  switch (currentState) {
    case ST_LISTENING:  // fast blink - recording your voice
      if (now - lastToggle >= 150) {
        ledOn = !ledOn;
        digitalWrite(LED_PIN, ledOn);
        lastToggle = now;
      }
      break;

    case ST_THINKING:   // slow pulse - AI is thinking
      if (now - lastToggle >= 600) {
        ledOn = !ledOn;
        digitalWrite(LED_PIN, ledOn);
        lastToggle = now;
      }
      break;

    case ST_SPEAKING:   // solid ON - bot is talking
      if (!ledOn) {
        digitalWrite(LED_PIN, HIGH);
        ledOn = true;
      }
      break;

    case ST_IDLE:        // OFF - nothing happening
    default:
      if (ledOn) {
        digitalWrite(LED_PIN, LOW);
        ledOn = false;
      }
      break;
  }
}

// ---------------------------------------------------------------
// HTTP handlers
// ---------------------------------------------------------------

void handlePing() {
  server.send(200, "text/plain", "ESP32_READY");
}

void handleCommand() {
  String body = server.arg("plain");
  body.trim();

  if (body == "LISTENING") {
    currentState = ST_LISTENING;
    server.send(200, "text/plain", "OK");
  }
  else if (body == "THINKING") {
    currentState = ST_THINKING;
    server.send(200, "text/plain", "OK");
  }
  else if (body == "SPEAKING") {
    currentState = ST_SPEAKING;
    server.send(200, "text/plain", "OK");
  }
  else if (body == "IDLE") {
    currentState = ST_IDLE;
    digitalWrite(LED_PIN, LOW);
    ledOn = false;
    server.send(200, "text/plain", "OK");
  }
  else if (body.startsWith("ANSWER:")) {
    // Answer text arrived - quick confirm blink, then solid ON,
    // then tell the laptop it's safe to start playing the voice answer.
    for (int i = 0; i < 5; i++) {
      digitalWrite(LED_PIN, HIGH); delay(200);
      digitalWrite(LED_PIN, LOW);  delay(200);
    }
    digitalWrite(LED_PIN, HIGH);
    ledOn = true;
    currentState = ST_SPEAKING;
    server.send(200, "text/plain", "ESP32_SPEAK_NOW");
  }
  else {
    server.send(400, "text/plain", "UNKNOWN_COMMAND");
  }
}

void handleNotFound() {
  server.send(404, "text/plain", "Not found");
}

// ---------------------------------------------------------------
// Setup / loop
// ---------------------------------------------------------------

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Serial.println();
  Serial.print("[WiFi] Connecting to ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  unsigned long startAttempt = millis();
  while (WiFi.status() != WL_CONNECTED) {
    delay(300);
    Serial.print(".");
    // After 20 seconds, blink fast forever so you know it failed
    // to connect (wrong SSID/password, or out of range).
    if (millis() - startAttempt > 20000) {
      Serial.println("\n[WiFi] Failed to connect. Check WIFI_SSID / WIFI_PASSWORD.");
      while (true) {
        digitalWrite(LED_PIN, HIGH); delay(100);
        digitalWrite(LED_PIN, LOW);  delay(100);
      }
    }
  }

  Serial.println();
  Serial.println("[WiFi] Connected!");
  Serial.print("[WiFi] IP address: ");
  Serial.println(WiFi.localIP());
  Serial.println("[WiFi] Put this IP into ESP32_IP in your .env file.");

  if (MDNS.begin(MDNS_NAME)) {
    Serial.print("[mDNS] Also reachable at http://");
    Serial.print(MDNS_NAME);
    Serial.println(".local  (if your OS supports mDNS)");
  }

  server.on("/ping", HTTP_GET, handlePing);
  server.on("/command", HTTP_POST, handleCommand);
  server.onNotFound(handleNotFound);
  server.begin();
  Serial.println("[HTTP] Server started on port 80");

  // Two quick blinks = booted and ready
  for (int i = 0; i < 2; i++) {
    digitalWrite(LED_PIN, HIGH); delay(150);
    digitalWrite(LED_PIN, LOW);  delay(150);
  }
}

void loop() {
  server.handleClient();
  applyLedPattern();

  // If WiFi drops (e.g. router restarts), try to reconnect quietly
  // in the background without blocking the LED pattern for too long.
  static unsigned long lastReconnectCheck = 0;
  if (WiFi.status() != WL_CONNECTED && millis() - lastReconnectCheck > 5000) {
    lastReconnectCheck = millis();
    Serial.println("[WiFi] Connection lost, retrying...");
    WiFi.reconnect();
  }
}
