"""Tests for Author and Category management."""
from app.models.author import Author
from app.models.category import Category
from app.models.book import Book


def test_add_author(librarian_client, app):
    response = librarian_client.post('/authors/add', data={
        'name': 'Donald Knuth',
        'bio': 'Author of The Art of Computer Programming',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Donald Knuth' in response.data
    assert b'added' in response.data

    with app.app_context():
        author = Author.query.filter_by(name='Donald Knuth').first()
        assert author is not None


def test_cannot_delete_author_with_books(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        author_id = book.author_id

    response = librarian_client.post(f'/authors/{author_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'Cannot delete author' in response.data or b'book' in response.data

    with app.app_context():
        assert app.extensions['sqlalchemy'].session.get(Author, author_id) is not None


def test_delete_author_without_books(librarian_client, app):
    with app.app_context():
        author = Author(name='Unassigned Author', bio='No books')
        app.extensions['sqlalchemy'].session.add(author)
        app.extensions['sqlalchemy'].session.commit()
        author_id = author.id

    response = librarian_client.post(f'/authors/{author_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'deleted' in response.data


def test_add_category(librarian_client, app):
    response = librarian_client.post('/categories/add', data={
        'name': 'Cloud Computing',
        'description': 'Distributed cloud systems',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Cloud Computing' in response.data
    assert b'added' in response.data

    with app.app_context():
        cat = Category.query.filter_by(name='Cloud Computing').first()
        assert cat is not None


def test_cannot_delete_category_with_books(librarian_client, app):
    with app.app_context():
        book = Book.query.first()
        cat_id = book.category_id

    response = librarian_client.post(f'/categories/{cat_id}/delete', follow_redirects=True)
    assert response.status_code == 200
    assert b'Cannot delete category' in response.data or b'book' in response.data
