"""Admin routes – maintenance, performance, settings, staff, backup, notifications, logs."""
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, abort, current_app, jsonify)
from flask_login import login_required, current_user
from datetime import datetime, timezone
import os
from app.extensions import db
from app.models.user import User
from app.models.setting import Setting, MIN_RETENTION_DAYS
from app.models.notification import Notification
from app.models.activity_log import ActivityLog
from app.services import purge as purge_svc
from app.services.memory import (full_performance_report, measure_eager_vs_lazy,
                                  get_process_memory, get_python_allocation, compression_summary)
from app.services.cache import search_cache
from app.services.activity import log_activity
from functools import wraps

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------- Performance Dashboard ----------

@admin_bp.route('/admin/performance')
@login_required
@admin_required
def performance():
    report = full_performance_report()
    return render_template('admin/performance.html', report=report)


@admin_bp.route('/admin/performance/console')
@login_required
@admin_required
def performance_console():
    """Same report as the dashboard, drawn as a skeuomorphic instrument panel."""
    report = full_performance_report()
    return render_template('admin/performance_console.html', report=report)


@admin_bp.route('/admin/performance/benchmark', methods=['POST'])
@login_required
@admin_required
def benchmark():
    result = measure_eager_vs_lazy()
    comp = compression_summary()
    cache = search_cache.stats()
    flash('Benchmark completed with real measurements.', 'success')
    return render_template('admin/benchmark.html', result=result, comp=comp, cache=cache)


# ---------- Database Maintenance ----------

@admin_bp.route('/admin/maintenance')
@login_required
@admin_required
def maintenance():
    db_size = purge_svc.get_db_size()
    return render_template('admin/maintenance.html', db_size=db_size,
                           tx_days=Setting.get_int('transaction_retention_days', 730),
                           log_days=Setting.get_int('log_retention_days', 365),
                           min_days=MIN_RETENTION_DAYS)


@admin_bp.route('/admin/maintenance/purge-transactions', methods=['POST'])
@login_required
@admin_required
def purge_transactions():
    days = request.form.get('days', Setting.get_int('transaction_retention_days', 730), type=int)
    if days < MIN_RETENTION_DAYS:
        flash(f'Keep at least {MIN_RETENTION_DAYS} days of loan history. Nothing was deleted.', 'danger')
        return redirect(url_for('admin.maintenance'))
    export_path = None
    if request.form.get('export_csv') == 'on':
        # one new file per purge, so an earlier archive is never overwritten
        stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        export_path = os.path.join(current_app.config['BACKUP_FOLDER'], 'archives',
                                   f'purged_transactions_{stamp}.csv')
    kept = purge_svc.kept_for_unpaid_fines(days)
    count = purge_svc.archive_old_transactions(older_than_days=days, export_csv_path=export_path)
    log_activity(current_user.id, 'purge_transactions',
                 f'Purged {count} old transactions (>{days} days); kept {kept} with unpaid fines')
    flash(f'Purged {count} old transaction(s).', 'success')
    if count and export_path:
        flash(f'Saved a copy first: backups/archives/{os.path.basename(export_path)}', 'info')
    if kept:
        flash(f'{kept} old loan(s) were kept because their fine is still unpaid.', 'info')
    return redirect(url_for('admin.maintenance'))


@admin_bp.route('/admin/maintenance/purge-logs', methods=['POST'])
@login_required
@admin_required
def purge_logs():
    days = request.form.get('days', Setting.get_int('log_retention_days', 365), type=int)
    if days < MIN_RETENTION_DAYS:
        flash(f'Keep at least {MIN_RETENTION_DAYS} days of activity logs. Nothing was deleted.', 'danger')
        return redirect(url_for('admin.maintenance'))
    count = purge_svc.purge_old_logs(older_than_days=days)
    log_activity(current_user.id, 'purge_logs', f'Purged {count} old activity logs (>{days} days)')
    flash(f'Purged {count} old log(s).', 'success')
    return redirect(url_for('admin.maintenance'))


@admin_bp.route('/admin/maintenance/vacuum', methods=['POST'])
@login_required
@admin_required
def vacuum():
    result = purge_svc.vacuum_database()
    log_activity(current_user.id, 'vacuum',
                 f'VACUUM: {result["before_bytes"]}→{result["after_bytes"]} bytes')
    flash(f'VACUUM complete. Before: {result["before_bytes"]:,} bytes, '
          f'After: {result["after_bytes"]:,} bytes, '
          f'Reclaimed: {result["reclaimed_bytes"]:,} bytes.', 'success')
    return redirect(url_for('admin.maintenance'))


@admin_bp.route('/admin/maintenance/analyze', methods=['POST'])
@login_required
@admin_required
def analyze():
    purge_svc.analyze_database()
    log_activity(current_user.id, 'analyze', 'ANALYZE executed')
    flash('ANALYZE complete. Query planner statistics updated.', 'success')
    return redirect(url_for('admin.maintenance'))


@admin_bp.route('/admin/maintenance/integrity', methods=['POST'])
@login_required
@admin_required
def integrity():
    result = purge_svc.integrity_check()
    log_activity(current_user.id, 'integrity_check', f'Result: {result}')
    if result == 'ok':
        flash('Database integrity check passed: OK', 'success')
    else:
        flash(f'Database integrity check result: {result}', 'warning')
    return redirect(url_for('admin.maintenance'))


@admin_bp.route('/admin/maintenance/full', methods=['POST'])
@login_required
@admin_required
def full_maintenance():
    results = []
    integrity = purge_svc.integrity_check()
    results.append(f'Integrity: {integrity}')
    purge_svc.analyze_database()
    results.append('ANALYZE: done')
    vac = purge_svc.vacuum_database()
    results.append(f'VACUUM: reclaimed {vac["reclaimed_bytes"]:,} bytes')
    log_activity(current_user.id, 'full_maintenance', '; '.join(results))
    flash('Full maintenance complete. ' + ' | '.join(results), 'success')
    return redirect(url_for('admin.maintenance'))


# ---------- Backup & Restore ----------

@admin_bp.route('/admin/backups')
@login_required
@admin_required
def backups():
    backup_folder = current_app.config['BACKUP_FOLDER']
    backup_list = purge_svc.list_backups(backup_folder)
    return render_template('admin/backups.html', backups=backup_list)


@admin_bp.route('/admin/backups/create', methods=['POST'])
@login_required
@admin_required
def create_backup():
    backup_folder = current_app.config['BACKUP_FOLDER']
    name = purge_svc.create_backup(backup_folder)
    if name:
        log_activity(current_user.id, 'backup_create', f'Created backup: {name}')
        flash(f'Backup created: {name}', 'success')
    else:
        flash('Backup failed: database not found.', 'danger')
    return redirect(url_for('admin.backups'))


@admin_bp.route('/admin/backups/restore/<name>', methods=['POST'])
@login_required
@admin_required
def restore_backup(name):
    backup_folder = current_app.config['BACKUP_FOLDER']
    try:
        safety = purge_svc.restore_backup(backup_folder, name)
        log_activity(current_user.id, 'backup_restore',
                     f'Restored from {name} (safety backup: {safety})')
        flash(f'Database restored from {name}. Safety backup: {safety}', 'success')
    except FileNotFoundError:
        flash('Backup file not found.', 'danger')
    except ValueError:
        flash('That backup is damaged or is not a SQLite database. Nothing was changed.', 'danger')
    return redirect(url_for('admin.backups'))


@admin_bp.route('/admin/backups/delete/<name>', methods=['POST'])
@login_required
@admin_required
def delete_backup(name):
    backup_folder = current_app.config['BACKUP_FOLDER']
    if purge_svc.delete_backup(backup_folder, name):
        log_activity(current_user.id, 'backup_delete', f'Deleted backup: {name}')
        flash(f'Backup {name} deleted.', 'success')
    else:
        flash('Backup not found.', 'danger')
    return redirect(url_for('admin.backups'))


# ---------- Settings ----------

@admin_bp.route('/admin/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    if request.method == 'POST':
        changes, errors, updates = [], [], {}
        for key in Setting.DEFAULTS:
            new_val = request.form.get(key, '').strip()
            if not new_val:
                continue
            ok, result = Setting.validate(key, new_val)
            if not ok:
                errors.append(result)
            elif Setting.get(key) != result:
                updates[key] = result
        if errors:                      # all-or-nothing: one bad value saves nothing
            for e in errors:
                flash(e, 'danger')
            return redirect(url_for('admin.settings'))
        for key, val in updates.items():
            changes.append(f'{key}: {Setting.get(key)}→{val}')
            Setting.set(key, val)
        # Reconfigure cache if changed
        cache_max = Setting.get_int('cache_max_size', 64)
        cache_ttl = Setting.get_int('cache_ttl', 120)
        search_cache.reconfigure(maxsize=cache_max, ttl=cache_ttl)

        if changes:
            search_cache.invalidate_all()       # cached dashboard figures may depend on the changed values
            log_activity(current_user.id, 'settings_change', '; '.join(changes))
            flash('Settings updated.', 'success')
        else:
            flash('No changes made.', 'info')
        return redirect(url_for('admin.settings'))

    groups = {}
    for key in Setting.DEFAULTS:
        kind, lo, hi = Setting.RULES[key]
        label, unit, group = Setting.UI[key]
        groups.setdefault(group, []).append({
            'key': key, 'label': label, 'unit': unit, 'value': Setting.get(key),
            'description': Setting.DEFAULTS[key][1], 'min': lo, 'max': hi,
            'step': 'any' if kind is float else 1,
        })
    return render_template('admin/settings.html', groups=groups)


# ---------- Staff Accounts ----------

@admin_bp.route('/admin/staff')
@login_required
@admin_required
def staff():
    users = User.query.filter(User.role.in_(['admin', 'librarian'])).order_by(User.username).all()
    return render_template('admin/staff.html', users=users)


@admin_bp.route('/admin/staff/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_staff():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'librarian')

        errors = []
        if not username:
            errors.append('Username is required.')
        if not email:
            errors.append('Email is required.')
        if len(password) < 6:
            errors.append('Password must be at least 6 characters.')
        if role not in ('admin', 'librarian'):
            errors.append('Invalid role.')
        if User.query.filter_by(username=username).first():
            errors.append('Username already taken.')
        if User.query.filter_by(email=email).first():
            errors.append('Email already registered.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('admin/staff_form.html', user=None, action='Add')

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        log_activity(current_user.id, 'staff_add', f'Created {role} account: {username}')
        flash(f'Staff account "{username}" created.', 'success')
        return redirect(url_for('admin.staff'))
    return render_template('admin/staff_form.html', user=None, action='Add')


@admin_bp.route('/admin/staff/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_staff(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
        return redirect(url_for('admin.staff'))
    user.is_active = not user.is_active
    db.session.commit()
    status = 'activated' if user.is_active else 'deactivated'
    log_activity(current_user.id, 'staff_toggle', f'{status} user: {user.username}')
    flash(f'User "{user.username}" {status}.', 'success')
    return redirect(url_for('admin.staff'))


# ---------- Notifications ----------

@admin_bp.route('/notifications')
@login_required
def notifications():
    page = request.args.get('page', 1, type=int)
    pagination = Notification.query.filter_by(user_id=current_user.id).order_by(
        Notification.created_at.desc()).paginate(page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('admin/notifications.html', pagination=pagination,
                           notifications=pagination.items)


@admin_bp.route('/notifications/<int:notif_id>/read', methods=['POST'])
@login_required
def mark_read(notif_id):
    n = db.session.get(Notification, notif_id)
    if n and n.user_id == current_user.id:
        n.read = True
        db.session.commit()
    return redirect(request.referrer or url_for('admin.notifications'))


@admin_bp.route('/notifications/read-all', methods=['POST'])
@login_required
def mark_all_read():
    Notification.query.filter_by(user_id=current_user.id, read=False).update({'read': True})
    db.session.commit()
    flash('All notifications marked as read.', 'success')
    return redirect(url_for('admin.notifications'))


# ---------- Activity Logs ----------

@admin_bp.route('/admin/activity-logs')
@login_required
@admin_required
def activity_logs():
    page = request.args.get('page', 1, type=int)
    search = request.args.get('q', '').strip()
    query = ActivityLog.query
    if search:
        query = query.filter(
            db.or_(ActivityLog.action.ilike(f'%{search}%'),
                   ActivityLog.details.ilike(f'%{search}%')))
    pagination = query.order_by(ActivityLog.created_at.desc()).paginate(
        page=page, per_page=Setting.get_int('page_size', 25), error_out=False)
    return render_template('admin/activity_logs.html', pagination=pagination,
                           logs=pagination.items, search=search)


# ---------- API for notification count ----------

@admin_bp.route('/api/notification-count')
@login_required
def notification_count():
    count = Notification.query.filter_by(user_id=current_user.id, read=False).count()
    return jsonify({'count': count})
