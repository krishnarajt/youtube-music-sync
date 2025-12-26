FROM python:3.12-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY main.py .
COPY dashboard.py .
COPY config.docker.yml ./config.yml

# Create downloads directory
RUN mkdir -p /downloads

# Run as non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app /downloads
USER appuser

# Default command
CMD ["python", "main.py"]