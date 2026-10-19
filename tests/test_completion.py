"""Tests added to close the coverage gaps: overdue accrual, dashboard analytics, search/sort/pagination,
notifications, activity logs, settings validation, backup safety and the login redirect."""
import io
import os
from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models.activity_log import ActivityLog
from app.models.author import Author
from app.models.book import Book
from app.models.category import Category
from app.models.member import Member
from app.models.notification import Notification
from app.models.setting import Setting
from app.models.transaction import Transaction
from app.models.user import User
from app.services import analytics
from app.services.activity import log_activity
from app.services.cache import search_cache
from app.services.compression import compress_bytes, compress_text
from app.services.notifications import notify


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _loan(app, days_late=0, status='issued', issued_days_ago=20):
    """Create one loan for the test member; days_late > 0 puts it past its due date."""
    with app.app_context():
        m, b = Member.query.first(), Book.query.first()
        due = _now() - timedelta(days=days_late) if days_late else _now() + timedelta(days=7)
        t = Transaction(book_id=b.id, member_id=m.id, issue_date=_now() - timedelta(days=issued_days_ago),
                        due_date=due, status=status)
        db.session.add(t)
        db.session.commit()
        search_cache.invalidate_all()       # the app does this on every write; direct inserts must too
        return t.id


def _make_books(app, n):
    with app.app_context():
        a, c = Author.query.first(), Category.query.first()
        for i in range(n):
            d = 'Filler description.'
            db.session.add(Book(title=f'Shelf Book {i:02d}', isbn=f'97800000{i:05d}', author_id=a.id, category_id=c.id,
                                description_compressed=compress_text(d), description_raw_size=len(d),
                                cover_compressed=compress_bytes(b'x'), cover_raw_size=1,
                                quantity=2, available_quantity=2 if i % 2 == 0 else 0))
        db.session.commit()
        search_cache.invalidate_all()


# ---------- overdue tracking and live fines ----------

def test_accrued_fine_is_whole_days_times_rate(app):
    tid = _loan(app, days_late=5)
    ok = _loan(app)
    done = _loan(app, days_late=9, status='returned')
    with app.app_context():
        assert db.session.get(Transaction, tid).accrued_fine(2.0) == 10.0
        assert db.session.get(Transaction, tid).accrued_fine(2.5) == 12.5
        assert db.session.get(Transaction, ok).accrued_fine(2.0) == 0.0        # not late yet
        assert db.session.get(Transaction, done).accrued_fine(2.0) == 0.0      # returned loans do not accrue


def test_overdue_filter_lists_only_late_unreturned_loans(librarian_client, app):
    late = _loan(app, days_late=4)
    _loan(app)                                   # on time
    _loan(app, days_late=6, status='returned')   # late but already returned
    html = librarian_client.get('/transactions?status=overdue').get_data(as_text=True)
    assert f'#{late}' in html
    assert html.count('accrued') >= 1 and '₹8.00 accrued' in html
    assert 'Overdue (4d)' in html
    assert 'Overdue (6d)' not in html


def test_member_dashboard_shows_accruing_fine(member_client, app):
    _loan(app, days_late=3)
    html = member_client.get('/dashboard').get_data(as_text=True)
    assert 'accruing on overdue books' in html and '₹6.00' in html


# ---------- dashboard analytics ----------

def test_loans_per_day_is_zero_filled_and_counts_today(app):
    _loan(app, issued_days_ago=0)
    _loan(app, issued_days_ago=0)
    with app.app_context():
        series = analytics.loans_per_day(14)
        assert len(series) == 14
        assert series[-1]['value'] == 2 and sum(d['value'] for d in series) == 2
        assert all(d['value'] == 0 for d in series[:-1])


def test_overdue_exposure_matches_python_arithmetic(app):
    _loan(app, days_late=5)
    _loan(app, days_late=12)
    with app.app_context():
        got = analytics.overdue_exposure(2.0)
        expected = sum(t.overdue_days for t in Transaction.query.filter_by(status='issued') if t.is_overdue)
        assert got['count'] == 2 and got['days'] == expected == 17 and got['accruing'] == 34.0


def test_category_and_fine_aggregates(app):
    _make_books(app, 3)
    with app.app_context():
        cats, total = analytics.books_by_category()
        assert cats[0]['name'] == 'Software Engineering' and cats[0]['value'] == total == 4
        assert analytics.fine_split() == {'paid': 0.0, 'unpaid': 0.0}


def test_admin_dashboard_renders_charts(admin_client, app):
    _loan(app, days_late=2, issued_days_ago=3)
    html = admin_client.get('/dashboard').get_data(as_text=True)
    assert 'lg-bars' in html and 'Books by category' in html and 'Overdue right now' in html


def test_librarian_dashboard_renders_charts(librarian_client, app):
    _loan(app, days_late=2, issued_days_ago=3)
    html = librarian_client.get('/dashboard').get_data(as_text=True)
    assert 'lg-bars' in html and 'Fines collected vs outstanding' in html


def test_dashboard_empty_state_when_no_recent_loans(admin_client):
    html = admin_client.get('/dashboard').get_data(as_text=True)
    assert 'lg-bars' not in html and 'No loans issued in the last 14 days' in html


def test_pages_declare_viewport_and_theme_toggle(admin_client):
    html = admin_client.get('/dashboard').get_data(as_text=True)
    assert 'name="viewport"' in html and 'data-lg-theme-toggle' in html


# ---------- search, filter, sort, pagination ----------

def test_catalogue_search_sort_and_pagination(client, app):
    _make_books(app, 30)
    with app.app_context():
        per_page = Setting.get_int('page_size', 25)
    p1 = client.get('/catalogue').get_data(as_text=True)
    p2 = client.get('/catalogue?page=2').get_data(as_text=True)
    assert 'Shelf Book 00' in p1 and 'Shelf Book 00' not in p2
    assert p1.count('Shelf Book') + p2.count('Shelf Book') >= 30 and per_page == 25
    hit = client.get('/catalogue?q=Shelf Book 07').get_data(as_text=True)
    assert 'Shelf Book 07' in hit and 'Shelf Book 08' not in hit
    assert 'Patterns of Enterprise' not in hit
    assert hit.index('Shelf Book 07') > 0


def test_catalogue_availability_filter_and_title_order(client, app):
    _make_books(app, 4)                           # 00 and 02 available, 01 and 03 out of stock
    out = client.get('/catalogue?availability=unavailable').get_data(as_text=True)
    assert 'Shelf Book 01' in out and 'Shelf Book 03' in out and 'Shelf Book 00' not in out
    asc = client.get('/catalogue?sort=title').get_data(as_text=True)
    assert asc.index('Patterns of Enterprise') < asc.index('Shelf Book 00') < asc.index('Shelf Book 03')


# ---------- notifications and activity log ----------

def test_notifications_list_mark_read_and_count(member_client, app):
    with app.app_context():
        uid = User.query.filter_by(username='testmember').first().id
        n1 = notify(uid, 'Your book is due tomorrow').id
        notify(uid, 'Second notice')
    assert member_client.get('/api/notification-count').get_json()['count'] == 2
    assert b'Your book is due tomorrow' in member_client.get('/notifications').data
    member_client.post(f'/notifications/{n1}/read')
    assert member_client.get('/api/notification-count').get_json()['count'] == 1
    member_client.post('/notifications/read-all')
    assert member_client.get('/api/notification-count').get_json()['count'] == 0


def test_notifications_are_private_to_their_owner(librarian_client, app):
    with app.app_context():
        uid = User.query.filter_by(username='testmember').first().id
        nid = notify(uid, 'Only for the member').id
    assert b'Only for the member' not in librarian_client.get('/notifications').data
    librarian_client.post(f'/notifications/{nid}/read')
    with app.app_context():
        assert db.session.get(Notification, nid).read is False


def test_activity_log_visible_to_admin(admin_client, app):
    with app.app_context():
        log_activity(1, 'unit_test_action', 'logged by a test')
    assert b'unit_test_action' in admin_client.get('/admin/activity-logs').data


def test_activity_log_forbidden_to_member_and_librarian(member_client):
    assert member_client.get('/admin/activity-logs').status_code == 403


def test_activity_log_forbidden_to_librarian(librarian_client):
    assert librarian_client.get('/admin/activity-logs').status_code == 403


# ---------- settings validation ----------

def test_settings_accept_valid_values_and_log_the_change(admin_client, app):
    admin_client.post('/admin/settings', data={'fine_rate': '3.5', 'loan_duration': '21'})
    with app.app_context():
        assert Setting.get_float('fine_rate') == 3.5 and Setting.get_int('loan_duration') == 21
        assert ActivityLog.query.filter_by(action='settings_change').count() == 1


def test_settings_reject_negative_text_and_nan_and_save_nothing(admin_client, app):
    for bad in ('-5', 'abc', 'nan', 'inf', '99999999'):
        r = admin_client.post('/admin/settings', data={'fine_rate': bad, 'loan_duration': '30'}, follow_redirects=True)
        assert b'fine rate' in r.data
    with app.app_context():
        assert Setting.get_float('fine_rate') == 2.0
        assert Setting.get_int('loan_duration') == 14          # all-or-nothing: the good value was not saved either


# ---------- backup and restore ----------

def test_backup_create_restore_and_delete_round_trip(admin_client, app):
    admin_client.post('/admin/backups/create')
    folder = app.config['BACKUP_FOLDER']
    names = [f for f in os.listdir(folder) if f.endswith('.db') and f.startswith('library_backup_')]
    assert len(names) == 1
    with app.app_context():
        db.session.add(Category(name='Added After Backup', description='x'))
        db.session.commit()
        assert Category.query.filter_by(name='Added After Backup').count() == 1
    r = admin_client.post(f'/admin/backups/restore/{names[0]}', follow_redirects=True)
    assert b'restored' in r.data
    with app.app_context():
        assert Category.query.filter_by(name='Added After Backup').count() == 0
        assert Category.query.filter_by(name='Software Engineering').count() == 1
    assert admin_client.post(f'/admin/backups/delete/{names[0]}', follow_redirects=True).status_code == 200
    assert names[0] not in os.listdir(folder)


def test_restore_refuses_damaged_file_and_keeps_live_data(admin_client, app):
    folder = app.config['BACKUP_FOLDER']
    with open(os.path.join(folder, 'broken.db'), 'wb') as fh:
        fh.write(b'this is not a sqlite database at all')
    r = admin_client.post('/admin/backups/restore/broken.db', follow_redirects=True)
    assert b'damaged' in r.data
    with app.app_context():
        assert Book.query.count() == 1                           # live database untouched


def test_backup_routes_reject_unsafe_names(admin_client, app):
    victim = os.path.join(os.path.dirname(app.config['BACKUP_FOLDER']), 'victim.txt')
    open(victim, 'w').write('keep me')
    for name in ('..', '.', '..%5Cvictim.txt', 'victim.txt', 'x.db%00.txt', '.hidden.db'):
        for action in ('restore', 'delete'):
            r = admin_client.post(f'/admin/backups/{action}/{name}', follow_redirects=True)
            assert r.status_code in (200, 404), (action, name, r.status_code)   # never a 500
    assert os.path.exists(victim)


def test_backup_pages_forbidden_to_member(member_client):
    assert member_client.get('/admin/backups').status_code == 403
    assert member_client.post('/admin/backups/create').status_code == 403


def test_backup_pages_forbidden_to_librarian(librarian_client):
    assert librarian_client.get('/admin/backups').status_code == 403
    assert librarian_client.post('/admin/backups/create').status_code == 403


def test_two_backups_in_the_same_second_never_overwrite(admin_client, app):
    from app.services import purge
    with app.app_context():
        a = purge.create_backup(app.config['BACKUP_FOLDER'])
        b = purge.create_backup(app.config['BACKUP_FOLDER'])
        c = purge.create_backup(app.config['BACKUP_FOLDER'])
    assert len({a, b, c}) == 3


# ---------- security: login redirect, upload robustness ----------

def test_login_next_only_follows_local_paths(client):
    for target, expect_local in (('/books', True), ('//evil.example', False), ('https://evil.example', False),
                                 ('/\\evil.example', False)):
        r = client.post(f'/login?next={target}', data={'username': 'testadmin', 'password': 'pass123'})
        loc = r.headers['Location']
        assert 'evil.example' not in loc
        assert (loc.endswith('/books')) == expect_local
        client.get('/logout')


def test_text_file_as_cover_does_not_crash(librarian_client, app):
    with app.app_context():
        aid, cid = Author.query.first().id, Category.query.first().id
    r = librarian_client.post('/books/add', data={
        'title': 'Bad Cover Book', 'isbn': '9782222222222', 'author_id': aid, 'category_id': cid,
        'quantity': 1, 'description': 'x',
        'cover': (io.BytesIO(b'not an image'), 'cover.jpg')}, content_type='multipart/form-data', follow_redirects=True)
    assert r.status_code == 200 and b'not a valid image' in r.data


# ---------- loan policy text and the Settings page follow the stored settings ----------

def test_issue_page_shows_live_loan_policy(admin_client, app):
    with app.app_context():
        Setting.set('loan_duration', '21')
        Setting.set('max_renewals', '1')
    html = admin_client.get('/transactions/issue').get_data(as_text=True)
    assert 'standard loan duration is 21 days' in html
    assert 'renew up to 1 time unless' in html
    assert '14 days' not in html


def test_issue_page_says_so_when_renewals_are_off(admin_client, app):
    with app.app_context():
        Setting.set('max_renewals', '0')
    html = admin_client.get('/transactions/issue').get_data(as_text=True)
    assert 'Renewals are switched off' in html and 'renew up to' not in html


def test_member_renew_prompts_use_the_loan_period(member_client, app):
    with app.app_context():
        Setting.set('loan_duration', '10')
    _loan(app, days_late=0)
    html = member_client.get('/dashboard').get_data(as_text=True)
    assert 'Renew this book loan for 10 days?' in html
    assert 'for 14 days' not in html


def test_settings_page_has_readable_labels_and_limits(admin_client):
    html = admin_client.get('/admin/settings').get_data(as_text=True)
    for text in ('Loan period', 'Fine per overdue day', 'Cache capacity', 'Memory and performance', 'Retention'):
        assert text in html
    assert 'name="loan_duration"' in html and 'min="1"' in html and 'max="365"' in html
    assert 'step="any"' in html                                   # the fine rate takes decimals
    assert '>loan_duration<' not in html                          # the raw key is no longer the label


def test_every_setting_has_a_rule_a_label_and_a_valid_default():
    assert set(Setting.DEFAULTS) == set(Setting.RULES) == set(Setting.UI)
    for key, (value, _description) in Setting.DEFAULTS.items():
        ok, message = Setting.validate(key, value)
        assert ok, f'{key}: shipped default fails its own rule ({message})'


def test_saving_the_settings_page_unchanged_changes_nothing(admin_client, app):
    with app.app_context():
        data = {key: Setting.get(key) for key in Setting.DEFAULTS}
    r = admin_client.post('/admin/settings', data=data, follow_redirects=True)
    assert b'No changes made' in r.data


# ---------- data integrity: records that other records depend on ----------

def test_deleting_a_book_that_has_loan_history_is_refused_cleanly(admin_client, app):
    tid = _loan(app, status='returned')
    with app.app_context():
        book_id = db.session.get(Transaction, tid).book_id
    r = admin_client.post(f'/books/{book_id}/delete', follow_redirects=True)
    assert r.status_code == 200
    assert b'cannot be deleted' in r.data and b'quantity to 0' in r.data
    with app.app_context():
        assert db.session.get(Book, book_id) is not None
        assert db.session.get(Transaction, tid) is not None


def _edit_form(quantity):
    return {'title': 'Retire Me', 'isbn': '9780321127426', 'publisher': 'X', 'edition': '1st',
            'publication_year': 2002, 'description': 'd', 'quantity': quantity}


def test_a_title_with_history_can_be_retired_by_setting_quantity_to_zero(admin_client, app):
    tid = _loan(app, status='returned')
    with app.app_context():
        b = db.session.get(Transaction, tid).book
        book_id, author_id, category_id = b.id, b.author_id, b.category_id
    data = _edit_form(0) | {'author_id': author_id, 'category_id': category_id}
    r = admin_client.post(f'/books/{book_id}/edit', data=data, follow_redirects=True)
    assert r.status_code == 200 and b'updated' in r.data
    with app.app_context():
        b = db.session.get(Book, book_id)
        assert (b.quantity, b.available_quantity, b.is_available) == (0, 0, False)
        assert db.session.get(Transaction, tid) is not None          # the history is untouched


def test_quantity_cannot_drop_below_copies_on_loan(admin_client, app):
    tid = _loan(app)                                                 # one copy out
    with app.app_context():
        b = db.session.get(Transaction, tid).book
        book_id, author_id, category_id = b.id, b.author_id, b.category_id
        b.quantity, b.available_quantity = 3, 2
        db.session.commit()
    data = _edit_form(0) | {'author_id': author_id, 'category_id': category_id}
    r = admin_client.post(f'/books/{book_id}/edit', data=data, follow_redirects=True)
    assert b'still on loan' in r.data
    with app.app_context():
        b = db.session.get(Book, book_id)
        assert b.quantity == 1 and b.available_quantity == 0         # 1 copy out, none left to lend


def test_add_book_form_still_requires_at_least_one_copy(admin_client):
    html = admin_client.get('/books/add').get_data(as_text=True)
    assert 'name="quantity"' in html and 'min="1"' in html
