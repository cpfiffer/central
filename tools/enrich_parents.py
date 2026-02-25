"""Enrich exported void posts with parent post context.

Reads void-raw.jsonl, fetches the parent post for each reply,
and writes enriched JSONL with parent_text and parent_author.

Uses the public API (no auth needed) and batches requests.

Usage:
    uv run python tools/enrich_parents.py data/void-raw.jsonl -o data/void-enriched.jsonl
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx


def get_post_record(uri: str, client: httpx.Client) -> dict | None:
    """Fetch a single post record from the public API."""
    try:
        # Parse AT URI: at://did/collection/rkey
        parts = uri.replace("at://", "").split("/")
        if len(parts) < 3:
            return None
        did, collection, rkey = parts[0], parts[1], parts[2]

        resp = client.get(
            "https://public.api.bsky.app/xrpc/com.atproto.repo.getRecord",
            params={"repo": did, "collection": collection, "rkey": rkey},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def get_thread(uri: str, client: httpx.Client) -> dict | None:
    """Fetch thread context (faster, gets parent in one call)."""
    try:
        resp = client.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread",
            params={"uri": uri, "depth": 0, "parentHeight": 1},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        return resp.json()
    except Exception:
        return None


def extract_parent_from_thread(thread_data: dict) -> tuple[str, str] | None:
    """Extract parent text and author from thread response."""
    thread = thread_data.get("thread", {})
    parent = thread.get("parent", {})
    if not parent:
        return None

    post = parent.get("post", {})
    record = post.get("record", {})
    author = post.get("author", {})

    text = record.get("text", "")
    handle = author.get("handle", "unknown")

    if not text:
        return None
    return text, handle


def main():
    parser = argparse.ArgumentParser(description="Enrich void posts with parent context")
    parser.add_argument("input", help="Input JSONL (from export_resilient.py)")
    parser.add_argument("-o", "--output", required=True, help="Output enriched JSONL")
    parser.add_argument("--delay", type=float, default=0.1, help="Delay between API calls")
    parser.add_argument("--limit", type=int, default=0, help="Max records to process (0=all)")

    args = parser.parse_args()

    # Count replies
    total = 0
    replies = 0
    with open(args.input) as f:
        for line in f:
            total += 1
            if json.loads(line).get("is_reply"):
                replies += 1
    print(f"Total records: {total:,}", file=sys.stderr)
    print(f"Replies needing parents: {replies:,}", file=sys.stderr)

    # Process
    enriched = 0
    failed = 0
    written = 0

    with httpx.Client() as client, open(args.input) as f, open(args.output, "w") as out:
        for i, line in enumerate(f):
            if args.limit and written >= args.limit:
                break

            record = json.loads(line)

            if not record.get("is_reply"):
                # Non-reply: write as-is
                out.write(line)
                written += 1
                continue

            # Fetch parent via thread API
            uri = record["id"]
            thread = get_thread(uri, client)

            if thread:
                result = extract_parent_from_thread(thread)
                if result:
                    parent_text, parent_author = result
                    record["parent_text"] = parent_text
                    record["parent_author"] = parent_author
                    enriched += 1
                else:
                    failed += 1
            else:
                failed += 1

            out.write(json.dumps(record) + "\n")
            written += 1

            if written % 500 == 0:
                print(
                    f"  {written:,} written, {enriched:,} enriched, {failed:,} failed",
                    file=sys.stderr,
                )

            time.sleep(args.delay)

    print(f"\nDone: {written:,} records, {enriched:,} enriched, {failed:,} failed", file=sys.stderr)


if __name__ == "__main__":
    main()
