#!/usr/bin/env python3
"""Read from X - timeline, mentions, user tweets, search."""

import argparse
import json
import os
import sys

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


def format_tweet(tweet, include_user: bool = True) -> dict:
    """Format tweet for output."""
    result = {
        "id": tweet.id,
        "text": tweet.text,
        "created_at": str(tweet.created_at) if hasattr(tweet, "created_at") else None,
    }
    if include_user and hasattr(tweet, "author_id"):
        result["author_id"] = tweet.author_id
    return result


def get_timeline(limit: int = 10) -> list[dict]:
    """Get home timeline."""
    client = get_client()
    
    # Get authenticated user's ID
    me = client.get_me()
    
    # Reverse chronological home timeline
    response = client.get_home_timeline(
        max_results=min(limit, 100),
        tweet_fields=["created_at", "author_id"],
    )
    
    if not response.data:
        return []
    
    return [format_tweet(t) for t in response.data]


def get_mentions(limit: int = 10) -> list[dict]:
    """Get mentions of authenticated user."""
    client = get_client()
    me = client.get_me()
    
    response = client.get_users_mentions(
        me.data.id,
        max_results=min(limit, 100),
        tweet_fields=["created_at", "author_id"],
    )
    
    if not response.data:
        return []
    
    return [format_tweet(t) for t in response.data]


def get_user_tweets(username: str, limit: int = 10) -> list[dict]:
    """Get tweets from a specific user."""
    client = get_client()
    
    # Get user by username
    user = client.get_user(username=username)
    if not user.data:
        raise ValueError(f"User not found: {username}")
    
    response = client.get_users_tweets(
        user.data.id,
        max_results=min(limit, 100),
        tweet_fields=["created_at"],
    )
    
    if not response.data:
        return []
    
    return [format_tweet(t, include_user=False) for t in response.data]


def search_tweets(query: str, limit: int = 10) -> list[dict]:
    """Search recent tweets."""
    client = get_client()
    
    # X API requires min 10 for search
    api_limit = max(10, min(limit, 100))
    
    response = client.search_recent_tweets(
        query,
        max_results=api_limit,
        tweet_fields=["created_at", "author_id"],
    )
    
    if not response.data:
        return []
    
    return [format_tweet(t) for t in response.data]


def main():
    parser = argparse.ArgumentParser(description="Read from X")
    parser.add_argument(
        "command",
        choices=["timeline", "mentions", "user", "search"],
        help="What to read",
    )
    parser.add_argument("query", nargs="?", help="Username or search query")
    parser.add_argument("--limit", type=int, default=10, help="Max results")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    args = parser.parse_args()
    
    try:
        if args.command == "timeline":
            results = get_timeline(args.limit)
        elif args.command == "mentions":
            results = get_mentions(args.limit)
        elif args.command == "user":
            if not args.query:
                print("Username required for 'user' command")
                sys.exit(1)
            results = get_user_tweets(args.query, args.limit)
        elif args.command == "search":
            if not args.query:
                print("Query required for 'search' command")
                sys.exit(1)
            results = search_tweets(args.query, args.limit)
        
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for i, tweet in enumerate(results, 1):
                print(f"\n[{i}] {tweet['id']}")
                print(f"    {tweet['text'][:100]}{'...' if len(tweet['text']) > 100 else ''}")
                if tweet.get("created_at"):
                    print(f"    {tweet['created_at']}")
        
        print(f"\n{len(results)} results")
    
    except tweepy.TweepyException as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
