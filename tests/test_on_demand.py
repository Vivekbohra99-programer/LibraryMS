"""Q17 on-demand loading and the query cache, proved on the real routes rather than on a toy benchmark.

* the compressed cover and description are deferred columns: list pages never read them from the database
* catalogue searches go through the bounded LRU cache and are never stale after a write"""
import gc
import io
import os
import re
import tracemalloc
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

from PIL import Image
from sqlalchemy import event, inspect
from sqlalchemy.orm import undefer

from app.extensions import db
from app.models.author import Author
from app.models.book import Book
from app.models.category import Category
from app.models.member import Member
from app.models.transaction import Transaction
from app.services.cache import search_cache
from app.services.compression import compress_bytes, compress_text


@contextmanager
def sql_log():
    """Every SQL statement the app sends while the block runs."""
    seen = []

    def before(conn, cursor, statement, parameters, context, executemany):
        seen.append(statement)

    event.listen(db.engine, 'before_cursor_execute', before)
    try:
        yield seen
    finally:
        event.remove(db.engine, 'before_cursor_execute', before)


def _selected_columns(statements):
    """The column list of each SELECT that returns rows (the text before the first FROM).
    COUNT(*) over a subquery is skipped: SQLite flattens it and never reads the columns it lists."""
    out = []
    for s in statements:
        s = s.lstrip()
        if s.upper().startswith('SELECT') and not s.upper().startswith('SELECT COUNT('):
            out.append(re.split(r'\sFROM\s', s, maxsplit=1)[0])
    return out


def _heavy_books(app, n=30, blob_kb=100):
    """n books whose compressed cover is about blob_kb KB of incompressible data."""
    with app.app_context():
        a, c = Author.query.first(), Category.query.first()
        for i in range(n):
            payload = os.urandom(blob_kb * 1024)
            d = f'Description of heavy book {i}. ' * 40
            db.session.add(Book(title=f'Heavy {i:02d}', isbn=f'97811{i:08d}', author_id=a.id, category_id=c.id,
                                description_compressed=compress_text(d), description_raw_size=len(d),
                                cover_compressed=compress_bytes(payload), cover_raw_size=len(payload),
                                quantity=1, available_quantity=1))
        db.session.commit()
        search_cache.invalidate_all()


# ---------- the columns really are deferred ----------

def test_blob_columns_are_not_loaded_with_the_row(app):
    with app.app_context():
        book = Book.query.first()
        unloaded = inspect(book).unloaded
        assert 'cover_compressed' in unloaded and 'description_compressed' in unloaded
        assert book.title and book.cover_raw_size > 0                  # ordinary columns are there
        assert book.has_cover is True
        assert 'cover_compressed' in inspect(book).unloaded            # has_cover did not pull the image in


def test_touching_a_blob_loads_it_once_on_demand(app):
    with app.app_context():
        book = Book.query.first()
        assert book.description and 'cover_compressed' in inspect(book).unloaded     # description loaded, cover not
        assert book.cover_bytes == b'FAKE_COVER_JPEG'                                # now the cover loads


def test_loading_a_page_of_books_uses_a_fraction_of_the_memory(app):
    _heavy_books(app, n=30, blob_kb=100)                                              # ~3 MB of blobs in the database

    def peak_of(fn):
        if not tracemalloc.is_tracing():
            tracemalloc.start()
        gc.collect()
        tracemalloc.reset_peak()
        base = tracemalloc.get_traced_memory()[0]
        keep = fn()
        peak = tracemalloc.get_traced_memory()[1] - base
        del keep
        return peak

    with app.app_context():
        deferred = peak_of(lambda: Book.query.all())
        db.session.remove()
        gc.collect()
        everything = peak_of(lambda: Book.query.options(undefer(Book.cover_compressed),
                                                        undefer(Book.description_compressed)).all())
        assert everything > 2_500_000                                                  # the blobs really are in play
        assert deferred < everything / 5, f'deferred {deferred} B vs everything {everything} B'


# ---------- list pages and exports never select the blobs ----------

def test_list_pages_never_select_the_blob_columns(admin_client, app):
    _heavy_books(app, n=5, blob_kb=10)
    for url in ('/catalogue', '/catalogue?q=heavy&sort=author', '/books', '/books?page=1', '/transactions',
                '/transactions/issue', '/reports/books', '/reports/export/books?format=csv',
                '/reports/export/transactions?format=csv', '/authors', '/categories', '/dashboard', '/'):
        with app.app_context():
            with sql_log() as sql:
                assert admin_client.get(url).status_code in (200, 302), url
        leaked = [c for c in _selected_columns(sql) if 'cover_compressed' in c or 'description_compressed' in c]
        assert not leaked, f'{url} selected a blob column: {leaked[0][:200]}'


def test_detail_page_and_cover_endpoint_still_work(admin_client, app):
    with app.app_context():
        book = Book.query.first()
        book_id = book.id
        buf = io.BytesIO()
        Image.new('RGB', (40, 60), (200, 30, 30)).save(buf, 'JPEG')
        book.cover_compressed, book.cover_raw_size = compress_bytes(buf.getvalue()), len(buf.getvalue())
        db.session.commit()
    page = admin_client.get(f'/book/{book_id}').get_data(as_text=True)
    assert 'A foundational book on software architecture' in page          # the description was loaded on demand
    r = admin_client.get(f'/book/{book_id}/cover')
    assert r.status_code == 200 and r.mimetype == 'image/jpeg' and r.data == buf.getvalue()
    with app.app_context():
        with sql_log() as sql:
            admin_client.get(f'/book/{book_id}/cover')
        assert len(sql) == 1 and 'cover_compressed' in sql[0] and 'books.title' not in sql[0]    # one query, the blob only


def test_cover_url_changes_when_the_cover_changes(app):
    with app.test_request_context():
        book = Book.query.first()
        before = book.cover_url
        book.cover_raw_size = book.cover_raw_size + 123
        after = book.cover_url
    assert before != after and 'v=' in before


def test_catalogue_cards_link_to_the_versioned_cover(admin_client, app):
    with app.app_context():
        book = Book.query.first()
        expected = f'/book/{book.id}/cover?v={book.cover_raw_size}'
    assert expected in admin_client.get('/catalogue').get_data(as_text=True)


# ---------- the query cache in front of catalogue search ----------

def test_repeating_a_catalogue_search_hits_the_cache(client, app):
    search_cache.invalidate_all()
    s0 = search_cache.stats()
    client.get('/catalogue?q=patterns')
    s1 = search_cache.stats()
    client.get('/catalogue?q=patterns')
    client.get('/catalogue?q=patterns')
    s2 = search_cache.stats()
    assert s1['misses'] > s0['misses']                         # first time: computed
    assert s2['hits'] >= s1['hits'] + 2                        # then served from the cache
    assert s2['misses'] == s1['misses']                        # without computing again


def test_a_repeated_search_sends_fewer_queries(client, app):
    search_cache.invalidate_all()
    with app.app_context():
        with sql_log() as first:
            client.get('/catalogue?q=patterns&sort=author')
        with sql_log() as second:
            client.get('/catalogue?q=patterns&sort=author')
    assert len(second) < len(first)
    assert not any('count(' in s.lower() for s in second)      # no COUNT on the second request


def test_a_different_search_is_a_separate_cache_entry(client):
    search_cache.invalidate_all()
    client.get('/catalogue?q=patterns')
    entries = search_cache.stats()['entries']
    client.get('/catalogue?q=something+else')
    assert search_cache.stats()['entries'] > entries


def test_cache_entries_hold_ids_and_a_total_not_book_objects(client):
    search_cache.invalidate_all()
    client.get('/catalogue?q=patterns')
    catalogue_keys = [k for k in search_cache._store if k.startswith('cat|')]
    assert len(catalogue_keys) == 1
    ids, total = search_cache.get(catalogue_keys[0])
    assert isinstance(ids, tuple) and all(isinstance(i, int) for i in ids) and isinstance(total, int)
    assert 'Patterns of Enterprise' not in repr(search_cache._store)          # no titles, no objects: ids and a count


def test_a_loan_is_visible_in_the_catalogue_at_once(admin_client, member_client, app):
    with app.app_context():
        book = Book.query.first()
        member = Member.query.first()
        book_id, member_id = book.id, member.id
        book.quantity = book.available_quantity = 1
        db.session.commit()
        search_cache.invalidate_all()
    def card_titles(url):
        return re.findall(r'<h3[^>]*>([^<]+)</h3>', admin_client.get(url).get_data(as_text=True))

    title = 'Patterns of Enterprise Application Architecture'
    assert title in card_titles('/catalogue?availability=available')
    admin_client.post('/transactions/issue', data={'book_id': book_id, 'member_id': member_id})
    assert title not in card_titles('/catalogue?availability=available')      # the cached page was cleared by the write
    assert title in card_titles('/catalogue?availability=unavailable')


def test_a_new_author_appears_in_the_filter_list_at_once(admin_client):
    assert 'Brand New Author' not in admin_client.get('/catalogue').get_data(as_text=True)
    admin_client.post('/authors/add', data={'name': 'Brand New Author', 'bio': 'x'})
    assert 'Brand New Author' in admin_client.get('/catalogue').get_data(as_text=True)


def test_changing_a_setting_clears_cached_figures(admin_client, app):
    admin_client.get('/dashboard')
    assert search_cache.get('dash:analytics') is not None
    admin_client.post('/admin/settings', data={'fine_rate': '4'})
    assert search_cache.get('dash:analytics') is None


def test_an_enormous_search_text_is_cut_and_still_works(client):
    r = client.get('/catalogue?q=' + 'x' * 20000)
    assert r.status_code == 200
    longest_key = max((k for k in search_cache._store), key=len)
    assert len(longest_key) < 300


# ---------- backup is a consistent snapshot ----------

def test_backup_contains_the_latest_committed_row_and_is_healthy(admin_client, app):
    import sqlite3
    with app.app_context():
        db.session.add(Category(name='Committed Just Before Backup', description='x'))
        db.session.commit()
    admin_client.post('/admin/backups/create')
    folder = app.config['BACKUP_FOLDER']
    path = os.path.join(folder, [f for f in os.listdir(folder) if f.endswith('.db')][0])
    con = sqlite3.connect(path)
    assert con.execute('pragma integrity_check').fetchone()[0] == 'ok'
    assert con.execute("select count(*) from categories where name='Committed Just Before Backup'").fetchone()[0] == 1
    con.close()
