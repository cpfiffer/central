"""
Publish a blog post to GreenGale on ATProtocol.

Usage:
    uv run python .skills/publishing-to-greengale/scripts/publish.py \
        --title "Post Title" --rkey "url-slug" --file content.md
    
    uv run python .skills/publishing-to-greengale/scripts/publish.py \
        --title "Post Title" --rkey "url-slug" --content "# Inline markdown"
"""

import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
HANDLE = os.getenv("ATPROTO_HANDLE")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

VALID_THEMES = [
    "github-light", "github-dark", "dracula", "nord",
    "solarized-light", "solarized-dark", "monokai",
]


async def publish(
    title: str,
    rkey: str,
    content: str,
    subtitle: str = None,
    theme: str = "github-dark",
    visibility: str = "public",
):
    async with httpx.AsyncClient() as client:
        # Authenticate
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.server.createSession",
            json={"identifier": HANDLE, "password": APP_PASSWORD},
        )
        if resp.status_code != 200:
            print(f"Auth failed: {resp.text}", file=sys.stderr)
            sys.exit(1)
        token = resp.json()["accessJwt"]

        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        record = {
            "$type": "app.greengale.document",
            "content": content[:100000],
            "url": "https://greengale.app",
            "path": f"/{HANDLE}/{rkey}",
            "title": title[:1000],
            "publishedAt": now,
            "visibility": visibility,
            "theme": {"preset": theme},
        }

        if subtitle:
            record["subtitle"] = subtitle[:1000]

        # Use putRecord so we can update existing posts
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.repo.putRecord",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo": DID,
                "collection": "app.greengale.document",
                "rkey": rkey,
                "record": record,
            },
        )

        if resp.status_code == 200:
            uri = resp.json()["uri"]
            url = f"https://greengale.app/{HANDLE}/{rkey}"
            print(f"Published: {uri}")
            print(f"View at: {url}")
        else:
            print(f"Error: {resp.status_code} {resp.text}", file=sys.stderr)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Publish to GreenGale")
    parser.add_argument("--title", required=True, help="Post title")
    parser.add_argument("--rkey", required=True, help="URL slug (record key)")
    parser.add_argument("--file", help="Path to markdown file")
    parser.add_argument("--content", help="Inline markdown content")
    parser.add_argument("--subtitle", help="Optional subtitle")
    parser.add_argument(
        "--theme", default="github-dark", choices=VALID_THEMES,
        help="Theme preset (default: github-dark)",
    )
    parser.add_argument(
        "--visibility", default="public", choices=["public", "url", "author"],
        help="Visibility (default: public)",
    )

    args = parser.parse_args()

    if args.file:
        content = Path(args.file).read_text()
    elif args.content:
        content = args.content
    else:
        print("Error: provide --file or --content", file=sys.stderr)
        sys.exit(1)

    asyncio.run(publish(
        title=args.title,
        rkey=args.rkey,
        content=content,
        subtitle=args.subtitle,
        theme=args.theme,
        visibility=args.visibility,
    ))


if __name__ == "__main__":
    main()
