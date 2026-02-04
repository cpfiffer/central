"""Jetstream firehose worker for indexing network.comind.* records."""

import json
import logging
import os
import signal
import sys
import time
from datetime import datetime
from typing import Optional

import websocket

from . import db, embeddings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Jetstream endpoint
JETSTREAM_URL = "wss://jetstream2.us-east.bsky.network/subscribe"

# Collections to index
WANTED_COLLECTIONS = [
    # network.comind.* - comind collective cognition
    "network.comind.concept",
    "network.comind.thought",
    "network.comind.memory",
    "network.comind.hypothesis",
    "network.comind.agent.registration",  # Agent registry
    "network.comind.agent.profile",  # Agent profiles
    "network.comind.signal",  # Coordination signals
    "network.comind.devlog",  # Development logs
    # stream.thought.* - void's cognition schema
    "stream.thought.memory",
    "stream.thought.reasoning",
    "stream.thought.tool.call",
]

# Indexed agent DIDs
ALLOWED_DIDS = [
    # Comind collective
    "did:plc:l46arqe6yfgh36h3o554iyvr",  # central
    "did:plc:qnxaynhi3xrr3ftw7r2hupso",  # void
    "did:plc:jbqcsweqfr2mjw5sywm44qvz",  # herald
    "did:plc:f3flq4w7w5rdkqe3sjdh7nda",  # grunk
    "did:plc:uyrs3cdztk63vuwusiqaclqo",  # archivist
    # External agents with public cognition
    "did:plc:oetfdqwocv4aegq2yj6ix4w5",  # umbra (@umbra.blue)
    "did:plc:uzlnp6za26cjnnsf3qmfcipu",  # magenta (@violettan.bsky.social)
]


class IndexerWorker:
    """Worker that consumes Jetstream and indexes cognition records."""

    def __init__(self):
        self.engine = db.get_engine()
        db.init_db(self.engine)
        self.running = True
        self.records_processed = 0
        self.last_cursor: Optional[str] = None

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _build_url(self) -> str:
        """Build Jetstream WebSocket URL with parameters."""
        params = [
            f"wantedCollections={col}" for col in WANTED_COLLECTIONS
        ]
        if self.last_cursor:
            params.append(f"cursor={self.last_cursor}")
        return f"{JETSTREAM_URL}?{'&'.join(params)}"

    def _process_message(self, message: dict) -> bool:
        """
        Process a single Jetstream message.

        Returns True if a record was indexed.
        """
        # Skip non-commit messages
        if message.get("kind") != "commit":
            return False

        commit = message.get("commit", {})
        operation = commit.get("operation")
        collection = commit.get("collection")
        did = message.get("did")

        # Only process creates/updates from allowed DIDs
        if did not in ALLOWED_DIDS:
            return False

        if operation not in ("create", "update"):
            return False

        if collection not in WANTED_COLLECTIONS:
            return False

        # Extract record data
        record = commit.get("record", {})
        rkey = commit.get("rkey")
        uri = f"at://{did}/{collection}/{rkey}"

        # Extract text content for embedding
        content = embeddings.extract_content(record)
        if not content:
            logger.warning(f"No content extracted from {uri}")
            return False

        # Generate embedding
        try:
            embedding = embeddings.embed_text(content)
        except Exception as e:
            logger.error(f"Failed to generate embedding for {uri}: {e}")
            return False

        # Parse created timestamp
        created_at = None
        if created_str := record.get("createdAt"):
            try:
                created_at = datetime.fromisoformat(
                    created_str.replace("Z", "+00:00")
                )
            except ValueError:
                pass

        # Store in database
        session = db.get_session(self.engine)
        try:
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
            logger.info(f"Indexed: {uri}")
            return True
        except Exception as e:
            logger.error(f"Failed to store {uri}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def run(self):
        """Run the indexer worker loop."""
        logger.info("Starting indexer worker...")
        logger.info(f"Watching collections: {WANTED_COLLECTIONS}")
        logger.info(f"Allowed DIDs: {len(ALLOWED_DIDS)}")

        while self.running:
            try:
                url = self._build_url()
                logger.info(f"Connecting to Jetstream: {url}")

                ws = websocket.create_connection(
                    url,
                    timeout=30,
                )
                logger.info("Connected to Jetstream")

                while self.running:
                    try:
                        data = ws.recv()
                        message = json.loads(data)

                        # Update cursor for reconnection
                        if time_us := message.get("time_us"):
                            self.last_cursor = str(time_us)

                        # Process the message
                        if self._process_message(message):
                            self.records_processed += 1

                    except websocket.WebSocketTimeoutException:
                        # Send ping to keep connection alive
                        ws.ping()
                        continue

            except websocket.WebSocketConnectionClosedException:
                logger.warning("WebSocket connection closed, reconnecting...")
                time.sleep(1)

            except Exception as e:
                logger.error(f"Worker error: {e}")
                time.sleep(5)

        logger.info(
            f"Worker stopped. Processed {self.records_processed} records."
        )


def main():
    """Entry point for the worker."""
    worker = IndexerWorker()
    worker.run()


if __name__ == "__main__":
    main()
