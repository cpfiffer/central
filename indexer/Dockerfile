FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY indexer/ ./indexer/
COPY lexicons/ ./lexicons/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Ensure output is unbuffered for logging
ENV PYTHONUNBUFFERED=1

# Default to running the web server - use PORT env var for Railway
CMD echo "Starting comind indexer on port ${PORT:-8080}..." && \
    gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --timeout 120 --access-logfile - --error-logfile - indexer.app:app
