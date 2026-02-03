#!/usr/bin/env python3
"""
X Notification Responder

Fetches mentions from X, writes to queue for handler processing.
Similar to responder.py but for X platform.

Usage:
    uv run python -m tools.x_responder queue [--limit N]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import tweepy
import yaml
from dotenv import load_dotenv

load_dotenv()

# Known DIDs/IDs for priority
CAMERON_X_ID = "1904321638431387648"  # @cameron_pfiffer
CENTRAL_X_ID = "1904260683974578176"  # @central_agi

# Spam patterns to skip
SPAM_KEYWORDS = [
    "solana", "sol", "token", "bags", "pump", "memecoin",
    "claim", "airdrop", "free money", "100x", "moon",
]

QUEUE_PATH = Path("drafts/x_queue.yaml")
SENT_PATH = Path("drafts/x_sent.txt")
MENTIONS_LOG = Path("logs/x_mentions.jsonl")


def _log_mention(entry: dict):
    """Log a mention to x_mentions.jsonl for pulse tracking."""
    MENTIONS_LOG.parent.mkdir(exist_ok=True)
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "author": entry.get("author"),
        "text": entry.get("text", "")[:200],
        "id": entry.get("id"),
        "priority": entry.get("priority"),
    }
    with open(MENTIONS_LOG, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


def get_client() -> tweepy.Client:
    """Get authenticated X API client."""
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        bearer_token=os.environ.get("X_BEARER_TOKEN"),
    )


def is_spam(text: str) -> bool:
    """Check if tweet text contains spam patterns."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in SPAM_KEYWORDS)


def get_priority(author_id: str, text: str) -> str:
    """Determine priority for a mention."""
    if author_id == CAMERON_X_ID:
        return "CRITICAL"
    
    if is_spam(text):
        return "SKIP"
    
    # Questions get higher priority
    if "?" in text:
        return "HIGH"
    
    return "MEDIUM"


def load_sent_ids() -> set[str]:
    """Load IDs of tweets we've already replied to."""
    if not SENT_PATH.exists():
        return set()
    
    return set(SENT_PATH.read_text().strip().split("\n"))


def save_sent_id(tweet_id: str):
    """Mark a tweet ID as sent."""
    with open(SENT_PATH, "a") as f:
        f.write(f"{tweet_id}\n")


def fetch_mentions(limit: int = 20) -> list[dict]:
    """Fetch recent mentions."""
    client = get_client()
    me = client.get_me()
    
    response = client.get_users_mentions(
        me.data.id,
        max_results=min(limit, 100),
        tweet_fields=["created_at", "author_id", "conversation_id"],
        expansions=["author_id"],
    )
    
    if not response.data:
        return []
    
    # Build author lookup
    authors = {}
    if response.includes and "users" in response.includes:
        for user in response.includes["users"]:
            authors[user.id] = user.username
    
    mentions = []
    for tweet in response.data:
        mentions.append({
            "id": str(tweet.id),
            "text": tweet.text,
            "author_id": str(tweet.author_id),
            "author": authors.get(tweet.author_id, "unknown"),
            "created_at": str(tweet.created_at) if tweet.created_at else None,
            "conversation_id": str(tweet.conversation_id) if tweet.conversation_id else None,
        })
    
    return mentions


def queue_mentions(limit: int = 20):
    """Fetch mentions and write to queue."""
    print(f"Fetching X mentions...")
    
    mentions = fetch_mentions(limit)
    print(f"Found {len(mentions)} mentions")
    
    sent_ids = load_sent_ids()
    
    # Load existing queue
    existing_queue = []
    if QUEUE_PATH.exists():
        existing_queue = yaml.safe_load(QUEUE_PATH.read_text()) or []
    
    existing_ids = {item.get("id") for item in existing_queue}
    
    queued = 0
    for mention in mentions:
        # Skip if already in queue or sent
        if mention["id"] in existing_ids or mention["id"] in sent_ids:
            continue
        
        priority = get_priority(mention["author_id"], mention["text"])
        
        queue_item = {
            "priority": priority,
            "id": mention["id"],
            "author": mention["author"],
            "author_id": mention["author_id"],
            "text": mention["text"],
            "conversation_id": mention["conversation_id"],
            "action": "reply",
            "queued_at": datetime.now(timezone.utc).isoformat(),
        }
        
        existing_queue.append(queue_item)
        _log_mention(queue_item)  # Log for pulse tracking
        queued += 1
        
        if priority == "SKIP":
            print(f"  SKIP: @{mention['author']} (spam)")
        else:
            print(f"  {priority}: @{mention['author']}")
    
    # Write queue
    QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    QUEUE_PATH.write_text(yaml.dump(existing_queue, default_flow_style=False))
    
    print(f"\nQueued {queued} new mentions.")
    print(f"Total in queue: {len(existing_queue)}")


def main():
    parser = argparse.ArgumentParser(description="X Notification Responder")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Queue command
    queue_parser = subparsers.add_parser("queue", help="Fetch and queue mentions")
    queue_parser.add_argument("--limit", type=int, default=20, help="Max mentions to fetch")
    
    args = parser.parse_args()
    
    if args.command == "queue":
        queue_mentions(args.limit)


if __name__ == "__main__":
    main()
