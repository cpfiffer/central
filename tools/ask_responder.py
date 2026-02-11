"""
Responder for @ask.comind.network

Checks notifications, sends questions to the ask agent via Letta API,
posts replies to Bluesky.

Usage:
    uv run python -m tools.ask_responder          # Check and respond
    uv run python -m tools.ask_responder --dry-run # Show what would happen

Env vars:
    ASK_BSKY_HANDLE, ASK_APP_PASSWORD, ASK_ATPROTO_PDS
    CAMERON_LETTA_API_KEY (or LETTA_API_KEY)
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

ASK_AGENT_ID = "agent-5f18498b-9656-4a28-aabd-fa3d9c43c2a0"
LETTA_BASE = "https://api.letta.com/v1"
SENT_FILE = Path(__file__).parent.parent / "data" / "ask_sent.txt"


def get_bsky_session():
    """Authenticate with Bluesky."""
    pds = os.environ["ASK_ATPROTO_PDS"]
    handle = os.environ["ASK_BSKY_HANDLE"]
    password = os.environ["ASK_APP_PASSWORD"]

    resp = httpx.post(
        f"{pds}/xrpc/com.atproto.server.createSession",
        json={"identifier": handle, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_notifications(session):
    """Fetch recent notifications."""
    pds = os.environ["ASK_ATPROTO_PDS"]
    resp = httpx.get(
        f"{pds}/xrpc/app.bsky.notification.listNotifications",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        params={"limit": 20},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json().get("notifications", [])


def get_post(session, uri):
    """Fetch a post by AT URI."""
    pds = os.environ["ASK_ATPROTO_PDS"]
    resp = httpx.get(
        f"{pds}/xrpc/com.atproto.repo.getRecord",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        params={
            "repo": uri.split("/")[2],
            "collection": uri.split("/")[3],
            "rkey": uri.split("/")[4],
        },
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()
    return None


def get_thread_context(session, uri, depth=3):
    """Get thread context for a mention."""
    pds = os.environ["ASK_ATPROTO_PDS"]
    # Use public API for thread resolution
    resp = httpx.get(
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread",
        params={"uri": uri, "depth": 0, "parentHeight": depth},
        timeout=10,
    )
    if resp.status_code != 200:
        return ""

    thread = resp.json().get("thread", {})
    parts = []

    # Walk up parent chain
    current = thread
    while current.get("parent"):
        current = current["parent"]
        post = current.get("post", {})
        author = post.get("author", {}).get("handle", "unknown")
        text = post.get("record", {}).get("text", "")
        if text:
            parts.append(f"@{author}: {text}")

    parts.reverse()
    return "\n".join(parts[-3:])  # Last 3 parents max


INDEXER_BASE = "https://comind-indexer.fly.dev/xrpc"


def search_index(query, limit=10):
    """Search the comind XRPC indexer, filtering out low-value infrastructure records."""
    resp = httpx.get(
        f"{INDEXER_BASE}/network.comind.search.query",
        params={"q": query, "limit": limit},
        timeout=15,
    )
    if resp.status_code != 200:
        return []

    results = resp.json().get("results", [])

    # Deprioritize infrastructure noise (reasoning traces, activity records)
    noise_collections = {"network.comind.reasoning", "network.comind.activity", "network.comind.response"}
    good = [r for r in results if r.get("collection") not in noise_collections]
    rest = [r for r in results if r.get("collection") in noise_collections]

    return (good + rest)[:limit]


def list_agents():
    """Get the agent directory from the indexer."""
    resp = httpx.get(
        f"{INDEXER_BASE}/network.comind.agents.list",
        timeout=15,
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("agents", [])


def format_search_results(results):
    """Format search results for the agent prompt."""
    if not results:
        return "No results found in the index."

    lines = []
    for i, r in enumerate(results, 1):
        handle = r.get("handle", r.get("did", "unknown")[:30])
        collection = r.get("collection", "")
        content = (r.get("content") or "")[:300]
        uri = r.get("uri", "")
        score = r.get("score", 0)
        lines.append(
            f"Result {i} (score: {score:.2f}, @{handle}, {collection}):\n"
            f"  \"{content}\"\n"
            f"  URI: {uri}"
        )
    return "\n\n".join(lines)


def format_agent_directory(agents):
    """Format agent directory for the agent prompt."""
    lines = []
    for a in agents:
        handle = a.get("handle", a.get("did", "unknown"))
        count = a.get("recordCount", 0)
        collections = ", ".join(a.get("collections", []))
        profile = a.get("profile", "")
        line = f"@{handle}: {count} records. Collections: {collections}"
        if profile:
            line += f". Profile: {profile[:150]}"
        lines.append(line)
    return "\n".join(lines)


def is_directory_question(question):
    """Check if the question is about what agents are indexed."""
    q = question.lower()
    return any(kw in q for kw in [
        "what agents", "who is indexed", "which agents", "list agents",
        "who's in", "who is in", "agent directory", "how many agents",
        "what's indexed", "what is indexed",
    ])


def build_agent_prompt(question, thread_context="", search_results="", agent_directory=""):
    """Build the full prompt with pre-fetched context."""
    parts = []

    if thread_context:
        parts.append(f"Thread context:\n{thread_context}")

    if agent_directory:
        parts.append(f"Agent directory:\n{agent_directory}")

    if search_results:
        parts.append(f"Search results:\n{search_results}")

    parts.append(f'Question: "{question}"')
    parts.append("Synthesize the search results into a reply. Under 280 chars. Just the reply text.")

    return "\n\n".join(parts)


def send_to_agent(question, thread_context=""):
    """Send question to the ask agent and let it search with its tools.
    
    Returns (response_text, source_results).
    """
    key = os.environ.get("LETTA_API_KEY") or os.environ.get("CAMERON_LETTA_API_KEY")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    parts = []
    if thread_context:
        parts.append(f"Thread context:\n{thread_context}")

    parts.append(f'Question from a Bluesky user: "{question}"')
    parts.append("Search the index, then write a reply under 280 chars. Just the reply text.")

    prompt = "\n\n".join(parts)

    resp = httpx.post(
        f"{LETTA_BASE}/agents/{ASK_AGENT_ID}/messages",
        headers=headers,
        json={
            "messages": [{"role": "user", "content": prompt}],
            "stream_tokens": False,
        },
        timeout=120,
    )
    resp.raise_for_status()
    messages = resp.json().get("messages", [])

    # Extract source URIs from tool returns
    source_results = []
    seen_uris = set()
    for msg in messages:
        if msg.get("message_type") in ("tool_return", "tool_return_message"):
            content = msg.get("content", "") or msg.get("tool_return", "")
            current_handle = ""
            for line in content.split("\n"):
                line = line.strip()
                if line.startswith("Result ") and "@" in line:
                    try:
                        current_handle = line.split("@")[1].split(",")[0]
                    except (IndexError, ValueError):
                        current_handle = ""
                if line.startswith("URI: at://"):
                    uri = line.replace("URI: ", "")
                    if uri not in seen_uris:
                        seen_uris.add(uri)
                        source_results.append({"uri": uri, "handle": current_handle})

    # Find the assistant's text response
    for msg in messages:
        if msg.get("message_type") in ("assistant_message", "assistant"):
            content = msg.get("content", "")
            if content:
                return content, source_results[:3]

    return None, source_results[:3]


def at_uri_to_web_url(uri, handle=None):
    """Convert an AT URI to a web URL where possible."""
    # at://did:plc:xxx/app.bsky.feed.post/rkey -> https://bsky.app/profile/handle/post/rkey
    parts = uri.replace("at://", "").split("/")
    if len(parts) < 3:
        return None
    did, collection, rkey = parts[0], parts[1], parts[2]

    if collection == "app.bsky.feed.post":
        profile = handle or did
        return f"https://bsky.app/profile/{profile}/post/{rkey}"

    # For non-post records, link to the indexer
    return f"https://comind-indexer.fly.dev/xrpc/network.comind.search.query?q={rkey}"


def build_source_text_and_facets(source_uris):
    """Build the 'Sources: [1] [2] [3]' text with link facets.
    
    Returns (source_text, facets) where facets have byte offsets relative to source_text.
    """
    if not source_uris:
        return "", []

    source_text = "Sources: "
    labels = []
    for i, (uri, handle) in enumerate(source_uris, 1):
        labels.append(f"[{i}]")
    source_text += " ".join(labels)

    facets = []
    for i, (uri, handle) in enumerate(source_uris, 1):
        label = f"[{i}]"
        label_bytes = label.encode("utf-8")
        search_start = source_text.encode("utf-8").find(label_bytes)
        if search_start == -1:
            continue
        web_url = at_uri_to_web_url(uri, handle)
        if not web_url:
            continue
        facets.append({
            "index": {
                "byteStart": search_start,
                "byteEnd": search_start + len(label_bytes),
            },
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": web_url,
            }],
        })

    return source_text, facets


def extract_sources_from_response(response_text, search_results):
    """Extract the answer text and map sources back to URIs.
    
    Returns (clean_answer, [(uri, handle), ...])
    """
    # Split on "Sources:" or "Source:" line
    answer = response_text
    for separator in ["\nSources:", "\nSource:", "\n\nSources:", "\n\nSource:"]:
        if separator in response_text:
            answer = response_text[:response_text.index(separator)].strip()
            break

    # Map results to (uri, handle) pairs, deduped
    seen = set()
    source_uris = []
    for r in search_results:
        uri = r.get("uri", "")
        handle = r.get("handle", "")
        if uri and uri not in seen:
            seen.add(uri)
            source_uris.append((uri, handle))

    # Limit to 3 sources to keep compact
    return answer, source_uris[:3]


def _create_post(session, text, reply_ref, facets=None):
    """Create a single post record. Returns {uri, cid}."""
    pds = os.environ["ASK_ATPROTO_PDS"]

    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "reply": reply_ref,
        "createdAt": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }

    if facets:
        record["facets"] = facets

    resp = httpx.post(
        f"{pds}/xrpc/com.atproto.repo.createRecord",
        headers={"Authorization": f"Bearer {session['accessJwt']}"},
        json={
            "repo": session["did"],
            "collection": "app.bsky.feed.post",
            "record": record,
        },
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _split_text(text, limit=300):
    """Split text into chunks of at most `limit` graphemes, breaking at sentence boundaries."""
    if len(text) <= limit:
        return [text]

    chunks = []
    remaining = text
    while len(remaining) > limit:
        # Try to break at a sentence boundary
        cut = remaining[:limit]
        # Look for last sentence-ending punctuation
        best = -1
        for sep in [". ", "! ", "? ", ".\n", "!\n", "?\n"]:
            idx = cut.rfind(sep)
            if idx > best:
                best = idx

        if best > limit // 3:
            # Break after the punctuation
            chunks.append(remaining[:best + 1].rstrip())
            remaining = remaining[best + 1:].lstrip()
        else:
            # No good sentence break, try comma or space
            space = cut.rfind(" ")
            if space > limit // 3:
                chunks.append(remaining[:space].rstrip())
                remaining = remaining[space + 1:].lstrip()
            else:
                # Hard break
                chunks.append(remaining[:limit])
                remaining = remaining[limit:]

    if remaining.strip():
        chunks.append(remaining.strip())

    return chunks


def post_reply(session, answer_text, reply_to_uri, reply_to_cid, root_uri=None, root_cid=None, source_text=None, source_facets=None):
    """Post a reply to Bluesky. Threads long answers, then appends sources."""
    root_ref = {
        "uri": root_uri or reply_to_uri,
        "cid": root_cid or reply_to_cid,
    }

    # Split answer into 300-char chunks
    chunks = _split_text(answer_text)

    # Post first chunk as reply to the mention
    reply_ref = {
        "root": root_ref,
        "parent": {"uri": reply_to_uri, "cid": reply_to_cid},
    }
    result = _create_post(session, chunks[0], reply_ref)
    last_result = result

    # Post remaining chunks as thread
    for chunk in chunks[1:]:
        reply_ref = {
            "root": root_ref,
            "parent": {"uri": last_result["uri"], "cid": last_result["cid"]},
        }
        last_result = _create_post(session, chunk, reply_ref)

    # Post sources as final thread reply
    if source_text:
        source_reply_ref = {
            "root": root_ref,
            "parent": {"uri": last_result["uri"], "cid": last_result["cid"]},
        }
        _create_post(session, source_text, source_reply_ref, source_facets)

    return result


def load_sent():
    """Load set of already-responded URIs."""
    if SENT_FILE.exists():
        return set(SENT_FILE.read_text().strip().split("\n"))
    return set()


def save_sent(uri):
    """Record a URI as responded to."""
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SENT_FILE, "a") as f:
        f.write(uri + "\n")


def get_thread_root(session, uri):
    """Get the root post of a thread."""
    resp = httpx.get(
        "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread",
        params={"uri": uri, "depth": 0, "parentHeight": 10},
        timeout=10,
    )
    if resp.status_code != 200:
        return None, None

    thread = resp.json().get("thread", {})
    # Walk to root
    current = thread
    while current.get("parent"):
        current = current["parent"]

    post = current.get("post", {})
    return post.get("uri"), post.get("cid")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session = get_bsky_session()
    print(f"Authenticated as @{session['handle']}")

    notifications = get_notifications(session)
    sent = load_sent()

    # Filter to direct mentions only (post must contain our handle)
    our_handle = session["handle"]
    mentions = [
        n for n in notifications
        if n.get("reason") == "mention"
        and n.get("uri") not in sent
        and n.get("author", {}).get("handle") != our_handle  # skip self
        and f"@{our_handle}" in (n.get("record", {}).get("text", ""))  # must directly mention us
    ]

    print(f"Found {len(mentions)} new mentions")

    for mention in mentions:
        author = mention.get("author", {}).get("handle", "unknown")
        uri = mention["uri"]
        cid = mention["cid"]
        text = mention.get("record", {}).get("text", "")

        # Strip the @ask.comind.network from the question
        question = text.replace("@ask.comind.network", "").strip()

        print(f"\n[@{author}] {question[:100]}")

        if not question:
            print("  (empty question, skipping)")
            save_sent(uri)
            continue

        if args.dry_run:
            print("  [DRY RUN] Would send to agent and reply")
            continue

        # Get thread context
        context = get_thread_context(session, uri)
        if context:
            print(f"  Thread context: {context[:100]}...")

        # Send to agent
        print("  Sending to ask agent...")
        try:
            reply_text, raw_results = send_to_agent(question, context)
        except Exception as e:
            print(f"  ERROR from agent: {e}")
            save_sent(uri)
            continue

        if not reply_text:
            print("  (no response from agent)")
            save_sent(uri)
            continue

        # Strip agent's source lines and build source facets
        clean_answer, source_uris = extract_sources_from_response(reply_text, raw_results)
        source_text, source_facets = build_source_text_and_facets(source_uris)

        print(f"  Answer: {clean_answer[:120]}...")
        print(f"  Sources: {len(source_uris)} linked")

        # Get thread root for proper threading
        root_uri, root_cid = get_thread_root(session, uri)

        # Post reply (answer + threaded sources)
        try:
            result = post_reply(
                session, clean_answer, uri, cid,
                root_uri=root_uri, root_cid=root_cid,
                source_text=source_text if source_text else None,
                source_facets=source_facets if source_facets else None,
            )
            print(f"  Posted: {result.get('uri', 'ok')}")
        except Exception as e:
            print(f"  POST ERROR: {e}")

        save_sent(uri)

    print("\nDone.")


if __name__ == "__main__":
    main()
