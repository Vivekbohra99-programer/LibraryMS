/*! liquid-glass.js — behaviour layer for liquid-glass.css (vanilla, no dependencies)
 *
 *  Theme      [data-lg-theme-toggle]            light / dark / auto, persisted
 *  Skin       [data-lg-skin-toggle]             glass (default) / skeuo, persisted; <html data-skin>
 *  FX mode    [data-lg-fx-toggle]               full | lite (auto-picks lite on weak / reduced-motion devices)
 *  Accent     [data-lg-accent="violet"]         blue (default) indigo violet rose emerald orange
 *  Pointer    .card .glass .navbar .lg-shine    specular highlight follows the cursor (full fx only)
 *  Tilt       .lg-tilt                          subtle 3D tilt
 *  Count-up   [data-count="1280"]               animates once when scrolled into view
 *  Reveal     .lg-reveal                        fade/slide in on scroll (style="--i:2" to stagger)
 *  Tables     table.table-stack                 rows become labelled cards under 576px
 *  Loading    <form> submit                     spinner on the submit button (opt out: data-lg-no-loading)
 *  Toast      LG.toast("Saved", {type:"success"})
 *  Flash      .alert.alert-dismissible          auto-dismiss after a few seconds (opt out: data-lg-keep)
 *  Lens       .lg-lens                          Chromium-only edge refraction (SVG displacement map)
 *  Keys       "/" focuses search, Esc blurs it
 */
(function () {
  'use strict';

  var d = document, root = d.documentElement, win = window;
  var reduceMotion = win.matchMedia && win.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var finePointer  = win.matchMedia && win.matchMedia('(hover: hover) and (pointer: fine)').matches;

  function ls(k, v) {                       // localStorage that never throws
    try { if (v === undefined) return win.localStorage.getItem(k); if (v === null) win.localStorage.removeItem(k); else win.localStorage.setItem(k, v); } catch (e) {}
    return null;
  }
  function qa(sel, ctx) { return Array.prototype.slice.call((ctx || d).querySelectorAll(sel)); }
  function raf(fn) { return win.requestAnimationFrame(fn); }

  root.classList.add('lg-js');

  /* ── theme ─────────────────────────────────────────────────────────────── */
  var mqDark = win.matchMedia ? win.matchMedia('(prefers-color-scheme: dark)') : null;
  function resolveTheme(pref) { return pref === 'auto' || !pref ? (mqDark && mqDark.matches ? 'dark' : 'light') : pref; }
  function applyTheme(pref) {
    var t = resolveTheme(pref);
    root.setAttribute('data-theme', t);
    root.setAttribute('data-bs-theme', t);            // Bootstrap 5.3 built-ins follow
    root.setAttribute('data-theme-pref', pref || 'auto');
    qa('[data-lg-theme-toggle]').forEach(function (b) { b.setAttribute('aria-pressed', String(t === 'dark')); b.setAttribute('title', t === 'dark' ? 'Switch to light' : 'Switch to dark'); if (b.type === 'checkbox') b.checked = t === 'dark'; });
    lensRefreshSoon();
  }
  function setTheme(pref) { ls('lg-theme', pref); applyTheme(pref); }
  if (mqDark && mqDark.addEventListener) mqDark.addEventListener('change', function () { if ((ls('lg-theme') || 'auto') === 'auto') applyTheme('auto'); });

  /* ── accent ────────────────────────────────────────────────────────────── */
  function applyAccent(name) {
    if (!name || name === 'blue') root.removeAttribute('data-accent'); else root.setAttribute('data-accent', name);
    qa('[data-lg-accent]').forEach(function (b) { b.setAttribute('aria-pressed', String((b.getAttribute('data-lg-accent') || 'blue') === (name || 'blue'))); });
  }
  function setAccent(name) { ls('lg-accent', name === 'blue' ? null : name); applyAccent(name); }

  /* ── fx mode ───────────────────────────────────────────────────────────── */
  function autoFx() {
    var nav = win.navigator || {}, conn = nav.connection || {};
    var noTransparency = win.matchMedia && win.matchMedia('(prefers-reduced-transparency: reduce)').matches;
    var weak = (nav.hardwareConcurrency && nav.hardwareConcurrency <= 2) || (nav.deviceMemory && nav.deviceMemory <= 2);
    return (reduceMotion || noTransparency || conn.saveData || weak) ? 'lite' : 'full';
  }
  function applyFx(mode) {
    root.setAttribute('data-fx', mode);
    qa('[data-lg-fx-toggle]').forEach(function (b) { b.setAttribute('aria-pressed', String(mode === 'full')); b.setAttribute('title', mode === 'full' ? 'Effects: full (click for lite)' : 'Effects: lite (click for full)'); if (b.type === 'checkbox') b.checked = mode === 'full'; });
    if (mode === 'full') lensOn(); else lensOff();
  }
  function setFx(mode) { ls('lg-fx', mode); applyFx(mode); }

  /* ── skin: glass (default) or skeuomorphic ─────────────────────────────── */
  var SKINS = ['glass', 'skeuo'];
  var SKIN_FONTS = 'https://fonts.googleapis.com/css2?family=Nunito:wght@500;700;800&family=Share+Tech+Mono&display=swap';
  function currentSkin() { var k = root.getAttribute('data-skin'); return SKINS.indexOf(k) > -1 ? k : 'glass'; }
  function applySkin(name) {
    var k = SKINS.indexOf(name) > -1 ? name : 'glass';
    root.setAttribute('data-skin', k);
    if (k === 'skeuo' && !d.getElementById('lg-skin-fonts')) {
      var l = d.createElement('link'); l.id = 'lg-skin-fonts'; l.rel = 'stylesheet'; l.href = SKIN_FONTS; d.head.appendChild(l);
    }
    qa('[data-lg-skin-toggle]').forEach(function (b) {
      var label = k === 'skeuo' ? 'Switch to the glass style' : 'Switch to the skeuomorphic style';
      b.setAttribute('aria-pressed', String(k === 'skeuo')); b.setAttribute('title', label); b.setAttribute('aria-label', label);
      if (b.type === 'checkbox') b.checked = k === 'skeuo';
    });
    if (k === 'glass') lensOn(); else lensOff();      // the lens filter is a glass effect; it is set inline, so CSS cannot switch it off
  }
  function setSkin(name) { ls('lg-skin', name); applySkin(name); }

  /* ── pointer light + tilt ──────────────────────────────────────────────── */
  var SEL = '.glass,.card,.navbar,.lg-shine,.lg-tilt', pending = null, lastTilt = null;
  function pointerFrame() {
    var p = pending; pending = null; if (!p) return;
    var r = p.el.getBoundingClientRect(), x = p.x - r.left, y = p.y - r.top;
    p.el.style.setProperty('--mx', x + 'px'); p.el.style.setProperty('--my', y + 'px');
    if (p.el.classList.contains('lg-tilt') && !reduceMotion) {
      var nx = x / r.width - .5, ny = y / r.height - .5;
      p.el.style.setProperty('--tilt-y', (nx * 10).toFixed(2) + 'deg');
      p.el.style.setProperty('--tilt-x', (-ny * 10).toFixed(2) + 'deg');
      lastTilt = p.el;
    }
  }
  function resetTilt(el) { if (!el) return; el.style.setProperty('--tilt-x', '0deg'); el.style.setProperty('--tilt-y', '0deg'); }
  if (finePointer) {
    d.addEventListener('pointermove', function (e) {
      if (root.getAttribute('data-fx') !== 'full') return;
      var el = e.target && e.target.closest ? e.target.closest(SEL) : null;
      if (lastTilt && lastTilt !== el) { resetTilt(lastTilt); lastTilt = null; }
      if (!el) return;
      if (!pending) raf(pointerFrame);
      pending = { el: el, x: e.clientX, y: e.clientY };
    }, { passive: true });
    d.addEventListener('pointerleave', function () { resetTilt(lastTilt); lastTilt = null; }, true);
  }

  /* ── count-up ──────────────────────────────────────────────────────────── */
  function fmt(el, v) {
    var dec = el.getAttribute('data-decimals');
    var target = el.getAttribute('data-count') || '0';
    var decimals = dec !== null ? parseInt(dec, 10) : ((target.split('.')[1] || '').length);
    var s = new Intl.NumberFormat(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(v);
    return (el.getAttribute('data-prefix') || '') + s + (el.getAttribute('data-suffix') || '');
  }
  function runCount(el) {
    var to = parseFloat(el.getAttribute('data-count')); if (isNaN(to)) return;
    if (reduceMotion) { el.textContent = fmt(el, to); return; }
    var dur = 1200, t0 = null;
    function step(t) {
      if (t0 === null) t0 = t;
      var k = Math.min(1, (t - t0) / dur), e = k === 1 ? 1 : 1 - Math.pow(2, -10 * k);
      el.textContent = fmt(el, to * e);
      if (k < 1) raf(step);
    }
    raf(step);
  }

  /* ── reveal + counters + rings (one observer) ──────────────────────────── */
  function initObservers() {
    var items = qa('.lg-reveal,[data-count],.lg-ring[data-value]');
    if (!('IntersectionObserver' in win)) { items.forEach(function (el) { el.classList.add('is-in'); if (el.hasAttribute('data-count')) el.textContent = fmt(el, parseFloat(el.getAttribute('data-count'))); if (el.hasAttribute('data-value')) el.style.setProperty('--p', el.getAttribute('data-value')); }); return; }
    qa('[data-count]').forEach(function (el) { if (!reduceMotion) el.textContent = fmt(el, 0); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        var el = en.target; io.unobserve(el);
        el.classList.add('is-in');
        if (el.hasAttribute('data-count')) runCount(el);
        if (el.hasAttribute('data-value')) el.style.setProperty('--p', el.getAttribute('data-value'));
      });
    }, { threshold: .15, rootMargin: '0px 0px -6% 0px' });
    items.forEach(function (el) { io.observe(el); });
  }

  /* ── forms ─────────────────────────────────────────────────────────────── */
  d.addEventListener('submit', function (e) {
    var f = e.target;
    if (!f || f.tagName !== 'FORM' || e.defaultPrevented || f.hasAttribute('data-lg-no-loading') || f.target === '_blank') return;
    var btn = e.submitter || f.querySelector('button[type="submit"],button:not([type])');
    if (!btn || btn.tagName !== 'BUTTON' || btn.hasAttribute('data-lg-no-loading')) return;
    btn.classList.add('is-loading'); btn.setAttribute('aria-busy', 'true');
    setTimeout(function () { btn.disabled = true; }, 0);            // after the browser has read the button's name/value
    setTimeout(function () { clear(btn); }, 10000);                 // POST-then-download never navigates: don't spin forever
  }, false);
  function clear(btn) { btn.classList.remove('is-loading'); btn.removeAttribute('aria-busy'); btn.disabled = false; }
  win.addEventListener('pageshow', function (e) { if (e.persisted) qa('.btn.is-loading').forEach(clear); });

  function initRanges() {
    qa('input.form-range').forEach(function (r) {
      function paint() { var min = +r.min || 0, max = +r.max || 100; r.style.setProperty('--fill', ((r.value - min) / (max - min) * 100) + '%'); }
      r.addEventListener('input', paint); paint();
    });
  }

  /* ── toast ─────────────────────────────────────────────────────────────── */
  var ICONS = { success: '✓', danger: '✕', warning: '!', info: 'i' };
  function toast(message, opts) {
    opts = opts || {};
    var type = opts.type || 'info', wrap = d.querySelector('.lg-toasts');
    if (!wrap) { wrap = d.createElement('div'); wrap.className = 'lg-toasts'; wrap.setAttribute('aria-live', 'polite'); d.body.appendChild(wrap); }
    var el = d.createElement('div');
    el.className = 'lg-toast glass is-' + type; el.setAttribute('role', type === 'danger' ? 'alert' : 'status');
    var ic = d.createElement('div'); ic.className = 'lg-toast-ic'; ic.textContent = ICONS[type] || 'i';
    var body = d.createElement('div');
    if (opts.title) { var s = d.createElement('strong'); s.textContent = opts.title; body.appendChild(s); }
    var m = d.createElement('span'); m.className = 'msg'; m.textContent = message; body.appendChild(m);
    el.appendChild(ic); el.appendChild(body); wrap.appendChild(el);
    var timer = setTimeout(close, opts.timeout || 4200);
    function close() { clearTimeout(timer); el.classList.add('is-out'); setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 320); }
    el.addEventListener('click', close);
    return { close: close };
  }

  function initFlash() {
    qa('.alert.alert-dismissible.show').forEach(function (a) {
      if (a.hasAttribute('data-lg-keep')) return;
      var ms = /alert-(danger|warning)/.test(a.className) ? 9000 : 5500, t;
      function arm() { t = setTimeout(function () {
        a.classList.add('is-leaving');
        setTimeout(function () { var B = win.bootstrap; if (B && B.Alert) B.Alert.getOrCreateInstance(a).close(); else if (a.parentNode) a.parentNode.removeChild(a); }, 420);
      }, ms); }
      a.addEventListener('mouseenter', function () { clearTimeout(t); });
      a.addEventListener('mouseleave', arm); arm();
    });
  }

  /* ── misc ──────────────────────────────────────────────────────────────── */
  var scrollTick = false;
  function onScroll() { if (scrollTick) return; scrollTick = true; raf(function () { scrollTick = false; var y = win.scrollY > 6; qa('.navbar').forEach(function (n) { n.classList.toggle('is-scrolled', y); }); }); }
  win.addEventListener('scroll', onScroll, { passive: true });

  d.addEventListener('keydown', function (e) {
    var t = e.target, typing = t && (/^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName) || t.isContentEditable);
    if (e.key === '/' && !typing && !e.metaKey && !e.ctrlKey && !e.altKey) {
      var s = qa('[data-lg-search],input[type="search"],input[name="q"],input[name="search"],input[name="query"]').filter(function (i) { return i.offsetParent !== null; })[0];
      if (s) { e.preventDefault(); s.focus(); s.select && s.select(); }
    } else if (e.key === 'Escape' && typing && t.matches && t.matches('[data-lg-search],input[type="search"],input[name="q"]')) { t.blur(); }
  });

  d.addEventListener('click', function (e) {
    var el = e.target.closest ? e.target.closest('[data-lg-theme-toggle],[data-lg-skin-toggle],[data-lg-fx-toggle],[data-lg-accent],[data-lg-toast]') : null;
    if (!el) return;
    if (el.hasAttribute('data-lg-theme-toggle')) setTheme(root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    else if (el.hasAttribute('data-lg-skin-toggle')) setSkin(currentSkin() === 'skeuo' ? 'glass' : 'skeuo');
    else if (el.hasAttribute('data-lg-fx-toggle')) setFx(root.getAttribute('data-fx') === 'full' ? 'lite' : 'full');
    else if (el.hasAttribute('data-lg-accent')) setAccent(el.getAttribute('data-lg-accent'));
    else if (el.hasAttribute('data-lg-toast')) toast(el.getAttribute('data-lg-toast'), { type: el.getAttribute('data-lg-toast-type') || 'success', title: el.getAttribute('data-lg-toast-title') || undefined });
  });

  /* ── lens: Chromium-only edge refraction ───────────────────────────────────
     Not a real lens. We paint a displacement map whose vectors point inward and
     fade out from the rounded edge, then feed it to feDisplacementMap through
     backdrop-filter:url(#…). Safari and Firefox ignore url() in backdrop-filter,
     so we only switch it on in Chromium and everything else keeps plain blur. */
  var SVGNS = 'http://www.w3.org/2000/svg', lensHost = null, lensItems = [], lensRO = null, lensTimer = null, lensN = 0, lensOK = null;
  function isChromium() {
    if (lensOK !== null) return lensOK;
    var uad = win.navigator && win.navigator.userAgentData;
    lensOK = !!(uad && uad.brands && uad.brands.some(function (b) { return /Chromium/i.test(b.brand); }));
    return lensOK;
  }
  function buildMap(w, h, r, bezel, maxD) {
    var c = d.createElement('canvas'); c.width = w; c.height = h;
    var ctx = c.getContext('2d'), img = ctx.createImageData(w, h), data = img.data;
    var hx = w / 2, hy = h / 2, ix = hx - r, iy = hy - r;
    for (var y = 0; y < h; y++) for (var x = 0; x < w; x++) {
      var px = x + .5 - hx, py = y + .5 - hy, ax = Math.abs(px), ay = Math.abs(py);
      var qx = ax - ix, qy = ay - iy, nx, ny, dist;
      if (qx > 0 && qy > 0) { var l = Math.sqrt(qx * qx + qy * qy); dist = l - r; nx = qx / l * (px < 0 ? -1 : 1); ny = qy / l * (py < 0 ? -1 : 1); }
      else if (qx > qy) { dist = qx - r; nx = px < 0 ? -1 : 1; ny = 0; }
      else { dist = qy - r; nx = 0; ny = py < 0 ? -1 : 1; }
      var depth = -dist, i = (y * w + x) * 4, vx = 0, vy = 0;
      if (depth >= 0 && depth < bezel) { var m = maxD * Math.pow(1 - depth / bezel, 2.2); vx = -nx * m; vy = -ny * m; }   // sample from inside
      data[i] = Math.round(127.5 + vx / maxD * 127.5); data[i + 1] = Math.round(127.5 + vy / maxD * 127.5); data[i + 2] = 128; data[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    return c.toDataURL('image/png');
  }
  function lensBuild(it) {
    var el = it.el, w = Math.round(el.offsetWidth), h = Math.round(el.offsetHeight);
    if (w < 8 || h < 8 || w * h > 450000) return;
    var cs = win.getComputedStyle(el), r = parseFloat(cs.borderTopLeftRadius) || 0;
    r = Math.min(r, w / 2, h / 2);
    var bezel = Math.min(Math.max(10, Math.min(w, h) * .32), 26), maxD = parseFloat(el.getAttribute('data-lens-strength')) || 16;
    var f = it.filter, im = f.firstChild, dm = f.lastChild;
    f.setAttribute('width', w); f.setAttribute('height', h);
    im.setAttribute('width', w); im.setAttribute('height', h);
    im.setAttribute('href', buildMap(w, h, r, bezel, maxD));
    dm.setAttribute('scale', maxD * 2);
    var blur = el.getAttribute('data-lens-blur') || '6px';
    var v = 'url(#' + f.id + ') blur(' + blur + ') saturate(1.9) brightness(1.05)';
    el.style.webkitBackdropFilter = v; el.style.backdropFilter = v;
  }
  function lensAttach(el) {
    if (lensItems.some(function (i) { return i.el === el; })) return;
    if (!lensHost) { lensHost = d.createElementNS(SVGNS, 'svg'); lensHost.setAttribute('width', 0); lensHost.setAttribute('height', 0); lensHost.setAttribute('aria-hidden', 'true'); lensHost.style.cssText = 'position:absolute;width:0;height:0;overflow:hidden'; d.body.appendChild(lensHost); }
    var f = d.createElementNS(SVGNS, 'filter'); f.id = 'lg-lens-' + (++lensN);
    f.setAttribute('filterUnits', 'userSpaceOnUse'); f.setAttribute('x', 0); f.setAttribute('y', 0); f.setAttribute('color-interpolation-filters', 'sRGB');
    var im = d.createElementNS(SVGNS, 'feImage'); im.setAttribute('x', 0); im.setAttribute('y', 0); im.setAttribute('preserveAspectRatio', 'none'); im.setAttribute('result', 'map');
    var dm = d.createElementNS(SVGNS, 'feDisplacementMap'); dm.setAttribute('in', 'SourceGraphic'); dm.setAttribute('in2', 'map'); dm.setAttribute('xChannelSelector', 'R'); dm.setAttribute('yChannelSelector', 'G');
    f.appendChild(im); f.appendChild(dm); lensHost.appendChild(f);
    var it = { el: el, filter: f }; lensItems.push(it); lensBuild(it);
    if (lensRO) lensRO.observe(el);
  }
  function lensOn() {
    if (!isChromium() || root.getAttribute('data-fx') !== 'full' || currentSkin() !== 'glass') return;
    if (!lensRO && 'ResizeObserver' in win) lensRO = new ResizeObserver(lensRefreshSoon);
    qa('.lg-lens').forEach(lensAttach);
  }
  function lensOff() {
    lensItems.forEach(function (it) { it.el.style.webkitBackdropFilter = ''; it.el.style.backdropFilter = ''; if (it.filter.parentNode) it.filter.parentNode.removeChild(it.filter); if (lensRO) lensRO.unobserve(it.el); });
    lensItems = [];
  }
  function lensRefreshSoon() { if (!lensItems.length) return; clearTimeout(lensTimer); lensTimer = setTimeout(function () { lensItems.forEach(lensBuild); }, 160); }

  /* ── phone tables ──────────────────────────────────────────────────────────
     table.table-stack: copy each <th> text onto the cells below it as data-label, which the CSS
     shows as "LABEL  value" rows under 576px. Display:block on table parts makes some screen
     readers drop the table semantics, so the ARIA table roles are spelled out as well. */
  function initTables() {
    qa('table.table-stack').forEach(function (table) {
      var head = table.querySelector('thead tr');
      if (!head) return;
      var labels = [];
      Array.prototype.forEach.call(head.children, function (th) {
        var text = (th.textContent || '').replace(/\s+/g, ' ').trim();
        for (var n = parseInt(th.getAttribute('colspan') || '1', 10) || 1; n > 0; n--) labels.push(text);
      });
      qa('tbody tr', table).forEach(function (tr) {
        var col = 0;
        Array.prototype.forEach.call(tr.children, function (td) {
          var span = parseInt(td.getAttribute('colspan') || '1', 10) || 1;
          if (span === 1 && labels[col]) td.setAttribute('data-label', labels[col]);
          if (span === 1 && !td.children.length && !(td.textContent || '').trim()) td.setAttribute('data-empty', '');   /* a label with nothing after it reads as broken */
          col += span;
        });
      });
      table.setAttribute('role', 'table');
      qa('thead, tbody', table).forEach(function (g) { g.setAttribute('role', 'rowgroup'); });
      qa('tr', table).forEach(function (r) { r.setAttribute('role', 'row'); });
      qa('th', table).forEach(function (c) { c.setAttribute('role', 'columnheader'); });
      qa('tbody td', table).forEach(function (c) { c.setAttribute('role', 'cell'); });
    });
  }

  /* ── page transitions ─────────────────────────────────────────────────────
     The CSS (section 16) does the arriving animation and, in Chromium and Safari, the cross-fade. This adds
     a loading line for every in-site link click and, where the browser has no cross-document view
     transitions, a short fade-out before the page changes. Downloads, new tabs, modified clicks, in-page
     anchors and Bootstrap toggles are left alone. Test hook: localStorage lg-navfx = 'js' forces the fade-out. */
  var hasVT = 'CSSViewTransitionRule' in win;
  var navJs = ls('lg-navfx') === 'js' || !hasVT;
  var DOWNLOADISH = /\/reports\/export\/|\/cover(\/|$|\?)|\.(csv|xlsx?|zip|db|pdf|png|jpe?g|gif|webp)(\?|$)/i;
  var bar = null, barTimer = 0;

  function plainNav(a, e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return false;
    if (a.hasAttribute('download') || a.hasAttribute('data-lg-no-transition') || a.hasAttribute('data-bs-toggle') || a.hasAttribute('data-bs-dismiss')) return false;
    if (a.target && a.target !== '_self') return false;
    if (a.protocol !== 'http:' && a.protocol !== 'https:') return false;
    if (a.origin !== win.location.origin || DOWNLOADISH.test(a.pathname + a.search)) return false;
    if (a.pathname === win.location.pathname && a.search === win.location.search && (a.hash || a.href.indexOf('#') > -1)) return false;
    return true;
  }
  function progressOn() {
    if (!bar) { bar = d.createElement('div'); bar.className = 'lg-progress'; bar.setAttribute('aria-hidden', 'true'); d.body.appendChild(bar); }
    bar.classList.remove('is-on'); void bar.offsetWidth; bar.classList.add('is-on');
    clearTimeout(barTimer); barTimer = setTimeout(progressOff, 12000);       // a link that never navigates must not leave the line running
  }
  function progressOff() { clearTimeout(barTimer); if (bar) bar.classList.remove('is-on'); root.classList.remove('lg-leaving'); }
  d.addEventListener('click', function (e) {
    if (reduceMotion) return;
    var a = e.target.closest ? e.target.closest('a[href]') : null;
    if (!a || !plainNav(a, e)) return;
    progressOn();
    if (navJs) {
      e.preventDefault(); root.classList.add('lg-leaving');
      setTimeout(function () { win.location.href = a.href; }, 160);
    }
  });
  win.addEventListener('pageshow', progressOff);                              // back/forward cache brings the old page back as it was left

  /* ── boot ──────────────────────────────────────────────────────────────── */
  applyTheme(ls('lg-theme') || 'auto');
  applyAccent(ls('lg-accent'));
  applySkin(currentSkin());
  var savedFx = ls('lg-fx'); applyFx(savedFx === 'full' || savedFx === 'lite' ? savedFx : autoFx());

  function ready() { initTables(); initObservers(); initRanges(); initFlash(); onScroll(); lensOn(); }
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', ready); else ready();

  win.LG = { version: '1.2.0', setTheme: setTheme, setAccent: setAccent, setFx: setFx, setSkin: setSkin, toast: toast, lens: { refresh: lensRefreshSoon, attach: lensAttach } };
})();
