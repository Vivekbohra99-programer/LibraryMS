"""Security and data-integrity behaviour: login throttling, headers, cookies, secret key, foreign keys."""
import os

import pytest
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models.activity_log import ActivityLog
from app.models.member import Member
from app.models.transaction import Transaction
from app.services.throttle import LoginThrottle
from datetime import datetime, timedelta, timezone


def _wrong(client, username='testmember', password='nope'):
    return client.post('/login', data={'username': username, 'password': password})


# ---------- the throttle on its own ----------

def test_throttle_locks_after_limit_and_expires():
    t = LoginThrottle(max_failures=3, lock_seconds=60)
    assert t.locked_for('1.2.3.4', 'sam', now=0) == 0
    assert not t.record_failure('1.2.3.4', 'sam', now=1)
    assert not t.record_failure('1.2.3.4', 'sam', now=2)
    assert t.record_failure('1.2.3.4', 'sam', now=3)               # third failure locks
    assert 0 < t.locked_for('1.2.3.4', 'sam', now=4) <= 60
    assert t.locked_for('1.2.3.4', 'other', now=4) == 0            # another username is not locked
    assert t.locked_for('9.9.9.9', 'sam', now=4) == 0              # another address is not locked
    assert t.locked_for('1.2.3.4', 'sam', now=70) == 0             # lock has run out
    assert not t.record_failure('1.2.3.4', 'sam', now=71)          # and counting starts again from one


def test_throttle_reset_and_username_case():
    t = LoginThrottle(max_failures=2, lock_seconds=60)
    t.record_failure('a', 'Sam', now=1)
    t.reset('a', 'sam')                                            # same user, different case
    assert not t.record_failure('a', 'SAM', now=2)                 # the earlier failure was cleared


def test_throttle_per_address_limit_stops_username_spraying():
    t = LoginThrottle(max_failures=2, lock_seconds=60, address_factor=3)      # address limit 6
    for i in range(5):
        assert not t.record_failure('1.1.1.1', f'user{i}', now=i)
    assert t.record_failure('1.1.1.1', 'user5', now=6)
    assert t.locked_for('1.1.1.1', 'a-brand-new-name', now=7) > 0


def test_throttle_memory_is_bounded():
    t = LoginThrottle(max_failures=5, max_entries=50)
    for i in range(5000):
        t.record_failure('1.1.1.1', f'made-up-{i}', now=i)
    assert len(t) <= 50


# ---------- the login route ----------

def test_five_wrong_passwords_lock_the_sign_in_even_for_the_right_password(client, app):
    for _ in range(5):
        assert _wrong(client).status_code == 200
    blocked = client.post('/login', data={'username': 'testmember', 'password': 'pass123'})
    assert blocked.status_code == 429
    assert b'Too many failed sign-in attempts' in blocked.data
    assert client.get('/dashboard').status_code in (302, 401)       # still not signed in
    with app.app_context():
        assert ActivityLog.query.filter_by(action='login_locked').count() == 1


def test_a_lock_on_one_username_does_not_stop_another_user(client):
    for _ in range(5):
        _wrong(client, 'testmember')
    ok = client.post('/login', data={'username': 'testadmin', 'password': 'pass123'}, follow_redirects=False)
    assert ok.status_code == 302


def test_correct_password_clears_the_failure_count(client):
    for _ in range(4):
        _wrong(client)
    assert client.post('/login', data={'username': 'testmember', 'password': 'pass123'}).status_code == 302
    client.get('/logout')
    for _ in range(4):                                              # four more would have locked it at five total
        assert _wrong(client).status_code == 200


def test_default_password_login_shows_a_notice(client, app):
    with app.app_context():
        from app.models.user import User
        u = User.query.filter_by(username='testmember').first()
        u.set_password('member123')
        db.session.commit()
    r = client.post('/login', data={'username': 'testmember', 'password': 'member123'}, follow_redirects=True)
    assert b'default demo password' in r.data


def test_normal_password_login_shows_no_default_notice(client):
    r = client.post('/login', data={'username': 'testmember', 'password': 'pass123'}, follow_redirects=True)
    assert b'default demo password' not in r.data


# ---------- headers and cookies ----------

def test_security_headers_are_present(client):
    r = client.get('/login')
    assert r.headers['X-Content-Type-Options'] == 'nosniff'
    assert r.headers['X-Frame-Options'] == 'SAMEORIGIN'
    assert r.headers['Referrer-Policy'] == 'same-origin'


def test_session_cookie_is_httponly_and_samesite(app):
    from config import Config
    assert Config.SESSION_COOKIE_HTTPONLY is True and Config.SESSION_COOKIE_SAMESITE == 'Lax'
    assert Config.REMEMBER_COOKIE_HTTPONLY is True and Config.REMEMBER_COOKIE_SAMESITE == 'Lax'


# ---------- secret key ----------

def _fresh_config(monkeypatch, tmp_path, env_key=None):
    """Import config.py again with BASE_DIR pointing at an empty folder."""
    import config
    monkeypatch.setattr(config, 'BASE_DIR', str(tmp_path))
    if env_key is None:
        monkeypatch.delenv('SECRET_KEY', raising=False)
    else:
        monkeypatch.setenv('SECRET_KEY', env_key)
    return config._secret_key()


def test_secret_key_is_random_persisted_and_not_the_old_public_string(monkeypatch, tmp_path):
    first = _fresh_config(monkeypatch, tmp_path)
    second = _fresh_config(monkeypatch, tmp_path)
    assert first == second and len(first) >= 64                       # created once, reused afterwards
    assert first != 'dev-secret-key-change-in-production'
    assert (tmp_path / 'instance' / 'secret.key').read_text().strip() == first
    if os.name == 'posix':
        assert oct((tmp_path / 'instance' / 'secret.key').stat().st_mode & 0o777) == '0o600'


def test_secret_key_environment_variable_wins(monkeypatch, tmp_path):
    assert _fresh_config(monkeypatch, tmp_path, env_key='from-the-environment') == 'from-the-environment'
    assert not (tmp_path / 'instance').exists()                       # nothing written when the env var is set


# ---------- database-level integrity ----------

def test_database_refuses_a_loan_for_a_book_that_does_not_exist(app):
    with app.app_context():
        member = Member.query.first()
        db.session.add(Transaction(book_id=987654, member_id=member.id,
                                   due_date=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


# ---------- user text inside JavaScript ----------

def test_staff_page_escapes_usernames_used_in_confirm_prompts(admin_client, app):
    from app.models.user import User
    with app.app_context():
        u = User(username='''o'brien");alert(1);//''', email='ob@test.com', role='librarian')
        u.set_password('pass123')
        db.session.add(u)
        db.session.commit()
    html = admin_client.get('/admin/staff').get_data(as_text=True)
    assert 'o\\u0027brien' in html                       # the quote is a JSON escape, not a string terminator
    assert "confirm('Deactivate o'brien" not in html and "Deactivate o'brien" not in html
