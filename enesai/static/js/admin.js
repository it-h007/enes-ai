/* ENES’AI admin behaviours. Everything works without JS as plain links/forms; this file
   adds confirmations, instant toggles, the order drawer, bulk selection and progress. */
(function () {
  'use strict';
  var doc = document, EA = window.EA;
  if (!EA) return;
  function closest(el, sel) { while (el && el.nodeType === 1) { if (el.matches(sel)) return el; el = el.parentElement; } return null; }

  /* ---------- danger confirmation modal (replaces window.confirm) ---------- */
  var pendingForm = null, pendingSubmitter = null;
  function confirmModal(text, form, submitter) {
    var m = doc.getElementById('ea-confirm');
    if (!m) {
      var w = doc.createElement('div');
      w.innerHTML = '<div class="ea-modal" role="presentation" id="ea-confirm" aria-hidden="true"><div class="ea-dialog ea-dialog--danger" role="dialog" aria-modal="true" aria-labelledby="dlg-t-confirm"><div class="ea-dialog__head"><div class="ea-row" style="align-items:flex-start;gap:14px"><span class="ea-dialog__danger-ic">' + EA.icon('triangle-alert') + '</span><div><h2 class="ea-dialog__title" id="dlg-t-confirm">Konfirmoni</h2><p class="ea-dialog__sub" data-ea-confirmtext></p></div></div><button class="ea-iconbtn" type="button" aria-label="Mbyll" data-ea="close">' + EA.icon('x') + '</button></div><div class="ea-dialog__foot"><button class="ea-btn ea-btn--ghost ea-btn--sm" type="button" data-ea="close">Anulo</button><button class="ea-btn ea-btn--danger ea-btn--sm ea-btn--square" type="button" data-ea="confirm-yes">Po, vazhdo</button></div></div></div>';
      m = w.firstChild; (closest(doc.querySelector('.ea-admin'), '.ea-site') || doc.body).appendChild(m);
    }
    m.querySelector('[data-ea-confirmtext]').textContent = text;
    pendingForm = form; pendingSubmitter = submitter; EA.setOpen('ea-confirm', true, submitter);
  }

  function fetchPost(url, body) {
    return EA.post(url, body || {});
  }

  /* ---------- order drawer ---------- */
  function openDrawer(nr, opener) {
    fetch(location.pathname.replace(/\/porosite.*$/, '/porosite') + '/' + encodeURIComponent(nr) + '/drawer', { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
      .then(function (html) { mountDrawer(html, opener); doc.querySelectorAll('tr[data-ref]').forEach(function (tr) { tr.classList.toggle('is-selected', tr.getAttribute('data-ref') === nr); }); })
      .catch(function () { location.href = opener.href; });
  }
  function mountDrawer(html, opener) {
    var old = doc.getElementById('ea-odrawer'); if (old) { EA.closeOrderDrawer(); }
    var site = closest(doc.querySelector('.ea-admin'), '.ea-site'), w = doc.createElement('div'); w.innerHTML = html;
    var nodes = [].slice.call(w.children); nodes.forEach(function (n) { if (n.classList.contains('ea-drawer')) { n.classList.remove('is-open'); n.setAttribute('data-dynamic', ''); } if (n.classList.contains('ea-scrim')) n.classList.remove('is-open'); site.insertBefore(n, doc.querySelector('[data-ea-toasts]')); });
    requestAnimationFrame(function () { EA.setOpen('ea-odrawer', true, opener); });
  }
  /* a drawer rendered by the server (?hap=…) gets the same focus handling */
  var srv = doc.getElementById('ea-odrawer');
  if (srv) { srv.classList.remove('is-open'); var s0 = srv.previousElementSibling; if (s0) s0.classList.remove('is-open'); srv.setAttribute('data-dynamic', ''); EA.setOpen('ea-odrawer', true, doc.querySelector('[data-ea="order-open"]')); }

  /* ---------- click hook from enesai.js ---------- */
  function click(kind, t, e) {
    if (kind === 'order-open') { e.preventDefault(); openDrawer(t.getAttribute('data-ref'), t); return; }
    if (kind === 'confirm-yes') {
      var f = pendingForm, sb = pendingSubmitter; EA.setOpen('ea-confirm', false);
      if (f) { f.setAttribute('data-confirmed', '1'); if (f.requestSubmit) f.requestSubmit(sb && sb.form === f ? sb : undefined); else f.submit(); }
      return;
    }
    if (kind === 'bulk-clear') { doc.querySelectorAll('[data-ea-rowcheck], [data-ea-checkall]').forEach(function (c) { c.checked = false; }); syncBulk(); return; }
    if (kind === 'coupon-pct') {
      var v = t.getAttribute('data-pct'), inp = doc.getElementById('cp-new-pct');
      closest(t, '.ea-discount__opts').querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b === t); });
      if (inp) { inp.value = v; couponExample(); } return;
    }
    if (kind === 'lang-tab') {
      var panel = closest(t, '.ea-panel-a') || closest(t, 'form'), lang = t.getAttribute('data-lang');
      closest(t, '.ea-seg').querySelectorAll('button').forEach(function (b) { b.setAttribute('aria-pressed', b === t); });
      panel.querySelectorAll('[data-lang-pane]').forEach(function (p) { p.hidden = p.getAttribute('data-lang-pane') !== lang; });
      return;
    }
    if (kind === 'hours-copy') {
      var o0 = doc.querySelector('input[name="h-open-0"]'), c0 = doc.querySelector('input[name="h-close-0"]'), x0 = doc.querySelector('input[name="h-closed-0"]');
      for (var i = 1; i < 7; i++) { doc.querySelector('input[name="h-open-' + i + '"]').value = o0.value; doc.querySelector('input[name="h-close-' + i + '"]').value = c0.value; doc.querySelector('input[name="h-closed-' + i + '"]').checked = x0.checked; }
      EA.toast({ tone: 'info', title: 'U kopjua orari i së hënës', text: 'Ruani cilësimet për ta aplikuar.' }); return;
    }
    if (kind === 'copy-list') { var el = doc.getElementById(t.getAttribute('data-target')); if (el) EA.copyText(el.value || el.textContent); return; }
    if (kind === 'inv-try' || kind === 'inv-open') return; /* plain links */
  }
  function couponExample() {
    var ex = doc.querySelector('[data-ea-cpex]'), inp = doc.getElementById('cp-new-pct'); if (!ex || !inp) return;
    var v = parseInt(inp.value, 10) || 0, max = parseInt(inp.getAttribute('max'), 10) || 90;
    ex.innerHTML = v > 0 && v <= max ? 'Shembull: porosi 3.000 L → zbritje <b>' + String(Math.round(3000 * v / 100)).replace(/\B(?=(\d{3})+(?!\d))/g, '.') + ' L</b>' : 'Shkruani 1–' + max + '%';
    doc.querySelectorAll('[data-ea="coupon-pct"]').forEach(function (b) { b.setAttribute('aria-pressed', +b.getAttribute('data-pct') === v); });
  }

  /* ---------- inputs ---------- */
  function syncBulk() {
    var n = doc.querySelectorAll('[data-ea-rowcheck]:checked').length, wrap = doc.querySelector('[data-ea-bulkwrap]');
    if (wrap) { wrap.hidden = !n; wrap.querySelector('[data-ea-bulkcount]').textContent = n; }
    doc.querySelectorAll('[data-ea-rowcheck]').forEach(function (c) { var tr = closest(c, 'tr'); if (tr) tr.classList.toggle('is-selected', c.checked); });
    var all = doc.querySelector('[data-ea-checkall]'), tot = doc.querySelectorAll('[data-ea-rowcheck]').length;
    if (all) { all.checked = n && n === tot; all.indeterminate = n > 0 && n < tot; }
  }
  function input(e) {
    var i = e.target;
    if (e.type === 'change') {
      if (i.hasAttribute('data-ea-submit')) { var f = closest(i, 'form'); if (f) f.submit(); return; }
      if (i.hasAttribute('data-ea-autosubmit-form')) { var f2 = closest(i, 'form'); if (f2) f2.submit(); return; }
      if (i.hasAttribute('data-ea-toggle')) {
        var url = i.getAttribute('data-ea-toggle'); i.disabled = true;
        fetchPost(url).then(function (d) { i.disabled = false; if (d.ok === false) { i.checked = !i.checked; EA.toast({ tone: 'error', title: d.message || 'Nuk u ruajt' }); } else EA.toast({ title: 'U ruajt', ms: 1600 }); })
          .catch(function () { i.disabled = false; i.checked = !i.checked; EA.toast({ tone: 'error', title: 'Nuk u ruajt', text: 'Kontrolloni lidhjen.' }); });
        return;
      }
      if (i.hasAttribute('data-ea-checkall')) { doc.querySelectorAll('[data-ea-rowcheck]').forEach(function (c) { c.checked = i.checked; }); syncBulk(); return; }
      if (i.hasAttribute('data-ea-rowcheck')) { syncBulk(); return; }
      if (i.hasAttribute('data-ea-catselect')) { fillSubs(i); return; }
      if (i.hasAttribute('data-ea-removeimg')) { var tile = closest(i, '.ea-uploader__tile'); tile.style.opacity = i.checked ? '.35' : ''; return; }
      if (i.hasAttribute('data-ea-photos')) { var names = [].map.call(i.files, function (f) { return f.name; }); var p = doc.querySelector('[data-ea-photonames]'); if (p) p.textContent = names.length ? 'Do të ngarkohen: ' + names.join(', ') : ''; return; }
      if (i.matches('[data-ea-dropzone] input[type=file]')) { var lbl = closest(i, '[data-ea-dropzone]').querySelector('[data-ea-dropname]'); if (lbl && i.files[0]) lbl.textContent = i.files[0].name; return; }
      if (i.hasAttribute('data-ea-chipcheck') && !i.checked) { closest(i, '.ea-chip').remove(); return; }
      if (i.name === 'role' && closest(i, '#ea-opmodal')) { managerOnly(i.value); return; }
      if (i.name === 'type' && doc.querySelector('[data-ea-jobfields]')) { doc.querySelector('[data-ea-jobfields]').hidden = i.value !== 'pune'; return; }
      if (i.name === 'price' && i.hasAttribute('data-ea-baseprice')) { priceChanged(i); return; }
    }
    if (i.id === 'cp-new-pct') couponExample();
    if (i.id === 'cp-new-code') { var pos = i.selectionStart; i.value = i.value.toUpperCase(); try { i.setSelectionRange(pos, pos); } catch (x) { } }
    if (i.hasAttribute && i.hasAttribute('data-ea-typeconfirm')) { var btn = doc.querySelector('[data-ea-typeconfirm-btn]'); if (btn) btn.disabled = i.value.trim() !== i.getAttribute('data-ea-typeconfirm'); }
    if (i.name === 'price' && i.hasAttribute('data-ea-baseprice')) priceChanged(i);
  }
  function priceChanged(i) {
    var wrap = doc.querySelector('[data-ea-discount]'); if (!wrap || !window.EA_updateDiscount) return;
    var base = parseInt(String(i.value).replace(/\D/g, ''), 10) || 0, pct = parseInt((wrap.querySelector('input[name="discount_pct"]') || {}).value, 10) || 0;
    wrap.setAttribute('data-base', base); window.EA_updateDiscount(wrap, base, pct);
  }
  function fillSubs(sel) {
    var sub = doc.querySelector('[data-ea-subselect]'); if (!sub) return;
    var map = {}; try { map = JSON.parse(sub.getAttribute('data-subs') || '{}'); } catch (x) { }
    var list = map[sel.value] || [];
    sub.innerHTML = '<option value="">— Asnjë —</option>' + list.map(function (s) { return '<option value="' + s[0] + '">' + EA.esc(s[1]) + '</option>'; }).join('');
  }
  function managerOnly(role) {
    doc.querySelectorAll('[data-ea-manager-only]').forEach(function (c) { c.disabled = role !== 'manager'; if (role !== 'manager') c.checked = false; });
  }
  var roleSel = doc.querySelector('#ea-opmodal select[name="role"]'); if (roleSel) managerOnly(roleSel.value);
  var typeSel = doc.querySelector('select[name="type"]'), jf = doc.querySelector('[data-ea-jobfields]'); if (typeSel && jf) jf.hidden = typeSel.value !== 'pune';

  /* ---------- submits ---------- */
  function submit(e) {
    var f = e.target;
    var needs = f.getAttribute('data-confirm') || (e.submitter && e.submitter.getAttribute('data-confirm'));
    if (needs && f.getAttribute('data-confirmed') !== '1') { e.preventDefault(); confirmModal(needs, f, e.submitter); return; }
    f.removeAttribute('data-confirmed');
    if (f.hasAttribute('data-ea-statusform') && window.fetch) {
      e.preventDefault();
      var st = e.submitter ? e.submitter.value : '';
      EA.post(f.action, { status: st }).then(function (d) {
        if (d.ok === false) { EA.toast({ tone: 'error', title: d.message || 'Gabim' }); return; }
        var dr = doc.getElementById('ea-odrawer'), w = doc.createElement('div'); w.innerHTML = d.drawer;
        var nd = w.querySelector('.ea-drawer'); dr.replaceWith(nd); nd.setAttribute('data-dynamic', '');
        var first = nd.querySelector('[aria-pressed="true"], .ea-iconbtn'); if (first) first.focus({ preventScroll: true });
        EA.toast({ title: 'Statusi u ndryshua', text: d.message });
        var row = doc.querySelector('tr[data-ref="' + nd.getAttribute('data-ref') + '"] .ea-status');
        var chip = nd.querySelector('.ea-drawer__head .ea-status'); if (row && chip) row.outerHTML = chip.outerHTML;
      }).catch(function () { f.submit(); });
      return;
    }
    if (f.hasAttribute('data-ea-bulkform') && e.submitter && e.submitter.value === 'delete') return; /* confirmed above */
  }

  /* ---------- import progress polling ---------- */
  var prog = doc.querySelector('[data-ea-importprogress]');
  if (prog) {
    var poll = function () {
      fetch(prog.getAttribute('data-ea-importprogress'), { credentials: 'same-origin' }).then(function (r) { return r.json(); }).then(function (d) {
        var pc = d.total ? Math.round(d.done * 100 / d.total) : 100;
        prog.setAttribute('aria-valuenow', pc); prog.querySelector('[data-ea-pc]').textContent = pc + '%'; prog.querySelector('[data-ea-bar]').style.width = pc + '%';
        prog.querySelector('[data-ea-rows]').textContent = d.done + ' nga ' + d.total + ' rreshta';
        if (d.status === 'running') setTimeout(poll, 900); else location.href = prog.getAttribute('data-done-url');
      }).catch(function () { setTimeout(poll, 3000); });
    };
    setTimeout(poll, 600);
  }

  /* ---------- drag to reorder rows (categories, announcements) ---------- */
  doc.querySelectorAll('[data-ea-sortable]').forEach(function (tb) {
    var drag = null;
    tb.addEventListener('dragstart', function (e) { drag = closest(e.target, 'tr[data-id]'); if (drag) { drag.style.opacity = '.5'; e.dataTransfer.effectAllowed = 'move'; } });
    tb.addEventListener('dragover', function (e) { var tr = closest(e.target, 'tr[data-id]'); if (!drag || !tr || tr === drag) return; e.preventDefault(); var r = tr.getBoundingClientRect(); tb.insertBefore(drag, (e.clientY - r.top) > r.height / 2 ? tr.nextSibling : tr); });
    tb.addEventListener('dragend', function () {
      if (!drag) return; drag.style.opacity = ''; drag = null;
      var ids = [].map.call(tb.querySelectorAll('tr[data-id]'), function (tr) { return tr.getAttribute('data-id'); });
      var body = new URLSearchParams(); ids.forEach(function (id) { body.append('order', id); });
      fetch(tb.getAttribute('data-ea-sortable'), { method: 'POST', credentials: 'same-origin', headers: { 'X-CSRF-Token': (doc.querySelector('meta[name="csrf-token"]') || {}).content, 'X-Requested-With': 'fetch' }, body: body })
        .then(function () { EA.toast({ title: 'Renditja u ruajt', ms: 1600 }); });
    });
  });

  function key(e) {
    if (e.key === 'Enter' && e.target && e.target.hasAttribute && e.target.hasAttribute('data-ea-gsearch')) return false; /* form submits natively */
    return false;
  }
  window.EA_ADMIN = { click: click, input: input, submit: submit, key: key };
  syncBulk();
})();
