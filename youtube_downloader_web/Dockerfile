# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install FFmpeg cleanly from the Debian repositories. 
# This avoids needing the Windows .exe in production and maps perfectly to our Python check!
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt ./

# Install the Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Ensure standard mode starts the app on Render's assigned port using Gunicorn.
# The yt-dlp library can be IO heavy, so we use threaded workers.
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 3 --threads 2 --timeout 300 app:app"]
