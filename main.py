import os
import uuid
import shutil
import ffmpeg
import httpx # NEW: For making HTTP requests to download files
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

# Mount static files from /tmp so clients can access the .m3u8 and .ts files
app.mount("/static", StaticFiles(directory="/tmp"), name="static")

# CORS setup (ensure this is configured correctly for your frontend's domain)
from fastapi.middleware.cors import CORSMiddleware

origins = [
    "https://serenekeks.com",  # Your frontend domain
    # Add other origins if needed, e.g., for local development
    "http://localhost",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
async def stream_file(video_url: str): # CHANGED: Now expects video_url
    """
    Downloads a video file from a given URL and converts it to an HLS stream.

    Args:
        video_url (str): The public URL of the video file to stream.

    Returns:
        JSONResponse: A JSON response containing the URL to the HLS stream
                      or an error message.
    """
    if not video_url:
        raise HTTPException(status_code=400, detail="No video URL provided.")

    file_id = str(uuid.uuid4())
    # Determine a suitable temporary input path
    # Extract file extension from the URL to use in the temp file
    file_extension = os.path.splitext(video_url)[1]
    if not file_extension:
        file_extension = ".mp4" # Default if no extension found

    temp_input_path = f"/tmp/{file_id}{file_extension}"
    output_dir = f"/tmp/{file_id}_hls"

    print(f"Attempting to download video from: {video_url}")
    print(f"Saving to temporary path: {temp_input_path}")

    try:
        # Download the video file
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(video_url)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)

            with open(temp_input_path, "wb") as f:
                f.write(response.content)
        print("Video downloaded successfully.")

        # Convert the downloaded file to HLS
        convert_to_hls(temp_input_path, output_dir)
        print("HLS conversion successful.")

    except httpx.HTTPStatusError as e:
        print(f"HTTP error downloading video: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=500, detail=f"Failed to download video: HTTP error {e.response.status_code}")
    except httpx.RequestError as e:
        print(f"Network error downloading video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download video: Network error - {e}")
    except RuntimeError as e:
        print(f"Runtime error during HLS conversion: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
    finally:
        # Clean up the temporary downloaded file
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
            print(f"Cleaned up temporary downloaded file: {temp_input_path}")


    # Return URL to HLS stream
    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }

# Keep the /upload endpoint as is, as it handles direct file uploads
@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    file_id = str(uuid.uuid4())
    input_path = f"/tmp/{file_id}_{file.filename}"
    output_dir = f"/tmp/{file_id}_hls"

    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    try:
        convert_to_hls(input_path, output_dir)
    except RuntimeError as e:
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
        if os.path.exists(input_path):
            os.remove(input_path)

    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }
