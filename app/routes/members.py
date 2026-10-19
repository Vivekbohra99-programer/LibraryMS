"""Member routes – CRUD and profile."""
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.member import Member
from app.models.transaction import Transaction
from app.models.fine import Fine
from app.models.user import User
from app.models.setting import Setting
from app.services.cache import search_cache
from app.services.activity import log_activity
from sqlalchemy import func
from functools import wraps

members_bp = Blueprint('members', __name__)


def staff_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_staff:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@members_bp.route('/members')
@login_required
@staff_required
def index():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    status = request.args.get('status', '')
    query = Member.query
    if search:
        query = query.filter(
            db.or_(Member.name.ilike(f'%{search}%'),
                   Member.email.ilike(f'%{search}%')))
    if status:
        query = query.filter_by(status=status)
    query = query.order_by(Member.name)
    pagination = query.paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('members/index.html', pagination=pagination,
                           members=pagination.items, search=search, status=status)


@members_bp.route('/members/add', methods=['GET', 'POST'])
@login_required
@staff_required
def add():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        loan_limit = request.form.get('loan_limit', Setting.get_int('member_loan_limit', 5), type=int)

        errors = []
        if not name:
            errors.append('Name is required.')
        if not email:
            errors.append('Email is required.')
        if Member.query.filter_by(email=email).first():
            errors.append('A member with this email already exists.')
        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('members/form.html', member=None, action='Add',
                                   default_loan_limit=Setting.get_int('member_loan_limit', 5))

        member = Member(name=name, email=email, phone=phone, address=address,
                        loan_limit=loan_limit)
        db.session.add(member)
        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'member_add', f'Added member: {name}')
        flash(f'Member "{name}" added.', 'success')
        return redirect(url_for('members.index'))
    return render_template('members/form.html', member=None, action='Add',
                           default_loan_limit=Setting.get_int('member_loan_limit', 5))


@members_bp.route('/members/<int:member_id>')
@login_required
def view(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        abort(404)
    # Members can only view their own profile
    if current_user.is_member_role:
        if not member.user_id or member.user_id != current_user.id:
            abort(403)

    active_loans = Transaction.query.filter_by(
        member_id=member.id, status='issued').all()
    history = Transaction.query.filter_by(member_id=member.id).order_by(
        Transaction.created_at.desc()).limit(20).all()
    total_fines = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(
        Fine.member_id == member.id, Fine.paid == False).scalar() or 0
    return render_template('members/view.html', member=member,
                           active_loans=active_loans, history=history,
                           total_fines=total_fines)


@members_bp.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
@login_required
@staff_required
def edit(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        abort(404)
    if request.method == 'POST':
        member.name = request.form.get('name', '').strip()
        new_email = request.form.get('email', '').strip()
        member.phone = request.form.get('phone', '').strip()
        member.address = request.form.get('address', '').strip()
        member.loan_limit = request.form.get('loan_limit', 5, type=int)
        member.status = request.form.get('status', 'active')

        if not member.name:
            flash('Name is required.', 'danger')
            return render_template('members/form.html', member=member, action='Edit')
        if new_email != member.email:
            if Member.query.filter(Member.email == new_email, Member.id != member.id).first():
                flash('Email already in use.', 'danger')
                return render_template('members/form.html', member=member, action='Edit')
            member.email = new_email

        db.session.commit()
        search_cache.invalidate_all()
        log_activity(current_user.id, 'member_edit', f'Edited member: {member.name}')
        flash(f'Member "{member.name}" updated.', 'success')
        return redirect(url_for('members.view', member_id=member.id))
    return render_template('members/form.html', member=member, action='Edit')


@members_bp.route('/members/<int:member_id>/delete', methods=['POST'])
@login_required
@staff_required
def delete(member_id):
    member = db.session.get(Member, member_id)
    if not member:
        abort(404)
    if member.transactions.filter_by(status='issued').count() > 0:
        flash('Cannot delete member with active loans.', 'danger')
        return redirect(url_for('members.view', member_id=member.id))
    name = member.name
    # Deactivate instead of hard delete
    member.status = 'inactive'
    db.session.commit()
    search_cache.invalidate_all()
    log_activity(current_user.id, 'member_deactivate', f'Deactivated member: {name}')
    flash(f'Member "{name}" deactivated.', 'success')
    return redirect(url_for('members.index'))


@members_bp.route('/profile')
@login_required
def profile():
    if current_user.is_member_role:
        member = Member.query.filter_by(user_id=current_user.id).first()
        if member:
            return redirect(url_for('members.view', member_id=member.id))
    return render_template('members/profile.html')
