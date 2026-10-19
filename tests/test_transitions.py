"""Page transitions: arriving animation, cross-document view transition, loading line, and what they must never touch."""
import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding='utf-8') as fh:
        return fh.read()


GLASS = _read('app', 'static', 'css', 'liquid-glass.css')
SKEUO = _read('app', 'static', 'css', 'skeuo-app.css')
JS = _read('app', 'static', 'js', 'liquid-glass.js')
SECTION = GLASS[GLASS.index('/* 16 ─ PAGE TRANSITIONS'):]


# ---------- markup ----------

def test_public_pages_are_wrapped_for_the_fade(client):
    for path in ('/login', '/catalogue', '/'):
        assert 'class="lg-page"' in client.get(path).get_data(as_text=True), path


def test_signed_in_pages_keep_the_content_area(admin_client):
    assert 'class="app-content"' in admin_client.get('/dashboard').get_data(as_text=True)


def test_pre_paint_class_is_set_in_the_head_script(client):
    """If the class were added by the deferred script, the page would paint fully visible and then restart its entrance."""
    html = client.get('/login').get_data(as_text=True)
    head = html[:html.index('</head>')]
    assert "classList.add('lg-pt')" in head


def test_stylesheets_carry_new_cache_busters(client):
    html = client.get('/login').get_data(as_text=True)
    assert re.search(r'liquid-glass\.css\?v=(\d+)', html) and int(re.search(r'liquid-glass\.css\?v=(\d+)', html).group(1)) >= 10
    assert re.search(r'liquid-glass\.js\?v=(\d+)', html) and int(re.search(r'liquid-glass\.js\?v=(\d+)', html).group(1)) >= 6


# ---------- css ----------

def test_view_transition_is_opt_in_for_motion_only():
    m = re.search(r'@media \(prefers-reduced-motion: no-preference\)\s*\{[^@]*@view-transition\s*\{\s*navigation:\s*auto;?\s*\}', SECTION)
    assert m, '@view-transition must sit inside prefers-reduced-motion: no-preference'
    assert SECTION.count('@view-transition') == 1


def test_reduced_motion_switches_everything_off():
    assert re.search(r'@media \(prefers-reduced-motion: reduce\)\s*\{[^}]*animation-duration:\s*\.001ms\s*!important', GLASS)
    assert re.search(r'prefers-reduced-motion: reduce\)\s*\{\s*\.lg-progress\s*\{\s*display:\s*none', SECTION)


def test_entrance_rules_start_only_when_the_page_class_is_set():
    rules = re.findall(r'^([^\n{@/][^{]*)\{[^}]*animation:\s*lg-page-(?:in|fade)', SECTION, re.M)
    assert len(rules) >= 3
    assert all('.lg-pt' in r for r in rules), rules


def test_entrance_leaves_scroll_reveals_and_modals_alone():
    rule = re.search(r'\.lg-pt \.app-content > ([^{]+)\{', SECTION).group(1)
    for excluded in ('.lg-reveal', '.modal'):
        assert f':not({excluded})' in rule


def test_every_entrance_animation_ends_visible():
    """No fill-mode 'forwards'/'both' on the entrance and keyframes with only a from-state: a failure cannot hide content."""
    for name in ('lg-page-in', 'lg-page-fade'):
        kf = re.search(r'@keyframes ' + name + r'\s*\{(.*?)\}\s*(?=@|\.|$|\n)', SECTION, re.S).group(1)
        assert 'from' in kf and 'to' not in kf
    uses = re.findall(r'animation:\s*lg-page-(?:in|fade)[^;]*;', SECTION)
    assert uses and all('backwards' in u and 'forwards' not in u and 'both' not in u for u in uses)


def test_stagger_indices_are_defined_and_capped():
    idx = [int(n) for n in re.findall(r'\.lg-pt \.app-content > :nth-child\(\d+\) \{ --pi: (\d+);', SECTION)]
    assert idx == list(range(1, 8))
    assert '--pi: 8' in SECTION          # everything past the 8th block shares one delay


def test_lite_effects_mode_is_shorter():
    root = re.search(r':root \{ --pt-dur: ([\d.]+)s', SECTION)
    lite = re.search(r'\[data-fx="lite"\] \{ --pt-dur: ([\d.]+)s', SECTION)
    assert root and lite and float(lite.group(1)) < float(root.group(1))


def test_skeuo_only_changes_timing_and_the_loading_line():
    block = SKEUO[SKEUO.index('/* 13 ─ PAGE TRANSITIONS'):]
    assert '--pt-ease' in block and '.lg-progress' in block
    assert '--pt-dur' not in block         # lite mode must still be able to shorten the duration


# ---------- script ----------

def _download_regex():
    m = re.search(r'var DOWNLOADISH = /(.+)/i;', JS)
    assert m
    return re.compile(m.group(1), re.I)


def test_script_declares_what_it_never_intercepts():
    for needle in ("e.button !== 0", "e.metaKey", "e.ctrlKey", "e.shiftKey", "e.altKey", "hasAttribute('download')",
                   "a.target !== '_self'", "data-bs-toggle", "a.origin !== win.location.origin", "'pageshow'", 'CSSViewTransitionRule', 'reduceMotion'):
        assert needle in JS, needle


def test_every_download_route_is_excluded(app):
    rx = _download_regex()
    with app.test_request_context():
        rules = [r for r in app.url_map.iter_rules() if '/export/' in r.rule or r.rule.endswith('/cover')]
    assert len(rules) >= 6
    for r in rules:
        sample = re.sub(r'<[^>]+>', '1', r.rule)
        assert rx.search(sample), f'{sample} would be turned into a fade-out and a loading line'


@pytest.mark.parametrize('path', ['/books', '/dashboard', '/members/3', '/admin/performance', '/transactions?status=overdue',
                                  '/book/5', '/reports', '/catalogue?q=cover', '/admin/backups'])
def test_ordinary_pages_are_not_excluded(path):
    assert not _download_regex().search(path), path


def test_the_loading_line_cannot_run_forever():
    assert 'setTimeout(progressOff, 12000)' in JS
    assert 'setTimeout(function () { win.location.href = a.href; }, 160)' in JS
