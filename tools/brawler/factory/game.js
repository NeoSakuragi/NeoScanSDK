// The Brawler Factory's GAME tab (?tab=game; Bruno 2026-10-12: "the main game meta"): the game-wide numbers and texts of
// game.json that recompile safely with no tokens (tools/brawler/gamecfg.py: each knob's range, default, the game's value).
// Edits are saved as the "game" draft section (feedback-api/lab/game: {values: {knob id: value}}, only what differs from
// the game), shipped by Ship pending changes (the Build tab; the ship service: gamecfg.py merge -> game.json, then the
// usual build / checks / publish / push). Numbers use the Assembly's knob rows (knobui.js, compact): "def N", "changed
// from N", reset. A row whose value is not in the game yet carries "unshipped" (or "queued" / "building").
// factory.js calls FactoryGame.load(lab/game) on each poll, .draw() on the tab, .pending(rows) for the Build tab.
(function () {
  'use strict';
  const LAB = 'feedback-api/lab/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v != null && v !== false) e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const P = document.getElementById('pGame');
  const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  let D = {}, rows = [], want = null, saveT = null, openText = null;   // D: {draft, game}; want: {id: value} (the page's)
  const msg = h('span', { class: 'msg', role: 'status', 'aria-live': 'polite' });
  document.head.append(h('style', { text: `
#pGame .knobs { border: var(--line); border-radius: 8px; background: var(--card); color: var(--fg); margin: 0; padding: 4px 8px; }
#pGame .knobs .khead b { display: none; }
#pGame .knobs .krow { border-bottom: var(--line); padding: 3px 0; }
#pGame .knobs .krow:last-child { border-bottom: 0; }
#pGame .knobs .krow.over { border: 0; border-bottom: var(--line); background: var(--accent-bg); }
#pGame .knobs .kctl button, #pGame .knobs .kback, #pGame .knobs .kreset, #pGame .knobs input[type=number] { border: var(--line); border-radius: 6px; background: var(--card); color: var(--fg); }
#pGame .knobs .kdef, #pGame .knobs .kunit { color: var(--muted); }
#pGame .gcho { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; padding: 4px 0; border-bottom: var(--line); }
#pGame .gcho .kname { flex: 1 1 8em; font-size: 13px; }
#pGame .gcho button[aria-pressed=true] { background: var(--accent); border-color: var(--accent); color: #fff; }
#pGame .gt { display: flex; gap: 6px; align-items: center; width: 100%; text-align: left; padding: 6px 8px; margin: 2px 0; }
#pGame .gt b { flex: 1 1 auto; font-weight: 600; }
#pGame .gt span.x { color: var(--muted); font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 0 1 50%; }
#pGame textarea, #pGame input[type=text] { width: 100%; font: inherit; font-size: 14px; border: var(--line); border-radius: 6px; padding: 6px; }
#pGame .gsec { margin-top: 10px; }
#pGame .gsec h2 { margin: 0 0 4px; }
#pGame .tag.ship { background: var(--run-bg); color: var(--run); }` }));

  const knobs = () => (D.game && D.game.knobs) || [];
  const gameVal = id => (knobs().find(k => k.id === id) || {}).value;
  const openShip = () => rows.find(r => r.game && (r.status === 'pending' || r.status === 'building'));
  function initWant() {                                 // the draft's values over the game's
    want = {}; const dv = (D.draft && D.draft.values) || {};
    for (const k of knobs()) want[k.id] = k.id in dv ? dv[k.id] : k.value;
  }
  const diff = () => knobs().filter(k => !eq(want[k.id], k.value));
  const draftDiff = () => { const dv = (D.draft && D.draft.values) || {}; return knobs().filter(k => k.id in dv && !eq(dv[k.id], k.value)); };

  function save(what) {                                 // (debounced: a run of +/- taps is one revision)
    clearTimeout(saveT); msg.className = 'msg'; msg.textContent = 'Saving…';
    saveT = setTimeout(async () => {
      const values = {}; for (const k of diff()) values[k.id] = want[k.id];
      try {
        const r = await fetch(LAB + 'game', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ values }) });
        const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
        D = j; msg.textContent = (what || 'Saved') + '. Ship it from the Build tab (Ship pending changes).';
      } catch (e) { msg.className = 'msg bad'; msg.textContent = 'Not saved: ' + e.message; }
      tags();
    }, 700);
  }
  function tagFor(id) {
    const k = knobs().find(x => x.id === id); if (!k || eq(want[id], k.value)) return null;
    const o = openShip(); return h('span', { class: 'tag ' + (o ? 'ship' : 'edit'), text: o ? (o.status === 'building' ? 'building' : 'queued') : 'unshipped', title: 'in the game: ' + JSON.stringify(k.value) });
  }
  function tags() {                                     // the "unshipped" marks, without redrawing the rows under his fingers
    P.querySelectorAll('[data-knob]').forEach(r => { r.querySelectorAll('.gtag').forEach(x => x.remove()); const t = tagFor(r.dataset.knob); if (t) { t.classList.add('gtag'); r.append(t); } });
    const n = diff().length, el = P.querySelector('.gcount'); if (el) el.textContent = n ? n + ' unshipped' : 'all in game';
  }

  function numPanel(ks, label) {
    const defs = ks.map(k => ({ id: k.id, name: k.name, unit: k.unit, default: k.default, min: k.min, max: k.max, step: k.step }));
    const vals = {}; for (const k of ks) if (want[k.id] !== k.default) vals[k.id] = want[k.id];
    return KnobUI.panel({ defs, values: vals, label, compact: true,
      onChange: v => { for (const k of ks) want[k.id] = k.id in v ? v[k.id] : k.default; save(); tags(); } });
  }
  function choiceRow(k) {
    const row = h('div', { class: 'gcho', 'data-knob': k.id }, h('span', { class: 'kname', text: k.name }),
      k.options.map(o => h('button', { type: 'button', 'aria-pressed': want[k.id] === o ? 'true' : 'false', text: o,
        onclick: () => { want[k.id] = o; row.querySelectorAll('button[aria-pressed]').forEach(b => b.setAttribute('aria-pressed', b.textContent === want[k.id] ? 'true' : 'false')); save(); tags(); } })),
      h('span', { class: 'kdef', text: 'def ' + k.default }));
    return row;
  }
  function textRow(k) {
    const isOpen = openText === k.id, v = want[k.id];
    const btn = h('button', { type: 'button', class: 'gt', 'aria-expanded': isOpen ? 'true' : 'false', onclick: () => { openText = isOpen ? null : k.id; draw(); } },
      h('b', { text: k.name }), h('span', { class: 'x', text: Array.isArray(v) ? v[0] : v }));
    const wrapEl = h('div', { 'data-knob': k.id }, btn);
    if (!isOpen) return wrapEl;
    const story = k.kind === 'story';
    const ta = story ? h('textarea', { rows: '6', 'aria-label': k.name + ': one sentence a line' }) : h('input', { type: 'text', maxlength: String(k.max), 'aria-label': k.name });
    ta.value = story ? v.join('\n') : v;
    const em = h('span', { class: 'msg' });
    const val = () => story ? ta.value.split('\n').map(s => s.trim()).filter(Boolean) : ta.value;
    const ok = () => { const x = val(); return story ? x.length >= 4 && x.length <= 5 && x.every(s => /^[\x20-\x7e]{1,160}$/.test(s)) : /^[\x20-\x7e]*$/.test(x) && x.replace(/^\^+/, '').length <= k.max; };
    ta.oninput = () => { em.className = ok() ? 'msg' : 'msg bad'; em.textContent = ok() ? '' : story ? '4 or 5 sentences, one a line, plain ASCII, at most 160 characters each' : 'at most ' + k.max + ' plain ASCII characters'; };
    wrapEl.append(ta, em, h('div', { class: 'btns' },
      h('button', { type: 'button', class: 'primary', text: 'Save', onclick: () => { if (!ok()) return ta.oninput(); want[k.id] = val(); openText = null; save(k.name + ': saved'); draw(); } }),
      !eq(v, k.value) ? h('button', { type: 'button', text: 'Back to the game\'s', onclick: () => { want[k.id] = k.value; openText = null; save(k.name + ': back to the game\'s'); draw(); } }) : null,
      h('button', { type: 'button', text: 'Close', onclick: () => { openText = null; draw(); } })));
    return wrapEl;
  }

  function draw() {
    const G = D.game;
    if (!G || !G.knobs) { P.replaceChildren(h('p', { class: 'note', text: 'The game\'s numbers are not known yet: the build daemon reports them when it starts and after each ship.' })); return; }
    if (!want) initWant();
    const groups = G.groups || [...new Set(G.knobs.map(k => k.group))];
    P.replaceChildren(h('div', { class: 'card' },
      h('h2', {}, 'Game', h('span', { class: 'sp' }), h('span', { class: 'gcount' }), ' · ', h('span', { class: 'gv', text: 'in game ' + (G.version || '?') })),
      msg,
      groups.map(g => {
        const ks = G.knobs.filter(k => k.group === g);
        const num = ks.filter(k => k.kind === 'num'), cho = ks.filter(k => k.kind === 'choice'), txt = ks.filter(k => k.kind === 'story' || k.kind === 'line');
        return h('section', { class: 'gsec', 'aria-label': g }, h('h2', { text: g }),
          num.length ? numPanel(num, g) : null, cho.map(choiceRow), txt.map(textRow));
      }),
      h('p', { class: 'msg', text: 'Not here (they need new code or data): chain lengths / damage totals / hit-stops, the jump arc, AI presets, continues / credits, the title text, gravity.' })));
    tags();
  }

  window.FactoryGame = {
    poll(d, r, shown) {                                // each poll: the server's {draft, game}, the ship queue; the page's
      rows = r || []; if (!d) return;                  // edits kept; redrawn only when the game changed (a ship landed)
      const gv = D.game && D.game.version; D = d;
      if (D.game && D.game.version !== gv && !openText) { want = null; if (shown) draw(); } else if (shown) tags();
    },
    draw,
    pending: () => !!D.game && !openShip() && draftDiff().length > 0,
  };
})();
