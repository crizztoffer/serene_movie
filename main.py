from flask import Flask, request, jsonify, make_response, send_from_directory, abort
import subprocess
import os
import uuid

app = Flask(__name__)

FRONTEND_ORIGIN = "https://serenekeks.com"

HLS_OUTPUT_DIR = "./hls_streams"
os.makedirs(HLS_OUTPUT_DIR, exist_ok=True)

def cors_response(response):
    response.headers['Access-Control-Allow-Origin'] = FRONTEND_ORIGIN
    response.headers['Access-Control-Allow-Methods'] = 'POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response

@app.route('/stream_file', methods=['POST', 'OPTIONS'])
def stream_file():
    if request.method == 'OPTIONS':
        # Reply to CORS preflight requests
        response = make_response()
        return cors_response(response)

    data = request.get_json()
    if not data or 'video_url' not in data:
        response = jsonify({'error': 'Missing video_url in JSON'})
        response.status_code = 400
        return cors_response(response)

    video_url = data['video_url']

    # Generate unique output folder for this stream
    stream_id = str(uuid.uuid4())
    output_folder = os.path.join(HLS_OUTPUT_DIR, stream_id)
    os.makedirs(output_folder, exist_ok=True)

    playlist_path = os.path.join(output_folder, "playlist.m3u8")

    # ffmpeg command to convert remote video URL to HLS
    ffmpeg_cmd = [
        "ffmpeg",
        "-y",  # overwrite output files if exist
        "-i", video_url,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-strict", "-2",  # for some AAC codec compliance
        "-flags", "+cgop",
        "-g", "30",
        "-hls_time", "10",
        "-hls_list_size", "0",
        "-f", "hls",
        playlist_path
    ]

    try:
        subprocess.run(ffmpeg_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        response = jsonify({'error': 'Failed to generate HLS stream', 'details': e.stderr.decode()})
        response.status_code = 500
        return cors_response(response)

    playlist_url = f"/hls_streams/{stream_id}/playlist.m3u8"

    response = jsonify({'playlist_url': playlist_url})
    return cors_response(response)

@app.route('/hls_streams/<stream_id>/<filename>')
def serve_hls(stream_id, filename):
    dir_path = os.path.join(HLS_OUTPUT_DIR, stream_id)
    if not os.path.isdir(dir_path):
        abort(404)
    return send_from_directory(dir_path, filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
