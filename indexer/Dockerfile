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

# Default to running the web server
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "indexer.app:app"]
