"""
memory_report.py
----------------
Ties all four Q17 features together into one readable report so the
memory-usage improvement is actually *visible*, not just asserted.

Uses tracemalloc (Python's built-in memory profiler) to measure:
  1. Eager load (all books materialised into a list) vs. On-Demand
     paginated load -- peak memory for each.
  2. Raw vs. compressed size of stored descriptions/covers.
  3. Current query-cache footprint (bounded, from cache.py stats).
  4. Current DB file size (post-purge effect, from purge.py).
"""

import tracemalloc

from db import get_connection
import loader
import compression
import cache as cache_module
import purge


def _fmt_kb(num_bytes: int) -> str:
    return f"{num_bytes / 1024:.1f} KB"


def measure_eager_vs_lazy_load():
    """
    Compares peak memory of two ways to "browse the catalogue":

      (a) naive/legacy style: fetchall() the whole table AND eagerly
          decompress every book's description/cover up front, keeping
          the full list alive -- this is what a system without Features
          1+2 would typically do when listing books.
      (b) this system: stream books page-by-page via the generator and
          only touch cheap fields (title/author) for the normal browse
          view, leaving description/cover compressed and undecompressed
          until a specific book's details are actually opened.

    Both scenarios read the exact same rows from the exact same table;
    the only difference is *how much of each row* gets materialised.
    """
    from models import Book

    # --- (a) naive: decompress everything, hold it all in memory ---
    tracemalloc.start()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM books")
    rows = cur.fetchall()
    naive_list = []
    for r in rows:
        b = Book(r)
        _ = b.description   # force-decompress, as a naive "load it all" design would
        _ = b.cover_bytes
        naive_list.append(b)
    _, eager_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    conn.close()
    del naive_list

    # --- (b) this system: paginated, browse-only (no decompression) ---
    tracemalloc.start()
    peak_seen = 0
    for book in loader.iter_all_books(page_size=20):
        _ = book.title  # typical browse-list usage -- description/cover untouched
        _, peak_now = tracemalloc.get_traced_memory()
        peak_seen = max(peak_seen, peak_now)
    lazy_peak = peak_seen
    tracemalloc.stop()

    return {
        "eager_peak_bytes": eager_peak,
        "lazy_peak_bytes": lazy_peak,
        "reduction_pct": round((1 - lazy_peak / eager_peak) * 100, 1) if eager_peak else 0.0,
    }


def compression_summary():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COALESCE(SUM(description_raw_size),0) r, "
        "COALESCE(SUM(LENGTH(description_compressed)),0) c, "
        "COALESCE(SUM(cover_raw_size),0) cr, "
        "COALESCE(SUM(LENGTH(cover_compressed)),0) cc FROM books"
    )
    row = cur.fetchone()
    conn.close()
    raw_total = row["r"] + row["cr"]
    compressed_total = row["c"] + row["cc"]
    return compression.compression_stats(raw_total, compressed_total)


def print_full_report():
    print("\n" + "=" * 60)
    print(" MEMORY USAGE REPORT  -  Q17: Reduce Memory Usage")
    print("=" * 60)

    n = loader.count_books()
    if n == 0:
        print("No books in the catalogue yet -- add some books first, "
              "then run this report again to see real numbers.")
        return

    print(f"\nCatalogue size: {n} book(s)\n")

    print("-- Feature 2: On-Demand Data Loading --")
    m = measure_eager_vs_lazy_load()
    print(f"  Eager load (fetchall) peak memory : {_fmt_kb(m['eager_peak_bytes'])}")
    print(f"  On-demand (paginated) peak memory : {_fmt_kb(m['lazy_peak_bytes'])}")
    print(f"  Peak memory reduction             : {m['reduction_pct']}%")

    print("\n-- Feature 1: Asset Compression --")
    c = compression_summary()
    print(f"  Raw size (descriptions + covers)  : {_fmt_kb(c['raw_bytes'])}")
    print(f"  Compressed size                   : {_fmt_kb(c['compressed_bytes'])}")
    print(f"  Space saved                       : {_fmt_kb(c['saved_bytes'])} ({c['saved_pct']}%)")

    print("\n-- Feature 4: Query Caching --")
    s = cache_module.search_cache.stats()
    print(f"  Cache entries                     : {s['entries']} / {s['max_entries']} (bounded)")
    print(f"  Hits / Misses                     : {s['hits']} / {s['misses']}")
    print(f"  Hit rate                          : {s['hit_rate_pct']}%")

    print("\n-- Feature 3: DB Purge Tools --")
    print(f"  Current database file size        : {_fmt_kb(purge.get_db_file_size())}")

    print("\n" + "=" * 60 + "\n")
