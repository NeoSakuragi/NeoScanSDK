// The Brawler Factory's PLAYERS tab (?tab=players): the Oros accounts with a brawler role (tag brawler_tester or
// brawler_admin; tools/feedback/server.py "THE BRAWLER APP"), one row each: the build the Brawler app gives it (a
// published VERSION; an admin's "Newest" = no cap), the build its app last said it plays, when it was last seen;
// Save = the "players" draft section (feedback-api/lab/players {assign: {account: VERSION}}), live at once: no ship,
// no agent. The app downloads the newest build up to the assigned one at its next start / poll.
(function () {
  'use strict';
  const LAB = 'feedback-api/lab/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v != null && v !== false) e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const P = document.getElementById('pPlayers');
  const ago = iso => { const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000)); return s < 90 ? s + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : s < 172800 ? Math.round(s / 3600) + ' h' : Math.round(s / 86400) + ' d'; };
  document.head.append(h('style', { text: `
#pPlayers .prow { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 2px 8px; align-items: center; padding: 6px 0; border-bottom: var(--line); }
#pPlayers .prow:last-child { border-bottom: 0; }
#pPlayers .prow b { font-size: 15px; }
#pPlayers .prow .st { grid-column: 1 / -1; font-size: 12px; color: var(--muted); }
#pPlayers select { font: inherit; font-size: 14px; border: var(--line); border-radius: 6px; padding: 3px 4px; background: var(--card); color: var(--fg); }` }));
  let D = null;
  const msg = h('p', { class: 'msg', role: 'status', 'aria-live': 'polite' });

  async function load() {
    try { const r = await fetch(LAB + 'players', { cache: 'no-store', credentials: 'same-origin' }); if (!r.ok) throw new Error('HTTP ' + r.status); D = await r.json(); }
    catch (e) { P.replaceChildren(h('p', { class: 'msg bad', text: 'Players unavailable: ' + e.message })); return; }
    draw();
  }
  async function save(name, v, btn) {
    const assign = Object.assign({}, (D.draft && D.draft.assign) || {}); assign[name] = v;
    btn.disabled = true; msg.className = 'msg'; msg.textContent = 'Saving…';
    try {
      const r = await fetch(LAB + 'players', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assign }) });
      const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      D = j; draw(); msg.textContent = name + ': ' + (v ? 'gets ' + v + ' at the next start of his app.' : 'no build assigned.');
    } catch (e) { btn.disabled = false; msg.className = 'msg bad'; msg.textContent = 'Not saved: ' + e.message; }
  }
  function draw() {
    if (!D) { P.replaceChildren(h('p', { class: 'msg', text: 'Loading…' })); return load(); }
    const assign = (D.draft && D.draft.assign) || {};
    const rows = (D.accounts || []).map(a => {
      const cur = assign[a.name] || '';
      const sel = h('select', { 'aria-label': 'Build for ' + a.name },
        h('option', { value: '', text: a.role === 'admin' ? 'Newest' : 'No build' }),
        (D.builds || []).map(v => h('option', { value: v, text: v, selected: v === cur ? '' : null })));
      const btn = h('button', { type: 'button', class: 'primary', text: 'Save', disabled: '' });
      sel.onchange = () => { btn.disabled = sel.value === cur; };
      btn.onclick = () => save(a.name, sel.value, btn);
      const s = a.seen;
      const st = (a.gets ? 'gets ' + a.gets : 'no build') + ' · ' + (s ? 'seen ' + ago(s.at) + ' ago' + (s.rom && s.rom !== 'none' ? ', playing ' + s.rom : '') : 'never signed in');
      return h('div', { class: 'prow' }, h('b', { text: a.name + (a.role === 'admin' ? ' (admin)' : '') }), sel, btn, h('span', { class: 'st', text: st }));
    });
    P.replaceChildren(h('div', { class: 'card' }, h('h2', { text: 'Players' }),
      rows.length ? rows : h('p', { class: 'msg', text: 'No Oros account has a brawler role yet (oros-server user-tags).' })), msg);
  }
  window.FactoryPlayers = { draw: () => { D = null; draw(); } };
})();
