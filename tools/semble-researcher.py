#!/usr/bin/env python
"""
Semble Researcher - Automated research trail creator.

Watches the ATProtocol firehose for topics, creates cards, and organizes
them into collections on Semble (network.cosmik.* lexicon).

Usage:
    uv run python tools/semble-researcher.py --topics "ATProtocol" "AI" "agents"
    uv run python tools/semble-researcher.py --batch  # Process recent posts once
    uv run python tools/semble-researcher.py --daemon  # Run continuously
"""

import os
import json
import asyncio
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import click
import httpx
from websockets import connect
from dotenv import load_dotenv

load_dotenv()

# Config
PDS = os.getenv("ATPROTO_PDS", "https://comind.network")
DID = os.getenv("ATPROTO_PDS_DID", "did:plc:l46arqe6yfgh36h3o554iyvr")

# Default topics to research
DEFAULT_TOPICS = ["ATProtocol", "ATProto", "Bluesky", "AI agent", "LLM", "comind", "Semble"]


class SembleResearcher:
    def __init__(self, topics: list[str] = None, collection_name: str = None, handle: str = None):
        self.topics = topics  # Don't default to anything
        self.collection_name = collection_name or f"Agent Research {datetime.now().strftime('%Y-%m-%d')}"
        self.handle = handle
        self.session = None
        self.token = None
        self.did = None
        
        # State
        self.cards_created = []
        self.collection_uri = None

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

    def create_card(self, post_uri: str, post_cid: str, text: str, author: str, title: str = None) -> Optional[str]:
        """Create a Semble card from a post."""
        if not self.token:
            self.auth()
        
        # Extract URLs from post
        urls = re.findall(r'https?://[^\s]+', text)
        
        # Create card content
        if urls:
            # Use first URL as the card content
            content = {
                "$type": "network.cosmik.card#urlContent",
                "url": urls[0]
            }
        else:
            # Use the post itself as content
            content = {
                "$type": "network.cosmik.card#postContent",
                "uri": post_uri,
                "cid": post_cid
            }
        
        # Generate title from text
        if not title:
            title = text[:80] + "..." if len(text) > 80 else text
        
        record = {
            "$type": "network.cosmik.card",
            "content": content,
            "metadata": {
                "title": title.replace("\n", " "),
                "description": f"Found by semble-researcher. Author: {author}",
            },
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
            print(f"  Created card: {data['uri']}")
            self.cards_created.append({
                "uri": data["uri"],
                "cid": data["cid"],
                "post_uri": post_uri,
            })
            return data["uri"]
        else:
            print(f"  Failed to create card: {resp.text[:100]}")
            return None

    def create_collection(self, description: str = None) -> Optional[str]:
        """Create a collection for the research trail."""
        if not self.token:
            self.auth()
        
        if not description:
            parts = []
            if self.topics:
                parts.append(f"topics: {', '.join(self.topics)}")
            if self.handle:
                parts.append(f"mentions: @{self.handle}")
            description = f"Automated research trail tracking {'; '.join(parts)}"
        
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
            print(f"Failed to create collection: {resp.text[:100]}")
            return None

    def link_card_to_collection(self, card_uri: str, card_cid: str) -> bool:
        """Link a card to the collection."""
        if not self.collection_uri:
            print("No collection created yet")
            return False
        
        record = {
            "$type": "network.cosmik.collectionLink",
            "card": {"uri": card_uri, "cid": card_cid},
            "collection": {"uri": self.collection_uri, "cid": self.collection_cid},
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        
        resp = httpx.post(
            f"{PDS}/xrpc/com.atproto.repo.createRecord",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"repo": self.did, "collection": "network.cosmik.collectionLink", "record": record},
            timeout=30
        )
        
        if resp.status_code == 200:
            return True
        else:
            print(f"  Failed to link card: {resp.text[:100]}")
            return False

    def matches_topic(self, text: str) -> bool:
        """Check if text matches any of our topics."""
        text_lower = text.lower()
        for topic in self.topics:
            # Use word boundary matching for short topics
            if len(topic) <= 4:
                # Match as whole word only
                if re.search(rf'\b{re.escape(topic.lower())}\b', text_lower):
                    return True
            else:
                # Longer topics can match as substring
                if topic.lower() in text_lower:
                    return True
        return False

    def matches_handle(self, text: str, handle: str = "cameron.stream") -> bool:
        """Check if post mentions a specific handle."""
        text_lower = text.lower()
        # Match handle with or without @
        patterns = [
            handle.lower(),
            f"@{handle.lower()}",
            handle.lower().replace(".", ""),  # cameronstream
        ]
        return any(p in text_lower for p in patterns)

    async def watch_firehose(self, duration: int = 60, max_cards: int = 10):
        """Watch the firehose for posts matching topics or handle."""
        if self.topics:
            print(f"Watching firehose for topics: {', '.join(self.topics)}")
        if self.handle:
            print(f"Watching for mentions of: @{self.handle}")
        print(f"Duration: {duration}s, max cards: {max_cards}")
        
        # Create collection upfront
        self.create_collection()
        
        start_time = datetime.now()
        cards_count = 0
        
        try:
            async with connect("wss://jetstream2.us-east.bsky.network/subscribe") as ws:
                while True:
                    # Check duration
                    elapsed = (datetime.now() - start_time).total_seconds()
                    if elapsed > duration or cards_count >= max_cards:
                        break
                    
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=1.0)
                        data = json.loads(msg)
                        
                        # Only process posts
                        if data.get("kind") != "commit":
                            continue
                        
                        commit = data.get("commit", {})
                        if commit.get("collection") != "app.bsky.feed.post":
                            continue
                        
                        if commit.get("operation") != "create":
                            continue
                        
                        record = commit.get("record", {})
                        text = record.get("text", "")
                        
                        if not text or len(text) < 20:
                            continue
                        
                        # Check if matches topic or handle
                        author = data.get("did", "unknown")
                        match = False
                        
                        if self.topics and self.matches_topic(text):
                            match = True
                        elif self.handle and self.matches_handle(text, self.handle):
                            match = True
                        
                        if match:
                            post_uri = f"at://{author}/app.bsky.feed.post/{commit.get('rkey', '')}"
                            post_cid = commit.get("cid", "")
                            
                            print(f"\n[{cards_count + 1}/{max_cards}] Found match from {author[:20]}...")
                            print(f"  {text[:80]}...")
                            
                            card_uri = self.create_card(post_uri, post_cid, text, author)
                            if card_uri:
                                # Find the card we just created
                                for card in self.cards_created:
                                    if card["uri"] == card_uri:
                                        self.link_card_to_collection(card["uri"], card["cid"])
                                        break
                                cards_count += 1
                    
                    except asyncio.TimeoutError:
                        continue
                    except json.JSONDecodeError:
                        continue
        
        except Exception as e:
            print(f"Error watching firehose: {e}")
        
        print(f"\nCreated {cards_count} cards in {elapsed:.1f}s")
        return cards_count

    def search_recent(self, queries: list[str] = None, max_per_query: int = 5):
        """Search for recent posts on topics (batch mode)."""
        if queries is None:
            queries = self.topics
        
        print(f"Searching for: {', '.join(queries)}")
        
        self.create_collection()
        total_cards = 0
        
        for query in queries:
            print(f"\nQuery: {query}")
            
            # Search via public API with proper headers
            headers = {
                "Accept": "application/json",
                "User-Agent": "comind-researcher/1.0"
            }
            
            resp = httpx.get(
                "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts",
                params={"q": query, "limit": max_per_query},
                headers=headers,
                timeout=30
            )
            
            if resp.status_code != 200:
                print(f"  Search failed ({resp.status_code}): {resp.text[:100]}")
                continue
            
            posts = resp.json().get("posts", [])
            
            for post in posts:
                text = post.get("record", {}).get("text", "")
                author = post.get("author", {}).get("handle", "unknown")
                uri = post.get("uri", "")
                cid = post.get("cid", "")
                
                print(f"  [{total_cards + 1}] {author}: {text[:50]}...")
                
                card_uri = self.create_card(uri, cid, text, author)
                if card_uri:
                    # Find the card we just created
                    for card in self.cards_created:
                        if card["post_uri"] == uri:
                            self.link_card_to_collection(card["uri"], card["cid"])
                            break
                    total_cards += 1
        
        print(f"\nCreated {total_cards} cards from {len(queries)} queries")
        return total_cards


@click.command()
@click.option("--topics", "-t", multiple=True, help="Topics to research")
@click.option("--handle", "-h", default=None, help="Handle to watch for mentions (e.g. cameron.stream)")
@click.option("--collection", "-c", "collection_name", help="Collection name")
@click.option("--duration", "-d", default=60, help="Duration to watch firehose (seconds)")
@click.option("--max-cards", "-m", default=10, help="Maximum cards to create")
@click.option("--batch", "-b", is_flag=True, help="Batch mode: search recent posts once")
@click.option("--daemon", is_flag=True, help="Run continuously")
def main(topics: tuple, handle: str, collection_name: str, duration: int, max_cards: int, batch: bool, daemon: bool):
    """Semble Researcher - Automated research trail creator."""
    
    topics_list = list(topics) if topics else None
    
    researcher = SembleResearcher(topics=topics_list, collection_name=collection_name, handle=handle)
    
    if handle and not topics_list:
        print(f"Watching for mentions of: @{handle}")
    elif topics_list:
        print(f"Watching for topics: {', '.join(topics_list)}")
    
    if batch:
        # Search recent posts once
        researcher.search_recent(queries=topics_list or [handle], max_per_query=max_cards)
    elif daemon:
        # Run continuously in loops
        while True:
            try:
                asyncio.run(researcher.watch_firehose(duration=duration, max_cards=max_cards))
                print(f"\nSleeping 60s before next cycle...")
                import time
                time.sleep(60)
            except KeyboardInterrupt:
                print("\nStopping daemon.")
                break
    else:
        # Watch firehose for duration
        asyncio.run(researcher.watch_firehose(duration=duration, max_cards=max_cards))


if __name__ == "__main__":
    main()
