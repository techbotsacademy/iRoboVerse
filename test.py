import os
from dotenv import load_dotenv

# Path to local FFmpeg binaries (for Windows system fallback)
FFMPEG_PATH="C:\\ffmpeg\\bin"
# Load variables from the .env file
load_dotenv()

# 1. Get the FFmpeg path from the .env file
ffmpeg_path = os.environ.get("FFMPEG_PATH")

# 2. Inject it into the system's runtime PATH variable if it exists
if ffmpeg_path:
    # On Windows, system paths are separated by a semicolon (;)
    os.environ["PATH"] += os.pathsep + ffmpeg_path
    print(f"[System] Injected FFmpeg path into runtime environment: {ffmpeg_path}")
else:
    os.environ["PATH"] += os.pathsep + FFMPEG_PATH
    print(os.environ["PATH"])