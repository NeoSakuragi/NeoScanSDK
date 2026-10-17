/* The feedback notes recorded during a play session (Bruno 2026-10-17): a small count badge on every session row (the
 * Live wall's tiles, the Sessions list, the admin hub's Stats rows); a tap opens the overview, one line per note (its
 * time in the session, its title, its status); a tap on a note opens it in the tracker (game.html#fb=<id>: text,
 * transcript, audio, screenshot, replay / test state, timeline). Notes are matched to the session by the server
 * (tools/feedback/server.py session_notes: same install id, sent between the session's first and last chunk), read
 * from feedback-api/session/<id>/notes; brawler admins only, like every feedback-api call.
 *   SessNotes.badge(sessionId, count, api)  -> a <button> (empty and hidden when count is 0); SessNotes.set(badge, n) */
(function () {
  'use strict';
  if (window.SessNotes) return;
  const css = document.createElement('style');
  css.textContent = `
.snbadge { display: inline-block; min-width: 22px; height: 22px; padding: 0 6px; margin-left: 4px; border: 2px solid #000;
  border-radius: 11px; background: #000; color: #fff; font: 700 12px/18px system-ui, sans-serif; text-align: center; cursor: pointer; vertical-align: middle; }
.snbadge[hidden] { display: none; }
.snover { position: fixed; inset: 0; z-index: 9999; background: rgba(0,0,0,.35); display: flex; align-items: flex-start; justify-content: center; padding: 16px; }
.snover .snbox { background: #fff; color: #000; border: 3px solid #000; width: 100%; max-width: 560px; max-height: calc(100vh - 32px); overflow: auto; font: 15px/1.35 system-ui, sans-serif; }
.snover .snhd { display: flex; gap: 8px; align-items: center; padding: 8px 10px; border-bottom: 2px solid #000; position: sticky; top: 0; background: #fff; }
.snover .snhd b { flex: 1; }
.snover .snhd button { font: inherit; min-height: 36px; padding: 0 12px; border: 2px solid #000; background: #fff; color: #000; }
.snover a.snrow { display: grid; grid-template-columns: 52px 1fr auto; gap: 8px; padding: 9px 10px; border-bottom: 1px solid #000; color: #000; text-decoration: none; }
.snover a.snrow:active { background: #000; color: #fff; }
.snover .snt { font-variant-numeric: tabular-nums; }
.snover .sns { border: 1px solid #000; padding: 0 5px; font-size: 12px; align-self: start; }
.snover p { margin: 10px; }`;
  document.head.append(css);
  const mmss = s => { s = Math.max(0, Math.round(s)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  const esc = s => String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
  const TRACKER = '/brawler-lab/game.html#fb=';

  async function open(sid, api) {
    const ov = document.createElement('div'); ov.className = 'snover';
    ov.innerHTML = `<div class="snbox"><div class="snhd"><b>Notes in this session</b><button>Close</button></div><p>Loading…</p></div>`;
    const box = ov.firstChild; box.querySelector('button').onclick = () => ov.remove();
    ov.onclick = e => { if (e.target === ov) ov.remove(); };
    document.body.append(ov);
    let j;
    try { const r = await fetch(api + 'session/' + sid + '/notes', { credentials: 'same-origin', cache: 'no-store' }); if (!r.ok) throw new Error('HTTP ' + r.status); j = await r.json(); }
    catch (e) { box.lastChild.textContent = 'Notes unavailable: ' + e.message; return; }
    box.lastChild.remove();
    box.querySelector('b').textContent = `${j.notes.length} note${j.notes.length === 1 ? '' : 's'} · ${sid}`;
    if (!j.notes.length) box.insertAdjacentHTML('beforeend', '<p>No note was recorded during this session.</p>');
    for (const n of j.notes) {
      const a = document.createElement('a'); a.className = 'snrow'; a.href = TRACKER + encodeURIComponent(n.id);
      a.innerHTML = `<span class="snt">${mmss(n.t)}</span><span>${esc(n.title) || '<i>(no title yet)</i>'}</span><span class="sns">${esc(n.status)}</span>`;
      a.onclick = e => {                                // the tracker reads #fb= when it loads: reload when already on it
        if (location.pathname.endsWith('/brawler-lab/game.html')) { e.preventDefault(); location.hash = 'fb=' + n.id; location.reload(); }
      };
      box.append(a);
    }
  }
  function set(b, n) { b.textContent = n > 0 ? String(n) : ''; b.hidden = !(n > 0); b.title = n + ' feedback note' + (n === 1 ? '' : 's') + ' in this session'; }
  function badge(sid, n, api) {
    const b = document.createElement('button'); b.type = 'button'; b.className = 'snbadge';
    b.onclick = e => { e.stopPropagation(); e.preventDefault(); open(sid, api || 'feedback-api/'); };
    set(b, n); return b;
  }
  window.SessNotes = { badge, set, open };
})();
