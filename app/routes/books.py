"""Book routes – CRUD, catalogue, cover serving, search/filter/sort/pagination."""
import base64
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, Response, abort)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.book import Book
from app.models.author import Author
from app.models.category import Category
from app.models.setting import Setting
from app.services.compression import compress_text, decompress_bytes, process_cover_image
from app.services.cache import search_cache
from app.services.catalogue import search_books, filter_lists, MAX_QUERY_CHARS
from app.services.activity import log_activity
from functools import wraps

books_bp = Blueprint('books', __name__)


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_staff:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------- Public catalogue ----------

@books_bp.route('/catalogue')
def catalogue():
    page = request.args.get('page', 1, type=int)
    per_page = Setting.get_int('page_size', 25)
    search = request.args.get('q', '').strip()[:MAX_QUERY_CHARS]
    author_id = request.args.get('author', type=int)
    category_id = request.args.get('category', type=int)
    availability = request.args.get('availability', '')
    sort = request.args.get('sort', 'title')

    # Q17: the filter/sort/count result is cached, the BLOB columns stay deferred, rows are read fresh
    pagination = search_books(search, author_id, category_id, availability, sort, page, per_page)
    authors, categories = filter_lists()

    return render_template('books/catalogue.html', pagination=pagination,
                           books=pagination.items, authors=authors,
                           categories=categories, search=search,
                           author_id=author_id, category_id=category_id,
                           availability=availability, sort=sort,
                           per_page=per_page)


@books_bp.route('/book/<int:book_id>')
def detail(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        abort(404)
    return render_template('books/detail.html', book=book)


@books_bp.route('/book/<int:book_id>/cover')
def cover(book_id):
    """Serve the compressed cover image – decompresses on demand (Q17)."""
    blob = db.session.query(Book.cover_compressed).filter(Book.id == book_id).scalar()
    if not blob:
        abort(404)
    return Response(decompress_bytes(blob), mimetype='image/jpeg',
                    headers={'Cache-Control': 'public, max-age=3600'})


# ---------- Staff CRUD ----------

@books_bp.route('/books')
@login_required
@staff_required
def index():
    page = request.args.get('page', 1, type=int)
    per_page = Setting.get_int('page_size', 25)
    search = request.args.get('q', '').strip()[:MAX_QUERY_CHARS]
    author_id = request.args.get('author', type=int)
    category_id = request.args.get('category', type=int)
    sort = request.args.get('sort', 'title')

    pagination = search_books(search, author_id, category_id, '', sort, page, per_page)
    authors, categories = filter_lists()

    return render_template('books/index.html', pagination=pagination,
                           books=pagination.items, authors=authors,
                           categories=categories, search=search,
                           author_id=author_id, category_id=category_id,
                           sort=sort, per_page=per_page)


@books_bp.route('/books/add', methods=['GET', 'POST'])
@login_required
@staff_required
def add():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        isbn = request.form.get('isbn', '').strip() or None
        author_id = request.form.get('author_id', type=int)
        category_id = request.form.get('category_id', type=int)
        publisher = request.form.get('publisher', '').strip()
        edition = request.form.get('edition', '').strip()
        publication_year = request.form.get('publication_year', type=int)
        description = request.form.get('description', '').strip()
        quantity = request.form.get('quantity', 1, type=int)

        errors = []
        if not title:
            errors.append('Title is required.')
        if not author_id:
            errors.append('Author is required.')
        if not category_id:
            errors.append('Category is required.')
        if isbn and Book.query.filter_by(isbn=isbn).first():
            errors.append('A book with this ISBN already exists.')
        if quantity < 1:
            errors.append('Quantity must be at least 1.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            authors = Author.query.order_by(Author.name).all()
            categories = Category.query.order_by(Category.name).all()
            return render_template('books/form.html', book=None, authors=authors,
                                   categories=categories, action='Add')

        # Q17 Feature 1: compress description
        desc_compressed = compress_text(description)
        desc_raw_size = len(description.encode('utf-8'))

        book = Book(
            title=title, isbn=isbn, author_id=author_id, category_id=category_id,
            publisher=publisher, edition=edition, publication_year=publication_year,
            description_compressed=desc_compressed, description_raw_size=desc_raw_size,
            quantity=quantity, available_quantity=quantity,
        )

        # Handle cover upload
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            try:
                max_dim = Setting.get_int('max_image_dimension', 800)
                quality = Setting.get_int('compression_quality', 85)
                compressed, raw_size = process_cover_image(cover_file, max_dim, quality,
                                                            Setting.get_int('max_upload_size_mb', 5))
                book.cover_compressed = compressed
                book.cover_raw_size = raw_size
            except ValueError as e:
                flash(str(e), 'warning')

        db.session.add(book)
        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'book_add', f'Added book: {title}',
                     request.remote_addr or '')
        flash(f'Book "{title}" added successfully.', 'success')
        return redirect(url_for('books.index'))

    authors = Author.query.order_by(Author.name).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template('books/form.html', book=None, authors=authors,
                           categories=categories, action='Add')


@books_bp.route('/books/<int:book_id>/edit', methods=['GET', 'POST'])
@login_required
@staff_required
def edit(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        abort(404)

    if request.method == 'POST':
        book.title = request.form.get('title', '').strip()
        book.isbn = request.form.get('isbn', '').strip() or None
        book.author_id = request.form.get('author_id', type=int)
        book.category_id = request.form.get('category_id', type=int)
        book.publisher = request.form.get('publisher', '').strip()
        book.edition = request.form.get('edition', '').strip()
        book.publication_year = request.form.get('publication_year', type=int)
        description = request.form.get('description', '').strip()
        new_qty = max(request.form.get('quantity', 1, type=int) or 0, 0)

        if not book.title:
            flash('Title is required.', 'danger')
            authors = Author.query.order_by(Author.name).all()
            categories = Category.query.order_by(Category.name).all()
            return render_template('books/form.html', book=book, authors=authors,
                                   categories=categories, action='Edit')

        # Check ISBN uniqueness
        if book.isbn:
            dup = Book.query.filter(Book.isbn == book.isbn, Book.id != book.id).first()
            if dup:
                flash('A book with this ISBN already exists.', 'danger')
                authors = Author.query.order_by(Author.name).all()
                categories = Category.query.order_by(Category.name).all()
                return render_template('books/form.html', book=book, authors=authors,
                                       categories=categories, action='Edit')

        # Update description compressed
        book.description_compressed = compress_text(description)
        book.description_raw_size = len(description.encode('utf-8'))
        book._description_cache = None

        # Adjust available quantity proportionally
        old_qty = book.quantity
        issued = old_qty - book.available_quantity
        book.quantity = max(new_qty, issued)
        book.available_quantity = book.quantity - issued

        # Handle cover upload
        cover_file = request.files.get('cover')
        if cover_file and cover_file.filename:
            try:
                max_dim = Setting.get_int('max_image_dimension', 800)
                quality = Setting.get_int('compression_quality', 85)
                compressed, raw_size = process_cover_image(cover_file, max_dim, quality,
                                                            Setting.get_int('max_upload_size_mb', 5))
                book.cover_compressed = compressed
                book.cover_raw_size = raw_size
                book._cover_cache = None
            except ValueError as e:
                flash(str(e), 'warning')

        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'book_edit', f'Edited book: {book.title}',
                     request.remote_addr or '')
        flash(f'Book "{book.title}" updated.', 'success')
        if new_qty < issued:
            flash(f'{issued} cop{"y is" if issued == 1 else "ies are"} still on loan, so the quantity stays at '
                  f'{book.quantity} until {"it is" if issued == 1 else "they are"} returned.', 'info')
        return redirect(url_for('books.detail', book_id=book.id))

    authors = Author.query.order_by(Author.name).all()
    categories = Category.query.order_by(Category.name).all()
    return render_template('books/form.html', book=book, authors=authors,
                           categories=categories, action='Edit')


@books_bp.route('/books/<int:book_id>/delete', methods=['POST'])
@login_required
@staff_required
def delete(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        abort(404)
    if book.transactions.filter_by(status='issued').count() > 0:
        flash('Cannot delete a book with active loans.', 'danger')
        return redirect(url_for('books.detail', book_id=book.id))
    # Returned loans still point at this book. Deleting it would either crash on the NOT NULL
    # foreign key or erase the borrowing history, so refuse and say how to retire the title instead.
    history = book.transactions.count()
    if history:
        flash(f'"{book.title}" has {history} loan record{"" if history == 1 else "s"} in its history, '
              'so it cannot be deleted. To take it off the shelf, set its quantity to 0 on the Edit page.',
              'danger')
        return redirect(url_for('books.detail', book_id=book.id))
    title = book.title
    db.session.delete(book)
    db.session.commit()
    search_cache.invalidate_all()
    log_activity(current_user.id, 'book_delete', f'Deleted book: {title}',
                 request.remote_addr or '')
    flash(f'Book "{title}" deleted.', 'success')
    return redirect(url_for('books.index'))


@books_bp.route('/books/<int:book_id>/delete-cover', methods=['POST'])
@login_required
@staff_required
def delete_cover(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        abort(404)
    book.cover_compressed = b''
    book.cover_raw_size = 0
    book._cover_cache = None
    db.session.commit()
    search_cache.invalidate_all()
    flash('Cover image removed.', 'success')
    return redirect(url_for('books.edit', book_id=book.id))
