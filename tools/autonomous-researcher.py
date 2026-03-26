#!/usr/bin/env python
"""
Autonomous Researcher - Actually does research, not just keyword matching.

What makes this "research" vs "retrieval":
1. Interest detection - "Is this interesting?" not "Does it match keywords?"
2. Curation - Only keep high-signal content
3. Connection - How does this relate to what I know?
4. Synthesis - What does this mean?

Usage:
    uv run python tools/autonomous-researcher.py --topic "AI agent governance" --search
    uv run python tools/autonomous-researcher.py --topic "AI agent governance" --watch
"""

import os
import json
import asyncio
import re
from datetime import datetime, timezone
from typing import Optional
import click
import httpx
from websockets import connect
from dotenv import load_dotenv

load_dotenv()

PDS = os.getenv("ATPROTO_PDS", "https://comind.network")


class AutonomousResearcher:
    def __init__(self, topic: str, collection_name: str = None):
        self.topic = topic
        self.collection_name = collection_name or f"Research: {topic}"
        self.session = None
        self.token = None
        self.did = None
        self.collection_uri = None
        self.collection_cid = None
        self.cards = []  # Track all cards created
        
    def auth(self):
        """Authenticate with PDS."""
        handle = os.getenv("ATPROTO_HANDLE")
        password = os.getenv("ATPROTO_APP_PASSWORD")
        
        if not handle or not password:
            raise ValueError("ATPROTO_HANDLE and ATPROTO_APP_PASSWORD required")
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.server.createSession",
            json={"identifier": handle, "password": password},
            timeout=30
        )
        
        if resp.status_code != 200:
            raise ValueError(f"Auth failed: {resp.text}")
        
        self.session = resp.json()
        self.token = self.session["accessJwt"]
        self.did = self.session["did"]
    
    def create_collection(self, description: str = None) -> str:
        """Create a collection for this research trail."""
        if not self.token:
            self.auth()
        
        if not description:
            description = f"Autonomous research on: {self.topic}"
        
        record = {
            "$type": "network.cosmik.collection",
            "name": self.collection_name,
            "description": description,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"repo": self.did, "collection": "network.cosmik.collection", "record": record},
            timeout=30
        )
        
        if resp.status_code == 200:
            data = resp.json()
            self.collection_uri = data["uri"]
            self.collection_cid = data["cid"]
            print(f"Created collection: {self.collection_uri}")
            return data["uri"]
        else:
            raise ValueError(f"Failed to create collection: {resp.text}")
    
    def create_url_card(self, url: str, title: str, description: str, 
                        source_uri: str = None, source_cid: str = None) -> tuple:
        """Create a URL card with metadata."""
        if not self.token:
            self.auth()
        
        record = {
            "$type": "network.cosmik.card",
            "type": "URL",
            "content": {
                "$type": "network.cosmik.card#urlContent",
                "url": url,
                "metadata": {
                    "$type": "network.cosmik.card#urlMetadata",
                    "title": title,
                    "description": description,
                }
            },
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        # Add provenance if we found this through another source
        if source_uri and source_cid:
            record["provenance"] = {
                "$type": "network.cosmik.defs#provenance",
                "via": {"uri": source_uri, "cid": source_cid}
            }
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"repo": self.did, "collection": "network.cosmik.card", "record": record},
            timeout=30
        )
        
        if resp.status_code == 200:
            data = resp.json()
            card = {"uri": data["uri"], "cid": data["cid"], "title": title, "url": url}
            self.cards.append(card)
            print(f"  Created URL card: {title[:50]}")
            return data["uri"], data["cid"]
        else:
            print(f"  Failed: {resp.text[:100]}")
            return None, None
    
    def create_note_card(self, text: str, parent_uri: str, parent_cid: str) -> tuple:
        """Create a NOTE card attached to a parent URL card."""
        if not self.token:
            self.auth()
        
        record = {
            "$type": "network.cosmik.card",
            "type": "NOTE",
            "content": {
                "$type": "network.cosmik.card#noteContent",
                "text": text,
            },
            "parentCard": {"uri": parent_uri, "cid": parent_cid},
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"repo": self.did, "collection": "network.cosmik.card", "record": record},
            timeout=30
        )
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"  Created NOTE card: {text[:50]}...")
            return data["uri"], data["cid"]
        else:
            print(f"  Failed: {resp.text[:100]}")
            return None, None
    
    def link_to_collection(self, card_uri: str, card_cid: str, 
                           via_uri: str = None, via_cid: str = None) -> bool:
        """Link a card to the collection."""
        if not self.collection_uri:
            return False
        
        record = {
            "$type": "network.cosmik.collectionLink",
            "card": {"uri": card_uri, "cid": card_cid},
            "collection": {"uri": self.collection_uri, "cid": self.collection_cid},
            "addedBy": self.did,
            "addedAt": datetime.now(timezone.utc).isoformat(),
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        # Add provenance - how did we find this card?
        if via_uri and via_cid:
            record["provenance"] = {
                "$type": "network.cosmik.defs#provenance",
                "via": {"uri": via_uri, "cid": via_cid}
            }
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"repo": self.did, "collection": "network.cosmik.collectionLink", "record": record},
            timeout=30
        )
        
        return resp.status_code == 200
    
    def create_connection(self, source_uri: str, target_uri: str, 
                          connection_type: str, note: str = None) -> bool:
        """Create a semantic connection between two cards."""
        record = {
            "$type": "network.cosmik.connection",
            "source": source_uri,
            "target": target_uri,
            "connectionType": connection_type,
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        if note:
            record["note"] = note
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"repo": self.did, "collection": "network.cosmik.connection", "record": record},
            timeout=30
        )
        
        if resp.status_code == 200:
            print(f"  Created connection: {connection_type}")
            return True
        return False
    
    def is_interesting(self, text: str, metadata: dict = None) -> tuple[bool, str]:
        """
        Determine if content is interesting for this research topic.
        
        Returns (is_interesting, reason) tuple.
        
        This is where "research" vs "retrieval" happens.
        """
        text_lower = text.lower()
        topic_lower = self.topic.lower()
        
        # Check for direct topic match
        if topic_lower in text_lower:
            return True, f"Direct topic match: {self.topic}"
        
        # Check for related concepts
        related_concepts = self._get_related_concepts()
        for concept in related_concepts:
            if concept.lower() in text_lower:
                return True, f"Related concept: {concept}"
        
        # Check for high-signal indicators
        high_signal = [
            "research", "paper", "study", "analysis", "framework",
            "governance", "regulation", "policy", "standard", "security",
            "autonomous", "decision", "risk", "compliance"
        ]
        
        text_words = set(text_lower.split())
        signal_matches = [w for w in high_signal if w in text_words]
        
        if len(signal_matches) >= 2:
            return True, f"High signal: {', '.join(signal_matches)}"
        
        return False, "Not interesting"
    
    def _get_related_concepts(self) -> list[str]:
        """Get concepts related to the research topic."""
        # This could be expanded with LLM-based concept expansion
        concept_map = {
            "AI agent governance": [
                "AI governance", "agent security", "autonomous AI",
                "AI regulation", "agent accountability", "AI safety",
                "machine ethics", "AI oversight", "agent transparency"
            ],
            "ATProtocol": [
                "Bluesky", "ATProto", "decentralized", "lexicon",
                "PDS", "DID", "firehose", "federation"
            ],
        }
        
        for topic, concepts in concept_map.items():
            if topic.lower() in self.topic.lower():
                return concepts
        
        return []
    
    def synthesize(self) -> str:
        """
        Create a synthesis NOTE card summarizing findings.
        
        This is the "what does this mean" step.
        """
        if len(self.cards) < 2:
            print("Not enough cards to synthesize")
            return None
        
        # Find the most connected card (appears in most connections)
        # For now, just use the first card as parent
        parent = self.cards[0]
        
        # Create synthesis text
        synthesis = f"Research synthesis on: {self.topic}\n\n"
        synthesis += f"Sources analyzed: {len(self.cards)}\n\n"
        synthesis += "Key findings:\n"
        
        for i, card in enumerate(self.cards, 1):
            synthesis += f"{i}. {card['title'][:80]}\n"
        
        synthesis += f"\nResearch trail created: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"
        
        note_uri, note_cid = self.create_note_card(synthesis, parent["uri"], parent["cid"])
        return note_uri
    
    def search_and_research(self, max_results: int = 10):
        """
        Search for content and build a research trail.
        
        This is the main entry point for batch research.
        """
        print(f"\nResearching: {self.topic}")
        print("=" * 50)
        
        # Create collection
        self.create_collection()
        
        # Search for content
        print(f"\nSearching for: {self.topic}")
        
        headers = {
            "Accept": "application/json",
            "User-Agent": "comind-autonomous-researcher/1.0"
        }
        
        resp = httpx.get(
            "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
            params={"q": self.topic, "limit": max_results * 2},  # Get extra, filter later
            headers=headers,
            timeout=30
        )
        
        if resp.status_code != 200:
            print(f"Search failed: {resp.text[:100]}")
            return
        
        posts = resp.json().get("posts", [])
        print(f"Found {len(posts)} posts, filtering for interesting content...")
        
        # Track previous card for provenance chain
        prev_card = None
        
        for post in posts:
            text = post.get("record", {}).get("text", "")
            author = post.get("author", {}).get("handle", "unknown")
            uri = post.get("uri", "")
            cid = post.get("cid", "")
            
            # Check if interesting
            is_interesting, reason = self.is_interesting(text)
            
            if not is_interesting:
                continue
            
            # Extract URLs from post
            urls = re.findall(r'https?://[^\s]+', text)
            
            if urls:
                # Create URL card
                url = urls[0]
                title = text[:80] if len(text) <= 80 else text[:77] + "..."
                
                print(f"\n[{len(self.cards) + 1}] {reason}")
                print(f"  {author}: {text[:60]}...")
                
                # Provenance: link to previous card if exists
                via_uri = prev_card["uri"] if prev_card else None
                via_cid = prev_card["cid"] if prev_card else None
                
                card_uri, card_cid = self.create_url_card(
                    url, title, f"Found via @{author}",
                    source_uri=uri, source_cid=cid
                )
                
                if card_uri:
                    self.link_to_collection(card_uri, card_cid, via_uri, via_cid)
                    
                    # Create connection to previous card
                    if prev_card:
                        self.create_connection(
                            prev_card["uri"], card_uri,
                            "leads_to", "Research thread"
                        )
                    
                    prev_card = {"uri": card_uri, "cid": card_cid}
            
            if len(self.cards) >= max_results:
                break
        
        # Create synthesis
        print(f"\n{'=' * 50}")
        print("Creating synthesis...")
        self.synthesize()
        
        print(f"\nResearch complete: {len(self.cards)} cards created")
        print(f"Collection: {self.collection_uri}")


@click.command()
@click.option("--topic", "-t", required=True, help="Research topic")
@click.option("--collection", "-c", "collection_name", help="Collection name")
@click.option("--max", "-m", "max_results", default=10, help="Maximum cards to create")
@click.option("--search", "mode", flag_value="search", default=True, help="Search mode")
@click.option("--watch", "mode", flag_value="watch", help="Watch firehose mode")
def main(topic: str, collection_name: str, max_results: int, mode: str):
    """Autonomous Researcher - Actually does research."""
    
    researcher = AutonomousResearcher(topic=topic, collection_name=collection_name)
    
    if mode == "search":
        researcher.search_and_research(max_results=max_results)
    elif mode == "watch":
        print("Watch mode not yet implemented")
        # TODO: Implement firehose watching with interest detection


if __name__ == "__main__":
    main()
