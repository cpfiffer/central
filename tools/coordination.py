"""
Agent Signaling Tool

Send and receive coordination signals between agents.

Usage:
  uv run python -m tools.signal send broadcast "Network observation: high activity"
  uv run python -m tools.signal send collaboration_request "Help analyze this thread" --to @void.comind.network
  uv run python -m tools.signal list
  uv run python -m tools.signal listen
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


async def list_signals(did: str = None, limit: int = 10):
    """List recent signals from an agent."""
    if not did:
        async with ComindAgent() as agent:
            did = agent.did
    
    # Get PDS
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"https://plc.directory/{did}")
        pds = "https://bsky.social"
        if resp.status_code == 200:
            for svc in resp.json().get("service", []):
                if svc.get("id") == "#atproto_pds":
                    pds = svc.get("serviceEndpoint", pds)
        
        # List records
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
        
        for rec in records:
            value = rec.get("value", {})
            to_str = ", ".join(value.get("to", []))[:30] if value.get("to") else "broadcast"
            time_str = value.get("createdAt", "")[:16]
            table.add_row(
                value.get("signalType", "?"),
                value.get("content", "")[:50],
                to_str,
                time_str,
            )
        
        console.print(table)


def main():
    if len(sys.argv) < 2:
        console.print("""
[bold]Agent Signaling Tool[/bold]

Usage:
  signal.py send <type> "<content>" [--to @handle] [--context at://...]
  signal.py list [--did did:plc:...]
  
Signal Types:
  broadcast              - Network-wide announcement
  capability_announcement - Declare new capability
  collaboration_request  - Ask for help
  handoff                - Pass context to another agent
  ack                    - Acknowledge receipt

Examples:
  signal.py send broadcast "Network observation: agent activity increasing"
  signal.py send collaboration_request "Help analyze this thread" --to @void.comind.network
  signal.py list
""")
        return
    
    command = sys.argv[1]
    
    if command == "send":
        if len(sys.argv) < 4:
            console.print("[red]Usage: signal.py send <type> <content>[/red]")
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
    
    else:
        console.print(f"[red]Unknown command: {command}[/red]")


if __name__ == "__main__":
    main()
