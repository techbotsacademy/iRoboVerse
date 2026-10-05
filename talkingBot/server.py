"""
ESP32 Talking Bot - Python Backend Server (WiFi edition)
=========================================================
Runs on your laptop and:
  1. Receives a trigger from the browser (via Flask)
  2. Records audio from the laptop microphone
  3. Transcribes speech using Groq's hosted Whisper API (no local install needed)
  4. Sends the question to Groq's chat API for an AI answer
  5. Converts the answer to speech using gTTS
  6. Plays the audio back through the laptop speakers
  7. Sends LED status commands to the ESP32 over WiFi/HTTP (optional)

The ESP32 no longer needs a USB cable to your laptop while it's running -
it just needs to be on the same WiFi network. Power it from a battery
pack and it will keep blinking its status LED as long as it can reach
this server's WiFi network and IP.

SETUP:
  1. python -m venv venv                 (create a virtual environment)
  2. venv\\Scripts\\activate               (Windows)  OR  source venv/bin/activate  (Mac/Linux)
  3. pip install -r requirements.txt
  4. Copy .env.example to .env, paste your free Groq API key, and set ESP32_IP
  5. python server.py

See README.md for full, per-OS instructions.
"""

import os
import sys
import time
import threading
import tempfile

from dotenv import load_dotenv

load_dotenv()  # reads variables from .env

# ------------------------------------------------------------------
# Friendly import check - tells the user exactly what to install
# instead of crashing with a cryptic traceback.
# ------------------------------------------------------------------
try:
    import requests
    import sounddevice as sd
    import soundfile as sf
    import numpy as np
    import pygame
    from gtts import gTTS
    from groq import Groq
    from flask import Flask, jsonify
    from flask_cors import CORS
except ImportError as e:
    print("\n[Missing library] " + str(e))
    print("Run this first:  pip install -r requirements.txt\n")
    sys.exit(1)

# ============================================================
#  CONFIGURATION (loaded from .env - see .env.example)
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_CHAT_MODEL = os.getenv("GROQ_CHAT_MODEL", "openai/gpt-oss-20b")
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
RECORDING_SECONDS = int(os.getenv("RECORDING_SECONDS", "5"))

# The ESP32's WiFi IP address (printed in the Arduino Serial Monitor
# the first time it connects - see esp32/esp32_wifi_led.ino).
# You can also try the mDNS name "talkingbot.local" here, but a raw
# IP like 192.168.1.42 is more reliable, especially on Windows.
ESP32_IP = os.getenv("ESP32_IP", "").strip()
ESP32_HTTP_TIMEOUT = float(os.getenv("ESP32_HTTP_TIMEOUT", "2"))

REQUIRE_ESP32 = os.getenv("REQUIRE_ESP32", "false").strip().lower() == "true"

if not GROQ_API_KEY or GROQ_API_KEY == "paste_your_groq_key_here":
    print("\n[Config Error] GROQ_API_KEY is missing.")
    print("1. Copy .env.example to a new file named .env")
    print("2. Get a free key from https://console.groq.com")
    print("3. Paste it into .env as GROQ_API_KEY=...\n")
    sys.exit(1)

groq_client = Groq(api_key=GROQ_API_KEY)

# ============================================================
#  ESP32 WIFI CONNECTION
# ============================================================


def esp32_base_url():
    if not ESP32_IP:
        return None
    if ESP32_IP.startswith("http://") or ESP32_IP.startswith("https://"):
        return ESP32_IP.rstrip("/")
    return f"http://{ESP32_IP}"


def check_esp32_connection():
    """Ping the ESP32's /ping endpoint to see if it's reachable on WiFi."""
    base = esp32_base_url()
    if not base:
        return False
    try:
        resp = requests.get(f"{base}/ping", timeout=ESP32_HTTP_TIMEOUT)
        return resp.ok and "ESP32_READY" in resp.text
    except requests.exceptions.RequestException:
        return False


# ============================================================
#  GLOBAL STATE
# ============================================================

app = Flask(__name__)
CORS(app)  # allow the browser page to call this local server

esp32_connected = False       # updated by the background ping thread
bot_status = "IDLE"
bot_response_text = ""
bot_emoji = "\U0001F634"       # 😴
is_busy = False

# ============================================================
#  ESP32 LED CONTROL (over WiFi/HTTP instead of USB serial)
# ============================================================


def send_led_command(command, wait_for_speak_ack=False):
    """
    Send a status command to the ESP32 over WiFi (no-op if not connected).
    If wait_for_speak_ack is True (used for "ANSWER:..."), returns True only
    if the ESP32 replied with ESP32_SPEAK_NOW, confirming it's ready.
    """
    global bot_status, bot_emoji, esp32_connected

    # Track status/emoji for the browser UI regardless of ESP32 state
    display_command = "SPEAKING" if command.startswith("ANSWER:") else command
    bot_status = display_command

    emoji_map = {
        "LISTENING": "\U0001F3A4",  # 🎤
        "THINKING": "\U0001F914",   # 🤔
        "SPEAKING": "\U0001F50A",   # 🔊
        "IDLE": "\U0001F634",       # 😴
    }
    bot_emoji = emoji_map.get(display_command, "\U0001F634")

    base = esp32_base_url()
    if not base:
        return False

    try:
        # ANSWER: needs a longer timeout since the ESP32 runs a short
        # blocking blink sequence before it replies.
        timeout = 6 if command.startswith("ANSWER:") else ESP32_HTTP_TIMEOUT
        resp = requests.post(f"{base}/command", data=command, timeout=timeout)
        esp32_connected = True

        if wait_for_speak_ack:
            return resp.ok and resp.text.strip() == "ESP32_SPEAK_NOW"
        return resp.ok

    except requests.exceptions.RequestException as e:
        esp32_connected = False
        print(f"[WiFi Error] Could not reach ESP32 at {base}: {e}")
        return False


def esp32_watchdog():
    """Background thread: periodically checks if the ESP32 is still reachable,
    so the browser's connection indicator stays accurate even when the bot
    is idle and not otherwise talking to the ESP32."""
    global esp32_connected
    while True:
        esp32_connected = check_esp32_connection()
        time.sleep(5)


# ============================================================
#  AUDIO RECORDING (sounddevice - reliable prebuilt wheels
#  on Windows/Mac/Linux, unlike pyaudio which often fails to build)
# ============================================================


def record_audio(duration_seconds=5):
    """Record audio from the default microphone and save it to a temp WAV file."""
    sample_rate = 16000  # good sample rate for speech recognition
    channels = 1

    print(f"[Recording] Listening for {duration_seconds} seconds...")
    audio_data = sd.rec(
        int(duration_seconds * sample_rate),
        samplerate=sample_rate,
        channels=channels,
        dtype="int16",
    )
    sd.wait()

    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    sf.write(temp_file.name, audio_data, sample_rate)
    print(f"[Recording] Saved to {temp_file.name}")
    return temp_file.name


# ============================================================
#  SPEECH TO TEXT (Groq-hosted Whisper - no local model download,
#  no ffmpeg dependency, works identically on every laptop)
# ============================================================


def transcribe_audio(audio_file_path):
    """Send the recorded audio to Groq's Whisper API and get back text."""
    print("[Whisper] Transcribing audio...")
    with open(audio_file_path, "rb") as f:
        result = groq_client.audio.transcriptions.create(
            file=(os.path.basename(audio_file_path), f.read()),
            model=GROQ_WHISPER_MODEL,
            language="en",
        )
    text = (result.text or "").strip()
    print(f"[Whisper] You said: '{text}'")

    os.unlink(audio_file_path)
    return text


# ============================================================
#  AI RESPONSE (Groq chat API - free tier)
# ============================================================


def get_ai_response(user_question):
    """Send the question to Groq's chat API and get a short English answer."""
    print(f"[Groq] Sending question: '{user_question}'")

    response = groq_client.chat.completions.create(
        model=GROQ_CHAT_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful voice assistant. "
                    "Always respond in clear, simple English. "
                    "Keep answers concise - 2 to 4 sentences maximum. "
                    "Do not use bullet points or special formatting. "
                    "Speak naturally as if talking to a person."
                ),
            },
            {"role": "user", "content": user_question},
        ],
        max_tokens=200,
        temperature=0.7,
    )

    answer = response.choices[0].message.content.strip()
    print(f"[Groq] Answer: '{answer}'")
    return answer


# ============================================================
#  TEXT TO SPEECH (gTTS - free, needs internet)
# ============================================================


def speak_text(text):
    """Convert text to speech and play it through the laptop speakers."""
    print(f"[TTS] Speaking: '{text}'")

    temp_filename = os.path.join(tempfile.gettempdir(), "voice_output.mp3")

    try:
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(temp_filename)

        pygame.mixer.init()
        pygame.mixer.music.load(temp_filename)
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.music.unload()
        pygame.mixer.quit()

    except Exception as e:
        print(f"[TTS Error] Could not play audio: {e}")

    finally:
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except Exception:
                pass

    print("[TTS] Done speaking.")


# ============================================================
#  MAIN BOT PIPELINE
# ============================================================


def run_bot_pipeline():
    """Full pipeline: Mic -> Whisper -> Groq AI -> ESP32 LED (WiFi) -> Speakers."""
    global bot_response_text, is_busy

    is_busy = True

    try:
        send_led_command("LISTENING")
        audio_path = record_audio(duration_seconds=RECORDING_SECONDS)

        send_led_command("THINKING")
        question = transcribe_audio(audio_path)

        if not question or len(question.strip()) < 2:
            bot_response_text = "I didn't catch that."
            send_led_command("IDLE")
            speak_text(bot_response_text)
            return

        answer = get_ai_response(question)
        bot_response_text = answer

        if REQUIRE_ESP32 and not esp32_connected:
            bot_response_text = "Error: ESP32 hardware is not connected."
            print("[Hardware Error] REQUIRE_ESP32 is true but ESP32 is not reachable on WiFi.")
            return

        if esp32_connected:
            print("[Hardware] Sending answer text to ESP32 over WiFi...")
            acknowledged = send_led_command(f"ANSWER:{answer}", wait_for_speak_ack=True)
            if not acknowledged:
                print("[Hardware] ESP32 didn't acknowledge in time - speaking anyway.")
        else:
            print("[Hardware] ESP32 not reachable on WiFi - speaking without LED sync.")

        send_led_command("SPEAKING")
        speak_text(answer)

    except Exception as e:
        print(f"[Error] Pipeline failed: {e}")
        bot_response_text = "Sorry, something went wrong."

    finally:
        send_led_command("IDLE")
        is_busy = False


# ============================================================
#  FLASK API ROUTES (Browser talks to these)
# ============================================================


@app.route("/status", methods=["GET"])
def get_status():
    return jsonify(
        {
            "status": bot_status,
            "emoji": bot_emoji,
            "response": bot_response_text,
            "busy": is_busy,
            "esp32_connected": esp32_connected,
        }
    )


@app.route("/listen", methods=["POST"])
def start_listening():
    if is_busy:
        return jsonify({"error": "Bot is busy, please wait."}), 429

    thread = threading.Thread(target=run_bot_pipeline, daemon=True)
    thread.start()
    return jsonify({"message": "Listening started"})


@app.route("/", methods=["GET"])
def index():
    return "Talking Bot server is running! Open index.html in your browser."


# ============================================================
#  STARTUP
# ============================================================

if __name__ == "__main__":
    print("=" * 50)
    print(" ESP32 Talking Bot - Python Server (WiFi edition)")
    print("=" * 50)

    if not ESP32_IP:
        print("[Startup] ESP32_IP is not set in .env - continuing without ESP32.")
        print("[Startup] Flash esp32/esp32_wifi_led.ino, read its IP from the")
        print("[Startup] Serial Monitor, and put it in .env as ESP32_IP=...")
    else:
        esp32_connected = check_esp32_connection()
        if esp32_connected:
            print(f"[Startup] ESP32 reachable at {esp32_base_url()}")
        else:
            print(f"[Startup] Could not reach ESP32 at {esp32_base_url()}")
            print("[Startup] Check that the ESP32 is powered on and on the same WiFi")
            print("[Startup] network as this computer. Continuing without it for now -")
            print("[Startup] the background watchdog will keep retrying.")

    watchdog = threading.Thread(target=esp32_watchdog, daemon=True)
    watchdog.start()

    print("[Startup] Starting web server on http://localhost:5000")
    print("[Startup] Open index.html in your browser to use the bot!")
    print("=" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False)
