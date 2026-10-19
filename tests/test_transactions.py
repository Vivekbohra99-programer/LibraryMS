"""Tests for transactions: issue, return, renewal, and loan constraints."""
from datetime import datetime, timedelta, timezone
from app.models.book import Book
from app.models.member import Member
from app.models.transaction import Transaction
from app.models.fine import Fine


def test_issue_book_success(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        book_id = book.id
        member_id = member.id
        init_avail = book.available_quantity

    response = librarian_client.post('/transactions/issue', data={
        'book_id': book_id,
        'member_id': member_id,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'issued' in response.data or b'Due' in response.data

    with app.app_context():
        b = Book.query.get(book_id)
        assert b.available_quantity == init_avail - 1
        txn = Transaction.query.filter_by(book_id=book_id, member_id=member_id, status='issued').first()
        assert txn is not None
        assert not txn.is_overdue


def test_issue_book_unavailable(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        book.available_quantity = 0
        app.extensions['sqlalchemy'].session.commit()
        book_id = book.id
        member_id = member.id

    response = librarian_client.post('/transactions/issue', data={
        'book_id': book_id,
        'member_id': member_id,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'no available copies' in response.data


def test_issue_book_suspended_member(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        member.status = 'suspended'
        app.extensions['sqlalchemy'].session.commit()
        book_id = book.id
        member_id = member.id

    response = librarian_client.post('/transactions/issue', data={
        'book_id': book_id,
        'member_id': member_id,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'not active' in response.data


def test_return_book_normal(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        txn = Transaction(
            book_id=book.id,
            member_id=member.id,
            issue_date=datetime.now(timezone.utc) - timedelta(days=5),
            due_date=datetime.now(timezone.utc) + timedelta(days=9),
            status='issued'
        )
        book.available_quantity -= 1
        app.extensions['sqlalchemy'].session.add(txn)
        app.extensions['sqlalchemy'].session.commit()
        txn_id = txn.id
        init_avail = book.available_quantity

    response = librarian_client.post(f'/transactions/{txn_id}/return', follow_redirects=True)
    assert response.status_code == 200
    assert b'Book returned' in response.data

    with app.app_context():
        t = Transaction.query.get(txn_id)
        assert t.status == 'returned'
        assert t.return_date is not None
        b = Book.query.get(t.book_id)
        assert b.available_quantity == init_avail + 1


def test_return_book_overdue_creates_fine(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        # 10 days overdue
        txn = Transaction(
            book_id=book.id,
            member_id=member.id,
            issue_date=datetime.now(timezone.utc) - timedelta(days=24),
            due_date=datetime.now(timezone.utc) - timedelta(days=10),
            status='issued'
        )
        book.available_quantity -= 1
        app.extensions['sqlalchemy'].session.add(txn)
        app.extensions['sqlalchemy'].session.commit()
        txn_id = txn.id

    response = librarian_client.post(f'/transactions/{txn_id}/return', follow_redirects=True)
    assert response.status_code == 200
    assert b'Fine' in response.data or b'fine' in response.data

    with app.app_context():
        t = Transaction.query.get(txn_id)
        assert t.status == 'returned'
        fine = Fine.query.filter_by(transaction_id=txn_id).first()
        assert fine is not None
        assert fine.amount > 0
        assert not fine.paid


def test_renew_book_success(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        initial_due = datetime.now(timezone.utc) + timedelta(days=7)
        txn = Transaction(
            book_id=book.id,
            member_id=member.id,
            issue_date=datetime.now(timezone.utc) - timedelta(days=7),
            due_date=initial_due,
            status='issued',
            renewal_count=0
        )
        app.extensions['sqlalchemy'].session.add(txn)
        app.extensions['sqlalchemy'].session.commit()
        txn_id = txn.id

    response = librarian_client.post(f'/transactions/{txn_id}/renew', follow_redirects=True)
    assert response.status_code == 200
    assert b'renewed' in response.data or b'Renewed' in response.data

    with app.app_context():
        t = Transaction.query.get(txn_id)
        assert t.renewal_count == 1
        # Normalize for comparison: SQLite strips timezone info
        due = t.due_date.replace(tzinfo=timezone.utc) if t.due_date.tzinfo is None else t.due_date
        assert due > initial_due


def test_renew_overdue_book_fails(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        txn = Transaction(
            book_id=book.id,
            member_id=member.id,
            issue_date=datetime.now(timezone.utc) - timedelta(days=20),
            due_date=datetime.now(timezone.utc) - timedelta(days=6),
            status='issued',
            renewal_count=0
        )
        app.extensions['sqlalchemy'].session.add(txn)
        app.extensions['sqlalchemy'].session.commit()
        txn_id = txn.id

    response = librarian_client.post(f'/transactions/{txn_id}/renew', follow_redirects=True)
    assert response.status_code == 200
    assert b'Cannot renew an overdue book' in response.data
