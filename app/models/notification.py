"""Notification model."""
from datetime import datetime, timezone
from app.extensions import db


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default='info')  # info, warning, success, danger
    read = db.Column(db.Boolean, default=False)
    link = db.Column(db.String(300), default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f'<Notification {self.id} read={self.read}>'
