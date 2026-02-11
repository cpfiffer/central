"""Backfill historical records from ATProto into the indexer.

Fetches all records for each agent's relevant collections from their PDS,
embeds them, and stores in the database. Skips records already indexed.

Usage:
    uv run python -m indexer.backfill                    # All agents
    uv run python -m indexer.backfill --did did:plc:...  # Specific agent
    uv run python -m indexer.backfill --dry-run           # Count only
"""

import argparse
import logging
import time
from datetime import datetime
from typing import Optional

import httpx

from indexer import db, embeddings
from indexer.worker import BASE_COLLECTIONS, SEED_DIDS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


def resolve_pds(did: str) -> Optional[str]:
    """Resolve DID to PDS endpoint."""
    try:
        resp = httpx.get(f"https://plc.directory/{did}", timeout=10)
        resp.raise_for_status()
        doc = resp.json()
        return doc["service"][0]["serviceEndpoint"]
    except Exception as e:
        logger.error(f"Failed to resolve PDS for {did}: {e}")
        return None


def resolve_handle(did: str) -> Optional[str]:
    """Resolve DID to handle."""
    try:
        resp = httpx.get(f"https://plc.directory/{did}", timeout=10)
        resp.raise_for_status()
        doc = resp.json()
        for alias in doc.get("alsoKnownAs", []):
            if alias.startswith("at://"):
                return alias[5:]
    except Exception:
        pass
    return None


def list_records(pds: str, did: str, collection: str):
    """List all records in a collection with pagination."""
    cursor = None
    while True:
        params = {
            "repo": did,
            "collection": collection,
            "limit": 100,
        }
        if cursor:
            params["cursor"] = cursor

        resp = httpx.get(
            f"{pds}/xrpc/com.atproto.repo.listRecords",
            params=params,
            timeout=30,
        )

        if resp.status_code == 400:
            # Collection doesn't exist for this repo
            return
        resp.raise_for_status()
        data = resp.json()

        records = data.get("records", [])
        if not records:
            return

        for record in records:
            yield record

        cursor = data.get("cursor")
        if not cursor:
            break


def get_existing_uris(engine) -> set:
    """Get set of all URIs already in the database."""
    session = db.get_session(engine)
    try:
        from sqlalchemy import text
        result = session.execute(text("SELECT uri FROM cognition_records"))
        return {row[0] for row in result}
    finally:
        session.close()


def backfill_agent(engine, did: str, handle: str, pds: str, collections: list[str], dry_run: bool = False):
    """Backfill all collections for a single agent."""
    logger.info(f"Backfilling @{handle} ({did}) from {pds}")

    existing = get_existing_uris(engine)
    total_new = 0
    total_skipped = 0

    for collection in collections:
        new = 0
        skipped = 0
        batch_texts = []
        batch_records = []

        for record in list_records(pds, did, collection):
            uri = record["uri"]
            if uri in existing:
                skipped += 1
                continue

            value = record.get("value", {})
            content = embeddings.extract_content(value)
            if not content:
                skipped += 1
                continue

            rkey = uri.split("/")[-1]
            created_at = None
            if created_str := value.get("createdAt"):
                try:
                    created_at = datetime.fromisoformat(
                        created_str.replace("Z", "+00:00")
                    )
                except ValueError:
                    pass

            batch_texts.append(content)
            batch_records.append({
                "uri": uri,
                "did": did,
                "collection": collection,
                "rkey": rkey,
                "content": content,
                "created_at": created_at,
                "handle": handle,
            })

            # Process in batches of 100
            if len(batch_texts) >= 100:
                if not dry_run:
                    _store_batch(engine, batch_texts, batch_records)
                new += len(batch_texts)
                batch_texts = []
                batch_records = []
                # Rate limit
                time.sleep(0.5)

        # Process remaining
        if batch_texts:
            if not dry_run:
                _store_batch(engine, batch_texts, batch_records)
            new += len(batch_texts)

        if new > 0 or skipped > 0:
            logger.info(f"  {collection}: {new} new, {skipped} skipped")
        total_new += new
        total_skipped += skipped

    logger.info(f"  Total: {total_new} new, {total_skipped} skipped")
    return total_new


def _store_batch(engine, texts: list[str], records: list[dict]):
    """Embed and store a batch of records."""
    try:
        embs = embeddings.embed_batch(texts)
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return

    session = db.get_session(engine)
    try:
        for rec, emb in zip(records, embs):
            db.upsert_record(
                session,
                uri=rec["uri"],
                did=rec["did"],
                collection=rec["collection"],
                rkey=rec["rkey"],
                content=rec["content"],
                embedding=emb,
                created_at=rec["created_at"],
                handle=rec["handle"],
            )
    except Exception as e:
        logger.error(f"Store failed: {e}")
        session.rollback()
    finally:
        session.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill ATProto records into indexer")
    parser.add_argument("--did", help="Backfill specific DID only")
    parser.add_argument("--dry-run", action="store_true", help="Count records without indexing")
    args = parser.parse_args()

    engine = db.get_engine()
    db.init_db(engine)

    dids = [args.did] if args.did else sorted(SEED_DIDS)
    collections = sorted(BASE_COLLECTIONS)

    total = 0
    for did in dids:
        pds = resolve_pds(did)
        if not pds:
            continue
        handle = resolve_handle(did) or did[:30]
        count = backfill_agent(engine, did, handle, pds, collections, dry_run=args.dry_run)
        total += count

    logger.info(f"Backfill complete. {total} new records indexed.")


if __name__ == "__main__":
    main()
