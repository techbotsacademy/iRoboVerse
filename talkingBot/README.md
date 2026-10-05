# ESP32 Talking Bot - Setup Guide (WiFi edition)

A browser button that records your voice, transcribes it, asks an AI for an
answer, speaks the answer out loud, and blinks an LED on an ESP32 to show
what the bot is doing.

**This version talks to the ESP32 over WiFi instead of a USB cable.** Flash
it once over USB, then power it from a battery pack / power bank - as long
as it's on the same WiFi network as your laptop, the LED keeps syncing.

## How it works

```
Browser (index.html) --HTTP--> server.py (your laptop) --WiFi/HTTP--> ESP32 (LED)
                                      |
                                      +--> Groq API (speech-to-text, AI answer)
                                      +--> gTTS + speakers (voice output)
```

The microphone and speakers are still your **laptop's** mic/speakers - only
the LED status indicator lives on the ESP32. The ESP32 runs its own tiny
WiFi web server; `server.py` sends it short HTTP requests ("LISTENING",
"THINKING", "SPEAKING", "IDLE") instead of USB serial commands.

## Files

| File                        | What it does                                          |
|------------------------------|--------------------------------------------------------|
| `server.py`                  | The main brain - run this on your laptop               |
| `index.html`                 | The browser UI - open this in Chrome/Edge/Firefox      |
| `esp32/esp32_wifi_led.ino`   | Upload this to the ESP32 (WiFi + LED control)           |
| `requirements.txt`           | Python libraries needed                                 |
| `.env.example`                | Template for your secret API key and settings          |

---

## STEP 1 - Install Python (3.10 or 3.11 recommended)

Download from https://www.python.org/downloads/ if you don't have it.
On Windows, tick **"Add Python to PATH"** during install.

## STEP 2 - Create a virtual environment (important!)

Installing libraries globally is the #1 reason a project "works on my
laptop but not on others" - different Python versions and other
projects' packages conflict. A virtual environment avoids this.

```bash
cd talking_bot
python -m venv venv

# Activate it:
venv\Scripts\activate        # Windows
source venv/bin/activate     # Mac / Linux
```

You should now see `(venv)` at the start of your terminal line.

## STEP 3 - Install the libraries

```bash
pip install -r requirements.txt
```

This project deliberately avoids `pyaudio` and local `openai-whisper` -
both are common install failures on Windows/Mac because they need
compilers or large downloads (ffmpeg, PyTorch). Instead it uses:
- `sounddevice` for recording (has ready-made wheels for every OS)
- Groq's hosted Whisper API for transcription (no local model, no ffmpeg)
- `requests` for talking to the ESP32 over WiFi (no serial driver needed)

If `sounddevice` still fails to install:
- **Windows**: usually just works with the command above.
- **Mac**: `brew install portaudio` first, then re-run pip install.
- **Linux**: `sudo apt install libportaudio2` first, then re-run pip install.

## STEP 4 - Get a free Groq API key

1. Go to https://console.groq.com and sign up (free)
2. Left sidebar -> API Keys -> Create API Key
3. Copy the key (starts with `gsk_...`)

## STEP 5 - Configure your secrets

```bash
cp .env.example .env        # Mac/Linux
copy .env.example .env      # Windows
```

Open `.env` in any text editor and paste your key:
```
GROQ_API_KEY=gsk_your_real_key_here
```

**Never share this `.env` file or commit it to GitHub** - anyone with the
key can use your free Groq quota. `.gitignore` already excludes it.

> If a Groq model name in `.env` ever stops working (Groq periodically
> retires older models), check https://console.groq.com/docs/models for
> the current list and update `GROQ_CHAT_MODEL` / `GROQ_WHISPER_MODEL`.

## STEP 6 - Set up the ESP32 for WiFi

Wiring (optional - most dev boards already have a built-in LED on GPIO 2):
```
LED long leg  (anode)   -> 220 ohm resistor -> GPIO 2
LED short leg (cathode) -> GND
```

1. Install Arduino IDE: https://www.arduino.cc/en/software
2. File -> Preferences -> "Additional boards manager URLs":
   `https://raw.githubusercontent.com/espressif/arduino-esp32/gh-pages/package_esp32_index.json`
3. Tools -> Board -> Boards Manager -> search "esp32" -> install
   (this also gives you the `WiFi.h`, `WebServer.h`, and `ESPmDNS.h`
   libraries used below - no separate library install needed)
4. Open `esp32/esp32_wifi_led.ino`
5. **Edit these two lines near the top of the file** to match your WiFi:
   ```cpp
   const char *WIFI_SSID     = "YOUR_WIFI_NAME";
   const char *WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
   ```
   Your ESP32 needs a **2.4GHz** WiFi network (it can't join 5GHz-only
   networks) - the same network your laptop is on.
6. Tools -> Board -> ESP32 Arduino -> ESP32 Dev Module
7. Tools -> Port -> select your ESP32's COM/USB port (still needed for
   this one-time upload)
8. Click Upload, wait for "Done uploading"
9. Open Tools -> Serial Monitor, set baud rate to **115200**. You should
   see something like:
   ```
   [WiFi] Connected!
   [WiFi] IP address: 192.168.1.42
   [WiFi] Put this IP into ESP32_IP in your .env file.
   ```
10. Copy that IP address into your `.env` file:
    ```
    ESP32_IP=192.168.1.42
    ```

**After this, you can unplug the USB cable.** Power the ESP32 from any
5V source - a USB battery pack / power bank plugged into its USB port
works great - and it will reconnect to WiFi on its own and keep
listening for commands from `server.py`.

> Tip: if your router lets you reserve a fixed/static IP for a device
> (sometimes called "DHCP reservation"), do that for the ESP32's MAC
> address so its IP never changes and you don't have to update `.env`
> again. Otherwise you may need to re-check the IP occasionally.

The ESP32 is **optional** - the bot still records, thinks, and speaks
without it; you'll just lose the LED status light.

## STEP 7 - Run it

```bash
python server.py
```

You should see something like:
```
[Startup] ESP32 reachable at http://192.168.1.42
[Startup] Starting web server on http://localhost:5000
```

Then open `index.html` by double-clicking it (or right-click -> Open with
-> your browser).

- Green dot = server is reachable
- "ESP32: connected" = LED sync is active over WiFi; otherwise it just runs voice-only
- Click the mic button, speak your question, wait for the answer

---

## Troubleshooting (why it breaks on a *different* laptop / network)

| Problem | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError` on startup | Libraries installed in the wrong environment | Make sure `(venv)` is active, then `pip install -r requirements.txt` again |
| `GROQ_API_KEY is missing` | `.env` wasn't created, or key not pasted | Copy `.env.example` to `.env` and paste a real key |
| "Server offline" in the browser | `server.py` isn't running, or a firewall is blocking port 5000 | Start `server.py` first; allow Python through the firewall when prompted |
| ESP32 not reachable / "voice-only mode" | Wrong IP in `.env`, ESP32 not on same WiFi, or its IP changed after a router restart | Reopen the Arduino Serial Monitor to see its current IP, update `ESP32_IP` in `.env`, and make sure ESP32 + laptop are on the **same** WiFi network |
| ESP32 LED never lights up at all | Wrong WiFi SSID/password in the sketch, or 5GHz-only network | Double check `WIFI_SSID`/`WIFI_PASSWORD` in the `.ino` file and re-upload; ESP32 needs 2.4GHz WiFi |
| Works on your laptop's WiFi but not a hotspot/guest network | Some guest/hotspot networks block "client isolation" (devices can't talk to each other) | Use a normal home WiFi network, or check your router's client-isolation setting |
| No sound / mic not recording | Wrong default microphone selected in OS sound settings | Check the OS sound settings and set the correct input/output device as default |
| Groq API error / model not found | Groq deprecated the model name | Check https://console.groq.com/docs/models and update `GROQ_CHAT_MODEL` in `.env` |
| Works for you but not a teammate | They're using your hardcoded API key/WiFi password, or missing `.env` | Everyone needs **their own** `.env`, and the `.ino` file's WiFi credentials must match whatever network their ESP32 is on |

---

## LED Status Guide

| LED pattern | Meaning            | Browser emoji |
|-------------|---------------------|----------------|
| OFF         | Idle                 | 😴             |
| Fast blink  | Recording your voice | 🎤             |
| Slow pulse  | AI is thinking       | 🤔             |
| Solid ON    | Bot is speaking      | 🔊             |
