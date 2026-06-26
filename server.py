"""
ESP32 Talking Bot - Python Backend Server
=========================================
This script runs on your laptop and:
  1. Receives trigger from browser (via Flask)
  2. Records audio from laptop microphone
  3. Transcribes speech using OpenAI Whisper (free, runs locally)
  4. Sends question to Groq API (free tier) for AI answer
  5. Converts answer to speech using gTTS
  6. Plays audio back through laptop speakers
  7. Sends LED status commands to ESP32 via USB Serial

Requirements - install these first:
  pip install flask flask-cors openai-whisper groq gtts pygame pyaudio pyserial

Groq API Key (FREE):
  Go to https://console.groq.com
  Sign up -> API Keys -> Create Key -> Copy it
  Paste it below where it says YOUR_GROQ_API_KEY_HERE
"""

import os
import time
import threading
import tempfile
import serial
import serial.tools.list_ports
import pyaudio
import wave
import whisper
import pygame
from gtts import gTTS
from groq import Groq
from flask import Flask, jsonify, request
from flask_cors import CORS

# ============================================================
#  CONFIGURATION - Edit these values
# ============================================================

# ============================================================
#  CONFIGURATION - Edit these values
# ============================================================

# Get free key from https://console.groq.com
GROQ_API_KEY = "API_KEY"   

# UPDATED: Changed from 'llama3-8b-8192' to the currently active model
GROQ_MODEL = "llama-3.1-8b-instant"            

# Max seconds to record voice (5 seconds)
RECORDING_SECONDS = 5                      

# Whisper model: "tiny"=fastest, "base"=balanced, "small"=accurate
WHISPER_MODEL = "base"                     

# Must match ESP32 code
SERIAL_BAUDRATE = 115200                  # Must match ESP32 code

# ============================================================
#  AUTO-DETECT ESP32 PORT
# ============================================================

def find_esp32_port():
    """Automatically find the ESP32 USB port."""
    ports = serial.tools.list_ports.comports()
    for port in ports:
        desc = (port.description or "").lower()
        if any(keyword in desc for keyword in ["cp210", "ch340", "ftdi", "usb serial", "uart"]):
            return port.device
    # If not found automatically, return None
    return None

# ============================================================
#  GLOBAL STATE
# ============================================================

app = Flask(__name__)
CORS(app)  # Allow browser to talk to this server

groq_client = Groq(api_key=GROQ_API_KEY)
whisper_model = None          # Loaded once on startup
esp32 = None                  # Serial connection to ESP32
bot_status = "IDLE"           # Current bot state
bot_response_text = ""        # Last answer from AI
bot_emoji = "😴"              # Emoji shown in browser
is_busy = False               # Prevent multiple requests at once

# ============================================================
#  ESP32 LED CONTROL
# ============================================================

def send_led_command(command):
    """Send status command to ESP32 LED over USB Serial."""
    global bot_status, bot_emoji
    bot_status = command

    # Map status to emoji for browser display
    emoji_map = {
        "LISTENING": "🎤",
        "THINKING":  "🤔",
        "SPEAKING":  "🔊",
        "IDLE":      "😴"
    }
    bot_emoji = emoji_map.get(command, "😴")

    # Send to ESP32 if connected
    if esp32 and esp32.is_open:
        try:
            esp32.write((command + "\n").encode())
        except Exception as e:
            print(f"[Serial Error] Could not send to ESP32: {e}")

# ============================================================
#  AUDIO RECORDING
# ============================================================

def record_audio(duration_seconds=5):
    """Record audio from laptop microphone and save to temp WAV file."""
    sample_rate = 16000   # 16kHz is what Whisper expects
    chunk_size = 1024
    channels = 1          # Mono

    audio = pyaudio.PyAudio()

    print(f"[Recording] Listening for {duration_seconds} seconds...")

    stream = audio.open(
        format=pyaudio.paInt16,
        channels=channels,
        rate=sample_rate,
        input=True,
        frames_per_buffer=chunk_size
    )

    frames = []
    for _ in range(0, int(sample_rate / chunk_size * duration_seconds)):
        data = stream.read(chunk_size, exception_on_overflow=False)
        frames.append(data)

    stream.stop_stream()
    stream.close()
    audio.terminate()

    # Save to temporary WAV file
    temp_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    with wave.open(temp_file.name, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(audio.get_sample_size(pyaudio.paInt16))
        wf.setframerate(sample_rate)
        wf.writeframes(b''.join(frames))

    print(f"[Recording] Saved to {temp_file.name}")
    return temp_file.name

# ============================================================
#  SPEECH TO TEXT (Whisper - runs locally, 100% free)
# ============================================================

def transcribe_audio(audio_file_path):
    """Convert recorded audio to text using local Whisper model."""
    global whisper_model

    print("[Whisper] Transcribing audio...")
    result = whisper_model.transcribe(audio_file_path, language="en")
    text = result["text"].strip()
    print(f"[Whisper] You said: '{text}'")

    # Clean up temp file
    os.unlink(audio_file_path)

    return text

# ============================================================
#  AI RESPONSE (Groq API - free tier)
# ============================================================

def get_ai_response(user_question):
    """Send question to Groq AI and get English answer."""
    print(f"[Groq] Sending question: '{user_question}'")

    response = groq_client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful voice assistant. "
                    "Always respond in clear, simple English. "
                    "Keep answers concise - 2 to 4 sentences maximum. "
                    "Do not use bullet points or special formatting. "
                    "Speak naturally as if talking to a person."
                )
            },
            {
                "role": "user",
                "content": user_question
            }
        ],
        max_tokens=200,
        temperature=0.7
    )

    answer = response.choices[0].message.content.strip()
    print(f"[Groq] Answer: '{answer}'")
    return answer

# ============================================================
#  TEXT TO SPEECH (gTTS - free, uses Google TTS)
# ============================================================

def speak_text(text):
    """Convert text to speech and play it through laptop speakers."""
    print(f"[TTS] Speaking: '{text}'")

    # Use a regular string path instead of NamedTemporaryFile to fix Windows locking bugs
    temp_filename = "voice_output.mp3"
    
    try:
        # Generate speech audio
        tts = gTTS(text=text, lang='en', slow=False)
        tts.save(temp_filename)

        # Play the audio
        pygame.mixer.init()
        pygame.mixer.music.load(temp_filename)
        pygame.mixer.music.play()

        # Wait until audio finishes playing
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)

        pygame.mixer.music.unload()
        pygame.mixer.quit()

    except Exception as e:
        print(f"[TTS Error] Could not play audio: {e}")
        
    finally:
        # Clean up the audio file safely if it exists
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
    """Full pipeline: Laptop Buttons -> AI -> ESP32 Hardware -> Laptop Speakers."""
    global bot_response_text, is_busy, esp32

    is_busy = True

    try:
        # Step 1: Record voice
        send_led_command("LISTENING")
        audio_path = record_audio(duration_seconds=RECORDING_SECONDS)

        # Step 2: Speech to text
        send_led_command("THINKING")
        question = transcribe_audio(audio_path)

        if not question or len(question.strip()) < 2:
            bot_response_text = "I didn't catch that."
            send_led_command("ANSWER:Error")
            speak_text(bot_response_text)
        else:
            # Step 3: Get AI answer from Groq
            answer = get_ai_response(question)
            bot_response_text = answer

            # CRITICAL STEP: Verify ESP32 is actually connected
            if esp32 and esp32.is_open:
                print(f"[Hardware] Sending answer text to ESP32 board...")
                # Clear any leftover serial data
                esp32.reset_input_buffer()
                
                # Send the answer text directly to the micro-controller
                esp32.write(f"ANSWER:{answer}\n".encode())
                
                print("[Hardware] Waiting for ESP32 authorization to speak...")
                # Wait for the ESP32 to flash its LEDs and reply back "ESP32_SPEAK_NOW"
                start_time = time.time()
                authorized = False
                while time.time() - start_time < 5:  # 5-second timeout
                    if esp32.in_waiting > 0:
                        response = esp32.readline().decode().strip()
                        if response == "ESP32_SPEAK_NOW":
                            authorized = True
                            break
                    time.sleep(0.1)
                
                if authorized:
                    print("[Hardware] ESP32 authorized speech! Playing audio output...")
                    speak_text(answer)
                else:
                    print("[Hardware Error] ESP32 did not respond in time.")
            else:
                print("[Hardware Error] ESP32 is not connected! Core pipeline blocked.")
                bot_response_text = "Error: ESP32 hardware disconnected."

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
    """Browser polls this to get current bot state."""
    return jsonify({
        "status": bot_status,
        "emoji": bot_emoji,
        "response": bot_response_text,
        "busy": is_busy
    })

@app.route("/listen", methods=["POST"])
def start_listening():
    """Browser calls this when user clicks the microphone button."""
    if is_busy:
        return jsonify({"error": "Bot is busy, please wait."}), 429

    # Run the full pipeline in a background thread
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
    print(" ESP32 Talking Bot - Python Server")
    print("=" * 50)

    # Load Whisper model (downloads once on first run ~140MB for 'base')
    print(f"[Startup] Loading Whisper '{WHISPER_MODEL}' model... (first run may take a minute)")
    whisper_model = whisper.load_model(WHISPER_MODEL)
    print("[Startup] Whisper loaded!")

    # Connect to ESP32 via USB Serial
    esp32_port = find_esp32_port()
    if esp32_port:
        try:
            esp32 = serial.Serial(esp32_port, SERIAL_BAUDRATE, timeout=1)
            print(f"[Startup] ESP32 connected on {esp32_port}")
            time.sleep(2)  # Wait for ESP32 to reset
        except Exception as e:
            print(f"[Startup] Could not connect to ESP32: {e}")
            print("[Startup] Continuing without ESP32 (LED won't work)")
    else:
        print("[Startup] ESP32 not found. Connect it via USB and restart.")
        print("[Startup] Continuing without ESP32 (LED won't work)")

    # Start Flask server
    print("[Startup] Starting web server on http://localhost:5000")
    print("[Startup] Open index.html in your browser to use the bot!")
    print("=" * 50)

    app.run(host="0.0.0.0", port=5000, debug=False)
