"""Catalogue search, shared by the public catalogue and the staff book list.

Q17 query cache. For a repeated search the costly work is the filter, the sort and the count, so the cache keeps
only what that work produces: the ids on the requested page and the total. That is a few hundred bytes per
entry, bounded by the cache's own size limit. The book rows themselves are read fresh on every request (one
IN query), so availability is never stale, and every write in the app already clears the cache."""
from types import SimpleNamespace

from flask_sqlalchemy.pagination import Pagination
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from app.extensions import db
from app.models.author import Author
from app.models.book import Book
from app.models.category import Category
from app.services.cache import search_cache

MAX_QUERY_CHARS = 100          # a longer search text is cut, so one request cannot make a giant cache key
SORTS = ('title', 'author', 'year', 'available', 'newest')


class CachedPagination(Pagination):
    """Pagination built from numbers we already have. The base class runs a query in __init__, so it is bypassed."""

    def __init__(self, items, page, per_page, total):          # noqa: super().__init__ would query the database
        self._query_args = {}
        self.page, self.per_page, self.max_per_page = page, per_page, None
        self.items, self.total = items, total

    def _query_items(self):
        return self.items

    def _query_count(self):
        return self.total


def _like(text):
    """Escape % and _ so they are searched for, not treated as wildcards."""
    return '%' + text.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'


def _order(sort):
    return {
        'title': (Book.title,),
        'author': (Author.name, Book.title),
        'year': (Book.publication_year.desc(), Book.title),
        'available': (Book.available_quantity.desc(), Book.title),
        'newest': (Book.created_at.desc(),),
    }[sort if sort in SORTS else 'title']


def search_books(q='', author_id=None, category_id=None, availability='', sort='title', page=1, per_page=25):
    """One page of books matching the filters, as a pagination object. Matches title, author name or ISBN."""
    q = (q or '').strip()[:MAX_QUERY_CHARS]
    page = max(int(page or 1), 1)
    sort = sort if sort in SORTS else 'title'
    availability = availability if availability in ('available', 'unavailable') else ''
    key = f'cat|{q.lower()}|{author_id or 0}|{category_id or 0}|{availability}|{sort}|{page}|{per_page}'

    cached = search_cache.get(key)
    if cached is None:
        query = db.session.query(Book.id).join(Author, Book.author_id == Author.id)
        if q:
            pattern = _like(q)
            query = query.filter(or_(Book.title.ilike(pattern, escape='\\'),
                                     Book.isbn.ilike(pattern, escape='\\'),
                                     Author.name.ilike(pattern, escape='\\')))
        if author_id:
            query = query.filter(Book.author_id == author_id)
        if category_id:
            query = query.filter(Book.category_id == category_id)
        if availability == 'available':
            query = query.filter(Book.available_quantity > 0)
        elif availability == 'unavailable':
            query = query.filter(Book.available_quantity == 0)
        total = query.count()
        ids = tuple(row[0] for row in query.order_by(*_order(sort), Book.id)
                    .offset((page - 1) * per_page).limit(per_page))
        cached = (ids, total)
        search_cache.set(key, cached)

    ids, total = cached
    rows = {}
    if ids:
        books = (Book.query.filter(Book.id.in_(ids))
                 .options(selectinload(Book.author), selectinload(Book.category)).all())
        rows = {b.id: b for b in books}
    return CachedPagination([rows[i] for i in ids if i in rows], page, per_page, total)


def filter_lists():
    """(authors, categories) for the filter drop-downs: id and name only, cached until the next write."""
    cached = search_cache.get('lists:authors+categories')
    if cached is None:
        authors = [SimpleNamespace(id=i, name=n) for i, n in db.session.query(Author.id, Author.name).order_by(Author.name)]
        categories = [SimpleNamespace(id=i, name=n) for i, n in db.session.query(Category.id, Category.name).order_by(Category.name)]
        cached = (authors, categories)
        search_cache.set('lists:authors+categories', cached)
    return cached
