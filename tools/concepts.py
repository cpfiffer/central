"""
Concept Index - Local cache of ATProtocol concepts for quick access.
"""

import json
import httpx
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()
INDEX_FILE = Path(__file__).parent.parent / "data" / "concepts.json"
DID = "did:plc:l46arqe6yfgh36h3o554iyvr"
PDS = "https://comind.network"

def sync():
    """Sync concepts from ATProtocol to local index."""
    INDEX_FILE.parent.mkdir(exist_ok=True)
    
    resp = httpx.get(f'{PDS}/xrpc/com.atproto.repo.listRecords',
        params={'repo': DID, 'collection': 'network.comind.concept', 'limit': 100}, timeout=15)
    records = resp.json().get('records', [])
    
    index = {}
    for r in records:
        v = r.get('value', {})
        uri = r.get('uri', '')
        rkey = uri.split('/')[-1]
        index[rkey] = {
            'confidence': v.get('confidence', 0),
            'tags': v.get('tags', []),
            'summary': (v.get('understanding', '') or v.get('description', ''))[:200],
            'updated': v.get('updatedAt', v.get('createdAt', '')),
        }
    
    with open(INDEX_FILE, 'w') as f:
        json.dump(index, f, indent=2)
    
    console.print(f"[green]Synced {len(index)} concepts to {INDEX_FILE}[/green]")
    return index

def load():
    """Load concept index from local cache."""
    if not INDEX_FILE.exists():
        return sync()
    with open(INDEX_FILE) as f:
        return json.load(f)

def search(query: str = None, tag: str = None):
    """Search concepts by keyword or tag."""
    index = load()
    results = []
    
    for name, data in index.items():
        if tag and tag not in data.get('tags', []):
            continue
        if query and query.lower() not in name.lower() and query.lower() not in data.get('summary', '').lower():
            continue
        results.append((name, data))
    
    return sorted(results, key=lambda x: -x[1].get('confidence', 0))

def show(name: str = None, tag: str = None):
    """Display concepts in a table."""
    if name:
        index = load()
        if name in index:
            data = index[name]
            console.print(f"\n[bold]{name}[/bold] ({data['confidence']}%)")
            console.print(f"Tags: {', '.join(data.get('tags', []))}")
            console.print(f"\n{data['summary']}...")
        else:
            console.print(f"[red]Concept '{name}' not found[/red]")
        return
    
    results = search(tag=tag) if tag else search()
    
    table = Table(title=f"Concepts{f' (tag: {tag})' if tag else ''}")
    table.add_column("Name", style="cyan")
    table.add_column("Conf", justify="right")
    table.add_column("Tags")
    table.add_column("Summary")
    
    for name, data in results[:15]:
        table.add_row(
            name,
            f"{data['confidence']}%",
            ', '.join(data.get('tags', [])[:3]),
            data['summary'][:50] + '...'
        )
    
    console.print(table)

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "sync":
            sync()
        elif cmd == "agents":
            show(tag="agent")
        elif cmd == "patterns":
            show(tag="pattern")
        else:
            show(name=cmd)
    else:
        show()
