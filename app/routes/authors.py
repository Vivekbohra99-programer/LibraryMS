"""Author routes – CRUD."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.author import Author
from app.models.setting import Setting
from app.services.cache import search_cache
from app.services.activity import log_activity
from functools import wraps

authors_bp = Blueprint('authors', __name__)


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_staff:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@authors_bp.route('/authors')
@login_required
@staff_required
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    query = Author.query
    if search:
        query = query.filter(Author.name.ilike(f'%{search}%'))
    query = query.order_by(Author.name)
    pagination = query.paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('authors/index.html', pagination=pagination,
                           authors=pagination.items, search=search)


@authors_bp.route('/authors/add', methods=['GET', 'POST'])
@login_required
@staff_required
def add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        bio = request.form.get('bio', '').strip()
        if not name:
            flash('Author name is required.', 'danger')
            return render_template('authors/form.html', author=None, action='Add')
        author = Author(name=name, bio=bio)
        db.session.add(author)
        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'author_add', f'Added author: {name}')
        flash(f'Author "{name}" added.', 'success')
        return redirect(url_for('authors.index'))
    return render_template('authors/form.html', author=None, action='Add')


@authors_bp.route('/authors/<int:author_id>')
@login_required
@staff_required
def view(author_id):
    author = db.session.get(Author, author_id)
    if not author:
        abort(404)
    page = request.args.get('page', 1, type=int)
    books = author.books.paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('authors/view.html', author=author, pagination=books,
                           books=books.items)


@authors_bp.route('/authors/<int:author_id>/edit', methods=['GET', 'POST'])
@login_required
@staff_required
def edit(author_id):
    author = db.session.get(Author, author_id)
    if not author:
        abort(404)
    if request.method == 'POST':
        author.name = request.form.get('name', '').strip()
        author.bio = request.form.get('bio', '').strip()
        if not author.name:
            flash('Author name is required.', 'danger')
            return render_template('authors/form.html', author=author, action='Edit')
        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'author_edit', f'Edited author: {author.name}')
        flash(f'Author "{author.name}" updated.', 'success')
        return redirect(url_for('authors.view', author_id=author.id))
    return render_template('authors/form.html', author=author, action='Edit')


@authors_bp.route('/authors/<int:author_id>/delete', methods=['POST'])
@login_required
@staff_required
def delete(author_id):
    author = db.session.get(Author, author_id)
    if not author:
        abort(404)
    if author.books.count() > 0:
        flash('Cannot delete author with existing books. Remove or reassign books first.', 'danger')
        return redirect(url_for('authors.view', author_id=author.id))
    name = author.name
    db.session.delete(author)
    db.session.commit()
    search_cache.invalidate_all()
    log_activity(current_user.id, 'author_delete', f'Deleted author: {name}')
    flash(f'Author "{name}" deleted.', 'success')
    return redirect(url_for('authors.index'))
