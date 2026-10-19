/* LibraryMS performance console: draws the dial gauges from data-* attributes and handles the day/night switch.
   No dependencies. Every number the gauges show is also printed in the page, so nothing depends on this script. */
(function () {
  'use strict';
  var root = document.documentElement, NS = 'http://www.w3.org/2000/svg';
  var $ = function (s) { return document.querySelector(s); };

  /* ── theme: shares the app's own 'lg-theme' key (light | dark | auto) ── */
  var sw = $('#theme'), lbl = $('#themeLbl');
  function isDark() { var t = root.getAttribute('data-theme'); return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches; }
  function syncTheme() { var d = isDark(); if (sw) sw.setAttribute('aria-checked', String(d)); if (lbl) lbl.textContent = d ? 'night' : 'day'; }
  if (sw) sw.addEventListener('click', function () {
    var next = isDark() ? 'light' : 'dark';
    root.setAttribute('data-theme', next);
    try { localStorage.setItem('lg-theme', next); } catch (e) {}
    syncTheme();
  });
  syncTheme();

  /* ── gauges ── */
  function el(name, attrs, text) { var e = document.createElementNS(NS, name); for (var k in attrs) e.setAttribute(k, attrs[k]); if (text) e.textContent = text; return e; }
  function pt(cx, cy, r, deg) { var a = (deg - 90) * Math.PI / 180; return [cx + r * Math.cos(a), cy + r * Math.sin(a)]; }
  // Smallest "neat" maximum at or above x, so the four quarter marks read 0.3, 0.4, 0.5, 0.6, 0.8, 1 ... times a power of ten.
  function nice(x) {
    if (!(x > 0)) return 1;
    var e = Math.floor(Math.log10(x)), m = x / Math.pow(10, e), S = [1.2, 1.6, 2, 2.4, 3.2, 4, 4.8, 6.4, 8, 10];
    for (var i = 0; i < S.length; i++) if (S[i] >= m - 1e-9) return S[i] * Math.pow(10, e);
    return 10 * Math.pow(10, e);
  }
  function fmt(v) {
    if (Math.abs(v) >= 1000) return String(Math.round(v / 100) / 10) + 'k';   // 16000 -> 16k, keeps small dials legible
    return (Math.abs(v) >= 10 || v === Math.round(v)) ? String(Math.round(v * 10) / 10) : v.toFixed(1);
  }

  var A0 = -120, SPAN = 240, CX = 100, CY = 104;
  function build(g) {
    var val = parseFloat(g.getAttribute('data-value')) || 0;
    var markAttr = g.getAttribute('data-mark'), mark = markAttr === null ? null : parseFloat(markAttr);
    var maxAttr = g.getAttribute('data-max'), max = (maxAttr && maxAttr !== 'auto') ? parseFloat(maxAttr) : nice(Math.max(val, mark || 0) * 1.2);
    var svg = el('svg', { viewBox: '0 0 200 200', 'aria-hidden': 'true' });
    for (var i = 0; i <= 24; i++) {
      var d = A0 + SPAN * i / 24, major = i % 6 === 0, a = pt(CX, CY, 78, d), b = pt(CX, CY, major ? 64 : 70, d);
      svg.appendChild(el('line', { x1: a[0], y1: a[1], x2: b[0], y2: b[1], stroke: 'currentColor', 'stroke-width': major ? 2.4 : 1, style: 'color:var(--dial-ink)' }));
      if (major) { var t = pt(CX, CY, 51, d); svg.appendChild(el('text', { x: t[0], y: t[1] + 4, 'text-anchor': 'middle', 'font-size': 12, 'font-weight': 800 }, fmt(i / 24 * max))); }
    }
    svg.appendChild(el('text', { x: 100, y: 166, 'text-anchor': 'middle', 'font-size': 11, 'font-weight': 800 }, g.getAttribute('data-unit') || ''));
    if (mark !== null && !isNaN(mark)) {      // red tab on the rim = the recorded peak
      var md = A0 + SPAN * Math.min(1, mark / max), m1 = pt(CX, CY, 80, md), m2 = pt(CX, CY, 91, md);
      svg.appendChild(el('line', { x1: m1[0], y1: m1[1], x2: m2[0], y2: m2[1], stroke: '#d93232', 'stroke-width': 4.5, 'stroke-linecap': 'round' }));
    }
    var needle = el('g', { 'class': 'needle' });
    needle.appendChild(el('polygon', { points: '97,104 100,34 103,104', fill: '#d93232', style: 'filter:drop-shadow(2px 3px 2px rgba(0,0,0,.35))' }));
    needle.appendChild(el('circle', { cx: CX, cy: CY, r: 9, fill: '#555a5e', stroke: '#2a2d30', 'stroke-width': 1.5 }));
    needle.appendChild(el('circle', { cx: CX, cy: CY, r: 3.4, fill: '#cfd3d5' }));
    svg.appendChild(needle);
    needle.style.transform = 'rotate(' + A0 + 'deg)';
    g.appendChild(svg);
    // One deliberate moment: the needles swing up from zero once the page has painted.
    requestAnimationFrame(function () { requestAnimationFrame(function () {
      needle.style.transform = 'rotate(' + (A0 + SPAN * Math.max(0, Math.min(1, val / max))) + 'deg)';
    }); });
  }
  Array.prototype.forEach.call(document.querySelectorAll('.gauge[data-value]'), build);

  /* ── benchmark key: the run takes a few seconds, so say so ── */
  var form = $('#benchForm'), msg = $('#runMsg');
  if (form) form.addEventListener('submit', function () {
    var b = form.querySelector('button'); if (b) { b.disabled = true; b.setAttribute('aria-busy', 'true'); }
    if (msg) msg.textContent = 'benchmark running, please wait';
  });
})();
