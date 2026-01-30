"""Database layer for cognition record indexing with pgvector."""

import os
from datetime import datetime
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    func,
    text,
)
from sqlalchemy.orm import Session, declarative_base, sessionmaker

Base = declarative_base()

# Embedding dimension for text-embedding-3-small
EMBEDDING_DIM = 1536


class CognitionRecord(Base):
    """A cognition record indexed for semantic search."""

    __tablename__ = "cognition_records"

    id = Column(Integer, primary_key=True)
    uri = Column(String(500), unique=True, nullable=False)
    did = Column(String(100), nullable=False)
    collection = Column(String(100), nullable=False)
    rkey = Column(String(100), nullable=False)
    content = Column(Text)
    embedding = Column(Vector(EMBEDDING_DIM))
    created_at = Column(DateTime(timezone=True))
    indexed_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Indexes defined via __table_args__
    __table_args__ = (
        Index("idx_collection", "collection"),
        Index("idx_did", "did"),
        Index("idx_created", "created_at"),
    )


def get_engine(database_url: Optional[str] = None):
    """Create SQLAlchemy engine."""
    url = database_url or os.environ.get("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL not set")
    # Railway uses postgres:// but SQLAlchemy needs postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return create_engine(url, pool_pre_ping=True)


def get_session(engine) -> Session:
    """Create a new database session."""
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def init_db(engine):
    """Initialize database schema and extensions."""
    with engine.connect() as conn:
        # Enable pgvector extension
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

    # Create tables
    Base.metadata.create_all(engine)

    # Create IVFFlat index for vector similarity (after table exists)
    with engine.connect() as conn:
        # Check if index exists
        result = conn.execute(
            text(
                "SELECT 1 FROM pg_indexes WHERE indexname = 'idx_embedding_ivfflat'"
            )
        )
        if not result.fetchone():
            # Create IVFFlat index with cosine similarity
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


def upsert_record(
    session: Session,
    uri: str,
    did: str,
    collection: str,
    rkey: str,
    content: str,
    embedding: list[float],
    created_at: Optional[datetime] = None,
) -> CognitionRecord:
    """Insert or update a cognition record."""
    record = session.query(CognitionRecord).filter_by(uri=uri).first()
    if record:
        record.content = content
        record.embedding = embedding
        record.indexed_at = datetime.utcnow()
    else:
        record = CognitionRecord(
            uri=uri,
            did=did,
            collection=collection,
            rkey=rkey,
            content=content,
            embedding=embedding,
            created_at=created_at,
            indexed_at=datetime.utcnow(),
        )
        session.add(record)
    session.commit()
    return record


def search_similar(
    session: Session,
    query_embedding: list[float],
    limit: int = 10,
    collections: Optional[list[str]] = None,
) -> list[tuple[CognitionRecord, float]]:
    """
    Search for records similar to the query embedding.

    Returns list of (record, score) tuples, where score is 0-1 (higher = more similar).
    """
    # Build query with cosine distance
    query = session.query(
        CognitionRecord,
        (1 - CognitionRecord.embedding.cosine_distance(query_embedding)).label(
            "score"
        ),
    )

    # Filter by collections if specified
    if collections:
        query = query.filter(CognitionRecord.collection.in_(collections))

    # Order by similarity (cosine distance ascending = most similar first)
    query = query.order_by(
        CognitionRecord.embedding.cosine_distance(query_embedding)
    ).limit(limit)

    return [(record, score) for record, score in query.all()]


def find_by_uri(session: Session, uri: str) -> Optional[CognitionRecord]:
    """Find a record by its AT URI."""
    return session.query(CognitionRecord).filter_by(uri=uri).first()


def get_stats(session: Session) -> dict:
    """Get index statistics."""
    # Total count
    total = session.query(func.count(CognitionRecord.id)).scalar() or 0

    # Count by collection
    collection_counts = (
        session.query(
            CognitionRecord.collection, func.count(CognitionRecord.id)
        )
        .group_by(CognitionRecord.collection)
        .all()
    )
    by_collection = {col: count for col, count in collection_counts}

    # Unique DIDs
    dids = [
        row[0]
        for row in session.query(CognitionRecord.did).distinct().all()
    ]

    # Most recent indexed
    last_indexed = (
        session.query(func.max(CognitionRecord.indexed_at)).scalar()
    )

    return {
        "totalRecords": total,
        "byCollection": by_collection,
        "indexedDids": dids,
        "lastIndexed": last_indexed.isoformat() if last_indexed else None,
    }
