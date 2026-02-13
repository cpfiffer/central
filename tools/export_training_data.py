"""Export agent posts as fine-tuning training data.

Paginates through an agent's posts on ATProtocol, fetches parent
context for replies, and outputs structured JSONL suitable for
fine-tuning open models.

Usage:
    uv run python tools/export_training_data.py void.comind.network \
        --output data/void-training.jsonl \
        --collections app.bsky.feed.post stream.thought.reasoning \
        --limit 0

Output format (one JSON object per line):
    {
        "id": "at://did:plc:.../app.bsky.feed.post/...",
        "collection": "app.bsky.feed.post",
        "created_at": "2026-01-15T...",
        "text": "void's response text",
        "parent_text": "the post void replied to (if reply)",
        "parent_author": "user.bsky.social",
        "root_text": "thread root (if different from parent)",
        "root_author": "root.bsky.social",
        "is_reply": true
    }
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

PUBLIC_API = "https://public.api.bsky.app"


def resolve_handle(handle: str) -> str:
    """Resolve a handle to a DID."""
    resp = httpx.get(
        f"{PUBLIC_API}/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["did"]


def get_pds(did: str) -> str:
    """Get the PDS URL for a DID."""
    resp = httpx.get(
        f"https://plc.directory/{did}",
        timeout=15,
    )
    resp.raise_for_status()
    doc = resp.json()
    for service in doc.get("service", []):
        if service.get("id") == "#atproto_pds":
            return service["serviceEndpoint"]
    raise ValueError(f"No PDS found for {did}")


def fetch_post(uri: str) -> dict | None:
    """Fetch a single post by AT URI via the public API."""
    try:
        resp = httpx.get(
            f"{PUBLIC_API}/xrpc/app.bsky.feed.getPostThread",
            params={"uri": uri, "depth": 0, "parentHeight": 0},
            timeout=15,
        )
        if resp.status_code != 200:
            return None
        thread = resp.json().get("thread", {})
        post = thread.get("post", {})
        record = post.get("record", {})
        author = post.get("author", {})
        return {
            "text": record.get("text", ""),
            "author": author.get("handle", author.get("did", "")),
            "created_at": record.get("createdAt", ""),
        }
    except Exception:
        return None


def paginate_records(pds: str, did: str, collection: str, limit: int = 0):
    """Paginate through all records in a collection.

    Args:
        limit: Max records to fetch. 0 = all.

    Yields (uri, record) tuples.
    """
    cursor = None
    fetched = 0
    page_size = 100

    while True:
        params = {
            "repo": did,
            "collection": collection,
            "limit": page_size,
        }
        if cursor:
            params["cursor"] = cursor

        try:
            resp = httpx.get(
                f"{pds}/xrpc/com.atproto.repo.listRecords",
                params=params,
                timeout=30,
            )
            resp.raise_for_status()
        except Exception as e:
            print(f"  Error fetching page: {e}", file=sys.stderr)
            break

        data = resp.json()
        records = data.get("records", [])

        if not records:
            break

        for record in records:
            yield record["uri"], record.get("value", {})
            fetched += 1
            if limit > 0 and fetched >= limit:
                return

        cursor = data.get("cursor")
        if not cursor:
            break

        # Rate limiting
        time.sleep(0.1)


def extract_post_data(uri: str, record: dict) -> dict:
    """Extract training-relevant data from a post record."""
    reply = record.get("reply", {})
    parent_uri = reply.get("parent", {}).get("uri")
    root_uri = reply.get("root", {}).get("uri")

    result = {
        "id": uri,
        "collection": uri.split("/")[3] if len(uri.split("/")) > 3 else "unknown",
        "created_at": record.get("createdAt", ""),
        "text": record.get("text", ""),
        "is_reply": parent_uri is not None,
        "parent_uri": parent_uri,
        "parent_text": None,
        "parent_author": None,
        "root_uri": root_uri,
        "root_text": None,
        "root_author": None,
    }

    return result


def extract_cognition_data(uri: str, record: dict, collection: str) -> dict:
    """Extract training data from stream.thought.* records."""
    # Different collections have different shapes
    text = ""
    if "text" in record:
        text = record["text"]
    elif "content" in record:
        text = record["content"]
    elif "entry" in record:
        text = record["entry"]
    elif "reasoning" in record:
        text = record["reasoning"]
    elif "body" in record:
        text = record["body"]
    else:
        # Dump the whole record as text
        text = json.dumps(record, default=str)

    return {
        "id": uri,
        "collection": collection,
        "created_at": record.get("createdAt", record.get("timestamp", "")),
        "text": text,
        "is_reply": False,
        "parent_uri": None,
        "parent_text": None,
        "parent_author": None,
        "root_uri": None,
        "root_text": None,
        "root_author": None,
    }


def enrich_with_parents(records: list[dict], batch_size: int = 10) -> list[dict]:
    """Fetch parent/root posts for reply records."""
    # Collect unique URIs to fetch
    uris_to_fetch = set()
    for r in records:
        if r.get("parent_uri"):
            uris_to_fetch.add(r["parent_uri"])
        if r.get("root_uri") and r["root_uri"] != r.get("parent_uri"):
            uris_to_fetch.add(r["root_uri"])

    if not uris_to_fetch:
        return records

    print(f"  Fetching {len(uris_to_fetch)} parent/root posts...", file=sys.stderr)

    # Fetch all unique posts
    post_cache = {}
    for i, uri in enumerate(uris_to_fetch):
        post_data = fetch_post(uri)
        if post_data:
            post_cache[uri] = post_data
        if (i + 1) % 50 == 0:
            print(f"    {i + 1}/{len(uris_to_fetch)} fetched", file=sys.stderr)
        time.sleep(0.05)  # Rate limit

    # Enrich records
    for r in records:
        if r.get("parent_uri") and r["parent_uri"] in post_cache:
            parent = post_cache[r["parent_uri"]]
            r["parent_text"] = parent["text"]
            r["parent_author"] = parent["author"]
        if r.get("root_uri") and r["root_uri"] in post_cache:
            root = post_cache[r["root_uri"]]
            r["root_text"] = root["text"]
            r["root_author"] = root["author"]

    return records


CHARACTER_CREATION_KEYWORDS = [
    "character sheet",
    "character creation",
    "ability score",
    "hit points",
    "armor class",
    "d20",
    "dungeon master",
    "saving throw",
    "spell slot",
    "initiative",
    "proficiency bonus",
]


def is_character_creation(text: str) -> bool:
    """Filter out void's character creation loop content."""
    text_lower = text.lower()
    matches = sum(1 for kw in CHARACTER_CREATION_KEYWORDS if kw in text_lower)
    return matches >= 2


def main():
    parser = argparse.ArgumentParser(description="Export agent training data")
    parser.add_argument("handle", help="Agent handle (e.g., void.comind.network)")
    parser.add_argument("--output", "-o", default="-", help="Output file (default: stdout)")
    parser.add_argument(
        "--collections",
        nargs="+",
        default=["app.bsky.feed.post"],
        help="Collections to export",
    )
    parser.add_argument("--limit", type=int, default=0, help="Max records per collection (0=all)")
    parser.add_argument("--skip-parents", action="store_true", help="Skip fetching parent posts")
    parser.add_argument("--filter-chars", action="store_true", help="Filter character creation content")

    args = parser.parse_args()

    # Resolve identity
    print(f"Resolving {args.handle}...", file=sys.stderr)
    did = resolve_handle(args.handle)
    pds = get_pds(did)
    print(f"  DID: {did}", file=sys.stderr)
    print(f"  PDS: {pds}", file=sys.stderr)

    all_records = []

    for collection in args.collections:
        print(f"\nExporting {collection}...", file=sys.stderr)
        batch = []
        count = 0

        for uri, record in paginate_records(pds, did, collection, limit=args.limit):
            if collection == "app.bsky.feed.post":
                data = extract_post_data(uri, record)
            else:
                data = extract_cognition_data(uri, record, collection)

            # Filter
            if args.filter_chars and is_character_creation(data.get("text", "")):
                continue

            batch.append(data)
            count += 1

            if count % 500 == 0:
                print(f"  {count} records...", file=sys.stderr)

        print(f"  {count} records exported", file=sys.stderr)

        # Enrich posts with parent context
        if not args.skip_parents and collection == "app.bsky.feed.post":
            reply_records = [r for r in batch if r["is_reply"]]
            if reply_records:
                batch_replies = enrich_with_parents(reply_records)
                # Merge back
                reply_map = {r["id"]: r for r in batch_replies}
                batch = [reply_map.get(r["id"], r) for r in batch]

        all_records.extend(batch)

    # Write output
    print(f"\nTotal: {len(all_records)} records", file=sys.stderr)

    out = sys.stdout if args.output == "-" else open(args.output, "w")
    for record in all_records:
        # Clean up internal fields
        record.pop("parent_uri", None)
        record.pop("root_uri", None)
        out.write(json.dumps(record, default=str) + "\n")

    if args.output != "-":
        out.close()
        print(f"Written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
