"""
compression.py
--------------
FEATURE 1: Asset Compression  (Quality Goal Q17 - Reduce Memory Usage)

Large assets -- book descriptions/summaries and cover images -- are the
biggest per-row memory/storage cost in a library catalogue. Instead of
storing them raw, we zlib-compress them before they ever touch the
database, and only decompress a given asset the moment it's actually
displayed to the user (see loader.py for the "on demand" half of this).

This keeps:
  1. The on-disk / in-DB footprint smaller.
  2. The in-memory footprint smaller, because callers hold the compressed
     bytes in memory and only inflate a description/cover for the single
     record currently being viewed, not for every record fetched.
"""

import zlib


def compress_text(text: str, level: int = 6) -> bytes:
    """Compress a text string (UTF-8) to bytes. level: 0 (none) - 9 (max)."""
    if text is None:
        text = ""
    return zlib.compress(text.encode("utf-8"), level)


def decompress_text(blob: bytes) -> str:
    """Reverse of compress_text. Returns '' for empty/None input."""
    if not blob:
        return ""
    return zlib.decompress(blob).decode("utf-8")


def compress_bytes(data: bytes, level: int = 6) -> bytes:
    """Compress arbitrary binary data (e.g. a cover image)."""
    if not data:
        return b""
    return zlib.compress(data, level)


def decompress_bytes(blob: bytes) -> bytes:
    """Reverse of compress_bytes."""
    if not blob:
        return b""
    return zlib.decompress(blob)


def compression_stats(raw_size: int, compressed_size: int) -> dict:
    """Return a small readable report of how much space compression saved."""
    if raw_size == 0:
        return {"raw_bytes": 0, "compressed_bytes": 0, "saved_bytes": 0, "saved_pct": 0.0}
    saved = raw_size - compressed_size
    return {
        "raw_bytes": raw_size,
        "compressed_bytes": compressed_size,
        "saved_bytes": saved,
        "saved_pct": round((saved / raw_size) * 100, 1),
    }
