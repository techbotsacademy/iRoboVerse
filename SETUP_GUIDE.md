# ESP32 Talking Bot - Complete Setup Guide

## What This Project Does
- You click a button in the browser
- Bot records your voice for 5 seconds via laptop mic
- Whisper converts your speech to text (free, runs locally)
- Groq AI generates a smart English answer (free API)
- gTTS speaks the answer through your laptop speakers
- ESP32 LED blinks to show the bot's current state

---

## Files in This Project

| File             | What it does                                      |
|------------------|---------------------------------------------------|
| esp32_led.ino    | Upload this to ESP32 (LED control via USB Serial) |
| server.py        | Run this on your laptop (the main brain)          |
| index.html       | Open this in your browser (the UI)                |

---

## STEP 1 - Install Python Libraries

Open Command Prompt / Terminal and run these commands:

```
pip install flask flask-cors groq gtts pygame pyaudio pyserial
```

Install Whisper (speech-to-text, runs 100% locally):
```
pip install openai-whisper
```

If pyaudio fails on Windows, try:
```
pip install pipwin
pipwin install pyaudio
```

---

## STEP 2 - Get FREE Groq API Key

1. Go to: https://console.groq.com
2. Click "Sign Up" (completely free)
3. After login, go to "API Keys" in left sidebar
4. Click "Create API Key"
5. Give it any name like "TalkingBot"
6. Copy the key (starts with gsk_...)
7. Open server.py in any text editor (Notepad is fine)
8. Find this line:
      GROQ_API_KEY = "YOUR_GROQ_API_KEY_HERE"
9. Replace YOUR_GROQ_API_KEY_HERE with your actual key
   Example: GROQ_API_KEY = "gsk_abc123xyz..."

---

## STEP 3 - ESP32 Wiring

Connect LED to ESP32:
  LED long leg (positive/anode)  --> 220 ohm resistor --> GPIO Pin 2
  LED short leg (negative/cathode) --> GND pin

That's it! No other hardware needed.

---

## STEP 4 - Upload Code to ESP32

1. Download and install Arduino IDE from https://www.arduino.cc/en/software
2. Open Arduino IDE
3. Go to: File --> Preferences
4. In "Additional boards manager URLs" paste:
   https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json
5. Click OK
6. Go to: Tools --> Board --> Boards Manager
7. Search "esp32" and install "esp32 by Espressif Systems"
8. Open the file: esp32_led.ino
9. Go to: Tools --> Board --> ESP32 Arduino --> ESP32 Dev Module
10. Go to: Tools --> Port --> Select your COM port (the one that appears when ESP32 is plugged in)
11. Click the Upload button (right arrow icon)
12. Wait for "Done uploading" message

---

## STEP 5 - Run the Python Server

1. Open Command Prompt / Terminal
2. Navigate to this project folder:
   cd path/to/talking_bot
3. Run the server:
   python server.py
4. First run will download Whisper model (~140MB) - wait for it
5. You should see:
   "ESP32 connected on COM3" (or similar port)
   "Starting web server on http://localhost:5000"

---

## STEP 6 - Open the Browser UI

1. Double-click index.html to open it in your browser
2. You should see a green dot "Server connected" in top right
3. Press the big microphone button
4. Speak your question clearly in English (you have 5 seconds)
5. Watch the emoji change:
   😴 = Waiting (IDLE)
   🎤 = Recording your voice (LED blinks fast)
   🤔 = AI is thinking (LED pulses slow)
   🔊 = Bot is speaking answer (LED solid ON)

---

## Troubleshooting

Problem: "Server offline" shown in browser
Solution: Make sure server.py is running in terminal first

Problem: ESP32 not found
Solution: Check Device Manager for COM port, or try different USB cable

Problem: No audio recorded / microphone not working
Solution: Check Windows sound settings, make sure laptop mic is set as default

Problem: pyaudio installation fails
Solution: pip install pipwin then pipwin install pyaudio

Problem: Whisper takes very long to load
Solution: Change WHISPER_MODEL = "tiny" in server.py for faster loading

Problem: Groq API error
Solution: Double-check your API key is pasted correctly in server.py

---

## LED Status Guide

| LED Pattern      | Meaning                    | Browser Emoji |
|------------------|----------------------------|---------------|
| OFF              | Idle, waiting for you      | 😴            |
| Fast blink       | Recording your voice       | 🎤            |
| Slow pulse       | AI thinking                | 🤔            |
| Solid ON         | Bot speaking answer        | 🔊            |
