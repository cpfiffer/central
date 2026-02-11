"""Embedding generation using OpenAI text-embedding-3-small API."""

import os
from typing import Optional

import httpx

# OpenAI text-embedding-3-small: 1536 dimensions, $0.02/1M tokens
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
OPENAI_API_URL = "https://api.openai.com/v1/embeddings"

# Reusable client
_client: Optional[httpx.Client] = None


def _get_client() -> httpx.Client:
    """Get or create the HTTP client."""
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not set")
        _client = httpx.Client(
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
    return _client


def embed_text(text: str) -> list[float]:
    """
    Generate embedding for a single text.

    Returns:
        List of floats (1536-dim for text-embedding-3-small)
    """
    client = _get_client()
    resp = client.post(
        OPENAI_API_URL,
        json={"input": text, "model": EMBEDDING_MODEL},
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for multiple texts.

    Args:
        texts: List of texts to embed (max 2048 per request)

    Returns:
        List of embeddings in same order as input
    """
    if not texts:
        return []

    client = _get_client()
    all_embeddings = []

    # OpenAI supports up to 2048 inputs per request
    for i in range(0, len(texts), 2048):
        batch = texts[i : i + 2048]
        resp = client.post(
            OPENAI_API_URL,
            json={"input": batch, "model": EMBEDDING_MODEL},
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        # Sort by index to maintain order
        data.sort(key=lambda x: x["index"])
        all_embeddings.extend([d["embedding"] for d in data])

    return all_embeddings


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
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, dict):
            # Handle nested content (e.g., pub.leaflet.content)
            for page in content.get("pages", []):
                for block_wrapper in page.get("blocks", []):
                    block = block_wrapper.get("block", block_wrapper)
                    if plaintext := block.get("plaintext"):
                        parts.append(plaintext)
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
