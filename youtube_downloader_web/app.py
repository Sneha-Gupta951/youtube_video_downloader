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
    # If requirements.txt is somehow missing or fails, install directly
    try:
        import yt_dlp
        from flask import Flask, request, jsonify, send_file, render_template
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp", "Flask"])
        import yt_dlp
        from flask import Flask, request, jsonify, send_file, render_template

app = Flask(__name__)

# Base directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS_DIR = os.path.join(BASE_DIR, 'downloads')
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# In-memory store for download progress 
progress_store = {}

def determine_ffmpeg():
    """Detects FFmpeg in system PATH or local directory/subdirectories."""
    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        # Check standard local paths first
        local_ffmpeg = os.path.join(BASE_DIR, "ffmpeg.exe")
        ffmpeg_folder_bin = os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe")
        
        if os.path.exists(local_ffmpeg):
            ffmpeg_path = local_ffmpeg
        elif os.path.exists(ffmpeg_folder_bin):
            ffmpeg_path = ffmpeg_folder_bin
        else:
            # Dynamically search in subdirectories (avoiding the downloads folder)
            for root, dirs, files in os.walk(BASE_DIR):
                if 'downloads' in dirs:
                    dirs.remove('downloads') # don't search downloaded videos
                
                if "ffmpeg.exe" in files:
                    ffmpeg_path = os.path.join(root, "ffmpeg.exe")
                    break
    return ffmpeg_path

def download_task(download_id, url, mode, quality):
    """Background task to handle yt-dlp downloading and post-processing."""
    # Create a unique directory for this download to avoid name collisons
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
    
    # yt-dlp Progress Hook
    def my_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            percent = (downloaded / total) * 100 if total > 0 else 0
            speed = d.get('speed')
            eta = d.get('eta')
            
            progress_store[download_id].update({
                'status': 'downloading',
                'percent': percent,
                'speed': speed,
                'eta': eta,
                'size': total
            })
        elif d['status'] == 'finished':
            # Finished downloading, post-processing (merging/extracting audio) begins
            progress_store[download_id].update({
                'status': 'processing'
            })
            
    # Base yt-dlp options
    ydl_opts = {
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'progress_hooks': [my_hook],
        'quiet': True,
        'no_warnings': True,
    }
    
    if has_ffmpeg:
        ydl_opts['ffmpeg_location'] = ffmpeg_path
        
    # Configure format and qualitative options
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
            # Fallback without FFmpeg
            ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
    else:
        # Video mode
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
                # Best Available
                ydl_opts['format'] = 'bestvideo[vcodec^=avc1]+bestaudio[acodec^=mp4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best'
        else:
            # Fallback without FFmpeg: cap at 720p, progressive MP4
            if "360p" in quality:
                ydl_opts['format'] = '18/best[height<=360][ext=mp4][acodec!=none]'
            elif "480p" in quality:
                ydl_opts['format'] = '135/best[height<=480][ext=mp4][acodec!=none]' # Often merged or fallback
            else:
                ydl_opts['format'] = '22/best[height<=720][ext=mp4][acodec!=none]'
                
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
        # Post-Processing fully complete when code reaches here
        # Read the resulting file
        files = os.listdir(download_dir)
        if files:
            progress_store[download_id].update({
                'status': 'done',
                'filename': files[0] # Original title with correct extension
            })
        else:
            raise Exception("File was not saved properly. No output found.")
            
    except Exception as e:
        progress_store[download_id].update({
            'status': 'error',
            'error': str(e)
        })

@app.route('/')
def index():
    has_ffmpeg = determine_ffmpeg() is not None
    return render_template('index.html', has_ffmpeg=has_ffmpeg)

@app.route('/api/download', methods=['POST'])
def start_download():
    """Endpoint to initiate downloading via background thread"""
    data = request.json
    url = data.get('url')
    mode = data.get('format', 'Video')
    quality = data.get('quality', 'Best Available (4K/8K)')
    
    if not url:
        return jsonify({'error': 'URL is required'}), 400
        
    download_id = str(uuid.uuid4())
    
    # Threading prevents the request from blocking while downloading
    t = threading.Thread(target=download_task, args=(download_id, url, mode, quality))
    t.start()
    
    return jsonify({'download_id': download_id})

@app.route('/api/progress/<download_id>')
def get_progress(download_id):
    """Endpoint to check the progress of an ongoing download"""
    if download_id not in progress_store:
        return jsonify({'error': 'Not found'}), 404
        
    return jsonify(progress_store[download_id])

@app.route('/api/file/<download_id>')
def get_file(download_id):
    """Endpoint to download the final output file from the server to the client"""
    if download_id not in progress_store or progress_store[download_id]['status'] != 'done':
        return "File not ready", 400
        
    download_dir = os.path.join(DOWNLOADS_DIR, download_id)
    if not os.path.exists(download_dir):
        return "File directory not found", 404
        
    # Filter out active parts and hidden system files dynamically generated by the OS
    files = [f for f in os.listdir(download_dir) if not f.endswith('.ini') and not f.endswith('.part') and not f.startswith('.')]
    if not files:
        return "File not found", 404
        
    file_path = os.path.join(download_dir, files[0])
    # The browser will download it as an attachment with the original filename parsed by yt-dlp
    return send_file(file_path, as_attachment=True)

if __name__ == '__main__':
    # Starts the local standalone dev server
    app.run(debug=True, port=5000)
