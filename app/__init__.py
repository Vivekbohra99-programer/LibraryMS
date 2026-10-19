"""Flask application factory."""
import tracemalloc
from flask import Flask, render_template, redirect, url_for, request
from flask_login import current_user
from config import Config
from app.extensions import db, login_manager, csrf
from app.services.notifications import get_unread_count, get_recent


def create_app(config_class=None):
    app = Flask(__name__)
    app.config.from_object(config_class or Config)

    # Start tracemalloc for Q17 memory monitoring
    if not tracemalloc.is_tracing():
        tracemalloc.start()

    from app.services.throttle import LoginThrottle
    app.extensions['login_throttle'] = LoginThrottle(
        max_failures=app.config.get('LOGIN_MAX_FAILURES', 5),
        lock_seconds=app.config.get('LOGIN_LOCK_SECONDS', 900))

    # Init extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.books import books_bp
    from app.routes.authors import authors_bp
    from app.routes.categories import categories_bp
    from app.routes.members import members_bp
    from app.routes.transactions import transactions_bp
    from app.routes.fines import fines_bp
    from app.routes.reports import reports_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(authors_bp)
    app.register_blueprint(categories_bp)
    app.register_blueprint(members_bp)
    app.register_blueprint(transactions_bp)
    app.register_blueprint(fines_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(admin_bp)

    # Landing page
    @app.route('/')
    def landing():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.index'))
        from app.models.book import Book
        from app.models.member import Member
        from app.services.cache import search_cache
        stats = {
            'total_books': search_cache.get('landing:books') or 0,
            'total_members': search_cache.get('landing:members') or 0,
        }
        # Refresh stats if cache miss
        if not search_cache.get('landing:books'):
            stats['total_books'] = Book.query.count()
            search_cache.set('landing:books', stats['total_books'])
        if not search_cache.get('landing:members'):
            stats['total_members'] = Member.query.count()
            search_cache.set('landing:members', stats['total_members'])

        featured = Book.query.filter(Book.cover_raw_size > 0).order_by(
            Book.created_at.desc()).limit(8).all()
        if len(featured) < 4:
            featured = Book.query.order_by(Book.created_at.desc()).limit(8).all()
        from app.services.memory import compression_summary
        comp = compression_summary()          # real, measured from the books table
        cache = search_cache.stats()          # real LRU cache counters / settings
        return render_template('landing.html', stats=stats, featured=featured,
                               comp=comp, cache=cache)

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')       # never guess a file's type
        resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')           # no embedding in other sites
        resp.headers.setdefault('Referrer-Policy', 'same-origin')
        return resp

    @app.context_processor
    def inject_skin():
        # which look the page starts in before the visitor's own choice (kept in their browser) is read
        skin = app.config.get('DEFAULT_SKIN')
        return {'default_skin': skin if skin in ('glass', 'skeuo') else 'glass'}

    # Context processor for notifications
    @app.context_processor
    def inject_notifications():
        if current_user.is_authenticated:
            return {
                'unread_count': get_unread_count(current_user.id),
                'recent_notifications': get_recent(current_user.id, 5),
            }
        return {'unread_count': 0, 'recent_notifications': []}

    # Error handlers
    @app.errorhandler(400)
    def bad_request(e):
        return render_template('errors/400.html'), 400

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    # Create tables on first run
    with app.app_context():
        db.create_all()
        from app.models.setting import Setting
        Setting.seed_defaults()
        if not app.config.get('TESTING'):
            from app.models.user import User
            from app.models.member import Member
            if User.query.first() is None:
                admin = User(username='admin', email='admin@library.local', role='admin')
                admin.set_password('admin123')
                librarian = User(username='librarian', email='librarian@library.local', role='librarian')
                librarian.set_password('librarian123')
                member_user = User(username='member', email='member@library.local', role='member')
                member_user.set_password('member123')
                db.session.add_all([admin, librarian, member_user])
                db.session.flush()
                member = Member(user_id=member_user.id, name='Standard Member',
                                email='member@library.local', phone='555-0100',
                                status='active', loan_limit=5)
                db.session.add(member)
                db.session.commit()

    return app
