"""Every setting on the Settings page has to change something. One test per effect, plus the purge rules
that depend on the retention settings."""
import csv
import glob
import io
import os
from datetime import datetime, timedelta, timezone

from PIL import Image

from app.extensions import db
from app.models.book import Book
from app.models.fine import Fine
from app.models.member import Member
from app.models.setting import Setting
from app.models.transaction import Transaction
from app.services import purge
from app.services.cache import search_cache
from app.services.compression import decompress_bytes, process_cover_image


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _set(app, **values):
    with app.app_context():
        for key, value in values.items():
            Setting.set(key, str(value))


def _returned_loan(app, days_ago=800, fine=None, paid=False):
    """A loan returned `days_ago` days ago, optionally with a fine of `fine` rupees."""
    with app.app_context():
        member, book = Member.query.first(), Book.query.first()
        when = _now() - timedelta(days=days_ago)
        txn = Transaction(book_id=book.id, member_id=member.id, issue_date=when - timedelta(days=14),
                          due_date=when, return_date=when, status='returned')
        db.session.add(txn)
        db.session.flush()
        if fine is not None:
            db.session.add(Fine(transaction_id=txn.id, member_id=member.id, amount=fine, paid=paid))
        db.session.commit()
        return txn.id


def _picture(width, height, noise=False, fmt='PNG'):
    img = Image.frombytes('RGB', (width, height), os.urandom(width * height * 3)) if noise \
        else Image.new('RGB', (width, height), (30, 90, 160))
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    buf.seek(0)
    return buf


def _book_form(app, quantity=1):
    with app.app_context():
        b = Book.query.first()
        return b.id, {'title': b.title, 'isbn': b.isbn, 'author_id': b.author_id, 'category_id': b.category_id,
                      'publisher': 'P', 'edition': '1', 'publication_year': 2000, 'description': 'd',
                      'quantity': quantity}


# ---------- circulation ----------

def test_loan_duration_setting_sets_the_due_date(admin_client, app):
    _set(app, loan_duration=10)
    with app.app_context():
        book_id, member_id = Book.query.first().id, Member.query.first().id
    admin_client.post('/transactions/issue', data={'book_id': book_id, 'member_id': member_id})
    with app.app_context():
        t = Transaction.query.first()
        assert (t.due_date - t.issue_date.replace(tzinfo=None)).days == 10


def test_fine_rate_setting_prices_an_overdue_return(admin_client, app):
    _set(app, fine_rate=3.5)
    with app.app_context():
        member, book = Member.query.first(), Book.query.first()
        t = Transaction(book_id=book.id, member_id=member.id, issue_date=_now() - timedelta(days=30),
                        due_date=_now() - timedelta(days=4, hours=1), status='issued')
        db.session.add(t)
        db.session.commit()
        search_cache.invalidate_all()
        tid = t.id
    admin_client.post(f'/transactions/{tid}/return', data={})
    with app.app_context():
        assert Fine.query.one().amount == 14.0                       # 4 whole days x 3.5


def test_max_renewals_setting_limits_renewals(admin_client, app):
    _set(app, max_renewals=1)
    with app.app_context():
        member, book = Member.query.first(), Book.query.first()
        t = Transaction(book_id=book.id, member_id=member.id, issue_date=_now(), due_date=_now() + timedelta(days=5),
                        status='issued')
        db.session.add(t)
        db.session.commit()
        tid = t.id
    admin_client.post(f'/transactions/{tid}/renew')
    r = admin_client.post(f'/transactions/{tid}/renew', follow_redirects=True)
    assert b'Maximum renewals (1) reached' in r.data
    with app.app_context():
        assert db.session.get(Transaction, tid).renewal_count == 1


def test_member_loan_limit_setting_is_the_default_for_new_members(admin_client, app):
    _set(app, member_loan_limit=9)
    assert 'value="9"' in admin_client.get('/members/add').get_data(as_text=True)
    admin_client.post('/members/add', data={'name': 'New Reader', 'email': 'new@reader.test'})
    with app.app_context():
        assert Member.query.filter_by(email='new@reader.test').one().loan_limit == 9


def test_member_loan_limit_setting_applies_to_self_registration(client, app):
    _set(app, member_loan_limit=7)
    client.post('/register', data={'username': 'selfreg', 'email': 'self@reg.test', 'name': 'Self Reg',
                                   'password': 'secret1', 'confirm_password': 'secret1', 'phone': ''})
    with app.app_context():
        assert Member.query.filter_by(email='self@reg.test').one().loan_limit == 7


# ---------- memory and performance ----------

def test_cache_settings_reconfigure_the_live_cache(admin_client, app):
    try:
        admin_client.post('/admin/settings', data={'cache_ttl': '77', 'cache_max_size': '33'})
        stats = search_cache.stats()
        assert stats['ttl'] == 77 and stats['max_entries'] == 33
    finally:
        search_cache.reconfigure(maxsize=64, ttl=120)


def test_max_image_dimension_setting_shrinks_uploaded_covers(admin_client, app):
    _set(app, max_image_dimension=200)
    book_id, form = _book_form(app)
    form['cover'] = (_picture(900, 600), 'cover.png', 'image/png')
    admin_client.post(f'/books/{book_id}/edit', data=form, content_type='multipart/form-data')
    with app.app_context():
        stored = Image.open(io.BytesIO(decompress_bytes(db.session.get(Book, book_id).cover_compressed)))
        assert max(stored.size) == 200


def test_compression_quality_changes_the_stored_size():
    class Upload:                     # the bits of a werkzeug FileStorage that process_cover_image uses
        content_type = 'image/png'

        def __init__(self, buf):
            self._buf = buf

        def read(self):
            return self._buf.getvalue()

    noisy = _picture(400, 400, noise=True)
    small, _ = process_cover_image(Upload(noisy), 800, 10)
    big, _ = process_cover_image(Upload(noisy), 800, 95)
    assert len(small) < len(big) / 2


def test_upload_limit_setting_refuses_a_bigger_image(admin_client, app):
    _set(app, max_upload_size_mb=1)
    book_id, form = _book_form(app)
    big = _picture(900, 900, noise=True)                             # ~2.4 MB as PNG
    assert len(big.getvalue()) > 1024 * 1024
    big.seek(0)
    form['cover'] = (big, 'big.png', 'image/png')
    r = admin_client.post(f'/books/{book_id}/edit', data=form, content_type='multipart/form-data',
                          follow_redirects=True)
    assert b'The limit is 1 MB' in r.data


def test_page_size_setting_applies_to_every_list(admin_client, app):
    with app.app_context():
        for i in range(7):
            db.session.add(Member(name=f'Pager {i:02d}', email=f'pager{i}@x.test', phone='1', status='active'))
        db.session.commit()
    _set(app, page_size=5)
    page1 = admin_client.get('/members?page=1').get_data(as_text=True)
    page2 = admin_client.get('/members?page=2').get_data(as_text=True)
    names = [f'Pager {i:02d}' for i in range(7)]
    assert sum(n in page1 for n in names) == 5 and sum(n in page2 for n in names) == 2


def test_stored_values_outside_the_allowed_range_cannot_crash_a_page(admin_client, app):
    _set(app, page_size=0, fine_rate=-3, cache_max_size=0)             # as an older version or a hand edit could leave them
    with app.app_context():
        assert Setting.get_int('page_size') == 5
        assert Setting.get_float('fine_rate') == 0
        assert Setting.get_int('cache_max_size') == 1
    for url in ('/books', '/members', '/transactions', '/fines', '/authors', '/categories', '/catalogue'):
        assert admin_client.get(url).status_code == 200, url


# ---------- retention and purge ----------

def test_maintenance_form_starts_from_the_retention_settings(admin_client, app):
    _set(app, transaction_retention_days=400, log_retention_days=120)
    html = admin_client.get('/admin/maintenance').get_data(as_text=True)
    assert 'name="days" value="400"' in html and 'name="days" value="120"' in html
    assert 'name="days" value="400" min="30"' in html


def test_purge_leaves_loans_with_unpaid_fines_and_removes_the_rest(app):
    plain = _returned_loan(app)
    paid = _returned_loan(app, fine=6.0, paid=True)
    unpaid = _returned_loan(app, fine=8.0, paid=False)
    recent = _returned_loan(app, days_ago=10)
    with app.app_context():
        assert purge.kept_for_unpaid_fines(365) == 1
        assert purge.archive_old_transactions(older_than_days=365) == 2
        assert db.session.get(Transaction, plain) is None and db.session.get(Transaction, paid) is None
        assert db.session.get(Transaction, unpaid) is not None and db.session.get(Transaction, recent) is not None
        assert [f.amount for f in Fine.query.all()] == [8.0]          # the unpaid fine is still on record


def test_purge_export_goes_to_a_new_timestamped_file_with_fine_columns(admin_client, app):
    _returned_loan(app, fine=5.0, paid=True)
    admin_client.post('/admin/maintenance/purge-transactions', data={'days': '365', 'export_csv': 'on'})
    folder = os.path.join(app.config['BACKUP_FOLDER'], 'archives')
    files = glob.glob(os.path.join(folder, 'purged_transactions_*.csv'))
    assert len(files) == 1
    rows = list(csv.reader(open(files[0])))
    assert rows[0][-2:] == ['fine_amount', 'fine_paid'] and rows[1][-2:] == ['5.0', 'yes']


def test_two_purges_never_overwrite_each_others_archive(admin_client, app):
    import time
    folder = os.path.join(app.config['BACKUP_FOLDER'], 'archives')
    for _ in range(2):
        _returned_loan(app)
        admin_client.post('/admin/maintenance/purge-transactions', data={'days': '365', 'export_csv': 'on'})
        time.sleep(1.1)                                                # file names carry the second
    assert len(glob.glob(os.path.join(folder, 'purged_transactions_*.csv'))) == 2


def test_purge_refuses_a_retention_below_the_minimum(admin_client, app):
    old = _returned_loan(app)
    for days in ('0', '-5', '29'):
        r = admin_client.post('/admin/maintenance/purge-transactions', data={'days': days}, follow_redirects=True)
        assert b'Keep at least 30 days' in r.data
        r = admin_client.post('/admin/maintenance/purge-logs', data={'days': days}, follow_redirects=True)
        assert b'Keep at least 30 days' in r.data
    with app.app_context():
        assert db.session.get(Transaction, old) is not None


def test_purge_without_a_days_value_uses_the_setting(admin_client, app):
    _set(app, transaction_retention_days=100)
    young = _returned_loan(app, days_ago=150)
    admin_client.post('/admin/maintenance/purge-transactions', data={})
    with app.app_context():
        assert db.session.get(Transaction, young) is None
