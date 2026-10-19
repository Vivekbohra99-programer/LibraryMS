# Library Management System — Q17: Reduce Memory Usage

A **full-stack web application** built with Flask, SQLAlchemy, and SQLite, designed for the **Q17 (Reduce Memory Usage)** TQM quality goal. The system implements four memory-optimization features alongside a complete library management workflow with role-based access control.

The interface has **two looks**, switchable at any time from the top bar: **Glass** (the default, an iOS-style frosted-glass design) and **Skeuomorphic** (brushed metal, paper, LED read-outs). Both cover every page, in light and dark mode, on desktop and phone. See *Look and Feel* below.

---

## Q17 Features

| # | Feature | Implementation | Description |
|---|---------|---------------|-------------|
| 1 | **Asset Compression** | `app/services/compression.py` | Book descriptions (`zlib`) and cover images (`Pillow`) are compressed before storage; decompressed on-demand |
| 2 | **On-Demand Data Loading** | `app/models/book.py` (deferred columns) | The compressed cover and description are *deferred* columns: list pages, exports and drop-downs never read them from the database. They are fetched, and decompressed, only when one book's page or cover is opened |
| 3 | **DB Purge Tools** | `app/services/purge.py` | Archive old transactions, purge stale logs, VACUUM database, backup/restore |
| 4 | **Query Caching** | `app/services/cache.py`, `app/services/catalogue.py` | Thread-safe bounded LRU cache with configurable TTL and automatic eviction. Holds catalogue search pages (the ids and the total only), the filter drop-downs, dashboard figures and landing-page counts |

### How These Features Reduce Memory

- **Compression** is stored in `BLOB` columns. Measured on the 40-book demo data: descriptions are **84% smaller** (70.8 KB to 11.5 KB). The demo covers are already JPEGs, so `zlib` alone saves only 28% on them; the big saving for covers happens at upload, where the image is resized and re-encoded (one 0.9 MB camera-size upload became 0.2 MB, **76% smaller**). Real photos behave like the upload, not like the demo covers.
- **On-demand loading** means a page of books reads only the ordinary columns. Measured on the demo data (peak Python memory while loading): a 25-book catalogue page needs **75% less** and loading every book (export, issue form) **79% less** than loading the BLOBs too. The gap grows with the size of the covers: in the test suite, 30 books with 100 KB covers load in under a fifth of the memory. The *Eager vs. lazy* benchmark on the admin Performance page measured **94% less** peak heap on the same data.
- **Purge tools** remove old returned transactions and activity logs, then `VACUUM` reclaims freed SQLite pages. Loans with an unpaid fine are never purged.
- **LRU caching** is bounded (`maxsize`, default 64 entries) so a repeated search is answered without recomputing the filter, sort and count, and the cache cannot grow without limit. Entries hold ids and numbers, not book objects, and book rows are read fresh each time, so availability is never stale. Any write operation clears the cache.

Numbers vary with your data and machine. Re-measure on the **Performance** page (and its *Console view*) before quoting them in a report.

---

## Project Structure

```
library_management_system/
├── run.py                    # Application entry point
├── config.py                 # Configuration (SECRET_KEY, DB URI, etc.)
├── requirements.txt          # Python dependencies
├── seed.py                   # Demo data seeder (40 books with covers)
├── pytest.ini                # Test configuration
├── app/
│   ├── __init__.py           # Application factory + bootstrap
│   ├── extensions.py         # SQLAlchemy, LoginManager, CSRF
│   ├── models/
│   │   ├── user.py           # User model (auth, roles)
│   │   ├── member.py         # Library member
│   │   ├── book.py           # Book with lazy decompression
│   │   ├── author.py         # Author
│   │   ├── category.py       # Category
│   │   ├── transaction.py    # Issue/return/renewal tracking
│   │   ├── fine.py           # Fine calculation and payment
│   │   ├── activity_log.py   # Audit trail
│   │   ├── notification.py   # In-app notifications
│   │   └── setting.py        # System-wide configuration
│   ├── routes/
│   │   ├── auth.py           # Login, register, password change
│   │   ├── dashboard.py      # Role-based dashboards
│   │   ├── books.py          # Book CRUD + public catalogue
│   │   ├── authors.py        # Author management
│   │   ├── categories.py     # Category management
│   │   ├── members.py        # Member CRUD + profiles
│   │   ├── transactions.py   # Issue, return, renew
│   │   ├── fines.py          # Fine listing and payment
│   │   ├── reports.py        # Reports + CSV/Excel exports
│   │   └── admin.py          # Admin panel (performance, settings, purge)
│   ├── services/
│   │   ├── compression.py    # Q17 Feature 1: zlib + Pillow compression
│   │   ├── cache.py          # Q17 Feature 4: LRU cache
│   │   ├── purge.py          # Q17 Feature 3: DB purge, vacuum, backup
│   │   ├── memory.py         # Q17 benchmark: eager vs. lazy comparison
│   │   ├── export.py         # CSV/Excel export utilities
│   │   ├── analytics.py      # Dashboard charts: SQL aggregates only, nothing loaded into memory
│   │   ├── catalogue.py      # Catalogue / book-list search: title, author or ISBN, cached page ids
│   │   ├── throttle.py       # Login lockout (bounded in-memory table)
│   │   ├── activity.py       # Activity logging
│   │   └── notifications.py  # Notification service
│   ├── templates/            # 56 Jinja2 templates (Bootstrap 5, two skins)
│   └── static/               # css/liquid-glass.css (Glass look), css/skeuo-app.css (Skeuomorphic look,
│                             #   every rule scoped to html[data-skin="skeuo"]), css/skeuo.css + js/skeuo.js
│                             #   (Performance console dials), js/liquid-glass.js (theme, skin, effects)
├── tests/                    # 246 pytest tests (100% pass)
│   ├── conftest.py           # Fixtures with isolated test DB
│   ├── test_auth.py
│   ├── test_books.py
│   ├── test_authors_categories.py
│   ├── test_members.py
│   ├── test_transactions.py
│   ├── test_fines.py
│   ├── test_q17.py           # All 4 Q17 features tested
│   ├── test_reports_exports.py
│   ├── test_permissions.py
│   ├── test_completion.py    # Overdue fines, analytics, catalogue, settings, backups, data integrity
│   ├── test_settings_effects.py  # Every setting changes behaviour; purge rules
│   ├── test_on_demand.py     # Deferred BLOBs, memory saved, catalogue cache, backup snapshot
│   ├── test_search.py        # Search, filters, sorting, pagination
│   ├── test_security.py      # Login lockout, headers, secret key, foreign keys
│   ├── test_skin.py          # Skin switch on every page, configurable default, skeuo CSS cannot leak into Glass
│   ├── test_contrast.py      # WCAG 4.5:1 on every text/background colour token, both looks, both themes
│   └── test_transitions.py   # Page transitions: reduced motion honoured, downloads never intercepted, nothing left hidden
└── library_management_system/ # Original CLI prototype (reference only)
```

---

## Requirements

- **Python 3.9+**
- Dependencies listed in `requirements.txt`:
  - Flask, Flask-SQLAlchemy, Flask-Login, Flask-WTF
  - Pillow (image compression)
  - openpyxl (Excel exports)

## Setup & Run

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Seed demo data — 40 books with compressed covers
python seed.py

# 3. Run the application
python run.py
```

The app starts at **http://127.0.0.1:5000**.

---

## Default Accounts

| Role | Username | Password | Access |
|------|----------|----------|--------|
| **Admin** | `admin` | `admin123` | Full access: settings, performance, purge, staff management |
| **Librarian** | `librarian` | `librarian123` | Books, members, transactions, fines, reports |
| **Member** | `member` | `member123` | Browse catalogue, view own loans/fines, renew books |

Default accounts are auto-created on first launch. New members can self-register via `/register`.

**These passwords are public (they are in this file). Change them under *Change Password* before anyone else can reach the app.** After you sign in with one of them, the app shows a reminder.

### Security notes (read before putting this online)

- This is a college project that runs on your own computer (`127.0.0.1`). It is **not** hardened for the public internet.
- Debug mode is **off** by default. Turn it on only on your own machine with `FLASK_DEBUG=1`; never on a server, because the debugger lets anyone who can open a page run code.
- The demo passwords above are public. Change them, or delete those accounts, before anyone else can reach the app.
- `instance/` (database and secret key), `uploads/` and `backups/` are listed in `.gitignore`. Do not commit them.
- Known limits: plain HTTP only (use a TLS proxy for anything real), no Content-Security-Policy header, sign-in lockout counters live in memory and reset on restart. See `CHANGES.md`, section 6.
- Dependencies were checked with `pip-audit` on 19 Oct 2026 and pinned to patched versions. Run `pip-audit -r requirements.txt` again before reuse.

The session-signing key is read from the `SECRET_KEY` environment variable. If it is not set, a random key is generated once and kept in `instance/secret.key`. Keep that file private and out of version control.

---

## Web Interface Features

### Public
- Landing page with library statistics and featured books
- Public catalogue with search (title, author or ISBN), filter by author/category/availability, sort (title, author name, year, availability, newest), and pagination

### Member
- Personal dashboard with active loans and due dates
- Self-service book renewal
- Fine history, a running estimate of the fine on books that are already overdue, and a notification inbox

### Librarian / Staff
- Full book CRUD with cover image upload (auto-compressed)
- Member management (add, edit, suspend/deactivate)
- Transaction workflow: issue → renew → return (with automatic fine calculation)
- Overdue tracking: filter the loan list to books that are late and not yet returned, each showing the fine accrued so far
- Fine collection and payment tracking
- Dashboard charts: loans per day (14 days), titles per category, paid vs. unpaid fines, overdue exposure
- Reports dashboard with CSV/Excel export
- A title with loan history cannot be deleted (the history is kept). Set its quantity to 0 to take it off the shelf

### Admin
- **Q17 Performance Monitor** — real-time memory metrics, compression stats, cache analytics, eager-vs-lazy benchmark; the **Console view** shows the same live numbers as dials and read-outs
- **Database Maintenance** — purge old transactions/logs (minimum 30 days; loans with an unpaid fine are always kept; each purge can save a timestamped CSV copy, fines included, in `backups/archives/`), VACUUM, integrity check
- **Backup & Restore** — create/restore SQLite snapshots
- **System Settings** — loan period, fine rate, renewals, member limit, cache size and lifetime, image quality and size, page size, retention. Every value is range-checked, and one bad value saves nothing
- **Staff Management** — create/edit staff accounts
- **Activity Logs** — full audit trail

---

## Look and Feel: Glass and Skeuomorphic

| | Glass (default) | Skeuomorphic |
|---|---|---|
| Idea | Frosted translucent panels over a soft colour mesh, spring animations | Brushed-metal chassis, paper panels, raised keys, LED/LCD read-outs |
| Light and dark | Yes | Yes (separate palettes, kept in step by a test) |
| Phone layout | Yes | Yes |

**Switching.** Use the toggle in the top bar (signed in), in the public navigation, or the *Skeuomorphic style* switch on the landing page. The choice is remembered per browser (`localStorage`, read inside a try/catch so a blocked store cannot break the page). Light/dark is a separate toggle and also remembered.

**Changing the default** (what a first-time visitor sees) without touching code:

```bash
# Linux / macOS
LMS_DEFAULT_SKIN=skeuo python run.py
# Windows (PowerShell)
$env:LMS_DEFAULT_SKIN = "skeuo"; python run.py
```

Anything other than `skeuo` falls back to `glass`.

**How it works.** `<html data-skin="glass|skeuo">` is set by a tiny inline script in `<head>` before first paint, so there is no flash of the wrong look. `skeuo-app.css` is always linked but every selector starts with `html[data-skin="skeuo"]`, so it cannot change the Glass look (a test checks every selector, and a pixel comparison of 24 pages showed no difference beyond render noise).

**Page transitions.** Every page change is animated, in both looks:
- *Leaving:* Chrome, Edge and Safari cross-fade from the old page to the new one (a cross-document view transition, one CSS rule); the side bar and top bar stay put and only the active link moves. Firefox has no such feature, so a short fade-out in `liquid-glass.js` does the job instead.
- *Arriving:* the page header and then each block below it rise into place one after another, and the first rows of a table fill in. The Skeuomorphic look settles with a slight mechanical overshoot.
- *Loading line:* a thin line (a lit LED strip in Skeuomorphic) runs along the top while the next page loads.
- *Never touched:* downloads (CSV/Excel exports, cover images), Ctrl/Shift/middle clicks, links that open a new tab, in-page anchors, dropdown toggles. If you cancel a "are you sure?" prompt, nothing animates.
- *Accessibility and weak machines:* with the operating system's "reduce motion" setting all of it is off. The *lite* effects switch shortens it. Every animation ends fully visible, so a script that fails to load cannot leave a blank page.
- *Tuning:* the timing is three variables at the top of section 16 of `liquid-glass.css` (`--pt-dur`, `--pt-step`, `--pt-ease`). To remove the effect completely, delete that section.

**Phones.** Below 576 px every data table turns into stacked cards (one card per row, each cell labelled), so nothing needs sideways scrolling. Between 992 and 1599 px table padding is tightened so action buttons are no longer clipped; at 992-1279 px (for example a tablet held sideways) the wider tables (books, members, loans, fines, a member's loan history, the librarian dashboard) still scroll sideways inside their card instead of squeezing. Measured: none do at 1280 px and wider.

**Contrast, measured, not assumed.** `e2e/contrast_audit.py` photographs every page with the text hidden, so it knows the real colour under each word (gradients, blur and grain included), then applies WCAG 2.x (4.5:1 normal text, 3:1 large). Run over 24 pages x 2 looks x 2 themes x desktop/phone, the last pass showed **0 failures** in Skeuomorphic and Glass except the items listed under *Known limits* below. Before this work the Glass default had roughly 300 failures on desktop-light (mostly grey-on-glass secondary text), so some Glass colours were adjusted slightly (a deeper blue, darker secondary text, a scrim behind the landing-page cover).

## Security and Data Integrity

| Area | What the code does |
|------|--------------------|
| Passwords | Hashed with Werkzeug (salted). Sign-in errors never say which half was wrong |
| Brute force | 5 wrong passwords for one username from one address lock that pair for 15 minutes (HTTP 429). 20 from one address, across any usernames, lock the address. The counter table is bounded, so it cannot grow without limit |
| Sessions | Random signing key, cookies are HttpOnly and SameSite=Lax, CSRF token on every form |
| Access control | Every route checks the role on the server. Hiding a menu item is never the only check |
| Redirects | `?next=` on the login page only follows paths on this site |
| Uploads | Pillow must be able to open the file as an image, or it is refused. The size limit comes from Settings (hard ceiling 16 MB) |
| Headers | `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` |
| Database | Foreign keys are enforced by SQLite itself. A book that has been loaned cannot be deleted. Settings are range-checked before anything is saved |
| Backups | File names are matched against a strict pattern, a backup must pass `PRAGMA integrity_check` before it replaces the live database, and a safety copy of the current database is taken first |

Not covered, and worth knowing: the app speaks plain HTTP (put it behind a TLS proxy before exposing it), there is no Content-Security-Policy, sign-out is a plain link rather than a form post, and the lockout table lives in the memory of one process, so it resets when the server restarts and is not shared between several worker processes.

---

## Running Tests

```bash
# Run all 246 tests (about 3 minutes)
python -m pytest -v

# Run only Q17 feature tests
python -m pytest tests/test_q17.py -v
```

### Test Coverage

| Module | Tests | Status |
|--------|-------|--------|
| Authentication | 6 | ✅ |
| Books CRUD | 7 | ✅ |
| Authors & Categories | 5 | ✅ |
| Members | 4 | ✅ |
| Transactions | 7 | ✅ |
| Fines | 2 | ✅ |
| Q17 Features | 13 | ✅ |
| Reports & Exports | 9 | ✅ |
| Permissions & RBAC | 9 | ✅ |
| Gap-closing: overdue fines, dashboard analytics, catalogue search/sort/pages, notifications, settings, backup/restore, data integrity | 37 | ✅ |
| Settings take effect; purge keeps unpaid fines and never overwrites an archive | 17 | ✅ |
| Security: lockout, headers, secret key, foreign keys, safe export, JS escaping | 15 | ✅ |
| On-demand loading and query cache, measured on the real routes | 16 | ✅ |
| Search, filtering, sorting, pagination | 12 | ✅ |
| Skin switch: present on every page, default configurable, Skeuomorphic CSS fully scoped | 21 | ✅ |
| Colour-token contrast, both looks, both themes | 42 | ✅ |
| Page transitions: motion rules, what is never intercepted, nothing left hidden | 24 | ✅ |
| **Total** | **246** | **All passing** |

---

## Notes for Report / Viva

- The **Q17 Performance page** (`/admin/performance`) provides live, measured memory metrics using Python's `tracemalloc` — real evidence for the "Reduce Memory Usage" quality goal.
- The eager-vs-lazy benchmark demonstrates measurable peak memory reduction (**94%** on the 40-book demo data; run it on your own data and quote that number).
- All compressed data is losslessly round-trippable — verified by tests.
- The LRU cache is bounded and thread-safe — it accelerates reads without becoming a memory leak.
- The two interface looks are a design choice, not a Q17 feature. The Q17 evidence is the Performance page and the measurements above.
- **Known limits of the UI work:** (1) two measurements are not fixed and are disclosed rather than hidden: on the landing page at phone width the title of one decorative book cover in the Skeuomorphic hero sits behind a floating tag (decorative, not content); the dashboard 'Add Member' button was flagged once at 3.38:1 but a pixel probe of the button at rest shows every pixel at 5.2:1 or better, so it is treated as a scroll-position artefact of the audit; (2) the page transitions were checked on real navigations in Chromium only. The Firefox fade-out path was forced and tested in Chromium, but never run in Firefox itself; the screenshots and contrast numbers were taken in Chromium with locally served fonts, other browsers and the real web fonts were not measured; (3) the audit measures text, not icons or focus rings.
- Database engine is **SQLite** — zero server setup. Swap to MySQL/PostgreSQL by changing only `SQLALCHEMY_DATABASE_URI`.
