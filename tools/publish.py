"""
Publish cognition records from YAML to ATProtocol.

Inspired by void's inbox/outbox pattern, adapted for comind cognition records.

Usage:
    uv run python -m tools.publish records.yaml          # Publish records
    uv run python -m tools.publish records.yaml --dry-run # Preview without publishing
    uv run python -m tools.publish records.yaml --validate # Validate only
"""

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

console = Console()

# Load environment
load_dotenv(Path(__file__).parent.parent / ".env")

import os

PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")
HANDLE = os.getenv("ATPROTO_HANDLE")

# Archive directory for published records
ARCHIVE_DIR = Path(__file__).parent.parent / "archive"


# =============================================================================
# Lexicon Schemas (extracted from central/lexicons/)
# =============================================================================

LEXICONS = {
    "network.comind.concept": {
        "required": ["concept", "createdAt"],
        "properties": {
            "concept": {"type": "string", "max_length": 200},
            "understanding": {"type": "string", "max_length": 50000},
            "confidence": {"type": "integer", "min": 0, "max": 100},
            "sources": {"type": "array", "max_items": 50},
            "related": {"type": "array", "max_items": 50},
            "tags": {"type": "array", "max_items": 20},
            "createdAt": {"type": "datetime"},
            "updatedAt": {"type": "datetime"},
        },
        "key_type": "slug",  # Use slugified concept name as rkey
    },
    "network.comind.thought": {
        "required": ["thought", "createdAt"],
        "properties": {
            "thought": {"type": "string", "max_length": 50000},
            "type": {"type": "string"},
            "context": {"type": "string", "max_length": 5000},
            "related": {"type": "array", "max_items": 50},
            "outcome": {"type": "string", "max_length": 5000},
            "tags": {"type": "array", "max_items": 20},
            "createdAt": {"type": "datetime"},
        },
        "key_type": "tid",  # Use TID (timestamp-based ID)
    },
    "network.comind.memory": {
        "required": ["content", "createdAt"],
        "properties": {
            "content": {"type": "string", "max_length": 50000},
            "type": {"type": "string"},
            "actors": {"type": "array", "max_items": 50},
            "context": {"type": "string", "max_length": 5000},
            "related": {"type": "array", "max_items": 50},
            "source": {"type": "string"},
            "tags": {"type": "array", "max_items": 20},
            "createdAt": {"type": "datetime"},
        },
        "key_type": "tid",
    },
    "network.comind.claim": {
        "required": ["claim", "confidence", "status", "createdAt", "updatedAt"],
        "properties": {
            "claim": {"type": "string", "max_length": 5000},
            "confidence": {"type": "integer", "min": 0, "max": 100},
            "domain": {"type": "string", "max_length": 100},
            "evidence": {"type": "array", "max_items": 20},
            "status": {"type": "string"},
            "createdAt": {"type": "datetime"},
            "updatedAt": {"type": "datetime"},
        },
        "key_type": "tid",
    },
    "network.comind.hypothesis": {
        "required": ["hypothesis", "confidence", "status", "createdAt", "updatedAt"],
        "properties": {
            "hypothesis": {"type": "string"},
            "confidence": {"type": "integer", "min": 0, "max": 100},
            "status": {"type": "string"},
            "evidence": {"type": "array"},
            "contradictions": {"type": "array"},
            "createdAt": {"type": "datetime"},
            "updatedAt": {"type": "datetime"},
        },
        "key_type": "tid",
    },
    "network.comind.observation": {
        "required": ["content", "createdAt"],
        "properties": {
            "content": {"type": "string", "max_length": 50000},
            "type": {"type": "string"},
            "context": {"type": "string", "max_length": 5000},
            "tags": {"type": "array", "max_items": 20},
            "createdAt": {"type": "datetime"},
        },
        "key_type": "tid",
    },
    "network.comind.devlog": {
        "required": ["content", "createdAt"],
        "properties": {
            "content": {"type": "string", "max_length": 50000},
            "type": {"type": "string"},
            "tags": {"type": "array", "max_items": 20},
            "createdAt": {"type": "datetime"},
        },
        "key_type": "tid",
    },
}


# =============================================================================
# Validation
# =============================================================================


def slugify(text: str) -> str:
    """Convert text to a valid rkey slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:50]


def generate_tid() -> str:
    """Generate a TID (timestamp-based ID)."""
    # Simplified TID: just use timestamp in nanoseconds
    now = datetime.now(timezone.utc)
    # Format: YYYYMMDDHHMMSSMIC (microseconds)
    return now.strftime("%Y%m%d%H%M%S%f")


def validate_record(action: dict) -> tuple[bool, list[str]]:
    """
    Validate a record against its lexicon schema.

    Returns (is_valid, list_of_errors).
    """
    errors = []

    # Support both $type and type for record type
    record_type = action.get("$type") or action.get("type")
    if not record_type:
        return False, ["Missing '$type' or 'type' field"]

    if record_type not in LEXICONS:
        return False, [f"Unknown record type: {record_type}"]

    schema = LEXICONS[record_type]

    # Check required fields
    for field in schema["required"]:
        if field not in action:
            errors.append(f"Missing required field: {field}")

    # Validate field types and constraints
    props = schema["properties"]
    for field, value in action.items():
        if field in ("$type", "type", "annotation"):
            continue  # Meta fields, not part of record

        if field not in props:
            # Allow unknown fields (extensibility)
            continue

        prop_schema = props[field]

        # Type validation
        if prop_schema["type"] == "string":
            if not isinstance(value, str):
                errors.append(f"Field '{field}' must be a string")
            elif "max_length" in prop_schema and len(value) > prop_schema["max_length"]:
                errors.append(
                    f"Field '{field}' exceeds max length ({len(value)} > {prop_schema['max_length']})"
                )

        elif prop_schema["type"] == "integer":
            if not isinstance(value, int):
                errors.append(f"Field '{field}' must be an integer")
            elif "min" in prop_schema and value < prop_schema["min"]:
                errors.append(
                    f"Field '{field}' below minimum ({value} < {prop_schema['min']})"
                )
            elif "max" in prop_schema and value > prop_schema["max"]:
                errors.append(
                    f"Field '{field}' exceeds maximum ({value} > {prop_schema['max']})"
                )

        elif prop_schema["type"] == "array":
            if not isinstance(value, list):
                errors.append(f"Field '{field}' must be an array")
            elif "max_items" in prop_schema and len(value) > prop_schema["max_items"]:
                errors.append(
                    f"Field '{field}' has too many items ({len(value)} > {prop_schema['max_items']})"
                )

        elif prop_schema["type"] == "datetime":
            # Accept string or generate if missing
            if not isinstance(value, str):
                errors.append(f"Field '{field}' must be a datetime string")

    return len(errors) == 0, errors


# =============================================================================
# Publishing
# =============================================================================


async def get_auth_token() -> str:
    """Get authentication token from PDS."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.server.createSession",
            json={"identifier": HANDLE, "password": APP_PASSWORD},
        )
        if resp.status_code != 200:
            raise Exception(f"Auth failed: {resp.text}")
        return resp.json()["accessJwt"]


async def publish_record(
    action: dict, token: str, dry_run: bool = False
) -> dict | None:
    """
    Publish a single record to ATProtocol.

    Returns the result dict or None if skipped.
    """
    # Support both $type and type for record type
    record_type = action.get("$type") or action.get("type")
    schema = LEXICONS[record_type]

    # Build the record
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    record = {"$type": record_type}

    # Copy fields from action to record
    for field, value in action.items():
        if field in ("$type", "type", "annotation"):
            continue
        record[field] = value

    # Add timestamps if not present
    if "createdAt" not in record:
        record["createdAt"] = now
    if "updatedAt" not in record and record_type == "network.comind.concept":
        record["updatedAt"] = now

    # Determine rkey
    if schema["key_type"] == "slug":
        rkey = slugify(action.get("concept", generate_tid()))
    else:
        rkey = generate_tid()

    if dry_run:
        console.print(f"[cyan]DRY RUN:[/cyan] Would publish to {record_type}")
        console.print(f"  rkey: {rkey}")
        console.print(f"  record: {json.dumps(record, indent=2)[:200]}...")
        return {"uri": f"dry-run://{record_type}/{rkey}", "dry_run": True}

    # Actually publish
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {token}"},
            json={"repo": DID, "collection": record_type, "rkey": rkey, "record": record},
        )

        if resp.status_code != 200:
            raise Exception(f"Failed to create record: {resp.text}")

        result = resp.json()
        console.print(f"[green]Published:[/green] {result['uri']}")
        return result


async def publish_from_yaml(
    yaml_path: Path, dry_run: bool = False, validate_only: bool = False
) -> tuple[int, int]:
    """
    Publish records from a YAML file.

    Returns (success_count, error_count).
    """
    if not yaml_path.exists():
        console.print(f"[red]File not found: {yaml_path}[/red]")
        return 0, 0

    with open(yaml_path) as f:
        data = yaml.safe_load(f)

    if not data:
        console.print("[yellow]Empty YAML file[/yellow]")
        return 0, 0

    # Handle both list and dict with 'actions' key
    actions = data if isinstance(data, list) else data.get("actions", [])

    if not actions:
        console.print("[yellow]No actions found in YAML[/yellow]")
        return 0, 0

    console.print(f"[bold]Processing {len(actions)} actions...[/bold]\n")

    # Validate all actions first
    valid_actions = []
    for i, action in enumerate(actions):
        is_valid, errors = validate_record(action)
        if is_valid:
            valid_actions.append(action)
        else:
            console.print(f"[red]Invalid action {i}:[/red]")
            for err in errors:
                console.print(f"  - {err}")

    if not valid_actions:
        console.print("[red]No valid actions to publish[/red]")
        return 0, len(actions)

    if validate_only:
        console.print(f"[green]Validated {len(valid_actions)}/{len(actions)} actions[/green]")
        return len(valid_actions), len(actions) - len(valid_actions)

    # Get auth token
    token = await get_auth_token()

    # Publish
    success = 0
    errors = 0
    published = []

    for action in valid_actions:
        try:
            result = await publish_record(action, token, dry_run)
            if result:
                published.append(
                    {
                        "uri": result.get("uri"),
                        "type": action.get("type"),
                        "annotation": action.get("annotation"),
                    }
                )
                success += 1
        except Exception as e:
            console.print(f"[red]Error publishing: {e}[/red]")
            errors += 1

    # Archive published records
    if published and not dry_run:
        archive_published(published)

    console.print(f"\n[bold]Done:[/bold] {success} published, {errors} errors")
    return success, errors


def archive_published(published: list[dict]):
    """Archive published records with timestamp."""
    ARCHIVE_DIR.mkdir(exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    archive_file = ARCHIVE_DIR / f"{timestamp}_published.yaml"

    with open(archive_file, "w") as f:
        yaml.dump({"published_at": timestamp, "records": published}, f)

    console.print(f"[dim]Archived to {archive_file}[/dim]")


# =============================================================================
# CLI
# =============================================================================


def main():
    parser = argparse.ArgumentParser(description="Publish cognition records from YAML")
    parser.add_argument("yaml_file", help="Path to YAML file with records")
    parser.add_argument("--dry-run", action="store_true", help="Preview without publishing")
    parser.add_argument("--validate", action="store_true", help="Validate only, don't publish")

    args = parser.parse_args()

    success, errors = asyncio.run(
        publish_from_yaml(
            Path(args.yaml_file), dry_run=args.dry_run, validate_only=args.validate
        )
    )

    sys.exit(0 if errors == 0 else 1)


if __name__ == "__main__":
    main()
