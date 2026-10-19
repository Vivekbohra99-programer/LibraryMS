"""Measured on the seeded database: what a catalogue page and a book export cost with and without the
on-demand (deferred) BLOB columns. Run from the project folder: python measure_q17.py"""
import gc
import sys
import tracemalloc

sys.path.insert(0, '.')
from sqlalchemy.orm import undefer                       # noqa: E402

from app import create_app                               # noqa: E402
from app.extensions import db                            # noqa: E402
from app.models.book import Book                         # noqa: E402

app = create_app()


def peak_of(fn):
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    db.session.remove()
    gc.collect()
    tracemalloc.reset_peak()
    base = tracemalloc.get_traced_memory()[0]
    keep = fn()
    peak = tracemalloc.get_traced_memory()[1] - base
    n = len(keep)
    del keep
    return peak, n


with app.app_context():
    total = Book.query.count()
    blob_bytes = db.session.execute(db.text('select sum(length(cover_compressed)+length(description_compressed)) from books')).scalar()
    print(f'books: {total}, compressed covers+descriptions stored: {blob_bytes/1024:.0f} KB')
    page = lambda opts: (lambda: Book.query.options(*opts).order_by(Book.title).limit(25).all())
    every = lambda opts: (lambda: Book.query.options(*opts).all())
    both = (undefer(Book.cover_compressed), undefer(Book.description_compressed))
    for label, maker in (('catalogue page (25 books)', page), ('every book (export / issue form)', every)):
        before, n = peak_of(maker(both))
        after, _ = peak_of(maker(()))
        print(f'{label:36s} {n:3d} rows   BLOBs loaded {before/1024:8.0f} KB   deferred {after/1024:7.0f} KB   '
              f'{(1 - after / before) * 100:5.1f}% less')
