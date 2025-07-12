from flask import Flask, request, jsonify, make_response, send_from_directory, abort
import subprocess
import os
import uuid

app = Flask(__name__)

FRONTEND_ORIGIN = "https://serenekeks.com"

# Directory to save generated HLS streams
HLS_OUTPUT_DIR = "./hls_streams"
os.makedirs(HLS_OUTPUT_DIR, exist_ok=True)

def cors_response(response):
    response.headers['Access-Control-Allow-Origin'] = FRONTEND_ORIGIN
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/stream_file', methods=['POST', 'OPTIONS'])
def stream_file():
    if request.method == 'OPTIONS':
        # Respond to preflight CORS request
        response = make_response()
        return cors_response(response)

    data = request.get_json()
    if not data or 'video_path' not in data:
        response = jsonify({'error': 'Missing video_path in JSON'})
        response.status_code = 400
        return cors_response(response)

    video_path = data['video_path']

    # Verify the video path exists on server (for security, restrict paths as needed)
    if not os.path.isfile(video_path):
        response = jsonify({'error': 'Video file not found on server'})
        response.status_code = 404
        return cors_response(response)

    # Create unique folder for HLS output
    stream_id = str(uuid.uuid4())
    output_folder = os.path.join(HLS_OUTPUT_DIR, stream_id)
    os.makedirs(output_folder, exist_ok=True)

    # Path for playlist output
    playlist_path = os.path.join(output_folder, "playlist.m3u8")

    # Build ffmpeg command to generate HLS (adjust as needed)
    ffmpeg_cmd = [
        "ffmpeg",
        "-i", video_path,
        "-codec:", "copy",
        "-start_number", "0",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-f", "hls",
        playlist_path
    ]

    try:
        # Run ffmpeg process
        subprocess.run(ffmpeg_cmd, check=True)
    except subprocess.CalledProcessError as e:
        response = jsonify({'error': 'Failed to generate HLS stream', 'details': str(e)})
        response.status_code = 500
        return cors_response(response)

    # Return playlist URL relative to this server
    playlist_url = f"/hls_streams/{stream_id}/playlist.m3u8"

    response = jsonify({'playlist_url': playlist_url})
    return cors_response(response)

@app.route('/hls_streams/<stream_id>/<filename>')
def serve_hls(stream_id, filename):
    # Serve generated HLS segments and playlists
    dir_path = os.path.join(HLS_OUTPUT_DIR, stream_id)
    if not os.path.isdir(dir_path):
        abort(404)
    return send_from_directory(dir_path, filename)

if __name__ == '__main__':
    # Run on all interfaces, port 8000 for example
    app.run(host='0.0.0.0', port=8000)
