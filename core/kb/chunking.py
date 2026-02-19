"""Deterministic text chunking for vector embedding."""

from __future__ import annotations

from core.config import get_settings


def chunk_text(
    text: str,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> list[str]:
    """Split text into fixed-size character chunks with overlap.

    Deterministic: same input always produces the same output.

    Args:
        text: The text to chunk.
        chunk_size: Max characters per chunk. Defaults to CHUNK_SIZE_CHARS.
        overlap: Characters of overlap between consecutive chunks.
                 Defaults to CHUNK_OVERLAP_CHARS.

    Returns:
        A list of text chunks.
    """
    settings = get_settings()
    chunk_size = chunk_size if chunk_size is not None else settings.CHUNK_SIZE_CHARS
    overlap = overlap if overlap is not None else settings.CHUNK_OVERLAP_CHARS

    if not text:
        return []

    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        if chunk:
            chunks.append(chunk)
        start += chunk_size - overlap

    return chunks
