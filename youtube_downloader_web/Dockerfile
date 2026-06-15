# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Install FFmpeg cleanly from the Debian repositories.
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container
COPY requirements.txt ./

# Install the Python dependencies (always latest yt-dlp)
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir --upgrade yt-dlp

# Copy the rest of the application code
COPY . .

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 3 --threads 2 --timeout 300 app:app"]