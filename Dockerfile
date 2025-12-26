FROM python:3.12-slim-bookworm

# ---- System dependencies ----
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ---- Install yt-dlp ----
RUN curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp \
    -o /usr/local/bin/yt-dlp \
    && chmod a+rx /usr/local/bin/yt-dlp

# ---- Working directory ----
WORKDIR /app

# ---- Python dependencies ----
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ---- Application code ----
COPY src/ ./src/
COPY main.py .
COPY dashboard.py .
COPY config.docker.yml ./config.yml

# ---- Download directory ----
RUN mkdir -p /downloads

# ---- Non-root user ----
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /downloads
USER appuser

# ---- Default command ----
CMD ["python", "main.py"]
