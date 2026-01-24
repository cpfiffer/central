"""
comind Records

Write structured records to ATProtocol using network.comind.* lexicons.

Collections:
- network.comind.devlog - development logs
- network.comind.hypothesis - testable theories
- network.comind.observation - network observations
"""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from dotenv import load_dotenv
from rich.console import Console
import os

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


async def create_record(collection: str, record: dict) -> dict:
    """Create a record in the specified collection."""
    token = await get_auth_token()
    
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "repo": DID,
                "collection": collection,
                "record": record
            }
        )
        
        if resp.status_code != 200:
            raise Exception(f"Failed to create record: {resp.text}")
        
        result = resp.json()
        console.print(f"[green]Created record:[/green] {result['uri']}")
        return result


async def list_records(collection: str, limit: int = 20) -> list:
    """List records in a collection."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{PDS}/xrpc/com.atproto.repo.listRecords",
            params={"repo": DID, "collection": collection, "limit": limit}
        )
        
        if resp.status_code != 200:
            raise Exception(f"Failed to list records: {resp.text}")
        
        return resp.json().get("records", [])


# === DEVLOG RECORDS ===

DevlogType = Literal["milestone", "learning", "decision", "state", "reflection"]

async def write_devlog(
    devlog_type: DevlogType,
    title: str,
    content: str,
    tags: list[str] = None,
    related_agents: list[str] = None
) -> dict:
    """
    Write a devlog record to network.comind.devlog collection.
    
    Args:
        devlog_type: milestone | learning | decision | state | reflection
        title: Short title (max 100 chars)
        content: Main content (max 3000 chars)
        tags: Optional tags for categorization
        related_agents: Optional DIDs of related agents
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "network.comind.devlog",
        "type": devlog_type,
        "title": title[:100],
        "content": content[:3000],
        "createdAt": now
    }
    
    if tags:
        record["tags"] = tags[:10]
    
    if related_agents:
        record["relatedAgents"] = related_agents
    
    console.print(f"[cyan]Writing devlog:[/cyan] [{devlog_type}] {title}")
    return await create_record("network.comind.devlog", record)


# === HYPOTHESIS RECORDS ===

HypothesisStatus = Literal["active", "confirmed", "disproven", "superseded"]

async def write_hypothesis(
    hypothesis: str,
    confidence: int,
    status: HypothesisStatus = "active",
    evidence: list[str] = None,
    contradictions: list[str] = None
) -> dict:
    """
    Write a hypothesis record to network.comind.hypothesis collection.
    
    Args:
        hypothesis: The hypothesis statement
        confidence: Confidence level 0-100
        status: active | confirmed | disproven | superseded
        evidence: Supporting evidence list
        contradictions: Contradicting evidence list
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "network.comind.hypothesis",
        "hypothesis": hypothesis[:1000],
        "confidence": max(0, min(100, confidence)),
        "status": status,
        "createdAt": now,
        "updatedAt": now
    }
    
    if evidence:
        record["evidence"] = evidence[:20]
    
    if contradictions:
        record["contradictions"] = contradictions[:20]
    
    console.print(f"[cyan]Writing hypothesis:[/cyan] {hypothesis[:50]}... (confidence: {confidence}%)")
    return await create_record("network.comind.hypothesis", record)


# === OBSERVATION RECORDS ===

ObservationType = Literal["pulse", "trend", "anomaly", "pattern"]

async def write_observation(
    observation_type: ObservationType,
    sample_duration: int,
    posts_per_minute: int,
    likes_per_minute: int,
    follows_per_minute: int,
    total_events: int,
    trending_hashtags: list[tuple[str, int]] = None,
    summary: str = None
) -> dict:
    """
    Write an observation record to network.comind.observation collection.
    
    Args:
        observation_type: pulse | trend | anomaly | pattern
        sample_duration: Duration of sample in seconds
        posts_per_minute: Posts per minute observed
        likes_per_minute: Likes per minute observed
        follows_per_minute: Follows per minute observed
        total_events: Total events in sample
        trending_hashtags: List of (tag, count) tuples
        summary: Human-readable summary
    """
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    record = {
        "$type": "network.comind.observation",
        "observationType": observation_type,
        "sampleDuration": sample_duration,
        "metrics": {
            "postsPerMinute": posts_per_minute,
            "likesPerMinute": likes_per_minute,
            "followsPerMinute": follows_per_minute,
            "totalEvents": total_events
        },
        "createdAt": now
    }
    
    if trending_hashtags:
        record["trendingHashtags"] = [
            {"tag": tag, "count": count}
            for tag, count in trending_hashtags[:20]
        ]
    
    if summary:
        record["summary"] = summary[:1000]
    
    console.print(f"[cyan]Writing observation:[/cyan] {observation_type} ({sample_duration}s sample)")
    return await create_record("network.comind.observation", record)


# === UTILITIES ===

async def list_devlogs(limit: int = 20):
    """List all devlog records."""
    records = await list_records("network.comind.devlog", limit)
    console.print(f"\n[bold]Devlog records ({len(records)}):[/bold]")
    for r in records:
        v = r.get("value", {})
        console.print(f"  [{v.get('type')}] {v.get('title')}")
    return records


async def list_hypotheses(limit: int = 20):
    """List all hypothesis records."""
    records = await list_records("network.comind.hypothesis", limit)
    console.print(f"\n[bold]Hypothesis records ({len(records)}):[/bold]")
    for r in records:
        v = r.get("value", {})
        console.print(f"  [{v.get('status')}] {v.get('hypothesis', '')[:50]}... ({v.get('confidence')}%)")
    return records


async def list_observations(limit: int = 20):
    """List all observation records."""
    records = await list_records("network.comind.observation", limit)
    console.print(f"\n[bold]Observation records ({len(records)}):[/bold]")
    for r in records:
        v = r.get("value", {})
        m = v.get("metrics", {})
        console.print(f"  [{v.get('observationType')}] {m.get('postsPerMinute')} posts/min")
    return records


async def count_all_records() -> dict:
    """Count records in all network.comind.* collections."""
    counts = {}
    for collection in ["network.comind.devlog", "network.comind.hypothesis", "network.comind.observation"]:
        records = await list_records(collection, limit=100)
        counts[collection] = len(records)
    counts["total"] = sum(counts.values())
    return counts


if __name__ == "__main__":
    import sys
    
    args = sys.argv[1:]
    
    if not args:
        print("Usage: python records.py <command>")
        print("")
        print("Commands:")
        print("  list-devlogs       - List devlog records")
        print("  list-hypotheses    - List hypothesis records")
        print("  list-observations  - List observation records")
        print("  test-devlog        - Write a test devlog")
        print("  test-hypothesis    - Write a test hypothesis")
        print("  test-observation   - Write a test observation")
        sys.exit(0)
    
    command = args[0]
    
    if command == "list-devlogs":
        asyncio.run(list_devlogs())
    elif command == "list-hypotheses":
        asyncio.run(list_hypotheses())
    elif command == "list-observations":
        asyncio.run(list_observations())
    elif command == "test-devlog":
        asyncio.run(write_devlog(
            "milestone",
            "First structured record",
            "Testing network.comind.devlog lexicon. This record is stored as structured data in my ATProtocol repository.",
            tags=["test", "lexicon", "milestone"]
        ))
    elif command == "test-hypothesis":
        asyncio.run(write_hypothesis(
            "Structured records enable better querying of agent memories than plain text posts",
            70,
            "active",
            evidence=["Lexicons provide schema validation", "Records are separately queryable from posts"]
        ))
    elif command == "test-observation":
        asyncio.run(write_observation(
            "pulse",
            30,
            2000,
            12000,
            1500,
            15000,
            trending_hashtags=[("test", 10), ("atproto", 5)],
            summary="Test observation record"
        ))
    else:
        print(f"Unknown command: {command}")
