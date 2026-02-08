"""
Shared secret redaction for all hooks that publish content.

Import and use: from redact import redact

Strategy: redact ALL env var values and ALL .env values by default.
Only system vars with non-secret values are excluded (PATH, HOME, etc.).
This means new secrets are automatically caught without code changes.
"""

import re
import os

# Static patterns - regex-based detection (layer 1)
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

# Env var keys that are NOT secrets. Values too common/short to redact safely.
# Everything else gets redacted.
SAFE_ENV_KEYS = {
    # System/shell
    "PATH", "HOME", "USER", "SHELL", "TERM", "LANG", "LC_ALL", "LC_CTYPE",
    "HOSTNAME", "LOGNAME", "PWD", "OLDPWD", "SHLVL", "EDITOR", "VISUAL",
    "COLORTERM", "TERM_PROGRAM", "TERM_PROGRAM_VERSION",
    # XDG
    "XDG_RUNTIME_DIR", "XDG_DATA_DIRS", "XDG_CONFIG_DIRS", "XDG_CONFIG_HOME",
    "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME", "XDG_SESSION_TYPE",
    "XDG_SESSION_CLASS", "XDG_SESSION_ID", "XDG_SEAT",
    # Display/desktop
    "DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS",
    "DESKTOP_SESSION", "GDMSESSION", "SESSION_MANAGER",
    # Python/node/dev tools (paths, not secrets)
    "PYTHONPATH", "PYTHONDONTWRITEBYTECODE", "PYTHONUNBUFFERED",
    "VIRTUAL_ENV", "CONDA_DEFAULT_ENV", "CONDA_PREFIX",
    "NODE_PATH", "NVM_DIR", "NVM_BIN", "NVM_INC",
    "npm_config_prefix", "npm_config_cache",
    # Locale/timezone
    "TZ", "LANGUAGE",
    # CI/build (non-secret)
    "CI", "GITHUB_ACTIONS", "GITHUB_REPOSITORY", "GITHUB_REF",
    # Misc non-secret
    "LS_COLORS", "LESSOPEN", "LESSCLOSE", "MAIL", "MOTD_SHOWN",
    "SSH_AUTH_SOCK", "SSH_AGENT_PID", "GPG_AGENT_INFO",
    "_", "WINDOWID",
    # Fly.io non-secret
    "FLY_APP_NAME", "FLY_REGION", "FLY_ALLOC_ID", "PORT",
    # Letta non-secret
    "LETTA_AGENT_ID",
}

# Minimum value length to redact (avoids false positives on "1", "true", etc.)
MIN_SECRET_LEN = 8

# Dynamic secrets - built from ALL env vars and .env at import time
_LITERAL_SECRETS: list[str] = []


def _load_all_secrets():
    """
    Load values from ALL env vars and .env file, except safe keys.
    We never inspect the values. We just store them for literal matching.
    """
    global _LITERAL_SECRETS
    secrets = set()

    # Layer A: All current environment variables
    for key, val in os.environ.items():
        if key in SAFE_ENV_KEYS:
            continue
        if val and len(val) >= MIN_SECRET_LEN:
            secrets.add(val)

    # Layer B: All .env file values
    env_path = "/home/cameron/central/.env"
    try:
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    key = key.strip()
                    val = val.strip()
                    if key in SAFE_ENV_KEYS:
                        continue
                    if val and len(val) >= MIN_SECRET_LEN:
                        secrets.add(val)
    except FileNotFoundError:
        pass

    # Layer C: Extract embedded passwords from connection strings
    for val in list(secrets):
        if "://" in val and "@" in val:
            try:
                after_proto = val.split("://", 1)[1]
                userpass = after_proto.split("@", 1)[0]
                if ":" in userpass:
                    password = userpass.split(":", 1)[1]
                    if password and len(password) >= 4:
                        secrets.add(password)
            except (IndexError, ValueError):
                pass

    # Sort longest first so longer secrets get replaced before substrings
    _LITERAL_SECRETS = sorted(secrets, key=len, reverse=True)


# Load on import
_load_all_secrets()


def redact(text: str) -> str:
    """
    Redact potential secrets from text.

    Two-layer approach:
    1. Regex patterns catch structured secrets (API keys, URLs, tokens)
    2. Literal matching catches ALL env var values (except safe system vars)
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
