"""
db.py
-----
Database layer for the Library Management System.

Quality Goal Q17 (Reduce Memory Usage) note:
This module keeps ONLY schema + connection concerns here. It deliberately
does NOT load full tables into Python lists anywhere -- callers that need
bulk data should go through loader.py, which streams rows instead of
materialising them all in memory at once.
"""

import sqlite3
import os
from datetime import datetime

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "library.db")

os.makedirs(DB_DIR, exist_ok=True)


def get_connection():
    """
    Return a new sqlite3 connection.

    A fresh short-lived connection per operation (instead of one giant
    connection held open for the app's lifetime with a huge in-memory
    statement cache) keeps SQLite's own internal page-cache footprint
    small and predictable -- this is a small but deliberate contribution
    to the memory-reduction goal.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all tables if they do not already exist."""
    conn = get_connection()
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            isbn TEXT UNIQUE,
            category TEXT,
            total_copies INTEGER NOT NULL DEFAULT 1,
            available_copies INTEGER NOT NULL DEFAULT 1,
            description_compressed BLOB,
            description_raw_size INTEGER DEFAULT 0,
            cover_compressed BLOB,
            cover_raw_size INTEGER DEFAULT 0,
            added_date TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            phone TEXT,
            joined_date TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
            member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            return_date TEXT,
            status TEXT NOT NULL DEFAULT 'issued'
        );

        -- Cold-storage table used by the DB Purge Tool. Old, closed-out
        -- transactions are moved here (or exported+deleted) instead of
        -- being kept forever in the hot `transactions` table, which keeps
        -- the working-set that normal queries touch small.
        CREATE TABLE IF NOT EXISTS archived_transactions (
            id INTEGER PRIMARY KEY,
            book_id INTEGER,
            member_id INTEGER,
            issue_date TEXT,
            due_date TEXT,
            return_date TEXT,
            status TEXT,
            archived_on TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_books_category ON books(category);
        CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
        CREATE INDEX IF NOT EXISTS idx_txn_status ON transactions(status);
        """
    )
    conn.commit()
    conn.close()


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str():
    return datetime.now().strftime("%Y-%m-%d")
