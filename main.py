import os
import uuid
import shutil
import ffmpeg
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Serve HLS content from /tmp
app.mount("/static", StaticFiles(directory="/tmp"), name="static")

# --- Correct and complete CORS config ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://serenekeks.com",
        "http://localhost",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Force handle all OPTIONS requests ---
@app.options("/{rest_of_path:path}")
async def preflight_handler(rest_of_path: str, request: Request):
    return JSONResponse(status_code=204, content=None)

def convert_to_hls(input_path: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    output_m3u8 = os.path.join(output_dir, "stream.m3u8")
    segment_pattern = os.path.join(output_dir, "seg_%03d.ts")

    try:
        (
            ffmpeg
            .input(input_path)
            .output(
                output_m3u8,
                format='hls',
                hls_time=10,
                hls_playlist_type='vod',
                hls_segment_filename=segment_pattern,
                loglevel='error'
            )
            .run(overwrite_output=True)
        )
    except ffmpeg.Error as e:
        raise RuntimeError(f"FFmpeg conversion failed: {e.stderr.decode()}")
    return output_m3u8

@app.post("/stream_file")
async def stream_file(video_url: str):
    if not video_url:
        raise HTTPException(status_code=400, detail="No video URL provided.")

    file_id = str(uuid.uuid4())
    file_extension = os.path.splitext(video_url)[1] or ".mp4"
    temp_input_path = f"/tmp/{file_id}{file_extension}"
    output_dir = f"/tmp/{file_id}_hls"

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(video_url)
            response.raise_for_status()
            with open(temp_input_path, "wb") as f:
                f.write(response.content)

        convert_to_hls(temp_input_path, output_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")
    finally:
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)

    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = f"/tmp/{file_id}_{file.filename}"
    output_dir = f"/tmp/{file_id}_hls"

    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        convert_to_hls(input_path, output_dir)
    except Exception as e:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")
    finally:
        if os.path.exists(input_path):
            os.remove(input_path)

    return {
        "message": "Upload successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }
