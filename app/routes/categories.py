"""Category routes – CRUD."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.category import Category
from app.models.setting import Setting
from app.services.cache import search_cache
from app.services.activity import log_activity
from functools import wraps

categories_bp = Blueprint('categories', __name__)


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_staff:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@categories_bp.route('/categories')
@login_required
@staff_required
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    query = Category.query
    if search:
        query = query.filter(Category.name.ilike(f'%{search}%'))
    query = query.order_by(Category.name)
    pagination = query.paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('categories/index.html', pagination=pagination,
                           categories=pagination.items, search=search)


@categories_bp.route('/categories/add', methods=['GET', 'POST'])
@login_required
@staff_required
def add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        if not name:
            flash('Category name is required.', 'danger')
            return render_template('categories/form.html', category=None, action='Add')
        if Category.query.filter_by(name=name).first():
            flash('A category with this name already exists.', 'danger')
            return render_template('categories/form.html', category=None, action='Add')
        cat = Category(name=name, description=description)
        db.session.add(cat)
        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'category_add', f'Added category: {name}')
        flash(f'Category "{name}" added.', 'success')
        return redirect(url_for('categories.index'))
    return render_template('categories/form.html', category=None, action='Add')


@categories_bp.route('/categories/<int:cat_id>')
@login_required
@staff_required
def view(cat_id):
    cat = db.session.get(Category, cat_id)
    if not cat:
        abort(404)
    page = request.args.get('page', 1, type=int)
    books = cat.books.paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('categories/view.html', category=cat, pagination=books,
                           books=books.items)


@categories_bp.route('/categories/<int:cat_id>/edit', methods=['GET', 'POST'])
@login_required
@staff_required
def edit(cat_id):
    cat = db.session.get(Category, cat_id)
    if not cat:
        abort(404)
    if request.method == 'POST':
        cat.name = request.form.get('name', '').strip()
        cat.description = request.form.get('description', '').strip()
        if not cat.name:
            flash('Category name is required.', 'danger')
            return render_template('categories/form.html', category=cat, action='Edit')
        dup = Category.query.filter(Category.name == cat.name, Category.id != cat.id).first()
        if dup:
            flash('A category with this name already exists.', 'danger')
            return render_template('categories/form.html', category=cat, action='Edit')
        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'category_edit', f'Edited category: {cat.name}')
        flash(f'Category "{cat.name}" updated.', 'success')
        return redirect(url_for('categories.view', cat_id=cat.id))
    return render_template('categories/form.html', category=cat, action='Edit')


@categories_bp.route('/categories/<int:cat_id>/delete', methods=['POST'])
@login_required
@staff_required
def delete(cat_id):
    cat = db.session.get(Category, cat_id)
    if not cat:
        abort(404)
    if cat.books.count() > 0:
        flash('Cannot delete category with existing books.', 'danger')
        return redirect(url_for('categories.view', cat_id=cat.id))
    name = cat.name
    db.session.delete(cat)
    db.session.commit()
    search_cache.invalidate_all()
    log_activity(current_user.id, 'category_delete', f'Deleted category: {name}')
    flash(f'Category "{name}" deleted.', 'success')
    return redirect(url_for('categories.index'))
