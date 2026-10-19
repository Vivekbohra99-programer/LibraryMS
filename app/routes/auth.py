"""Authentication routes."""
from urllib.parse import urlparse
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.member import Member
from app.models.setting import Setting
from app.services.activity import log_activity

auth_bp = Blueprint('auth', __name__)

# Passwords of the demo accounts created on first run (and by seed.py). Public in the README, so worth a nudge.
DEFAULT_PASSWORDS = {'admin123', 'librarian123', 'member123'}


def _safe_next(target):
    """Only follow `next` to a path on this site. Blocks //evil.com, https://evil.com and backslash tricks."""
    if not target or not target.startswith('/') or target.startswith('//') or '\\' in target:
        return None
    parts = urlparse(target)
    return target if not parts.scheme and not parts.netloc else None


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        throttle = current_app.extensions['login_throttle']
        address = request.remote_addr or ''
        wait = throttle.locked_for(address, username)
        if wait:        # checked before the password, so a lock cannot be used to test guesses
            minutes = max(1, round(wait / 60))
            flash(f'Too many failed sign-in attempts. Try again in {minutes} minute{"" if minutes == 1 else "s"}.',
                  'danger')
            return render_template('auth/login.html'), 429
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            if not user.is_active:
                flash('Your account has been deactivated. Contact the administrator.', 'danger')
                return render_template('auth/login.html')
            throttle.reset(address, username)
            login_user(user)
            log_activity(user.id, 'login', f'User {user.username} logged in', address)
            if password in DEFAULT_PASSWORDS:
                flash('You are signing in with a default demo password. Open Change Password in the account menu '
                      'and choose your own.', 'warning')
            return redirect(_safe_next(request.args.get('next')) or url_for('dashboard.index'))
        if throttle.record_failure(address, username) and user:
            log_activity(user.id, 'login_locked',
                         f'Sign-in for {user.username} locked after repeated wrong passwords from {address}', address)
        flash('Invalid username or password.', 'danger')
    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        name = request.form.get('name', '').strip()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')
        phone = request.form.get('phone', '').strip()

        errors = []
        if not username or len(username) < 3:
            errors.append('Username must be at least 3 characters.')
        if not email:
            errors.append('Email is required.')
        if not name:
            errors.append('Name is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if password != confirm:
            errors.append('Passwords do not match.')
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')
        if Member.query.filter_by(email=email).first():
            errors.append('A member with this email already exists.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('auth/register.html')

        user = User(username=username, email=email, role='member')
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        member = Member(user_id=user.id, name=name, email=email, phone=phone,
                        loan_limit=Setting.get_int('member_loan_limit', 5))
        db.session.add(member)
        db.session.commit()

        log_activity(user.id, 'register', f'New member registered: {username}')
        flash('Registration successful! Please log in.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    log_activity(current_user.id, 'logout', f'User {current_user.username} logged out',
                 request.remote_addr or '')
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_pw = request.form.get('current_password', '')
        new_pw = request.form.get('new_password', '')
        confirm_pw = request.form.get('confirm_password', '')

        if not current_user.check_password(current_pw):
            flash('Current password is incorrect.', 'danger')
        elif len(new_pw) < 6:
            flash('New password must be at least 6 characters.', 'danger')
        elif new_pw != confirm_pw:
            flash('New passwords do not match.', 'danger')
        else:
            current_user.set_password(new_pw)
            db.session.commit()
            log_activity(current_user.id, 'change_password', 'Password changed')
            flash('Password changed successfully.', 'success')
            return redirect(url_for('dashboard.index'))
    return render_template('auth/change_password.html')
