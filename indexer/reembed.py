"""Re-embed all records using the new embedding model.

Run after switching embedding models to regenerate all vectors.
Safe to re-run: skips records that already have embeddings.

Usage:
    cd indexer && uv run python reembed.py
"""

import os
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from indexer import db, embeddings


def log(msg):
    print(msg, flush=True)


def main():
    engine = db.get_engine()

    # Run migrations (will alter column dimension and clear embeddings if needed)
    log("Running migrations...")
    db.init_db(engine)

    session = db.get_session(engine)

    # Get records that need re-embedding (skip already done)
    records = (
        session.query(db.CognitionRecord)
        .filter(db.CognitionRecord.content.isnot(None))
        .filter(db.CognitionRecord.content != "")
        .filter(db.CognitionRecord.embedding.is_(None))
        .all()
    )

    total = len(records)
    already = (
        session.query(db.CognitionRecord)
        .filter(db.CognitionRecord.embedding.isnot(None))
        .count()
    )
    log(f"Skipping {already} already embedded. Re-embedding {total} records with {embeddings.EMBEDDING_MODEL} ({embeddings.EMBEDDING_DIM} dim)")

    if total == 0:
        log("Nothing to do.")
        return

    # Process in batches
    batch_size = 50  # Smaller batches for reliability
    done = 0
    failed = 0
    start = time.time()

    for i in range(0, total, batch_size):
        batch = records[i : i + batch_size]
        texts = [r.content[:8000] for r in batch]

        try:
            vectors = embeddings.embed_batch(texts)
        except Exception as e:
            log(f"  Batch {i}-{i+len(batch)} failed: {e}")
            # Try individually
            for record in batch:
                try:
                    vec = embeddings.embed_text(record.content[:8000])
                    record.embedding = vec
                    done += 1
                except Exception as e2:
                    log(f"    Record {record.uri}: {e2}")
                    failed += 1
            session.commit()
            continue

        for record, vector in zip(batch, vectors):
            record.embedding = vector

        session.commit()
        done += len(batch)

        elapsed = time.time() - start
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        log(f"  {done}/{total} ({done/total*100:.0f}%) - {rate:.0f} rec/s - ETA {eta:.0f}s")

    elapsed = time.time() - start
    log(f"\nDone. {done} embedded, {failed} failed in {elapsed:.0f}s")

    # Now create the IVFFlat index
    log("Creating IVFFlat index...")
    with engine.connect() as conn:
        from sqlalchemy import text

        conn.execute(text("DROP INDEX IF EXISTS idx_embedding_ivfflat"))
        conn.execute(
            text(
                """
                CREATE INDEX idx_embedding_ivfflat 
                ON cognition_records 
                USING ivfflat (embedding vector_cosine_ops) 
                WITH (lists = 100)
                """
            )
        )
        conn.commit()
    log("Index created.")

    session.close()


if __name__ == "__main__":
    main()
