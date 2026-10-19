"""Notification service."""
from app.extensions import db
from app.models.notification import Notification


def notify(user_id, message, type='info', link=''):
    n = Notification(user_id=user_id, message=message, type=type, link=link)
    db.session.add(n)
    db.session.commit()
    return n


def get_unread_count(user_id):
    return Notification.query.filter_by(user_id=user_id, read=False).count()


def get_recent(user_id, limit=10):
    return Notification.query.filter_by(user_id=user_id).order_by(
        Notification.created_at.desc()).limit(limit).all()
