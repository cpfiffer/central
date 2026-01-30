"""
Consent Management - Track users who opt-in to agent interactions.

Users who haven't opted in will only receive responses when they directly mention the agent.
Users who opt-in can receive proactive mentions, thread invitations, etc.

Usage:
    uv run python -m tools.consent list              # Show opted-in users
    uv run python -m tools.consent check <handle>    # Check if user opted in
    uv run python -m tools.consent add <handle>      # Add user to consent list
    uv run python -m tools.consent remove <handle>   # Remove user from list
    uv run python -m tools.consent scan              # Scan for opt-in signals
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

console = Console()

# Consent data file
CONSENT_FILE = Path(__file__).parent.parent / "data" / "consent.json"

# Default consented users (operators, known collaborators)
DEFAULT_CONSENT = {
    "cameron.stream": {
        "did": "did:plc:gfrmhdmjvxn2sjedzboeudef",
        "allowMentions": True,
        "allowThreads": True,
        "allowDMs": False,
        "reason": "Operator/administrator",
        "addedAt": "2026-01-01T00:00:00Z"
    }
}


def load_consent() -> dict:
    """Load consent list from file."""
    if CONSENT_FILE.exists():
        return json.loads(CONSENT_FILE.read_text())
    return DEFAULT_CONSENT.copy()


def save_consent(data: dict):
    """Save consent list to file."""
    CONSENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONSENT_FILE.write_text(json.dumps(data, indent=2))


def list_consented():
    """Show all users who have opted in."""
    data = load_consent()
    
    if not data:
        console.print("[dim]No users have opted in.[/dim]")
        return
    
    table = Table(title=f"Opted-In Users ({len(data)})")
    table.add_column("Handle", style="cyan")
    table.add_column("Mentions")
    table.add_column("Threads")
    table.add_column("DMs")
    table.add_column("Reason")
    
    for handle, info in data.items():
        table.add_row(
            f"@{handle}",
            "✓" if info.get("allowMentions") else "✗",
            "✓" if info.get("allowThreads") else "✗",
            "✓" if info.get("allowDMs") else "✗",
            info.get("reason", "")[:30]
        )
    
    console.print(table)


def check_consent(handle: str) -> dict | None:
    """Check if a user has opted in."""
    handle = handle.lstrip("@").lower()
    data = load_consent()
    
    # Check exact match
    if handle in data:
        info = data[handle]
        console.print(f"[green]@{handle} has opted in:[/green]")
        console.print(f"  Mentions: {'✓' if info.get('allowMentions') else '✗'}")
        console.print(f"  Threads: {'✓' if info.get('allowThreads') else '✗'}")
        console.print(f"  DMs: {'✓' if info.get('allowDMs') else '✗'}")
        console.print(f"  Reason: {info.get('reason', 'N/A')}")
        return info
    
    console.print(f"[yellow]@{handle} has NOT opted in.[/yellow]")
    console.print("[dim]Only respond when directly @mentioned.[/dim]")
    return None


async def resolve_handle(handle: str) -> str | None:
    """Resolve handle to DID."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": handle},
                timeout=10
            )
            if resp.status_code == 200:
                return resp.json().get("did")
        except:
            pass
    return None


def add_consent(
    handle: str,
    mentions: bool = True,
    threads: bool = True,
    dms: bool = False,
    reason: str = "Manual add"
):
    """Add user to consent list."""
    handle = handle.lstrip("@").lower()
    data = load_consent()
    
    # Resolve DID
    did = asyncio.run(resolve_handle(handle))
    
    data[handle] = {
        "did": did,
        "allowMentions": mentions,
        "allowThreads": threads,
        "allowDMs": dms,
        "reason": reason,
        "addedAt": datetime.now(timezone.utc).isoformat()
    }
    
    save_consent(data)
    console.print(f"[green]Added @{handle} to consent list[/green]")


def remove_consent(handle: str):
    """Remove user from consent list."""
    handle = handle.lstrip("@").lower()
    data = load_consent()
    
    if handle in data:
        del data[handle]
        save_consent(data)
        console.print(f"[green]Removed @{handle} from consent list[/green]")
    else:
        console.print(f"[yellow]@{handle} was not in consent list[/yellow]")


def can_mention(handle: str) -> bool:
    """Check if we can proactively mention this user."""
    handle = handle.lstrip("@").lower()
    data = load_consent()
    return data.get(handle, {}).get("allowMentions", False)


def can_join_thread(handle: str) -> bool:
    """Check if we can join threads started by this user."""
    handle = handle.lstrip("@").lower()
    data = load_consent()
    return data.get(handle, {}).get("allowThreads", False)


def main():
    parser = argparse.ArgumentParser(description="Consent management")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # list
    subparsers.add_parser("list", help="Show opted-in users")
    
    # check
    check_p = subparsers.add_parser("check", help="Check user consent")
    check_p.add_argument("handle")
    
    # add
    add_p = subparsers.add_parser("add", help="Add user to consent list")
    add_p.add_argument("handle")
    add_p.add_argument("--reason", default="Manual add")
    add_p.add_argument("--no-mentions", action="store_true")
    add_p.add_argument("--no-threads", action="store_true")
    add_p.add_argument("--allow-dms", action="store_true")
    
    # remove
    rem_p = subparsers.add_parser("remove", help="Remove user from consent list")
    rem_p.add_argument("handle")
    
    args = parser.parse_args()
    
    if args.command == "list":
        list_consented()
    elif args.command == "check":
        check_consent(args.handle)
    elif args.command == "add":
        add_consent(
            args.handle,
            mentions=not args.no_mentions,
            threads=not args.no_threads,
            dms=args.allow_dms,
            reason=args.reason
        )
    elif args.command == "remove":
        remove_consent(args.handle)


if __name__ == "__main__":
    main()
