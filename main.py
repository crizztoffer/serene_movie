import os
import uuid
import shutil
import ffmpeg
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static files from /tmp so clients can access the .m3u8 and .ts files
app.mount("/static", StaticFiles(directory="/tmp"), name="static")

def convert_to_hls(input_path: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    output_m3u8 = os.path.join(output_dir, "stream.m3u8")
    segment_pattern = os.path.join(output_dir, "seg_%03d.ts")

    (
        ffmpeg
        .input(input_path)
        .output(
            output_m3u8,
            format='hls',
            hls_time=10,
            hls_playlist_type='vod',
            hls_segment_filename=segment_pattern
        )
        .run(overwrite_output=True)
    )

    return output_m3u8

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    # Create unique temp file names
    file_id = str(uuid.uuid4())
    input_path = f"/tmp/{file_id}_{file.filename}"
    output_dir = f"/tmp/{file_id}_hls"

    # Save uploaded file to disk
    with open(input_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Convert to HLS
    try:
        convert_to_hls(input_path, output_dir)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    # Return URL to HLS stream
    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }
