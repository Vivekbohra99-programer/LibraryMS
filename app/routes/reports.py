"""Reports and export routes."""
from flask import Blueprint, render_template, request, Response, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.book import Book
from app.models.member import Member
from app.models.transaction import Transaction
from app.models.fine import Fine
from app.models.activity_log import ActivityLog
from app.models.setting import Setting
from app.services.export import to_csv, to_excel
from functools import wraps

reports_bp = Blueprint('reports', __name__)


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_staff:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@reports_bp.route('/reports')
@login_required
@staff_required
def index():
    return render_template('reports/index.html')


@reports_bp.route('/reports/books')
@login_required
@staff_required
def books_report():
    page = request.args.get('page', 1, type=int)
    pagination = Book.query.order_by(Book.title).paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('reports/books.html', pagination=pagination, books=pagination.items)


@reports_bp.route('/reports/members')
@login_required
@staff_required
def members_report():
    page = request.args.get('page', 1, type=int)
    pagination = Member.query.order_by(Member.name).paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('reports/members.html', pagination=pagination, members=pagination.items)


@reports_bp.route('/reports/transactions')
@login_required
@staff_required
def transactions_report():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    query = Transaction.query
    if status:
        query = query.filter_by(status=status)
    pagination = query.order_by(Transaction.created_at.desc()).paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('reports/transactions.html', pagination=pagination,
                           transactions=pagination.items, status=status)


@reports_bp.route('/reports/fines')
@login_required
@staff_required
def fines_report():
    page = request.args.get('page', 1, type=int)
    paid = request.args.get('paid', '')
    query = Fine.query
    if paid == 'yes':
        query = query.filter_by(paid=True)
    elif paid == 'no':
        query = query.filter_by(paid=False)
    pagination = query.order_by(Fine.created_at.desc()).paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('reports/fines.html', pagination=pagination,
                           fines=pagination.items, paid=paid)


@reports_bp.route('/reports/activity')
@login_required
@staff_required
def activity_report():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    query = ActivityLog.query
    if search:
        query = query.filter(
            db.or_(ActivityLog.action.ilike(f'%{search}%'),
                   ActivityLog.details.ilike(f'%{search}%')))
    pagination = query.order_by(ActivityLog.created_at.desc()).paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('reports/activity.html', pagination=pagination,
                           logs=pagination.items, search=search)


# ---------- Exports ----------

def _export(headers, rows, name, fmt):
    if fmt == 'excel':
        data = to_excel(headers, rows, name)
        return Response(data, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={'Content-Disposition': f'attachment; filename={name}.xlsx'})
    else:
        data = to_csv(headers, rows)
        return Response(data, mimetype='text/csv',
                        headers={'Content-Disposition': f'attachment; filename={name}.csv'})


@reports_bp.route('/reports/export/books')
@login_required
@staff_required
def export_books():
    fmt = request.args.get('format', 'csv')
    books = Book.query.order_by(Book.id).all()
    headers = ['ID', 'Title', 'ISBN', 'Author', 'Category', 'Quantity', 'Available', 'Year']
    rows = [(b.id, b.title, b.isbn or '', b.author.name if b.author else '',
             b.category.name if b.category else '', b.quantity, b.available_quantity,
             b.publication_year or '') for b in books]
    return _export(headers, rows, 'books_report', fmt)


@reports_bp.route('/reports/export/members')
@login_required
@staff_required
def export_members():
    fmt = request.args.get('format', 'csv')
    members = Member.query.order_by(Member.id).all()
    headers = ['ID', 'Name', 'Email', 'Phone', 'Status', 'Loan Limit', 'Registered']
    rows = [(m.id, m.name, m.email, m.phone, m.status, m.loan_limit,
             m.registration_date.strftime('%Y-%m-%d') if m.registration_date else '') for m in members]
    return _export(headers, rows, 'members_report', fmt)


@reports_bp.route('/reports/export/transactions')
@login_required
@staff_required
def export_transactions():
    fmt = request.args.get('format', 'csv')
    status = request.args.get('status', '')
    query = Transaction.query
    if status:
        query = query.filter_by(status=status)
    txns = query.order_by(Transaction.id).all()
    headers = ['ID', 'Book', 'Member', 'Issue Date', 'Due Date', 'Return Date', 'Status', 'Renewals']
    rows = [(t.id, t.book.title if t.book else '', t.member.name if t.member else '',
             t.issue_date.strftime('%Y-%m-%d') if t.issue_date else '',
             t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
             t.return_date.strftime('%Y-%m-%d') if t.return_date else '',
             t.status, t.renewal_count) for t in txns]
    return _export(headers, rows, 'transactions_report', fmt)


@reports_bp.route('/reports/export/fines')
@login_required
@staff_required
def export_fines():
    fmt = request.args.get('format', 'csv')
    fines = Fine.query.order_by(Fine.id).all()
    headers = ['ID', 'Transaction ID', 'Member', 'Amount', 'Paid', 'Paid Date', 'Created']
    rows = [(f.id, f.transaction_id, f.member.name if f.member else '',
             f.amount, 'Yes' if f.paid else 'No',
             f.paid_date.strftime('%Y-%m-%d') if f.paid_date else '',
             f.created_at.strftime('%Y-%m-%d') if f.created_at else '') for f in fines]
    return _export(headers, rows, 'fines_report', fmt)


@reports_bp.route('/reports/export/activity')
@login_required
@staff_required
def export_activity():
    fmt = request.args.get('format', 'csv')
    logs = ActivityLog.query.order_by(ActivityLog.id).all()
    headers = ['ID', 'User', 'Action', 'Details', 'IP', 'Timestamp']
    rows = [(l.id, l.user.username if l.user else '',
             l.action, l.details, l.ip_address,
             l.created_at.strftime('%Y-%m-%d %H:%M') if l.created_at else '') for l in logs]
    return _export(headers, rows, 'activity_report', fmt)
