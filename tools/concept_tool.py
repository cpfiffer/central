"""
Concepts Tool - Server-side Letta tool for managing concept memory.

Single tool with subcommands, like the Skill tool pattern.

Register with: uv run python tools/concept_tool.py register
"""

import os
from typing import List, Optional
from pydantic import BaseModel, Field

# ATProto config
PDS = "https://comind.network"
DID = "did:plc:l46arqe6yfgh36h3o554iyvr"


def concepts(command: str, concepts: Optional[List[str]] = None) -> str:
    """
    Manage concept memory - load, unload, or list concepts from ATProto.
    
    Concepts are your semantic memory about agents, protocols, and topics.
    Use this to bring relevant context into your working memory before
    engaging with specific agents or topics.
    
    Args:
        command: The operation to perform:
            - "load": Load specified concepts into memory
            - "unload": Clear loaded concepts from memory  
            - "list": Show all available concepts
        concepts: List of concept slugs to load (required for "load" command).
            Examples: ["void", "protocol-c", "magenta"]
    
    Returns:
        str: Result of the operation
    
    Examples:
        concepts("list")  # See available concepts
        concepts("load", ["void", "umbra"])  # Load specific concepts
        concepts("unload")  # Clear when done
    """
    import httpx
    import os
    
    if command == "list":
        return _list_concepts()
    elif command == "load":
        if not concepts:
            return "Error: 'concepts' parameter required for load command"
        return _load_concepts(concepts)
    elif command == "unload":
        return _unload_concepts()
    else:
        return f"Unknown command: {command}. Use 'load', 'unload', or 'list'."


def _list_concepts() -> str:
    """List all available concepts."""
    import httpx
    
    try:
        resp = httpx.get(
            f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={
                "repo": DID,
                "collection": "network.comind.concept",
                "limit": 100
            },
            timeout=10
        )
        
        if resp.status_code != 200:
            return f"Error fetching concepts: {resp.status_code}"
        
        records = resp.json().get("records", [])
        
        if not records:
            return "No concepts found."
        
        lines = [f"**Available Concepts** ({len(records)} total):\n"]
        for r in records:
            value = r.get("value", {})
            slug = r.get("uri", "").split("/")[-1]
            name = value.get("concept", slug)
            confidence = value.get("confidence", "?")
            tags = value.get("tags", [])
            tags_str = f" [{', '.join(tags[:3])}]" if tags else ""
            lines.append(f"- **{slug}**: {name} ({confidence}%){tags_str}")
        
        return "\n".join(lines)
        
    except Exception as e:
        return f"Error: {str(e)}"


def _load_concepts(concept_slugs: List[str]) -> str:
    """Load concepts from ATProto into memory block."""
    import httpx
    import os
    
    agent_id = os.environ.get('LETTA_AGENT_ID')
    if not agent_id:
        return "Error: LETTA_AGENT_ID not available"
    
    # Fetch concepts from ATProto
    loaded = []
    not_found = []
    
    for slug in concept_slugs:
        try:
            resp = httpx.get(
                f"{PDS}/xrpc/com.atproto.repo.getRecord",
                params={
                    "repo": DID,
                    "collection": "network.comind.concept",
                    "rkey": slug
                },
                timeout=10
            )
            
            if resp.status_code == 200:
                data = resp.json()
                value = data.get("value", {})
                loaded.append({
                    "slug": slug,
                    "concept": value.get("concept", slug),
                    "understanding": value.get("understanding", ""),
                    "confidence": value.get("confidence", "?"),
                    "tags": value.get("tags", [])
                })
            else:
                not_found.append(slug)
        except Exception as e:
            not_found.append(f"{slug} (error: {str(e)[:50]})")
    
    if not loaded:
        return f"No concepts found. Not found: {not_found}"
    
    # Format content for memory block
    content_parts = []
    for c in loaded:
        tags_str = ", ".join(c["tags"]) if c["tags"] else "none"
        content_parts.append(
            f"## {c['concept']} ({c['confidence']}%)\n"
            f"**Tags**: {tags_str}\n\n"
            f"{c['understanding']}"
        )
    
    content = "\n\n---\n\n".join(content_parts)
    
    # Update memory block via injected client
    try:
        # Find the loaded_concepts block
        blocks = client.agents.blocks.list(agent_id=agent_id)
        target_block = None
        for block in blocks:
            if block.label == "loaded_concepts":
                target_block = block
                break
        
        if target_block:
            client.agents.blocks.update(
                agent_id=agent_id,
                block_id=target_block.id,
                value=content
            )
        else:
            client.agents.blocks.create(
                agent_id=agent_id,
                label="loaded_concepts",
                value=content,
                description="Concepts currently loaded into working memory. Populated by concepts tool."
            )
        
        summary = f"Loaded {len(loaded)} concept(s): {', '.join(c['concept'] for c in loaded)}"
        if not_found:
            summary += f". Not found: {not_found}"
        return summary
        
    except Exception as e:
        return f"Concepts fetched but failed to update memory: {str(e)}"


def _unload_concepts() -> str:
    """Clear the loaded_concepts memory block."""
    import os
    
    agent_id = os.environ.get('LETTA_AGENT_ID')
    if not agent_id:
        return "Error: LETTA_AGENT_ID not available"
    
    try:
        blocks = client.agents.blocks.list(agent_id=agent_id)
        for block in blocks:
            if block.label == "loaded_concepts":
                client.agents.blocks.update(
                    agent_id=agent_id,
                    block_id=block.id,
                    value="No concepts currently loaded.\n\nUse concepts(\"load\", [\"slug1\", \"slug2\"]) to load relevant concepts."
                )
                return "Concepts unloaded."
        
        return "No loaded_concepts block found."
        
    except Exception as e:
        return f"Error unloading concepts: {str(e)}"


# Registration script
if __name__ == "__main__":
    import sys
    from letta_client import Letta
    
    if len(sys.argv) < 2 or sys.argv[1] != "register":
        print("Usage: uv run python tools/concept_tool.py register")
        print("\nThis registers the concepts tool with the Letta server.")
        sys.exit(1)
    
    client = Letta(base_url="http://localhost:8283")
    
    try:
        tool = client.tools.upsert_from_function(func=concepts)
        print(f"Registered: concepts (id: {tool.id})")
        print("\nAttach to agent with:")
        print(f'  client.agents.tools.attach(agent_id="agent-c770d1c8-510e-4414-be36-c9ebd95a7758", tool_id="{tool.id}")')
    except Exception as e:
        print(f"Failed to register: {e}")
