"""
main.py
-------
Library Management System - [Q17: Reduce Memory Usage]

CLI entry point. Wires together:
  - db.py          : schema / connections
  - compression.py : Feature 1 - Asset Compression
  - loader.py       : Feature 2 - On-Demand Data Loading (+ query caching)
  - cache.py        : Feature 4 - Query Caching
  - purge.py        : Feature 3 - DB Purge Tools
  - memory_report.py: visualises the effect of all four features

Run with:  python main.py
"""

from datetime import datetime, timedelta

from db import init_db, get_connection, now_str, today_str
import loader
import compression
import cache as cache_module
import purge
import memory_report

LOAN_PERIOD_DAYS = 14


def pause():
    input("\nPress Enter to continue...")


# ---------------------------------------------------------------- BOOKS ---

def add_book():
    print("\n-- Add Book --")
    title = input("Title: ").strip()
    author = input("Author: ").strip()
    isbn = input("ISBN (optional): ").strip() or None
    category = input("Category (optional): ").strip() or None
    try:
        copies = int(input("Number of copies [1]: ").strip() or "1")
    except ValueError:
        copies = 1
    description = input("Description/summary (optional, can be long): ").strip()

    # FEATURE 1: Asset Compression -- compress before it ever reaches the DB.
    desc_compressed = compression.compress_text(description)

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO books (title, author, isbn, category, total_copies,
                            available_copies, description_compressed,
                            description_raw_size, added_date)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (title, author, isbn, category, copies, copies,
         desc_compressed, len(description.encode("utf-8")), today_str()),
    )
    conn.commit()
    conn.close()

    cache_module.search_cache.invalidate_all()  # catalogue changed -> stale cache
    print(f"'{title}' added ({copies} cop{'y' if copies == 1 else 'ies'}).")
    pause()


def browse_books():
    page = 1
    while True:
        total = loader.count_books()
        books = loader.get_books_page(page_number=page, page_size=loader.PAGE_SIZE)
        print(f"\n-- Books (page {page}, {total} total) --")
        if not books:
            print("(No books on this page.)")
        for b in books:
            print(f"  #{b.id:<4} {b.title:<30} by {b.author:<20} "
                  f"[{b.available_copies}/{b.total_copies} available]")
        print("\n[n] next page  [p] prev page  [d] details  [b] back")
        choice = input("> ").strip().lower()
        if choice == "n":
            if page * loader.PAGE_SIZE < total:
                page += 1
        elif choice == "p" and page > 1:
            page -= 1
        elif choice == "d":
            try:
                bid = int(input("Book ID: ").strip())
            except ValueError:
                continue
            show_book_detail(bid)
        elif choice == "b":
            return


def show_book_detail(book_id):
    book = loader.get_book_by_id(book_id)
    if not book:
        print("Not found.")
        return
    # .description is decompressed lazily, right here, only because we
    # asked for it -- Feature 2's "on demand" half at the object level.
    print(f"\n#{book.id} {book.title} by {book.author}")
    print(f"Category : {book.category or '-'}")
    print(f"ISBN     : {book.isbn or '-'}")
    print(f"Copies   : {book.available_copies}/{book.total_copies}")
    print(f"Added    : {book.added_date}")
    print(f"Summary  : {book.description or '(none)'}")


def search_books():
    print("\n-- Search Books --")
    print("[1] By title  [2] By author  [3] By category")
    choice = input("> ").strip()
    field = {"1": "title", "2": "author", "3": "category"}.get(choice)
    if not field:
        return
    term = input("Search term: ").strip()
    results = loader.search_books(field, term)
    print(f"\n{len(results)} result(s):")
    for b in results:
        print(f"  #{b.id} {b.title} by {b.author}")
    pause()


# -------------------------------------------------------------- MEMBERS ---

def add_member():
    print("\n-- Add Member --")
    name = input("Name: ").strip()
    email = input("Email: ").strip()
    phone = input("Phone (optional): ").strip() or None

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO members (name, email, phone, joined_date, active) VALUES (?, ?, ?, ?, 1)",
        (name, email, phone, today_str()),
    )
    conn.commit()
    conn.close()
    print(f"Member '{name}' added.")
    pause()


# ---------------------------------------------------------- ISSUE/RETURN --

def issue_book():
    print("\n-- Issue Book --")
    try:
        book_id = int(input("Book ID: ").strip())
        member_id = int(input("Member ID: ").strip())
    except ValueError:
        print("Invalid ID.")
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT available_copies FROM books WHERE id = ?", (book_id,))
    row = cur.fetchone()
    if not row or row["available_copies"] < 1:
        print("Book unavailable.")
        conn.close()
        return

    issue_date = today_str()
    due_date = (datetime.now() + timedelta(days=LOAN_PERIOD_DAYS)).strftime("%Y-%m-%d")
    cur.execute(
        "INSERT INTO transactions (book_id, member_id, issue_date, due_date, status) "
        "VALUES (?, ?, ?, ?, 'issued')",
        (book_id, member_id, issue_date, due_date),
    )
    cur.execute(
        "UPDATE books SET available_copies = available_copies - 1 WHERE id = ?",
        (book_id,),
    )
    conn.commit()
    conn.close()
    cache_module.search_cache.invalidate_all()
    print(f"Issued. Due back {due_date}.")
    pause()


def return_book():
    print("\n-- Return Book --")
    try:
        txn_id = int(input("Transaction ID: ").strip())
    except ValueError:
        print("Invalid ID.")
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE id = ? AND status = 'issued'", (txn_id,))
    txn = cur.fetchone()
    if not txn:
        print("No matching open transaction.")
        conn.close()
        return

    cur.execute(
        "UPDATE transactions SET status = 'returned', return_date = ? WHERE id = ?",
        (today_str(), txn_id),
    )
    cur.execute(
        "UPDATE books SET available_copies = available_copies + 1 WHERE id = ?",
        (txn["book_id"],),
    )
    conn.commit()
    conn.close()
    cache_module.search_cache.invalidate_all()
    print("Returned. Thank you!")
    pause()


# ------------------------------------------------------------ ADMIN TOOLS -

def admin_menu():
    while True:
        print("\n-- Admin Tools --")
        print("[1] Purge old returned transactions (archive)")
        print("[2] Purge old returned transactions (hard delete + CSV export)")
        print("[3] Vacuum database (reclaim disk space)")
        print("[4] Memory usage report (all Q17 features)")
        print("[5] Cache stats")
        print("[b] Back")
        choice = input("> ").strip().lower()

        if choice == "1":
            days = input("Archive transactions returned more than how many days ago? [365]: ").strip()
            days = int(days) if days else 365
            n = purge.archive_old_transactions(older_than_days=days, hard_delete=False)
            print(f"Archived {n} transaction(s).")
            pause()
        elif choice == "2":
            days = input("Delete transactions returned more than how many days ago? [365]: ").strip()
            days = int(days) if days else 365
            n = purge.archive_old_transactions(
                older_than_days=days, hard_delete=True, export_csv="purged_transactions.csv"
            )
            print(f"Hard-deleted {n} transaction(s)."
                  + (" Exported to purged_transactions.csv." if n else ""))
            pause()
        elif choice == "3":
            result = purge.vacuum_database()
            print(f"DB size before: {result['before_bytes']} bytes, "
                  f"after: {result['after_bytes']} bytes, "
                  f"reclaimed: {result['reclaimed_bytes']} bytes.")
            pause()
        elif choice == "4":
            memory_report.print_full_report()
            pause()
        elif choice == "5":
            s = cache_module.search_cache.stats()
            print(f"Entries: {s['entries']}/{s['max_entries']}  "
                  f"Hits: {s['hits']}  Misses: {s['misses']}  "
                  f"Hit rate: {s['hit_rate_pct']}%")
            pause()
        elif choice == "b":
            return


# ------------------------------------------------------------------ MENU --

def main_menu():
    init_db()
    while True:
        print("\n===== Library Management System - [Q17: Reduce Memory Usage] =====")
        print("[1] Add Book")
        print("[2] Browse Books (paginated)")
        print("[3] Search Books")
        print("[4] Add Member")
        print("[5] Issue Book")
        print("[6] Return Book")
        print("[7] Admin Tools")
        print("[0] Exit")
        choice = input("> ").strip()

        if choice == "1":
            add_book()
        elif choice == "2":
            browse_books()
        elif choice == "3":
            search_books()
        elif choice == "4":
            add_member()
        elif choice == "5":
            issue_book()
        elif choice == "6":
            return_book()
        elif choice == "7":
            admin_menu()
        elif choice == "0":
            print("Goodbye!")
            break
        else:
            print("Invalid choice.")


if __name__ == "__main__":
    main_menu()
