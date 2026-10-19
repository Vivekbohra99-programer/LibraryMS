"""Transaction routes – issue, return, renewal."""
from datetime import datetime, timedelta, timezone
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.book import Book
from app.models.member import Member
from app.models.transaction import Transaction
from app.models.fine import Fine
from app.models.setting import Setting
from app.services.cache import search_cache
from app.services.activity import log_activity
from app.services.notifications import notify
from functools import wraps

transactions_bp = Blueprint('transactions', __name__)


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_staff:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@transactions_bp.route('/transactions')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    status = request.args.get('status', '')
    search = request.args.get('q', '').strip()

    if current_user.is_member_role:
        member = Member.query.filter_by(user_id=current_user.id).first()
        if not member:
            return render_template('transactions/index.html', pagination=None,
                                   transactions=[], status=status, search=search)
        query = Transaction.query.filter_by(member_id=member.id)
    else:
        query = Transaction.query

    if status == 'overdue':
        # not a stored status: loans still out and past their due date
        query = query.filter(Transaction.status == 'issued',
                             Transaction.due_date < datetime.now(timezone.utc).replace(tzinfo=None))
    elif status:
        query = query.filter_by(status=status)
    if search:
        query = query.join(Book).join(Member).filter(
            db.or_(Book.title.ilike(f'%{search}%'),
                   Member.name.ilike(f'%{search}%')))

    query = query.order_by(Transaction.created_at.desc())
    pagination = query.paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('transactions/index.html', pagination=pagination,
                           transactions=pagination.items, status=status, search=search,
                           fine_rate=Setting.get_float('fine_rate', 2.0),
                           loan_days=Setting.get_int('loan_duration', 14))


@transactions_bp.route('/transactions/issue', methods=['GET', 'POST'])
@login_required
@staff_required
def issue():
    if request.method == 'POST':
        book_id = request.form.get('book_id', type=int)
        member_id = request.form.get('member_id', type=int)
        loan_days = Setting.get_int('loan_duration', 14)

        book = db.session.get(Book, book_id) if book_id else None
        member = db.session.get(Member, member_id) if member_id else None

        errors = []
        if not book:
            errors.append('Book not found.')
        elif not book.is_available:
            errors.append(f'"{book.title}" has no available copies.')
        if not member:
            errors.append('Member not found.')
        elif not member.is_active:
            errors.append(f'Member "{member.name}" is not active (status: {member.status}).')
        elif not member.can_borrow:
            errors.append(f'Member "{member.name}" has reached their loan limit ({member.loan_limit}).')

        if errors:
            for e in errors:
                flash(e, 'danger')
        else:
            now = datetime.now(timezone.utc)
            due = now + timedelta(days=loan_days)
            txn = Transaction(
                book_id=book.id, member_id=member.id,
                issue_date=now, due_date=due,
                status='issued', issued_by=current_user.id
            )
            book.available_quantity -= 1
            db.session.add(txn)
            db.session.commit()
            search_cache.invalidate_all()
            log_activity(current_user.id, 'book_issue',
                         f'Issued "{book.title}" to {member.name}')
            if member.user_id:
                notify(member.user_id,
                       f'Book "{book.title}" has been issued to you. Due: {due.strftime("%Y-%m-%d")}',
                       type='success', link=url_for('transactions.index'))
            flash(f'Book "{book.title}" issued to {member.name}. Due: {due.strftime("%Y-%m-%d")}',
                  'success')
            return redirect(url_for('transactions.index'))

    books = Book.query.filter(Book.available_quantity > 0).order_by(Book.title).all()
    members = Member.query.filter_by(status='active').order_by(Member.name).all()
    return render_template('transactions/issue.html', books=books, members=members,
                           loan_days=Setting.get_int('loan_duration', 14),
                           max_renewals=Setting.get_int('max_renewals', 2))


@transactions_bp.route('/transactions/<int:txn_id>/return', methods=['GET', 'POST'])
@login_required
@staff_required
def return_book(txn_id):
    txn = db.session.get(Transaction, txn_id)
    if not txn or txn.status != 'issued':
        flash('Transaction not found or already returned.', 'danger')
        return redirect(url_for('transactions.index'))

    fine_rate = Setting.get_float('fine_rate', 2.0)
    overdue_days = txn.overdue_days
    fine_amount = round(overdue_days * fine_rate, 2) if overdue_days > 0 else 0

    if request.method == 'POST':
        now = datetime.now(timezone.utc)
        txn.return_date = now
        txn.status = 'returned'
        txn.returned_by = current_user.id
        txn.book.available_quantity += 1

        if fine_amount > 0:
            fine = Fine(transaction_id=txn.id, member_id=txn.member_id,
                        amount=fine_amount)
            db.session.add(fine)

        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'book_return',
                     f'Returned "{txn.book.title}" from {txn.member.name}'
                     + (f' (fine: ₹{fine_amount})' if fine_amount else ''))

        member = txn.member
        if member.user_id:
            msg = f'Book "{txn.book.title}" has been returned.'
            if fine_amount > 0:
                msg += f' A fine of ₹{fine_amount} has been applied.'
            notify(member.user_id, msg, type='info',
                   link=url_for('transactions.index'))

        flash(f'Book returned.' + (f' Fine: ₹{fine_amount}' if fine_amount else ''), 'success')
        return redirect(url_for('transactions.index'))

    return render_template('transactions/return.html', txn=txn,
                           overdue_days=overdue_days, fine_amount=fine_amount)


@transactions_bp.route('/transactions/<int:txn_id>/renew', methods=['POST'])
@login_required
def renew(txn_id):
    txn = db.session.get(Transaction, txn_id)
    if not txn or txn.status != 'issued':
        flash('Transaction not found or not eligible for renewal.', 'danger')
        return redirect(url_for('transactions.index'))

    # Permission check: staff or own transaction
    if current_user.is_member_role:
        member = Member.query.filter_by(user_id=current_user.id).first()
        if not member or txn.member_id != member.id:
            abort(403)

    max_renewals = Setting.get_int('max_renewals', 2)
    loan_days = Setting.get_int('loan_duration', 14)

    if txn.renewal_count >= max_renewals:
        flash(f'Maximum renewals ({max_renewals}) reached.', 'danger')
        return redirect(url_for('transactions.index'))

    if txn.is_overdue:
        flash('Cannot renew an overdue book. Please return it first.', 'danger')
        return redirect(url_for('transactions.index'))

    txn.due_date = txn.due_date + timedelta(days=loan_days)
    txn.renewal_count += 1
    db.session.commit()
    search_cache.invalidate_all()
    log_activity(current_user.id, 'book_renew',
                 f'Renewed "{txn.book.title}" for {txn.member.name} (renewal #{txn.renewal_count})')

    if txn.member.user_id:
        notify(txn.member.user_id,
               f'Book "{txn.book.title}" renewed. New due date: {txn.due_date.strftime("%Y-%m-%d")}',
               type='success', link=url_for('transactions.index'))

    flash(f'Book renewed. New due date: {txn.due_date.strftime("%Y-%m-%d")}', 'success')
    return redirect(url_for('transactions.index'))
