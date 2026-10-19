"""Book model – stores covers and descriptions compressed (Q17 Feature 1)."""
from datetime import datetime, timezone
from app.extensions import db


class Book(db.Model):
    __tablename__ = 'books'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False, index=True)
    isbn = db.Column(db.String(20), unique=True, nullable=True, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('authors.id'), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=False, index=True)
    publisher = db.Column(db.String(200), default='')
    edition = db.Column(db.String(50), default='')
    publication_year = db.Column(db.Integer, nullable=True)

    # Q17 Feature 1: Asset Compression – description stored compressed
    # Q17 Feature 2: On-demand loading – the two BLOB columns are deferred, so a query that returns Book rows
    # (a catalogue page, the issue form's drop-down, a report) leaves them in the database. They are read from
    # the database only when something touches them (the detail page, the cover endpoint, the edit form).
    description_compressed = db.deferred(db.Column(db.LargeBinary, default=b''))
    description_raw_size = db.Column(db.Integer, default=0)

    # Q17 Feature 1: Cover image stored compressed
    cover_compressed = db.deferred(db.Column(db.LargeBinary, default=b''))
    cover_raw_size = db.Column(db.Integer, default=0)

    quantity = db.Column(db.Integer, nullable=False, default=1)
    available_quantity = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    transactions = db.relationship('Transaction', backref='book', lazy='dynamic')

    # ---------- Q17: Lazy decompression helpers ----------
    _description_cache = None
    _cover_cache = None

    @property
    def description(self):
        """Decompress description only when actually read (Feature 2)."""
        if self._description_cache is None:
            from app.services.compression import decompress_text
            self._description_cache = decompress_text(self.description_compressed)
        return self._description_cache

    @property
    def cover_bytes(self):
        """Decompress cover only when actually read (Feature 2)."""
        if self._cover_cache is None:
            from app.services.compression import decompress_bytes
            self._cover_cache = decompress_bytes(self.cover_compressed)
        return self._cover_cache

    @property
    def has_cover(self):
        # cover_raw_size is a plain column that always loads with the row. Reading cover_compressed here would
        # fetch the whole image from the database once per book just to answer yes or no.
        return bool(self.cover_raw_size)

    @property
    def cover_url(self):
        """Link to the cover. The size is in the URL so a replaced cover is not hidden by the browser's
        one-hour cache of the old image."""
        from flask import url_for
        return url_for('books.cover', book_id=self.id, v=self.cover_raw_size or 0)

    @property
    def is_available(self):
        return self.available_quantity > 0

    @property
    def compressed_footprint(self):
        return len(self.description_compressed or b'') + len(self.cover_compressed or b'')

    @property
    def raw_footprint(self):
        return (self.description_raw_size or 0) + (self.cover_raw_size or 0)

    @property
    def compression_savings_pct(self):
        raw = self.raw_footprint
        if raw == 0:
            return 0.0
        return round((1 - self.compressed_footprint / raw) * 100, 1)

    def __repr__(self):
        return f'<Book {self.title}>'
