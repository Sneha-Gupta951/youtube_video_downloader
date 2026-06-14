import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import os
import shutil
import zipfile
import urllib.request
import sys
import subprocess

# --- Auto-Install yt-dlp if missing ---
try:
    import yt_dlp
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "yt-dlp"])
    import yt_dlp

# FIX 1: Script ki directory base banao, cwd nahi
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class YoutubeDownloaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("YouTube Downloader (4K/1080p Support)")
        self.root.geometry("600x650")
        self.root.resizable(False, False)
        
        # --- FFmpeg Check ---
        self.ffmpeg_path = self.determine_ffmpeg()
        self.has_ffmpeg = self.ffmpeg_path is not None
        
        # --- Colors ---
        self.bg_color = "#2c3e50"
        self.fg_color = "#ecf0f1"
        self.accent_color = "#e74c3c"
        self.success_color = "#2ecc71"
        self.warning_color = "#f39c12"
        self.secondary_btn_color = "#34495e"
        
        self.root.configure(bg=self.bg_color)
        
        self.style = ttk.Style()
        self.style.theme_use('clam')
        self.style.map('TCombobox', fieldbackground=[('readonly', 'white')])
        self.style.configure("TCombobox", arrowsize=15)
        
        self.setup_ui()

    def determine_ffmpeg(self):
        """
        FIX 1: Improved FFmpeg detection.
        - System PATH check (all OS)
        - Local paths with .exe and without (Windows + Linux/Mac)
        - Subdirectory walk with executable verification
        """
        # Step 1: System PATH
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path:
            return ffmpeg_path

        # Step 2: Common local paths (Windows + Linux/Mac)
        candidates = [
            os.path.join(BASE_DIR, "ffmpeg.exe"),
            os.path.join(BASE_DIR, "ffmpeg"),
            os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg.exe"),
            os.path.join(BASE_DIR, "ffmpeg", "bin", "ffmpeg"),
        ]
        for path in candidates:
            if os.path.exists(path):
                return path

        # Step 3: Walk subdirectories (skip downloads folder)
        for root_dir, dirs, files in os.walk(BASE_DIR):
            dirs[:] = [d for d in dirs if d != 'downloads']
            for name in ["ffmpeg.exe", "ffmpeg"]:
                if name in files:
                    candidate = os.path.join(root_dir, name)
                    try:
                        result = subprocess.run(
                            [candidate, "-version"],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                            timeout=5
                        )
                        if result.returncode == 0:
                            return candidate
                    except Exception:
                        continue

        return None

    def setup_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()

        # --- Header ---
        header_frame = tk.Frame(self.root, bg=self.bg_color)
        header_frame.pack(pady=15)
        
        title_label = tk.Label(header_frame, text="YouTube Downloader", font=("Helvetica", 24, "bold"), bg=self.bg_color, fg=self.fg_color)
        title_label.pack()

        if self.has_ffmpeg:
            sub_text = "✨ High Quality System Active (1080p/4K Ready)"
            sub_color = self.success_color
        else:
            sub_text = "⚠️ Standard Mode (720p Max) - Enable HQ below"
            sub_color = self.warning_color
            
        self.subtitle_label = tk.Label(header_frame, text=sub_text, font=("Helvetica", 10, "bold"), bg=self.bg_color, fg=sub_color)
        self.subtitle_label.pack()

        # --- FFmpeg Install / Locate Area (Only if missing) ---
        if not self.has_ffmpeg:
            self.install_frame = tk.Frame(self.root, bg=self.bg_color, highlightbackground=self.warning_color, highlightthickness=1)
            self.install_frame.pack(pady=10, padx=40, fill="x")
            
            lbl_info = tk.Label(self.install_frame, text="Want 1080p & 4K? You need the HQ Component.", bg=self.bg_color, fg=self.fg_color, font=("Arial", 9))
            lbl_info.pack(pady=(5, 0))
            
            self.btn_install = tk.Button(
                self.install_frame, text="Auto-Install HQ Component (Recommended)",
                command=self.start_ffmpeg_install,
                bg=self.warning_color, fg="black", font=("Arial", 10, "bold"), cursor="hand2"
            )
            self.btn_install.pack(pady=(5, 2))

            lbl_or = tk.Label(self.install_frame, text="- OR -", bg=self.bg_color, fg="#95a5a6", font=("Arial", 8))
            lbl_or.pack(pady=0)

            self.btn_locate = tk.Button(
                self.install_frame, text="I already have ffmpeg.exe (Locate File)",
                command=self.locate_ffmpeg,
                bg=self.secondary_btn_color, fg="white", font=("Arial", 9), cursor="hand2"
            )
            self.btn_locate.pack(pady=(2, 5))
            
            self.install_progress = ttk.Progressbar(self.install_frame, orient="horizontal", length=100, mode="determinate")

        # --- Input Area ---
        input_frame = tk.Frame(self.root, bg=self.bg_color)
        input_frame.pack(pady=10, padx=40, fill="x")
        
        lbl_url = tk.Label(input_frame, text="Paste Video Link:", bg=self.bg_color, fg=self.fg_color, font=("Arial", 11))
        lbl_url.pack(anchor="w", pady=(0, 5))
        
        self.url_entry = tk.Entry(input_frame, font=("Arial", 12), width=50)
        self.url_entry.pack(fill="x", ipady=5)

        # --- Options Area ---
        options_frame = tk.Frame(self.root, bg=self.bg_color)
        options_frame.pack(pady=15, padx=40, fill="x")
        
        type_frame = tk.Frame(options_frame, bg=self.bg_color)
        type_frame.pack(side="left", fill="x", expand=True, padx=(0, 10))
        
        lbl_type = tk.Label(type_frame, text="Format:", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10))
        lbl_type.pack(anchor="w", pady=(0, 2))
        
        self.type_var = tk.StringVar(value="Video")
        self.type_combo = ttk.Combobox(type_frame, textvariable=self.type_var, state="readonly", font=("Arial", 10))
        self.type_combo['values'] = ("Video", "Audio Only (MP3)")
        self.type_combo.pack(fill="x", ipady=3)
        self.type_combo.bind("<<ComboboxSelected>>", self.toggle_quality_dropdown)

        self.quality_frame = tk.Frame(options_frame, bg=self.bg_color)
        self.quality_frame.pack(side="left", fill="x", expand=True, padx=(10, 0))
        
        lbl_quality = tk.Label(self.quality_frame, text="Quality:", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10))
        lbl_quality.pack(anchor="w", pady=(0, 2))
        
        self.quality_var = tk.StringVar()
        self.quality_combo = ttk.Combobox(self.quality_frame, textvariable=self.quality_var, state="readonly", font=("Arial", 10))
        self.quality_combo.pack(fill="x", ipady=3)
        
        self.toggle_quality_dropdown()

        # --- Stats/Progress ---
        self.progress_frame = tk.Frame(self.root, bg=self.bg_color)
        self.progress_frame.pack(pady=10, padx=40, fill="x")
        
        self.status_label = tk.Label(self.progress_frame, text="Ready", bg=self.bg_color, fg="#bdc3c7", font=("Arial", 10, "bold"))
        self.status_label.pack(anchor="w", pady=(0, 5))
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", length=100, mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 10))

        stats_frame = tk.Frame(self.progress_frame, bg=self.bg_color)
        stats_frame.pack(fill="x")
        self.lbl_speed = tk.Label(stats_frame, text="Speed: --", bg=self.bg_color, fg="#95a5a6", font=("Arial", 9))
        self.lbl_speed.pack(side="left", expand=True)
        self.lbl_size = tk.Label(stats_frame, text="Size: --", bg=self.bg_color, fg="#95a5a6", font=("Arial", 9))
        self.lbl_size.pack(side="left", expand=True)
        self.lbl_eta = tk.Label(stats_frame, text="Time Left: --", bg=self.bg_color, fg="#95a5a6", font=("Arial", 9))
        self.lbl_eta.pack(side="left", expand=True)

        # --- Main Button ---
        self.btn_download = tk.Button(
            self.root, text="Download Video", command=self.start_download_thread,
            bg=self.accent_color, fg="white", font=("Arial", 12, "bold"),
            relief="flat", padx=30, pady=12, cursor="hand2"
        )
        self.btn_download.pack(pady=15)

    def toggle_quality_dropdown(self, event=None):
        mode = self.type_var.get()
        if mode == "Audio Only (MP3)":
            self.quality_combo['values'] = ["Standard (128kbps)", "High (192kbps)", "Best (320kbps)"]
            self.quality_combo.current(1)
        else:
            if self.has_ffmpeg:
                self.quality_combo['values'] = [
                    "Best Available (4K/8K)",
                    "1440p (2K)",
                    "1080p (Full HD)",
                    "720p (HD)",
                    "360p (Data Saver)"
                ]
                self.quality_combo.current(0)
            else:
                self.quality_combo['values'] = [
                    "720p (HD) [Limit]",
                    "360p (Data Saver)"
                ]
                self.quality_combo.current(0)

    def locate_ffmpeg(self):
        file_path = filedialog.askopenfilename(
            title="Locate ffmpeg.exe",
            filetypes=[("Executable Files", "*.exe"), ("All Files", "*.*")]
        )
        
        if file_path:
            filename = os.path.basename(file_path).lower()
            if "ffmpeg" not in filename:
                confirm = messagebox.askyesno(
                    "Confirmation",
                    f"You selected '{filename}'.\nNormally this file is named 'ffmpeg.exe'.\n\nAre you sure this is the correct FFmpeg executable?"
                )
                if not confirm:
                    return

            self.ffmpeg_path = file_path
            self.has_ffmpeg = True
            messagebox.showinfo("Success", "FFmpeg path linked successfully!\nHigh Quality modes enabled.")
            self.setup_ui()

    def start_ffmpeg_install(self):
        self.btn_install.config(state="disabled", text="Downloading Components... (This takes a moment)")
        self.btn_locate.config(state="disabled")
        self.install_progress.pack(fill="x", pady=5)
        self.install_progress.start(10)
        threading.Thread(target=self.install_ffmpeg_logic, daemon=True).start()

    def install_ffmpeg_logic(self):
        try:
            url = "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
            zip_path = os.path.join(BASE_DIR, "ffmpeg.zip")
            
            urllib.request.urlretrieve(url, zip_path)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                ffmpeg_src = None
                for file in file_list:
                    if file.endswith("ffmpeg.exe"):
                        ffmpeg_src = file
                        break
                
                if ffmpeg_src:
                    zip_ref.extract(ffmpeg_src, BASE_DIR)
                    extracted_path = os.path.join(BASE_DIR, ffmpeg_src)
                    dest_path = os.path.join(BASE_DIR, "ffmpeg.exe")
                    shutil.move(extracted_path, dest_path)

                    # FIX 2: Windows + Linux safe folder cleanup
                    top_folder = ffmpeg_src.replace("\\", "/").split("/")[0]
                    top_folder_path = os.path.join(BASE_DIR, top_folder)
                    if os.path.exists(top_folder_path) and os.path.isdir(top_folder_path):
                        shutil.rmtree(top_folder_path)
            
            if os.path.exists(zip_path):
                os.remove(zip_path)

            self.ffmpeg_path = os.path.join(BASE_DIR, "ffmpeg.exe")
            self.has_ffmpeg = True
            
            self.root.after(0, lambda: messagebox.showinfo("Success", "High Quality Components Installed!\n1080p and 4K are now enabled."))
            self.root.after(0, self.setup_ui)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Install Error", f"Failed to auto-install: {str(e)}\nPlease try restarting the app."))
            self.root.after(0, self.setup_ui)

    # FIX 3: filedialog main thread pe, phir background thread
    def start_download_thread(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please paste a link.")
            return

        # Pehle folder select karo (main thread pe - safe)
        save_dir = filedialog.askdirectory(title="Select Download Folder")
        if not save_dir:
            return

        self.btn_download.config(state="disabled", text="Processing...")
        self.status_label.config(text="Initializing...", fg=self.warning_color)
        self.progress_bar['value'] = 0

        # Ab background thread chalao, save_dir pass karo
        threading.Thread(target=self.download_logic, args=(url, save_dir), daemon=True).start()

    def download_logic(self, url, save_dir):
        # FIX 3: filedialog yahan se hata diya
        mode = self.type_var.get()
        quality = self.quality_var.get()
        
        ydl_opts = {
            'outtmpl': os.path.join(save_dir, '%(title)s.%(ext)s'),
            'progress_hooks': [self.my_hook],
            'quiet': True,
            'no_warnings': True,
        }

        if self.has_ffmpeg and self.ffmpeg_path:
            ydl_opts['ffmpeg_location'] = self.ffmpeg_path

        if mode == "Audio Only (MP3)":
            if self.has_ffmpeg:
                bitrate = "192"
                if "128" in quality: bitrate = "128"
                elif "320" in quality: bitrate = "320"
                
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': bitrate}],
                })
            else:
                ydl_opts['format'] = 'bestaudio[ext=m4a]/bestaudio'
        else:
            if self.has_ffmpeg:
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
                else:
                    ydl_opts['format'] = '22/best[height<=720][ext=mp4][acodec!=none]'

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            self.root.after(0, lambda: messagebox.showinfo("Success", "Download Completed!"))
            self.root.after(0, lambda: self.status_label.config(text="Done!", fg=self.success_color))
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", f"An error occurred:\n{str(e)}"))
            self.root.after(0, lambda: self.status_label.config(text="Error", fg=self.accent_color))
        finally:
            self.root.after(0, self.reset_ui)

    def my_hook(self, d):
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes', 0)
                percent = (downloaded / total) * 100 if total > 0 else 0
                
                speed_bps = d.get('speed')
                speed = f"{speed_bps/1048576:.1f} MB/s" if speed_bps else "--"
                
                eta = d.get('eta')
                eta_str = f"{int(eta//60)}:{int(eta%60):02d}" if eta else "--:--"
                
                size = f"{total/1048576:.1f} MB" if total else "--"

                self.root.after(0, lambda: self.update_stats(percent, speed, size, eta_str))
            except:
                pass
        elif d['status'] == 'finished':
            self.root.after(0, lambda: self.status_label.config(text="Processing/Merging...", fg=self.warning_color))

    def update_stats(self, p, s, z, e):
        self.progress_bar['value'] = p
        self.status_label.config(text=f"Downloading: {p:.1f}%")
        self.lbl_speed.config(text=f"Speed: {s}")
        self.lbl_size.config(text=f"Size: {z}")
        self.lbl_eta.config(text=f"ETA: {e}")

    def reset_ui(self):
        self.btn_download.config(state="normal", text="Download Video")
        if "Done" not in self.status_label.cget("text"):
            self.progress_bar['value'] = 0

if __name__ == "__main__":
    root = tk.Tk()
    app = YoutubeDownloaderApp(root)
    root.mainloop()