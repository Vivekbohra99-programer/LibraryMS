"""Fine model."""
from datetime import datetime, timezone
from app.extensions import db


class Fine(db.Model):
    __tablename__ = 'fines'

    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.Integer, db.ForeignKey('transactions.id'), nullable=False)
    member_id = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False, index=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    paid = db.Column(db.Boolean, default=False)
    paid_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Fine ₹{self.amount} paid={self.paid}>'
