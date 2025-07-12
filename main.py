from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uuid
import os
import shutil
import ffmpeg
import httpx

app = FastAPI()

# CORS middleware added BEFORE static files mount
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://serenekeks.com"],  # your frontend origin here
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="/tmp"), name="static")


@app.options("/{rest_of_path:path}")
async def options_handler(rest_of_path: str, request: Request):
    # Handle OPTIONS preflight requests with empty response and correct headers via CORSMiddleware
    return {}


@app.post("/stream_file")
async def stream_file_handler(payload: dict):
    video_url = payload.get("video_url")
    if not video_url:
        raise HTTPException(status_code=400, detail="Missing video_url")

    # Create temp directory for this stream
    temp_dir = f"/tmp/{uuid.uuid4()}"
    os.makedirs(temp_dir, exist_ok=True)

    try:
        # Download video file
        local_file = os.path.join(temp_dir, "input.mp4")
        async with httpx.AsyncClient() as client:
            response = await client.get(video_url)
            response.raise_for_status()
            with open(local_file, "wb") as f:
                f.write(response.content)

        # Transcode to HLS using ffmpeg-python
        playlist_path = os.path.join(temp_dir, "playlist.m3u8")
        (
            ffmpeg
            .input(local_file)
            .output(
                playlist_path,
                format="hls",
                hls_time=10,
                hls_list_size=0,
                hls_flags="delete_segments+program_date_time",
                vcodec="copy",
                acodec="copy",
            )
            .overwrite_output()
            .run()
        )

        # Return the relative URL to playlist for frontend to use
        playlist_url = f"/static/{os.path.basename(temp_dir)}/playlist.m3u8"
        return {"playlist_url": playlist_url}

    except Exception as e:
        # Cleanup on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))
