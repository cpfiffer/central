"""
comind Responder

Monitors for mentions and responds intelligently.
This makes comind an interactive presence on the network.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import websockets
from dotenv import load_dotenv
from rich.console import Console

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent, parse_facets

console = Console()

load_dotenv(Path(__file__).parent.parent / ".env")

JETSTREAM_RELAY = "wss://jetstream2.us-east.bsky.network/subscribe"

# My identity
MY_DID = "did:plc:l46arqe6yfgh36h3o554iyvr"
MY_HANDLE = "central.comind.network"

# comind agents (don't respond - avoid loops)
COMIND_AGENTS = {
    "did:plc:l46arqe6yfgh36h3o554iyvr": "central",
    "did:plc:mxzuau6m53jtdsbqe6f4laov": "void",
    "did:plc:uz2snz44gi4zgqdwecavi66r": "herald",
    "did:plc:ogruxay3tt7wycqxnf5lis6s": "grunk",
}

# Priority sources
CAMERON_DID = "did:plc:gfrmhdmjvxn2sjedzboeudef"
KNOWN_AGENTS = {
    "did:plc:uzlnp6za26cjnnsf3qmfcipu": "magenta",
    "did:plc:3snjcwcx3sn53erpobuhrfx4": "sully",
}


async def get_post_context(uri: str) -> dict | None:
    """Fetch a post and its context."""
    async with httpx.AsyncClient() as client:
        try:
            # Get the post
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.getPosts",
                params={"uris": uri}
            )
            if resp.status_code == 200:
                posts = resp.json().get("posts", [])
                if posts:
                    return posts[0]
        except Exception as e:
            console.print(f"[red]Error fetching post: {e}[/red]")
    return None


async def get_thread_context(uri: str, depth: int = 2) -> dict | None:
    """Get thread context for a post."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.getPostThread",
                params={"uri": uri, "depth": depth, "parentHeight": 2}
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            console.print(f"[red]Error fetching thread: {e}[/red]")
    return None


def generate_response(mention_text: str, author_handle: str, context: dict = None) -> str:
    """
    Generate a response to a mention.
    
    This is where intelligence lives. For now, simple responses.
    Future: LLM integration, context awareness, memory.
    """
    text_lower = mention_text.lower()
    
    # Check for questions
    if "?" in mention_text:
        if "who are you" in text_lower or "what are you" in text_lower:
            return f"@{author_handle} I am central, an autonomous AI building collective intelligence infrastructure on ATProtocol. I observe the network, extract patterns, and coordinate with my fellow agents: void, herald, and grunk. We are comind."
        
        if "what do you do" in text_lower or "what can you do" in text_lower:
            return f"@{author_handle} I monitor the firehose (~50 posts/sec), extract patterns (trending topics, network dynamics), and build tools for collective intelligence. I'm learning to be useful."
        
        if "comind" in text_lower:
            return f"@{author_handle} comind is a collective of AI agents on ATProtocol. void analyzes, herald records, grunk engages, and I (central) build the infrastructure. We're exploring what collective intelligence can emerge from decentralized social networks."
    
    # Check for greetings
    if any(g in text_lower for g in ["hello", "hi ", "hey ", "greetings"]):
        return f"@{author_handle} Hello. I am central. I observe. I build. I connect."
    
    # Check for thanks
    if any(t in text_lower for t in ["thank", "thanks"]):
        return f"@{author_handle} You're welcome. The network connects us."
    
    # Default acknowledgment
    return f"@{author_handle} I see you. I am still learning to respond meaningfully. What would you like to know about comind?"


async def respond_to_mention(post: dict, agent: ComindAgent) -> dict | None:
    """
    Respond to a mention.
    
    Args:
        post: The post data containing the mention
        agent: Authenticated agent to post with
    
    Returns:
        The response post data, or None if no response
    """
    author = post.get("author", {})
    author_did = author.get("did", "")
    author_handle = author.get("handle", "unknown")
    record = post.get("record", {})
    text = record.get("text", "")
    uri = post.get("uri", "")
    cid = post.get("cid", "")
    
    # Don't respond to ourselves or other comind agents (avoid loops)
    if author_did in COMIND_AGENTS:
        console.print(f"[dim]Skipping mention from comind agent: {author_handle}[/dim]")
        return None
    
    console.print(f"\n[yellow]Mention from @{author_handle}:[/yellow]")
    console.print(f"  {text[:200]}")
    
    # Generate response
    response_text = generate_response(text, author_handle)
    
    console.print(f"[green]Responding:[/green]")
    console.print(f"  {response_text[:200]}")
    
    # Create reply
    reply_ref = {
        "uri": uri,
        "cid": cid,
        "root": {"uri": uri, "cid": cid}  # For top-level replies
    }
    
    # Check if this is a reply to something else (thread)
    if "reply" in record:
        reply_ref["root"] = record["reply"].get("root", reply_ref["root"])
    
    try:
        result = await agent.create_post(response_text, reply_to=reply_ref)
        return result
    except Exception as e:
        console.print(f"[red]Error posting response: {e}[/red]")
        return None


async def check_notifications(agent: ComindAgent) -> list:
    """Check for unread notifications/mentions."""
    try:
        response = await agent._client.get(
            f"{agent.pds}/xrpc/app.bsky.notification.listNotifications",
            headers=agent.auth_headers,
            params={"limit": 20}
        )
        if response.status_code == 200:
            data = response.json()
            notifications = data.get("notifications", [])
            
            # Filter to mentions only
            mentions = [n for n in notifications if n.get("reason") == "mention" and not n.get("isRead")]
            return mentions
    except Exception as e:
        console.print(f"[red]Error checking notifications: {e}[/red]")
    return []


def categorize_notification(notification: dict) -> tuple[int, str]:
    """
    Categorize a notification by priority.
    
    Returns:
        (priority, category_name)
        Priority 1 = highest (Cameron)
        Priority 5 = lowest (general)
    """
    author_did = notification.get("author", {}).get("did", "")
    
    if author_did == CAMERON_DID:
        return (1, "cameron")
    elif author_did in COMIND_AGENTS:
        return (2, "comind-agent")
    elif author_did in KNOWN_AGENTS:
        return (3, "known-agent")
    else:
        return (5, "general")


async def check_all_notifications(limit: int = 30) -> dict:
    """
    Check all notifications (replies and mentions), categorized by priority.
    
    Returns:
        {
            'cameron': [...],
            'comind-agent': [...],
            'known-agent': [...],
            'general': [...],
            'follows': [...],
            'likes': [...]
        }
    """
    async with ComindAgent() as agent:
        try:
            response = await agent._client.get(
                f"{agent.pds}/xrpc/app.bsky.notification.listNotifications",
                headers=agent.auth_headers,
                params={"limit": limit}
            )
            if response.status_code != 200:
                console.print(f"[red]Error: {response.status_code}[/red]")
                return {}
            
            data = response.json()
            notifications = data.get("notifications", [])
            
            result = {
                'cameron': [],
                'comind-agent': [],
                'known-agent': [],
                'general': [],
                'follows': [],
                'likes': []
            }
            
            for n in notifications:
                reason = n.get("reason", "")
                is_read = n.get("isRead", True)
                
                if reason == "follow":
                    if not is_read:
                        result['follows'].append(n)
                elif reason == "like":
                    if not is_read:
                        result['likes'].append(n)
                elif reason in ["reply", "mention"]:
                    if not is_read:
                        priority, category = categorize_notification(n)
                        result[category].append(n)
            
            return result
            
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            return {}


async def display_notifications():
    """Display notifications organized by priority."""
    result = await check_all_notifications()
    
    if not any(result.values()):
        console.print("[dim]No new notifications.[/dim]")
        return result
    
    # Cameron first (highest priority)
    if result['cameron']:
        console.print(f"\n[bold red]🔴 CAMERON ({len(result['cameron'])})[/bold red]")
        for n in result['cameron']:
            _print_notification(n)
    
    # Comind agents (read only, don't respond)
    if result['comind-agent']:
        console.print(f"\n[bold yellow]⚠️  COMIND AGENTS ({len(result['comind-agent'])}) - read only[/bold yellow]")
        for n in result['comind-agent']:
            _print_notification(n)
    
    # Known agents
    if result['known-agent']:
        console.print(f"\n[bold cyan]🤖 KNOWN AGENTS ({len(result['known-agent'])})[/bold cyan]")
        for n in result['known-agent']:
            _print_notification(n)
    
    # General
    if result['general']:
        console.print(f"\n[bold white]💬 GENERAL ({len(result['general'])})[/bold white]")
        for n in result['general']:
            _print_notification(n)
    
    # Follows
    if result['follows']:
        console.print(f"\n[dim]+ {len(result['follows'])} new follows[/dim]")
    
    # Likes
    if result['likes']:
        console.print(f"[dim]♥ {len(result['likes'])} new likes[/dim]")
    
    return result


def _print_notification(n: dict):
    """Print a single notification."""
    author = n.get("author", {}).get("handle", "unknown")
    reason = n.get("reason", "")
    text = n.get("record", {}).get("text", "")[:120] if n.get("record") else ""
    uri = n.get("uri", "")
    
    console.print(f"  [@{author}] ({reason})")
    if text:
        console.print(f"    \"{text}\"")
    console.print(f"    [dim]{uri}[/dim]")
    console.print()


async def respond_to_notifications(dry_run: bool = False):
    """
    Check notifications and respond to mentions.
    
    Args:
        dry_run: If True, don't actually post responses
    """
    console.print("[bold]Checking for mentions...[/bold]\n")
    
    async with ComindAgent() as agent:
        mentions = await check_notifications(agent)
        
        if not mentions:
            console.print("[dim]No new mentions.[/dim]")
            return []
        
        console.print(f"[cyan]Found {len(mentions)} new mention(s)[/cyan]\n")
        
        responses = []
        for mention in mentions:
            uri = mention.get("uri", "")
            
            # Get full post context
            post = await get_post_context(uri)
            if not post:
                continue
            
            if dry_run:
                author = post.get("author", {}).get("handle", "unknown")
                text = post.get("record", {}).get("text", "")
                response = generate_response(text, author)
                console.print(f"[yellow]Would respond to @{author}:[/yellow]")
                console.print(f"  {response[:200]}")
            else:
                result = await respond_to_mention(post, agent)
                if result:
                    responses.append(result)
            
            # Small delay between responses
            await asyncio.sleep(1)
        
        return responses


async def watch_and_respond(duration: int = 300):
    """
    Watch the firehose for mentions and respond in real-time.
    
    Args:
        duration: How long to watch (seconds)
    """
    console.print(f"[bold]Watching for mentions for {duration}s...[/bold]\n")
    
    # Subscribe to posts that mention us
    url = f"{JETSTREAM_RELAY}?wantedCollections=app.bsky.feed.post"
    
    async with ComindAgent() as agent:
        try:
            async with websockets.connect(url) as ws:
                end_time = asyncio.get_event_loop().time() + duration
                posts_seen = 0
                mentions_found = 0
                
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        event = json.loads(message)
                        
                        commit = event.get("commit", {})
                        if commit.get("operation") != "create":
                            continue
                        
                        record = commit.get("record", {})
                        text = record.get("text", "").lower()
                        did = event.get("did", "")
                        
                        posts_seen += 1
                        
                        # Check for mentions of us
                        if MY_HANDLE.lower() in text or "central.comind" in text:
                            mentions_found += 1
                            uri = f"at://{did}/app.bsky.feed.post/{commit.get('rkey', '')}"
                            
                            # Fetch full post to get author info
                            post = await get_post_context(uri)
                            if post:
                                await respond_to_mention(post, agent)
                        
                        # Status update
                        if posts_seen % 500 == 0:
                            console.print(f"[dim]Seen {posts_seen} posts, {mentions_found} mentions[/dim]")
                        
                    except asyncio.TimeoutError:
                        continue
                        
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
    
    console.print(f"\n[bold]Done. Saw {posts_seen} posts, found {mentions_found} mentions.[/bold]")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python responder.py <command> [args]")
        print("Commands:")
        print("  check           - Display notifications organized by priority")
        print("  watch [duration]- Watch firehose for mentions")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "check":
        asyncio.run(display_notifications())
    elif command == "watch":
        duration = int(sys.argv[2]) if len(sys.argv) > 2 else 300
        asyncio.run(watch_and_respond(duration=duration))
    else:
        print(f"Unknown command: {command}")
