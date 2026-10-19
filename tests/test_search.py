"""Catalogue search, filtering, sorting and pagination (the shared search_books service)."""
import re

from app.extensions import db
from app.models.author import Author
from app.models.book import Book
from app.models.category import Category
from app.models.setting import Setting
from app.services.cache import search_cache
from app.services.compression import compress_text


def _book(title, author, category, isbn, year=2000, available=1, quantity=1):
    d = f'About {title}'
    return Book(title=title, isbn=isbn, author_id=author.id, category_id=category.id, publication_year=year,
                description_compressed=compress_text(d), description_raw_size=len(d),
                quantity=quantity, available_quantity=available)


def _shelf(app):
    """Zed's book is created first (lower author id) but Abe sorts first by name."""
    with app.app_context():
        cat = Category.query.first()
        zed, abe = Author(name='Zed Author', bio=''), Author(name='Abe Author', bio='')
        db.session.add_all([zed, abe])
        db.session.flush()
        db.session.add_all([
            _book('Zebra Handbook', zed, cat, '9780000000011', 1999, available=1),
            _book('Alpha Guide', abe, cat, '9780000000028', 2015, available=0),
            _book('Discount 50% Off', abe, cat, '9780000000035', 2020, available=1),
            _book('Under_score Tales', zed, cat, '9780000000042', 2010, available=1),
        ])
        db.session.commit()
        search_cache.invalidate_all()


def _titles(html):
    """Book titles in page order (the cards put the title in <h3>)."""
    return re.findall(r'<h3[^>]*>([^<]+)</h3>', html)


def test_search_matches_title_isbn_and_author_name(client, app):
    _shelf(app)
    assert 'Zebra Handbook' in client.get('/catalogue?q=zebra').get_data(as_text=True)
    assert 'Zebra Handbook' in client.get('/catalogue?q=9780000000011').get_data(as_text=True)
    page = client.get('/catalogue?q=abe+author').get_data(as_text=True)
    assert 'Alpha Guide' in page and 'Discount 50% Off' in page and 'Zebra Handbook' not in page


def test_search_is_case_insensitive(client, app):
    _shelf(app)
    assert 'Zebra Handbook' in client.get('/catalogue?q=ZEBRA').get_data(as_text=True)


def test_percent_and_underscore_are_searched_for_not_treated_as_wildcards(client, app):
    _shelf(app)
    page = client.get('/catalogue?q=50%25').get_data(as_text=True)
    assert 'Discount 50% Off' in page and 'Zebra Handbook' not in page
    page = client.get('/catalogue?q=_').get_data(as_text=True)
    assert 'Under_score Tales' in page and 'Zebra Handbook' not in page
    page = client.get('/catalogue?q=%25').get_data(as_text=True)         # a lone % matches only titles containing a %
    assert 'Discount 50% Off' in page and 'Zebra Handbook' not in page and 'Under_score Tales' not in page


def test_sort_by_author_orders_by_name_not_by_id(client, app):
    _shelf(app)
    titles = [t for t in _titles(client.get('/catalogue?sort=author&q=author').get_data(as_text=True))]
    abe_idx = max(titles.index('Alpha Guide'), titles.index('Discount 50% Off'))
    zed_idx = min(titles.index('Zebra Handbook'), titles.index('Under_score Tales'))
    assert abe_idx < zed_idx                                    # all of Abe's books before any of Zed's


def test_sort_by_year_newest_first_and_title_az(client, app):
    _shelf(app)
    years = _titles(client.get('/catalogue?sort=year&q=author').get_data(as_text=True))
    assert years.index('Discount 50% Off') < years.index('Alpha Guide') < years.index('Under_score Tales') < years.index('Zebra Handbook')
    az = _titles(client.get('/catalogue?sort=title&q=author').get_data(as_text=True))
    assert az == sorted(az)


def test_unknown_sort_falls_back_to_title(client, app):
    _shelf(app)
    assert client.get('/catalogue?sort=;drop+table+books').status_code == 200


def test_availability_and_author_and_category_filters(client, app):
    _shelf(app)
    with app.app_context():
        abe_id = Author.query.filter_by(name='Abe Author').one().id
    only_out = client.get('/catalogue?availability=unavailable&q=author').get_data(as_text=True)
    assert 'Alpha Guide' in only_out and 'Zebra Handbook' not in only_out
    abe = client.get(f'/catalogue?author={abe_id}').get_data(as_text=True)
    assert 'Alpha Guide' in abe and 'Zebra Handbook' not in abe
    assert 'Zebra Handbook' not in client.get('/catalogue?category=99999').get_data(as_text=True)


def test_pages_are_disjoint_and_complete_even_when_the_sort_key_ties(client, app):
    with app.app_context():
        cat, author = Category.query.first(), Author.query.first()
        for i in range(30):
            db.session.add(_book(f'Tie {i:02d}', author, cat, f'97855{i:08d}'))
        Setting.set('page_size', '5')
        db.session.commit()
        search_cache.invalidate_all()
    seen = []
    for page in range(1, 8):
        seen += [t for t in _titles(client.get(f'/catalogue?q=tie&sort=author&page={page}').get_data(as_text=True))
                 if t.startswith('Tie ')]
    assert len(seen) == 30 and len(set(seen)) == 30             # nothing repeated, nothing skipped


def test_pagination_controls_render_and_page_two_works(client, app):
    with app.app_context():
        cat, author = Category.query.first(), Author.query.first()
        for i in range(12):
            db.session.add(_book(f'Pg {i:02d}', author, cat, f'97866{i:08d}'))
        Setting.set('page_size', '5')
        db.session.commit()
        search_cache.invalidate_all()
    p1 = client.get('/catalogue?q=pg').get_data(as_text=True)
    p2 = client.get('/catalogue?q=pg&page=2').get_data(as_text=True)
    p3 = client.get('/catalogue?q=pg&page=3').get_data(as_text=True)
    assert 'Pg 00' in p1 and 'Pg 05' in p2 and 'Pg 10' in p3 and 'Pg 00' not in p2
    assert 'page=2' in p1 and 'page=3' in p2 and '12' in p1             # links and the total are rendered


def test_a_page_past_the_end_and_a_bad_page_number_are_harmless(client, app):
    assert client.get('/catalogue?page=9999').status_code == 200
    assert client.get('/catalogue?page=0').status_code == 200
    assert client.get('/catalogue?page=-3').status_code == 200
    assert client.get('/catalogue?page=abc').status_code == 200


def test_staff_book_list_uses_the_same_search(librarian_client, app):
    _shelf(app)
    page = librarian_client.get('/books?q=abe+author').get_data(as_text=True)
    assert 'Alpha Guide' in page and 'Zebra Handbook' not in page


def test_page_size_above_the_pagination_cap_is_rejected(admin_client, app):
    admin_client.post('/admin/settings', data={'page_size': '150'})
    with app.app_context():
        assert Setting.get_int('page_size') == 25
