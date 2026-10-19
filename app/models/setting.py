"""System settings – stored in DB, not hardcoded."""
from datetime import datetime, timezone
from app.extensions import db


MIN_RETENTION_DAYS = 30     # purging anything newer than a month is almost always a mistake


class Setting(db.Model):
    __tablename__ = 'settings'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.String(500), nullable=False, default='')
    description = db.Column(db.String(300), default='')
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Defaults loaded on first run
    DEFAULTS = {
        'fine_rate': ('2.0', 'Fine per day (₹) for overdue books'),
        'loan_duration': ('14', 'Default loan duration in days'),
        'max_renewals': ('2', 'Maximum number of renewals per transaction'),
        'member_loan_limit': ('5', 'Default loan limit per member'),
        'cache_ttl': ('120', 'Cache TTL in seconds'),
        'cache_max_size': ('64', 'Maximum cache entries'),
        'compression_quality': ('85', 'JPEG compression quality (1-100)'),
        'max_image_dimension': ('800', 'Maximum image width/height in pixels'),
        'page_size': ('25', 'Default page size for pagination'),
        'log_retention_days': ('365', 'Days to keep activity logs'),
        'transaction_retention_days': ('730', 'Days to keep returned transactions'),
        'max_upload_size_mb': ('5', 'Maximum upload size in MB'),
    }

    # key: (type, minimum, maximum). Applied by validate() before anything is saved.
    RULES = {
        'fine_rate': (float, 0, 10000),
        'loan_duration': (int, 1, 365),
        'max_renewals': (int, 0, 20),
        'member_loan_limit': (int, 1, 100),
        'cache_ttl': (int, 1, 86400),
        'cache_max_size': (int, 1, 10000),
        'compression_quality': (int, 1, 100),
        'max_image_dimension': (int, 100, 4000),
        'page_size': (int, 5, 100),
        'log_retention_days': (int, MIN_RETENTION_DAYS, 36500),
        'transaction_retention_days': (int, MIN_RETENTION_DAYS, 36500),
        'max_upload_size_mb': (int, 1, 16),
    }

    # key: (label, unit, group). Presentation only; the Settings page reads this so the form never shows raw keys.
    UI = {
        'loan_duration': ('Loan period', 'days', 'Circulation'),
        'max_renewals': ('Renewals allowed per loan', 'times', 'Circulation'),
        'member_loan_limit': ('Books a member may hold', 'books', 'Circulation'),
        'fine_rate': ('Fine per overdue day', '₹', 'Circulation'),
        'cache_ttl': ('Cache lifetime', 'seconds', 'Memory and performance'),
        'cache_max_size': ('Cache capacity', 'entries', 'Memory and performance'),
        'compression_quality': ('Cover JPEG quality', '1 to 100', 'Memory and performance'),
        'max_image_dimension': ('Largest cover side', 'pixels', 'Memory and performance'),
        'max_upload_size_mb': ('Largest upload', 'MB', 'Memory and performance'),
        'page_size': ('Rows per page', 'rows', 'Memory and performance'),
        'log_retention_days': ('Keep activity logs for', 'days', 'Retention'),
        'transaction_retention_days': ('Keep returned loans for', 'days', 'Retention'),
    }

    @classmethod
    def validate(cls, key, raw):
        """Return (True, cleaned_string) or (False, message). Rejects text, NaN/inf and out-of-range numbers."""
        kind, lo, hi = cls.RULES.get(key, (str, None, None))
        if kind is str:
            return True, str(raw).strip()
        label = key.replace('_', ' ')
        try:
            num = kind(raw)
        except (TypeError, ValueError):
            return False, f'{label}: "{raw}" is not a valid {"whole number" if kind is int else "number"}.'
        if num != num or num in (float('inf'), float('-inf')) or not (lo <= num <= hi):
            return False, f'{label}: must be between {lo} and {hi}.'
        return True, (str(int(num)) if kind is int else str(round(num, 2)))

    @classmethod
    def get(cls, key, default=None):
        s = cls.query.filter_by(key=key).first()
        if s:
            return s.value
        # Fall back to built-in default
        if key in cls.DEFAULTS:
            return cls.DEFAULTS[key][0]
        return default

    @classmethod
    def _clamp(cls, key, value):
        """Keep a stored value inside its allowed range. Rows saved before validation existed (or edited by
        hand in the database) could hold 0 or -5 for a page size, and that must not crash a page."""
        rule = cls.RULES.get(key)
        if rule and rule[0] in (int, float):
            return min(max(value, rule[1]), rule[2])
        return value

    @classmethod
    def get_int(cls, key, default=0):
        try:
            return cls._clamp(key, int(cls.get(key, str(default))))
        except (ValueError, TypeError):
            return default

    @classmethod
    def get_float(cls, key, default=0.0):
        try:
            value = float(cls.get(key, str(default)))
        except (ValueError, TypeError):
            return default
        if value != value:                       # NaN
            return default
        return cls._clamp(key, value)

    @classmethod
    def set(cls, key, value):
        s = cls.query.filter_by(key=key).first()
        if s:
            s.value = str(value)
        else:
            desc = cls.DEFAULTS.get(key, ('', ''))[1]
            s = cls(key=key, value=str(value), description=desc)
            db.session.add(s)
        db.session.commit()

    @classmethod
    def seed_defaults(cls):
        for key, (val, desc) in cls.DEFAULTS.items():
            if not cls.query.filter_by(key=key).first():
                db.session.add(cls(key=key, value=val, description=desc))
        db.session.commit()

    def __repr__(self):
        return f'<Setting {self.key}={self.value}>'
