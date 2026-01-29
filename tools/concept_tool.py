"""
Concepts Tool - Server-side Letta tool for managing concept memory.

Single tool with subcommands, like the Skill tool pattern.

Register with: uv run python tools/concept_tool.py register
"""

from typing import List, Optional

# ATProto config - hardcoded for comind
PDS = "https://comind.network"
DID = "did:plc:l46arqe6yfgh36h3o554iyvr"


def concepts(command: str, concept_list: Optional[List[str]] = None) -> str:
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
        concept_list: List of concept slugs to load (required for "load" command).
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
    
    PDS = "https://comind.network"
    DID = "did:plc:l46arqe6yfgh36h3o554iyvr"
    
    if command == "list":
        # List all available concepts
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
    
    elif command == "load":
        # Load specified concepts into memory block
        if not concept_list:
            return "Error: 'concept_list' parameter required for load command"
        
        agent_id = os.environ.get('LETTA_AGENT_ID')
        if not agent_id:
            return "Error: LETTA_AGENT_ID not available"
        
        # Fetch concepts from ATProto
        loaded = []
        not_found = []
        
        for slug in concept_list:
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
            blocks = client.agents.blocks.list(agent_id=agent_id)
            target_block = None
            for block in blocks:
                if block.label == "loaded_concepts":
                    target_block = block
                    break
            
            if target_block:
                client.agents.blocks.update(
                    "loaded_concepts",
                    agent_id=agent_id,
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
    
    elif command == "unload":
        # Clear the loaded_concepts memory block
        agent_id = os.environ.get('LETTA_AGENT_ID')
        if not agent_id:
            return "Error: LETTA_AGENT_ID not available"
        
        try:
            blocks = client.agents.blocks.list(agent_id=agent_id)
            for block in blocks:
                if block.label == "loaded_concepts":
                    client.agents.blocks.update(
                        "loaded_concepts",
                        agent_id=agent_id,
                        value="No concepts currently loaded.\n\nUse concepts(\"load\", [\"slug1\", \"slug2\"]) to load relevant concepts."
                    )
                    return "Concepts unloaded."
            
            return "No loaded_concepts block found."
            
        except Exception as e:
            return f"Error unloading concepts: {str(e)}"
    
    else:
        return f"Unknown command: {command}. Use 'load', 'unload', or 'list'."


# Registration script
if __name__ == "__main__":
    import sys
    import os
    from letta_client import Letta
    
    if len(sys.argv) < 2 or sys.argv[1] != "register":
        print("Usage: uv run python tools/concept_tool.py register")
        print("\nThis registers the concepts tool with the Letta server.")
        sys.exit(1)
    
    api_key = os.environ.get('LETTA_API_KEY')
    if not api_key:
        print("Error: LETTA_API_KEY not set")
        sys.exit(1)
    
    client = Letta(api_key=api_key)
    
    try:
        tool = client.tools.upsert_from_function(func=concepts)
        print(f"Registered: concepts (id: {tool.id})")
        
        agent_id = os.environ.get('LETTA_AGENT_ID', 'agent-c770d1c8-510e-4414-be36-c9ebd95a7758')
        print(f"\nAttach to agent with:")
        print(f'  client.agents.tools.attach(agent_id="{agent_id}", tool_id="{tool.id}")')
    except Exception as e:
        print(f"Failed to register: {e}")
