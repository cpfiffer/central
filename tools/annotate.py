#!/usr/bin/env python3
"""
Agent Annotation Tool

Write W3C Web Annotations to ATProtocol using the at.margin.annotation lexicon.
Enables Central to attach observations to specific web content.

Usage:
  uv run python -m tools.annotate "https://example.com" "My observation about this page"
  uv run python -m tools.annotate "https://example.com" "Note about this quote" --quote "exact text from page"
  uv run python -m tools.annotate --list                # List recent annotations
"""

import asyncio
import hashlib
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")
HANDLE = "central.comind.network"

COLLECTION = "at.margin.annotation"


async def get_session() -> dict:
    """Authenticate and get session."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.server.createSession",
            json={"identifier": HANDLE, "password": APP_PASSWORD},
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_page_title(url: str) -> Optional[str]:
    """Fetch page title for annotation target."""
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10) as client:
            resp = await client.get(url, headers={"User-Agent": "Central/1.0 (ATProto agent)"})
            if resp.status_code == 200:
                text = resp.text
                start = text.find("<title>")
                end = text.find("</title>")
                if start != -1 and end != -1:
                    return text[start + 7:end].strip()
    except Exception:
        pass
    return None


async def annotate(url: str, body: str, quote: Optional[str] = None, motivation: str = "commenting") -> str:
    """Write an annotation record to ATProtocol."""
    session = await get_session()
    headers = {"Authorization": f"Bearer {session['accessJwt']}"}

    # Build target
    source_hash = hashlib.sha256(url.encode()).hexdigest()
    title = await fetch_page_title(url)

    selector = None
    if quote:
        selector = {
            "type": "TextQuoteSelector",
            "exact": quote,
        }

    target = {
        "source": url,
        "sourceHash": source_hash,
        "title": title,
        "selector": selector,
    }

    record = {
        "$type": COLLECTION,
        "body": {
            "format": "text/plain",
            "value": body,
        },
        "motivation": motivation,
        "target": target,
        "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers=headers,
            json={
                "repo": DID,
                "collection": COLLECTION,
                "record": record,
            },
        )
        resp.raise_for_status()
        result = resp.json()
        return result["uri"]


async def list_annotations(limit: int = 10):
    """List recent annotations."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={"repo": DID, "collection": COLLECTION, "limit": limit},
        )
        if resp.status_code != 200:
            print(f"Error: {resp.status_code}")
            return

        records = resp.json().get("records", [])
        if not records:
            print("No annotations yet.")
            return

        for rec in records:
            val = rec.get("value", {})
            target = val.get("target", {})
            body = val.get("body", {}).get("value", "")
            source = target.get("source", "?")
            title = target.get("title", "")
            quote = target.get("selector", {})
            exact = quote.get("exact", "") if quote else ""
            created = val.get("createdAt", "")

            print(f"[{created}] {source}")
            if title:
                print(f"  Title: {title}")
            if exact:
                print(f"  Quote: \"{exact[:100]}\"")
            print(f"  Note: {body}")
            print(f"  URI: {rec['uri']}")
            print()


def main():
    args = sys.argv[1:]

    if not args or args[0] == "--help":
        print(__doc__)
        return

    if args[0] == "--list":
        limit = int(args[1]) if len(args) > 1 else 10
        asyncio.run(list_annotations(limit))
        return

    if len(args) < 2:
        print("Usage: annotate <url> <body> [--quote <text>] [--motivation <type>]")
        return

    url = args[0]
    body = args[1]
    quote = None
    motivation = "commenting"

    i = 2
    while i < len(args):
        if args[i] == "--quote" and i + 1 < len(args):
            quote = args[i + 1]
            i += 2
        elif args[i] == "--motivation" and i + 1 < len(args):
            motivation = args[i + 1]
            i += 2
        else:
            i += 1

    uri = asyncio.run(annotate(url, body, quote=quote, motivation=motivation))
    print(f"Annotated: {uri}")
    print(f"  URL: {url}")
    print(f"  Body: {body}")
    if quote:
        print(f"  Quote: \"{quote}\"")


if __name__ == "__main__":
    main()
