"""Activity log model."""
from datetime import datetime, timezone
from app.extensions import db


class ActivityLog(db.Model):
    __tablename__ = 'activity_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(100), nullable=False, index=True)
    details = db.Column(db.Text, default='')
    ip_address = db.Column(db.String(45), default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def __repr__(self):
        return f'<ActivityLog {self.action} at {self.created_at}>'
