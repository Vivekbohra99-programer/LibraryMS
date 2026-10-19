"""Tests for Q17: Reduce Memory Usage features."""
import time
from datetime import datetime, timedelta, timezone
from app.services.compression import compress_text, decompress_text, compress_bytes, decompress_bytes, compression_stats
from app.services.cache import LRUCache, search_cache
from app.services.purge import (archive_old_transactions, purge_old_logs,
                                vacuum_database, integrity_check,
                                create_backup, restore_backup, list_backups)
from app.services.memory import measure_eager_vs_lazy, full_performance_report
from app.models.book import Book
from app.models.transaction import Transaction
from app.models.activity_log import ActivityLog
from app.models.member import Member


# ========================================================
# Feature 1: Asset Compression
# ========================================================

def test_text_compression_lossless():
    sample_text = "This is a detailed book summary used to test compression. " * 30
    compressed = compress_text(sample_text)
    decompressed = decompress_text(compressed)
    assert decompressed == sample_text
    assert len(compressed) < len(sample_text.encode('utf-8'))


def test_bytes_compression_lossless():
    sample_bytes = b"binary_cover_data_sample_content_for_compression_" * 50
    compressed = compress_bytes(sample_bytes)
    decompressed = decompress_bytes(compressed)
    assert decompressed == sample_bytes
    assert len(compressed) < len(sample_bytes)


def test_compression_stats_calculation():
    stats = compression_stats(1000, 300)
    assert stats['raw_bytes'] == 1000
    assert stats['compressed_bytes'] == 300
    assert stats['saved_bytes'] == 700
    assert stats['saved_pct'] == 70.0


# ========================================================
# Feature 2: Lazy Decompression & On-Demand Loading
# ========================================================

def test_lazy_decompression_on_book_model(app):
    with app.app_context():
        book = Book.query.first()
        # Ensure internal caches start empty
        book._description_cache = None
        book._cover_cache = None

        # Verify reading property decompresses and caches
        assert book.description == "A foundational book on software architecture and patterns."
        assert book.cover_bytes == b'FAKE_COVER_JPEG'
        assert book._description_cache is not None
        assert book._cover_cache is not None


def test_measure_eager_vs_lazy_benchmark(app):
    with app.app_context():
        bench = measure_eager_vs_lazy()
        assert 'eager_peak_bytes' in bench
        assert 'lazy_peak_bytes' in bench
        assert 'reduction_pct' in bench
        assert bench['eager_peak_bytes'] >= 0
        assert bench['lazy_peak_bytes'] >= 0


# ========================================================
# Feature 3: DB Purge Tools & VACUUM
# ========================================================

def test_archive_old_transactions(app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        # Create an old returned transaction (400 days old)
        old_time = datetime.now(timezone.utc) - timedelta(days=400)
        old_txn = Transaction(
            book_id=book.id,
            member_id=member.id,
            issue_date=old_time - timedelta(days=14),
            due_date=old_time,
            return_date=old_time,
            status='returned'
        )
        app.extensions['sqlalchemy'].session.add(old_txn)
        app.extensions['sqlalchemy'].session.commit()
        old_id = old_txn.id

        # Purge transactions older than 365 days
        purged = archive_old_transactions(older_than_days=365)
        assert purged >= 1
        assert Transaction.query.get(old_id) is None


def test_purge_old_activity_logs(app):
    with app.app_context():
        old_time = datetime.now(timezone.utc) - timedelta(days=400)
        old_log = ActivityLog(
            action='old_action',
            details='very old audit log',
            created_at=old_time
        )
        app.extensions['sqlalchemy'].session.add(old_log)
        app.extensions['sqlalchemy'].session.commit()

        purged = purge_old_logs(older_than_days=365)
        assert purged >= 1


def test_vacuum_and_integrity(app):
    with app.app_context():
        vac = vacuum_database()
        assert 'before_bytes' in vac
        assert 'after_bytes' in vac
        assert 'reclaimed_bytes' in vac

        integrity = integrity_check()
        assert integrity == 'ok'


def test_backup_and_restore(app):
    with app.app_context():
        backup_folder = app.config['BACKUP_FOLDER']
        backup_name = create_backup(backup_folder)
        assert backup_name is not None
        assert backup_name.endswith('.db')

        backups = list_backups(backup_folder)
        assert any(b['name'] == backup_name for b in backups)

        # Restore
        safety = restore_backup(backup_folder, backup_name)
        assert safety is not None


# ========================================================
# Feature 4: Query Caching
# ========================================================

def test_lru_cache_bounded_eviction():
    cache = LRUCache(maxsize=3, ttl_seconds=60)
    cache.set('a', 1)
    cache.set('b', 2)
    cache.set('c', 3)
    assert cache.get('a') == 1
    assert cache.get('b') == 2
    assert cache.get('c') == 3

    # Adding 4th element should evict the oldest unaccessed ('a' was accessed before 'b' and 'c')
    cache.set('d', 4)
    stats = cache.stats()
    assert stats['entries'] == 3
    assert stats['evictions'] == 1


def test_lru_cache_ttl_expiration():
    cache = LRUCache(maxsize=10, ttl_seconds=1)
    cache.set('key', 'value')
    assert cache.get('key') == 'value'
    time.sleep(1.1)
    assert cache.get('key') is None


def test_lru_cache_invalidation():
    cache = LRUCache(maxsize=10, ttl_seconds=60)
    cache.set('search:1', [1, 2, 3])
    cache.set('search:2', [4, 5])
    assert cache.get('search:1') == [1, 2, 3]

    cache.invalidate('search:1')
    assert cache.get('search:1') is None
    assert cache.get('search:2') == [4, 5]

    cache.invalidate_all()
    assert cache.get('search:2') is None


def test_performance_report_generation(app):
    with app.app_context():
        report = full_performance_report()
        assert 'process' in report
        assert 'python_alloc' in report
        assert 'compression' in report
        assert 'cache' in report
        assert 'db_size_kb' in report
