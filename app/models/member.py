"""Member model."""
from datetime import datetime, timezone
from app.extensions import db


class Member(db.Model):
    __tablename__ = 'members'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, unique=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    phone = db.Column(db.String(20), default='')
    address = db.Column(db.Text, default='')
    registration_date = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    status = db.Column(db.String(20), default='active', index=True)  # active, suspended, inactive
    loan_limit = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    transactions = db.relationship('Transaction', backref='member', lazy='dynamic')
    fines = db.relationship('Fine', backref='member', lazy='dynamic')

    @property
    def is_active(self):
        return self.status == 'active'

    @property
    def active_loans_count(self):
        from app.models.transaction import Transaction
        return self.transactions.filter(Transaction.status == 'issued').count()

    @property
    def can_borrow(self):
        return self.is_active and self.active_loans_count < self.loan_limit

    @property
    def remaining_capacity(self):
        return max(0, self.loan_limit - self.active_loans_count)

    def __repr__(self):
        return f'<Member {self.name}>'
