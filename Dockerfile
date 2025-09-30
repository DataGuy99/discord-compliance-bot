# Discord Compliance Bot - Development Dockerfile
# Python 3.12.7 (Heroku-compatible)

FROM python:3.12.7-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 botuser && chown -R botuser:botuser /app

# Copy requirements first for layer caching
COPY heroku-api/requirements.txt ./heroku-api/
COPY discord-bot/requirements.txt ./discord-bot/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r heroku-api/requirements.txt

# Copy application code
COPY . .

# Switch to non-root user
USER botuser

# Health check (FastAPI)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default: run FastAPI server
CMD ["granian", "heroku-api.main:app", "--interface", "asgi", "--host", "0.0.0.0", "--port", "8000"]