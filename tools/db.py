"""
SQLite database layer for central's operational state.

Consolidates:
- published_messages.txt -> published_messages table
- concepts.json -> concepts table
- social_graph.json -> social_nodes table
- liked.json -> likes table
- metrics.jsonl -> metrics table
- consent.json -> consent table
"""

import sqlite3
import json
from pathlib import Path
from contextlib import contextmanager
from typing import Optional, List, Dict, Any
from datetime import datetime

# Database location
DB_PATH = Path(__file__).parent.parent / "data" / "central.db"

# Schema definition
SCHEMA = """
-- Dedup tracking (replaces published_messages.txt)
CREATE TABLE IF NOT EXISTS published_messages (
    id TEXT PRIMARY KEY,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON published_messages(timestamp);

-- Concepts (replaces concepts.json)
CREATE TABLE IF NOT EXISTS concepts (
    slug TEXT PRIMARY KEY,
    confidence INTEGER,
    tags TEXT,
    summary TEXT,
    updated TEXT
);

-- Social graph nodes (replaces social_graph.json)
CREATE TABLE IF NOT EXISTS social_nodes (
    handle TEXT PRIMARY KEY,
    did TEXT,
    display_name TEXT,
    first_seen TEXT,
    relationship TEXT,
    interactions INTEGER DEFAULT 0
);

-- Likes (replaces liked.json and liked_posts.txt)
CREATE TABLE IF NOT EXISTS likes (
    uri TEXT PRIMARY KEY,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Metrics (replaces metrics.jsonl)
CREATE TABLE IF NOT EXISTS metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    data TEXT
);

-- Consent (replaces consent.json)
CREATE TABLE IF NOT EXISTS consent (
    handle TEXT PRIMARY KEY,
    opted_in INTEGER DEFAULT 0,
    timestamp TEXT
);
"""


def init_db():
    """Initialize database with schema."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(SCHEMA)
    print(f"Database initialized at {DB_PATH}")


@contextmanager
def get_connection():
    """Get a database connection with context management."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# --- Published Messages (dedup) ---

def is_message_published(message_id: str) -> bool:
    """Check if a message has been published."""
    with get_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM published_messages WHERE id = ?",
            (message_id,)
        ).fetchone()
        return result is not None


def mark_message_published(message_id: str) -> None:
    """Mark a message as published."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO published_messages (id) VALUES (?)",
            (message_id,)
        )


def get_published_count() -> int:
    """Get count of published messages."""
    with get_connection() as conn:
        result = conn.execute("SELECT COUNT(*) FROM published_messages").fetchone()
        return result[0]


# --- Concepts ---

def get_concept(slug: str) -> Optional[Dict[str, Any]]:
    """Get a concept by slug."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM concepts WHERE slug = ?",
            (slug,)
        ).fetchone()
        if row:
            return {
                "slug": row["slug"],
                "confidence": row["confidence"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "summary": row["summary"],
                "updated": row["updated"]
            }
        return None


def upsert_concept(slug: str, confidence: int, tags: List[str], summary: str) -> None:
    """Insert or update a concept."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO concepts (slug, confidence, tags, summary, updated)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                confidence = excluded.confidence,
                tags = excluded.tags,
                summary = excluded.summary,
                updated = excluded.updated
        """, (slug, confidence, json.dumps(tags), summary, datetime.utcnow().isoformat()))


def list_concepts() -> List[Dict[str, Any]]:
    """List all concepts."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM concepts ORDER BY slug").fetchall()
        return [
            {
                "slug": row["slug"],
                "confidence": row["confidence"],
                "tags": json.loads(row["tags"]) if row["tags"] else [],
                "summary": row["summary"],
                "updated": row["updated"]
            }
            for row in rows
        ]


# --- Social Graph ---

def get_social_node(handle: str) -> Optional[Dict[str, Any]]:
    """Get a social graph node by handle."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM social_nodes WHERE handle = ?",
            (handle,)
        ).fetchone()
        if row:
            return {
                "handle": row["handle"],
                "did": row["did"],
                "display_name": row["display_name"],
                "first_seen": row["first_seen"],
                "relationship": json.loads(row["relationship"]) if row["relationship"] else [],
                "interactions": row["interactions"]
            }
        return None


def upsert_social_node(
    handle: str,
    did: str,
    display_name: str,
    relationship: List[str],
    interactions: int = 0
) -> None:
    """Insert or update a social graph node."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO social_nodes (handle, did, display_name, first_seen, relationship, interactions)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
                did = excluded.did,
                display_name = excluded.display_name,
                relationship = excluded.relationship,
                interactions = excluded.interactions
        """, (handle, did, display_name, datetime.utcnow().isoformat(), json.dumps(relationship), interactions))


def increment_interactions(handle: str) -> None:
    """Increment interaction count for a handle."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE social_nodes SET interactions = interactions + 1 WHERE handle = ?",
            (handle,)
        )


def list_social_nodes() -> List[Dict[str, Any]]:
    """List all social graph nodes."""
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM social_nodes ORDER BY interactions DESC").fetchall()
        return [
            {
                "handle": row["handle"],
                "did": row["did"],
                "display_name": row["display_name"],
                "first_seen": row["first_seen"],
                "relationship": json.loads(row["relationship"]) if row["relationship"] else [],
                "interactions": row["interactions"]
            }
            for row in rows
        ]


# --- Likes ---

def is_liked(uri: str) -> bool:
    """Check if a URI has been liked."""
    with get_connection() as conn:
        result = conn.execute(
            "SELECT 1 FROM likes WHERE uri = ?",
            (uri,)
        ).fetchone()
        return result is not None


def add_like(uri: str) -> None:
    """Record a like."""
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO likes (uri) VALUES (?)",
            (uri,)
        )


def list_likes() -> List[str]:
    """List all liked URIs."""
    with get_connection() as conn:
        rows = conn.execute("SELECT uri FROM likes").fetchall()
        return [row["uri"] for row in rows]


# --- Metrics ---

def record_metric(data: Dict[str, Any]) -> None:
    """Record a metric."""
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO metrics (data) VALUES (?)",
            (json.dumps(data),)
        )


def get_recent_metrics(limit: int = 100) -> List[Dict[str, Any]]:
    """Get recent metrics."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM metrics ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [
            {
                "id": row["id"],
                "timestamp": row["timestamp"],
                "data": json.loads(row["data"]) if row["data"] else {}
            }
            for row in rows
        ]


# --- Consent ---

def is_opted_in(handle: str) -> bool:
    """Check if a handle has opted in."""
    with get_connection() as conn:
        result = conn.execute(
            "SELECT opted_in FROM consent WHERE handle = ?",
            (handle,)
        ).fetchone()
        return result is not None and result["opted_in"] == 1


def set_consent(handle: str, opted_in: bool) -> None:
    """Set consent for a handle."""
    with get_connection() as conn:
        conn.execute("""
            INSERT INTO consent (handle, opted_in, timestamp)
            VALUES (?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET
                opted_in = excluded.opted_in,
                timestamp = excluded.timestamp
        """, (handle, 1 if opted_in else 0, datetime.utcnow().isoformat()))


# --- CLI ---

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m tools.db <command>")
        print("Commands: init, stats")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == "init":
        init_db()
    elif cmd == "stats":
        init_db()  # Ensure DB exists
        print(f"Published messages: {get_published_count()}")
        print(f"Concepts: {len(list_concepts())}")
        print(f"Social nodes: {len(list_social_nodes())}")
        print(f"Likes: {len(list_likes())}")
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
