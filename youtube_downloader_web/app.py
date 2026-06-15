import os
import threading
import uuid
import shutil
import sys
import subprocess

try:
    import yt_dlp
    from flask import Flask, request, jsonify, send_file, render_template
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    try:
        import yt_dlp
        from flask import Flask, request, jsonify, send_file, render_template
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp", "Flask"])
        import yt_dlp
        from flask import Flask, request, jsonify, send_file, render_template

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

progress_store = {}

def determine_ffmpeg():
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        local_ffmpeg = os.path.join(BASE_DIR, "ffmpeg.exe")
        ffmpeg_folder_bin = os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            ffmpeg_path = local_ffmpeg
        elif os.path.exists(ffmpeg_folder_bin):
            ffmpeg_path = ffmpeg_folder_bin
        else:
            for root, dirs, files in os.walk(BASE_DIR):
                if 'downloads' in dirs:
                    dirs.remove('downloads')
                if "ffmpeg.exe" in files:
                    ffmpeg_path = os.path.join(root, "ffmpeg.exe")
                    break
    return ffmpeg_path

def try_download(ydl_opts, url, download_dir):
    """Try download and return list of files if successful."""
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    files = os.listdir(download_dir)
    if not files:
        raise Exception("No output file found.")
    return files

def download_task(download_id, url, mode, quality):
    download_dir = os.path.join(DOWNLOADS_DIR, download_id)
    os.makedirs(download_dir, exist_ok=True)

    progress_store[download_id] = {
        'status': 'initializing',
        'percent': 0,
        'speed': None,
        'eta': None,
        'size': None,
        'error': None,
        'filename': None
    }

    ffmpeg_path = determine_ffmpeg()
    has_ffmpeg = ffmpeg_path is not None

    def my_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total) * 100 if total > 0 else 0
            progress_store[download_id].update({
                'status': 'downloading',
                'percent': percent,
                'speed': d.get('speed'),
                'eta': d.get('eta'),
                'size': total
            })
        elif d['status'] == 'finished':
            progress_store[download_id].update({'status': 'processing'})

    base = {
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'progress_hooks': [my_hook],
        'quiet': True,
        'no_warnings': True,
        'retries': 3,
        'fragment_retries': 3,
    }
    if has_ffmpeg:
        base['ffmpeg_location'] = ffmpeg_path

    # Format selection
    if mode == "Audio Only (MP3)":
        if has_ffmpeg:
            bitrate = "192"
            if "128" in quality: bitrate = "128"
            elif "320" in quality: bitrate = "320"
            format_opts = {
                'format': 'bestaudio/best',
                'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': bitrate}],
            }
        else:
            format_opts = {'format': 'bestaudio[ext=m4a]/bestaudio'}
    else:
        if has_ffmpeg:
            base['merge_output_format'] = 'mp4'
            if "360p" in quality:
                fmt = 'bestvideo[height<=360]+bestaudio/best[height<=360]'
            elif "480p" in quality:
                fmt = 'bestvideo[height<=480]+bestaudio/best[height<=480]'
            elif "720p" in quality:
                fmt = 'bestvideo[height<=720]+bestaudio/best[height<=720]'
            elif "1080p" in quality:
                fmt = 'bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
            elif "1440p" in quality:
                fmt = 'bestvideo[height<=1440]+bestaudio/best[height<=1440]/best'
            else:
                fmt = 'bestvideo+bestaudio/best'
            format_opts = {'format': fmt}
        else:
            if "360p" in quality:
                format_opts = {'format': '18/best[height<=360][ext=mp4]'}
            elif "480p" in quality:
                format_opts = {'format': 'best[height<=480][ext=mp4]'}
            else:
                format_opts = {'format': '22/best[height<=720][ext=mp4]'}

    # Try multiple clients in order
    clients_to_try = [
        # 1. iOS client — works best on Render
        {'extractor_args': {'youtube': {'player_client': ['ios']}}},
        # 2. Android client
        {'extractor_args': {'youtube': {'player_client': ['android']}}},
        # 3. TV embedded client
        {'extractor_args': {'youtube': {'player_client': ['tv_embedded']}}},
        # 4. mweb client
        {'extractor_args': {'youtube': {'player_client': ['mweb']}}},
        # 5. Last resort — no client specified
        {},
    ]

    cookies_path = os.path.join(BASE_DIR, 'cookies.txt')
    
    last_error = None
    for client_opts in clients_to_try:
        try:
            ydl_opts = {**base, **format_opts, **client_opts}
            if os.path.exists(cookies_path):
                ydl_opts['cookiefile'] = cookies_path
            
            files = try_download(ydl_opts, url, download_dir)
            progress_store[download_id].update({
                'status': 'done',
                'filename': files[0]
            })
            return  # Success!
        except Exception as e:
            last_error = str(e)
            # Clean partial files before next attempt
            for f in os.listdir(download_dir):
                if f.endswith('.part') or f.endswith('.ytdl'):
                    os.remove(os.path.join(download_dir, f))
            continue

    # All clients failed
    progress_store[download_id].update({
        'status': 'error',
        'error': last_error
    })


@app.route('/')
def index():
    has_ffmpeg = determine_ffmpeg() is not None
    return render_template('index.html', has_ffmpeg=has_ffmpeg)

@app.route('/api/download', methods=['POST'])
def start_download():
    data = request.json
    url = data.get('url')
    mode = data.get('format', 'Video')
    quality = data.get('quality', 'Best Available (4K/8K)')
    if not url:
        return jsonify({'error': 'URL is required'}), 400
    download_id = str(uuid.uuid4())
    t = threading.Thread(target=download_task, args=(download_id, url, mode, quality))
    t.start()
    return jsonify({'download_id': download_id})

@app.route('/api/progress/<download_id>')
def get_progress(download_id):
    if download_id not in progress_store:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(progress_store[download_id])

@app.route('/api/file/<download_id>')
def get_file(download_id):
    if download_id not in progress_store or progress_store[download_id]['status'] != 'done':
        return "File not ready", 400
    download_dir = os.path.join(DOWNLOADS_DIR, download_id)
    if not os.path.exists(download_dir):
        return "File directory not found", 404
    files = [f for f in os.listdir(download_dir) if not f.endswith('.ini') and not f.endswith('.part') and not f.startswith('.')]
    if not files:
        return "File not found", 404
    file_path = os.path.join(download_dir, files[0])
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True, port=5000)