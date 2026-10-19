"""Fine routes."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from datetime import datetime, timezone
from app.extensions import db
from app.models.fine import Fine
from app.models.member import Member
from app.models.setting import Setting
from app.services.cache import search_cache
from app.services.activity import log_activity
from app.services.notifications import notify
from functools import wraps

fines_bp = Blueprint('fines', __name__)


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_staff:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@fines_bp.route('/fines')
@login_required
def index():
    page = request.args.get('page', 1, type=int)
    paid_filter = request.args.get('paid', '')

    if current_user.is_member_role:
        member = Member.query.filter_by(user_id=current_user.id).first()
        if not member:
            return render_template('fines/index.html', pagination=None,
                                   fines=[], paid_filter=paid_filter, totals={})
        query = Fine.query.filter_by(member_id=member.id)
    else:
        query = Fine.query

    if paid_filter == 'paid':
        query = query.filter_by(paid=True)
    elif paid_filter == 'unpaid':
        query = query.filter_by(paid=False)

    query = query.order_by(Fine.created_at.desc())
    pagination = query.paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)

    # Totals
    base_q = Fine.query
    if current_user.is_member_role and member:
        base_q = base_q.filter_by(member_id=member.id)
    totals = {
        'total': db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            *base_q.whereclause.clauses if hasattr(base_q, 'whereclause') and base_q.whereclause is not None else []).scalar() if False else 0,
        'paid': 0,
        'unpaid': 0,
    }
    # Simpler total calculation
    if current_user.is_member_role and member:
        totals['total'] = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            Fine.member_id == member.id).scalar() or 0
        totals['paid'] = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            Fine.member_id == member.id, Fine.paid == True).scalar() or 0
        totals['unpaid'] = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            Fine.member_id == member.id, Fine.paid == False).scalar() or 0
    else:
        totals['total'] = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).scalar() or 0
        totals['paid'] = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            Fine.paid == True).scalar() or 0
        totals['unpaid'] = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
            Fine.paid == False).scalar() or 0

    return render_template('fines/index.html', pagination=pagination,
                           fines=pagination.items, paid_filter=paid_filter,
                           totals=totals)


@fines_bp.route('/fines/<int:fine_id>/pay', methods=['POST'])
@login_required
@staff_required
def pay(fine_id):
    fine = db.session.get(Fine, fine_id)
    if not fine:
        abort(404)
    if fine.paid:
        flash('Fine already paid.', 'info')
        return redirect(url_for('fines.index'))
    fine.paid = True
    fine.paid_date = datetime.now(timezone.utc)
    db.session.commit()
    search_cache.invalidate_all()
    log_activity(current_user.id, 'fine_paid',
                 f'Marked fine #{fine.id} (₹{fine.amount}) as paid for member #{fine.member_id}')
    member = db.session.get(Member, fine.member_id)
    if member and member.user_id:
        notify(member.user_id, f'Your fine of ₹{fine.amount} has been marked as paid.',
               type='success', link=url_for('fines.index'))
    flash(f'Fine of ₹{fine.amount} marked as paid.', 'success')
    return redirect(url_for('fines.index'))
