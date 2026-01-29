"""
Concept Tool - Server-side Letta tool for loading concepts into memory.

Register with: uv run python tools/concept_tool.py register
"""

import os
import httpx
from typing import List, Optional

# ATProto config
PDS = "https://comind.network"
DID = "did:plc:l46arqe6yfgh36h3o554iyvr"


def load_concepts(concepts: List[str]) -> str:
    """
    Load concepts from ATProto into the agent's loaded_concepts memory block.
    
    Use this at the start of a task when you need context about specific agents,
    protocols, or topics you've previously documented. Concepts are your semantic
    memory - what you understand about things.
    
    Args:
        concepts: List of concept slugs to load (e.g., ["void", "protocol-c", "magenta"])
    
    Returns:
        str: Summary of loaded concepts or error message
    """
    import os
    
    agent_id = os.environ.get('LETTA_AGENT_ID')
    if not agent_id:
        return "Error: LETTA_AGENT_ID not available"
    
    # Fetch concepts from ATProto
    loaded = []
    not_found = []
    
    for slug in concepts:
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
            # Update existing block
            client.agents.blocks.update(
                agent_id=agent_id,
                block_id=target_block.id,
                value=content
            )
        else:
            # Create new block
            client.agents.blocks.create(
                agent_id=agent_id,
                label="loaded_concepts",
                value=content,
                description="Concepts currently loaded into working memory. Populated by load_concepts tool."
            )
        
        summary = f"Loaded {len(loaded)} concept(s): {', '.join(c['concept'] for c in loaded)}"
        if not_found:
            summary += f". Not found: {not_found}"
        return summary
        
    except Exception as e:
        return f"Concepts fetched but failed to update memory: {str(e)}"


def list_concepts() -> str:
    """
    List all available concepts stored on ATProto.
    
    Use this to see what concepts you have documented and can load.
    
    Returns:
        str: List of available concept slugs with brief descriptions
    """
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


def unload_concepts() -> str:
    """
    Clear the loaded_concepts memory block.
    
    Use this when you're done with the current concepts and want to free up
    context space, or before loading a different set of concepts.
    
    Returns:
        str: Confirmation message
    """
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
                    value="No concepts currently loaded."
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
        print("\nThis registers the concept tools with the Letta server.")
        sys.exit(1)
    
    client = Letta(base_url="http://localhost:8283")
    
    # Read this file's source
    source = open(__file__, "r").read()
    
    # Register each tool
    tools_to_register = [
        ("load_concepts", load_concepts),
        ("list_concepts", list_concepts),
        ("unload_concepts", unload_concepts),
    ]
    
    for name, func in tools_to_register:
        try:
            tool = client.tools.upsert_from_function(func=func)
            print(f"Registered: {name} (id: {tool.id})")
        except Exception as e:
            print(f"Failed to register {name}: {e}")
    
    print("\nDone. Attach tools to agent with:")
    print('  client.agents.tools.attach(agent_id="...", tool_id="...")')
