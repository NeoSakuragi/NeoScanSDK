// The Brawler Factory's ROSTER & SELECT (the Characters tab, above the cast; Bruno 2026-10-12: "Go"): who is playable
// and where he stands on the select screen (tools/brawler/roster.py: state = what the game has, merge = the checks).
// One row per fighter with a Selectable switch (a Lab-only fighter, game.json roster_benched "lab": true, onto the
// roster, or one the Factory brought back to the Lab); the select layout editor is the Lab's own (chainlab/
// selectscreen.js + selectrender.js, hosted: window.SelectHost) on the build's select.json (/brawler-factory/select.json,
// written by the ship service after each ship); a fighter not in the build yet stands there as a grey placeholder at the
// free place. Edits = the "roster" draft section (feedback-api/lab/roster: {selectable: {f: bool}, layout?}), shipped by
// Ship pending changes (the Build tab). factory.js: FactoryRoster.poll(lab/roster, rows) each poll, .card() in the cast
// view, .pending() for the Build tab.
(function () {
  'use strict';
  const LAB = 'feedback-api/lab/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v != null && v !== false) e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const clone = x => JSON.parse(JSON.stringify(x));
  let D = {}, rows = [], faces = {}, open = false, host = null;
  const root = h('div', { class: 'card roster', id: 'roster' });
  const msg = h('span', { class: 'msg', role: 'status', 'aria-live': 'polite' });
  const edCol = h('div', { id: 'selcol' });

  const G = () => D.game || null;
  const openShip = () => rows.find(r => r.roster && (r.status === 'pending' || r.status === 'building'));
  const gameSel = n => !!(G().fighters.find(f => f.name === n) || {}).selectable;
  function wantSel(n) { const s = (D.draft && D.draft.selectable) || {}; return n in s ? s[n] : gameSel(n); }
  const changed = () => G().fighters.filter(f => wantSel(f.name) !== f.selectable).map(f => f.name);
  const layoutChanged = () => !!(D.draft && D.draft.layout && !eq(norm(D.draft.layout), norm(G().layout)));
  const norm = L => Object.keys(L).sort().map(n => [n, L[n].x, L[n].y, L[n].z, L[n].facing, L[n].pose, L[n].slot]);
  const nSel = () => G().fighters.filter(f => wantSel(f.name)).length;

  // roster.py free_place / place, the same rules (the server places a fighter the draft leaves without a place)
  function freePlace(L) {
    let best = null;
    for (const y of [184, 197, 210]) for (let x = 40; x <= 728; x++) {
      let d = Infinity; for (const v of Object.values(L)) { const q = (x - v.x) ** 2 + (2.2 * (y - v.y)) ** 2; if (q < d) d = q; }
      if (!best || d > best[0]) best = [d, x, y];
    }
    return [best[1], best[2]];
  }
  function place(L, n, pose) {
    const [x, y] = freePlace(L), order = Object.keys(L).sort((a, b) => L[a].slot - L[b].slot);
    let prev = null; for (const m of order) if (L[m].x <= x && (!prev || L[m].x > L[prev].x)) prev = m;
    if (!prev && order.length) prev = order[order.length - 1];
    order.splice(prev ? order.indexOf(prev) + 1 : 0, 0, n);
    const zs = Object.keys(L).sort((a, b) => L[a].z - L[b].z); zs.splice(zs.filter(m => L[m].y <= y).length, 0, n);
    const out = clone(L); out[n] = { x, y, z: 0, facing: x > 384 ? 'left' : 'right', pose, slot: 0 };
    order.forEach((m, k) => { out[m].slot = k; }); zs.forEach((m, k) => { out[m].z = k; });
    return out;
  }
  function wantLayout() {                              // the draft's layout (else the game's) for the selectable set
    const base = clone((D.draft && D.draft.layout) || G().layout), sel = G().fighters.filter(f => wantSel(f.name));
    let L = {}; for (const f of sel) if (base[f.name]) L[f.name] = base[f.name];
    for (const k of ['slot', 'z']) Object.keys(L).sort((a, b) => L[a][k] - L[b][k]).forEach((n, i) => { L[n][k] = i; });
    for (const f of sel) if (!L[f.name]) L = place(L, f.name, f.pose);
    return L;
  }

  async function save(body, what) {
    msg.className = 'msg'; msg.textContent = 'Saving…';
    try {
      const r = await fetch(LAB + 'roster', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      D = j; msg.textContent = what + ': saved. Ship it from the Build tab (Ship pending changes).';
    } catch (e) { msg.className = 'msg bad'; msg.textContent = 'Not saved: ' + e.message; throw e; }
    finally { draw(); }
  }
  function selBody(over, layout) {
    const s = {}; for (const f of G().fighters) { const v = f.name in over ? over[f.name] : wantSel(f.name); if (v !== f.selectable) s[f.name] = v; }
    const b = { selectable: s }; const L = layout !== undefined ? layout : D.draft && D.draft.layout;
    if (L) b.layout = Object.fromEntries(Object.entries(L).filter(([n]) => (n in over ? over[n] : wantSel(n))));
    return b;
  }
  function toggle(f, on) {
    if (on && nSel() >= G().max) { msg.className = 'msg bad'; msg.textContent = `The select screen holds ${G().max} fighters (its sprites): take one off first.`; return draw(); }
    save(selBody({ [f.name]: on }), f.display + (on ? ' selectable' : ' back to the Lab only')).catch(() => {});
    if (open) openEditor();
  }

  function theme(f) { return f.music_ok ? '♪ ' + f.music : '♪ stage song'; }
  function row(f) {
    const on = wantSel(f.name), ch = on !== f.selectable, can = f.lab || f.from_lab, o = openShip();
    const sw = h('input', { type: 'checkbox', role: 'switch', 'aria-label': 'Selectable: ' + f.display, disabled: can && !o ? null : '' });
    sw.checked = on; sw.onchange = () => toggle(f, sw.checked);
    const place = on ? (f.selectable ? 'place ' + f.place : 'a free place') : 'Lab only';
    return h('div', { class: 'rrow' + (ch ? ' ch' : ''), title: can ? '' : 'in the game\'s data (only a fighter brought from the Lab goes back there)' },
      faces[f.name] ? h('img', { src: faces[f.name], alt: '', width: '28', height: '28', loading: 'lazy' }) : h('span', { class: 'noface' }),
      h('span', { class: 'rn' }, h('b', { text: f.display }), h('small', { text: place + ' · ' + theme(f) + (f.locked ? ' · locked: boss of stage ' + (f.unlock.boss_of_stage || '?') : '') + (f.face ? '' : ' · NO FACE') })),
      ch ? h('span', { class: 'tag ' + (o ? 'ship' : 'edit'), text: o ? (o.status === 'building' ? 'building' : 'queued') : 'unshipped' }) : null,
      h('label', { class: 'sw' }, sw, h('span', { text: 'Selectable' })));
  }
  function roomLine(r) {
    if (!r || r.c_used == null) return 'Room: not reported yet.';
    const mb = b => (b / 1048576).toFixed(1);
    return `Room in ${G().version}: C ROM ${mb(r.c_used)} of ${mb(r.c_cap)} MB (${mb(r.c_cap - r.c_used)} left) · P ` +
      r.p.map(p => `${p.name.replace('bank ', 'bank')} ${Math.round(p.free / 1024)} KB`).join(', ') + ' free' + (r.ok === false ? ' · bank_proof FAILED' : '');
  }
  function draw() {
    if (!G()) { root.replaceChildren(h('h2', { text: 'Roster & select' }), h('p', { class: 'note', text: 'Not known yet: the build daemon reports it when it starts and after each ship.' })); return; }
    const fs = G().fighters.slice().sort((a, b) => ((a.lab || a.from_lab ? 0 : 1) - (b.lab || b.from_lab ? 0 : 1)) || ((a.place || 99) - (b.place || 99)));   // (the switchable ones first)
    const added = G().fighters.filter(f => wantSel(f.name) && !f.selectable);
    const n = changed().length + (layoutChanged() ? 1 : 0);
    root.replaceChildren(
      h('h2', {}, 'Roster & select', h('span', { class: 'sp' }), h('span', { class: 'gcount', text: n ? n + ' unshipped' : 'all in game' }), ' · ', h('span', { class: 'gv', text: nSel() + ' of ' + G().max + ' places' })),
      h('div', { class: 'rrows' }, fs.map(row)),
      ...added.map(f => h('p', { class: 'rnote', text: `${f.display}: stage 1 plays ${f.music_ok ? 'his theme ' + f.music : 'the stage song (his theme is not in the sound ROM; no song is dropped automatically to make room)'}. His room (C ROM, P bank) is checked by the ship's build (bank_proof ALL OK), else the ship fails and nothing changes.` })),
      h('p', { class: 'rnote', text: roomLine(G().room) }),
      h('div', { class: 'btns' }, h('button', { type: 'button', 'aria-expanded': open ? 'true' : 'false', text: open ? 'Close the select layout' : 'Select layout…', onclick: () => { open = !open; if (open) openEditor(); else { host && (host.alive = false); edCol.replaceChildren(); } draw(); } }),
        layoutChanged() && !openShip() ? h('button', { type: 'button', text: 'Layout back to the game\'s', onclick: () => save(selBody({}, null), 'Layout back to the game\'s').then(() => open && openEditor(), () => {}) }) : null),
      msg, ...(open ? [edCol] : []));
  }

  function load(src) { return new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = no; document.body.append(s); }); }
  async function openEditor() {                        // a fresh editor instance on the draft (selectscreen.js runs once per load)
    if (host) host.alive = false;
    edCol.replaceChildren(h('p', { class: 'msg', text: 'Loading the select screen…' }));
    const me = host = { alive: true, col: null, data: '/brawler-factory/select.json',
      active: () => me.alive && open,
      prepare(Dx) {                                    // placeholders for the fighters not in this build yet (a grey block)
        const L = wantLayout();
        for (const n of Object.keys(L)) if (!Dx.fighters[n]) {
          const f = G().fighters.find(x => x.name === n), w = 40, hh = 96;
          const pals = new Array(16).fill(0); pals[1] = 0x4444;
          Dx.fighters[n] = { name: f.display, locked: f.locked, wide: [], poses: [{ w, h: hh, ox: w >> 1, oy: hh - 1, px: new Uint8Array(w * hh).fill(1), cols: [], ncols: 3,
            pose: L[n].pose, head: [0, -84], pals, rom: false, alias: [L[n].pose] }] };
        }
        return L;
      },
      save: L => save(selBody({}, L), 'Select layout') };
    me.col = h('div');
    edCol.replaceChildren(h('p', { class: 'note', text: 'The game\'s select screen (the street, the stick, the start order; bosses locked or beaten). A fighter not in the game yet: a grey block at the free place. "Save to the draft", then Ship pending changes.' }), me.col);
    try {
      if (!window.SelectRender) await load('selectrender.js');
      window.SelectHost = me; await load('selectscreen.js?' + Date.now());
    } catch (e) { me.col.replaceChildren(h('p', { class: 'msg bad', text: 'The select screen editor could not be loaded.' })); }
  }

  window.FactoryRoster = {
    poll(d, r, shown) { rows = r || []; if (!d) return; const gv = D.game && D.game.version; D = d; if (shown && (!open || (D.game && D.game.version !== gv))) draw(); },
    card(cast) { faces = {}; for (const c of (cast && cast.fighters) || []) if (c.face) faces[c.name] = c.face; draw(); return root; },
    pending: () => !!G() && !openShip() && (changed().length > 0 || layoutChanged()),
  };
})();
