#!/usr/bin/env python3
"""Post tweets and threads to X."""

import argparse
import os
import sys
from pathlib import Path

import tweepy
from dotenv import load_dotenv

load_dotenv()


def get_client() -> tweepy.Client:
    """Get authenticated X API client."""
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
        bearer_token=os.environ.get("X_BEARER_TOKEN"),
    )


def get_api_v1() -> tweepy.API:
    """Get v1.1 API for media uploads."""
    auth = tweepy.OAuth1UserHandler(
        os.environ["X_API_KEY"],
        os.environ["X_API_SECRET"],
        os.environ["X_ACCESS_TOKEN"],
        os.environ["X_ACCESS_TOKEN_SECRET"],
    )
    return tweepy.API(auth)


def upload_media(filepath: str) -> str:
    """Upload media and return media_id."""
    api = get_api_v1()
    media = api.media_upload(filepath)
    return media.media_id_string


def create_tweet(
    text: str,
    reply_to: str | None = None,
    media_ids: list[str] | None = None,
) -> dict:
    """Create a single tweet."""
    client = get_client()
    
    kwargs = {"text": text}
    if reply_to:
        kwargs["in_reply_to_tweet_id"] = reply_to
    if media_ids:
        kwargs["media_ids"] = media_ids
    
    response = client.create_tweet(**kwargs)
    return {
        "id": response.data["id"],
        "text": response.data["text"],
    }


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


def main():
    parser = argparse.ArgumentParser(description="Post to X")
    parser.add_argument("text", nargs="*", help="Tweet text(s)")
    parser.add_argument("--thread", action="store_true", help="Post as thread")
    parser.add_argument("--media", type=str, help="Path to media file")
    parser.add_argument("--reply-to", type=str, help="Tweet ID to reply to")
    
    args = parser.parse_args()
    
    if not args.text:
        parser.print_help()
        sys.exit(1)
    
    try:
        media_ids = None
        if args.media:
            if not Path(args.media).exists():
                print(f"Media file not found: {args.media}")
                sys.exit(1)
            media_id = upload_media(args.media)
            media_ids = [media_id]
            print(f"Uploaded media: {media_id}")
        
        if args.thread or len(args.text) > 1:
            results = create_thread(args.text)
            print(f"\nThread posted: {len(results)} tweets")
            print(f"First tweet: https://x.com/i/status/{results[0]['id']}")
        else:
            tweet = create_tweet(
                args.text[0],
                reply_to=args.reply_to,
                media_ids=media_ids,
            )
            print(f"Posted: https://x.com/i/status/{tweet['id']}")
    
    except tweepy.TweepyException as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
