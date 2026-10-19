"""The Glass / Skeuomorphic switch: present everywhere, scoped so glass is untouched, default configurable."""
import importlib
import os
import re

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
CSS_DIR = os.path.join(ROOT, 'app', 'static', 'css')
JS_FILE = os.path.join(ROOT, 'app', 'static', 'js', 'liquid-glass.js')


def _read(path):
    with open(path, encoding='utf-8') as fh:
        return fh.read()


# ---------- the switch is on every kind of page ----------

@pytest.mark.parametrize('path', ['/', '/login', '/register', '/catalogue'])
def test_public_pages_have_the_switch_and_the_stylesheet(client, path):
    html = client.get(path).get_data(as_text=True)
    assert 'data-lg-skin-toggle' in html
    assert 'css/skeuo-app.css' in html


def test_admin_dashboard_has_the_switch(admin_client):
    html = admin_client.get('/dashboard').get_data(as_text=True)
    assert 'data-lg-skin-toggle' in html and 'css/skeuo-app.css' in html


def test_member_dashboard_has_the_switch(member_client):
    assert 'data-lg-skin-toggle' in member_client.get('/dashboard').get_data(as_text=True)


def test_stylesheet_is_served_as_css(client):
    r = client.get('/static/css/skeuo-app.css')
    assert r.status_code == 200 and 'text/css' in r.content_type
    r.close()


# ---------- the default look ----------

def test_default_is_glass(client):
    assert 'var k = "glass"' in client.get('/login').get_data(as_text=True)


def test_config_can_default_to_skeuo(app, client):
    app.config['DEFAULT_SKIN'] = 'skeuo'
    assert 'var k = "skeuo"' in client.get('/login').get_data(as_text=True)


@pytest.mark.parametrize('bad', ['neon', '', None, '"</script><script>alert(1)</script>', 'SKEUO'])
def test_unknown_default_falls_back_to_glass(app, client, bad):
    app.config['DEFAULT_SKIN'] = bad
    html = client.get('/login').get_data(as_text=True)
    assert 'var k = "glass"' in html
    assert 'alert(1)' not in html


def test_environment_variable_sets_the_default(monkeypatch):
    import config
    try:
        monkeypatch.setenv('LMS_DEFAULT_SKIN', '  Skeuo ')
        assert importlib.reload(config).Config.DEFAULT_SKIN == 'skeuo'
        monkeypatch.setenv('LMS_DEFAULT_SKIN', 'banana')
        assert importlib.reload(config).Config.DEFAULT_SKIN == 'glass'
        monkeypatch.delenv('LMS_DEFAULT_SKIN')
        assert importlib.reload(config).Config.DEFAULT_SKIN == 'glass'
    finally:
        monkeypatch.undo()
        importlib.reload(config)


def test_head_script_survives_blocked_storage(client):
    """localStorage can throw (private windows); the skin choice must be read inside try/catch."""
    html = client.get('/login').get_data(as_text=True)
    m = re.search(r"try \{ var saved = localStorage\.getItem\('lg-skin'\)", html)
    assert m, 'saved skin must be read inside a try block'


# ---------- the skeuo stylesheet cannot leak into the glass look ----------

def _selectors(css):
    """Every top-level selector of every rule, including rules nested in @media."""
    css = re.sub(r'/\*.*?\*/', '', css, flags=re.S)
    out = []

    def walk(text):
        pos = 0
        while True:
            b = text.find('{', pos)
            if b < 0:
                return
            head = text[pos:b].strip()
            depth, j = 1, b + 1
            while depth and j < len(text):
                depth += {'{': 1, '}': -1}.get(text[j], 0)
                j += 1
            body = text[b + 1:j - 1]
            if head.startswith(('@media', '@supports')):
                walk(body)
            elif head.startswith('@'):
                out.append(head)             # @keyframes, @font-face... would be global
            else:
                parts, d, cur = [], 0, ''
                for ch in head:              # split on commas that are not inside :is( ) / :not( )
                    if ch in '([':
                        d += 1
                    elif ch in ')]':
                        d -= 1
                    if ch == ',' and d == 0:
                        parts.append(cur.strip())
                        cur = ''
                    else:
                        cur += ch
                parts.append(cur.strip())
                out.extend(parts)
            pos = j

    walk(css)
    return out


def test_every_skeuo_selector_is_scoped():
    sels = _selectors(_read(os.path.join(CSS_DIR, 'skeuo-app.css')))
    assert len(sels) > 200
    loose = [s for s in sels if 'html[data-skin="skeuo"]' not in s]
    assert not loose, f'selectors that would also hit the glass look: {loose[:5]}'


def test_scoper_catches_an_unscoped_rule():
    assert _selectors('.card { color: red } html[data-skin="skeuo"] .x { color: red }')[0] == '.card'


def test_dark_tokens_mirror_the_light_tokens():
    """Both themes must define the same colour tokens, or a page can show one theme's ink on the other's metal."""
    css = _read(os.path.join(CSS_DIR, 'skeuo-app.css'))
    light = css[css.index('html[data-skin="skeuo"] {'):css.index('html[data-skin="skeuo"][data-theme="dark"] {')]
    dark = css[css.index('html[data-skin="skeuo"][data-theme="dark"] {'):css.index('/* 1 ')]
    must_flip = ['--sk-desk', '--sk-face', '--sk-paper', '--sk-field', '--sk-plate', '--sk-ink', '--sk-ink-2', '--sk-ink-3',
                 '--sk-key', '--sk-well', '--lg-t-danger', '--lg-surface']
    for tok in must_flip:
        assert re.search(re.escape(tok) + r'\s*:', light), f'{tok} missing in light block'
        assert re.search(re.escape(tok) + r'\s*:', dark), f'{tok} missing in dark block'


# ---------- script ----------

def test_script_exposes_the_switch():
    js = _read(JS_FILE)
    for needle in ("lg-skin", "setSkin", "data-lg-skin-toggle", "data-skin"):
        assert needle in js
    assert re.search(r'LG\s*=\s*\{[^}]*setSkin', js, re.S) or 'setSkin: setSkin' in js or 'setSkin:' in js


def test_accent_swatches_are_hidden_in_skeuo():
    css = _read(os.path.join(CSS_DIR, 'skeuo-app.css'))
    assert '.lg-accent-row' in css
    assert 'lg-accent-row' in _read(os.path.join(ROOT, 'app', 'templates', 'landing.html'))
