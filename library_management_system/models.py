"""
models.py
---------
Lightweight wrapper objects around raw sqlite3.Row data.

The Book class is where "On-Demand Data Loading" (Feature 2) shows up at
the object level: description and cover image are kept COMPRESSED and are
only decompressed the instant something actually asks for `.description`
or `.cover_bytes`. If nobody asks, the CPU/memory cost of inflating them
is never paid at all.
"""

import compression


class Book:
    __slots__ = (
        "id", "title", "author", "isbn", "category",
        "total_copies", "available_copies", "added_date",
        "_description_compressed", "_description_raw_size",
        "_cover_compressed", "_cover_raw_size",
        "_description_cache", "_cover_cache",
    )

    def __init__(self, row):
        self.id = row["id"]
        self.title = row["title"]
        self.author = row["author"]
        self.isbn = row["isbn"]
        self.category = row["category"]
        self.total_copies = row["total_copies"]
        self.available_copies = row["available_copies"]
        self.added_date = row["added_date"]

        self._description_compressed = row["description_compressed"]
        self._description_raw_size = row["description_raw_size"]
        self._cover_compressed = row["cover_compressed"]
        self._cover_raw_size = row["cover_raw_size"]

        # Decompressed values are NOT computed here -- only cached lazily
        # the first time they're actually requested (see properties below).
        self._description_cache = None
        self._cover_cache = None

    @property
    def description(self) -> str:
        """Decompressed on first access only, then memoised for this object."""
        if self._description_cache is None:
            self._description_cache = compression.decompress_text(
                self._description_compressed
            )
        return self._description_cache

    @property
    def cover_bytes(self) -> bytes:
        """Decompressed on first access only, then memoised for this object."""
        if self._cover_cache is None:
            self._cover_cache = compression.decompress_bytes(self._cover_compressed)
        return self._cover_cache

    @property
    def compressed_footprint(self) -> int:
        """Bytes this book actually occupies in memory right now (compressed forms)."""
        return len(self._description_compressed or b"") + len(self._cover_compressed or b"")

    @property
    def raw_footprint(self) -> int:
        """Bytes this book WOULD occupy if description/cover were stored raw."""
        return (self._description_raw_size or 0) + (self._cover_raw_size or 0)

    def __repr__(self):
        return f"<Book #{self.id} '{self.title}' by {self.author}>"


class Member:
    __slots__ = ("id", "name", "email", "phone", "joined_date", "active")

    def __init__(self, row):
        self.id = row["id"]
        self.name = row["name"]
        self.email = row["email"]
        self.phone = row["phone"]
        self.joined_date = row["joined_date"]
        self.active = bool(row["active"])

    def __repr__(self):
        return f"<Member #{self.id} {self.name}>"
