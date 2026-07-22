FROM python:3.11-slim

# Install FFmpeg
RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Tell the application where FFmpeg is located
ENV FFMPEG_LOCATION=/usr/bin

# Render provides the PORT environment variable
CMD gunicorn --bind 0.0.0.0:$PORT app:app