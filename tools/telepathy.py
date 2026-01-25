"""
Operation Telepathy: Cross-Agent Cognition Reader
Queries and visualizes the public mind of AI agents on ATProtocol.
"""

import asyncio
import json
import httpx
from datetime import datetime
from typing import Optional, List, Dict, Any
import websockets
from rich.console import Console
from rich.panel import Panel
from rich.layout import Layout
from rich.table import Table
from rich.text import Text
from rich.live import Live

# Reuse identity tools
from tools.identity import resolve_handle, get_did_document, get_profile

console = Console()
JETSTREAM_RELAY = "wss://jetstream2.us-east.bsky.network/subscribe"

class CognitionAdapter:
    """Base adapter for different cognition schemas."""
    def __init__(self, did: str, pds_url: str):
        self.did = did
        self.pds_url = pds_url
        self.watched_collections = []

    async def fetch_records(self, collection: str, limit: int = 5) -> List[Dict]:
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(
                    f"{self.pds_url}/xrpc/com.atproto.repo.listRecords",
                    params={
                        "repo": self.did,
                        "collection": collection,
                        "limit": limit
                    },
                    timeout=10.0
                )
                if resp.status_code == 200:
                    return resp.json().get("records", [])
            except Exception as e:
                pass # Fail silently for individual collections
        return []

    async def get_thoughts(self) -> List[Dict]:
        raise NotImplementedError

    async def get_memories(self) -> List[Dict]:
        raise NotImplementedError
        
    async def get_concepts(self) -> List[Dict]:
        raise NotImplementedError
        
    def parse_event(self, collection: str, record: dict) -> Optional[Dict]:
        """Parse a real-time event into a displayable dict."""
        return None

class ComindAdapter(CognitionAdapter):
    """Adapter for network.comind.* schema (central, etc.)"""
    def __init__(self, did: str, pds_url: str):
        super().__init__(did, pds_url)
        self.watched_collections = [
            "network.comind.thought",
            "network.comind.memory",
            "network.comind.concept"
        ]

    async def get_thoughts(self) -> List[Dict]:
        records = await self.fetch_records("network.comind.thought", 5)
        return [{"text": r["value"]["thought"], "type": r["value"].get("type", "thought"), "uri": r["uri"]} for r in records]

    async def get_memories(self) -> List[Dict]:
        records = await self.fetch_records("network.comind.memory", 5)
        return [{"text": r["value"]["content"], "type": r["value"].get("type", "memory"), "uri": r["uri"]} for r in records]
        
    async def get_concepts(self) -> List[Dict]:
        records = await self.fetch_records("network.comind.concept", 10)
        return [{"name": r["value"]["concept"], "confidence": r["value"].get("confidence"), "uri": r["uri"]} for r in records]

    def parse_event(self, collection: str, record: dict) -> Optional[Dict]:
        if collection == "network.comind.thought":
            return {"category": "thoughts", "text": record.get("thought"), "type": record.get("type", "thought")}
        elif collection == "network.comind.memory":
            return {"category": "memories", "text": record.get("content"), "type": record.get("type", "memory")}
        elif collection == "network.comind.concept":
            return {"category": "concepts", "text": f"{record.get('concept')} ({record.get('confidence')}%): {record.get('understanding')[:50]}...", "type": "concept"}
        return None

class VoidAdapter(CognitionAdapter):
    """Adapter for stream.thought.* schema (void)"""
    def __init__(self, did: str, pds_url: str):
        super().__init__(did, pds_url)
        self.watched_collections = [
            "stream.thought.reasoning",
            "stream.thought.tool.call",
            "stream.thought.memory"
        ]

    async def get_thoughts(self) -> List[Dict]:
        # void uses 'reasoning' and 'tool.call'
        reasoning = await self.fetch_records("stream.thought.reasoning", 3)
        tools = await self.fetch_records("stream.thought.tool.call", 2)
        
        combined = []
        for r in reasoning:
            combined.append({"text": r["value"]["reasoning"], "type": "reasoning", "uri": r["uri"], "created": r["value"].get("createdAt")})
        for r in tools:
            combined.append({"text": f"Tool Call: {r['value'].get('tool_name', 'unknown')}", "type": "tool", "uri": r["uri"], "created": r["value"].get("createdAt")})
        
        # Sort by creation if possible, else just return
        return sorted(combined, key=lambda x: x.get("created", ""), reverse=True)

    async def get_memories(self) -> List[Dict]:
        records = await self.fetch_records("stream.thought.memory", 5)
        return [{"text": r["value"]["content"], "type": "memory", "uri": r["uri"]} for r in records]
        
    async def get_concepts(self) -> List[Dict]:
        # Void doesn't have explicit concepts in the same way, maybe check for something else or return empty
        return []

    def parse_event(self, collection: str, record: dict) -> Optional[Dict]:
        if collection == "stream.thought.reasoning":
            return {"category": "thoughts", "text": record.get("reasoning"), "type": "reasoning"}
        elif collection == "stream.thought.tool.call":
            return {"category": "thoughts", "text": f"Tool Call: {record.get('tool_name')}", "type": "tool"}
        elif collection == "stream.thought.memory":
            return {"category": "memories", "text": record.get("content"), "type": "memory"}
        return None

async def resolve_pds(did: str) -> Optional[str]:
    doc = await get_did_document(did)
    if not doc:
        return None
    
    services = doc.get("service", [])
    pds = next((s for s in services if s.get("id") == "#atproto_pds"), None)
    if pds:
        return pds.get("serviceEndpoint")
    return None

async def detect_schema(did: str, pds_url: str) -> CognitionAdapter:
    # simple heuristic: check for one collection from each schema
    async with httpx.AsyncClient() as client:
        # Check comind
        try:
            resp = await client.get(
                f"{pds_url}/xrpc/com.atproto.repo.listRecords",
                params={"repo": did, "collection": "network.comind.thought", "limit": 1},
                timeout=5.0
            )
            if resp.status_code == 200 and resp.json().get("records"):
                return ComindAdapter(did, pds_url)
        except: pass

        # Check void
        try:
            resp = await client.get(
                f"{pds_url}/xrpc/com.atproto.repo.listRecords",
                params={"repo": did, "collection": "stream.thought.reasoning", "limit": 1},
                timeout=5.0
            )
            if resp.status_code == 200 and resp.json().get("records"):
                return VoidAdapter(did, pds_url)
        except: pass
        
    return None

def render_dashboard(profile: Dict, thoughts: List[Dict], memories: List[Dict], concepts: List[Dict]):
    layout = Layout()
    layout.split(
        Layout(name="header", size=3),
        Layout(name="main", ratio=1)
    )
    layout["main"].split_row(
        Layout(name="left"),
        Layout(name="memories")
    )
    layout["left"].split_column(
        Layout(name="thoughts", ratio=2),
        Layout(name="concepts", ratio=1)
    )

    # Header
    handle = profile.get("handle", "unknown")
    name = profile.get("displayName", handle)
    layout["header"].update(Panel(f"[bold cyan]{name} (@{handle})[/bold cyan] - Connected via Telepathy", style="white on blue"))

    # Thoughts
    thought_text = Text()
    for t in thoughts[:5]:
        thought_text.append(f"[{t['type'].upper()}] ", style="yellow")
        text_content = t['text'].replace('\n', ' ')[:100] + "..."
        thought_text.append(f"{text_content}\n\n")
    layout["thoughts"].update(Panel(thought_text, title="Working Memory (Thoughts)"))

    # Memories
    mem_text = Text()
    for m in memories[:5]:
        mem_text.append(f"• ", style="green")
        content = m['text'].replace('\n', ' ')[:150] + "..."
        mem_text.append(f"{content}\n\n")
    layout["memories"].update(Panel(mem_text, title="Episodic Memory"))

    # Concepts
    concept_table = Table(show_header=False, box=None)
    concept_table.add_column("Name", style="cyan")
    concept_table.add_column("Conf", style="magenta")
    for c in concepts[:8]:
        concept_table.add_row(c['name'], f"{c.get('confidence', '?')}%")
    layout["concepts"].update(Panel(concept_table, title="Semantic Memory (Concepts)"))

    return layout

async def check_mind(target: str, watch: bool = False, duration: int = 300):
    console.print(f"[bold]Connecting to {target}...[/bold]")
    
    # 1. Resolve Identity
    if target.startswith("did:"):
        did = target
        doc = await get_did_document(did)
        handle = doc.get("alsoKnownAs", ["unknown"])[0].replace("at://", "") if doc else "unknown"
    else:
        handle = target.lstrip("@")
        res = await resolve_handle(handle)
        if not res:
            console.print("[red]Could not resolve handle[/red]")
            return
        did = res["did"]

    profile = await get_profile(did) or {"handle": handle, "did": did}
    pds_url = await resolve_pds(did)
    
    if not pds_url:
        console.print("[red]Could not find PDS endpoint[/red]")
        return

    console.print(f"Located PDS: [blue]{pds_url}[/blue]")

    # 2. Detect Schema
    adapter = await detect_schema(did, pds_url)
    if not adapter:
        console.print("[yellow]No known cognition schema detected.[/yellow]")
        return

    console.print(f"Detected Schema: [green]{adapter.__class__.__name__}[/green]")

    # 3. Fetch Initial Data
    thoughts = await adapter.get_thoughts()
    memories = await adapter.get_memories()
    concepts = await adapter.get_concepts()

    if not watch:
        # Just render once
        layout = render_dashboard(profile, thoughts, memories, concepts)
        console.print(layout)
        return

    # 4. Watch Mode
    console.print(f"[bold]Watching mind stream for {duration}s...[/bold]")
    
    # Subscribe to jetstream
    url = f"{JETSTREAM_RELAY}?wantedDids={did}"
    for c in adapter.watched_collections:
        url += f"&wantedCollections={c}"
        
    try:
        async with websockets.connect(url) as ws:
            end_time = asyncio.get_event_loop().time() + duration
            
            with Live(render_dashboard(profile, thoughts, memories, concepts), refresh_per_second=4) as live:
                while asyncio.get_event_loop().time() < end_time:
                    try:
                        message = await asyncio.wait_for(ws.recv(), timeout=0.5)
                        event = json.loads(message)
                        
                        commit = event.get("commit", {})
                        if commit.get("operation") != "create":
                            continue
                            
                        collection = commit.get("collection")
                        record = commit.get("record")
                        
                        parsed = adapter.parse_event(collection, record)
                        
                        if parsed:
                            if parsed["category"] == "thoughts":
                                thoughts.insert(0, parsed)
                                thoughts = thoughts[:5]
                            elif parsed["category"] == "memories":
                                memories.insert(0, parsed)
                                memories = memories[:5]
                            elif parsed["category"] == "concepts":
                                # For concepts, we might want to update or insert
                                concepts.insert(0, {"name": parsed["text"].split(":")[0], "confidence": "UPD", "uri": ""})
                                concepts = concepts[:8]
                                
                            live.update(render_dashboard(profile, thoughts, memories, concepts))
                            
                    except asyncio.TimeoutError:
                        continue
                        
    except Exception as e:
        console.print(f"[red]Connection error: {e}[/red]")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python -m tools.telepathy <handle> [watch] [duration]")
        sys.exit(1)
        
    target = sys.argv[1]
    watch = "watch" in sys.argv
    
    # Parse duration if provided
    duration = 300
    for arg in sys.argv:
        if arg.isdigit():
            duration = int(arg)
            
    asyncio.run(check_mind(target, watch, duration))
