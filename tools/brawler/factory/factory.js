// The BRAWLER FACTORY (canneji.duckdns.org/brawler-factory/, Bruno 2026-10-12: "only include things that can safely be
// modified and recompiled without tokens"). One page, two live tabs (Game and Levels come next):
//   ?tab=chars            the cast (cast.json: every roster fighter, his HUD face) with his edit / ship state
//   ?tab=chars&f=<f>      his Assembly sheet: chainlab/arbitrage.js itself (body[data-app=factory]: no Workshop links),
//                         saving to the same answers + live config as the Lab (the Player's Character lab unchanged)
//   ?tab=build            the ship service (brawler-ship.service, tools/brawler/labcfg.py ship-worker): the daemon's
//                         heartbeat, the ship in progress (its phase, elapsed time, live log), the queue, the last 20 ships
//                         (version, fighters, game.json changes, result, duration, log), Ship pending changes / per
//                         fighter / Rebuild & ship current
// The base URL is /brawler-lab/: cast.json, faces/, the scripts and feedback-api/ are the Lab's.
(function () {
  'use strict';
  const LAB = 'feedback-api/lab/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v != null && v !== false) e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const getJ = u => fetch(u, { cache: 'no-store', credentials: 'same-origin' }).then(r => r.ok ? r.json() : null, () => null);
  const postJ = (u, body) => fetch(u, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(async r => { const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status); return j; });
  const Q = new URLSearchParams(location.search);
  const F = Q.get('f');
  const P = { chars: document.getElementById('pChars'), build: document.getElementById('pBuild') };
  const tabs = [...document.querySelectorAll('.ftabs button[data-tab]')];
  const daemonEl = document.getElementById('daemon');
  const PHASES = ['pull', 'compile', 'build', 'checks', 'publish', 'Lab packs', 'push'];
  let S = { rows: [], daemon: null, skew: 0, configs: [] };     // the queue + the heartbeat; skew = server clock - ours
  const t = iso => iso ? Date.parse(iso) : NaN;
  const ago = ms => { const s = Math.max(0, Math.round(ms / 1000)); return s < 90 ? s + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : s < 172800 ? Math.round(s / 3600) + ' h' : Math.round(s / 86400) + ' d'; };
  const dur = ms => { const s = Math.max(0, Math.round(ms / 1000)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  const hm = iso => { const d = new Date(iso); return isNaN(d) ? '?' : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  const nowS = () => Date.now() + S.skew;
  const fsOf = r => r.fighters || (r.fighter === 'rebuild' ? [] : [r.fighter]);
  const revOf = (r, f) => r.revs ? r.revs[f] : r.fighter === f ? r.rev : undefined;

  // ---- tabs ----
  let tab = Q.get('tab') === 'build' ? 'build' : 'chars';
  function show(k) {
    tab = k;
    for (const [n, el] of Object.entries(P)) el.hidden = n !== k;
    tabs.forEach(b => b.dataset.tab === k ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current'));
    const u = new URL(location.href); u.searchParams.set('tab', k); history.replaceState(null, '', u.pathname + u.search);
    document.title = (k === 'build' ? 'Build' : F || 'Characters') + ' · Brawler Factory';
    if (k === 'build') drawBuild();
    poll();
  }
  tabs.forEach(b => { b.onclick = () => show(b.dataset.tab); });

  // ---- the queue + the heartbeat (every 5 s on the Build tab, every 20 s elsewhere) ----
  let pollT = null;
  async function poll() {
    clearTimeout(pollT);
    const [q, cfg] = await Promise.all([getJ(LAB + 'ship'), getJ(LAB + 'config')]);
    if (q) { S.rows = q.requests || []; S.daemon = q.daemon; if (q.now) S.skew = t(q.now) - Date.now(); }
    if (cfg) S.configs = cfg.configs || [];
    drawDaemon();
    if (tab === 'build') drawBuild(); else drawCastTags();
    pollT = setTimeout(poll, tab === 'build' ? 5000 : 20000);
  }
  function daemonState() {
    const d = S.daemon;
    if (!d) return { cls: 'bad', text: 'Build daemon: never seen' };
    const age = nowS() - t(d.at);
    if (age > 90000) return { cls: 'bad', text: 'Build daemon: OFFLINE since ' + hm(d.at) };
    return d.state === 'building' ? { cls: 'run', text: `Build daemon: building ${d.version || ''} · ${d.step || ''} (seen ${ago(age)} ago)` }
      : { cls: 'ok', text: `Build daemon: online (last seen ${ago(age)} ago)` };
  }
  function drawDaemon() {
    const s = daemonState();
    daemonEl.className = 'pill ' + s.cls;
    daemonEl.textContent = s.cls === 'ok' ? 'daemon online' : s.cls === 'run' ? 'building' : 'daemon OFFLINE';
    daemonEl.title = s.text;
  }

  // ---- what is not shipped: a live config newer than the last ship that covered the fighter ----
  function shipState(f) {
    const mine = S.rows.filter(r => fsOf(r).includes(f));
    const open = mine.find(r => r.status === 'pending' || r.status === 'building');
    const cfg = S.configs.find(c => c.fighter === f);
    const done = mine.filter(r => r.status === 'done');
    const shippedRev = Math.max(0, ...done.map(r => revOf(r, f) || 0));
    const first = S.rows.length ? t(S.rows[0].at) : Infinity;     // (configs older than the ship queue: shipped by hand)
    const unshipped = !!cfg && cfg.version > shippedRev && t(cfg.updated) > first && !open;
    const last = done.map(r => (/(?:shipped|build) (\d\S*)/.exec(r.result || '') || [])[1]).filter(Boolean).pop();
    return { open, unshipped, cfg, last };
  }
  const pendingFighters = () => [...new Set(S.configs.map(c => c.fighter))].filter(f => shipState(f).unshipped);

  // ---- Characters ----
  let cast = null; const cards = {};
  async function drawChars() {
    cast = await getJ('cast.json');
    if (!cast) { P.chars.replaceChildren(h('p', { class: 'note', text: 'The cast (cast.json) could not be read: sign in, or the Lab site is not built.' })); return; }
    if (F) return drawSheet(F);
    const q = h('input', { type: 'search', placeholder: 'Find', 'aria-label': 'Find a fighter' });
    const n = h('span');
    const grid = h('div', { class: 'cast' }, cast.fighters.map(c => {
      const ok = c.engine_decoded && c.dictionary;
      const a = h('a', { class: 'ccard' + (ok ? '' : ' off'), href: ok ? '/brawler-factory/?tab=chars&f=' + encodeURIComponent(c.name) : null, title: ok ? c.display : c.display + ': no Assembly (' + (c.engine_note || 'no dictionary') + ')' },
        c.face ? h('img', { src: c.face, alt: '', width: '44', height: '44', loading: 'lazy' }) : h('span', { class: 'noface' }),
        h('span', { class: 'cb' }, h('b', { text: c.display }), h('span', { class: 'cg', text: c.game_name }), h('span', { class: 'tags' })));
      a._txt = (c.name + ' ' + c.display + ' ' + c.game_name).toLowerCase(); cards[c.name] = a;
      return a;
    }));
    q.oninput = () => { const s = q.value.trim().toLowerCase(); let k = 0; for (const a of Object.values(cards)) { a.hidden = !!s && !a._txt.includes(s); if (!a.hidden) k++; } n.textContent = k + ' fighters'; };
    P.chars.replaceChildren(h('div', { class: 'castbar' }, q, n), grid);
    q.oninput(); drawCastTags();
  }
  function tagsFor(f) {
    const s = shipState(f), out = [];
    if (s.open) out.push(h('span', { class: 'tag ship', text: s.open.status === 'building' ? 'building' : 'queued' }));
    else if (s.unshipped) out.push(h('span', { class: 'tag edit', text: 'unshipped r' + s.cfg.version }));
    if (s.last) out.push(h('span', { class: 'tag ok', text: 'in game ' + s.last }));
    return out;
  }
  function drawCastTags() {
    for (const [f, a] of Object.entries(cards)) a.querySelector('.tags').replaceChildren(...tagsFor(f));
    if (F && sheetTags) sheetTags.replaceChildren(...tagsFor(F));
  }
  let sheetTags = null;
  function drawSheet(f) {
    const C = cast.fighters.find(c => c.name === f);
    if (!C) { P.chars.replaceChildren(h('p', { class: 'note' }, 'No fighter "' + f + '". ', h('a', { href: '/brawler-factory/', text: 'The cast' }))); return; }
    sheetTags = h('span', { class: 'tags' });
    const head = h('div', { class: 'fhead' },
      h('a', { href: '/brawler-factory/?tab=chars', text: '← Cast', 'aria-label': 'Back to the cast' }),
      C.face ? h('img', { src: C.face, alt: '' }) : null,
      h('div', { class: 'who' }, h('b', { text: C.display }), C.game_name + ' · ' + (C.archetype || '?') + ' · ', sheetTags));
    if (!C.engine_decoded || !C.dictionary) { P.chars.replaceChildren(head, h('p', { class: 'note', text: C.engine_note || 'No animation dictionary for him yet: no Assembly.' })); return; }
    const arb = h('section', { id: 'arb', 'aria-label': 'Assembly' }, h('p', { class: 'msg', text: 'Loading his sheet…' }));
    P.chars.replaceChildren(head, arb);
    const s = document.createElement('script'); s.src = 'arbitrage.js';   // (the Lab's, as is: it reads ?f= and fills #arb)
    s.onerror = () => arb.replaceChildren(h('p', { class: 'note', text: 'arbitrage.js could not be loaded.' }));
    document.body.append(s);
    drawCastTags();
  }

  // ---- Build ----
  let openLog = null;                               // the request id whose log is open (refreshed while it builds)
  const B = { msg: h('span', { class: 'msg', role: 'status', 'aria-live': 'polite' }) };
  async function ship(body, label) {
    B.msg.className = 'msg'; B.msg.textContent = 'Queuing ' + label + '…';
    try { const j = await postJ(LAB + 'ship_batch', body); B.msg.textContent = `Queued #${j.ship.id}: ${label}.`; }
    catch (e) { B.msg.className = 'msg bad'; B.msg.textContent = 'Not queued: ' + e.message; }
    poll();
  }
  function stepsEl(r) {
    const i = PHASES.indexOf(r.step);
    const failedAt = r.status === 'failed' ? PHASES.indexOf(PHASE_OF((/^([a-z_ -]+?):/i.exec(r.result || '') || [])[1])) : -1;
    return h('div', { class: 'steps', 'aria-label': 'Steps' }, PHASES.map((p, k) => h('span', {
      class: r.status === 'building' ? (k < i ? 'done' : k === i ? 'now' : '') : r.status === 'done' && /^shipped/.test(r.result || '') ? 'done' : k === failedAt ? 'fail' : k < failedAt ? 'done' : '', text: p })));
  }
  const STEP_PHASE = { reset: 'pull', 'git pull': 'pull', arb_compile: 'compile', 'make sdk': 'build', make: 'build', bank_proof: 'checks', 'regress bleed': 'checks',
                       commit: 'publish', 'publish-vps': 'publish', 'scenario publish': 'publish', labpub: 'Lab packs', push: 'push' };
  function PHASE_OF(step) { return STEP_PHASE[step] || step; }
  const logs = {};                                  // id -> the log text (a closed ship's is fetched once)
  function logBox(r) {
    const pre = h('pre', { class: 'log', text: logs[r.id] || 'Loading the log…' });
    if (logs[r.id] && r.status !== 'building') return pre;
    fetch(LAB + 'ship_log/' + r.id, { cache: 'no-store', credentials: 'same-origin' }).then(async x => {
      logs[r.id] = pre.textContent = x.ok ? await x.text() : (x.status === 404 ? 'No log on the server for #' + r.id + ' (ships before the Factory kept it on brunux only).' : 'HTTP ' + x.status);
      if (r.status === 'building') pre.scrollTop = pre.scrollHeight;
    });
    return pre;
  }
  function shipRow(r, cur) {
    const fs = fsOf(r);
    const start = t(r.started_at) || t(r.at), end = r.closed_at ? t(r.closed_at) : nowS();
    const ver = r.status === 'done' ? (/(?:shipped|build) (\d\S*)/.exec(r.result || '') || [])[1] || '' : r.version || '';   // (a "nothing changed" ship made no version)
    const res = r.status === 'done' ? (/^nothing changed/.test(r.result || '') ? 'nothing changed' : '✓ shipped') : r.status;
    const logBtn = h('button', { type: 'button', text: openLog === r.id ? 'Hide log' : 'Log', onclick: () => { openLog = openLog === r.id ? null : r.id; drawBuild(); } });
    return h('div', { class: 'ship' },
      h('span', { class: 'v', text: ver || '#' + r.id }),
      h('span', { class: 'who', text: (fs.length ? fs.join(', ') : 'rebuild (engine as pushed)') }),
      h('span', { class: 't', text: cur ? dur(end - start) : (r.closed_at ? hm(r.closed_at) + ' · ' + dur(end - start) : hm(r.at)) }),
      cur || r.status === 'failed' ? stepsEl(r) : null,
      (r.changes || []).length ? r.changes.map(c => h('p', { class: 'ch', text: c })) : null,
      h('p', { class: 'res' + (r.status === 'failed' ? ' bad' : ''), text: cur ? (r.result || 'starting') : res + (r.result && r.status !== 'done' || /left out/.test(r.result || '') ? ' — ' + r.result : '') }),
      r.status === 'dropped' || r.status === 'pending' ? null : h('div', { class: 'acts' }, logBtn),
      openLog === r.id ? logBox(r) : null);
  }
  function drawBuild() {
    const d = daemonState();
    const pend = pendingFighters();
    const building = S.rows.filter(r => r.status === 'building');
    const queued = S.rows.filter(r => r.status === 'pending');
    const hist = S.rows.filter(r => r.status === 'done' || r.status === 'failed').slice(-20).reverse();
    const shipAll = h('button', { type: 'button', class: 'primary', disabled: pend.length ? null : '', text: pend.length ? `Ship pending changes (${pend.join(', ')})` : 'Ship pending changes (none)',
      onclick: () => ship({ fighters: pend, note: 'Ship pending changes (the Factory)' }, pend.join(', ')) });
    const rebuild = h('button', { type: 'button', text: 'Rebuild & ship current', title: 'No data change: the game as pushed (e.g. after an engine merge), new version',
      onclick: () => { if (confirm('Rebuild and ship the game as pushed (no data change)?')) ship({ rebuild: true, note: 'Rebuild & ship current (the Factory)' }, 'rebuild'); } });
    const per = pend.length ? h('div', { class: 'pend' }, 'One at a time:', pend.map(f => h('button', { type: 'button', text: 'Ship ' + f, onclick: () => ship({ fighters: [f], note: 'Ship ' + f + ' (the Factory)' }, f) }))) : null;
    P.build.replaceChildren(...[
      h('div', { class: 'card' }, h('p', { class: 'dline' }, h('span', { class: 'pill ' + d.cls, text: d.text })), h('div', { class: 'btns' }, shipAll, rebuild), per, B.msg),
      building.length ? h('div', { class: 'card cur' }, h('h2', { text: 'Now building' }), building.map(r => shipRow(r, true))) : null,
      queued.length ? h('div', { class: 'card' }, h('h2', { text: 'Queue (' + queued.length + ')' }), queued.map(r => shipRow(r, false))) : null,
      h('div', { class: 'card' }, h('h2', { text: 'Last ' + hist.length + ' ships' }), hist.length ? hist.map(r => shipRow(r, false)) : h('p', { class: 'msg', text: 'None yet.' }))].filter(Boolean));
  }

  // ---- start ----
  drawChars();
  show(tab);
  window.factoryReady = true;
})();
