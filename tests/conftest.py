"""Pytest fixtures for Library Management System."""
import sys
import os
import tempfile
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.member import Member
from app.models.author import Author
from app.models.category import Category
from app.models.book import Book
from app.models.setting import Setting
from app.services.compression import compress_text, compress_bytes
from app.services.cache import search_cache


@pytest.fixture
def app():
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, 'test_library.db')
    upload_dir = os.path.join(temp_dir, 'uploads')
    backup_dir = os.path.join(temp_dir, 'backups')
    os.makedirs(upload_dir, exist_ok=True)
    os.makedirs(backup_dir, exist_ok=True)

    class CustomTestConfig:
        TESTING = True
        SECRET_KEY = 'test-secret-key'
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{db_path}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        WTF_CSRF_ENABLED = False
        UPLOAD_FOLDER = upload_dir
        BACKUP_FOLDER = backup_dir
        ITEMS_PER_PAGE = 10

    app = create_app(CustomTestConfig)

    with app.app_context():
        db.create_all()
        Setting.seed_defaults()

        # Create base test users
        admin = User(username='testadmin', email='admin@test.com', role='admin')
        admin.set_password('pass123')
        db.session.add(admin)

        librarian = User(username='testlibrarian', email='librarian@test.com', role='librarian')
        librarian.set_password('pass123')
        db.session.add(librarian)

        member_user = User(username='testmember', email='member@test.com', role='member')
        member_user.set_password('pass123')
        db.session.add(member_user)
        db.session.flush()

        member = Member(user_id=member_user.id, name='Test Member',
                        email='member@test.com', phone='555-1234',
                        status='active', loan_limit=5)
        db.session.add(member)

        # Base author and category
        author = Author(name='Martin Fowler', bio='Software architect')
        category = Category(name='Software Engineering', description='Software design')
        db.session.add_all([author, category])
        db.session.flush()

        # Base book
        desc = "A foundational book on software architecture and patterns."
        book = Book(
            title='Patterns of Enterprise Application Architecture',
            isbn='9780321127426',
            author_id=author.id,
            category_id=category.id,
            publisher='Addison-Wesley',
            edition='1st',
            publication_year=2002,
            description_compressed=compress_text(desc),
            description_raw_size=len(desc.encode('utf-8')),
            cover_compressed=compress_bytes(b'FAKE_COVER_JPEG'),
            cover_raw_size=len(b'FAKE_COVER_JPEG'),
            quantity=5,
            available_quantity=5,
        )
        db.session.add(book)
        db.session.commit()
        search_cache.invalidate_all()

    yield app

    with app.app_context():
        db.session.remove()
        db.engine.dispose()

    # Clean up temp files
    for root, dirs, files in os.walk(temp_dir, topdown=False):
        for name in files:
            try:
                os.remove(os.path.join(root, name))
            except OSError:
                pass
        for name in dirs:
            try:
                os.rmdir(os.path.join(root, name))
            except OSError:
                pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_client(app, client):
    client.post('/login', data={'username': 'testadmin', 'password': 'pass123'}, follow_redirects=True)
    return client


@pytest.fixture
def librarian_client(app, client):
    client.post('/login', data={'username': 'testlibrarian', 'password': 'pass123'}, follow_redirects=True)
    return client


@pytest.fixture
def member_client(app, client):
    client.post('/login', data={'username': 'testmember', 'password': 'pass123'}, follow_redirects=True)
    return client
