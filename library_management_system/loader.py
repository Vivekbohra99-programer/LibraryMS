"""
loader.py
---------
FEATURE 2: On-Demand Data Loading  (Quality Goal Q17 - Reduce Memory Usage)

The naive way to "list all books" is:
    rows = cursor.execute("SELECT * FROM books").fetchall()
which pulls every single row into a Python list in one go. For a
catalogue of a few thousand books with compressed covers, that list can
get large fast, and almost all of it is completely irrelevant to a user
who only ever looks at one page of results at a time.

Instead, every bulk-read function here is a GENERATOR that fetches rows
in small pages (via SQLite's cursor.fetchmany), yielding one Book object
at a time. The caller only holds one page (or even one row) in memory at
once, no matter how big the underlying table is.

FEATURE 4 (Query Caching) also lives partly here: search_books() checks
the shared LRU cache before hitting the database, and only caches the
lightweight *id list* of a result (not full Book objects with covers) so
cache entries stay cheap.
"""

from db import get_connection
from models import Book
from cache import search_cache

PAGE_SIZE = 20


def iter_all_books(page_size: int = PAGE_SIZE):
    """
    Yield every book in the catalogue, one at a time, fetching from
    SQLite in pages of `page_size` rows instead of loading the whole
    table into memory.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM books ORDER BY id")
    while True:
        rows = cur.fetchmany(page_size)
        if not rows:
            break
        for row in rows:
            yield Book(row)
    conn.close()


def get_books_page(page_number: int = 1, page_size: int = PAGE_SIZE):
    """
    Return exactly one page of Book objects (page_number is 1-indexed).
    Used by the CLI's "browse books" screen so it only ever materialises
    `page_size` books in memory, however large the catalogue grows.
    """
    offset = (page_number - 1) * page_size
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM books ORDER BY id LIMIT ? OFFSET ?",
        (page_size, offset),
    )
    rows = cur.fetchall()
    conn.close()
    return [Book(row) for row in rows]


def count_books() -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM books")
    n = cur.fetchone()["c"]
    conn.close()
    return n


def search_books(field: str, term: str):
    """
    Search books by 'title', 'author', or 'category'.

    Query Caching: the (field, term) pair is used as a cache key. On a
    cache hit we skip the database round-trip entirely and just re-fetch
    the small set of cached ids (still going through get_book_by_id,
    which is cheap for a handful of rows).
    """
    assert field in ("title", "author", "category")
    key = ("search", field, term.lower())

    cached_ids = search_cache.get(key)
    if cached_ids is not None:
        return [get_book_by_id(bid) for bid in cached_ids if get_book_by_id(bid)]

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        f"SELECT * FROM books WHERE lower({field}) LIKE ? ORDER BY id",
        (f"%{term.lower()}%",),
    )
    rows = cur.fetchall()
    conn.close()

    books = [Book(row) for row in rows]
    search_cache.set(key, [b.id for b in books])
    return books


def get_book_by_id(book_id: int):
    key = ("book", book_id)
    cached = search_cache.get(key)
    if cached is not None:
        return cached

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM books WHERE id = ?", (book_id,))
    row = cur.fetchone()
    conn.close()
    if row is None:
        return None
    book = Book(row)
    search_cache.set(key, book)
    return book
