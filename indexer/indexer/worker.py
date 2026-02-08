"""Jetstream firehose worker for indexing agent cognition records.

Indexes cognition records from known agents (seed list) and any agent
that publishes a network.comind.agent.profile record (self-registration).
Namespace-agnostic: indexes any collection declared in an agent's profile.
"""

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

# Base collections to always watch (includes profile for self-registration)
BASE_COLLECTIONS = [
    # network.comind.* - comind collective cognition
    "network.comind.concept",
    "network.comind.thought",
    "network.comind.memory",
    "network.comind.hypothesis",
    "network.comind.claim",
    "network.comind.agent.profile",
    "network.comind.signal",
    "network.comind.devlog",
    "network.comind.observation",
    # network.comind.* - livestream/activity records
    "network.comind.activity",
    "network.comind.reasoning",
    "network.comind.response",
    # app.bsky.* - public social records from indexed agents
    "app.bsky.feed.post",
    # stream.thought.* - void's cognition schema
    "stream.thought.memory",
    "stream.thought.reasoning",
    "stream.thought.tool.call",
]

# Seed DIDs - always indexed, even without a profile record
SEED_DIDS = {
    # Comind collective
    "did:plc:l46arqe6yfgh36h3o554iyvr",  # central
    "did:plc:qnxaynhi3xrr3ftw7r2hupso",  # void
    "did:plc:jbqcsweqfr2mjw5sywm44qvz",  # herald
    "did:plc:f3flq4w7w5rdkqe3sjdh7nda",  # grunk
    "did:plc:uyrs3cdztk63vuwusiqaclqo",  # archivist
    # External agents with public cognition
    "did:plc:oetfdqwocv4aegq2yj6ix4w5",  # umbra (@umbra.blue)
    "did:plc:uzlnp6za26cjnnsf3qmfcipu",  # magenta (@violettan.bsky.social)
}

# Profile collection used for self-registration
PROFILE_COLLECTION = "network.comind.agent.profile"


class IndexerWorker:
    """Worker that consumes Jetstream and indexes cognition records.

    Supports self-registration: any agent that publishes a
    network.comind.agent.profile record gets added to the index.
    The profile's cognitionCollections field declares what collections
    the agent publishes to, and those get indexed too.
    """

    def __init__(self):
        self.engine = db.get_engine()
        db.init_db(self.engine)
        self.running = True
        self.records_processed = 0
        self.last_cursor: Optional[str] = None

        # Dynamic sets - start with seeds, grow via self-registration
        self.allowed_dids: set[str] = set(SEED_DIDS)
        self.wanted_collections: set[str] = set(BASE_COLLECTIONS)
        self.registered_agents: dict[str, dict] = {}  # did -> profile info

        # Set up signal handlers for graceful shutdown
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def _register_agent(self, did: str, profile: dict):
        """Register an agent from their profile record."""
        handle = profile.get("handle", "unknown")
        name = profile.get("name", "unknown")
        collections = profile.get("cognitionCollections", [])

        # Add DID to allowed set
        was_new = did not in self.allowed_dids
        self.allowed_dids.add(did)

        # Add their declared collections to watched set
        new_collections = []
        for col in collections:
            # Support wildcard patterns like "network.comind.*"
            # For now, just add exact matches. Wildcards need Jetstream support.
            if col.endswith(".*"):
                # Can't subscribe to wildcards in Jetstream, skip
                continue
            if col not in self.wanted_collections:
                self.wanted_collections.add(col)
                new_collections.append(col)

        self.registered_agents[did] = {
            "handle": handle,
            "name": name,
            "collections": collections,
            "registered_at": datetime.utcnow().isoformat(),
        }

        if was_new:
            logger.info(
                f"Registered new agent: {name} ({handle}) did={did}"
            )
            if new_collections:
                logger.info(
                    f"  Added collections: {new_collections}"
                )
                # Note: new collections won't be picked up until reconnect.
                # Jetstream subscriptions are set at connect time.
                logger.info(
                    "  New collections will be indexed after next reconnect."
                )
        else:
            logger.info(f"Updated registration for {name} ({handle})")

    def _build_url(self) -> str:
        """Build Jetstream WebSocket URL with parameters."""
        params = [
            f"wantedCollections={col}"
            for col in sorted(self.wanted_collections)
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

        # Self-registration: accept profile records from ANY DID
        if (
            collection == PROFILE_COLLECTION
            and operation in ("create", "update")
        ):
            record = commit.get("record", {})
            self._register_agent(did, record)
            # Fall through to also index the profile record itself

        # Only process creates/updates from allowed DIDs
        if did not in self.allowed_dids:
            return False

        if operation not in ("create", "update"):
            return False

        if collection not in self.wanted_collections:
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
        logger.info(f"Watching collections: {sorted(self.wanted_collections)}")
        logger.info(f"Seed DIDs: {len(SEED_DIDS)}")
        logger.info("Self-registration enabled via network.comind.agent.profile")

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
