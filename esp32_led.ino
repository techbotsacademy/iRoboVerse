#define LED_PIN 2

String inputString = "";
bool stringComplete = false;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);
  
  // Python ko signal dene ke liye ki ESP32 boot ho chuka hai
  Serial.println("ESP32_READY");
}

void loop() {
  // Laptop (Python) se serial data read karne ke liye loop
  while (Serial.available() > 0) {
    char inChar = (char)Serial.read();
    if (inChar == '\n') {
      stringComplete = true;
    } else {
      inputString += inChar;
    }
  }

  // Agar poora message ya command aa gaya hai
  if (stringComplete) {
    inputString.trim(); // Faltu spaces hatane ke liye

    if (inputString == "LISTENING") {
      // Laptop par recording chal rahi hai -> Fast Blink
      digitalWrite(LED_PIN, HIGH); delay(150);
      digitalWrite(LED_PIN, LOW);  delay(150);
      
      stringComplete = false;
      inputString = "";
    } 
    else if (inputString == "THINKING") {
      // AI answer process kar raha hai -> Slow Pulse
      digitalWrite(LED_PIN, HIGH); delay(600);
      digitalWrite(LED_PIN, LOW);  delay(600);
      
      stringComplete = false;
      inputString = "";
    } 
    else if (inputString.startsWith("ANSWER:")) {
      // ESP32 ko text answer mil gaya! 
      // 5 baar jaldi-jaldi blink karega dikhane ke liye ki "Processing" ho rahi hai
      for(int i = 0; i < 5; i++) {
        digitalWrite(LED_PIN, HIGH); delay(200);
        digitalWrite(LED_PIN, LOW);  delay(200);
      }
      
      // Speaker par bolte waqt LED solid ON rahegi
      digitalWrite(LED_PIN, HIGH);
      
      // Laptop ko signal bhejo ki ESP32 ne data verify kar liya hai, ab voice play karo
      Serial.println("ESP32_SPEAK_NOW");
      
      stringComplete = false;
      inputString = "";
    } 
    else if (inputString == "IDLE") {
      // Kuch nahi ho raha -> LED OFF
      digitalWrite(LED_PIN, LOW);
      
      stringComplete = false;
      inputString = "";
    }
  }
}