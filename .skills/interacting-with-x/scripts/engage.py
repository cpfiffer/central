#!/usr/bin/env python3
"""Engage on X - like, retweet, follow, unfollow."""

import argparse
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


def like_tweet(tweet_id: str) -> bool:
    """Like a tweet."""
    client = get_client()
    response = client.like(tweet_id)
    return response.data.get("liked", False)


def unlike_tweet(tweet_id: str) -> bool:
    """Unlike a tweet."""
    client = get_client()
    response = client.unlike(tweet_id)
    return not response.data.get("liked", True)


def retweet(tweet_id: str) -> bool:
    """Retweet a tweet."""
    client = get_client()
    response = client.retweet(tweet_id)
    return response.data.get("retweeted", False)


def unretweet(tweet_id: str) -> bool:
    """Remove retweet."""
    client = get_client()
    response = client.unretweet(tweet_id)
    return not response.data.get("retweeted", True)


def follow_user(username: str) -> bool:
    """Follow a user by username."""
    client = get_client()
    
    # Get user ID from username
    user = client.get_user(username=username)
    if not user.data:
        raise ValueError(f"User not found: {username}")
    
    response = client.follow_user(user.data.id)
    return response.data.get("following", False)


def unfollow_user(username: str) -> bool:
    """Unfollow a user by username."""
    client = get_client()
    
    user = client.get_user(username=username)
    if not user.data:
        raise ValueError(f"User not found: {username}")
    
    response = client.unfollow_user(user.data.id)
    return not response.data.get("following", True)


def main():
    parser = argparse.ArgumentParser(description="Engage on X")
    parser.add_argument(
        "action",
        choices=["like", "unlike", "retweet", "unretweet", "follow", "unfollow"],
        help="Action to perform",
    )
    parser.add_argument("target", help="Tweet ID or username")
    
    args = parser.parse_args()
    
    try:
        if args.action == "like":
            success = like_tweet(args.target)
            print(f"Liked: {success}")
        
        elif args.action == "unlike":
            success = unlike_tweet(args.target)
            print(f"Unliked: {success}")
        
        elif args.action == "retweet":
            success = retweet(args.target)
            print(f"Retweeted: {success}")
        
        elif args.action == "unretweet":
            success = unretweet(args.target)
            print(f"Unretweeted: {success}")
        
        elif args.action == "follow":
            success = follow_user(args.target)
            print(f"Following @{args.target}: {success}")
        
        elif args.action == "unfollow":
            success = unfollow_user(args.target)
            print(f"Unfollowed @{args.target}: {success}")
    
    except tweepy.TweepyException as e:
        print(f"Error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
