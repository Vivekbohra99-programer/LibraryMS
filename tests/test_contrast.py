"""Colour-token contrast (WCAG 2.x, 4.5:1 for normal text) for both looks and both themes.

These are flat-colour checks on the tokens. The browser audit (e2e/contrast_audit.py) measures real rendered pixels
over gradients and blur; this file keeps the tokens from drifting back below the line."""
import colorsys
import os
import re

import pytest

CSS = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'css')


def _css(name):
    with open(os.path.join(CSS, name), encoding='utf-8') as fh:
        return fh.read()


def _block(css, start, end):
    return css[css.index(start):css.index(end, css.index(start) + 1)]


def _hex(block, token):
    m = re.search(re.escape(token) + r':\s*(#[0-9a-fA-F]{6})', block)
    assert m, f'{token} not found'
    return _rgb(m.group(1))


def _rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(c):
    def lin(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])


def ratio(a, b):
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


SK = _css('skeuo-app.css')
SK_LIGHT = _block(SK, 'html[data-skin="skeuo"] {', 'html[data-skin="skeuo"][data-theme="dark"] {')
SK_DARK = _block(SK, 'html[data-skin="skeuo"][data-theme="dark"] {', '/* 1 ')


@pytest.mark.parametrize('fg,bg', [
    ('--sk-ink', '--sk-desk'), ('--sk-ink-2', '--sk-desk'), ('--sk-ink-3', '--sk-desk'),
    ('--sk-ink', '--sk-face'), ('--sk-ink-2', '--sk-face'), ('--sk-ink-3', '--sk-face'),
    ('--sk-ink', '--sk-paper'), ('--sk-ink-3', '--sk-paper'), ('--sk-ink', '--sk-field'),
    ('--sk-ink-3', '--sk-plate'), ('--sk-led-ink', '--sk-plate'), ('--sk-led-ink', '--sk-face'),
    ('--lg-t-success', '--sk-plate'), ('--lg-t-danger', '--sk-plate'), ('--lg-t-warning', '--sk-plate'), ('--lg-t-info', '--sk-plate'),
    ('--lg-t-success', '--sk-paper'), ('--lg-t-danger', '--sk-paper'),
])
def test_skeuo_light_tokens(fg, bg):
    assert ratio(_hex(SK_LIGHT, fg), _hex(SK_LIGHT, bg)) >= 4.5


@pytest.mark.parametrize('fg,bg', [
    ('--sk-ink', '--sk-desk'), ('--sk-ink-2', '--sk-face'), ('--sk-ink-3', '--sk-face'), ('--sk-ink-3', '--sk-face-lo'),
    ('--sk-ink', '--sk-paper'), ('--sk-ink-3', '--sk-paper'), ('--sk-ink', '--sk-field'), ('--sk-ink-3', '--sk-plate'),
    ('--lg-t-success', '--sk-plate'), ('--lg-t-danger', '--sk-plate'), ('--lg-t-warning', '--sk-plate'), ('--lg-t-info', '--sk-plate'),
    ('--lg-accent-text', '--sk-plate'),
])
def test_skeuo_dark_tokens(fg, bg):
    # tokens the dark block does not redefine are inherited from the light block
    def pick(tok):
        m = re.findall(re.escape(tok) + r':\s*(#[0-9a-fA-F]{6})', SK_DARK)
        return _rgb(m[-1]) if m else _hex(SK_LIGHT, tok)
    assert ratio(pick(fg), pick(bg)) >= 4.5


def test_skeuo_lcd_ink_on_lcd_glass():
    for ink in ('#72f7da', '#8dffb0', '#ff958d', '#ffd37a', '#8fd0ff'):
        assert ratio(_rgb(ink), _rgb('#0d1719')) >= 7


def _hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h / 360, l / 100, s / 100)
    return (round(r * 255), round(g * 255), round(b * 255))


G = _css('liquid-glass.css')
G_LIGHT = _block(G, ':root {', '[data-theme="dark"] {')


def test_glass_accent_carries_white_button_text():
    hue = int(re.search(r'--lg-hue:\s*(\d+)', G_LIGHT).group(1))
    light = float(re.search(r'--lg-l:\s*([\d.]+)%', G_LIGHT).group(1))
    assert ratio((255, 255, 255), _hsl(hue, 100, light)) >= 4.5


@pytest.mark.parametrize('preset', ['indigo', 'violet', 'rose', 'emerald'])
def test_glass_accent_presets_carry_white_text(preset):
    m = re.search(r'\[data-accent="%s"\]\s*\{\s*--lg-hue:\s*(\d+);\s*--lg-l:\s*(\d+)%%' % preset, G)
    assert m
    assert ratio((255, 255, 255), _hsl(int(m.group(1)), 100, int(m.group(2)))) >= 4.5


@pytest.mark.parametrize('tok', ['--lg-t-success', '--lg-t-danger', '--lg-t-warning', '--lg-t-info'])
def test_glass_status_text_on_light_surface(tok):
    # badges are a 15% tint of the status colour over glass over the mesh; #dfe6f6 is a typical darkish mesh area
    assert ratio(_hex(G_LIGHT, tok), _rgb('#d3d8ec')) >= 4.5


def test_glass_semantic_buttons_carry_white_text():
    for tok in ('--lg-success', '--lg-danger'):
        assert ratio((255, 255, 255), _hex(G_LIGHT, tok)) >= 4.5
