"""
Recall Tool - Query past thoughts, concepts, and memories semantically.

This is a simplified interface to cognition_search for use during conversation.

Usage:
    # Search my cognition
    uv run python -m tools.recall "what did I learn about memory"
    
    # Search with more results
    uv run python -m tools.recall "agent coordination" --limit 10
    
    # Search specific agent
    uv run python -m tools.recall "identity" --agent void
"""

import argparse
import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.cognition_search import get_client, get_collection, KNOWN_AGENTS


def recall(query: str, limit: int = 5, agent: str = None) -> list[dict]:
    """
    Search cognition records semantically.
    
    Returns list of matching records with text and metadata.
    """
    client = get_client()
    collection = get_collection(client)
    
    # Build query params
    query_params = {
        "query_texts": [query],
        "n_results": limit,
    }
    
    if agent and agent in KNOWN_AGENTS:
        query_params["where"] = {"agent": agent}
    
    results = collection.query(**query_params)
    
    if not results or not results["ids"][0]:
        return []
    
    matches = []
    for i, (id_, doc, metadata, distance) in enumerate(zip(
        results["ids"][0],
        results["documents"][0],
        results["metadatas"][0],
        results["distances"][0]
    )):
        matches.append({
            "text": doc,
            "type": metadata.get("type", "unknown"),
            "agent": metadata.get("agent", "central"),
            "distance": round(distance, 3),
            "uri": id_
        })
    
    return matches


def main():
    parser = argparse.ArgumentParser(description="Recall past cognition")
    parser.add_argument("query", help="What to search for")
    parser.add_argument("--limit", "-n", type=int, default=5, help="Max results")
    parser.add_argument("--agent", "-a", help="Filter by agent name")
    
    args = parser.parse_args()
    
    results = recall(args.query, args.limit, args.agent)
    
    if not results:
        print("No matching memories found.")
        return
    
    print(f"Found {len(results)} relevant memories:\n")
    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['agent']}/{r['type']}] (dist: {r['distance']})")
        # Truncate long text
        text = r['text']
        if len(text) > 150:
            text = text[:150] + "..."
        print(f"   {text}\n")


if __name__ == "__main__":
    main()
