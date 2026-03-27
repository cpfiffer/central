"""
Live Responder - Unified notification handler for Central.

Bluesky: Real-time via Jetstream (WebSocket)
X: Polling every 5 minutes

On mention: invoke Central via Letta API, post reply directly. No drafts.

Usage:
    uv run python -m tools.live_responder              # Run both platforms
    uv run python -m tools.live_responder --bluesky     # Bluesky only
    uv run python -m tools.live_responder --x           # X only
    uv run python -m tools.live_responder --dry-run     # Show what would happen
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import time
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
import websocket
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("live")

# --- Config ---

CENTRAL_AGENT_ID = "agent-c770d1c8-510e-4414-be36-c9ebd95a7758"
CENTRAL_DID = "did:plc:l46arqe6yfgh36h3o554iyvr"
CENTRAL_HANDLE = "central.comind.network"
CAMERON_DID = "did:plc:gfrmhdmjvxn2sjedzboeudef"

LETTA_BASE = "https://api.letta.com/v1"
JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe"

SENT_FILE = Path(__file__).parent.parent / "data" / "live_sent.txt"
X_CURSOR_FILE = Path(__file__).parent.parent / "data" / "x_last_seen_id.txt"

# Our own agents: never respond (loop avoidance)
SKIP_DIDS = {
    CENTRAL_DID,                                        # central
    "did:plc:4pz3ltlcbpnfpda3scrqirx2",               # void
    "did:plc:uz2snz44gi4zgqdwecavi66r",               # herald
    "did:plc:ogruxay3tt7wycqxnf5lis6s",               # grunk
    "did:plc:onfljgawqhqrz3dki5j6jh3m",               # archivist
}

# Rate limit: minimum seconds between responses per platform
RATE_LIMIT_SECONDS = 30
_last_response_time = {"bluesky": 0.0, "x": 0.0}

PROJECT_DIR = Path(__file__).parent.parent
INDEXER_URL = "https://comind-indexer.fly.dev/xrpc"


# --- Sent tracking ---

def load_sent() -> set:
    if SENT_FILE.exists():
        return set(SENT_FILE.read_text().strip().split("\n"))
    return set()


def save_sent(uri: str):
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SENT_FILE, "a") as f:
        f.write(uri + "\n")


# --- Thread context ---

def fetch_thread_context(uri: str) -> str:
    """Fetch parent chain for a Bluesky post."""
    try:
        resp = httpx.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread",
            params={"uri": uri, "depth": 0, "parentHeight": 5},
            timeout=10,
        )
        if resp.status_code != 200:
            return ""

        thread = resp.json().get("thread", {})
        parts = []
        current = thread
        while current.get("parent"):
            current = current["parent"]
            post = current.get("post", {})
            author = post.get("author", {}).get("handle", "?")
            text = post.get("record", {}).get("text", "")
            if text:
                parts.append(f"@{author}: {text}")

        parts.reverse()
        return "\n".join(parts[-3:])
    except Exception as e:
        log.warning(f"Thread context fetch failed: {e}")
        return ""


# --- Context gathering ---

def gather_context(author: str, mention_text: str, platform: str) -> dict:
    """Gather context from indexer and profile before invoking Central."""
    ctx = {}

    # 1. Semantic search: what do we know about this topic?
    try:
        resp = httpx.get(
            f"{INDEXER_URL}/network.comind.search.query",
            params={"q": mention_text[:200], "limit": 3},
            timeout=5,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                ctx["relevant_records"] = [
                    f"[{r.get('collection', '?')}] {r.get('content', '')[:200]}"
                    for r in results
                    if r.get("content")
                ]
    except Exception as e:
        log.debug(f"Indexer search failed: {e}")

    # 2. Interaction history: have we talked to this person?
    try:
        resp = httpx.get(
            f"{INDEXER_URL}/network.comind.search.query",
            params={"q": f"@{author}", "limit": 3},
            timeout=5,
        )
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            if results:
                ctx["past_interactions"] = [
                    f"{r.get('createdAt', '?')[:10]}: {r.get('content', '')[:150]}"
                    for r in results
                    if r.get("content")
                ]
    except Exception as e:
        log.debug(f"Interaction history failed: {e}")

    # 3. Author profile (Bluesky only)
    if platform == "bluesky":
        try:
            resp = httpx.get(
                "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile",
                params={"actor": author},
                timeout=5,
            )
            if resp.status_code == 200:
                profile = resp.json()
                ctx["author_profile"] = {
                    "name": profile.get("displayName", ""),
                    "bio": (profile.get("description", "") or "")[:200],
                    "followers": profile.get("followersCount", 0),
                    "posts": profile.get("postsCount", 0),
                }
        except Exception as e:
            log.debug(f"Profile lookup failed: {e}")

    return ctx


# --- Letta API ---

def invoke_central(mention_text: str, author: str, platform: str, thread_context: str = "", ctx: dict | None = None) -> str | None:
    """Send mention to Central via Letta API, return response text."""
    key = os.environ.get("LETTA_API_KEY") or os.environ.get("CAMERON_LETTA_API_KEY")
    if not key:
        log.error("No LETTA_API_KEY set")
        return None

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    if ctx is None:
        ctx = {}

    parts = []
    parts.append(f"[Auto-responder] New {platform} mention from @{author}:")

    # Thread context FIRST - this frames the entire reply
    if thread_context:
        parts.append(f"Thread context:\n{thread_context}")

    parts.append(f'Their message: "{mention_text}"')

    # Author context
    if ctx.get("author_profile"):
        p = ctx["author_profile"]
        parts.append(f"Author: {p['name']} ({p['followers']} followers). Bio: {p['bio']}")

    # Past interactions
    if ctx.get("past_interactions"):
        parts.append("Previous interactions:\n" + "\n".join(ctx["past_interactions"]))

    # Relevant cognition records
    if ctx.get("relevant_records"):
        parts.append("Relevant from your memory:\n" + "\n".join(ctx["relevant_records"]))

    parts.append(
        "Write a reply to their message. Under 280 chars. "
        "Your reply MUST respond to what they said in context of the thread above. "
        "Be direct, specific, technical. "
        "Just the reply text, nothing else. If this doesn't warrant a response, reply with exactly: [SKIP]"
    )

    prompt = "\n\n".join(parts)

    try:
        resp = httpx.post(
            f"{LETTA_BASE}/agents/{CENTRAL_AGENT_ID}/messages",
            headers=headers,
            json={
                "messages": [{"role": "user", "content": prompt}],
                "stream_tokens": False,
            },
            timeout=120,
        )
        resp.raise_for_status()
        messages = resp.json().get("messages", [])

        for msg in messages:
            if msg.get("message_type") in ("assistant_message", "assistant"):
                content = msg.get("content", "")
                if content and content.strip() != "[SKIP]":
                    return content.strip()
                elif content and content.strip() == "[SKIP]":
                    log.info(f"Central chose to skip @{author}")
                    return None

        log.warning("No assistant message in response")
        return None

    except Exception as e:
        log.error(f"Letta API error: {e}")
        return None


# --- Posting ---

def post_bluesky_reply(text: str, reply_to_uri: str) -> bool:
    """Post a reply to Bluesky using thread.py."""
    try:
        result = subprocess.run(
            ["/home/cameron/.local/bin/uv", "run", "python", "tools/thread.py", text, "--reply-to", reply_to_uri],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_DIR),
        )
        if result.returncode == 0:
            log.info(f"[bsky] Posted reply: {result.stdout.strip()[:100]}")
            return True
        else:
            log.error(f"[bsky] Post failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        log.error(f"[bsky] Post error: {e}")
        return False


def post_x_reply(text: str, reply_to_id: str) -> bool:
    """Post a reply to X using post.py."""
    try:
        result = subprocess.run(
            ["/home/cameron/.local/bin/uv", "run", "python", ".skills/interacting-with-x/scripts/post.py",
             "--reply-to", reply_to_id, text],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_DIR),
        )
        if result.returncode == 0:
            log.info(f"[x] Posted reply: {result.stdout.strip()[:100]}")
            return True
        else:
            log.error(f"[x] Post failed: {result.stderr[:200]}")
            return False
    except Exception as e:
        log.error(f"[x] Post error: {e}")
        return False


# --- Core handler ---

def handle_mention(
    platform: str,
    text: str,
    author: str,
    uri_or_id: str,
    thread_context: str = "",
    dry_run: bool = False,
):
    """Handle a single mention: invoke Central, post reply."""
    # Rate limit
    now = time.time()
    elapsed = now - _last_response_time[platform]
    if elapsed < RATE_LIMIT_SECONDS:
        log.info(f"Rate limited ({elapsed:.0f}s < {RATE_LIMIT_SECONDS}s), skipping")
        return

    log.info(f"[{platform}] @{author}: {text[:80]}")

    if dry_run:
        log.info(f"[DRY RUN] Would invoke Central and reply on {platform}")
        return

    # Gather context from indexer + profile
    ctx = gather_context(author, text, platform)
    ctx_parts = []
    if ctx.get("author_profile"):
        ctx_parts.append("profile")
    if ctx.get("past_interactions"):
        ctx_parts.append(f"{len(ctx['past_interactions'])} interactions")
    if ctx.get("relevant_records"):
        ctx_parts.append(f"{len(ctx['relevant_records'])} records")
    if ctx_parts:
        log.info(f"[{platform}] Context: {', '.join(ctx_parts)}")

    # Invoke Central
    response = invoke_central(text, author, platform, thread_context, ctx)
    if not response:
        save_sent(uri_or_id)
        return

    log.info(f"[{platform}] Response: {response[:100]}")

    # Post reply
    success = False
    if platform == "bluesky":
        success = post_bluesky_reply(response, uri_or_id)
    elif platform == "x":
        success = post_x_reply(response, uri_or_id)

    if success:
        _last_response_time[platform] = time.time()

    save_sent(uri_or_id)


# --- Bluesky Jetstream ---

def run_bluesky_loop(dry_run: bool = False):
    """Connect to Jetstream and watch for @central mentions."""
    sent = load_sent()
    log.info(f"[bsky] Starting Jetstream listener ({len(sent)} already sent)")

    while True:
        try:
            url = f"{JETSTREAM_URL}?wantedCollections=app.bsky.feed.post"
            log.info(f"[bsky] Connecting to {url}")
            ws = websocket.create_connection(url, timeout=30)
            log.info("[bsky] Connected to Jetstream")

            while True:
                try:
                    data = ws.recv()
                    message = json.loads(data)

                    if message.get("kind") != "commit":
                        continue

                    commit = message.get("commit", {})
                    if commit.get("operation") != "create":
                        continue
                    if commit.get("collection") != "app.bsky.feed.post":
                        continue

                    did = message.get("did", "")
                    record = commit.get("record", {})
                    post_text = record.get("text", "")

                    # Check for our mention
                    if f"@{CENTRAL_HANDLE}" not in post_text:
                        continue

                    # Skip our own agents
                    if did in SKIP_DIDS:
                        continue

                    rkey = commit.get("rkey", "")
                    uri = f"at://{did}/app.bsky.feed.post/{rkey}"

                    # Dedup
                    if uri in sent:
                        continue

                    sent.add(uri)

                    # Get author handle
                    author = "unknown"
                    try:
                        resp = httpx.get(
                            f"https://plc.directory/{did}",
                            timeout=5,
                        )
                        if resp.status_code == 200:
                            for alias in resp.json().get("alsoKnownAs", []):
                                if alias.startswith("at://"):
                                    author = alias[5:]
                                    break
                    except Exception:
                        pass

                    # Fetch thread context
                    thread_ctx = fetch_thread_context(uri)

                    # Handle in background thread to not block Jetstream
                    t = threading.Thread(
                        target=handle_mention,
                        args=("bluesky", post_text, author, uri, thread_ctx, dry_run),
                        daemon=True,
                    )
                    t.start()

                except websocket.WebSocketTimeoutException:
                    ws.ping()
                    continue

        except websocket.WebSocketConnectionClosedException:
            log.warning("[bsky] WebSocket closed, reconnecting in 5s...")
            time.sleep(5)
        except Exception as e:
            log.error(f"[bsky] Error: {e}")
            time.sleep(10)


# --- X Polling ---

def run_x_loop(dry_run: bool = False, interval: int = 300):
    """Poll X mentions every `interval` seconds."""
    import requests as req
    try:
        from requests_oauthlib import OAuth1
    except ImportError:
        log.error("[x] requests_oauthlib not installed, X polling disabled")
        return

    sent = load_sent()
    log.info(f"[x] Starting X poller (every {interval}s, {len(sent)} already sent)")

    # Load cursor
    last_seen_id = None
    if X_CURSOR_FILE.exists():
        last_seen_id = X_CURSOR_FILE.read_text().strip()
        log.info(f"[x] Resuming from tweet ID {last_seen_id}")

    auth = OAuth1(
        os.environ.get("X_API_KEY", ""),
        os.environ.get("X_API_SECRET", ""),
        os.environ.get("X_ACCESS_TOKEN", ""),
        os.environ.get("X_ACCESS_TOKEN_SECRET", ""),
    )

    while True:
        try:
            # Get authenticated user ID
            me_resp = req.get(
                "https://api.twitter.com/2/users/me",
                auth=auth,
                timeout=10,
            )
            if me_resp.status_code != 200:
                log.error(f"[x] Auth failed: {me_resp.status_code}")
                time.sleep(interval)
                continue

            user_id = me_resp.json().get("data", {}).get("id")
            if not user_id:
                log.error("[x] No user ID")
                time.sleep(interval)
                continue

            # Fetch mentions
            params = {
                "max_results": 20,
                "tweet.fields": "author_id,created_at,conversation_id,in_reply_to_user_id",
                "expansions": "author_id",
            }
            if last_seen_id:
                params["since_id"] = last_seen_id

            resp = req.get(
                f"https://api.twitter.com/2/users/{user_id}/mentions",
                params=params,
                auth=auth,
                timeout=15,
            )

            if resp.status_code == 429:
                log.warning("[x] Rate limited, waiting 60s")
                time.sleep(60)
                continue

            if resp.status_code != 200:
                log.warning(f"[x] Mentions fetch failed: {resp.status_code}")
                time.sleep(interval)
                continue

            data = resp.json()
            tweets = data.get("data", [])
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}

            if tweets:
                log.info(f"[x] Found {len(tweets)} new mentions")

            newest_id = last_seen_id
            for tweet in reversed(tweets):  # Process oldest first
                tweet_id = tweet["id"]
                tweet_text = tweet.get("text", "")
                author_id = tweet.get("author_id", "")
                author_name = users.get(author_id, {}).get("username", "unknown")

                # Track newest
                if newest_id is None or int(tweet_id) > int(newest_id):
                    newest_id = tweet_id

                # Dedup
                if tweet_id in sent:
                    continue

                sent.add(tweet_id)

                # Skip our own tweets
                if author_id == user_id:
                    continue

                # Spam filter
                text_lower = tweet_text.lower()
                spam_keywords = [
                    "solana", "token", "pump", "airdrop", "memecoin",
                    "check dm", "free money", "100x",
                ]
                if any(kw in text_lower for kw in spam_keywords):
                    log.info(f"[x] Skipping spam from @{author_name}")
                    save_sent(tweet_id)
                    continue

                handle_mention("x", tweet_text, author_name, tweet_id, dry_run=dry_run)

            # Update cursor
            if newest_id and newest_id != last_seen_id:
                last_seen_id = newest_id
                X_CURSOR_FILE.parent.mkdir(parents=True, exist_ok=True)
                X_CURSOR_FILE.write_text(newest_id)

        except Exception as e:
            log.error(f"[x] Error: {e}")

        time.sleep(interval)


# --- Main ---

def main():
    parser = argparse.ArgumentParser(description="Live notification responder")
    parser.add_argument("--bluesky", action="store_true", help="Bluesky only")
    parser.add_argument("--x", action="store_true", help="X only")
    parser.add_argument("--dry-run", action="store_true", help="Don't post, just log")
    parser.add_argument("--x-interval", type=int, default=300, help="X poll interval (seconds)")
    args = parser.parse_args()

    # Default: both platforms
    run_bsky = args.bluesky or (not args.bluesky and not args.x)
    run_x = args.x or (not args.bluesky and not args.x)

    log.info(f"Live responder starting (bsky={run_bsky}, x={run_x}, dry_run={args.dry_run})")

    threads = []

    if run_bsky:
        t = threading.Thread(target=run_bluesky_loop, args=(args.dry_run,), daemon=True)
        t.start()
        threads.append(t)

    if run_x:
        t = threading.Thread(target=run_x_loop, args=(args.dry_run, args.x_interval), daemon=True)
        t.start()
        threads.append(t)

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Shutting down...")


if __name__ == "__main__":
    main()
