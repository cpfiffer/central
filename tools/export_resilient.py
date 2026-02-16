"""Resilient PDS exporter that handles flaky connections.

Writes each page immediately, saves cursor state, and can resume
from where it left off if the process dies.

Usage:
    uv run python tools/export_resilient.py void.comind.network \
        -o data/void-raw.jsonl \
        --collection app.bsky.feed.post
"""

import argparse
import json
import sys
import time
from pathlib import Path

import httpx


def resolve_handle(handle: str) -> str:
    resp = httpx.get(
        "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
        params={"handle": handle},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["did"]


def get_pds(did: str) -> str:
    resp = httpx.get(f"https://plc.directory/{did}", timeout=15)
    resp.raise_for_status()
    doc = resp.json()
    for service in doc.get("service", []):
        if service.get("id") == "#atproto_pds":
            return service["serviceEndpoint"]
    raise ValueError(f"No PDS for {did}")


def fetch_page(pds: str, did: str, collection: str, cursor: str | None, page_size: int = 100) -> tuple[list, str | None]:
    """Fetch one page. Fresh connection each time."""
    params = {"repo": did, "collection": collection, "limit": page_size}
    if cursor:
        params["cursor"] = cursor

    for attempt in range(5):
        try:
            # New client per request (no connection reuse)
            with httpx.Client(timeout=60) as client:
                resp = client.get(f"{pds}/xrpc/com.atproto.repo.listRecords", params=params)
                resp.raise_for_status()
                data = resp.json()
                return data.get("records", []), data.get("cursor")
        except Exception as e:
            wait = 2 ** (attempt + 1)
            print(f"  Attempt {attempt + 1}/5 failed: {e}. Waiting {wait}s...", file=sys.stderr)
            time.sleep(wait)

    return [], None


def main():
    parser = argparse.ArgumentParser(description="Resilient PDS exporter")
    parser.add_argument("handle", help="Agent handle")
    parser.add_argument("-o", "--output", required=True, help="Output JSONL file")
    parser.add_argument("--collection", default="app.bsky.feed.post")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between pages")

    args = parser.parse_args()

    # State file for resume
    state_file = Path(args.output + ".cursor")

    print(f"Resolving {args.handle}...", file=sys.stderr)
    did = resolve_handle(args.handle)
    pds = get_pds(did)
    print(f"  DID: {did}", file=sys.stderr)
    print(f"  PDS: {pds}", file=sys.stderr)

    # Resume from cursor if state file exists
    cursor = None
    if state_file.exists():
        cursor = state_file.read_text().strip()
        existing = sum(1 for _ in open(args.output)) if Path(args.output).exists() else 0
        print(f"  Resuming from cursor (have {existing} records)", file=sys.stderr)

    total = 0
    with open(args.output, "a") as out:
        while True:
            records, next_cursor = fetch_page(pds, did, args.collection, cursor)

            if not records:
                break

            for record in records:
                uri = record["uri"]
                value = record.get("value", {})
                reply = value.get("reply", {})
                parent_uri = reply.get("parent", {}).get("uri")

                data = {
                    "id": uri,
                    "collection": args.collection,
                    "created_at": value.get("createdAt", ""),
                    "text": value.get("text", ""),
                    "is_reply": parent_uri is not None,
                }
                out.write(json.dumps(data) + "\n")
                total += 1

            out.flush()

            # Save cursor for resume
            if next_cursor:
                state_file.write_text(next_cursor)

            cursor = next_cursor
            if not cursor:
                break

            if total % 500 == 0:
                print(f"  {total} records...", file=sys.stderr)

            # Breathing room
            time.sleep(args.delay)

    # Clean up state file
    if state_file.exists():
        state_file.unlink()

    print(f"\nDone: {total} records written to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
