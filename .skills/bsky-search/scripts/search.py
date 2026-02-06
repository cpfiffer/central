#!/usr/bin/env python3
"""
Bluesky Search - Search posts and users on the AT Protocol network.

No authentication required. Uses the public Bluesky API.

Usage:
  python search.py posts "query"           # Search posts
  python search.py users "query"           # Search users
  python search.py feed @handle            # Get user's recent posts
  python search.py thread at://did/...     # View a post thread
  python search.py profile @handle         # Get user profile
  python search.py resolve @handle         # Resolve handle to DID

Examples:
  python search.py posts "AI agents ATProtocol"
  python search.py users "comind"
  python search.py feed @void.comind.network
  python search.py profile @cameron.stream
"""

import sys
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

API = "https://public.api.bsky.app"


def get(endpoint: str, params: dict) -> dict | None:
    """Make a GET request to the Bluesky public API."""
    query = urllib.parse.urlencode(params)
    url = f"{API}/xrpc/{endpoint}?{query}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.reason}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def fmt_time(ts: str) -> str:
    """Format ISO timestamp."""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except:
        return ts


def fmt_post(post: dict) -> str:
    """Format a post for display."""
    author = post.get("author", {})
    record = post.get("record", {})
    handle = author.get("handle", "?")
    text = record.get("text", "")
    created = fmt_time(record.get("createdAt", ""))
    likes = post.get("likeCount", 0)
    replies = post.get("replyCount", 0)
    uri = post.get("uri", "")
    return f"@{handle} ({created})\n{text}\n[{replies} replies, {likes} likes] {uri}\n"


def search_posts(query: str, limit: int = 10):
    """Search posts by text."""
    data = get("app.bsky.feed.searchPosts", {"q": query, "limit": limit})
    if not data:
        return
    posts = data.get("posts", [])
    print(f"Found {len(posts)} posts for '{query}':\n")
    for i, post in enumerate(posts, 1):
        print(f"[{i}] {fmt_post(post)}")


def search_users(query: str, limit: int = 10):
    """Search users by name or handle."""
    data = get("app.bsky.actor.searchActors", {"q": query, "limit": limit})
    if not data:
        return
    actors = data.get("actors", [])
    print(f"Found {len(actors)} users for '{query}':\n")
    for actor in actors:
        handle = actor.get("handle", "?")
        name = actor.get("displayName", "")
        desc = (actor.get("description", "") or "")[:100]
        followers = actor.get("followersCount", 0)
        did = actor.get("did", "")
        print(f"@{handle} - {name}")
        print(f"  {desc}")
        print(f"  {followers} followers | {did}")
        print()


def get_feed(actor: str, limit: int = 10):
    """Get a user's recent posts."""
    data = get("app.bsky.feed.getAuthorFeed", {"actor": actor, "limit": limit})
    if not data:
        return
    feed = data.get("feed", [])
    print(f"Recent posts by {actor} ({len(feed)} posts):\n")
    for i, item in enumerate(feed, 1):
        post = item.get("post", {})
        reason = item.get("reason")
        if reason and reason.get("$type") == "app.bsky.feed.defs#reasonRepost":
            by = reason.get("by", {}).get("handle", "?")
            print(f"[{i}] (repost by @{by})")
        else:
            print(f"[{i}] {fmt_post(post)}")


def get_thread(uri: str, depth: int = 6):
    """View a post thread."""
    data = get("app.bsky.feed.getPostThread", {"uri": uri, "depth": depth})
    if not data:
        return
    thread = data.get("thread", {})

    # Show parent chain
    parent = thread.get("parent")
    if parent and parent.get("post"):
        print("--- Parent ---")
        print(fmt_post(parent["post"]))

    # Main post
    print("--- Main Post ---")
    if thread.get("post"):
        print(fmt_post(thread["post"]))

    # Replies
    replies = thread.get("replies", [])
    if replies:
        print(f"--- Replies ({len(replies)}) ---")
        for r in replies[:10]:
            if r.get("post"):
                print(f"  {fmt_post(r['post'])}")


def get_profile(actor: str):
    """Get user profile details."""
    data = get("app.bsky.actor.getProfile", {"actor": actor})
    if not data:
        return
    print(f"Handle:      @{data.get('handle', '?')}")
    print(f"Name:        {data.get('displayName', '')}")
    print(f"DID:         {data.get('did', '')}")
    print(f"Description: {data.get('description', '')}")
    print(f"Followers:   {data.get('followersCount', 0)}")
    print(f"Following:   {data.get('followsCount', 0)}")
    print(f"Posts:        {data.get('postsCount', 0)}")
    created = data.get("createdAt", "")
    if created:
        print(f"Created:     {fmt_time(created)}")


def resolve_handle(handle: str):
    """Resolve a handle to a DID."""
    data = get("com.atproto.identity.resolveHandle", {"handle": handle})
    if not data:
        return
    print(data.get("did", "Not found"))


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    arg = " ".join(sys.argv[2:])

    if cmd == "posts":
        search_posts(arg)
    elif cmd == "users":
        search_users(arg)
    elif cmd == "feed":
        get_feed(arg)
    elif cmd == "thread":
        get_thread(arg)
    elif cmd == "profile":
        get_profile(arg)
    elif cmd == "resolve":
        resolve_handle(arg.lstrip("@"))
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
