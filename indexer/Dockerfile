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

# Print a startup message
RUN echo 'echo "Hello from comind!"' > /startup.sh && chmod +x /startup.sh

# Default to running the web server - use PORT env var for Railway
CMD sh -c "/startup.sh && gunicorn --bind 0.0.0.0:\${PORT:-8080} --workers 2 --timeout 120 indexer.app:app"
