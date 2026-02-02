"""Embedding generation using OpenAI."""

import os
from typing import Optional

from openai import OpenAI

# Default model - good balance of quality and cost
DEFAULT_MODEL = "text-embedding-3-small"


def get_client() -> OpenAI:
    """Get OpenAI client."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


def embed_text(text: str, model: str = DEFAULT_MODEL) -> list[float]:
    """
    Generate embedding for a single text.

    Args:
        text: Text to embed
        model: OpenAI embedding model

    Returns:
        List of floats (1536-dim for text-embedding-3-small)
    """
    client = get_client()
    response = client.embeddings.create(input=text, model=model)
    return response.data[0].embedding


def embed_batch(
    texts: list[str], model: str = DEFAULT_MODEL
) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.

    More efficient than calling embed_text in a loop.

    Args:
        texts: List of texts to embed
        model: OpenAI embedding model

    Returns:
        List of embeddings in same order as input
    """
    if not texts:
        return []

    client = get_client()
    response = client.embeddings.create(input=texts, model=model)

    # Sort by index to maintain order
    embeddings = sorted(response.data, key=lambda x: x.index)
    return [e.embedding for e in embeddings]


def extract_content(record: dict) -> Optional[str]:
    """
    Extract searchable text content from a cognition record.

    Handles different record types:
    - network.comind.concept: title + description + content
    - network.comind.thought: content
    - network.comind.memory: content + context
    """
    parts = []

    # Common fields
    if title := record.get("title"):
        parts.append(title)
    if description := record.get("description"):
        parts.append(description)
    if content := record.get("content"):
        parts.append(content)
    if thought := record.get("thought"):
        parts.append(thought)
    if context := record.get("context"):
        parts.append(context)
    if text := record.get("text"):
        parts.append(text)

    # Tags
    if tags := record.get("tags"):
        if isinstance(tags, list):
            parts.append(" ".join(tags))

    return " ".join(parts) if parts else None
