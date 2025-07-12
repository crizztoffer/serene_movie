import os
import uuid
import shutil
import ffmpeg
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static files from /tmp so clients can access the .m3u8 and .ts files
app.mount("/static", StaticFiles(directory="/tmp"), name="static")

def convert_to_hls(input_path: str, output_dir: str):
    """
    Converts a given video file to HLS format.

    Args:
        input_path (str): The path to the input video file.
        output_dir (str): The directory where HLS segments and playlist will be saved.
    """
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
                hls_time=10,  # Segment duration in seconds
                hls_playlist_type='vod', # Video on Demand playlist
                hls_segment_filename=segment_pattern,
                loglevel='error' # Suppress excessive ffmpeg output for cleaner logs
            )
            .run(overwrite_output=True)
        )
    except ffmpeg.Error as e:
        print(f"FFmpeg error: {e.stderr.decode()}")
        raise RuntimeError(f"FFmpeg conversion failed: {e.stderr.decode()}")
    except Exception as e:
        print(f"An unexpected error occurred during HLS conversion: {e}")
        raise RuntimeError(f"HLS conversion failed: {e}")

    return output_m3u8

@app.post("/stream_file")
async def stream_file(file_location: str):
    """
    Converts a file from a given local path to an HLS stream.

    Args:
        file_location (str): The absolute path to the file on the server's local filesystem.

    Returns:
        JSONResponse: A JSON response containing the URL to the HLS stream
                      or an error message.
    """
    # Validate the provided file_location
    if not os.path.exists(file_location):
        raise HTTPException(status_code=404, detail=f"File not found at: {file_location}")
    if not os.path.isfile(file_location):
        raise HTTPException(status_code=400, detail=f"The provided path is not a file: {file_location}")

    # Generate a unique ID for this conversion process
    file_id = str(uuid.uuid4())
    output_dir = f"/tmp/{file_id}_hls"

    try:
        # Convert the file to HLS
        convert_to_hls(file_location, output_dir)
    except RuntimeError as e:
        # Clean up the partially created directory if conversion fails
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")

    # Return URL to HLS stream
    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }

# You can keep your existing /upload endpoint if you still need file uploads
@app.post("/upload")
async def upload_video(file: UploadFile):
    # Create unique temp file names
    file_id = str(uuid.uuid4())
    input_path = f"/tmp/{file_id}_{file.filename}"
    output_dir = f"/tmp/{file_id}_hls"

    # Save uploaded file to disk
    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # Convert to HLS
    try:
        convert_to_hls(input_path, output_dir)
    except RuntimeError as e:
        # Clean up if conversion fails
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
    finally:
        # Clean up the original uploaded file after successful conversion
        if os.path.exists(input_path):
            os.remove(input_path)


    # Return URL to HLS stream
    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }
