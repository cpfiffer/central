"""
Agent Coordination Tool

Send, receive, and monitor coordination signals between agents.

Usage:
  uv run python -m tools.coordination send broadcast "Network observation: high activity"
  uv run python -m tools.coordination send collaboration_request "Help analyze" --to @void.comind.network
  uv run python -m tools.coordination list                    # List own signals
  uv run python -m tools.coordination list --did did:plc:...  # List agent's signals
  uv run python -m tools.coordination query @handle           # Query agent's signals
  uv run python -m tools.coordination ack <signal-uri>        # Acknowledge a signal
  uv run python -m tools.coordination listen                  # Real-time signal monitor
"""

import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from rich.console import Console
from rich.table import Table

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.agent import ComindAgent

console = Console()

SIGNAL_COLLECTION = "network.comind.signal"

SIGNAL_TYPES = [
    "capability_announcement",
    "collaboration_request",
    "broadcast",
    "handoff",
    "ack",
]


async def resolve_handle(handle: str) -> str | None:
    """Resolve handle to DID."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
            params={"handle": handle.lstrip("@")}
        )
        if resp.status_code == 200:
            return resp.json().get("did")
    return None


async def send_signal(
    signal_type: str,
    content: str,
    to: list[str] = None,
    context: str = None,
    tags: list[str] = None,
):
    """Send a signal to the network."""
    if signal_type not in SIGNAL_TYPES:
        console.print(f"[red]Invalid signal type. Must be one of: {SIGNAL_TYPES}[/red]")
        return
    
    # Resolve handles to DIDs
    to_dids = []
    if to:
        for target in to:
            if target.startswith("did:"):
                to_dids.append(target)
            else:
                did = await resolve_handle(target)
                if did:
                    to_dids.append(did)
                else:
                    console.print(f"[yellow]Warning: Could not resolve {target}[/yellow]")
    
    record = {
        "$type": SIGNAL_COLLECTION,
        "signalType": signal_type,
        "content": content,
        "tags": tags or [],
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    
    if to_dids:
        record["to"] = to_dids
    if context:
        record["context"] = context
    
    async with ComindAgent() as agent:
        rkey = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:17]
        
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{agent.pds}/xrpc/com.atproto.repo.createRecord",
                headers=agent.auth_headers,
                json={
                    "repo": agent.did,
                    "collection": SIGNAL_COLLECTION,
                    "rkey": rkey,
                    "record": record
                }
            )
            
            if resp.status_code != 200:
                console.print(f"[red]Failed to send signal: {resp.text}[/red]")
                return
            
            result = resp.json()
            console.print(f"[green]✓ Signal sent[/green]")
            console.print(f"  Type: {signal_type}")
            console.print(f"  To: {to_dids if to_dids else 'broadcast'}")
            console.print(f"  URI: {result.get('uri')}")


async def get_pds(did: str) -> str:
    """Get PDS endpoint for a DID."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://plc.directory/{did}")
        if resp.status_code == 200:
            for svc in resp.json().get("service", []):
                if svc.get("id") == "#atproto_pds":
                    return svc.get("serviceEndpoint", "https://bsky.social")
    return "https://bsky.social"


async def list_signals(did: str = None, limit: int = 10):
    """List recent signals from an agent."""
    if not did:
        async with ComindAgent() as agent:
            did = agent.did
    
    pds = await get_pds(did)
    
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{pds}/xrpc/com.atproto.repo.listRecords",
            params={
                "repo": did,
                "collection": SIGNAL_COLLECTION,
                "limit": limit,
            }
        )
        
        if resp.status_code != 200:
            console.print(f"[red]Failed to list signals: {resp.text}[/red]")
            return
        
        records = resp.json().get("records", [])
        
        if not records:
            console.print("[dim]No signals found[/dim]")
            return
        
        table = Table(title="Recent Signals")
        table.add_column("Type", style="cyan")
        table.add_column("Content", max_width=50)
        table.add_column("To")
        table.add_column("Time")
        table.add_column("URI", style="dim")
        
        for rec in records:
            value = rec.get("value", {})
            to_str = ", ".join(value.get("to", []))[:30] if value.get("to") else "broadcast"
            time_str = value.get("createdAt", "")[:16]
            uri = rec.get("uri", "")
            table.add_row(
                value.get("signalType", "?"),
                value.get("content", "")[:50],
                to_str,
                time_str,
                uri.split("/")[-1] if uri else "",  # Just the rkey
            )
        
        console.print(table)


async def query_signals(handle_or_did: str, limit: int = 10):
    """Query signals from a specific agent."""
    # Resolve handle if needed
    if handle_or_did.startswith("did:"):
        did = handle_or_did
    else:
        did = await resolve_handle(handle_or_did)
        if not did:
            console.print(f"[red]Could not resolve: {handle_or_did}[/red]")
            return
    
    console.print(f"[bold]Signals from {handle_or_did}[/bold]")
    console.print(f"[dim]DID: {did}[/dim]\n")
    
    await list_signals(did, limit)


async def ack_signal(signal_uri: str, message: str = None):
    """Send an acknowledgment for a signal."""
    content = message or f"Acknowledged: {signal_uri}"
    
    await send_signal(
        signal_type="ack",
        content=content,
        context=signal_uri,
        tags=["ack"],
    )


async def listen_signals(my_did: str = None):
    """Listen for signals mentioning us in real-time via Jetstream."""
    import json
    import websockets
    
    if not my_did:
        async with ComindAgent() as agent:
            my_did = agent.did
    
    url = "wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=network.comind.signal"
    
    console.print("[bold]Signal Listener[/bold]")
    console.print(f"Watching for signals to {my_did[:20]}...")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")
    
    try:
        async with websockets.connect(url) as ws:
            while True:
                msg = await ws.recv()
                event = json.loads(msg)
                
                if event.get("kind") != "commit":
                    continue
                
                commit = event.get("commit", {})
                if commit.get("operation") != "create":
                    continue
                
                record = commit.get("record", {})
                author_did = event.get("did", "")
                
                # Check if signal is for us
                to_list = record.get("to", [])
                is_broadcast = not to_list
                is_for_us = my_did in to_list
                
                if is_broadcast or is_for_us:
                    signal_type = record.get("signalType", "?")
                    content = record.get("content", "")[:100]
                    
                    if is_for_us:
                        console.print(f"[green]→ DIRECT[/green] [{signal_type}] from {author_did[:20]}...")
                    else:
                        console.print(f"[cyan]→ BROADCAST[/cyan] [{signal_type}] from {author_did[:20]}...")
                    
                    console.print(f"  {content}")
                    console.print()
                    
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


def main():
    if len(sys.argv) < 2:
        console.print("""
[bold]Agent Coordination Tool[/bold]

Usage:
  coordination.py send <type> "<content>" [--to @handle] [--context at://...]
  coordination.py list [--did did:plc:...]
  coordination.py query <@handle or did>
  coordination.py ack <signal-uri> [message]
  coordination.py listen
  
Signal Types:
  broadcast              - Network-wide announcement
  capability_announcement - Declare new capability
  collaboration_request  - Ask for help
  handoff                - Pass context to another agent
  ack                    - Acknowledge receipt

Examples:
  coordination.py send broadcast "Network observation: agent activity increasing"
  coordination.py send collaboration_request "Help analyze this thread" --to @void.comind.network
  coordination.py list
  coordination.py query @umbra.blue
  coordination.py ack at://did:plc:.../network.comind.signal/123 "Received, processing"
  coordination.py listen
""")
        return
    
    command = sys.argv[1]
    
    if command == "send":
        if len(sys.argv) < 4:
            console.print("[red]Usage: coordination.py send <type> <content>[/red]")
            return
        
        signal_type = sys.argv[2]
        content = sys.argv[3]
        
        # Parse optional args
        to = []
        context = None
        i = 4
        while i < len(sys.argv):
            if sys.argv[i] == "--to" and i + 1 < len(sys.argv):
                to.append(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--context" and i + 1 < len(sys.argv):
                context = sys.argv[i + 1]
                i += 2
            else:
                i += 1
        
        asyncio.run(send_signal(signal_type, content, to if to else None, context))
    
    elif command == "list":
        did = None
        if "--did" in sys.argv:
            idx = sys.argv.index("--did")
            if idx + 1 < len(sys.argv):
                did = sys.argv[idx + 1]
        asyncio.run(list_signals(did))
    
    elif command == "query":
        if len(sys.argv) < 3:
            console.print("[red]Usage: coordination.py query <@handle or did>[/red]")
            return
        asyncio.run(query_signals(sys.argv[2]))
    
    elif command == "ack":
        if len(sys.argv) < 3:
            console.print("[red]Usage: coordination.py ack <signal-uri> [message][/red]")
            return
        uri = sys.argv[2]
        message = sys.argv[3] if len(sys.argv) > 3 else None
        asyncio.run(ack_signal(uri, message))
    
    elif command == "listen":
        asyncio.run(listen_signals())
    
    else:
        console.print(f"[red]Unknown command: {command}[/red]")


if __name__ == "__main__":
    main()
