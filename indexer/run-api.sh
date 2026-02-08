#!/bin/bash
# Load environment variables
export $(grep -E '^(DATABASE_URL|OPENAI_API_KEY)=' /home/cameron/central/.env | xargs)

cd /home/cameron/central/indexer
exec uv run gunicorn --bind 0.0.0.0:8787 --workers 2 --timeout 120 indexer.app:app
