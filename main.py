from flask import Flask, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import subprocess
import os
import uuid

app = Flask(__name__)
CORS(app, origins=["https://serenekeks.com"])  # Restrict origin to your frontend domain

# Directory to save HLS output segments/playlists
HLS_OUTPUT_DIR = "hls_streams"
os.makedirs(HLS_OUTPUT_DIR, exist_ok=True)

@app.route('/stream_file', methods=['POST', 'OPTIONS'])
def stream_file():
    if request.method == 'OPTIONS':
        # Preflight CORS response
        return '', 204

    data = request.get_json()
    if not data or 'video_url' not in data:
        return jsonify({"error": "Missing 'video_url' in request body"}), 400

    video_url = data['video_url']
    print(f"Received video_url to stream: {video_url}")

    # Generate a unique ID for this stream session
    stream_id = str(uuid.uuid4())
    stream_dir = os.path.join(HLS_OUTPUT_DIR, stream_id)
    os.makedirs(stream_dir, exist_ok=True)

    # Output playlist filename
    playlist_filename = "playlist.m3u8"
    output_path = os.path.join(stream_dir, playlist_filename)

    # FFmpeg command to convert video URL to HLS segments/playlist
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",  # overwrite output
        "-i", video_url,  # input video URL
        "-codec:", "copy",  # copy codecs (no re-encoding for speed, remove if incompatible)
        "-start_number", "0",
        "-hls_time", "10",  # 10-second segments
        "-hls_list_size", "0",  # include all segments in playlist
        "-f", "hls",
        output_path
    ]

    try:
        # Run ffmpeg and wait for it to complete
        print("Running ffmpeg command...")
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print("FFmpeg error:", result.stderr)
            return jsonify({"error": "FFmpeg failed to process video"}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "FFmpeg timed out"}), 500

    # Return relative playlist URL for client to play
    playlist_url = f"/hls_streams/{stream_id}/{playlist_filename}"
    print(f"Streaming ready: {playlist_url}")

    return jsonify({"playlist_url": playlist_url})


# Serve HLS stream files (playlist + ts segments)
@app.route('/hls_streams/<stream_id>/<path:filename>')
def serve_hls_files(stream_id, filename):
    directory = os.path.join(HLS_OUTPUT_DIR, stream_id)
    if not os.path.exists(os.path.join(directory, filename)):
        abort(404)
    return send_from_directory(directory, filename)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
