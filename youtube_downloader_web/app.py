import os
import threading
import uuid
import shutil
import sys
import subprocess

# --- Auto-Install Dependencies if missing ---
try:
    import yt_dlp
    from flask import Flask, request, jsonify, send_file, render_template
except ImportError:
    print("Missing dependencies. Installing automatically...")
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
    """Detects FFmpeg in system PATH or local directory/subdirectories."""
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

def get_ydl_base_opts():
    """
    Returns base yt-dlp options that bypass YouTube bot detection.
    Uses multiple strategies to avoid the 'Sign in to confirm' error.
    """
    opts = {
        # Mimic a real browser request
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        },
        # Use TV client — much less bot detection than web client
        'extractor_args': {
            'youtube': {
                'player_client': ['tv_embedded', 'web'],
                'player_skip': ['webpage', 'configs'],
            }
        },
        # Retry on failure
        'retries': 5,
        'fragment_retries': 5,
        'skip_unavailable_fragments': True,
        # Sleep between requests to avoid rate limiting
        'sleep_interval': 1,
        'max_sleep_interval': 3,
    }

    # If cookies.txt file exists (user-provided), use it
    cookies_path = os.path.join(BASE_DIR, 'cookies.txt')
    if os.path.exists(cookies_path):
        opts['cookiefile'] = cookies_path

    return opts

def download_task(download_id, url, mode, quality):
    """Background task to handle yt-dlp downloading and post-processing."""
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

    # Start with base anti-bot options
    ydl_opts = get_ydl_base_opts()
    ydl_opts.update({
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'progress_hooks': [my_hook],
        'quiet': True,
        'no_warnings': True,
    })

    if has_ffmpeg:
        ydl_opts['ffmpeg_location'] = ffmpeg_path

    # Configure format based on mode and quality
    if mode == "Audio Only (MP3)":
        if has_ffmpeg:
            bitrate = "192"
            if "128" in quality: bitrate = "128"
            elif "320" in quality: bitrate = "320"
            ydl_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': bitrate
                }],
            })
        else:
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
    else:
        if has_ffmpeg:
            ydl_opts['merge_output_format'] = 'mp4'
            if "360p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=360][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=360]+bestaudio/best[height<=360]'
            elif "480p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=480][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=480]+bestaudio/best[height<=480]'
            elif "720p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=720][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]'
            elif "1080p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=1080][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]/best'
            elif "1440p" in quality:
                ydl_opts['format'] = 'bestvideo[height<=1440][vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[height<=1440][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1440]+bestaudio/best[height<=1440]/best'
            else:
                ydl_opts['format'] = 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        else:
            if "360p" in quality:
                ydl_opts['format'] = '18/best[height<=360][ext=mp4][acodec!=none]'
            elif "480p" in quality:
                ydl_opts['format'] = '135/best[height<=480][ext=mp4][acodec!=none]'
            else:
                ydl_opts['format'] = '22/best[height<=720][ext=mp4][acodec!=none]'

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        files = os.listdir(download_dir)
        if files:
            progress_store[download_id].update({
                'status': 'done',
                'filename': files[0]
            })
        else:
            raise Exception("File was not saved properly. No output found.")

    except Exception as e:
        error_msg = str(e)
        # If still getting bot error, try fallback with android client
        if 'Sign in to confirm' in error_msg or 'bot' in error_msg.lower():
            try:
                fallback_opts = get_ydl_base_opts()
                fallback_opts.update({
                    'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
                    'progress_hooks': [my_hook],
                    'quiet': True,
                    'no_warnings': True,
                    'format': 'best[ext=mp4]/best',
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android', 'web_creator'],
                        }
                    },
                })
                if has_ffmpeg:
                    fallback_opts['ffmpeg_location'] = ffmpeg_path

                with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                    ydl.download([url])

                files = os.listdir(download_dir)
                if files:
                    progress_store[download_id].update({
                        'status': 'done',
                        'filename': files[0]
                    })
                else:
                    raise Exception("Fallback also failed. No output found.")
            except Exception as e2:
                progress_store[download_id].update({
                    'status': 'error',
                    'error': str(e2)
                })
        else:
            progress_store[download_id].update({
                'status': 'error',
                'error': error_msg
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
