from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
import uuid
import os
import subprocess
import shutil
import asyncio

app = FastAPI()

# Enable CORS for all origins (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

TMP_BASE = "/tmp/hls_streams"
os.makedirs(TMP_BASE, exist_ok=True)

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

@app.options("/convert")
async def options_convert():
    # Reply to CORS preflight
    return JSONResponse(status_code=200, content={})

@app.post("/convert")
async def convert(request: Request):
    data = await request.json()
    video_url = data.get("video_url")
    if not video_url:
        raise HTTPException(400, detail="Missing video_url")

    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TMP_BASE, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # Build ffmpeg command to create HLS stream in temp folder
    ffmpeg_cmd = [
        "ffmpeg",
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

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_old_sessions())
