from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
import uuid
import os
import subprocess
from pathlib import Path

app = FastAPI()

# === CONFIGURATION ===
ALLOWED_ORIGINS = ["https://serenekeks.com"]
STATIC_DIR = "static"
Path(STATIC_DIR).mkdir(parents=True, exist_ok=True)


# === CORS MIDDLEWARE ===
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# === FALLBACK MANUAL OPTIONS ROUTE FOR CORS (if necessary) ===
@app.options("/stream_file", include_in_schema=False)
async def cors_fallback_options():
    return Response(status_code=204, headers={
        "Access-Control-Allow-Origin": ALLOWED_ORIGINS[0],
        "Access-Control-Allow-Methods": "POST, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Max-Age": "86400"
    })


# === MODEL FOR REQUEST BODY ===
class StreamRequest(BaseModel):
    video_url: str


# === MAIN ROUTE TO PROCESS VIDEO ===
@app.post("/stream_file")
async def stream_file(req: StreamRequest):
    video_url = req.video_url

    if not video_url:
        raise HTTPException(status_code=400, detail="Missing video_url.")

    file_id = str(uuid.uuid4())
    input_path = f"{STATIC_DIR}/{file_id}_source.mp4"
    output_dir = f"{STATIC_DIR}/{file_id}_hls"
    os.makedirs(output_dir, exist_ok=True)

    try:
        # Download video
        subprocess.run([
            "ffmpeg", "-y", "-i", video_url, "-c", "copy", input_path
        ], check=True)

        # Convert to HLS
        subprocess.run([
            "ffmpeg", "-y", "-i", input_path,
            "-codec:V", "libx264", "-codec:a", "aac",
            "-f", "hls", "-hls_time", "4",
            "-hls_playlist_type", "vod",
            "-hls_segment_filename", f"{output_dir}/segment_%03d.ts",
            f"{output_dir}/stream.m3u8"
        ], check=True)

        # Return playlist path
        playlist_rel_path = f"/{output_dir}/stream.m3u8"
        return JSONResponse(
            content={"playlist_url": playlist_rel_path},
            headers={"Access-Control-Allow-Origin": ALLOWED_ORIGINS[0]}
        )

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"ffmpeg error: {e}")

    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Internal error: {str(ex)}")

