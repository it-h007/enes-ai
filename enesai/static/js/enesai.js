/* ENES’AI — behaviours (port of source/authoring/js/40-behaviour.js).
   One delegated listener per event type, keyed by data-ea. The prototype's mock hooks
   are replaced by real endpoints (fetch + CSRF); every server-backed control also works
   as a plain link/form without JavaScript. Fixes from the handoff audit: focus trap +
   restore + scroll lock for drawers/modals (X2), clipboard promise handled (#81),
   “Pastro filtrat / Pastro të gjitha” (X11), “Shfaqi përsëri” (X10), typed quantity
   clamping (S-36), admin phone menu (X1), real search suggestions (X3). */
(function () {
  'use strict';
  var doc = document;
  var CSRF = (doc.querySelector('meta[name="csrf-token"]') || {}).content || '';
  var LANG = doc.documentElement.lang || 'sq';
  var reduced = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------- small helpers ---------- */
  function closest(el, sel) { while (el && el.nodeType === 1) { if (el.matches(sel)) return el; el = el.parentElement; } return null; }
  function frag(html) { var w = doc.createElement('div'); w.innerHTML = html.trim(); return w.firstElementChild; }
  function swap(oldEl, html) { var n = frag(html); if (oldEl && oldEl.parentNode && n) oldEl.parentNode.replaceChild(n, oldEl); return n; }
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function store(k, v) { try { if (v === undefined) return JSON.parse(localStorage.getItem(k) || 'null'); localStorage.setItem(k, JSON.stringify(v)); } catch (e) { return null; } }
  var ICON = {
    check: '<path d="M20 6 9 17l-5-5"/>', x: '<path d="M18 6 6 18"/> <path d="m6 6 12 12"/>',
    'circle-check': '<circle cx="12" cy="12" r="10"/> <path d="m9 12 2 2 4-4"/>',
    'circle-alert': '<circle cx="12" cy="12" r="10"/> <line x1="12" x2="12" y1="8" y2="12"/> <line x1="12" x2="12.01" y1="16" y2="16"/>',
    info: '<circle cx="12" cy="12" r="10"/> <path d="M12 16v-4"/> <path d="M12 8h.01"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/> <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    'arrow-right': '<path d="M5 12h14"/> <path d="m12 5 7 7-7 7"/>', 'folder-tree': '<path d="M20 10a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-2.5a1 1 0 0 1-.8-.4l-.9-1.2A1 1 0 0 0 15 3h-2a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1Z"/> <path d="M20 21a1 1 0 0 0 1-1v-3a1 1 0 0 0-1-1h-2.9a1 1 0 0 1-.88-.55l-.42-.85a1 1 0 0 0-.92-.6H13a1 1 0 0 0-1 1v5a1 1 0 0 0 1 1Z"/> <path d="M3 5a2 2 0 0 0 2 2h3"/> <path d="M3 3v13a2 2 0 0 0 2 2h3"/>',
    'search-x': '<path d="m13.5 8.5-5 5"/> <path d="m8.5 8.5 5 5"/> <circle cx="11" cy="11" r="8"/> <path d="m21 21-4.3-4.3"/>',
    crosshair: '<circle cx="12" cy="12" r="10"/> <line x1="22" x2="18" y1="12" y2="12"/> <line x1="6" x2="2" y1="12" y2="12"/> <line x1="12" x2="12" y1="6" y2="2"/> <line x1="12" x2="12" y1="22" y2="18"/>',
    'map-pinned': '<path d="M18 8c0 3.613-3.869 7.429-5.393 8.795a1 1 0 0 1-1.214 0C9.87 15.429 6 11.613 6 8a6 6 0 0 1 12 0"/> <circle cx="12" cy="8" r="2"/> <path d="M8.714 14h-3.71a1 1 0 0 0-.948.683l-2.004 6A1 1 0 0 0 3 22h18a1 1 0 0 0 .948-1.316l-2-6a1 1 0 0 0-.949-.684h-3.712"/>',
    'map-pin': '<path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/> <circle cx="12" cy="10" r="3"/>',
    'triangle-alert': '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/> <path d="M12 9v4"/> <path d="M12 17h.01"/>',
    'external-link': '<path d="M15 3h6v6"/> <path d="M10 14 21 3"/> <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    'file-down': '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/> <path d="M14 2v4a2 2 0 0 0 2 2h4"/> <path d="M12 18v-6"/> <path d="m9 15 3 3 3-3"/>',
    ban: '<circle cx="12" cy="12" r="10"/> <path d="m4.9 4.9 14.2 14.2"/>', 'rotate-ccw': '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/> <path d="M3 3v5h5"/>'
  };
  function icon(n, cls) { return '<svg class="ea-icon' + (cls ? ' ' + cls : '') + '" viewBox="0 0 24 24" aria-hidden="true" focusable="false">' + (ICON[n] || '') + '</svg>'; }
  var T = LANG === 'en' ? {
    added: 'Added to cart', seeCart: 'View cart', copied: 'Copied', inClip: 'is on the clipboard.', clipFail: 'Copy it by hand', error: 'Something went wrong',
    retry: 'Check your connection and try again.', removed: 'Removed from cart', undo: 'Undo', noNumber: 'The market number is missing',
    noNumberText: 'Choose the contact yourself in WhatsApp.', results: 'See %n results', none: 'No results for', keys: '↑↓ to move · Enter to open', cats: 'Categories', prods: 'Products',
    shown: 'You have seen %a of %b products', locLoading: 'Getting your location… Allow access when the browser asks.'
  } : {
    added: 'U shtua në shportë', seeCart: 'Shiko shportën', copied: 'U kopjua', inClip: 'është në clipboard.', clipFail: 'Kopjojeni me dorë', error: 'Diçka shkoi keq',
    retry: 'Kontrolloni lidhjen dhe provoni sërish.', removed: 'U hoq nga shporta', undo: 'Anulo', noNumber: 'Numri i marketit mungon',
    noNumberText: 'Vendoseni te Paneli › Cilësimet › Fatura & WhatsApp. Tani zgjidhni kontaktin vetë në WhatsApp.', results: 'Shiko %n rezultate', none: 'Asnjë rezultat për', keys: '↑↓ për të lëvizur · Enter për të hapur',
    cats: 'Kategori', prods: 'Produkte', shown: 'Keni parë %a nga %b produkte', locLoading: 'Po marrim vendndodhjen… Lejoni aksesin kur shfletuesi ju pyet.'
  };

  function post(url, data) {
    var body = new URLSearchParams(); Object.keys(data || {}).forEach(function (k) { body.append(k, data[k]); });
    return fetch(url, { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': CSRF, 'X-Requested-With': 'fetch', 'Accept': 'application/json' }, body: body })
      .then(function (r) { return r.status === 204 ? {} : r.json().then(function (j) { if (!r.ok && !j.message) j.message = T.retry; j._status = r.status; return j; }); });
  }

  function toast(o) {
    var region = doc.querySelector('[data-ea-toasts]'); if (!region) return;
    var lead = o.img ? '<img class="ea-toast__img" src="' + esc(o.img) + '" alt="">' : '<span class="ea-toast__ic">' + icon(o.icon || (o.tone === 'error' ? 'circle-alert' : o.tone === 'info' ? 'info' : 'circle-check')) + '</span>';
    var t = frag('<div class="ea-toast ea-toast--' + (o.tone || 'success') + '" role="' + (o.tone === 'error' ? 'alert' : 'status') + '">' + lead + '<div><p class="ea-toast__title">' + esc(o.title) + '</p>' + (o.html || o.text ? '<p class="ea-toast__text">' + (o.html || esc(o.text)) + '</p>' : '') + '</div><button class="ea-iconbtn" type="button" aria-label="Mbyll njoftimin" data-ea="toast-close">' + icon('x', 'ea-icon--sm') + '</button></div>');
    region.appendChild(t);
    var tm = setTimeout(function () { leave(t); }, o.ms || 3600);
    t._timer = tm; return t;
  }
  function leave(t) { if (!t || !t.parentNode) return; t.classList.add('is-leaving'); setTimeout(function () { if (t.parentNode) t.parentNode.removeChild(t); }, 220); }
  doc.querySelectorAll('[data-ea-toasts] .ea-toast').forEach(function (t) { setTimeout(function () { leave(t); }, 5000); });

  function setCartCount(n, bump) {
    doc.querySelectorAll('[data-ea-cart]').forEach(function (c) {
      c.textContent = String(n); c.hidden = !n;
      var a = closest(c, 'a'); if (a) a.setAttribute('aria-label', (LANG === 'en' ? 'Cart, ' : 'Shporta, ') + n + (LANG === 'en' ? ' products' : ' produkte'));
      if (bump && !reduced) { c.classList.remove('is-bump'); void c.offsetWidth; c.classList.add('is-bump'); }
    });
  }
  function fly(btn) {
    if (reduced || !btn.getAttribute('data-img')) return;
    var cart = doc.querySelector('[data-ea-cart]:not([hidden])') || doc.querySelector('[data-ea-cartlink]'); if (!cart || !cart.animate) return;
    var a = btn.getBoundingClientRect(), b = cart.getBoundingClientRect(); if (!b.width) return;
    var img = doc.createElement('img'); img.className = 'ea-fly'; img.src = btn.getAttribute('data-img'); img.alt = '';
    img.style.left = (a.left + a.width / 2) + 'px'; img.style.top = (a.top + a.height / 2) + 'px'; doc.body.appendChild(img);
    var dx = b.left + b.width / 2 - (a.left + a.width / 2), dy = b.top + b.height / 2 - (a.top + a.height / 2);
    img.animate([{ transform: 'translate(0,0) scale(1)', opacity: 1 }, { transform: 'translate(' + dx * 0.5 + 'px,' + (dy * 0.5 - 60) + 'px) scale(0.8)', opacity: 1, offset: 0.55 }, { transform: 'translate(' + dx + 'px,' + dy + 'px) scale(0.3)', opacity: 0.2 }], { duration: 520, easing: 'cubic-bezier(0.65, 0, 0.35, 1)' }).onfinish = function () { img.remove(); };
  }

  /* ---------- overlays: drawers + modals with focus trap / restore / scroll lock / inert ---------- */
  var openStack = [];
  var FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  function siblingsOf(el) { var site = closest(el, '.ea-site') || doc.body; return [].filter.call(site.children, function (c) { return c !== el && !c.classList.contains('ea-scrim') && !c.matches('[data-ea-toasts]'); }); }
  function setOpen(id, open, opener) {
    var d = doc.getElementById(id); if (!d) return;
    var isModal = d.classList.contains('ea-modal');
    if (open === d.classList.contains('is-open')) return;
    d.classList.toggle('is-open', open); d.setAttribute('aria-hidden', open ? 'false' : 'true');
    var s = d.previousElementSibling; if (s && s.classList.contains('ea-scrim')) s.classList.toggle('is-open', open);
    doc.querySelectorAll('[aria-controls="' + id + '"]').forEach(function (b) { b.setAttribute('aria-expanded', open); });
    if (open) {
      openStack.push({ id: id, opener: opener || doc.activeElement, inert: siblingsOf(d) });
      openStack[openStack.length - 1].inert.forEach(function (n) { n.setAttribute('inert', ''); });
      doc.documentElement.style.overflow = 'hidden';
      var f = (isModal ? d.querySelector('.ea-dialog') : d).querySelector(FOCUSABLE); if (f) f.focus({ preventScroll: true });
    } else {
      var i = -1; openStack.forEach(function (e, k) { if (e.id === id) i = k; });
      var ent = i > -1 ? openStack.splice(i, 1)[0] : null;
      if (ent) ent.inert.forEach(function (n) { n.removeAttribute('inert'); });
      if (!openStack.length) doc.documentElement.style.overflow = '';
      if (ent && ent.opener && ent.opener.focus && doc.contains(ent.opener)) ent.opener.focus({ preventScroll: true });
    }
  }
  function topOverlay() { return openStack.length ? doc.getElementById(openStack[openStack.length - 1].id) : null; }

  /* ---------- favourites (C-21: this browser only) ---------- */
  function favs() { var f = store('ea_favs'); return Array.isArray(f) ? f : []; }
  function syncFavs() {
    var list = favs();
    doc.querySelectorAll('[data-ea="fav"][data-pid]').forEach(function (b) { b.setAttribute('aria-pressed', list.indexOf(String(b.getAttribute('data-pid'))) > -1 ? 'true' : 'false'); });
    doc.querySelectorAll('[data-ea-favlink]').forEach(function (a) {
      a.href = '/dyqani?te-preferuarat=1&ids=' + list.join(',');
      a.setAttribute('aria-label', (LANG === 'en' ? 'Favourites (' : 'Të preferuarat (') + list.length + ')');
    });
  }

  /* ---------- search suggestions (GET /api/kerko) ---------- */
  var sTimer = null, sSeq = 0;
  function suggest(input) {
    var form = closest(input, '.ea-search'), panel = form && form.querySelector('.ea-suggest'); if (!panel) return;
    var q = input.value.trim(); clearTimeout(sTimer);
    if (q.length < 2) { closeSuggest(form); return; }
    sTimer = setTimeout(function () {
      var seq = ++sSeq;
      fetch('/api/kerko?q=' + encodeURIComponent(q), { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) {
        if (seq !== sSeq) return;
        var html = '';
        if (!d.products.length && !d.categories.length) html = '<div class="ea-suggest__empty">' + icon('search-x', 'ea-icon--sm') + ' ' + T.none + ' “<b>' + esc(q) + '</b>”.</div>';
        else {
          if (d.categories.length) html += '<div class="ea-suggest__group">' + T.cats + '</div><div style="padding:2px 4px 0">' + d.categories.map(function (c) { return '<a class="ea-suggest__cat" href="' + esc(c.url) + '">' + icon('folder-tree', 'ea-icon--sm') + esc(c.name) + '</a>'; }).join('') + '</div>';
          if (d.products.length) html += '<div class="ea-suggest__group">' + T.prods + '</div>' + d.products.map(function (p, i) {
            var name = esc(p.name), k = p.name.toLowerCase().indexOf(q.toLowerCase());
            if (k > -1) name = esc(p.name.slice(0, k)) + '<mark>' + esc(p.name.slice(k, k + q.length)) + '</mark>' + esc(p.name.slice(k + q.length));
            return '<a class="ea-suggest__item" role="option" id="' + panel.id + '-o' + i + '" href="' + esc(p.url) + '" aria-selected="false"><img src="' + esc(p.image) + '" alt=""><span><span class="ea-suggest__name">' + name + '</span><br><span class="ea-suggest__meta">' + esc(p.pack) + ' · ' + esc(p.cat) + '</span></span><span class="ea-suggest__price">' + esc(p.price) + '</span></a>';
          }).join('');
          html += '<div class="ea-suggest__foot"><span class="ea-muted">' + T.keys + '</span><a href="/dyqani?q=' + encodeURIComponent(q) + '">' + T.results.replace('%n', d.total) + ' ' + icon('arrow-right', 'ea-icon--sm') + '</a></div>';
        }
        panel.innerHTML = html; form.classList.add('is-open'); input.setAttribute('aria-expanded', 'true');
      }).catch(function () { closeSuggest(form); });
    }, 200);
  }
  function closeSuggest(form) { if (!form) return; form.classList.remove('is-open'); var i = form.querySelector('.ea-search__input'); if (i) { i.setAttribute('aria-expanded', 'false'); i.removeAttribute('aria-activedescendant'); } }
  function moveSuggest(input, dir) {
    var form = closest(input, '.ea-search'), items = [].slice.call(form.querySelectorAll('.ea-suggest__item, .ea-suggest__cat')); if (!items.length || !form.classList.contains('is-open')) return false;
    var cur = items.findIndex(function (a) { return a.getAttribute('aria-selected') === 'true'; }), nxt = (cur + dir + items.length) % items.length;
    items.forEach(function (a, i) { a.setAttribute('aria-selected', i === nxt ? 'true' : 'false'); });
    if (items[nxt].id) input.setAttribute('aria-activedescendant', items[nxt].id);
    items[nxt].scrollIntoView({ block: 'nearest' }); return true;
  }

  /* ---------- stepper ---------- */
  function clampStepper(st, v) {
    var inp = st.querySelector('input'), max = parseInt(st.getAttribute('data-max') || '99', 10) || 1;
    v = Math.max(1, Math.min(max, parseInt(v, 10) || 1)); inp.value = v;
    var dec = st.querySelector('[data-ea="dec"]'), inc = st.querySelector('[data-ea="inc"]');
    if (dec) dec.disabled = v <= 1; if (inc) inc.disabled = v >= max;
    st.classList.toggle('is-max', v >= max && max > 1);
    var note = closest(st, '.ea-pdp__info'); note = note && note.querySelector('[data-ea-maxnote]'); if (note) note.hidden = !(v >= max);
    return v;
  }
  var qtyTimers = {};
  function cartQty(row, v) {
    var id = row.getAttribute('data-slug'); clearTimeout(qtyTimers[id]);
    qtyTimers[id] = setTimeout(function () { post('/shporta/sasia', { product: id, qty: v }).then(function (d) { if (d.ok === false) return toast({ tone: 'error', title: d.message || T.error }); renderCart(d); }).catch(netErr); }, 250);
  }
  function renderCart(d) {
    if (!d || d.lines === undefined) return;
    if (d.empty) { location.reload(); return; }
    setCartCount(d.count);
    d.lines.forEach(function (l) {
      var row = doc.querySelector('.ea-citem[data-slug="' + l.id + '"]'); if (!row) return;
      var st = row.querySelector('.ea-stepper'); st.setAttribute('data-max', l.max); clampStepper(st, l.qty);
      row.querySelector('.ea-citem__total .ea-price').textContent = l.line_total;
    });
    var fb = doc.querySelector('[data-ea-freebar]'); if (fb && d.freebar) swap(fb, d.freebar);
    var sm = doc.querySelector('[data-ea-cartpage] [data-ea-summary]'); if (sm && d.summary) swap(sm, d.summary);
    var mb = doc.querySelector('.ea-mobilebar__total .ea-price'); if (mb) mb.textContent = d.totals.total;
    var h = doc.getElementById('ci-t'); if (h) { var n = doc.querySelectorAll('.ea-citem').length; h.textContent = n + (n === 1 ? (LANG === 'en' ? ' product' : ' produkt') : (LANG === 'en' ? ' products' : ' produkte')); }
  }
  function netErr() { toast({ tone: 'error', title: T.error, text: T.retry }); }

  /* ---------- checkout: validation (same rules as the server) ---------- */
  var PHONE_AL = /^(?:\+355|00355|0)6[5-9]\d{7}$/, PHONE_INTL = /^\+\d{8,15}$/;
  var CHECKS = {
    'co-name': function (v) { return v.length < 2 ? 'Shkruani emrin.' : ''; },
    'co-surname': function (v) { return v.length < 2 ? 'Shkruani mbiemrin.' : ''; },
    'co-tel': function (v) { var n = v.replace(/[\s\-().]/g, ''); return !n ? 'Shkruani numrin e telefonit, p.sh. 069 123 4567.' : PHONE_AL.test(n) || PHONE_INTL.test(n) ? '' : 'Numri nuk duket i saktë. Shembull: 069 123 4567 ose +355 69 123 4567.'; },
    'co-mail': function (v) { return v && !/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v) ? 'Email-i nuk duket i saktë (p.sh. emri@gmail.com) — ose lëreni bosh.' : ''; },
    'co-addr': function (v) { return v.length < 6 ? 'Shkruani të paktën rrugën dhe pallatin / shtëpinë.' : ''; }
  };
  var LABELS = { 'co-name': 'Emri', 'co-surname': 'Mbiemri', 'co-tel': 'Telefoni', 'co-mail': 'Email-i', 'co-loc': 'Vendndodhja', 'co-addr': 'Adresa e plotë', 'co-terms': 'Kushtet' };
  function fieldMsg(input, msg) {
    var f = closest(input, '.ea-field'); if (!f) return;
    var e = f.querySelector('.ea-field__error');
    f.classList.toggle('is-invalid', !!msg); f.classList.toggle('is-valid', !msg && !!input.value.trim());
    if (msg) { input.setAttribute('aria-invalid', 'true'); input.setAttribute('aria-describedby', input.id + '-e'); if (e) e.innerHTML = icon('circle-alert') + esc(msg); }
    else { input.removeAttribute('aria-invalid'); if (f.querySelector('#' + input.id + '-h')) input.setAttribute('aria-describedby', input.id + '-h'); }
  }
  function validateCheckout(form) {
    var errs = [];
    ['co-name', 'co-surname', 'co-tel', 'co-mail'].forEach(function (id) { var i = form.querySelector('#' + id); if (!i) return; var m = CHECKS[id](i.value.trim()); fieldMsg(i, m); if (m) errs.push([id, m]); });
    var loc = form.querySelector('[data-ea-loc]'), lat = form.querySelector('input[name="lat"]'), locOk = !!(lat && lat.value !== '');
    if (loc) loc.classList.toggle('is-invalid', !locOk);
    if (!locOk) errs.push(['co-loc', 'Zgjidhni pikën: GPS ose në hartë']);
    var ad = form.querySelector('#co-addr'); if (ad) { var m2 = CHECKS['co-addr'](ad.value.trim()); fieldMsg(ad, m2); if (m2) errs.push(['co-addr', m2]); }
    var tm = form.querySelector('#co-terms'), tl = tm && closest(tm, '.ea-terms');
    if (tm) { tl.classList.toggle('is-invalid', !tm.checked); if (!tm.checked) errs.push(['co-terms', 'Pranoni kushtet e shitjes']); }
    var host = form.querySelector('.ea-checkout__form') || form, old = host.querySelector('.ea-errsum'); if (old) old.remove();
    if (errs.length) {
      var box = frag('<div class="ea-errsum" role="alert" tabindex="-1">' + icon('circle-alert') + '<div><b>Kontrolloni ' + (errs.length === 1 ? '1 fushë' : errs.length + ' fusha') + ' para se të vazhdoni</b><ul>' + errs.map(function (e) { return '<li><a href="#' + e[0] + '">' + LABELS[e[0]] + '</a> — ' + esc(e[1].replace(/\.$/, '')) + '</li>'; }).join('') + '</ul></div></div>');
      host.insertBefore(box, host.firstChild); box.focus({ preventScroll: true }); box.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'center' });
    }
    return !errs.length;
  }

  /* ---------- checkout: location (GPS or a pin on the map; typed coordinates never accepted) ---------- */
  function mapsUrl(lat, lng) { return 'https://www.google.com/maps/search/?api=1&query=' + (+lat).toFixed(6) + ',' + (+lng).toFixed(6); }
  function setLoc(box, o) {
    var map = box.querySelector('[data-ea-map]'), status = box.querySelector('[data-ea-loc-status]');
    var st = o.state, ok = st === 'ok';
    box.setAttribute('data-state', st); box.setAttribute('data-src', o.src || ''); box.setAttribute('data-acc', o.acc || '');
    box.classList.toggle('is-ok', ok); if (ok) box.classList.remove('is-invalid');
    var bG = box.querySelector('[data-ea="loc-gps"]'), bM = box.querySelector('[data-ea="loc-map"]');
    bG.setAttribute('aria-pressed', String(o.src === 'gps' || st === 'loading')); bM.setAttribute('aria-pressed', String(o.src === 'map' || st === 'map' || st === 'denied'));
    var showMap = ok || st === 'map' || st === 'denied'; map.hidden = !showMap;
    if (o.lat != null) { map.setAttribute('data-lat', o.lat); map.setAttribute('data-lng', o.lng); }
    var lat = +map.getAttribute('data-lat'), lng = +map.getAttribute('data-lng');
    status.innerHTML = {
      idle: '<span class="ea-loc__hint">' + icon('info', 'ea-icon--sm') + 'E detyrueshme — korrieri vjen direkt te pika që zgjidhni, pa ju telefonuar.</span>',
      loading: '<span class="ea-loc__hint"><span class="ea-spinner"></span>' + T.locLoading + '</span>',
      map: '<span class="ea-loc__hint">' + icon('map-pinned', 'ea-icon--sm') + '<span>Lëvizni hartën derisa pika e artë të jetë mbi shtëpinë tuaj, pastaj shtypni <b>“Konfirmo këtë pikë”</b>.</span></span>',
      denied: '<span class="ea-loc__warn">' + icon('triangle-alert', 'ea-icon--sm') + '<span><b>Leja për GPS u refuzua.</b> Vendosni pikën në hartë — është po aq e saktë.</span></span>',
      ok: '<span class="ea-loc__ok">' + icon('circle-check', 'ea-icon--sm') + '<span><b>Vendndodhja u konfirmua</b> <span class="ea-num">' + lat.toFixed(5) + ', ' + lng.toFixed(5) + '</span>' + (o.acc ? ' · ±' + o.acc + ' m' : '') + ' · ' + (o.src === 'map' ? 'zgjedhur në hartë' : 'nga GPS') + '</span></span><a class="ea-btn ea-btn--link" href="' + mapsUrl(lat, lng) + '" target="_blank" rel="noopener">Kontrollo në Google Maps ' + icon('external-link', 'ea-icon--sm') + '</a>'
    }[st];
    box.querySelector('input[name="lat"]').value = ok ? lat.toFixed(6) : '';
    box.querySelector('input[name="lng"]').value = ok ? lng.toFixed(6) : '';
    box.querySelector('input[name="loc_source"]').value = ok ? o.src : '';
    box.querySelector('input[name="accuracy_m"]').value = ok && o.acc ? o.acc : '';
    if (showMap) mountMap(box, ok ? 17 : 15);
  }
  function mountMap(box, zoom) {
    var wrap = box.querySelector('[data-ea-map]'), canvas = wrap.querySelector('[data-ea-map-canvas]'), form = closest(box, '[data-ea-checkout]');
    var lat = +wrap.getAttribute('data-lat'), lng = +wrap.getAttribute('data-lng');
    if (!window.L) return;
    if (box._map) { box._user = false; box._map.invalidateSize(); box._map.setView([lat, lng], zoom, { animate: false }); return; }
    canvas.innerHTML = '';
    var map = L.map(canvas, { zoomControl: true, attributionControl: true }).setView([lat, lng], zoom); box._map = map;
    var fails = 0, tiles = L.tileLayer(form.getAttribute('data-map-tiles'), { maxZoom: 19, attribution: form.getAttribute('data-map-attr') }).addTo(map);
    tiles.on('tileerror', function () { if (++fails === 3 && !wrap.querySelector('.ea-loc__offline')) wrap.insertAdjacentHTML('beforeend', '<p class="ea-loc__offline">Harta kërkon internet. Pa internet, përdorni butonin “Përdor vendndodhjen time”.</p>'); });
    ['pointerdown', 'wheel', 'keydown', 'touchstart'].forEach(function (ev) { canvas.addEventListener(ev, function () { box._user = true; }, { passive: true }); });
    map.on('click', function (e) { box._user = true; map.panTo(e.latlng); });
    map.on('move', function () {
      if (!box._user) return;   /* only the customer's own map moves change the point */
      var c = map.getCenter(); wrap.setAttribute('data-lat', c.lat.toFixed(6)); wrap.setAttribute('data-lng', c.lng.toFixed(6));
      if (box.getAttribute('data-state') === 'ok') {   /* moving after confirming updates the confirmed point (map source) */
        box.querySelector('input[name="lat"]').value = c.lat.toFixed(6); box.querySelector('input[name="lng"]').value = c.lng.toFixed(6);
        box.querySelector('input[name="loc_source"]').value = 'map'; box.querySelector('input[name="accuracy_m"]').value = '';
        box.setAttribute('data-src', 'map');
        var num = box.querySelector('.ea-loc__ok .ea-num'); if (num) num.textContent = c.lat.toFixed(5) + ', ' + c.lng.toFixed(5);
        var link = box.querySelector('.ea-loc__status a'); if (link) link.href = mapsUrl(c.lat, c.lng);
      }
    });
    setTimeout(function () { map.invalidateSize(); }, 60);
  }
  function locGps(box) {
    setLoc(box, { state: 'loading', src: 'gps' });
    if (!navigator.geolocation) { setLoc(box, { state: 'denied', src: 'map' }); return; }
    navigator.geolocation.getCurrentPosition(function (p) {
      setLoc(box, { state: 'ok', src: 'gps', lat: p.coords.latitude, lng: p.coords.longitude, acc: Math.round(p.coords.accuracy) });
    }, function () { setLoc(box, { state: 'denied', src: 'map' }); }, { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 });
  }

  /* ---------- checkout: coupon (POST /api/kupon/kontrollo returns the re-rendered step 4 + summary) ---------- */
  function applyCoupon(form, remove) {
    var input = form.querySelector('#cp-code'), btn = form.querySelector('[data-ea="coupon-apply"]'), terms = form.querySelector('#co-terms');
    var code = remove ? 'x' : (input ? input.value : '');
    if (btn) { btn.classList.add('is-loading'); btn.setAttribute('aria-busy', 'true'); }
    post('/api/kupon/kontrollo', { code: code, remove: remove ? '1' : '0', terms: terms && terms.checked ? '1' : '0' }).then(function (d) {
      if (d._status === 429) { toast({ tone: 'error', title: d.message || T.error }); if (btn) { btn.classList.remove('is-loading'); btn.removeAttribute('aria-busy'); } return; }
      var fin = form.querySelector('[data-ea-cofinal]'), sum = form.querySelector('[data-ea-summary]');
      var n = swap(fin, d.final); if (sum) swap(sum, d.summary);
      if (d.ok) { toast({ title: 'Kuponi u aplikua', html: '<b>' + esc(d.code) + '</b> · −' + d.pct + '% nga produktet' }); var rm = n.querySelector('[data-ea="coupon-remove"]'); if (rm) rm.focus({ preventScroll: true }); }
      else { var ni = n.querySelector('#cp-code'); if (ni) ni.focus({ preventScroll: true }); }
    }).catch(function () { netErr(); if (btn) { btn.classList.remove('is-loading'); btn.removeAttribute('aria-busy'); } });
  }

  /* ---------- clipboard (#81: promise rejection handled) ---------- */
  function copyText(text) {
    var ok = function () { toast({ tone: 'info', icon: 'copy', title: T.copied, html: '<b>' + esc(text) + '</b> ' + T.inClip }); };
    var fail = function () { toast({ tone: 'info', icon: 'copy', title: T.clipFail, html: '<b>' + esc(text) + '</b>' }); };
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(ok, function () { legacyCopy(text) ? ok() : fail(); });
      else legacyCopy(text) ? ok() : fail();
    } catch (e) { fail(); }
  }
  function legacyCopy(text) { try { var t = doc.createElement('textarea'); t.value = text; t.setAttribute('readonly', ''); t.style.position = 'fixed'; t.style.opacity = '0'; doc.body.appendChild(t); t.select(); var r = doc.execCommand('copy'); t.remove(); return r; } catch (e) { return false; } }

  /* ---------- announcements: remember dismissal per visitor (V1-04) + restore (X10) ---------- */
  function hiddenAnns() { var h = store('ea_ann_hidden'); return Array.isArray(h) ? h : []; }
  function annRestoreLine(list) {
    var p = frag('<p class="ea-announce__restore">Njoftimet u fshehën. <button type="button" data-ea="ann-restore">Shfaqi përsëri</button></p>');
    list.parentNode.insertBefore(p, list.nextSibling); list.hidden = true;
  }
  function initAnns() {
    var list = doc.querySelector('.ea-announce'); if (!list) return;
    var h = hiddenAnns(), left = 0;
    list.querySelectorAll('[data-ann-key]').forEach(function (c) { if (h.indexOf(c.getAttribute('data-ann-key')) > -1) c.hidden = true; else left++; });
    list.setAttribute('data-count', left); if (!left) annRestoreLine(list);
  }

  /* ---------- click ---------- */
  function onClick(e) {
    var t = closest(e.target, '[data-ea]');
    if (!t) {
      doc.querySelectorAll('.ea-search.is-open').forEach(function (s) { if (!s.contains(e.target)) closeSuggest(s); });
      return;
    }
    var kind = t.getAttribute('data-ea');
    if (kind === 'fav') {
      e.preventDefault(); var id = String(t.getAttribute('data-pid') || ''), list = favs(), k = list.indexOf(id);
      if (k > -1) list.splice(k, 1); else if (id) list.push(id);
      store('ea_favs', list.slice(-200)); syncFavs();
      if (!reduced) { t.classList.remove('is-pop'); void t.offsetWidth; t.classList.add('is-pop'); }
      return;
    }
    if (kind === 'add') {
      e.preventDefault(); if (t.classList.contains('is-done') || t.classList.contains('is-loading')) return;
      var label = t.innerHTML, qty = 1, buy = closest(t, '.ea-pdp__buy'), si = buy && buy.querySelector('.ea-stepper input');
      if (si) qty = clampStepper(closest(si, '.ea-stepper'), si.value);
      t.classList.add('is-loading'); t.setAttribute('aria-busy', 'true');
      post('/shporta/shto', { product: t.getAttribute('data-slug'), qty: qty }).then(function (d) {
        t.classList.remove('is-loading'); t.removeAttribute('aria-busy');
        if (d.ok === false) { toast({ tone: 'error', title: d.message || T.error }); return; }
        t.classList.remove('ea-btn--primary'); t.classList.add('is-done'); t.innerHTML = icon('check') + (LANG === 'en' ? 'Added' : 'U shtua');
        var card = closest(t, '.ea-pcard'); if (card) card.classList.add('is-added');
        fly(t); setTimeout(function () { setCartCount(d.count, true); }, reduced ? 0 : 480);
        toast({ img: t.getAttribute('data-img'), title: T.added, html: (qty > 1 ? qty + ' × ' : '') + esc(t.getAttribute('data-name') || '') + (d.note ? ' · ' + esc(d.note) : '') + ' · <a href="/shporta">' + T.seeCart + '</a>' });
        setTimeout(function () { t.classList.remove('is-done'); t.classList.add('ea-btn--primary'); t.innerHTML = label; if (card) card.classList.remove('is-added'); }, 2200);
      }).catch(function () { t.classList.remove('is-loading'); t.removeAttribute('aria-busy'); netErr(); });
      return;
    }
    if (kind === 'inc' || kind === 'dec') {
      var st = closest(t, '.ea-stepper'), inp = st.querySelector('input');
      var v = clampStepper(st, (parseInt(inp.value, 10) || 1) + (kind === 'inc' ? 1 : -1));
      var ci = closest(t, '.ea-citem'); if (ci) cartQty(ci, v);
      return;
    }
    if (kind === 'cart-remove') {
      var row = closest(t, '.ea-citem'), pid = row.getAttribute('data-slug'), oldQty = row.querySelector('.ea-stepper input').value, name = (row.querySelector('.ea-citem__name') || {}).textContent || '';
      row.classList.add('is-removing'); row.style.opacity = '0';
      post('/shporta/hiq', { product: pid }).then(function (d) {
        setTimeout(function () { row.remove(); renderCart(d); }, 200);
        var tt = toast({ tone: 'info', title: T.removed, html: esc(name) + ' · <button class="ea-btn ea-btn--link" type="button" data-ea="cart-undo" data-pid="' + esc(pid) + '" data-qty="' + esc(oldQty) + '">' + T.undo + '</button>', ms: 5000 });
      }).catch(function () { row.classList.remove('is-removing'); row.style.opacity = ''; netErr(); });
      return;
    }
    if (kind === 'cart-undo') { post('/shporta/shto', { product: t.getAttribute('data-pid'), qty: t.getAttribute('data-qty') }).then(function () { location.reload(); }).catch(netErr); return; }
    if (kind === 'cart-clear') { setOpen('ea-clearcart', true, t); return; }
    if (kind === 'thumb') {
      var g = closest(t, '.ea-gallery'), main = g.querySelector('[data-ea-main]'), wrapM = main.parentElement;
      g.querySelectorAll('[data-ea="thumb"]').forEach(function (b) { b.removeAttribute('aria-current'); }); t.setAttribute('aria-current', 'true');
      wrapM.classList.add('is-loading'); setTimeout(function () { main.src = t.getAttribute('data-src'); wrapM.classList.remove('is-loading'); }, reduced ? 0 : 160);
      return;
    }
    if (kind === 'zoom' || kind === 'zoom-btn') { if (kind === 'zoom' && closest(e.target, '.ea-fav, .ea-gallery__zoom')) return; var m = kind === 'zoom' ? t : closest(t, '.ea-gallery__main'); m.classList.toggle('is-zoom'); return; }
    if (kind === 'open' || kind === 'open-modal') { e.preventDefault(); setOpen(t.getAttribute('data-target'), true, t); return; }
    if (kind === 'close') {
      e.preventDefault();
      var id2 = t.getAttribute('data-target');
      if (!id2) { var md = closest(t, '.ea-modal, .ea-drawer'); id2 = md && md.id; }
      if (id2 === 'ea-odrawer') { closeOrderDrawer(); return; }
      if (id2) setOpen(id2, false);
      return;
    }
    if (kind === 'dismiss') {
      var card2 = closest(t, '.ea-acard'), list2 = card2.parentElement, h = hiddenAnns();
      h.push(card2.getAttribute('data-ann-key')); store('ea_ann_hidden', h.slice(-50));
      card2.classList.add('is-dismissed');
      setTimeout(function () { card2.hidden = true; var n = list2.querySelectorAll('.ea-acard:not([hidden])').length; list2.setAttribute('data-count', n); if (!n) { annRestoreLine(list2); var rb = doc.querySelector('[data-ea="ann-restore"]'); if (rb) rb.focus(); } else { var nx = list2.querySelector('.ea-acard:not([hidden]) .ea-acard__close'); if (nx) nx.focus({ preventScroll: true }); } }, reduced ? 0 : 260);
      return;
    }
    if (kind === 'ann-restore') {
      store('ea_ann_hidden', []); var l3 = doc.querySelector('.ea-announce');
      if (l3) { l3.hidden = false; l3.querySelectorAll('.ea-acard').forEach(function (c) { c.hidden = false; c.classList.remove('is-dismissed'); }); l3.setAttribute('data-count', l3.querySelectorAll('.ea-acard').length); }
      var line = closest(t, '.ea-announce__restore'); if (line) line.remove();
      return;
    }
    if (kind === 'view') {
      var grid = doc.querySelector('[data-ea-grid]'); if (!grid) return;
      var list = t.getAttribute('data-view') === 'list'; grid.classList.toggle('is-list', list); store('ea_view', list ? 'list' : 'grid');
      closest(t, '.ea-seg').querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b === t); });
      return;
    }
    if (kind === 'filter-all') { var ff = doc.getElementById(t.getAttribute('form')); doc.querySelectorAll('input[name="kategoria"][form="' + t.getAttribute('form') + '"], input[name="nenkategoria"][form="' + t.getAttribute('form') + '"]').forEach(function (c) { c.checked = false; }); t.checked = true; return; }
    if (kind === 'load-more') {
      e.preventDefault(); if (t.classList.contains('is-loading')) return;
      var url = t.getAttribute('href'); t.classList.add('is-loading'); t.setAttribute('aria-busy', 'true');
      fetch(url + (url.indexOf('?') > -1 ? '&' : '?') + 'partial=1', { headers: { 'Accept': 'application/json' }, credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) {
        var gridEl = doc.querySelector('[data-ea-grid]'), w = doc.createElement('div'); w.innerHTML = d.html; var first = w.firstElementChild;
        while (w.firstChild) gridEl.appendChild(w.firstChild); syncFavs();
        var lm = closest(t, '[data-ea-loadmore]'); lm.querySelector('[role="status"]').textContent = T.shown.replace('%a', d.shown).replace('%b', d.total);
        lm.querySelector('.ea-progressline span').style.width = Math.round(d.shown / d.total * 100) + '%';
        if (d.next) { t.href = d.next; t.classList.remove('is-loading'); t.removeAttribute('aria-busy'); } else t.remove();
        if (first) { var a = first.querySelector('.ea-pcard__name a'); if (a) a.focus({ preventScroll: true }); }
      }).catch(function () { location.href = url; });
      return;
    }
    if (kind === 'toast-close') { leave(closest(t, '.ea-toast')); return; }
    if (kind === 'copy') { var text = t.getAttribute('data-copy') || ''; if (text) copyText(text); if (closest(t, '.ea-confirm__ref')) t.innerHTML = icon('check'); return; }
    if (kind === 'cookie-ok') {
      var ck = closest(t, '[data-ea-cookie]'); ck.classList.add('is-hidden');
      doc.cookie = 'ea_cookie_ok=' + new Date().toISOString().slice(0, 10) + '; Max-Age=' + 60 * 60 * 24 * 365 + '; Path=/; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
      setTimeout(function () { ck.remove(); }, 260); return;
    }
    if (kind === 'discount') {
      var wrapD = closest(t, '[data-ea-discount]'), base = parseInt(wrapD.getAttribute('data-base'), 10) || 0, pct = parseInt(t.getAttribute('data-pct'), 10);
      var baseInput = doc.querySelector('[data-ea-baseprice]'); if (baseInput) base = parseInt(String(baseInput.value).replace(/\D/g, ''), 10) || 0;
      wrapD.querySelectorAll('[data-ea="discount"]').forEach(function (b) { b.setAttribute('aria-pressed', b === t); });
      var hid = wrapD.querySelector('input[name="discount_pct"]'); if (hid) hid.value = pct;
      updateDiscount(wrapD, base, pct); return;
    }
    /* checkout */
    if (kind === 'loc-gps') { locGps(closest(t, '[data-ea-loc]')); return; }
    if (kind === 'loc-map') { var lb = closest(t, '[data-ea-loc]'); setLoc(lb, { state: 'map', src: 'map' }); return; }
    if (kind === 'loc-confirm') { var cb = closest(t, '[data-ea-loc]'); setLoc(cb, { state: 'ok', src: 'map' }); var nb = cb.querySelector('.ea-loc__status a'); if (nb) nb.focus({ preventScroll: true }); return; }
    if (kind === 'coupon-apply') { e.preventDefault(); applyCoupon(closest(t, 'form')); return; }
    if (kind === 'coupon-remove') { applyCoupon(closest(t, 'form'), true); return; }
    /* confirmation */
    if (kind === 'wa-send') {
      var conf = doc.querySelector('[data-ea-confirm]');
      if (t.getAttribute('data-has-number') === '0') toast({ tone: 'info', title: T.noNumber, text: T.noNumberText, ms: 6000 });
      if (conf) post('/porosia/' + encodeURIComponent(conf.getAttribute('data-ref')) + '/wa', { t: conf.getAttribute('data-token') }).catch(function () { });
      markWaOpened();
      return; /* the link itself opens wa.me (target=_blank, rel=noopener) */
    }
    if (kind === 'sort') return;
    if (window.EA_ADMIN && window.EA_ADMIN.click) window.EA_ADMIN.click(kind, t, e);
  }
  function updateDiscount(wrapD, base, pct) {
    var nw = Math.round(base * (1 - pct / 100));
    wrapD.querySelector('[data-ea-new]').textContent = String(nw).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' L';
    var old = wrapD.querySelector('[data-ea-old]'); old.textContent = String(base).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' L';
    old.classList.toggle('ea-price--old', pct > 0); old.style.fontSize = pct ? '16px' : '';
    wrapD.querySelector('[data-ea-pct]').textContent = pct ? '−' + pct + '%' : '';
  }
  window.EA_updateDiscount = updateDiscount;
  function markWaOpened() {
    doc.querySelectorAll('[data-ea-wablock]').forEach(function (b) {
      if (b.classList.contains('is-sent')) return;
      b.classList.add('is-sent');
      b.querySelector('.ea-wablock__ic').innerHTML = icon('circle-check');
      b.querySelector('.ea-wablock__text').innerHTML = '<b>Fatura u hap në WhatsApp te numri i marketit.</b><span>Nëse nuk e shtypët “Dërgo” brenda WhatsApp-it, dërgojeni sërish.</span>';
      var btn = b.querySelector('[data-ea="wa-send"]'); if (btn) btn.lastChild.textContent = 'Dërgo sërish në WhatsApp';
    });
    doc.querySelectorAll('[data-ea-wabar]').forEach(function (b) { b.classList.add('is-sent'); });
    var step = doc.querySelector('[data-ea-step-wa]');
    if (step) { var ic = step.querySelector('.ea-checklist__ic'); ic.className = 'ea-checklist__ic ea-checklist__ic--ok'; ic.innerHTML = icon('check'); step.querySelector('.ea-caption').textContent = 'U hap në WhatsApp — sigurohuni që shtypët “Dërgo”.'; }
  }
  function closeOrderDrawer() {
    var od = doc.getElementById('ea-odrawer'); if (!od) return;
    setOpen('ea-odrawer', false);
    if (od.hasAttribute('data-dynamic')) { var s0 = od.previousElementSibling; if (s0 && s0.classList.contains('ea-scrim')) s0.remove(); od.remove(); }
    doc.querySelectorAll('tr.is-selected[data-ref]').forEach(function (tr) { tr.classList.remove('is-selected'); });
  }
  window.EA = { setOpen: setOpen, toast: toast, post: post, swap: swap, closeOrderDrawer: closeOrderDrawer, copyText: copyText, icon: icon, esc: esc };

  /* ---------- other events ---------- */
  function onInput(e) {
    var i = e.target; if (!i.matches) return;
    if (i.classList.contains('ea-search__input') && e.type === 'input') { suggest(i); return; }
    var form = closest(i, '[data-ea-checkout]');
    if (form && CHECKS[i.id]) { var f = closest(i, '.ea-field'); if (f && f.classList.contains('is-invalid')) fieldMsg(i, CHECKS[i.id](i.value.trim())); }
    if (form && i.id === 'co-terms') { var tl = closest(i, '.ea-terms'); if (tl && i.checked) tl.classList.remove('is-invalid'); }
    if (i.id === 'cp-code') { var cp = closest(i, '.ea-coupon'); if (cp && cp.classList.contains('is-invalid')) { cp.classList.remove('is-invalid'); i.removeAttribute('aria-invalid'); cp.querySelector('.ea-coupon__msg').textContent = 'Çdo kupon përdoret vetëm një herë dhe shënohet në faturë.'; } }
    if (e.type === 'change') {
      if (i.hasAttribute('data-ea-autosubmit')) { var fid = i.getAttribute('form'); var fe = fid && doc.getElementById(fid); if (fe && !closest(i, '.ea-drawer')) fe.requestSubmit ? fe.requestSubmit() : fe.submit(); return; }
      if (i.matches('select[data-ea="sort"]')) { var u = new URL(location.href); u.searchParams.set(i.getAttribute('data-param') || 'rendit', i.value); u.searchParams.delete('faqe'); location.href = u.pathname + u.search; return; }
      if (i.matches('input[name="kategoria"]') && i.checked) { var all = doc.querySelector('[data-ea="filter-all"][form="' + i.getAttribute('form') + '"]'); if (all) all.checked = false; }
      if (i.matches('.ea-stepper input')) { var st = closest(i, '.ea-stepper'), v = clampStepper(st, i.value), ci = closest(i, '.ea-citem'); if (ci) cartQty(ci, v); }
    }
    if (window.EA_ADMIN && window.EA_ADMIN.input) window.EA_ADMIN.input(e);
  }
  function onBlur(e) {
    var i = e.target; if (!i.matches) return;
    if (i.matches('.ea-stepper input')) { clampStepper(closest(i, '.ea-stepper'), i.value); return; }
    if (!closest(i, '[data-ea-checkout]') || !CHECKS[i.id]) return;
    if (i.value.trim()) fieldMsg(i, CHECKS[i.id](i.value.trim()));
  }
  function onSubmit(e) {
    var f = e.target;
    if (f.matches('[data-ea="newsletter"]')) {
      e.preventDefault();
      var inp = f.querySelector('input[type="email"]'), v = inp.value.trim(), btn = f.querySelector('button[type="submit"]');
      f.classList.remove('is-error', 'is-success', 'is-duplicate');
      if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(v)) { f.classList.add('is-error'); inp.setAttribute('aria-invalid', 'true'); inp.focus(); return; }
      inp.removeAttribute('aria-invalid'); btn.classList.add('is-loading'); btn.setAttribute('aria-busy', 'true');
      post('/abonohu', { email: v, source: (f.querySelector('input[name="source"]') || {}).value || 'ballina' }).then(function (d) {
        btn.classList.remove('is-loading'); btn.removeAttribute('aria-busy');
        if (d.ok) { f.classList.add('is-success'); inp.value = ''; } else if (d.error === 'duplicate') f.classList.add('is-duplicate'); else if (d.error === 'invalid') { f.classList.add('is-error'); inp.focus(); } else toast({ tone: 'error', title: T.error, text: T.retry });
      }).catch(function () { btn.classList.remove('is-loading'); btn.removeAttribute('aria-busy'); netErr(); });
      return;
    }
    if (f.matches('[data-ea-checkout]')) {
      var sub = e.submitter;
      if (sub && sub.getAttribute('data-ea') === 'coupon-apply') { e.preventDefault(); applyCoupon(f); return; }
      if (!validateCheckout(f)) { e.preventDefault(); return; }
      var cbtn = f.querySelector('[data-ea="confirm-order"]');
      if (cbtn) { if (cbtn.classList.contains('is-loading')) { e.preventDefault(); return; } cbtn.classList.add('is-loading'); cbtn.setAttribute('aria-busy', 'true'); }
      return; /* real POST: server validates again, creates the order and redirects */
    }
    if (window.EA_ADMIN && window.EA_ADMIN.submit) window.EA_ADMIN.submit(e);
  }
  function onFocus(e) {
    var i = e.target; if (!i.classList || !i.classList.contains('ea-search__input')) return;
    var s = closest(i, '.ea-search'); if (s.querySelector('.ea-suggest').children.length && i.value.trim().length >= 2) { s.classList.add('is-open'); i.setAttribute('aria-expanded', 'true'); }
  }
  function onKey(e) {
    var tg = e.target;
    if (e.key === 'Enter' && tg && tg.id === 'cp-code') { e.preventDefault(); var b = closest(tg, 'form').querySelector('[data-ea="coupon-apply"]'); if (b) b.click(); return; }
    if (tg && tg.classList && tg.classList.contains('ea-search__input')) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { if (moveSuggest(tg, e.key === 'ArrowDown' ? 1 : -1)) e.preventDefault(); return; }
      if (e.key === 'Enter') { var sel = closest(tg, '.ea-search').querySelector('[aria-selected="true"]'); if (sel && closest(tg, '.ea-search').classList.contains('is-open')) { e.preventDefault(); location.href = sel.href; } return; }
      if (e.key === 'Escape') { closeSuggest(closest(tg, '.ea-search')); return; }
    }
    if (window.EA_ADMIN && window.EA_ADMIN.key && window.EA_ADMIN.key(e)) return;
    if (e.key === 'Tab') {
      var top = topOverlay(); if (!top) return;
      var box = top.classList.contains('ea-modal') ? top.querySelector('.ea-dialog') : top;
      var fs = [].filter.call(box.querySelectorAll(FOCUSABLE), function (n) { return n.offsetParent !== null || n === doc.activeElement; });
      if (!fs.length) return;
      if (e.shiftKey && doc.activeElement === fs[0]) { e.preventDefault(); fs[fs.length - 1].focus(); }
      else if (!e.shiftKey && doc.activeElement === fs[fs.length - 1]) { e.preventDefault(); fs[0].focus(); }
      else if (!box.contains(doc.activeElement)) { e.preventDefault(); fs[0].focus(); }
      return;
    }
    if (e.key !== 'Escape') return;
    var o = topOverlay();
    if (o) { if (o.id === 'ea-odrawer') closeOrderDrawer(); else setOpen(o.id, false); return; }
    doc.querySelectorAll('.ea-search.is-open').forEach(closeSuggest);
  }

  /* ---------- init ---------- */
  doc.addEventListener('click', onClick); doc.addEventListener('submit', onSubmit);
  doc.addEventListener('focusin', onFocus); doc.addEventListener('keydown', onKey);
  doc.addEventListener('input', onInput); doc.addEventListener('change', onInput); doc.addEventListener('focusout', onBlur);
  doc.querySelectorAll('[data-indeterminate]').forEach(function (c) { c.indeterminate = true; });
  syncFavs(); initAnns();
  if (store('ea_view') === 'list') { var gv = doc.querySelector('[data-ea-grid]'), lb = doc.querySelector('[data-ea="view"][data-view="list"]'); if (gv && lb && getComputedStyle(lb).display !== 'none') { gv.classList.add('is-list'); lb.closest('.ea-seg').querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b === lb); }); } }
  doc.querySelectorAll('.ea-stepper').forEach(function (st) { var i = st.querySelector('input'); if (i) clampStepper(st, i.value); });
  var es = doc.querySelector('[data-ea-errsum]'); if (es) { es.focus({ preventScroll: true }); es.scrollIntoView({ block: 'center' }); }
  var locBox = doc.querySelector('[data-ea-loc][data-state="ok"]'); if (locBox) window.addEventListener('load', function () { mountMap(locBox, 17); });
  /* sticky green WhatsApp bar on phones: only while the big panel is off-screen (CR-15) */
  var bar = doc.querySelector('[data-ea-wabar]'), blk = doc.querySelector('[data-ea-wablock]');
  if (bar && blk && window.IntersectionObserver) new IntersectionObserver(function (en) { bar.style.visibility = en[0].isIntersecting ? 'hidden' : ''; }, { threshold: 0.35 }).observe(blk);
})();
