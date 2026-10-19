# Library Management System — [Q17: Reduce Memory Usage]

A command-line Library Management System in Python, built for the **Q17 (Reduce
Memory Usage)** quality goal, implementing all four required features:

| # | Feature | File |
|---|---------|------|
| 1 | Asset Compression | `compression.py` |
| 2 | On-Demand Data Loading | `loader.py`, `models.py` |
| 3 | DB Purge Tools | `purge.py` |
| 4 | Query Caching | `cache.py` |

## Why these features reduce memory usage

**1. Asset Compression** — Book descriptions and cover images are the largest
per-record payloads in a library catalogue. They are `zlib`-compressed
*before* they are written to the database, and stored compressed. In the demo
data this alone cuts storage for text assets by **~97%**.

**2. On-Demand Data Loading** — Two levels:
- *Query level* (`loader.py`): book listings are fetched from SQLite in small
  pages (`fetchmany`) via generators, instead of pulling the entire catalogue
  into a Python list with `fetchall()`. A UI showing "page 1 of results" never
  holds more than one page in memory, no matter how large the catalogue gets.
- *Object level* (`models.py`): a `Book`'s description/cover stay compressed
  inside the object and are only decompressed the instant something reads
  `.description` or `.cover_bytes`. Browsing a list of titles never pays the
  decompression cost at all.

**3. DB Purge Tools** — Closed-out ("returned") transactions older than a
configurable cutoff can be archived into cold storage or hard-deleted (with
optional CSV export first). A `VACUUM` tool reclaims the freed SQLite pages so
the on-disk file — and the OS page cache built around it — actually shrinks.

**4. Query Caching** — A bounded LRU (Least-Recently-Used) cache with a TTL
sits in front of repeated searches/lookups. Because it's bounded (`maxsize`),
it can never grow without limit — it evicts old entries instead — so caching
speeds things up *without* becoming its own memory problem. Any write
(add/issue/return/purge) invalidates the cache so stale data is never served.

## Project structure

```
library_management_system/
├── main.py              # CLI entry point / menu
├── db.py                # SQLite schema + connections
├── models.py             # Book / Member objects (lazy decompression)
├── compression.py        # Feature 1: Asset Compression
├── loader.py              # Feature 2: On-Demand / paginated loading + search
├── cache.py               # Feature 4: bounded LRU Query Cache
├── purge.py               # Feature 3: DB Purge Tools + VACUUM
├── memory_report.py       # Ties all 4 features into one readable report
├── seed_and_test.py       # Optional: seeds sample data & self-tests everything
└── data/                  # SQLite database file lives here (auto-created)
```

## Requirements

Python 3.9+ and the standard library only — no `pip install` needed.

## Running it

```bash
# 1. (Optional but recommended) seed sample data and see a self-test run,
#    including a real before/after memory usage report:
python seed_and_test.py

# 2. Run the actual application:
python main.py
```

### Menu overview (`main.py`)

```
1. Add Book               5. Issue Book
2. Browse Books (paged)    6. Return Book
3. Search Books            7. Admin Tools
4. Add Member              0. Exit
```

**Admin Tools** (option 7) is where the memory-management features live:
archiving/purging old transactions, vacuuming the database, viewing cache
stats, and running the full memory usage report.

## Sample report output

Running `python seed_and_test.py` seeds a 300-book catalogue and prints a
report similar to this (your numbers will vary slightly):

```
-- Feature 2: On-Demand Data Loading --
  Eager load (fetchall) peak memory : 1176.0 KB
  On-demand (paginated) peak memory : 29.1 KB
  Peak memory reduction             : 97.5%

-- Feature 1: Asset Compression --
  Raw size (descriptions + covers)  : 925.8 KB
  Compressed size                   : 27.5 KB
  Space saved                       : 898.2 KB (97.0%)

-- Feature 4: Query Caching --
  Cache entries                     : 32 / 32 (bounded)
  Hit rate                          : 49.8%

-- Feature 3: DB Purge Tools --
  Current database file size        : 128.0 KB
```

## Notes for the report/viva

- The database engine is **SQLite** (via Python's built-in `sqlite3` module)
  so the project runs anywhere with no server setup. Swapping to MySQL later
  only requires changing `db.py`'s connection function — every other module
  talks to the DB only through `db.get_connection()`.
- `memory_report.py` uses Python's built-in `tracemalloc` module to produce
  real, measured memory numbers rather than estimates — useful evidence for
  the "Reduce Memory Usage" quality goal in your submission.
