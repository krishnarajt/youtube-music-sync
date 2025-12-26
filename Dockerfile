# Use the official uv image for the build stage
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

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

# ---- Install dependencies with uv ----
# Enable bytecode compilation for faster startups
ENV UV_COMPILE_BYTECODE=1
# Copy only dependency files first to leverage Docker cache
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# ---- Final Stage ----
FROM python:3.12-slim-bookworm

# Re-install system tools in final image
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
COPY --from=builder /usr/local/bin/yt-dlp /usr/local/bin/yt-dlp

WORKDIR /app

# Copy the virtual environment and application code
COPY --from=builder /app/.venv /app/.venv
COPY src/ ./src/
COPY utils/ ./utils/
COPY main.py dashboard.py ./

# Set environment to use the uv virtualenv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Create download directory and user
RUN mkdir -p /downloads && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app /downloads

USER appuser

CMD ["python", "main.py"]