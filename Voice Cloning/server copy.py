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
# 1. CORE MONKEY-PATCHES & UNIVERSAL LOADER
# ==========================================
# Bypass PyTorch 2.6+ strict weight checks for legacy models
original_load = torch.load
torch.load = lambda *args, **kwargs: original_load(*args, **{**kwargs, 'weights_only': False})

# ==========================================
# 1. CORE MONKEY-PATCHES & UNIVERSAL LOADER
# ==========================================
# Bypass PyTorch 2.6+ strict weight checks for legacy models
original_load = torch.load
torch.load = lambda *args, **kwargs: original_load(*args, **{**kwargs, 'weights_only': False})

# Secure the original torchaudio.load pointer to prevent infinite recursion loops
original_audio_load = torchaudio.load

def universal_audio_load(filepath, *args, **kwargs):
    """
    Attempts to read audio files via soundfile. If a browser container (WebM/Ogg)
    header error occurs, it drops down to the native torchaudio loader safely.
    """
    try:
        data, samplerate = sf.read(filepath, dtype='float32')
        tensor = torch.FloatTensor(data).t()
        if tensor.ndim == 1:
            tensor = tensor.unsqueeze(0)
        return tensor, samplerate
    except Exception:
        # Fallback: Let the original torchaudio backend safely handle container parsing
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            if hasattr(torchaudio, 'load_backend'):
                return torchaudio.load_backend(filepath, format="webm")
            # Call original_audio_load instead of torchaudio.load to break recursion
            return original_audio_load(filepath, *args, **kwargs)

# Force torchaudio to use the robust multi-format loader patch
torchaudio.load = universal_audio_load

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

# Resolve paths absolutely relative to this script's directory
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
    """Receives user microphone recording stream and guarantees hard file creation on disk."""
    try:
        # Directly copy the incoming upload stream to speaker.wav on disk
        with open(SPEAKER_WAV_PATH, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        # Verify file presence and size integrity
        if not os.path.exists(SPEAKER_WAV_PATH) or os.path.getsize(SPEAKER_WAV_PATH) == 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty or could not be written.")
            
        print(f"--> SUCCESS: Voice sample physically saved to {SPEAKER_WAV_PATH}")
        return {"status": "success", "message": "Voice profile updated successfully."}
        
    except Exception as e:
        print(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to save voice file: {str(e)}")
        
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