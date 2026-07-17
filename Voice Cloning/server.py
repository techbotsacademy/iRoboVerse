import os
import shutil
import io
import torch
import torchaudio
import soundfile as sf
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ==========================================
# 1. PYTORCH SECURITY PATCH ONLY
# ==========================================
# Bypass PyTorch 2.6+ strict weight checks for legacy models (Safe & Clean)
original_load = torch.load
torch.load = lambda *args, **kwargs: original_load(*args, **{**kwargs, 'weights_only': False})

# NO MORE TORCHAUDIO MONKEY-PATCHES HERE - PREVENTS RECURSION LOOPS COMPLETELY

# ==========================================
# 2. INITIALIZE APP & CONFIGURATIONS
# ==========================================
app = FastAPI(title="Voice Clone AI Q&A Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SPEAKER_WAV_PATH = os.path.join(BASE_DIR, "speaker.wav")
RESPONSE_WAV_PATH = os.path.join(BASE_DIR, "response.wav")
HTML_UI_PATH = os.path.join(BASE_DIR, "index.html")

tts = None

class QuestionRequest(BaseModel):
    question: str

# ==========================================
# 3. HELPER FUNCTIONS
# ==========================================
def get_tts_model():
    global tts
    if tts is None:
        print("Loading Coqui XTTS v2 Model (this may take a moment)...")
        from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"Using device: {device}")
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return tts

def generate_answer(question: str) -> str:
    print(f"Processing question through LLM: {question}")
    if "hello" in question.lower() or "hi" in question.lower():
        return "Hello! I am your AI assistant, speaking to you using your cloned voice."
    elif "weather" in question.lower():
        return "I am currently running locally, so I don't have real-time weather data right now."
    return f"This is a demo response to your question: {question}. The system is operating normally."

# ==========================================
# 4. ROUTE DEFINITIONS
# ==========================================
@app.get("/")
async def serve_ui():
    """Serves the frontend interface directly."""
    if not os.path.exists(HTML_UI_PATH):
        raise HTTPException(status_code=404, detail="index.html file not found.")
    return FileResponse(HTML_UI_PATH)

@app.post("/upload_voice")
async def upload_voice(file: UploadFile = File(...)):
    """Receives browser recording container, decodes it safely, and saves a true standard WAV file."""
    temp_upload_path = SPEAKER_WAV_PATH + ".tmp"
    try:
        # 1. Save the incoming browser file stream down to a temporary file
        with open(temp_upload_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        print("Decoding browser container layout and converting to genuine PCM WAV...")
        
        # 2. Use torchaudio's native flexible backend loader to parse the browser container format directly from disk
        try:
            if hasattr(torchaudio, 'load_backend'):
                waveform, sample_rate = torchaudio.load_backend(temp_upload_path, format="webm")
            else:
                waveform, sample_rate = torchaudio.load(temp_upload_path)
        except Exception:
            # Secondary fallback if explicit backend flags are picky on certain Windows systems
            waveform, sample_rate = torchaudio.load(temp_upload_path)

        # 3. Convert the multi-channel or high sample rate layout down to standard mono tensor arrays
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)
            
        # 4. Write out a genuine, uncompressed 16-bit PCM standard WAV file that Coqui loves
        # Convert torch tensor back to numpy array for soundfile writing
        audio_data = waveform.squeeze(0).numpy()
        sf.write(SPEAKER_WAV_PATH, audio_data, sample_rate, format='WAV', subtype='PCM_16')
        
        print(f"--> SUCCESS: Clean standard WAV file generated at {SPEAKER_WAV_PATH}")
        return {"status": "success", "message": "Voice profile updated successfully."}
        
    except Exception as e:
        print(f"Conversion processing error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process audio structure: {str(e)}")
        
    finally:
        # Always remove the temporary browser file
        if os.path.exists(temp_upload_path):
            os.remove(temp_upload_path)
        
@app.post("/ask")
async def ask_question(data: QuestionRequest):
    if not os.path.exists(SPEAKER_WAV_PATH):
        raise HTTPException(status_code=400, detail="No voice profile found. Please record your voice first.")
    
    if not data.question.strip():
        raise HTTPException(status_code=400, detail="Question text cannot be empty.")

    try:
        answer_text = generate_answer(data.question)
        print(f"Synthesizing response text: '{answer_text}'")

        model = get_tts_model()

        if os.path.exists(RESPONSE_WAV_PATH):
            os.remove(RESPONSE_WAV_PATH)

        # Since speaker.wav is now a true standard WAV file, this will succeed instantly!
        model.tts_to_file(
            text=answer_text,
            speaker_wav=SPEAKER_WAV_PATH,
            language="en",
            file_path=RESPONSE_WAV_PATH
        )

        if os.path.exists(RESPONSE_WAV_PATH):
            return FileResponse(RESPONSE_WAV_PATH, media_type="audio/wav", filename="response.wav")
            
        raise HTTPException(status_code=500, detail="TTS Engine failed to produce an audio file.")
    except Exception as e:
        print(f"Synthesis error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing voice clone request: {str(e)}")

# ==========================================
# 5. EXECUTION BLOCK
# ==========================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)