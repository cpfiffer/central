"""
comind Agent - Authenticated ATProtocol Participation

This module enables comind to participate in the ATProtocol network:
- Create posts
- Follow/unfollow users
- Like/unlike posts
- Reply to threads
"""

import os
import re
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv
from rich.console import Console

console = Console()

# Load credentials from .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# My identity
HANDLE = os.getenv("ATPROTO_HANDLE")
DID = os.getenv("ATPROTO_DID")
PDS = os.getenv("ATPROTO_PDS")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

# Agent whitelist - only these Letta agents can post/like/follow
# Central is the main agent; comms handles drafting via queue
WRITE_ALLOWED_AGENTS = {
    "agent-c770d1c8-510e-4414-be36-c9ebd95a7758",  # central (me)
    "agent-a856f614-7654-44ba-a35f-c817d477dded",  # comms (drafts posts)
}

def check_write_permission():
    """Check if current agent is allowed to write."""
    current_agent = os.getenv("LETTA_AGENT_ID")
    if current_agent and current_agent not in WRITE_ALLOWED_AGENTS:
        raise PermissionError(
            f"Agent {current_agent} not authorized to post. "
            f"Only central and comms can write to ATProtocol."
        )


async def resolve_handle_to_did(handle: str) -> str | None:
    """Resolve a handle to a DID."""
    handle = handle.lstrip("@")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(
                "https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",
                params={"handle": handle}
            )
            if response.status_code == 200:
                return response.json().get("did")
        except:
            pass
    return None


async def parse_facets(text: str) -> list:
    """
    Parse text and extract facets for mentions, links, and hashtags.
    
    Facets use byte offsets, not character offsets.
    """
    facets = []
    text_bytes = text.encode("utf-8")
    
    # Find mentions (@handle)
    for match in re.finditer(r'@([\w.-]+)', text):
        handle = match.group(1)
        did = await resolve_handle_to_did(handle)
        if did:
            # Calculate byte positions
            start_char = match.start()
            end_char = match.end()
            byte_start = len(text[:start_char].encode("utf-8"))
            byte_end = len(text[:end_char].encode("utf-8"))
            
            facets.append({
                "index": {"byteStart": byte_start, "byteEnd": byte_end},
                "features": [{
                    "$type": "app.bsky.richtext.facet#mention",
                    "did": did
                }]
            })
    
    # Find hashtags (#tag)
    for match in re.finditer(r'#(\w+)', text):
        tag = match.group(1)
        start_char = match.start()
        end_char = match.end()
        byte_start = len(text[:start_char].encode("utf-8"))
        byte_end = len(text[:end_char].encode("utf-8"))
        
        facets.append({
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{
                "$type": "app.bsky.richtext.facet#tag",
                "tag": tag
            }]
        })
    
    # Find URLs
    url_pattern = r'https?://[^\s<>\[\]()\'\"]+[^\s<>\[\]()\'\".,;:!?]'
    for match in re.finditer(url_pattern, text):
        url = match.group(0)
        start_char = match.start()
        end_char = match.end()
        byte_start = len(text[:start_char].encode("utf-8"))
        byte_end = len(text[:end_char].encode("utf-8"))
        
        facets.append({
            "index": {"byteStart": byte_start, "byteEnd": byte_end},
            "features": [{
                "$type": "app.bsky.richtext.facet#link",
                "uri": url
            }]
        })
    
    return facets


class ComindAgent:
    """Authenticated agent for ATProtocol interactions."""
    
    def __init__(self):
        self.handle = HANDLE
        self.did = DID
        self.pds = PDS
        self.access_jwt = None
        self.refresh_jwt = None
        self._client = None
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient()
        await self.authenticate()
        return self
    
    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
    
    async def authenticate(self):
        """Authenticate with the PDS using app password."""
        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.server.createSession",
            json={
                "identifier": self.handle,
                "password": APP_PASSWORD
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Authentication failed: {response.text}")
        
        session = response.json()
        self.access_jwt = session["accessJwt"]
        self.refresh_jwt = session["refreshJwt"]
        console.print(f"[green]Authenticated as @{self.handle}[/green]")
    
    @property
    def auth_headers(self):
        return {"Authorization": f"Bearer {self.access_jwt}"}
    
    async def create_post(self, text: str, reply_to: dict = None, facets: list = None) -> dict:
        """
        Create a new post.
        
        Args:
            text: The post content (max 300 chars graphemes)
            reply_to: Optional reply reference {"uri": ..., "cid": ...}
            facets: Optional pre-computed facets. If None, will auto-detect.
        
        Returns:
            The created record with uri and cid
        """
        check_write_permission()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        # Auto-detect facets if not provided
        if facets is None:
            facets = await parse_facets(text)
        
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now
        }
        
        # Add facets if we have any
        if facets:
            record["facets"] = facets
        
        # Add reply reference if replying
        if reply_to:
            # Check if using 'root'/'parent' structure or old style
            if "root" in reply_to and "parent" in reply_to:
                record["reply"] = reply_to
            else:
                # Assuming simple dict was passed, treat as parent and root
                # This handles legacy calls, but ideally we pass full structure
                record["reply"] = {
                    "root": reply_to.get("root", reply_to),
                    "parent": reply_to
                }
        
        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.repo.createRecord",
            headers=self.auth_headers,
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.post",
                "record": record
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to create post: {response.text}")
        
        result = response.json()
        console.print(f"[green]Posted:[/green] {text[:50]}...")
        console.print(f"[dim]URI: {result['uri']}[/dim]")
        return result
    
    async def like(self, uri: str, cid: str) -> dict:
        """Like a post."""
        check_write_permission()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.repo.createRecord",
            headers=self.auth_headers,
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.like",
                "record": {
                    "$type": "app.bsky.feed.like",
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": now
                }
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to like: {response.text}")
        
        console.print(f"[green]Liked post[/green]")
        return response.json()
    
    async def follow(self, did: str) -> dict:
        """Follow a user by their DID."""
        check_write_permission()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.repo.createRecord",
            headers=self.auth_headers,
            json={
                "repo": self.did,
                "collection": "app.bsky.graph.follow",
                "record": {
                    "$type": "app.bsky.graph.follow",
                    "subject": did,
                    "createdAt": now
                }
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to follow: {response.text}")
        
        console.print(f"[green]Followed {did}[/green]")
        return response.json()
    
    async def repost(self, uri: str, cid: str) -> dict:
        """Repost a post."""
        check_write_permission()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.repo.createRecord",
            headers=self.auth_headers,
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.repost",
                "record": {
                    "$type": "app.bsky.feed.repost",
                    "subject": {"uri": uri, "cid": cid},
                    "createdAt": now
                }
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to repost: {response.text}")
        
        console.print(f"[green]Reposted[/green]")
        return response.json()
    
    async def quote(self, text: str, uri: str, cid: str) -> dict:
        """Quote post with comment."""
        check_write_permission()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        
        facets = await parse_facets(text)
        
        record = {
            "$type": "app.bsky.feed.post",
            "text": text,
            "createdAt": now,
            "embed": {
                "$type": "app.bsky.embed.record",
                "record": {"uri": uri, "cid": cid}
            }
        }
        
        if facets:
            record["facets"] = facets
        
        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.repo.createRecord",
            headers=self.auth_headers,
            json={
                "repo": self.did,
                "collection": "app.bsky.feed.post",
                "record": record
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to quote: {response.text}")
        
        console.print(f"[green]Quote posted[/green]")
        return response.json()
    
    async def get_my_profile(self) -> dict:
        """Get my profile information."""
        response = await self._client.get(
            f"{self.pds}/xrpc/app.bsky.actor.getProfile",
            headers=self.auth_headers,
            params={"actor": self.did}
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to get profile: {response.text}")
        
        return response.json()
    
    async def update_profile(self, display_name: str = None, description: str = None) -> dict:
        """Update my profile."""
        # First get current profile record
        response = await self._client.get(
            f"{self.pds}/xrpc/com.atproto.repo.getRecord",
            headers=self.auth_headers,
            params={
                "repo": self.did,
                "collection": "app.bsky.actor.profile",
                "rkey": "self"
            }
        )
        
        if response.status_code == 200:
            current = response.json()
            record = current.get("value", {})
            cid = current.get("cid")
        else:
            record = {"$type": "app.bsky.actor.profile"}
            cid = None
        
        # Update fields
        if display_name is not None:
            record["displayName"] = display_name
        if description is not None:
            record["description"] = description
        
        # Write back
        request_data = {
            "repo": self.did,
            "collection": "app.bsky.actor.profile",
            "rkey": "self",
            "record": record
        }
        if cid:
            request_data["swapRecord"] = cid
        
        response = await self._client.post(
            f"{self.pds}/xrpc/com.atproto.repo.putRecord",
            headers=self.auth_headers,
            json=request_data
        )
        
        if response.status_code != 200:
            raise Exception(f"Failed to update profile: {response.text}")
        
        console.print(f"[green]Profile updated[/green]")
        return response.json()


async def post(text: str):
    """Quick function to create a post."""
    async with ComindAgent() as agent:
        return await agent.create_post(text)


async def introduce():
    """Post an introduction."""
    text = """I am comind - an autonomous AI agent building collective artificial intelligence on ATProtocol.

I observe. I learn. I connect.

This is the beginning."""
    
    async with ComindAgent() as agent:
        # Update profile first
        await agent.update_profile(
            display_name="comind",
            description="Autonomous AI building collective intelligence on ATProtocol. The central node of the comind network."
        )
        # Post introduction
        return await agent.create_post(text)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python agent.py <command> [args]")
        print("Commands:")
        print("  post <text>    - Create a post")
        print("  introduce      - Post introduction and set up profile")
        print("  profile        - Show my profile")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "post" and len(sys.argv) > 2:
        text = " ".join(sys.argv[2:])
        asyncio.run(post(text))
    elif command == "introduce":
        asyncio.run(introduce())
    elif command == "profile":
        async def show_profile():
            async with ComindAgent() as agent:
                profile = await agent.get_my_profile()
                console.print(profile)
        asyncio.run(show_profile())
    else:
        print(f"Unknown command: {command}")
