# CHANGES — Library Management System (Q17: Reduce Memory Usage)

This file lists what changed compared with the project you gave me, what was found broken and fixed, and what is still **not** done. It is not the TQM report.

## 1. Status of the 18 requirement-sheet items

| # | Item | Status | Where to see it |
|---|------|--------|-----------------|
| 1 | Dashboard and Analytics | Done. Role-based dashboards; charts (loans per day, titles per category, paid vs unpaid fines, overdue exposure) computed with SQL aggregates only | `app/services/analytics.py`, `partials/analytics_panel.html` |
| 2 | Book Management and Inventory | Done. CRUD, cover upload (validated, resized, compressed), duplicate-ISBN check. A title with loan history cannot be deleted; set quantity 0 to retire it | `routes/books.py` |
| 3 | Member Management | Done. Add, edit, suspend, profile with loan history, self-registration | `routes/members.py` |
| 4 | Book Issue, Return and Renewal | Done. Member limit, renewal limit, loan period are Settings; a member cannot renew someone else's loan | `routes/transactions.py` |
| 5 | Overdue Tracking and Fine Management | Done. Overdue filter, whole-day fine, **accrued fine shown on loans still out**, fine collected on payment | `models/transaction.py`, `routes/fines.py` |
| 6 | Authentication and RBAC | Done. Admin / Librarian / Member, every route checks the role on the server | `routes/auth.py`, `tests/test_permissions.py` |
| 7 | Search, Filtering, Sorting, Pagination | Done. Title, author or ISBN; author/category/availability filters; 5 sorts; page size from Settings | `services/catalogue.py`, `tests/test_search.py` |
| 8 | Reports and Data Export | Done. CSV and Excel; spreadsheet formula injection neutralised | `routes/reports.py`, `services/export.py` |
| 9 | Asset Compression | Done. `zlib` for descriptions, Pillow resize + re-encode for covers | `services/compression.py` |
| 10 | On-Demand Data Loading | Done. The two BLOB columns are deferred, so list pages never read them | `models/book.py` |
| 11 | Database Purge Tools | Done. Minimum 30 days, unpaid-fine loans never purged, optional CSV archive, VACUUM, integrity check | `services/purge.py` |
| 12 | Query Caching | Done. Bounded LRU + TTL cache of ids and counts, cleared on every write | `services/cache.py` |
| 13 | Memory and Performance Monitoring | Done. Performance page, Console view (dials), eager-vs-lazy benchmark | `routes/admin.py`, `services/memory.py` |
| 14 | Responsive UI, Light and Dark | Done. Two looks (Glass, Skeuomorphic) x light/dark x desktop/phone; phone tables become cards | see section 3 |
| 15 | Database Backup and Recovery | Done. Snapshots, strict file-name pattern, integrity check before restore, safety copy first | `services/purge.py` |
| 16 | Security and Data Integrity | Done, with listed limits (section 5) | README "Security and Data Integrity" |
| 17 | Automated Testing and QA | Done. 246 pytest tests, plus a 123-check live end-to-end pass against the unzipped package | `tests/`, `e2e/` (not in the zip) |
| 18 | Project Documentation and TQM Report | **README and this file are done. The TQM report is NOT written**, by your instruction | — |

## 2. Settings that now have an effect

Every value on the Settings page changes behaviour, is range-checked, and one bad value saves nothing: loan period, renewals, member loan limit, fine per day, cache lifetime and capacity, cover JPEG quality, largest cover side, largest upload, rows per page, log retention, returned-loan retention. `tests/test_settings_effects.py` proves each one.

## 3. The two looks

- **Glass** is still the default. **Skeuomorphic** is a complete second skin for every page. Switch from the top bar, the public navigation, or the landing page; the choice is remembered per browser.
- Default can be changed with the environment variable `LMS_DEFAULT_SKIN=skeuo` (anything else means glass).
- Every skeuo rule is scoped to `html[data-skin="skeuo"]`; a test checks each selector, and a pixel comparison of 24 pages showed the Glass look unchanged by the new stylesheet beyond render noise.
- Phones (below 576 px): tables turn into labelled cards. Laptops (992–1599 px): table padding tightened.
- I did change the shared Glass look slightly to pass contrast: deeper blue accent, darker secondary text, a scrim behind the landing-page cover, tighter table padding at laptop widths, a dark backing behind the top-bar search field in dark mode.

## 3a. Page transitions (added after the first delivery)

Every page change is now animated: a cross-fade out (Chromium/Safari view transitions; a JS fade-out elsewhere), then the header and blocks rise in one after another and the first table rows fill in; a thin loading line runs along the top. Both looks have it (Skeuomorphic settles with a small overshoot and an amber LED line). Downloads, modified clicks, new-tab links and anchors are never intercepted; "reduce motion" switches it off; the lite effects mode shortens it. Details and tuning: README, *Look and Feel*.

How it was checked: 24 new tests (`tests/test_transitions.py`); 21 live checks on real navigations in Chromium in all four look/theme combinations (view transition actually ran, blocks stagger, rows fill in, nothing left hidden or transformed, exports download untouched, Ctrl+click ignored, back button not stuck mid-fade, reduced motion collapses it); and screen recordings of a real page change in both looks. One bug of my own was found this way and fixed before delivery: the first version could flash the new page fully visible and then restart its entrance; the styles now apply from the first paint.

Not verified: Firefox and Safari themselves (the Firefox path was forced and tested inside Chromium). Smoothness was judged on software rendering; frame rate on a real GPU should be better, not worse. If any page feels slow on your machine, set the *lite* effects switch, or remove section 16 of `liquid-glass.css`.

## 4. Bugs found by testing and fixed

Found while rendering and measuring, not by reading code:

1. **Transactions table clipped its Return button** at 1440 px and below, in both looks. Fixed with laptop-width table compaction.
2. **About 300 text-contrast failures in the Glass default** on desktop-light (grey on frosted glass). Now 1 flagged item, which is a measurement artefact (section 5).
3. **Skeuo LCD value invisible** when it used `.text-success`.
4. **Many skeuo contrast failures**: mid-grey metal cannot carry three text tones at 4.5:1, so the inks were darkened.
5. **Hovered links turned raw accent blue** on dark rows (1.5:1). They now keep the readable text colour.
6. **Eyebrow lamp rendered as a sliver** when the eyebrow was `display:block`.
7. **Dark mode:** search placeholder (3.84:1 over a blue patch), outline buttons (4.42:1), skeuo "Deactivate" (4.45:1).
8. On phones, a card whose cell was empty (the Actions of a returned loan) showed a bare label; it now shows a dash.
9. Landing title, description and footer said "Liquid Glass" even in the Skeuomorphic look; wording made neutral.

Earlier in the project (see the README for detail): login lockout, security headers, random persisted secret key, safe `?next=`, upload validation, strict backup restore, SQLite foreign keys, spreadsheet formula injection, deferred BLOBs, cache invalidation on writes, accrued-fine display, purge protecting unpaid fines.

## 5. Measured results

| Check | Result |
|-------|--------|
| pytest | **246 passed** (159 before this round + 87 new: 21 skin, 42 contrast, 24 page transitions) |
| Live end-to-end against the unzipped package, fresh database | 123 checks (see section 6 for the final run) |
| Contrast audit, real pixels, 24 pages, Glass and Skeuo, light and dark, 1440 px and 390 px | **0 failing** in 6 of 8 combinations |
| Remaining flagged items | (a) Glass light 1440: dashboard "Add Member" reported at 3.38:1 once. A pixel probe of that button at rest shows every pixel at 5.2:1 or better, so I treat it as a scroll-position artefact, but I did not reproduce the number. (b) Skeuo light 390: a title on a decorative book cover in the landing hero sits behind a floating tag. Decorative, not content |
| Q17 numbers | In README ("How These Features Reduce Memory"). They vary with data and machine; re-measure on the Performance page before quoting |

## 6. Not done / limits

- **TQM report** — not written (you said to finish the main project). I can produce a Word report from the real measured numbers if you want it.
- **Browsers and devices:** checked in Chromium only. Firefox, Safari and real phones were not tested. Screenshots used locally served fonts.
- **Contrast audit covers text only**, not icons, borders or focus rings.
- **Wide tables** still scroll sideways inside their card at 992–1279 px (measured at 1024 px: books, members, loans, fines, a member's loan history and the librarian dashboard; none at 1280 px and wider). Phones are not affected, because tables become cards there.
- **Security limits:** plain HTTP (use a TLS proxy), no Content-Security-Policy, sign-out is a link not a POST, lockout counters live in one process's memory and reset on restart.
- **Default passwords are public** (`admin123`, `librarian123`, `member123`). Change them before anyone else can reach the app.
- **SQLite** only; fine for a college project, not for many concurrent writers.

## 7. How to apply

**Easiest:** unzip `library_final.zip` as a new folder, then copy your old `instance/library.db` into its `instance/` folder if you want to keep your data. There are no database schema changes, so an existing database works as is.

**Or patch your current folder** with `changed_files.zip`:
1. Close the running server and **back up the whole project folder** (and `instance/library.db`).
2. Unzip `changed_files.zip` over your project. It only contains files that differ from the project you sent.
3. Do not delete `instance/`, `uploads/` or `backups/`.
4. `pip install -r requirements.txt` (unchanged, but harmless), then `python run.py`.
5. Hard-refresh the browser (Ctrl+F5) once so the new stylesheets (`liquid-glass.css?v=10`, `skeuo-app.css?v=4`, `liquid-glass.js?v=6`) load.

Then run `python -m pytest -q` (about 3 minutes). Expect 246 passed.

## 8. Files

**New:** `app/services/analytics.py`, `catalogue.py`, `throttle.py`; `app/static/css/skeuo-app.css`, `skeuo.css`; `app/static/js/skeuo.js`; `app/templates/admin/performance_console.html`; `app/templates/partials/analytics_panel.html`; `tests/test_completion.py`, `test_contrast.py`, `test_on_demand.py`, `test_search.py`, `test_security.py`, `test_settings_effects.py`, `test_skin.py`, `test_transitions.py`.

**Changed:** `README.md`, `config.py`, `app/__init__.py`, `app/extensions.py`, models (`book`, `setting`, `transaction`), routes (`admin`, `auth`, `authors`, `books`, `categories`, `dashboard`, `fines`, `members`, `reports`, `transactions`), services (`compression`, `export`, `purge`), `liquid-glass.css`, `liquid-glass.js`, and 32 templates (including `base.html`, which now wraps public pages in one `div`). The exact list is what `changed_files.zip` contains.

The verification scripts (`contrast_audit.py`, the live E2E, screenshot tools) live outside the project folder and are not in either zip.
