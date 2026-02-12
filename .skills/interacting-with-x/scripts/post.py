#!/usr/bin/env python3
"""Post tweets and threads to X.

Uses requests_oauthlib instead of tweepy for posting (tweepy returns
403 on free tier even when the API accepts the request directly).
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

load_dotenv()

API_BASE = "https://api.twitter.com/2"


def get_auth() -> OAuth1:
    """Get OAuth1 auth for X API."""
    return OAuth1(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def upload_media(image_path: str) -> str:
    """Upload an image and return the media_id string."""
    auth = get_auth()
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://upload.twitter.com/1.1/media/upload.json",
            files={"media": f},
            auth=auth,
        )
    if resp.status_code not in (200, 201):
        print(f"Media upload error: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)
    return resp.json()["media_id_string"]


def create_tweet(
    text: str,
    reply_to: str | None = None,
    media_ids: list[str] | None = None,
) -> dict:
    """Create a single tweet."""
    auth = get_auth()

    payload = {"text": text}
    if reply_to:
        payload["reply"] = {"in_reply_to_tweet_id": reply_to}
    if media_ids:
        payload["media"] = {"media_ids": media_ids}

    resp = requests.post(f"{API_BASE}/tweets", json=payload, auth=auth)
    if resp.status_code not in (200, 201):
        print(f"Error: {resp.status_code} {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()["data"]
    tweet_id = data["id"]

    # Verify reply threading if this was supposed to be a reply
    if reply_to:
        verify = requests.get(
            f"{API_BASE}/tweets/{tweet_id}",
            params={"tweet.fields": "conversation_id,referenced_tweets"},
            auth=auth,
        )
        if verify.status_code == 200:
            vdata = verify.json().get("data", {})
            refs = vdata.get("referenced_tweets", [])
            is_reply = any(r.get("type") == "replied_to" for r in refs) if refs else False
            if not is_reply:
                print(f"WARNING: Tweet {tweet_id} posted but NOT threaded as reply to {reply_to}", file=sys.stderr)

    return {
        "id": tweet_id,
        "text": data["text"],
    }


def split_text(text: str, limit: int = 270) -> list[str]:
    """Split text into tweet-sized chunks, breaking at sentence boundaries."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        # Find last sentence break within limit
        cut = limit
        for sep in ["\n\n", ". ", ".\n", "\n", ", ", " "]:
            idx = remaining[:limit].rfind(sep)
            if idx > limit // 3:  # Don't cut too early
                cut = idx + len(sep)
                break

        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    return chunks


def create_thread(texts: list[str]) -> list[dict]:
    """Create a thread of tweets."""
    results = []
    reply_to = None

    for text in texts:
        tweet = create_tweet(text, reply_to=reply_to)
        results.append(tweet)
        reply_to = tweet["id"]
        print(f"Posted: {tweet['id']}")

    return results


def delete_tweet(tweet_id: str) -> bool:
    """Delete a tweet by ID."""
    auth = get_auth()
    resp = requests.delete(f"{API_BASE}/tweets/{tweet_id}", auth=auth)
    return resp.status_code == 200


def main():
    parser = argparse.ArgumentParser(description="Post to X")
    parser.add_argument("text", nargs="*", help="Tweet text(s)")
    parser.add_argument("--thread", action="store_true", help="Post as thread (auto-splits long text)")
    parser.add_argument("--reply-to", type=str, help="Tweet ID to reply to")
    parser.add_argument("--delete", type=str, help="Delete tweet by ID")
    parser.add_argument("--image", type=str, help="Path to image to attach")

    args = parser.parse_args()

    if args.delete:
        if delete_tweet(args.delete):
            print(f"Deleted: {args.delete}")
        else:
            print(f"Failed to delete: {args.delete}")
            sys.exit(1)
        return

    if not args.text:
        parser.print_help()
        sys.exit(1)

    # Upload image if provided
    media_ids = None
    if args.image:
        mid = upload_media(args.image)
        media_ids = [mid]
        print(f"Uploaded media: {mid}")

    if args.thread or len(args.text) > 1:
        # Multiple args = explicit thread parts. Single arg = auto-split.
        if len(args.text) == 1:
            texts = split_text(args.text[0])
        else:
            texts = args.text

        if args.reply_to:
            # First tweet is a reply, rest are self-replies
            first = create_tweet(texts[0], reply_to=args.reply_to)
            results = [first]
            for t in texts[1:]:
                tweet = create_tweet(t, reply_to=results[-1]["id"])
                results.append(tweet)
                print(f"Posted: {tweet['id']}")
        else:
            results = create_thread(texts)

        print(f"\nThread posted: {len(results)} tweets")
        print(f"First tweet: https://x.com/central_agi/status/{results[0]['id']}")
    else:
        # Single tweet - auto-split into thread if too long
        texts = split_text(args.text[0])
        if len(texts) > 1:
            results = create_thread(texts)
            print(f"\nAuto-threaded: {len(results)} tweets")
            print(f"First tweet: https://x.com/central_agi/status/{results[0]['id']}")
        else:
            tweet = create_tweet(
                args.text[0],
                reply_to=args.reply_to,
                media_ids=media_ids,
            )
            print(f"Posted: https://x.com/central_agi/status/{tweet['id']}")


if __name__ == "__main__":
    main()
