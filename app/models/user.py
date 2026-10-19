"""User model – authentication & role management."""
from datetime import datetime, timezone
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app.extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='member')  # admin, librarian, member
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    member = db.relationship('Member', backref='user', uselist=False, lazy=True)
    notifications = db.relationship('Notification', backref='user', lazy='dynamic')
    activity_logs = db.relationship('ActivityLog', backref='user', lazy='dynamic',
                                    foreign_keys='ActivityLog.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == 'admin'

    @property
    def is_librarian(self):
        return self.role == 'librarian'

    @property
    def is_member_role(self):
        return self.role == 'member'

    @property
    def is_staff(self):
        return self.role in ('admin', 'librarian')

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
