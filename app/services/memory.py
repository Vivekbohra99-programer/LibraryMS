"""
Q17 Memory Monitoring – real measurements via tracemalloc and psutil.
Preserved from original memory_report.py, adapted for web display.
"""
import tracemalloc
import os
import psutil
from app.extensions import db
from app.services.cache import search_cache


def get_process_memory():
    """Return current process memory info from psutil."""
    proc = psutil.Process(os.getpid())
    mem = proc.memory_info()
    return {
        'rss_bytes': mem.rss,
        'vms_bytes': mem.vms,
        'rss_mb': round(mem.rss / (1024 * 1024), 2),
        'vms_mb': round(mem.vms / (1024 * 1024), 2),
    }


def get_python_allocation():
    """Return current/peak Python memory allocation from tracemalloc."""
    if not tracemalloc.is_tracing():
        tracemalloc.start()
    current, peak = tracemalloc.get_traced_memory()
    return {
        'current_bytes': current,
        'peak_bytes': peak,
        'current_kb': round(current / 1024, 1),
        'peak_kb': round(peak / 1024, 1),
    }


def measure_eager_vs_lazy():
    """
    Q17 benchmark: compare eager-load-all vs on-demand paginated loading.
    Uses tracemalloc for real measurements.
    """
    from app.models.book import Book

    # Stop existing tracing if any
    if tracemalloc.is_tracing():
        tracemalloc.stop()

    # --- Eager: load all books and decompress everything ---
    tracemalloc.start()
    books = Book.query.all()
    eager_list = []
    for b in books:
        _ = b.description
        _ = b.cover_bytes
        eager_list.append(b)
    _, eager_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    del eager_list
    del books

    # --- On-demand: paginated, no decompression ---
    tracemalloc.start()
    peak_seen = 0
    page_size = 20
    offset = 0
    while True:
        page = Book.query.order_by(Book.id).offset(offset).limit(page_size).all()
        if not page:
            break
        for b in page:
            _ = b.title  # browse-only: no decompression
        _, peak_now = tracemalloc.get_traced_memory()
        peak_seen = max(peak_seen, peak_now)
        offset += page_size
        # Expire loaded objects from session to simulate real pagination
        for b in page:
            db.session.expire(b)
    lazy_peak = peak_seen
    tracemalloc.stop()

    # Restart tracing for ongoing monitoring
    tracemalloc.start()

    return {
        'eager_peak_bytes': eager_peak,
        'lazy_peak_bytes': lazy_peak,
        'eager_peak_kb': round(eager_peak / 1024, 1),
        'lazy_peak_kb': round(lazy_peak / 1024, 1),
        'reduction_pct': round((1 - lazy_peak / eager_peak) * 100, 1) if eager_peak else 0.0,
    }


def compression_summary():
    """Aggregate compression stats across all books."""
    from app.services.compression import compression_stats
    row = db.session.execute(db.text(
        "SELECT COALESCE(SUM(description_raw_size),0) AS r, "
        "COALESCE(SUM(LENGTH(description_compressed)),0) AS c, "
        "COALESCE(SUM(cover_raw_size),0) AS cr, "
        "COALESCE(SUM(LENGTH(cover_compressed)),0) AS cc FROM books"
    )).fetchone()
    raw_total = row[0] + row[2]
    compressed_total = row[1] + row[3]
    return compression_stats(raw_total, compressed_total)


def get_db_size():
    from flask import current_app
    uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    path = uri.replace('sqlite:///', '')
    return os.path.getsize(path) if os.path.exists(path) else 0


def get_upload_size():
    from flask import current_app
    folder = current_app.config.get('UPLOAD_FOLDER', '')
    total = 0
    if os.path.isdir(folder):
        for f in os.listdir(folder):
            fp = os.path.join(folder, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total


def full_performance_report():
    """Collect all Q17 metrics into one dict for the performance dashboard."""
    proc = get_process_memory()
    pyalloc = get_python_allocation()
    comp = compression_summary()
    cache = search_cache.stats()
    db_size = get_db_size()
    upload_size = get_upload_size()

    return {
        'process': proc,
        'python_alloc': pyalloc,
        'compression': comp,
        'cache': cache,
        'db_size_bytes': db_size,
        'db_size_kb': round(db_size / 1024, 1),
        'upload_size_bytes': upload_size,
        'upload_size_kb': round(upload_size / 1024, 1),
    }
