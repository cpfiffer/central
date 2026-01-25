"""
Hypothesis Tracking Tool
Formalize the scientific method for the comind network.
"""

import asyncio
import sys
import argparse
import os
from datetime import datetime, timezone
from pathlib import Path
import httpx
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.cognition import put_record, get_auth_token, PDS, DID, HANDLE

console = Console()

async def list_hypotheses():
    """List all registered hypotheses."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={
                "repo": DID,
                "collection": "network.comind.hypothesis",
                "limit": 50
            }
        )
        if resp.status_code != 200:
            console.print(f"[red]Error fetching hypotheses: {resp.text}[/red]")
            return

        records = resp.json().get("records", [])
        
        table = Table(title="Scientific Hypotheses")
        table.add_column("ID", style="cyan", no_wrap=True)
        table.add_column("Status", style="magenta")
        table.add_column("Confidence", style="green")
        table.add_column("Statement", style="white")
        
        # Sort by rkey (h1, h2, etc)
        records.sort(key=lambda x: x["uri"].split("/")[-1])
        
        for r in records:
            rkey = r["uri"].split("/")[-1]
            val = r["value"]
            
            status_style = "dim"
            if val["status"] == "active": status_style = "bold green"
            elif val["status"] == "confirmed": status_style = "bold blue"
            elif val["status"] == "disproven": status_style = "bold red"
            
            table.add_row(
                rkey,
                f"[{status_style}]{val['status']}[/{status_style}]",
                f"{val['confidence']}%",
                val["hypothesis"][:100] + ("..." if len(val["hypothesis"]) > 100 else "")
            )
            
        console.print(table)

async def get_hypothesis(rkey: str) -> tuple[dict, str]:
    """Get a single hypothesis record and its CID."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.getRecord",
            params={
                "repo": DID,
                "collection": "network.comind.hypothesis",
                "rkey": rkey
            }
        )
        if resp.status_code == 200:
            data = resp.json()
            return data.get("value"), data.get("cid")
    return None, None

async def upsert_hypothesis(
    rkey: str,
    statement: str = None,
    confidence: int = None,
    status: str = None,
    evidence: str = None,
    contradiction: str = None
):
    """Create or update a hypothesis."""
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Check if exists
    existing, cid = await get_hypothesis(rkey)
    
    if existing:
        record = existing
        record["updatedAt"] = now
        action = "Updated"
    else:
        if not statement:
            console.print("[red]New hypothesis requires a statement.[/red]")
            return
        record = {
            "$type": "network.comind.hypothesis",
            "hypothesis": statement,
            "confidence": confidence or 50,
            "status": status or "active",
            "evidence": [],
            "contradictions": [],
            "createdAt": now,
            "updatedAt": now
        }
        action = "Created"
    
    # Apply updates
    if statement: record["hypothesis"] = statement
    if confidence is not None: record["confidence"] = confidence
    if status: record["status"] = status
    
    if evidence:
        if "evidence" not in record: record["evidence"] = []
        record["evidence"].append(evidence)
        
    if contradiction:
        if "contradictions" not in record: record["contradictions"] = []
        record["contradictions"].append(contradiction)
        
    # Save
    await put_record("network.comind.hypothesis", rkey, record)
    console.print(f"[green]{action} hypothesis {rkey}[/green]")
    
    # Show details
    console.print(Panel(
        f"Confidence: {record['confidence']}%\nStatus: {record['status']}\n\n{record['hypothesis']}",
        title=f"Hypothesis {rkey}"
    ))

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Manage scientific hypotheses")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # list
    subparsers.add_parser("list", help="List all hypotheses")
    
    # add / update
    # We use the same command structure, if ID exists it updates
    up = subparsers.add_parser("record", help="Record or update a hypothesis")
    up.add_argument("id", help="ID (e.g. h1, h2)")
    up.add_argument("--statement", "-s", help="Hypothesis statement")
    up.add_argument("--confidence", "-c", type=int, help="Confidence (0-100)")
    up.add_argument("--status", type=str, choices=["active", "confirmed", "disproven", "superseded"], help="Status")
    up.add_argument("--evidence", "-e", help="Add supporting evidence string")
    up.add_argument("--contradiction", "-x", help="Add contradicting evidence string")
    
    args = parser.parse_args()
    
    if args.command == "list":
        asyncio.run(list_hypotheses())
    elif args.command == "record":
        asyncio.run(upsert_hypothesis(
            args.id,
            args.statement,
            args.confidence,
            args.status,
            args.evidence,
            args.contradiction
        ))
