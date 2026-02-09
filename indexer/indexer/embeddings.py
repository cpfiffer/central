"""Embedding generation using local models via fastembed (ONNX runtime)."""

from typing import Optional

from fastembed import TextEmbedding

# all-MiniLM-L6-v2: 384 dimensions, ~22MB, fast on CPU
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

# Lazy-loaded singleton
_model: Optional[TextEmbedding] = None


def get_model() -> TextEmbedding:
    """Get or create the embedding model (lazy singleton)."""
    global _model
    if _model is None:
        _model = TextEmbedding(model_name=DEFAULT_MODEL)
    return _model


def embed_text(text: str) -> list[float]:
    """
    Generate embedding for a single text.

    Returns:
        List of floats (384-dim for all-MiniLM-L6-v2)
    """
    model = get_model()
    embeddings = list(model.embed([text]))
    return embeddings[0].tolist()


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.

    Args:
        texts: List of texts to embed

    Returns:
        List of embeddings in same order as input
    """
    if not texts:
        return []

    model = get_model()
    embeddings = list(model.embed(texts))
    return [e.tolist() for e in embeddings]


def extract_content(record: dict) -> Optional[str]:
    """
    Extract searchable text content from a cognition record.

    Handles different record types:
    - network.comind.concept: title + description + content
    - network.comind.thought: content
    - network.comind.memory: content + context
    - app.bsky.feed.post: text
    """
    parts = []

    # Common fields
    if name := record.get("name"):
        parts.append(name)
    if title := record.get("title"):
        parts.append(title)
    if description := record.get("description"):
        parts.append(description)
    if content := record.get("content"):
        parts.append(content)
    if thought := record.get("thought"):
        parts.append(thought)
    if claim := record.get("claim"):
        parts.append(claim)
    if hypothesis := record.get("hypothesis"):
        parts.append(hypothesis)
    if understanding := record.get("understanding"):
        parts.append(understanding)
    if context := record.get("context"):
        parts.append(context)
    if text := record.get("text"):
        parts.append(text)
    if domain := record.get("domain"):
        parts.append(domain)

    # Tags
    if tags := record.get("tags"):
        if isinstance(tags, list):
            parts.append(" ".join(tags))

    return " ".join(parts) if parts else None
