// The Brawler Factory's PLAYERS tab (?tab=players): the player admin console of the closed beta (Bruno 2026-10-16;
// docs/feedback.md "Sign-up and the player admin"). Canneji only, behind the brawler admin gate; never on brawler27.
// Three sources, merged here (each side keeps its own data, one source of truth each):
//   /oros/api/brawler/players            the accounts (Oros: tags, joined via which code, sign-up IP / device), the
//                                         invite codes (+ who joined with each), the blocked addresses, the Oros audit
//   feedback-api/players                 the play data (sessions, play time, devices, app versions, IPs, notes, cloud
//                                         saves, language) + who is LIVE now + the feedback side's audit
//   feedback-api/lab/players             the build each account gets (the testers' "*" assignment, the admins' own)
// Actions: /oros/api/brawler/account {username, action} (block [+ its IPs], unblock, grant, make_admin / remove_admin,
// nightly_on / nightly_off, reset_password -> the temporary password shown ONCE, sign_out, delete), /oros/api/brawler/codes,
// /oros/api/brawler/ipblock, feedback-api/players/reset_save; the build: feedback-api/lab/players {assign}. Every action
// lands in an audit log (both sides', merged below). Destructive ones confirm (delete: twice).
// One row per item, details on tap; text labels on every state (never colour alone).
(function () {
  'use strict';
  const LAB = 'feedback-api/lab/', FB = 'feedback-api/', OROS = '/oros/api/brawler/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v != null && v !== false) e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const P = document.getElementById('pPlayers');
  const agoS = s => { s = Math.max(0, Math.round(s)); return s < 90 ? s + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : s < 172800 ? Math.round(s / 3600) + ' h' : Math.round(s / 86400) + ' d'; };
  const ago = ms => agoS((Date.now() - ms) / 1000) + ' ago';
  const day = sec => sec ? new Date(sec * 1000).toLocaleDateString([], { month: 'short', day: 'numeric', year: '2-digit' }) : '?';
  const when = sec => sec ? new Date(sec * 1000).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '?';
  const hms = s => { s = Math.round(s || 0); return s >= 3600 ? Math.floor(s / 3600) + ' h ' + String(Math.floor(s % 3600 / 60)).padStart(2, '0') : Math.floor(s / 60) + ' min'; };
  const kb = n => n >= 1e6 ? (n / 1e6).toFixed(1) + ' MB' : Math.round(n / 1024) + ' KB';
  const getJ = async u => { const r = await fetch(u, { cache: 'no-store', credentials: 'same-origin' }); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.message || j.error || 'HTTP ' + r.status); return j; };
  const postJ = async (u, body) => { const r = await fetch(u, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.message || j.error || 'HTTP ' + r.status); return j; };
  document.head.append(h('style', { text: `
#pPlayers .card { margin-bottom: 10px; }
#pPlayers h2 { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
#pPlayers h2 small { font-weight: 400; font-size: 13px; color: var(--muted); }
#pPlayers .prow { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: 2px 8px; align-items: center; padding: 6px 0; border-bottom: var(--line); }
#pPlayers .prow:last-child { border-bottom: 0; }
#pPlayers .prow b { font-size: 15px; }
#pPlayers .prow .st { grid-column: 1 / -1; font-size: 12px; color: var(--muted); }
#pPlayers select, #pPlayers input[type=text], #pPlayers input[type=number] { font: inherit; font-size: 14px; border: var(--line); border-radius: 6px; padding: 3px 6px; background: var(--card); color: var(--fg); min-width: 0; }
#pPlayers .acc { border-bottom: var(--line); }
#pPlayers .acc:last-child { border-bottom: 0; }
#pPlayers .acc > summary { list-style: none; cursor: pointer; padding: 6px 0; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 1px 8px; }
#pPlayers .acc > summary::-webkit-details-marker { display: none; }
#pPlayers .acc > summary b { font-size: 15px; }
#pPlayers .acc > summary .r { font-size: 12px; color: var(--muted); text-align: right; white-space: nowrap; }
#pPlayers .acc > summary .l2 { grid-column: 1 / -1; font-size: 12px; color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#pPlayers .acc[open] > summary { border-bottom: 1px dashed var(--rule); }
#pPlayers .det { padding: 6px 0 10px; font-size: 13px; }
#pPlayers .det dl { display: grid; grid-template-columns: max-content minmax(0, 1fr); gap: 2px 10px; margin: 0 0 8px; }
#pPlayers .det dt { color: var(--muted); }
#pPlayers .det dd { margin: 0; overflow-wrap: anywhere; }
#pPlayers .acts { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 4px; }
#pPlayers .acts button.danger { border-color: var(--bad); color: var(--bad); }
#pPlayers .sub { margin: 6px 0; }
#pPlayers .sub > div { padding: 3px 0; border-top: 1px dotted var(--rule); display: flex; gap: 8px; align-items: baseline; }
#pPlayers .sub > div > span:first-child { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
#pPlayers .shared { font-weight: 700; color: var(--bad); }
#pPlayers .temp { border: 2px solid var(--fg); padding: 8px; margin: 6px 0; font-size: 14px; }
#pPlayers .temp code { font-size: 20px; letter-spacing: .08em; user-select: all; }
#pPlayers .live { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 8px; align-items: center; padding: 6px 0; border-bottom: var(--line); }
#pPlayers .live:last-child { border-bottom: 0; }
#pPlayers .form { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 8px; }
#pPlayers .form input[type=text] { width: 9em; } #pPlayers .form input[type=number] { width: 5em; }
#pPlayers .audit div { font-size: 12px; padding: 2px 0; border-top: 1px dotted var(--rule); }
#pPlayers .audit div b { font-weight: 600; }
#pPlayers a.spect { font-weight: 700; border: 2px solid var(--accent); border-radius: 6px; padding: 3px 10px; text-decoration: none; }` }));

  let O = null, F = null, B = null, err = '';
  const openSet = new Set();                         // the accounts whose details are open (kept across redraws)
  const temp = {};                                   // username -> the temporary password, shown once
  const msg = h('p', { class: 'msg', role: 'status', 'aria-live': 'polite' });
  const say = (t, bad) => { msg.className = 'msg' + (bad ? ' bad' : ''); msg.textContent = t; };

  async function load() {
    const [o, f, b] = await Promise.allSettled([getJ(OROS + 'players'), getJ(FB + 'players'), getJ(LAB + 'players')]);
    err = [o, f, b].filter(x => x.status === 'rejected').map(x => x.reason.message).join(' · ');
    if (o.status === 'fulfilled') O = o.value; if (f.status === 'fulfilled') F = f.value; if (b.status === 'fulfilled') B = b.value;
    draw();
  }
  async function act(fn, done) {
    say('Working…');
    try { const j = await fn(); if (done) done(j); await load(); }
    catch (e) { say('Failed: ' + e.message, true); }
  }
  const account = (u, action, extra) => act(async () => {
    const j = await postJ(OROS + 'account', Object.assign({ username: u, action }, extra || {}));
    if (j.temp_password) temp[u] = j.temp_password;
    O = j; return j;
  }, () => say(u + ': ' + ACT_DONE[action] + '.'));
  const ACT_DONE = { block: 'blocked', unblock: 'unblocked', grant: 'access granted', make_admin: 'now an admin', remove_admin: 'admin role removed',
    nightly_on: 'nightly on: the newest published build at its next check', nightly_off: 'nightly off: the testers\' build again',
    reset_password: 'temporary password made (shown below once)', sign_out: 'signed out everywhere', delete: 'account deleted' };

  // ---- the merged view ----
  function ipOwners() {                              // ip -> Set(users): sign-up IPs + every IP seen in the play data
    const m = new Map(); const add = (ip, u) => { if (!ip) return; if (!m.has(ip)) m.set(ip, new Set()); m.get(ip).add(u); };
    for (const a of (O && O.accounts) || []) if (a.signup) add(a.signup.ip, a.username);
    for (const [u, p] of Object.entries((F && F.players) || {})) for (const ip of p.ips || []) add(ip, u);
    return m;
  }
  function ipsOf(a, p) { const s = new Set(); if (a.signup && a.signup.ip) s.add(a.signup.ip); for (const ip of (p && p.ips) || []) s.add(ip); return [...s]; }
  function tags(a, p, nightly) {
    const t = [];
    if (F && F.players[a.username] && F.players[a.username].live) t.push(h('span', { class: 'tag ok', text: '● LIVE' }));
    t.push(h('span', { class: 'tag' + (a.brawler === 'blocked' ? ' bad' : a.brawler === 'admin' ? ' ship' : ''), text: a.brawler === 'none' ? 'no access' : a.brawler }));
    if (nightly) t.push(h('span', { class: 'tag edit', text: 'nightly' }));
    if (a.must_change) t.push(h('span', { class: 'tag edit', text: 'temp password' }));
    if (a.role !== 'brawler') t.push(h('span', { class: 'tag', text: 'Oros account' }));
    return t;
  }

  function liveCard() {
    const L = (F && F.live) || [];
    return h('div', { class: 'card', id: 'plLive' }, h('h2', { text: 'Online now' }, h('small', { text: L.length ? L.length + ' playing (a chunk in the last ' + ((F && F.live_s) || 15) + ' s)' : 'nobody is playing' })),
      L.map(s => h('div', { class: 'live' },
        h('span', {}, h('b', { text: s.user }), ' · ' + (s.rom_version || '?') + ' · ' + hms(s.seconds) + ' · ' + (s.device || '')),
        h('a', { class: 'spect', href: '/brawler-lab/game.html#sess=' + s.id, target: '_blank', rel: 'noopener', text: 'SPECTATE' }))));
  }

  function accountRow(a, owners, bacc) {
    const p = (F && F.players[a.username]) || null;
    const nightly = a.tags.includes('brawler_nightly');
    const ips = ipsOf(a, p);
    const shared = ips.filter(ip => (owners.get(ip) || new Set()).size > 1);
    const seen = Math.max((a.last_seen || 0) * 1000, p && p.last ? p.last * 1000 : 0, p && p.seen ? Date.parse(p.seen.at) || 0 : 0);
    const sum = h('summary', {},
      h('span', {}, h('b', { text: a.username }), ' ', tags(a, p, nightly)),
      h('span', { class: 'r', text: seen ? 'seen ' + ago(seen) : 'never seen' }),
      h('span', { class: 'l2', text: [p ? hms(p.seconds) + ' played' : '0 min played', (p ? p.sessions : 0) + ' sessions', (p ? p.notes : 0) + ' notes',
        shared.length ? '⚑ shared IP' : '', a.signup ? 'via ' + a.signup.code : ''].filter(Boolean).join(' · ') }));
    const det = h('details', { class: 'acc', 'data-u': a.username, open: openSet.has(a.username) ? '' : null }, sum);
    det.ontoggle = () => { if (det.open) { openSet.add(a.username); fillDetails(det, a, p, ips, owners, bacc, nightly); } else openSet.delete(a.username); };
    if (det.open) fillDetails(det, a, p, ips, owners, bacc, nightly);
    return det;
  }

  function fillDetails(det, a, p, ips, owners, bacc, nightly) {
    det.querySelector('.det') && det.querySelector('.det').remove();
    const u = a.username, s = a.signup;
    const saves = (p && p.saves) || [];
    const ipList = ips.length ? ips.map(ip => { const o = [...(owners.get(ip) || [])].filter(x => x !== u); return h('div', {}, ip, o.length ? h('span', { class: 'shared', text: ' ⚑ also ' + o.join(', ') }) : ''); }) : '—';
    const dl = h('dl', {},
      h('dt', { text: 'Joined' }), h('dd', { text: s ? 'code ' + s.code + ', ' + when(s.at) : 'Oros account, created ' + day(a.created) }),
      h('dt', { text: 'Sign-up' }), h('dd', { text: s ? (s.device || '?') + ' · ' + s.ip + ' · ' + (s.user_agent || '') : '—' }),
      h('dt', { text: 'Language' }), h('dd', { text: p && p.language ? ({ en: 'English', fr: 'Français' }[p.language] || p.language) : 'not set yet' }),
      h('dt', { text: 'Devices' }), h('dd', { text: (p && p.devices.length) ? p.devices.join(', ') : '—' }),
      h('dt', { text: 'App versions' }), h('dd', { text: (p && p.apps.length) ? p.apps.join(', ') : '—' }),
      h('dt', { text: 'IPs' }), h('dd', {}, ipList),
      h('dt', { text: 'Play' }), h('dd', { text: p ? hms(p.seconds) + ' in ' + p.sessions + ' sessions' + (p.first ? ', first ' + when(p.first) : '') : 'none' }),
      h('dt', { text: 'Build' }), h('dd', { text: (bacc && bacc.gets ? 'gets ' + bacc.gets : 'no build') + (nightly ? ' (nightly: the newest published)' : '') + (p && p.seen && p.seen.rom ? ' · plays ' + p.seen.rom : '') }),
      h('dt', { text: 'Cloud save' }), h('dd', { text: saves.length ? saves.map(x => x.game + ' ' + kb(x.size) + ' (rev ' + x.rev + ')').join(', ') : 'none' }),
      h('dt', { text: 'Last sign-in' }), h('dd', { text: a.last_login ? when(a.last_login) : '—' }));
    const sess = h('div', { class: 'sub' }, h('b', { text: 'Sessions' }), ' ', h('a', { href: '/brawler-lab/game.html?user=' + encodeURIComponent(u) + '#sessions', target: '_blank', rel: 'noopener', text: 'all in the Lab' }), h('div', {}, h('span', { text: 'loading…' })));
    const notes = h('div', { class: 'sub' }, h('b', { text: 'Notes' }), h('div', {}, h('span', { text: 'loading…' })));
    const B2 = (label, fn, cls) => h('button', { type: 'button', class: cls || null, text: label, onclick: fn });
    const yes = q => window.confirm(q);
    const acts = h('div', { class: 'acts' });
    const isAdmin = a.brawler === 'admin';
    if (a.brawler === 'blocked') acts.append(B2('Unblock', () => account(u, 'unblock')));
    else if (a.brawler === 'none') acts.append(B2('Grant access', () => account(u, 'grant')));
    else if (!isAdmin) {
      const also = h('input', { type: 'checkbox', id: 'bip-' + u });
      acts.append(B2('Block', () => { if (yes('Block ' + u + '? The tester tag goes, every device is signed out.' + (also.checked && ips.length ? '\nAlso block ' + ips.join(', ') + '.' : ''))) account(u, 'block', { block_ips: also.checked ? ips : [] }); }, 'danger'),
        h('label', { for: 'bip-' + u, style: 'font-size:12px' }, also, ' also block IP' + (ips.length > 1 ? 's' : '')));
    }
    if (a.brawler !== 'blocked') acts.append(B2(nightly ? 'Nightly off' : 'Nightly on', () => account(u, nightly ? 'nightly_off' : 'nightly_on')));
    acts.append(B2(isAdmin ? 'Remove admin' : 'Make admin', () => { if (yes(isAdmin ? 'Remove the brawler admin role of ' + u + '?' : 'Make ' + u + ' a brawler admin? Admins see the Lab, the Factory, every player and these controls.')) account(u, isAdmin ? 'remove_admin' : 'make_admin'); }));
    acts.append(B2('Reset password', () => { if (yes('Reset the password of ' + u + '? A temporary one is shown once; the app asks for a new one at the next sign-in.')) account(u, 'reset_password'); }));
    acts.append(B2('Sign out everywhere', () => { if (yes('Sign ' + u + ' out on every device?')) account(u, 'sign_out'); }));
    if (saves.length) acts.append(B2('Reset cloud save', () => { if (yes('Delete the cloud save of ' + u + '? (Kept on the server as a backup revision.)')) act(async () => { F = await postJ(FB + 'players/reset_save', { user: u }); }, () => say(u + ': cloud save reset.')); }, 'danger'));
    if (a.role === 'brawler' && !isAdmin) acts.append(B2('Delete account', () => {
      if (!yes('Delete the account ' + u + '? Its sessions and notes stay; the sign-up row stays in the audit.')) return;
      if (window.prompt('Type the login to confirm: ' + u) !== u) { say('Not deleted: the login typed did not match.', true); return; }
      openSet.delete(u); account(u, 'delete');
    }, 'danger'));
    const box = h('div', { class: 'det' }, temp[u] ? h('div', { class: 'temp' }, 'Temporary password for ', h('b', { text: u }), ' (shown once, send it to the player): ', h('br'), h('code', { text: temp[u] }), ' ', B2('Copy', () => navigator.clipboard && navigator.clipboard.writeText(temp[u])), ' ', B2('Hide', () => { delete temp[u]; draw(); })) : '',
      dl, acts, sess, notes);
    det.append(box);
    getJ(FB + 'sessions?user=' + encodeURIComponent(u) + '&limit=12').then(j => {
      const rs = j.sessions || [];
      sess.replaceChildren(h('b', { text: 'Sessions' }), ' ', h('a', { href: '/brawler-lab/game.html?user=' + encodeURIComponent(u) + '#sessions', target: '_blank', rel: 'noopener', text: 'all ' + ((p && p.sessions) || rs.length) + ' in the Lab' }),
        ...(rs.length ? rs.map(r => h('div', {}, h('span', { text: (r.live ? '● LIVE · ' : '') + new Date(r.started).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) + ' · ' + hms(r.seconds) + ' · ' + (r.rom_version || '') + ' · ' + (r.device || '') }),
          h('a', { href: '/brawler-lab/game.html#sess=' + r.id, target: '_blank', rel: 'noopener', text: r.live ? 'Spectate' : 'Watch' }))) : [h('div', {}, h('span', { text: 'none' }))]));
    }, e => sess.replaceChildren(h('b', { text: 'Sessions' }), h('div', {}, h('span', { text: 'unavailable: ' + e.message }))));
    getJ(FB + 'list?user=' + encodeURIComponent(u)).then(j => {
      const rs = j.rows || [];
      notes.replaceChildren(h('b', { text: 'Notes' }), ...(rs.length ? rs.slice(0, 15).map(r => h('div', {}, h('span', { text: (r.title || r.final_text || r.raw_transcript || '(no text)').slice(0, 90) }),
        h('a', { href: '/brawler-lab/game.html#fb=' + r.id, target: '_blank', rel: 'noopener', text: r.status }))) : [h('div', {}, h('span', { text: 'none' }))]),
        rs.length > 15 ? h('div', {}, h('span', { text: '+ ' + (rs.length - 15) + ' more in the Lab' })) : '');
    }, e => notes.replaceChildren(h('b', { text: 'Notes' }), h('div', {}, h('span', { text: 'unavailable: ' + e.message }))));
  }

  // ---- the build each gets (the former Players tab) ----
  async function saveBuild(name, v, btn) {
    const assign = Object.assign({}, (B.draft && B.draft.assign) || {}); assign[name] = v;
    btn.disabled = true; say('Saving…');
    try { B = await postJ(LAB + 'players', { assign }); draw(); say((name === '*' ? 'Every tester' : name) + ': ' + (v ? 'gets ' + v + ' at the next check of the app (every 30 s).' : 'no build assigned.')); }
    catch (e) { btn.disabled = false; say('Not saved: ' + e.message, true); }
  }
  function buildRow(key, label, cur, empty, st) {
    const sel = h('select', { 'aria-label': 'Build for ' + label }, h('option', { value: '', text: empty }),
      (B.builds || []).map(v => h('option', { value: v, text: v, selected: v === cur ? '' : null })));
    const btn = h('button', { type: 'button', class: 'primary', text: 'Save', disabled: '' });
    sel.onchange = () => { btn.disabled = sel.value === cur; };
    btn.onclick = () => saveBuild(key, sel.value, btn);
    return h('div', { class: 'prow' }, h('b', { text: label }), sel, btn, h('span', { class: 'st', text: st }));
  }
  function buildCard() {
    if (!B) return h('div', { class: 'card' }, h('h2', { text: 'Builds' }), h('p', { class: 'msg bad', text: 'unavailable' }));
    const assign = (B.draft && B.draft.assign) || {};
    const acc = B.accounts || [];
    const night = acc.filter(a => a.nightly).map(a => a.name);
    return h('div', { class: 'card' }, h('h2', { text: 'Builds' }, h('small', { text: night.length ? 'nightly (newest published): ' + night.join(', ') : '' })),
      buildRow('*', 'All testers', assign['*'] || '', 'No build', acc.filter(a => a.role !== 'admin' && !a.nightly).length + ' testers on it'),
      acc.filter(a => a.role === 'admin').map(a => buildRow(a.name, a.name + ' (admin)', assign[a.name] || '', 'Newest', (a.gets ? 'gets ' + a.gets : 'no build') + (a.nightly ? ' · nightly' : ''))));
  }

  // ---- invite codes, blocked addresses, grant, audit ----
  function codesCard() {
    const C = (O && O.codes) || [];
    const code = h('input', { type: 'text', placeholder: 'CODE', 'aria-label': 'New code', maxlength: 32, style: 'text-transform:uppercase' });
    const label = h('input', { type: 'text', placeholder: 'label (which group)', 'aria-label': 'Label' });
    const max = h('input', { type: 'number', min: 1, max: 100000, value: 50, 'aria-label': 'Max uses' });
    return h('div', { class: 'card' }, h('h2', { text: 'Invite codes' }),
      C.map(c => {
        const d = h('details', { class: 'acc' }, h('summary', {}, h('span', {}, h('b', { text: c.code }), ' ', h('span', { class: 'tag' + (c.active ? ' ok' : ' bad'), text: c.active ? 'on' : 'off' }), c.uses >= c.max_uses ? h('span', { class: 'tag edit', text: 'used up' }) : ''),
          h('span', { class: 'r', text: c.uses + ' / ' + c.max_uses + ' used' }), h('span', { class: 'l2', text: (c.label || '') + ' · made ' + day(c.created) })),
          h('div', { class: 'det' },
            h('div', { class: 'sub' }, h('b', { text: 'Joined with it' }), c.joined.length ? c.joined.map(j => h('div', {}, h('span', { text: j.username + (j.deleted ? ' (deleted)' : '') }), h('span', { text: when(j.at) }))) : h('div', {}, h('span', { text: 'nobody yet' }))),
            h('div', { class: 'acts' }, h('button', { type: 'button', text: c.active ? 'Switch off' : 'Switch on', onclick: () => act(async () => { O = await postJ(OROS + 'codes', { code: c.code, active: !c.active }); }, () => say(c.code + (c.active ? ' switched off.' : ' switched on.'))) }),
              h('button', { type: 'button', text: 'Change max uses', onclick: () => { const n = parseInt(window.prompt('Max uses for ' + c.code, c.max_uses), 10); if (n >= 0) act(async () => { O = await postJ(OROS + 'codes', { code: c.code, max_uses: n }); }, () => say(c.code + ': max ' + n + '.')); } }))));
        return d;
      }),
      h('div', { class: 'form' }, code, label, max, h('button', { type: 'button', class: 'primary', text: 'Add code', onclick: () => {
        const v = code.value.trim().toUpperCase();
        if (!/^[A-Z0-9_-]{3,32}$/.test(v)) { say('A code is 3 to 32 of A-Z, 0-9, _ and -.', true); return; }
        act(async () => { O = await postJ(OROS + 'codes', { code: v, label: label.value.trim(), max_uses: parseInt(max.value, 10) || 0 }); }, () => say(v + ' added.'));
      } })));
  }
  function blocksCard() {
    const L = (O && O.blocks) || [];
    const ip = h('input', { type: 'text', placeholder: 'address', 'aria-label': 'Address to block' });
    const why = h('input', { type: 'text', placeholder: 'reason', 'aria-label': 'Reason' });
    return h('div', { class: 'card' }, h('h2', { text: 'Blocked addresses' }, h('small', { text: L.length ? '' : 'none' })),
      L.map(b => h('div', { class: 'prow' }, h('b', { text: b.ip }), h('span', { class: 'st', style: 'grid-column:auto', text: day(b.at) }),
        h('button', { type: 'button', text: 'Unblock', onclick: () => act(async () => { O = await postJ(OROS + 'ipblock', { ip: b.ip, blocked: false }); }, () => say(b.ip + ' unblocked.')) }),
        h('span', { class: 'st', text: (b.reason || '') + (b.by ? ' · by ' + b.by : '') }))),
      h('div', { class: 'form' }, ip, why, h('button', { type: 'button', class: 'primary', text: 'Block address', onclick: () => {
        const v = ip.value.trim(); if (!v) return;
        if (window.confirm('Block ' + v + '? No sign-up from it, no sign-in of a self-registered account from it.')) act(async () => { O = await postJ(OROS + 'ipblock', { ip: v, blocked: true, reason: why.value.trim() }); }, () => say(v + ' blocked.'));
      } })));
  }
  function grantCard() {
    const others = (O && O.others) || [];
    if (!others.length) return '';
    const sel = h('select', { 'aria-label': 'Oros account' }, others.map(n => h('option', { value: n, text: n })));
    return h('div', { class: 'card' }, h('h2', { text: 'Grant access' }, h('small', { text: 'an existing Oros account becomes a tester' })),
      h('div', { class: 'form' }, sel, h('button', { type: 'button', class: 'primary', text: 'Grant', onclick: () => { if (window.confirm('Give ' + sel.value + ' the brawler tester role?')) account(sel.value, 'grant'); } })));
  }
  let auditAll = false;
  function auditCard() {
    const A = [].concat(((O && O.audit) || []).map(x => Object.assign({ side: 'accounts' }, x)), ((F && F.audit) || []).map(x => Object.assign({ side: 'play data' }, x)))
      .sort((a, b) => b.at - a.at);
    const shown = auditAll ? A : A.slice(0, 20);
    return h('div', { class: 'card audit' }, h('h2', { text: 'Audit log' }, h('small', { text: A.length + ' actions' })),
      shown.map(x => h('div', {}, when(x.at) + ' · ', h('b', { text: x.by }), ' ' + x.action.replace(/_/g, ' ') + ' ', h('b', { text: x.target || '' }), x.detail ? ' · ' + x.detail : '')),
      A.length > 20 && !auditAll ? h('button', { type: 'button', text: 'Show all', onclick: () => { auditAll = true; draw(); } }) : '');
  }

  function draw() {
    if (!O && !F && !B) { P.replaceChildren(h('p', { class: 'msg', text: err ? 'Players unavailable: ' + err : 'Loading…' })); if (!err) load(); return; }
    const owners = ipOwners();
    const bacc = Object.fromEntries(((B && B.accounts) || []).map(a => [a.name, a]));
    const accs = (O && O.accounts) || [];
    const live = new Set(((F && F.live) || []).map(s => s.user));
    const sorted = accs.slice().sort((x, y) => (live.has(y.username) - live.has(x.username)) || (Math.max(y.last_seen, (F && F.players[y.username] || {}).last || 0) - Math.max(x.last_seen, (F && F.players[x.username] || {}).last || 0)));
    const counts = { tester: 0, admin: 0, blocked: 0 }; for (const a of accs) counts[a.brawler] = (counts[a.brawler] || 0) + 1;
    P.replaceChildren(msg, err ? h('p', { class: 'msg bad', text: 'Partly unavailable: ' + err }) : '', liveCard(),
      h('div', { class: 'card' }, h('h2', { text: 'Players' }, h('small', { text: counts.tester + ' testers · ' + counts.admin + ' admins · ' + counts.blocked + ' blocked · tap a row' })),
        sorted.length ? sorted.map(a => accountRow(a, owners, bacc[a.username])) : h('p', { class: 'msg', text: O ? 'No brawler account yet.' : 'Accounts unavailable.' })),
      codesCard(), grantCard(), buildCard(), blocksCard(), auditCard());
  }

  // the Online now card follows the play every 10 s while the tab is open (the rest is redrawn on each action)
  let liveT = 0;
  async function liveTick() {
    clearTimeout(liveT);
    if (P.hidden || document.hidden) { liveT = setTimeout(liveTick, 10000); return; }
    try { F = await getJ(FB + 'players'); const old = document.getElementById('plLive'); if (old) old.replaceWith(liveCard()); } catch (e) { /* the next tick */ }
    liveT = setTimeout(liveTick, 10000);
  }
  window.FactoryPlayers = { draw: () => { O = F = B = null; err = ''; draw(); clearTimeout(liveT); liveT = setTimeout(liveTick, 10000); } };
})();
