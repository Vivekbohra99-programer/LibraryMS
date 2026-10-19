"""Transaction model – tracks book issue/return/renewal."""
from datetime import datetime, timezone
from app.extensions import db


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey('books.id'), nullable=False, index=True)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False, index=True)
    issue_date = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    due_date = db.Column(db.DateTime, nullable=False, index=True)
    return_date = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default='issued', index=True)
    renewal_count = db.Column(db.Integer, default=0)
    issued_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    returned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    fine = db.relationship('Fine', backref='transaction', uselist=False, lazy=True)
    issuer = db.relationship('User', foreign_keys=[issued_by], lazy=True)
    returner = db.relationship('User', foreign_keys=[returned_by], lazy=True)

    @property
    def is_overdue(self):
        if self.status != 'issued':
            return False
        return datetime.now(timezone.utc) > self.due_date.replace(tzinfo=timezone.utc) if self.due_date.tzinfo is None else datetime.now(timezone.utc) > self.due_date

    @property
    def overdue_days(self):
        if not self.is_overdue:
            return 0
        due = self.due_date.replace(tzinfo=timezone.utc) if self.due_date.tzinfo is None else self.due_date
        return (datetime.now(timezone.utc) - due).days

    def accrued_fine(self, rate):
        """Fine owed if the book were returned right now: whole days late x daily rate.

        Not stored. A Fine row is only created when the book is actually returned,
        so this is a live estimate for loans that are still out."""
        days = self.overdue_days
        return round(days * rate, 2) if days > 0 else 0.0

    def __repr__(self):
        return f'<Transaction {self.id} book={self.book_id} member={self.member_id} status={self.status}>'
