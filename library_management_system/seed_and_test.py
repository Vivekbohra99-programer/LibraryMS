"""
seed_and_test.py
----------------
Not part of the delivered app menu -- this is a self-test / demo seeder
that populates sample data and exercises every Q17 feature end-to-end,
so correctness can be verified without manual CLI input.

Run with: python seed_and_test.py
"""

import os
import random
from datetime import datetime, timedelta

from db import init_db, get_connection, DB_PATH
import compression
import loader
import cache as cache_module
import purge
import memory_report

SAMPLE_DESCRIPTION = (
    "This is a sample long-form book summary used to demonstrate asset "
    "compression. " * 40
)

TITLES = [
    ("Clean Code", "Robert C. Martin", "Software"),
    ("The Pragmatic Programmer", "Andrew Hunt", "Software"),
    ("Introduction to Algorithms", "Thomas H. Cormen", "Computer Science"),
    ("Database System Concepts", "Abraham Silberschatz", "Computer Science"),
    ("Operating System Concepts", "Abraham Silberschatz", "Computer Science"),
    ("Design Patterns", "Erich Gamma", "Software"),
    ("The Mythical Man-Month", "Fred Brooks", "Software"),
    ("Computer Networks", "Andrew S. Tanenbaum", "Networking"),
    ("Artificial Intelligence: A Modern Approach", "Stuart Russell", "AI"),
    ("Deep Learning", "Ian Goodfellow", "AI"),
]


def reset_db():
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db()


def seed_books(n_copies_each=2, total_books=300):
    """
    Seed `total_books` catalogue entries (cycling through the sample
    titles with numbered variants) so the memory-usage report has a
    realistic-sized catalogue to measure against, rather than just the
    handful of distinct titles in TITLES.
    """
    conn = get_connection()
    cur = conn.cursor()
    desc_compressed = compression.compress_text(SAMPLE_DESCRIPTION)
    raw_size = len(SAMPLE_DESCRIPTION.encode("utf-8"))

    for i in range(total_books):
        title, author, category = TITLES[i % len(TITLES)]
        variant = i // len(TITLES)
        full_title = title if variant == 0 else f"{title} (Vol. {variant + 1})"
        cur.execute(
            """
            INSERT INTO books (title, author, isbn, category, total_copies,
                                available_copies, description_compressed,
                                description_raw_size, added_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (full_title, author, f"ISBN-{random.randint(100000,999999)}-{i}", category,
             n_copies_each, n_copies_each, desc_compressed,
             raw_size, "2026-01-01"),
        )
    conn.commit()
    conn.close()
    print(f"Seeded {total_books} books.")


def seed_members(n=5):
    conn = get_connection()
    cur = conn.cursor()
    for i in range(1, n + 1):
        cur.execute(
            "INSERT INTO members (name, email, phone, joined_date, active) VALUES (?, ?, ?, ?, 1)",
            (f"Member {i}", f"member{i}@example.com", f"90000000{i}", "2026-01-01"),
        )
    conn.commit()
    conn.close()
    print(f"Seeded {n} members.")


def seed_old_transactions(n=10, days_old=400):
    """Create returned transactions far enough in the past to be purge-eligible."""
    conn = get_connection()
    cur = conn.cursor()
    old_date = (datetime.now() - timedelta(days=days_old)).strftime("%Y-%m-%d %H:%M:%S")
    for i in range(n):
        book_id = (i % len(TITLES)) + 1
        member_id = (i % 5) + 1
        cur.execute(
            """
            INSERT INTO transactions (book_id, member_id, issue_date, due_date, return_date, status)
            VALUES (?, ?, ?, ?, ?, 'returned')
            """,
            (book_id, member_id, old_date, old_date, old_date),
        )
    conn.commit()
    conn.close()
    print(f"Seeded {n} old returned transactions (eligible for purge).")


def test_search_and_cache():
    print("\n-- Testing search + cache (Feature 4) --")
    r1 = loader.search_books("category", "Software")
    print(f"First search (cold): {len(r1)} result(s)")
    r2 = loader.search_books("category", "Software")
    print(f"Second search (should hit cache): {len(r2)} result(s)")
    stats = cache_module.search_cache.stats()
    print(f"Cache stats: {stats}")
    assert stats["hits"] >= 1, "Expected at least one cache hit"


def test_pagination():
    print("\n-- Testing on-demand pagination (Feature 2) --")
    total = loader.count_books()
    page1 = loader.get_books_page(1, page_size=5)
    print(f"Total books: {total}, page 1 size: {len(page1)}")
    assert len(page1) <= 5


def test_compression():
    print("\n-- Testing asset compression (Feature 1) --")
    raw = SAMPLE_DESCRIPTION
    comp = compression.compress_text(raw)
    stats = compression.compression_stats(len(raw.encode("utf-8")), len(comp))
    print(f"Compression stats for one description: {stats}")
    assert stats["saved_bytes"] > 0


def test_purge_and_vacuum():
    print("\n-- Testing DB purge + vacuum (Feature 3) --")
    purged = purge.archive_old_transactions(older_than_days=365, hard_delete=False)
    print(f"Archived {purged} old transaction(s).")
    result = purge.vacuum_database()
    print(f"Vacuum result: {result}")


def test_book_object_lazy_load():
    print("\n-- Testing Book lazy decompression (Feature 2, object level) --")
    b = loader.get_book_by_id(1)
    assert b._description_cache is None, "Description should NOT be decompressed yet"
    _ = b.description  # trigger lazy decompression
    assert b._description_cache is not None, "Description should now be cached"
    print("Lazy decompression works as expected.")


if __name__ == "__main__":
    reset_db()
    seed_books()
    seed_members()
    seed_old_transactions()

    test_compression()
    test_pagination()
    test_search_and_cache()
    test_book_object_lazy_load()
    test_purge_and_vacuum()

    memory_report.print_full_report()

    print("\nALL TESTS PASSED.")
