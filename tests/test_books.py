"""Tests for Book CRUD, catalogue, cover serving, and availability."""
from app.models.book import Book
from app.models.author import Author
from app.models.category import Category


def test_public_catalogue_access(client):
    response = client.get('/catalogue')
    assert response.status_code == 200
    assert b'Patterns of Enterprise Application Architecture' in response.data


def test_book_detail_page(client, app):
    with app.app_context():
        book = Book.query.first()
        book_id = book.id
    response = client.get(f'/book/{book_id}')
    assert response.status_code == 200
    assert b'Patterns of Enterprise Application Architecture' in response.data
    assert b'Compression' in response.data or b'saved' in response.data or b'KB' in response.data


def test_book_cover_serving(client, app):
    with app.app_context():
        book = Book.query.first()
        book_id = book.id
    response = client.get(f'/book/{book_id}/cover')
    assert response.status_code == 200
    assert response.data == b'FAKE_COVER_JPEG'


def test_add_book_staff(librarian_client, app):
    with app.app_context():
        author = Author.query.first()
        category = Category.query.first()
        author_id = author.id
        category_id = category.id

    response = librarian_client.post('/books/add', data={
        'title': 'Test New Book',
        'isbn': '9781111111111',
        'author_id': author_id,
        'category_id': category_id,
        'publisher': 'Test Publisher',
        'edition': '1st Edition',
        'publication_year': 2024,
        'quantity': 3,
        'description': 'This is a test book description that will be compressed.',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'added successfully' in response.data

    with app.app_context():
        b = Book.query.filter_by(isbn='9781111111111').first()
        assert b is not None
        assert b.title == 'Test New Book'
        assert b.available_quantity == 3
        # Check compression
        assert b.description == 'This is a test book description that will be compressed.'
        assert len(b.description_compressed) > 0


def test_duplicate_isbn_prevention(librarian_client, app):
    with app.app_context():
        author = Author.query.first()
        category = Category.query.first()
        existing_isbn = Book.query.first().isbn

    response = librarian_client.post('/books/add', data={
        'title': 'Duplicate ISBN Book',
        'isbn': existing_isbn,
        'author_id': author.id,
        'category_id': category.id,
        'quantity': 1,
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'already exists' in response.data


def test_edit_book(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        book_id = book.id
        author_id = book.author_id
        category_id = book.category_id

    response = librarian_client.post(f'/books/{book_id}/edit', data={
        'title': 'Updated Book Title',
        'isbn': '9780321127426',
        'author_id': author_id,
        'category_id': category_id,
        'publisher': 'Addison-Wesley Updated',
        'edition': '2nd',
        'publication_year': 2005,
        'quantity': 6,
        'description': 'Updated description',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'updated' in response.data

    with app.app_context():
        b = Book.query.get(book_id)
        assert b.title == 'Updated Book Title'
        assert b.quantity == 6


def test_delete_book(admin_client, app):
    with app.app_context():
        book = Book.query.first()
        book_id = book.id

    response = admin_client.post(f'/books/{book_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'deleted' in response.data

    with app.app_context():
        assert Book.query.get(book_id) is None
