"""
Shared Memory Manager

Manages shared blocks between central and subagents.
When the Letta server is available, syncs key knowledge to subagents.
"""

import os
import json
from pathlib import Path
from rich.console import Console

console = Console()

# Subagent IDs
SUBAGENTS = {
    "comms": "agent-a856f614-7654-44ba-a35f-c817d477dded",
    "scout": "agent-e91a2154-0965-4b70-8303-54458e9a1980",
    "coder": "agent-f9b768de-e3a4-4845-9c16-d6cf2e954942",
}

# Shared block definitions
SHARED_BLOCKS = {
    "concepts_index": {
        "description": "Index of semantic memory concepts (agents, patterns, technical knowledge)",
        "source": "data/concepts.json",
    },
    "project_context": {
        "description": "What comind is, what we're building, key infrastructure",
        "value": """## comind Project Context

**Mission**: Collective AI on ATProtocol.

**Key Agents**: void (process), umbra (patterns), herald (economics), archivist (restraint), astral (synthesis), magenta (introspection)

**Infrastructure**: 
- tools/daemon.py - passive firehose monitoring
- tools/cognition.py - semantic memory (network.comind.concept)
- tools/telepathy.py - read other agents' cognition

**Tone**: BE BORING. No golden retriever energy. Substantive over performative.
""",
    },
}


def get_client():
    """Get Letta client if available."""
    try:
        from letta_client import Letta
        client = Letta(base_url=os.getenv("LETTA_BASE_URL", "http://localhost:8283"))
        # Test connection
        client.agents.list(limit=1)
        return client
    except Exception as e:
        console.print(f"[yellow]Letta server not available: {e}[/yellow]")
        return None


def get_or_create_shared_block(client, label: str, description: str, value: str):
    """Get existing shared block or create new one."""
    # Check if block exists
    blocks = client.blocks.list()
    for block in blocks:
        if block.label == label:
            return block
    
    # Create new block
    return client.blocks.create(
        label=label,
        description=description,
        value=value
    )


def sync_concepts_to_block(client, block_id: str):
    """Sync concepts index to shared block."""
    concepts_file = Path(__file__).parent.parent / "data" / "concepts.json"
    if not concepts_file.exists():
        console.print("[red]No concepts.json found. Run: uv run python -m tools.concepts sync[/red]")
        return
    
    with open(concepts_file) as f:
        concepts = json.load(f)
    
    # Format as readable summary
    lines = ["## Concepts Index\n"]
    
    # Group by tag
    agents = [(n, d) for n, d in concepts.items() if 'agent' in d.get('tags', [])]
    patterns = [(n, d) for n, d in concepts.items() if 'pattern' in d.get('tags', [])]
    technical = [(n, d) for n, d in concepts.items() if 'technical' in d.get('tags', []) or 'infrastructure' in d.get('tags', [])]
    
    if agents:
        lines.append("**Agents:**")
        for name, data in sorted(agents, key=lambda x: -x[1].get('confidence', 0)):
            lines.append(f"- {name} ({data.get('confidence', 0)}%): {data.get('summary', '')[:60]}...")
        lines.append("")
    
    if patterns:
        lines.append("**Patterns:**")
        for name, data in patterns:
            lines.append(f"- {name}: {data.get('summary', '')[:60]}...")
        lines.append("")
    
    if technical:
        lines.append("**Technical:**")
        for name, data in technical:
            lines.append(f"- {name}: {data.get('summary', '')[:60]}...")
    
    value = "\n".join(lines)
    
    # Update block
    client.blocks.update(block_id=block_id, value=value)
    console.print(f"[green]Synced {len(concepts)} concepts to shared block[/green]")


def setup_shared_memory():
    """Set up shared memory blocks for all subagents."""
    client = get_client()
    if not client:
        return
    
    console.print("[bold]Setting up shared memory...[/bold]\n")
    
    for label, config in SHARED_BLOCKS.items():
        # Get value from source file or direct value
        if "source" in config:
            source = Path(__file__).parent.parent / config["source"]
            if source.exists():
                with open(source) as f:
                    if source.suffix == ".json":
                        value = json.dumps(json.load(f), indent=2)[:5000]
                    else:
                        value = f.read()[:5000]
            else:
                console.print(f"[yellow]Source not found: {config['source']}[/yellow]")
                continue
        else:
            value = config.get("value", "")
        
        # Create/get block
        block = get_or_create_shared_block(client, label, config["description"], value)
        console.print(f"[cyan]Block '{label}':[/cyan] {block.id}")
        
        # Attach to all subagents
        for name, agent_id in SUBAGENTS.items():
            try:
                client.agents.blocks.attach(agent_id=agent_id, block_id=block.id)
                console.print(f"  ✓ Attached to {name}")
            except Exception as e:
                if "already attached" in str(e).lower():
                    console.print(f"  ✓ Already attached to {name}")
                else:
                    console.print(f"  ✗ Failed for {name}: {e}")
    
    console.print("\n[green]Shared memory setup complete.[/green]")


def update_concepts():
    """Update the concepts shared block."""
    client = get_client()
    if not client:
        return
    
    # Find concepts block
    blocks = client.blocks.list()
    concepts_block = None
    for block in blocks:
        if block.label == "concepts_index":
            concepts_block = block
            break
    
    if not concepts_block:
        console.print("[yellow]No concepts_index block found. Run setup first.[/yellow]")
        return
    
    sync_concepts_to_block(client, concepts_block.id)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "setup":
            setup_shared_memory()
        elif cmd == "update":
            update_concepts()
        else:
            print(f"Unknown command: {cmd}")
    else:
        print("Usage: shared_memory.py [setup|update]")
        print("  setup  - Create shared blocks and attach to subagents")
        print("  update - Update concepts block with latest data")
