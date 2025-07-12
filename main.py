from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
import uuid
import os
import subprocess
import shutil
import asyncio
from contextlib import asynccontextmanager

TMP_BASE = "/tmp/hls_streams"
os.makedirs(TMP_BASE, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup
    asyncio.create_task(cleanup_old_sessions())
    yield
    # On shutdown (if needed)

app = FastAPI(lifespan=lifespan)

# Enable CORS for all origins (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For production, consider using specific origins like ["https://serenekeks.com"]
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Serve static HLS files for each session id
@app.get("/stream/{session_id}/{filename}")
async def stream_file(session_id: str, filename: str):
    dir_path = os.path.join(TMP_BASE, session_id)
    file_path = os.path.join(dir_path, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(404, "File not found")
    return FileResponse(file_path, headers={
        "Access-Control-Allow-Origin": "*",
    })

@app.post("/convert")
async def convert(request: Request):
    data = await request.json()
    video_url = data.get("video_url")
    if not video_url:
        raise HTTPException(400, detail="Missing video_url")

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TMP_BASE, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # Determine the ffmpeg executable path
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        # Fallback if shutil.which doesn't find it for some reason (less likely with nixpacks)
        # This path is based on your error message's indication of `/root/.nix-profile`
        # You might need to confirm this path on your Railway container if issues persist.
        ffmpeg_path = "/root/.nix-profile/bin/ffmpeg"
        if not os.path.exists(ffmpeg_path):
            raise RuntimeError("ffmpeg executable not found. Ensure it's installed and accessible.")

    # Build ffmpeg command to create HLS stream in temp folder
    ffmpeg_cmd = [
        ffmpeg_path,  # Use the determined full path to ffmpeg
        "-y",
        "-i", video_url,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-f", "hls",
        "-hls_time", "4",
        "-hls_list_size", "5",
        "-hls_flags", "delete_segments+temp_file",
        os.path.join(session_dir, "index.m3u8"),
    ]

    # Run ffmpeg in background, detached (no wait)
    subprocess.Popen(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    playlist_url = f"/stream/{session_id}/index.m3u8"
    return JSONResponse({"playlist_url": playlist_url})


# Optional cleanup task (not mandatory, but recommended)
async def cleanup_old_sessions():
    while True:
        now = int(asyncio.get_event_loop().time())
        for folder in os.listdir(TMP_BASE):
            folder_path = os.path.join(TMP_BASE, folder)
            if os.path.isdir(folder_path):
                # Remove folders older than 1 hour (3600s)
                try:
                    mod_time = os.path.getmtime(folder_path)
                    if (now - mod_time) > 3600:
                        shutil.rmtree(folder_path)
                        print(f"Deleted old session folder: {folder_path}")
                except Exception as e:
                    print(f"Error cleaning folder {folder_path}: {e}")
        await asyncio.sleep(3600)  # Run cleanup every hour
