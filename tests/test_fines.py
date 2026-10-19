"""Tests for Fine calculation, listing, and payment."""
from datetime import datetime, timezone
from app.models.fine import Fine
from app.models.member import Member
from app.models.book import Book
from app.models.transaction import Transaction


def test_pay_fine_staff(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        txn = Transaction(
            book_id=book.id,
            member_id=member.id,
            issue_date=datetime.now(timezone.utc),
            due_date=datetime.now(timezone.utc),
            status='returned'
        )
        app.extensions['sqlalchemy'].session.add(txn)
        app.extensions['sqlalchemy'].session.flush()

        fine = Fine(
            transaction_id=txn.id,
            member_id=member.id,
            amount=20.00,
            paid=False
        )
        app.extensions['sqlalchemy'].session.add(fine)
        app.extensions['sqlalchemy'].session.commit()
        fine_id = fine.id

    response = librarian_client.post(f'/fines/{fine_id}/pay', follow_redirects=True)
    assert response.status_code == 200
    assert b'marked as paid' in response.data

    with app.app_context():
        f = Fine.query.get(fine_id)
        assert f.paid
        assert f.paid_date is not None


def test_member_views_own_fines(member_client):
    response = member_client.get('/fines')
    assert response.status_code == 200
    assert b'Fines' in response.data or b'Fine' in response.data
