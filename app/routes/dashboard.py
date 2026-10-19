"""Dashboard routes – role-specific dashboards."""
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.book import Book
from app.models.member import Member
from app.models.transaction import Transaction
from app.models.fine import Fine
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.services.cache import search_cache
from app.services.analytics import dashboard_analytics
from app.models.setting import Setting
from app.services.memory import get_process_memory, get_python_allocation, get_db_size
from datetime import datetime, timedelta, timezone

dashboard_bp = Blueprint('dashboard', __name__)


def _cache_get(key, fn):
    """Helper: check cache, call fn on miss, store result."""
    val = search_cache.get(key)
    if val is not None:
        return val
    val = fn()
    search_cache.set(key, val)
    return val


@dashboard_bp.route('/dashboard')
@login_required
def index():
    if current_user.is_admin:
        return admin_dashboard()
    elif current_user.is_librarian:
        return librarian_dashboard()
    else:
        return member_dashboard()


def admin_dashboard():
    now = datetime.now(timezone.utc)
    stats = {
        'total_books': _cache_get('dash:total_books', lambda: Book.query.count()),
        'total_copies': _cache_get('dash:total_copies',
            lambda: db.session.query(func.coalesce(func.sum(Book.quantity), 0)).scalar()),
        'available_copies': _cache_get('dash:avail_copies',
            lambda: db.session.query(func.coalesce(func.sum(Book.available_quantity), 0)).scalar()),
        'issued_books': _cache_get('dash:issued',
            lambda: Transaction.query.filter_by(status='issued').count()),
        'overdue_books': Transaction.query.filter(
            Transaction.status == 'issued', Transaction.due_date < now).count(),
        'total_members': _cache_get('dash:total_members', lambda: Member.query.count()),
        'active_members': _cache_get('dash:active_members',
            lambda: Member.query.filter_by(status='active').count()),
        'suspended_members': Member.query.filter_by(status='suspended').count(),
        'total_fines': db.session.query(func.coalesce(func.sum(Fine.amount), 0)).scalar(),
        'paid_fines': db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            Fine.paid == True).scalar() or 0,
        'unpaid_fines': db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            Fine.paid == False).scalar() or 0,
    }
    recent_txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
    recent_activity = ActivityLog.query.order_by(ActivityLog.created_at.desc()).limit(10).all()
    due_soon = Transaction.query.filter(
        Transaction.status == 'issued',
        Transaction.due_date.between(now, now + timedelta(days=3))
    ).all()

    mem = get_process_memory()
    cache_stats = search_cache.stats()
    db_size = get_db_size()

    return render_template('dashboard/admin.html', stats=stats,
                           recent_txns=recent_txns, recent_activity=recent_activity,
                           due_soon=due_soon, mem=mem, cache_stats=cache_stats,
                           db_size=db_size, an=_cache_get('dash:analytics', dashboard_analytics))


def librarian_dashboard():
    now = datetime.now(timezone.utc)
    stats = {
        'total_books': _cache_get('dash:total_books', lambda: Book.query.count()),
        'available_books': _cache_get('dash:avail_copies',
            lambda: db.session.query(func.coalesce(func.sum(Book.available_quantity), 0)).scalar()),
        'issued_books': Transaction.query.filter_by(status='issued').count(),
        'overdue_books': Transaction.query.filter(
            Transaction.status == 'issued', Transaction.due_date < now).count(),
        'total_members': _cache_get('dash:total_members', lambda: Member.query.count()),
    }
    due_soon = Transaction.query.filter(
        Transaction.status == 'issued',
        Transaction.due_date.between(now, now + timedelta(days=3))
    ).limit(10).all()
    recent_txns = Transaction.query.order_by(Transaction.created_at.desc()).limit(10).all()
    return render_template('dashboard/librarian.html', stats=stats,
                           due_soon=due_soon, recent_txns=recent_txns,
                           an=_cache_get('dash:analytics', dashboard_analytics))


def member_dashboard():
    member = Member.query.filter_by(user_id=current_user.id).first()
    if not member:
        return render_template('dashboard/member.html', member=None,
                               active_loans=[], due_soon=[], overdue=[], fines_total=0)

    now = datetime.now(timezone.utc)
    active_loans = Transaction.query.filter_by(
        member_id=member.id, status='issued').order_by(Transaction.due_date).all()
    due_soon = [t for t in active_loans
                if t.due_date and (t.due_date.replace(tzinfo=timezone.utc)
                if t.due_date.tzinfo is None else t.due_date) <= now + timedelta(days=3)
                and (t.due_date.replace(tzinfo=timezone.utc)
                if t.due_date.tzinfo is None else t.due_date) >= now]
    overdue = [t for t in active_loans if t.is_overdue]
    fine_rate = Setting.get_float('fine_rate', 2.0)
    accruing_total = round(sum(t.accrued_fine(fine_rate) for t in overdue), 2)
    fines_total = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
        Fine.member_id == member.id, Fine.paid == False).scalar() or 0

    recent = Transaction.query.filter_by(member_id=member.id).order_by(
        Transaction.created_at.desc()).limit(10).all()
    notifications = Notification.query.filter_by(
        user_id=current_user.id).order_by(Notification.created_at.desc()).limit(10).all()

    return render_template('dashboard/member.html', member=member,
                           active_loans=active_loans, due_soon=due_soon,
                           overdue=overdue, fines_total=fines_total,
                           fine_rate=fine_rate, accruing_total=accruing_total,
                           loan_days=Setting.get_int('loan_duration', 14),
                           recent=recent, notifications=notifications)
