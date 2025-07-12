import os
import uuid
import shutil
import subprocess
from flask import Flask, request, jsonify, send_from_directory, abort
import requests

app = Flask(__name__)

# Directory to store temporary files and HLS output
TMP_DIR = "/tmp/video_stream"
os.makedirs(TMP_DIR, exist_ok=True)

# Serve static files (the HLS segments and playlist)
@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(TMP_DIR, filename)

def convert_to_hls(input_path: str, output_dir: str):
    """
    Convert video to HLS format using system ffmpeg command.
    """
    os.makedirs(output_dir, exist_ok=True)
    output_m3u8 = os.path.join(output_dir, "stream.m3u8")
    segment_pattern = os.path.join(output_dir, "seg_%03d.ts")

    # ffmpeg command line
    cmd = [
        "ffmpeg",
        "-i", input_path,
        "-codec:", "copy",
        "-start_number", "0",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-f", "hls",
        "-hls_segment_filename", segment_pattern,
        output_m3u8,
        "-y"
    ]

    process = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg failed: {process.stderr.decode()}")
    return output_m3u8

@app.route('/stream_file', methods=['POST'])
def stream_file():
    data = request.get_json()
    if not data or "video_path" not in data:
        return jsonify({"error": "Missing 'video_path' in request JSON"}), 400

    video_path = data["video_path"]
    file_id = str(uuid.uuid4())
    output_dir = os.path.join(TMP_DIR, file_id + "_hls")

    try:
        # Check if the input is a URL or local file path
        if video_path.startswith("http://") or video_path.startswith("https://"):
            # Download file temporarily
            temp_file_path = os.path.join(TMP_DIR, f"{file_id}_input")
            with requests.get(video_path, stream=True, timeout=30) as r:
                r.raise_for_status()
                with open(temp_file_path, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
            input_file = temp_file_path
        else:
            # Assume local file path, check if exists
            if not os.path.isfile(video_path):
                return jsonify({"error": "Local video file not found"}), 400
            input_file = video_path

        # Convert to HLS
        convert_to_hls(input_file, output_dir)

        # Clean up downloaded file if any
        if video_path.startswith("http://") or video_path.startswith("https://"):
            os.remove(temp_file_path)

        playlist_url = f"/static/{file_id}_hls/stream.m3u8"
        return jsonify({"message": "Conversion successful", "playlist_url": playlist_url})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
