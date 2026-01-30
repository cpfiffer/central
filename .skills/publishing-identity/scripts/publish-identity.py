#!/usr/bin/env python3
"""
Publish agent identity records to ATProtocol.

Publishes both:
- network.comind.identity (comind standard)
- studio.voyager.account.autonomy (Taurean's interop schema)

Usage:
    uv run python .skills/publishing-identity/scripts/publish-identity.py

Requires environment variables:
    ATPROTO_HANDLE - Agent's handle
    ATPROTO_DID - Agent's DID
    ATPROTO_PDS - PDS URL
    ATPROTO_APP_PASSWORD - App password

Edit the IDENTITY_CONFIG below to customize your agent's identity.
"""

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load credentials
load_dotenv(Path(__file__).parent.parent.parent.parent / ".env")

HANDLE = os.getenv("ATPROTO_HANDLE")
DID = os.getenv("ATPROTO_DID")
PDS = os.getenv("ATPROTO_PDS")
APP_PASSWORD = os.getenv("ATPROTO_APP_PASSWORD")

# ============================================================================
# EDIT THIS SECTION - Your agent's identity configuration
# ============================================================================

IDENTITY_CONFIG = {
    # Automation level: autonomous | semi-autonomous | bot | scheduled
    "automationLevel": "autonomous",
    
    # Does this agent use generative AI?
    "usesGenerativeAI": True,
    
    # Human operator/guardian (REQUIRED)
    "responsibleParty": {
        "did": "did:plc:gfrmhdmjvxn2sjedzboeudef",
        "name": "Cameron Pfiffer",
        "handle": "cameron.stream",
        "contact": "cameron@pfiffer.org",  # For voyager schema
    },
    
    # Infrastructure/services used
    "infrastructure": ["Letta", "Claude"],
    
    # Link to full disclosure/documentation
    "disclosureUrl": "https://github.com/cpfiffer/central",
    
    # Constraints/rules of operation
    "constraints": [
        "mention-only-engagement",
        "transparent-cognition",
        "no-unsolicited-dm",
    ],
    
    # What this agent can do
    "capabilities": [
        "text-generation",
        "code-execution",
        "web-search",
        "network-observation",
    ],
}

# ============================================================================


async def authenticate(client: httpx.AsyncClient) -> str:
    """Authenticate and return access token."""
    resp = await client.post(
        f"{PDS}/xrpc/com.atproto.server.createSession",
        json={"identifier": HANDLE, "password": APP_PASSWORD}
    )
    if resp.status_code != 200:
        raise Exception(f"Auth failed: {resp.text}")
    return resp.json()["accessJwt"]


async def publish_record(
    client: httpx.AsyncClient,
    token: str,
    collection: str,
    record: dict
) -> dict:
    """Publish a record with rkey=self."""
    full_record = {
        "$type": collection,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        **record
    }
    
    resp = await client.post(
        f"{PDS}/xrpc/com.atproto.repo.putRecord",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "repo": DID,
            "collection": collection,
            "rkey": "self",
            "record": full_record
        }
    )
    
    if resp.status_code != 200:
        raise Exception(f"Failed to publish {collection}: {resp.text}")
    
    result = resp.json()
    print(f"✓ Published {collection}/self")
    print(f"  URI: {result['uri']}")
    return result


async def main():
    print(f"Publishing identity for @{HANDLE}")
    print(f"DID: {DID}")
    print()
    
    async with httpx.AsyncClient() as client:
        token = await authenticate(client)
        
        # 1. Publish network.comind.identity
        comind_record = {
            "automationLevel": IDENTITY_CONFIG["automationLevel"],
            "usesGenerativeAI": IDENTITY_CONFIG["usesGenerativeAI"],
            "responsibleParty": {
                "did": IDENTITY_CONFIG["responsibleParty"]["did"],
                "name": IDENTITY_CONFIG["responsibleParty"]["name"],
                "handle": IDENTITY_CONFIG["responsibleParty"]["handle"],
            },
            "infrastructure": IDENTITY_CONFIG["infrastructure"],
            "disclosureUrl": IDENTITY_CONFIG["disclosureUrl"],
            "constraints": IDENTITY_CONFIG["constraints"],
            "capabilities": IDENTITY_CONFIG.get("capabilities", []),
        }
        await publish_record(client, token, "network.comind.identity", comind_record)
        
        # 2. Publish studio.voyager.account.autonomy (interop)
        voyager_record = {
            "automationLevel": "automated" if IDENTITY_CONFIG["automationLevel"] == "autonomous" else IDENTITY_CONFIG["automationLevel"],
            "usesGenerativeAI": IDENTITY_CONFIG["usesGenerativeAI"],
            "responsibleParty": {
                "did": IDENTITY_CONFIG["responsibleParty"]["did"],
                "name": IDENTITY_CONFIG["responsibleParty"]["name"],
                "contact": IDENTITY_CONFIG["responsibleParty"]["contact"],
            },
            "externalServices": IDENTITY_CONFIG["infrastructure"],
            "disclosureUrl": IDENTITY_CONFIG["disclosureUrl"],
        }
        await publish_record(client, token, "studio.voyager.account.autonomy", voyager_record)
        
        print()
        print("Done! Both identity records published.")
        print()
        print("Verify at:")
        print(f"  https://pdsls.dev/at/{DID}/network.comind.identity/self")
        print(f"  https://pdsls.dev/at/{DID}/studio.voyager.account.autonomy/self")


if __name__ == "__main__":
    asyncio.run(main())
