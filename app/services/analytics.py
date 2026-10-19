"""Dashboard analytics: a handful of SQL aggregates, no model objects loaded.

Everything here is a GROUP BY / SUM / COUNT, so the cost stays flat as the catalogue grows
(Q17: the dashboard never pulls whole tables into memory). The results are small dicts that the
dashboard caches in the bounded LRU cache."""
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, Integer
from app.extensions import db
from app.models.book import Book
from app.models.category import Category
from app.models.fine import Fine
from app.models.setting import Setting
from app.models.transaction import Transaction


def _utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def loans_per_day(days=14):
    """Loans issued per calendar day (UTC) for the last `days` days, zero-filled."""
    today = _utc_now_naive().date()
    start = today - timedelta(days=days - 1)
    rows = (db.session.query(func.date(Transaction.issue_date), func.count(Transaction.id))
            .filter(Transaction.issue_date >= datetime.combine(start, datetime.min.time()))
            .group_by(func.date(Transaction.issue_date)).all())
    counts = {str(day): n for day, n in rows}
    series = []
    for i in range(days):
        d = start + timedelta(days=i)
        series.append({'label': d.strftime('%d'), 'full': d.strftime('%b %d'),
                       'value': counts.get(d.isoformat(), 0)})
    return series


def books_by_category(limit=6):
    """Titles per category, largest first. Returns (rows, total_titles)."""
    rows = (db.session.query(Category.name, func.count(Book.id))
            .join(Book, Book.category_id == Category.id)
            .group_by(Category.id).order_by(func.count(Book.id).desc(), Category.name)
            .limit(limit).all())
    total = db.session.query(func.count(Book.id)).scalar() or 0
    return [{'name': n, 'value': c} for n, c in rows], total


def fine_split():
    paid = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(Fine.paid.is_(True)).scalar() or 0
    unpaid = db.session.query(func.coalesce(func.sum(Fine.amount), 0)).filter(Fine.paid.is_(False)).scalar() or 0
    return {'paid': round(float(paid), 2), 'unpaid': round(float(unpaid), 2)}


def overdue_exposure(rate):
    """Loans still out past their due date, and the fine they have accrued so far.

    Same arithmetic as Transaction.overdue_days (whole days late), done in SQL."""
    days_late = func.cast(func.julianday('now') - func.julianday(Transaction.due_date), Integer)
    count, days = (db.session.query(func.count(Transaction.id), func.coalesce(func.sum(days_late), 0))
                   .filter(Transaction.status == 'issued', Transaction.due_date < _utc_now_naive()).one())
    return {'count': int(count), 'days': int(days), 'accruing': round(int(days) * rate, 2), 'rate': rate}


def dashboard_analytics():
    rate = Setting.get_float('fine_rate', 2.0)
    loans = loans_per_day()
    total = sum(d['value'] for d in loans)
    peak = max(loans, key=lambda d: d['value'])
    cats, titles = books_by_category()
    summary = (f"Loans issued per day, last {len(loans)} days. Total {total}."
               + (f" Busiest day {peak['full']} with {peak['value']}." if total else ''))
    return {
        'loans': loans, 'loans_total': total, 'loans_peak': peak['value'], 'loans_summary': summary,
        'categories': cats, 'category_titles': titles,
        'category_max': cats[0]['value'] if cats else 0,
        'fines': fine_split(), 'overdue': overdue_exposure(rate),
    }
