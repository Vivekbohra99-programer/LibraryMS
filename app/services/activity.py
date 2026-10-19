"""Activity logging service."""
from app.extensions import db
from app.models.activity_log import ActivityLog


def log_activity(user_id, action, details='', ip_address=''):
    entry = ActivityLog(
        user_id=user_id,
        action=action,
        details=details,
        ip_address=ip_address,
    )
    db.session.add(entry)
    db.session.commit()
