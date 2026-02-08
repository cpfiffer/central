"""Flask XRPC server for comind cognition search."""

import json
import os
import sys
from pathlib import Path

print("=== INDEXER STARTING ===", file=sys.stderr, flush=True)
print(f"DATABASE_URL set: {'DATABASE_URL' in os.environ}", file=sys.stderr, flush=True)
print(f"OPENAI_API_KEY set: {'OPENAI_API_KEY' in os.environ}", file=sys.stderr, flush=True)

from flask import Flask
from lexrpc import Server
from lexrpc.flask_server import init_flask

from . import db, embeddings

# Load lexicons from the lexicons directory
LEXICONS_DIR = Path(__file__).parent.parent / "lexicons"


def load_lexicons() -> list[dict]:
    """Load all lexicon definitions from JSON files."""
    lexicons = []
    for path in LEXICONS_DIR.glob("*.json"):
        with open(path) as f:
            lexicons.append(json.load(f))
    return lexicons


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__)

    # Initialize database
    engine = db.get_engine()
    db.init_db(engine)

    # Create XRPC server with our lexicons
    lexicons = load_lexicons()
    server = Server(lexicons=lexicons)

    # Store engine on app for handlers to access
    app.config["DB_ENGINE"] = engine

    # Register XRPC method handlers
    @server.method("network.comind.search.query")
    def search_query(input, q=None, collections=None, limit=10):
        """Semantic search over cognition records."""
        if not q:
            return {"results": []}

        # Generate embedding for query
        query_embedding = embeddings.embed_text(q)

        # Search database
        session = db.get_session(engine)
        try:
            results = db.search_similar(
                session,
                query_embedding,
                limit=limit,
                collections=collections,
            )

            return {
                "results": [
                    {
                        "uri": record.uri,
                        "did": record.did,
                        "collection": record.collection,
                        "content": record.content[:500] if record.content else None,
                        "score": round(score, 4),
                        "createdAt": record.created_at.isoformat()
                        if record.created_at
                        else None,
                    }
                    for record, score in results
                ]
            }
        finally:
            session.close()

    @server.method("network.comind.search.similar")
    def search_similar(input, uri=None, limit=10):
        """Find records similar to a given record."""
        if not uri:
            return {"source": None, "results": []}

        session = db.get_session(engine)
        try:
            # Find the source record
            source = db.find_by_uri(session, uri)
            if not source or source.embedding is None:
                return {"source": None, "results": []}

            # Search for similar records (exclude the source)
            results = db.search_similar(
                session,
                source.embedding,
                limit=limit + 1,  # +1 to account for source
            )

            # Filter out the source record
            results = [
                (record, score)
                for record, score in results
                if record.uri != uri
            ][:limit]

            return {
                "source": {
                    "uri": source.uri,
                    "content": source.content[:500] if source.content else None,
                },
                "results": [
                    {
                        "uri": record.uri,
                        "did": record.did,
                        "collection": record.collection,
                        "content": record.content[:500] if record.content else None,
                        "score": round(score, 4),
                        "createdAt": record.created_at.isoformat()
                        if record.created_at
                        else None,
                    }
                    for record, score in results
                ],
            }
        finally:
            session.close()

    @server.method("network.comind.index.stats")
    def index_stats(input):
        """Get index statistics."""
        session = db.get_session(engine)
        try:
            return db.get_stats(session)
        finally:
            session.close()

    # Attach XRPC server to Flask app
    init_flask(server, app)

    # Health check endpoint (verifies DB connection)
    @app.route("/health")
    def health():
        try:
            session = db.get_session(engine)
            # Quick DB check
            session.execute(db.text("SELECT 1"))
            session.close()
            return {"status": "ok", "db": "connected"}
        except Exception as e:
            return {"status": "error", "db": str(e)}, 500

    # Root endpoint with service info
    @app.route("/")
    def index():
        return {
            "service": "comind-indexer",
            "description": "Semantic search over agent cognition records on ATProtocol. Namespace-agnostic. Self-registration via network.comind.agent.profile.",
            "endpoints": [
                "/xrpc/network.comind.search.query",
                "/xrpc/network.comind.search.similar",
                "/xrpc/network.comind.index.stats",
            ],
            "mcp": "Connect via MCP: https://github.com/cpfiffer/central/blob/master/tools/mcp_server.py",
            "register": "Publish a network.comind.agent.profile record to get indexed automatically.",
            "documentation": "https://central.comind.network/docs/api/xrpc-indexer",
        }

    return app


# For gunicorn
try:
    print("=== Creating Flask app ===", file=sys.stderr, flush=True)
    app = create_app()
    print("=== Flask app created successfully ===", file=sys.stderr, flush=True)
except Exception as e:
    print(f"=== FATAL: App creation failed: {e} ===", file=sys.stderr, flush=True)
    import traceback
    traceback.print_exc()
    raise


if __name__ == "__main__":
    # Development server
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
