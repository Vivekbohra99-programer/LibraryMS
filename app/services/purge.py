"""
Q17 Feature 3: DB Purge Tools
Preserved from original purge.py, adapted for SQLAlchemy.
"""
import csv
import os
import re
import shutil
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from app.extensions import db
from app.services.cache import search_cache


def _old_returned_loans(older_than_days: int):
    """Query: loans returned before the cutoff. Used by both the purge and the 'kept' count."""
    from app.models.transaction import Transaction
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    return Transaction.query.filter(
        Transaction.status == 'returned',
        Transaction.return_date.isnot(None),
        Transaction.return_date < cutoff)


def kept_for_unpaid_fines(older_than_days: int = 365) -> int:
    """How many old returned loans a purge will leave alone because their fine has not been paid."""
    from app.models.fine import Fine
    from app.models.transaction import Transaction
    return (_old_returned_loans(older_than_days)
            .join(Fine, Fine.transaction_id == Transaction.id)
            .filter(Fine.paid.is_(False)).count())


def archive_old_transactions(older_than_days: int = 365, export_csv_path: str = None):
    """Delete old returned loans (and their paid fines) to reduce the working set. Returns how many went.

    A loan whose fine is still unpaid is never deleted: that row is the record of money owed.
    With export_csv_path, the rows are written there first (including fine amount and status)."""
    from app.models.fine import Fine
    from app.models.transaction import Transaction
    txns = (_old_returned_loans(older_than_days)
            .outerjoin(Fine, Fine.transaction_id == Transaction.id)
            .filter(or_(Fine.id.is_(None), Fine.paid.is_(True)))
            .all())
    if not txns:
        return 0

    if export_csv_path:
        os.makedirs(os.path.dirname(os.path.abspath(export_csv_path)), exist_ok=True)
        with open(export_csv_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['id', 'book_id', 'member_id', 'issue_date',
                             'due_date', 'return_date', 'status', 'renewal_count',
                             'fine_amount', 'fine_paid'])
            for t in txns:
                writer.writerow([t.id, t.book_id, t.member_id,
                                 t.issue_date, t.due_date, t.return_date,
                                 t.status, t.renewal_count,
                                 t.fine.amount if t.fine else '', ('yes' if t.fine.paid else 'no') if t.fine else ''])

    count = len(txns)
    for t in txns:
        # Delete associated fines first
        if t.fine:
            db.session.delete(t.fine)
        db.session.delete(t)
    db.session.commit()
    search_cache.invalidate_all()
    return count


def purge_old_logs(older_than_days: int = 365):
    """Delete activity logs older than the specified number of days."""
    from app.models.activity_log import ActivityLog
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    count = ActivityLog.query.filter(ActivityLog.created_at < cutoff).delete()
    db.session.commit()
    return count


def vacuum_database():
    """Run SQLite VACUUM to reclaim unused pages. Returns before/after sizes."""
    db_path = _get_db_path()
    before = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    db.session.execute(db.text('VACUUM'))
    db.session.commit()
    after = os.path.getsize(db_path) if os.path.exists(db_path) else 0
    return {'before_bytes': before, 'after_bytes': after,
            'reclaimed_bytes': before - after}


def analyze_database():
    """Run SQLite ANALYZE to update query planner statistics."""
    db.session.execute(db.text('ANALYZE'))
    db.session.commit()


def integrity_check():
    """Run SQLite integrity_check. Returns the result string."""
    result = db.session.execute(db.text('PRAGMA integrity_check')).fetchone()
    return result[0] if result else 'unknown'


def get_db_size():
    db_path = _get_db_path()
    return os.path.getsize(db_path) if os.path.exists(db_path) else 0


def _get_db_path():
    from flask import current_app
    uri = current_app.config['SQLALCHEMY_DATABASE_URI']
    return uri.replace('sqlite:///', '')


def create_backup(backup_folder: str):
    """Create a timestamped copy of the SQLite database."""
    os.makedirs(backup_folder, exist_ok=True)
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        return None
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_name = f'library_backup_{timestamp}.db'
    n = 1
    while os.path.exists(os.path.join(backup_folder, backup_name)):
        # never overwrite an existing backup: two copies in the same second get _1, _2 ...
        backup_name = f'library_backup_{timestamp}_{n}.db'
        n += 1
    backup_path = os.path.join(backup_folder, backup_name)
    # SQLite's online backup copies a consistent snapshot even while another request is writing.
    # Copying the file with shutil could catch it half-way through a transaction.
    source = sqlite3.connect(db_path)
    try:
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    return backup_name


_BACKUP_NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.\-]*\.db$')


def _backup_path(backup_folder: str, backup_name: str):
    """Absolute path of an existing backup, or None. Names come from the URL, so only plain
    file names ending in .db are accepted: no separators, no '..', no directories."""
    if not isinstance(backup_name, str) or not _BACKUP_NAME.match(backup_name) or '..' in backup_name:
        return None
    path = os.path.join(backup_folder, backup_name)
    return path if os.path.isfile(path) else None


def backup_is_healthy(path: str) -> bool:
    """True only if `path` opens as a SQLite database and passes PRAGMA integrity_check."""
    try:
        con = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            return con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        finally:
            con.close()
    except sqlite3.Error:
        return False


def restore_backup(backup_folder: str, backup_name: str):
    """Restore the database from a backup file.

    Raises FileNotFoundError for an unknown or invalid name, and ValueError if the file is not
    a healthy SQLite database. In both cases the live database is left untouched."""
    backup_path = _backup_path(backup_folder, backup_name)
    if not backup_path:
        raise FileNotFoundError(f'Backup not found: {backup_name}')
    if not backup_is_healthy(backup_path):
        raise ValueError(f'Backup is damaged or not a SQLite database: {backup_name}')
    db_path = _get_db_path()
    # Create safety backup first
    safety = create_backup(backup_folder)
    # Close all connections
    db.session.remove()
    db.engine.dispose()
    shutil.copy2(backup_path, db_path)
    search_cache.invalidate_all()
    return safety


def list_backups(backup_folder: str):
    """Return list of backup files with metadata."""
    os.makedirs(backup_folder, exist_ok=True)
    backups = []
    for f in sorted(os.listdir(backup_folder), reverse=True):
        if f.endswith('.db'):
            path = os.path.join(backup_folder, f)
            backups.append({
                'name': f,
                'size': os.path.getsize(path),
                'created': datetime.fromtimestamp(os.path.getmtime(path)),
            })
    return backups


def delete_backup(backup_folder: str, backup_name: str):
    path = _backup_path(backup_folder, backup_name)
    if path:
        os.remove(path)
        return True
    return False


def get_upload_folder_size(upload_folder: str):
    total = 0
    if os.path.exists(upload_folder):
        for f in os.listdir(upload_folder):
            fp = os.path.join(upload_folder, f)
            if os.path.isfile(fp):
                total += os.path.getsize(fp)
    return total
