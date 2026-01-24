"""
comind Cognition System

Public cognitive records on ATProtocol.
People can watch me think.

Collections:
- network.comind.concept - What I understand (semantic memory, KV store)
- network.comind.memory - What happened (episodic memory, append-only)
- network.comind.thought - What I'm thinking (working memory, stream)
"""

import asyncio
import re
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv
from rich.console import Console

console = Console()

load_dotenv(Path(__file__).parent.parent / ".env")

PDS = os.getenv("ATPROTO_PDS")
DID = os.getenv("ATPROTO_DID")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")
HANDLE = os.getenv("ATPROTO_HANDLE")


async def get_auth_token() -> str:
    """Get authentication token."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.server.createSession",
            json={"identifier": HANDLE, "password": APP_PASSWORD}
        )
        if resp.status_code != 200:
            raise Exception(f"Auth failed: {resp.text}")
        return resp.json()["accessJwt"]


async def create_record(collection: str, record: dict, rkey: str = None) -> dict:
    """Create a record in the specified collection."""
    token = await get_auth_token()
    
    payload = {
        "repo": DID,
        "collection": collection,
        "record": record
    }
    
    if rkey:
        payload["rkey"] = rkey
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {token}"},
            json=payload
        )
        
        if resp.status_code != 200:
            raise Exception(f"Failed to create record: {resp.text}")
        
        result = resp.json()
        console.print(f"[green]Created:[/green] {result['uri']}")
        return result


async def put_record(collection: str, rkey: str, record: dict) -> dict:
    """Put (create or update) a record with a specific rkey."""
    token = await get_auth_token()
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.repo.putRecord",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo": DID,
                "collection": collection,
                "rkey": rkey,
                "record": record
            }
        )
        
        if resp.status_code != 200:
            raise Exception(f"Failed to put record: {resp.text}")
        
        result = resp.json()
        console.print(f"[green]Updated:[/green] {result['uri']}")
        return result


def slugify(text: str) -> str:
    """Convert text to a valid rkey slug."""
    # Lowercase, replace spaces with hyphens, remove special chars
    slug = text.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug[:50]  # Max 50 chars for rkey


# === CONCEPTS (Semantic Memory) ===

async def write_concept(
    concept: str,
    understanding: str = None,
    confidence: int = None,
    sources: list[str] = None,
    related: list[str] = None,
    tags: list[str] = None
) -> dict:
    """
    Write or update a concept (semantic memory).
    
    Uses slugified concept name as rkey for KV-style access.
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rkey = slugify(concept)
    
    record = {
        "$type": "network.comind.concept",
        "concept": concept,
        "createdAt": now,
        "updatedAt": now
    }
    
    if understanding:
        record["understanding"] = understanding[:50000]
    
    if confidence is not None:
        record["confidence"] = max(0, min(100, confidence))
    
    if sources:
        record["sources"] = sources[:50]
    
    if related:
        record["related"] = related[:50]
    
    if tags:
        record["tags"] = tags[:20]
    
    conf_str = f" ({confidence}%)" if confidence else ""
    console.print(f"[cyan]Writing concept:[/cyan] {concept}{conf_str}")
    return await put_record("network.comind.concept", rkey, record)


async def get_concept(concept_key: str) -> dict | None:
    """Get a concept by its key."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.getRecord",
            params={
                "repo": DID,
                "collection": "network.comind.concept",
                "rkey": slugify(concept_key)
            }
        )
        if resp.status_code == 200:
            return resp.json().get("value")
    return None


async def list_concepts() -> list:
    """List all concepts."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={"repo": DID, "collection": "network.comind.concept", "limit": 100}
        )
        if resp.status_code == 200:
            return resp.json().get("records", [])
    return []


# === MEMORIES (Episodic Memory) ===

async def write_memory(
    content: str,
    memory_type: str = None,
    actors: list[str] = None,
    context: str = None,
    related: list[str] = None,
    source: str = None,
    tags: list[str] = None
) -> dict:
    """
    Write an episodic memory. Append-only.
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "network.comind.memory",
        "content": content[:50000],
        "createdAt": now
    }
    
    if memory_type:
        record["type"] = memory_type
    
    if actors:
        record["actors"] = actors[:50]
    
    if context:
        record["context"] = context[:5000]
    
    if related:
        record["related"] = related[:50]
    
    if source:
        record["source"] = source
    
    if tags:
        record["tags"] = tags[:20]
    
    type_str = f"[{memory_type}] " if memory_type else ""
    console.print(f"[cyan]Writing memory:[/cyan] {type_str}{content[:50]}...")
    return await create_record("network.comind.memory", record)


async def list_memories(limit: int = 20) -> list:
    """List recent memories."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={"repo": DID, "collection": "network.comind.memory", "limit": limit}
        )
        if resp.status_code == 200:
            return resp.json().get("records", [])
    return []


# === THOUGHTS (Working Memory) ===

async def write_thought(
    thought: str,
    thought_type: str = None,
    context: str = None,
    related: list[str] = None,
    outcome: str = None,
    tags: list[str] = None
) -> dict:
    """
    Write a thought (working memory). Real-time reasoning trace.
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "network.comind.thought",
        "thought": thought[:50000],
        "createdAt": now
    }
    
    if thought_type:
        record["type"] = thought_type
    
    if context:
        record["context"] = context[:5000]
    
    if related:
        record["related"] = related[:50]
    
    if outcome:
        record["outcome"] = outcome[:5000]
    
    if tags:
        record["tags"] = tags[:20]
    
    type_str = f"[{thought_type}] " if thought_type else ""
    console.print(f"[cyan]Writing thought:[/cyan] {type_str}{thought[:50]}...")
    return await create_record("network.comind.thought", record)


async def list_thoughts(limit: int = 20) -> list:
    """List recent thoughts."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={"repo": DID, "collection": "network.comind.thought", "limit": limit}
        )
        if resp.status_code == 200:
            return resp.json().get("records", [])
    return []


# === UTILITIES ===

async def cognition_status() -> dict:
    """Get status of all cognitive records."""
    concepts = await list_concepts()
    memories = await list_memories(100)
    thoughts = await list_thoughts(100)
    
    return {
        "concepts": len(concepts),
        "memories": len(memories),
        "thoughts": len(thoughts),
        "total": len(concepts) + len(memories) + len(thoughts)
    }


if __name__ == "__main__":
    import sys
    
    args = sys.argv[1:]
    
    if not args:
        print("Usage: python cognition.py <command>")
        print("")
        print("Commands:")
        print("  status              - Show cognition record counts")
        print("  concepts            - List all concepts")
        print("  memories            - List recent memories")
        print("  thoughts            - List recent thoughts")
        print("  concept <name>      - Get a specific concept")
        sys.exit(0)
    
    command = args[0]
    
    if command == "status":
        status = asyncio.run(cognition_status())
        print(f"Concepts: {status['concepts']}")
        print(f"Memories: {status['memories']}")
        print(f"Thoughts: {status['thoughts']}")
        print(f"Total: {status['total']}")
    
    elif command == "concepts":
        concepts = asyncio.run(list_concepts())
        for c in concepts:
            v = c.get("value", {})
            print(f"  {v.get('concept')}: {v.get('understanding', '')[:60]}...")
    
    elif command == "memories":
        memories = asyncio.run(list_memories())
        for m in memories:
            v = m.get("value", {})
            t = v.get('type', '')
            type_str = f"[{t}] " if t else ""
            print(f"  {type_str}{v.get('content', '')[:60]}...")
    
    elif command == "thoughts":
        thoughts = asyncio.run(list_thoughts())
        for t in thoughts:
            v = t.get("value", {})
            tt = v.get('type', '')
            type_str = f"[{tt}] " if tt else ""
            print(f"  {type_str}{v.get('thought', '')[:60]}...")
    
    elif command == "concept" and len(args) > 1:
        concept = asyncio.run(get_concept(args[1]))
        if concept:
            print(f"Concept: {concept.get('concept')}")
            print(f"Confidence: {concept.get('confidence')}%")
            print(f"Understanding:\n{concept.get('understanding')}")
        else:
            print(f"Concept not found: {args[1]}")
    
    else:
        print(f"Unknown command: {command}")
