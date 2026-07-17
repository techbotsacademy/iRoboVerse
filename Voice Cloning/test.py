import os
import shutil
import torch
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Voice Clone AI Q&A Backend")

# 1. Middlewares first
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SPEAKER_WAV_PATH = "speaker.wav"
RESPONSE_WAV_PATH = "response.wav"
tts = None

def get_tts_model():
    global tts
    if tts is None:
        print("Loading Coqui XTTS v2 Model...")
        from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return tts

def generate_answer(question: str) -> str:
    return f"This is a demo response to your question: {question}."

class QuestionRequest(BaseModel):
    question: str

# 2. Route definitions must come before uvicorn.run
@app.get("/")
async def serve_ui():
    """Serves the frontend interface directly at http://127.0.0.1:8000/"""
    return FileResponse("index.html")

@app.post("/upload_voice")
async def upload_voice(file: UploadFile = File(...)):
    try:
        with open(SPEAKER_WAV_PATH, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        return {"status": "success", "message": "Voice profile updated."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/ask")
async def ask_question(data: QuestionRequest):
    if not os.path.exists(SPEAKER_WAV_PATH):
        raise HTTPException(status_code=400, detail="No voice profile found.")
    try:
        answer_text = generate_answer(data.question)
        model = get_tts_model()
        if os.path.exists(RESPONSE_WAV_PATH):
            os.remove(RESPONSE_WAV_PATH)
        model.tts_to_file(text=answer_text, speaker_wav=SPEAKER_WAV_PATH, language="en", file_path=RESPONSE_WAV_PATH)
        return FileResponse(RESPONSE_WAV_PATH, media_type="audio/wav", filename="response.wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 3. Execution block must be at the ABSOLUTE BOTTOM
if __name__ == "__main__":
    import uvicorn
    # Use string notation 'server:app' so that hot reloading works correctly on Windows
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)