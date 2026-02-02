---
name: deploying-to-railway
description: Deploy Python services to Railway with PostgreSQL/pgvector. Use when deploying web services, workers, or databases. Covers CLI workflow, variable linking, and multi-service patterns.
---

# Deploying to Railway

Guide for deploying Python services to Railway.

## Prerequisites

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login
```

## Basic Workflow

### 1. Link Project
```bash
cd /path/to/service
railway link
# Select workspace and project (or create new)
```

### 2. Add PostgreSQL (if needed)
```bash
railway add
# Select: Database → Postgres
```

**IMPORTANT:** Standard Postgres does NOT have pgvector. For vector search:
- Delete standard Postgres
- Add service from template: https://railway.com/deploy/pgvector-latest

### 3. Set Environment Variables
```bash
railway variables set KEY="value"

# Reference another service's variable:
railway variables set 'DATABASE_URL=${{Postgres.DATABASE_URL}}'
railway variables set 'DATABASE_URL=${{pgvector.DATABASE_URL}}'
```

### 4. Deploy
```bash
railway up --detach
```

### 5. Get Domain
```bash
railway domain
# Returns: https://service-production.up.railway.app
```

## Multi-Service Pattern (API + Worker)

### Deploy API Service
```bash
railway link  # Link to main service
railway up --detach
```

### Add Worker Service
```bash
railway add --service worker
railway service link worker
railway variables set 'DATABASE_URL=${{pgvector.DATABASE_URL}}'
railway variables set OPENAI_API_KEY="$OPENAI_API_KEY"
# Set start command in dashboard or railway.toml
railway up --detach
```

## Gotchas

1. **pgvector not available** - Use pgvector template, not standard Postgres
2. **Interactive prompts** - Some commands need interactive mode (run manually)
3. **Variable references** - Use `${{ServiceName.VARIABLE}}` syntax
4. **Dockerfile required** - For custom Python services, include Dockerfile
5. **Procfile** - Railway can use Procfile for multi-process apps

## Useful Commands

```bash
railway status          # Current project/service
railway variables       # List environment variables
railway logs            # View service logs
railway service status  # Deployment status
railway redeploy --yes  # Force redeploy
```

## Example Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY myapp/ ./myapp/

RUN pip install --no-cache-dir .

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "myapp.app:app"]
```
