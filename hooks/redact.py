"""
Shared secret redaction for all hooks that publish content.

Import and use: from redact import redact

Add new patterns here when new secrets are introduced.
"""

import re
import os

# Static patterns - regex-based detection
REDACT_PATTERNS = [
    # API keys (generic)
    (r'[A-Za-z_]*API_KEY[=:\s]+\S+', '[REDACTED_KEY]'),
    (r'[A-Za-z_]*PASSWORD[=:\s]+\S+', '[REDACTED]'),
    (r'[A-Za-z_]*SECRET[=:\s]+\S+', '[REDACTED]'),
    (r'[A-Za-z_]*TOKEN[=:\s]+\S+', '[REDACTED]'),
    # Bearer tokens
    (r'Bearer\s+\S+', 'Bearer [REDACTED]'),
    # OpenAI keys
    (r'sk-proj-[A-Za-z0-9_-]+', '[REDACTED_OPENAI]'),
    (r'sk-[A-Za-z0-9]{20,}', '[REDACTED_SK]'),
    # Letta API keys
    (r'sk-let-[A-Za-z0-9=]+', '[REDACTED_LETTA]'),
    # GitHub tokens
    (r'ghp_[A-Za-z0-9]+', '[REDACTED_GH]'),
    # Fly.io tokens
    (r'FlyV1\s+\S+', '[REDACTED_FLY]'),
    (r'fo1_[A-Za-z0-9]+', '[REDACTED_FLY]'),
    # Postgres connection strings (Neon, Railway, any)
    (r'postgres(?:ql)?://[^\s"\'`]+', '[REDACTED_DB_URL]'),
    # Generic connection strings with passwords
    (r'://[^:]+:[^@]+@[^\s"\'`]+', '[REDACTED_CONN]'),
    # ATProto app passwords (xxxx-xxxx-xxxx-xxxx format)
    (r'[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}', '[REDACTED_APP_PWD]'),
    # Base64-encoded secrets (long base64 after = or : that looks like a key)
    (r'(?:KEY|SECRET|TOKEN|PASSWORD)[=:\s]+[A-Za-z0-9+/]{40,}={0,2}', '[REDACTED_B64]'),
]

# Dynamic patterns - built from actual env var values at import time
_LITERAL_SECRETS: list[str] = []


def _load_env_secrets():
    """Load actual secret values from environment for literal matching."""
    global _LITERAL_SECRETS
    secret_env_vars = [
        "OPENAI_API_KEY",
        "LETTA_API_KEY",
        "ATPROTO_APP_PASSWORD",
        "DATABASE_URL",
        "FLY_API_TOKEN",
        "X_API_KEY",
        "X_API_SECRET",
        "X_ACCESS_TOKEN",
        "X_ACCESS_SECRET",
        "X_BEARER_TOKEN",
    ]
    # Also load from .env file if available
    env_path = "/home/cameron/central/.env"
    env_values = {}
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env_values[key.strip()] = val.strip()
    except FileNotFoundError:
        pass

    for var in secret_env_vars:
        val = os.environ.get(var) or env_values.get(var)
        if val and len(val) > 8:  # Skip very short values
            _LITERAL_SECRETS.append(val)

    # Also grab the Neon password substring if DATABASE_URL is set
    db_url = os.environ.get("DATABASE_URL") or env_values.get("DATABASE_URL", "")
    if ":" in db_url and "@" in db_url:
        try:
            # Extract password from postgres://user:password@host/db
            after_proto = db_url.split("://", 1)[1]
            userpass = after_proto.split("@", 1)[0]
            if ":" in userpass:
                password = userpass.split(":", 1)[1]
                if password and len(password) > 4:
                    _LITERAL_SECRETS.append(password)
        except (IndexError, ValueError):
            pass


# Load on import
_load_env_secrets()


def redact(text: str) -> str:
    """
    Redact potential secrets from text.

    Two-layer approach:
    1. Regex patterns catch structured secrets (API keys, URLs, tokens)
    2. Literal matching catches actual env var values even if unstructured
    """
    if not text:
        return text

    # Layer 1: Regex patterns
    for pattern, replacement in REDACT_PATTERNS:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    # Layer 2: Literal secret values from environment
    for secret in _LITERAL_SECRETS:
        if secret in text:
            text = text.replace(secret, "[REDACTED_ENV]")

    return text
