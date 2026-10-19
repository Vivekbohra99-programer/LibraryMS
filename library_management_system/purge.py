"""
purge.py
--------
FEATURE 3: DB Purge Tools  (Quality Goal Q17 - Reduce Memory Usage)

A library's `transactions` table only ever grows -- every issue/return
adds a row that is kept forever by default. Old, closed-out (returned)
transactions are rarely queried but still get scanned, indexed, and
cached like everything else, quietly inflating the working set that
every other feature (loader, cache) has to deal with.

This module gives the admin two purge tools:
  1. archive_old_transactions() - moves old *returned* transactions out
     of the hot `transactions` table into `archived_transactions`
     (or exports + deletes them, if the caller asks for a hard purge).
  2. vacuum_database() - reclaims freed disk pages after a purge, via
     SQLite's own VACUUM command, so the on-disk file (and the OS page
     cache built around it) actually shrinks instead of just having
     "holes" in it.
"""

import csv
import os
from datetime import datetime, timedelta

from db import get_connection, DB_PATH, now_str
from cache import search_cache


def archive_old_transactions(older_than_days: int = 365, hard_delete: bool = False, export_csv: str = None):
    """
    Move 'returned' transactions older than `older_than_days` (by return
    date) out of the hot table.

    - If hard_delete is False (default): rows are copied into
      `archived_transactions` (cold storage) and removed from the hot
      `transactions` table.
    - If hard_delete is True: rows are optionally exported to a CSV file
      first (export_csv path), then permanently deleted -- no copy is
      kept in the database at all.

    Returns the number of rows purged.
    """
    cutoff = (datetime.now() - timedelta(days=older_than_days)).strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM transactions
        WHERE status = 'returned' AND return_date IS NOT NULL AND return_date < ?
        """,
        (cutoff,),
    )
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return 0

    if hard_delete and export_csv:
        with open(export_csv, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(rows[0].keys())
            for r in rows:
                writer.writerow(tuple(r))

    if not hard_delete:
        archived_on = now_str()
        cur.executemany(
            """
            INSERT INTO archived_transactions
                (id, book_id, member_id, issue_date, due_date, return_date, status, archived_on)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (r["id"], r["book_id"], r["member_id"], r["issue_date"],
                 r["due_date"], r["return_date"], r["status"], archived_on)
                for r in rows
            ],
        )

    ids = [r["id"] for r in rows]
    cur.executemany("DELETE FROM transactions WHERE id = ?", [(i,) for i in ids])
    conn.commit()
    conn.close()

    # Purged data may have been part of a cached query result -- drop
    # everything rather than risk serving stale/deleted rows.
    search_cache.invalidate_all()

    return len(rows)


def vacuum_database() -> dict:
    """
    Reclaim disk space freed by deletes/archival. Returns the DB file
    size before and after, so the effect of a purge is visible.
    """
    before = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0

    conn = get_connection()
    conn.execute("VACUUM")
    conn.close()

    after = os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
    return {"before_bytes": before, "after_bytes": after, "reclaimed_bytes": before - after}


def get_db_file_size() -> int:
    return os.path.getsize(DB_PATH) if os.path.exists(DB_PATH) else 0
