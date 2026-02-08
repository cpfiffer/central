#!/bin/bash
# Load environment variables
export $(grep -E '^(DATABASE_URL|OPENAI_API_KEY)=' /home/cameron/central/.env | xargs)

cd /home/cameron/central/indexer
exec uv run python -m indexer.worker
