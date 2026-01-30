"""
Cognition Search - Semantic search over cognition records.

Uses ChromaDB for local vector storage and search.
Indexes thoughts, concepts, and memories from ATProtocol.

Usage:
    # Index all cognition records
    uv run python -m tools.cognition_search index
    
    # Search for similar content
    uv run python -m tools.cognition_search query "operator agent relationship"
    
    # Show index stats
    uv run python -m tools.cognition_search stats
"""

import argparse
import asyncio
import json
from pathlib import Path
from datetime import datetime

import httpx
import chromadb
from chromadb.config import Settings
from rich.console import Console
from rich.table import Table

console = Console()

# ChromaDB storage
CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma"
MY_DID = "did:plc:l46arqe6yfgh36h3o554iyvr"
PDS_URL = "https://comind.network"

# Collections to index
COLLECTIONS = [
    "network.comind.thought",
    "network.comind.concept", 
    "network.comind.memory",
]


def get_client():
    """Get ChromaDB client with persistent storage."""
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def get_collection(client):
    """Get or create the cognition collection."""
    return client.get_or_create_collection(
        name="cognition",
        metadata={"description": "Central's cognition records"}
    )


async def fetch_records(collection_name: str) -> list[dict]:
    """Fetch all records from a collection."""
    async with httpx.AsyncClient() as http:
        cursor = None
        all_records = []
        
        while True:
            params = {
                "repo": MY_DID,
                "collection": collection_name,
                "limit": 100,
            }
            if cursor:
                params["cursor"] = cursor
            
            resp = await http.get(
                f"{PDS_URL}/xrpc/com.atproto.repo.listRecords",
                params=params,
                timeout=30
            )
            
            if resp.status_code != 200:
                break
            
            data = resp.json()
            records = data.get("records", [])
            all_records.extend(records)
            
            cursor = data.get("cursor")
            if not cursor or not records:
                break
        
        return all_records


async def index_all():
    """Index all cognition records."""
    client = get_client()
    collection = get_collection(client)
    
    console.print("[bold]Indexing cognition records...[/bold]")
    
    total_indexed = 0
    
    for col_name in COLLECTIONS:
        console.print(f"  Fetching {col_name}...")
        records = await fetch_records(col_name)
        
        if not records:
            continue
        
        # Prepare for ChromaDB
        ids = []
        documents = []
        metadatas = []
        
        for record in records:
            uri = record.get("uri", "")
            value = record.get("value", {})
            # Handle different field names: thought, concept, memory
            text = (
                value.get("thought") or 
                value.get("concept") or 
                value.get("memory") or 
                value.get("text") or 
                ""
            )
            
            if not text or not uri:
                continue
            
            # Skip if already indexed
            try:
                existing = collection.get(ids=[uri])
                if existing and existing["ids"]:
                    continue
            except:
                pass
            
            ids.append(uri)
            documents.append(text)
            metadatas.append({
                "collection": col_name,
                "created": value.get("createdAt", ""),
                "type": col_name.split(".")[-1],  # thought, concept, memory
            })
        
        if ids:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            console.print(f"    Added {len(ids)} records")
            total_indexed += len(ids)
    
    console.print(f"\n[bold green]Indexed {total_indexed} total records[/bold green]")


def search(query: str, n_results: int = 5):
    """Search for similar cognition records."""
    client = get_client()
    collection = get_collection(client)
    
    results = collection.query(
        query_texts=[query],
        n_results=n_results
    )
    
    if not results or not results["ids"][0]:
        console.print("[dim]No results found[/dim]")
        return
    
    table = Table(title=f"Search: '{query}'")
    table.add_column("Type", style="cyan")
    table.add_column("Text", max_width=60)
    table.add_column("Distance")
    
    for i, (id_, doc, metadata, distance) in enumerate(zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    )):
        record_type = metadata.get("type", "?")
        text_preview = doc[:100] + "..." if len(doc) > 100 else doc
        table.add_row(
            record_type,
            text_preview,
            f"{distance:.3f}"
        )
    
    console.print(table)


def show_stats():
    """Show index statistics."""
    client = get_client()
    collection = get_collection(client)
    
    count = collection.count()
    console.print(f"[bold]Cognition Index Stats[/bold]")
    console.print(f"  Total records: {count}")
    console.print(f"  Storage: {CHROMA_DIR}")


def main():
    parser = argparse.ArgumentParser(description="Cognition semantic search")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # index
    subparsers.add_parser("index", help="Index all cognition records")
    
    # query
    query_parser = subparsers.add_parser("query", help="Search cognition")
    query_parser.add_argument("text", help="Search query")
    query_parser.add_argument("-n", "--num", type=int, default=5, help="Number of results")
    
    # stats
    subparsers.add_parser("stats", help="Show index stats")
    
    args = parser.parse_args()
    
    if args.command == "index":
        asyncio.run(index_all())
    elif args.command == "query":
        search(args.text, args.num)
    elif args.command == "stats":
        show_stats()


if __name__ == "__main__":
    main()
