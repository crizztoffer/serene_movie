import os
import uuid
import shutil
import ffmpeg
import httpx  # For making HTTP requests to download files
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from fastapi.middleware.cors import CORSMiddleware # Import CORSMiddleware for CORS handling

app = FastAPI()

# Mount static files from /tmp so clients can access the .m3u8 and .ts files
# Ensure /tmp is accessible and writable by your application process in the container.
app.mount("/static", StaticFiles(directory="/tmp"), name="static")

# --- CORS Configuration ---
# This middleware must be configured to allow your frontend's domain to access your backend.
origins = [
    "https://serenekeks.com",  # Explicitly allow your frontend domain
    "http://localhost",        # For local development of your frontend (if you run PHP locally)
    "http://localhost:8080",   # Another common local development port
    # If you access your Railway app directly for testing, you might temporarily add its domain:
    # "https://serenemovie-production.up.railway.app",
    # Be more restrictive in production if possible.
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,       # List of allowed origins
    allow_credentials=True,      # Allow cookies, authorization headers, etc.
    allow_methods=["*"],         # Allow all HTTP methods (GET, POST, PUT, DELETE, OPTIONS)
    allow_headers=["*"],         # Allow all headers in the request
)
# --- End CORS Configuration ---


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
        # The .run() method of ffmpeg-python executes the ffmpeg command.
        # This requires the 'ffmpeg' binary to be installed on the system where the app runs.
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
        # Capture stderr from FFmpeg process for more specific error messages
        print(f"FFmpeg error: {e.stderr.decode()}")
        raise RuntimeError(f"FFmpeg conversion failed: {e.stderr.decode()}")
    except Exception as e:
        # Catch any other unexpected exceptions during conversion
        print(f"An unexpected error occurred during HLS conversion: {e}")
        raise RuntimeError(f"HLS conversion failed: {e}")

    return output_m3u8

@app.post("/stream_file")
async def stream_file(video_url: str):
    """
    Downloads a video file from a given URL and converts it to an HLS stream.

    Args:
        video_url (str): The public URL of the video file to stream (e.g., from serenekeks.com).

    Returns:
        JSONResponse: A JSON response containing the URL to the HLS stream
                      or an error message.
    """
    if not video_url:
        raise HTTPException(status_code=400, detail="No video URL provided.")

    file_id = str(uuid.uuid4())
    # Extract file extension from the URL to use in the temp file name.
    # This helps ffmpeg correctly identify the input file type.
    file_extension = os.path.splitext(video_url)[1]
    if not file_extension:
        file_extension = ".mp4" # Fallback default if no extension found

    temp_input_path = f"/tmp/{file_id}{file_extension}"
    output_dir = f"/tmp/{file_id}_hls"

    print(f"Attempting to download video from: {video_url}")
    print(f"Saving to temporary path: {temp_input_path}")

    try:
        # Use httpx.AsyncClient for asynchronous HTTP requests to download the video.
        # follow_redirects=True: Important if the video URL redirects to the actual file.
        # timeout=30.0: Prevents download from hanging indefinitely.
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            response = await client.get(video_url)
            response.raise_for_status() # Raises an exception for 4xx/5xx HTTP responses

            with open(temp_input_path, "wb") as f:
                f.write(response.content) # Write the downloaded content to a temporary file
        print("Video downloaded successfully.")

        # Convert the downloaded file to HLS format.
        convert_to_hls(temp_input_path, output_dir)
        print("HLS conversion successful.")

    except httpx.HTTPStatusError as e:
        # Handle HTTP errors during the download process (e.g., source video not found)
        print(f"HTTP error downloading video: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=500, detail=f"Failed to download video: HTTP error {e.response.status_code}")
    except httpx.RequestError as e:
        # Handle network-related errors during download (e.g., connection issues)
        print(f"Network error downloading video: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to download video: Network error - {e}")
    except RuntimeError as e:
        # Handle errors specifically raised by the convert_to_hls function
        print(f"Runtime error during HLS conversion: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        # Catch any other unexpected errors during the entire process
        print(f"An unexpected error occurred: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {e}")
    finally:
        # Crucially, clean up the temporary downloaded input file.
        # The HLS output directory (/tmp/{file_id}_hls) is left, as the client needs to access it via /static.
        # Railway's ephemeral filesystem will clean /tmp on container restarts.
        if os.path.exists(temp_input_path):
            os.remove(temp_input_path)
            print(f"Cleaned up temporary downloaded file: {temp_input_path}")


    # Return the relative URL to the HLS playlist.
    # The frontend will prepend the backend's base URL to this.
    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }

# This endpoint handles direct file uploads and converts them to HLS.
# It uses the same HLS conversion logic.
@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    # Generate unique IDs for the uploaded file and its HLS output directory
    file_id = str(uuid.uuid4())
    input_path = f"/tmp/{file_id}_{file.filename}"
    output_dir = f"/tmp/{file_id}_hls"

    # Save the uploaded file to a temporary location on disk
    try:
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f) # Efficiently copies file content
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {e}")

    # Convert the uploaded file to HLS
    try:
        convert_to_hls(input_path, output_dir)
    except RuntimeError as e:
        # Clean up if conversion fails
        if os.path.exists(input_path):
            os.remove(input_path)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir) # Remove directory and its contents
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

    # Return the relative URL to the HLS playlist
    return {
        "message": "Conversion successful",
        "playlist_url": f"/static/{file_id}_hls/stream.m3u8"
    }
