"""Backfill script to index existing cognition records."""

import logging
from datetime import datetime

from atproto import Client

from . import db, embeddings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Collections to backfill
COLLECTIONS = [
    "network.comind.concept",
    "network.comind.thought",
    "network.comind.memory",
    "network.comind.hypothesis",
]

# Comind collective handles
HANDLES = [
    "central.comind.network",
    "void.comind.network",
    "herald.comind.network",
    "grunk.comind.network",
    "archivist.comind.network",
]


def backfill_account(client: Client, engine, handle: str):
    """Backfill all cognition records from an account."""
    import httpx
    
    logger.info(f"Backfilling {handle}...")

    # Resolve handle to DID using public API
    try:
        resp = httpx.get(
            "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile",
            params={"actor": handle},
            timeout=10
        )
        resp.raise_for_status()
        did = resp.json()["did"]
    except Exception as e:
        logger.error(f"Failed to resolve {handle}: {e}")
        return

    session = db.get_session(engine)
    indexed = 0

    try:
        for collection in COLLECTIONS:
            logger.info(f"  Collection: {collection}")
            cursor = None

            while True:
                # List records in collection
                params = {
                    "repo": did,
                    "collection": collection,
                    "limit": 100,
                }
                if cursor:
                    params["cursor"] = cursor

                try:
                    # Use comind PDS directly for custom collections
                    resp = httpx.get(
                        "https://comind.network/xrpc/com.atproto.repo.listRecords",
                        params=params,
                        timeout=30
                    )
                    resp.raise_for_status()
                    response = resp.json()
                except Exception as e:
                    logger.error(f"Failed to list {collection}: {e}")
                    break

                records = response.get("records", [])
                if not records:
                    break

                # Process each record
                for record_view in records:
                    uri = record_view["uri"]
                    rkey = uri.split("/")[-1]
                    record = record_view["value"]

                    # Check if already indexed
                    existing = db.find_by_uri(session, uri)
                    if existing:
                        continue

                    # Extract content
                    content = embeddings.extract_content(record)
                    if not content:
                        continue

                    # Generate embedding
                    try:
                        embedding = embeddings.embed_text(content)
                    except Exception as e:
                        logger.error(f"Embedding failed for {uri}: {e}")
                        continue

                    # Parse timestamp
                    created_at = None
                    if created_str := record.get("createdAt"):
                        try:
                            created_at = datetime.fromisoformat(
                                created_str.replace("Z", "+00:00")
                            )
                        except ValueError:
                            pass

                    # Store record
                    db.upsert_record(
                        session,
                        uri=uri,
                        did=did,
                        collection=collection,
                        rkey=rkey,
                        content=content,
                        embedding=embedding,
                        created_at=created_at,
                    )
                    indexed += 1
                    logger.info(f"    Indexed: {rkey}")

                # Check for more pages
                cursor = response.get("cursor")
                if not cursor:
                    break

    finally:
        session.close()

    logger.info(f"Backfilled {indexed} records from {handle}")


def main():
    """Run the backfill."""
    # Initialize database
    engine = db.get_engine()
    db.init_db(engine)

    # Create unauthenticated client (public data only)
    client = Client()

    for handle in HANDLES:
        backfill_account(client, engine, handle)
    
    logger.info("Backfill complete.")


if __name__ == "__main__":
    main()
