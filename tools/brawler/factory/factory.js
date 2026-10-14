// The BRAWLER FACTORY (canneji.duckdns.org/brawler-factory/, Bruno 2026-10-12: "only include things that can safely be
// modified and recompiled without tokens"). One page, three live tabs (Game comes next):
//   ?tab=chars            the cast (cast.json: every roster fighter, his HUD face) with his edit / ship state
//   ?tab=chars&f=<f>      his Assembly sheet: chainlab/arbitrage.js itself (body[data-app=factory]: no Workshop links),
//                         saving to the same answers + live config as the Lab (the Player's Character lab unchanged)
//   ?tab=build            the ship service (brawler-ship.service, tools/brawler/labcfg.py ship-worker): the daemon's
//                         heartbeat, the ship in progress (its phase, elapsed time, live log), the queue, the last 20 ships
//                         (version, fighters, game.json changes, result, duration, log), Ship pending changes / per
//                         fighter / Rebuild & ship current
//   ?tab=levels           each campaign stage's name, background, song (tools/brawler/levels.py): edits saved as the
//                         Levels draft (lab/levels), shipped by Ship pending changes; the songs' 20 s previews are MP3s
//                         the ship service plays in our emulator (/brawler-factory/songs/). Waves: not here
//   ?tab=chars (the cast) also carries Roster & select (roster.js, tools/brawler/roster.py): the Selectable switches and
//                         the select layout editor, the "roster" draft section (lab/roster), shipped by Ship pending changes
//   ?tab=players         the brawler Oros accounts (admins, testers) and the build each gets (players.js, the "players" section, live)
//   ?tab=game             the game-wide numbers and texts (game.js, tools/brawler/gamecfg.py): the "game" draft section
//                         (lab/game), shipped by Ship pending changes
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
  const P = { chars: document.getElementById('pChars'), build: document.getElementById('pBuild'), levels: document.getElementById('pLevels'), game: document.getElementById('pGame'), players: document.getElementById('pPlayers') };
  const FG = window.FactoryGame;                    // the Game tab (game.js)
  const FR = window.FactoryRoster;                  // Roster & select (roster.js, the cast view)
  const tabs = [...document.querySelectorAll('.ftabs button[data-tab]')];
  const daemonEl = document.getElementById('daemon');
  const PHASES = ['pull', 'compile', 'build', 'checks', 'publish', 'Lab packs', 'push'];
  let S = { rows: [], daemon: null, skew: 0, configs: [], lv: {} };   // lv: the Levels {draft, game}     // the queue + the heartbeat; skew = server clock - ours
  const t = iso => iso ? Date.parse(iso) : NaN;
  const ago = ms => { const s = Math.max(0, Math.round(ms / 1000)); return s < 90 ? s + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : s < 172800 ? Math.round(s / 3600) + ' h' : Math.round(s / 86400) + ' d'; };
  const dur = ms => { const s = Math.max(0, Math.round(ms / 1000)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  const hm = iso => { const d = new Date(iso); return isNaN(d) ? '?' : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  const nowS = () => Date.now() + S.skew;
  const fsOf = r => r.fighters || (r.fighter === 'rebuild' ? [] : [r.fighter]);
  const revOf = (r, f) => r.revs ? r.revs[f] : r.fighter === f ? r.rev : undefined;

  // ---- tabs ----
  let tab = ['build', 'levels', 'game', 'players'].includes(Q.get('tab')) ? Q.get('tab') : 'chars';
  function show(k) {
    tab = k;
    for (const [n, el] of Object.entries(P)) el.hidden = n !== k;
    tabs.forEach(b => b.dataset.tab === k ? b.setAttribute('aria-current', 'page') : b.removeAttribute('aria-current'));
    const u = new URL(location.href); u.searchParams.set('tab', k); history.replaceState(null, '', u.pathname + u.search);
    document.title = ({ build: 'Build', levels: 'Levels', game: 'Game', players: 'Players' }[k] || F || 'Characters') + ' · Brawler Factory';
    if (k === 'build') drawBuild();
    if (k === 'game') FG.draw();
    if (k === 'players') window.FactoryPlayers.draw();
    if (k !== 'levels') stopPreview();
    poll();
  }
  tabs.forEach(b => { b.onclick = () => show(b.dataset.tab); });

  // ---- the queue + the heartbeat (every 5 s on the Build tab, every 20 s elsewhere) ----
  let pollT = null;
  async function poll() {
    clearTimeout(pollT);
    const [q, cfg, lv, gm, ro] = await Promise.all([getJ(LAB + 'ship'), getJ(LAB + 'config'), getJ(LAB + 'levels'), getJ(LAB + 'game'), getJ(LAB + 'roster')]);
    if (q) { S.rows = q.requests || []; S.daemon = q.daemon; if (q.now) S.skew = t(q.now) - Date.now(); }
    if (cfg) S.configs = cfg.configs || [];
    if (lv) S.lv = lv;
    FG.poll(gm, S.rows, tab === 'game');
    FR.poll(ro, S.rows, tab === 'chars' && !F);
    drawDaemon();
    if (tab === 'build') drawBuild(); else if (tab === 'game') { /* (FG.poll: its marks) */ } else if (tab === 'levels') { if (lvOpenStage < 0) drawLevels(); } else if (tab === 'players') { /* (players.js: drawn on open and on Save) */ } else drawCastTags();   // (an open editor: not redrawn under his fingers)
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
  // the Levels: the draft's stages (or the game's), what differs from the game, a levels ship queued / building
  const LF = ['name', 'background', 'music'];
  const lvGame = () => (S.lv.game && S.lv.game.stages) || null;
  const lvWant = () => { const g = lvGame(), d = S.lv.draft && S.lv.draft.stages; return g && d && d.length === g.length ? d : g; };
  const lvDiff = () => { const g = lvGame(), w = lvWant(); return g ? g.map((x, i) => LF.filter(k => x[k] !== w[i][k])) : []; };
  // the bonus stages (TODO T7, levels.py bonus_view): the draft's bonus (or the game's), whether it differs
  const bnGame = () => (S.lv.game && S.lv.game.bonus) || null;
  const bnWant = () => (S.lv.draft && S.lv.draft.bonus) || bnGame();
  const bnDiff = () => !!bnGame() && JSON.stringify(bnWant()) !== JSON.stringify(bnGame());
  // the stage intro (note 20261014-192343-5d29, levels.py intro_view): the draft's (or the game's), whether it differs
  const inGame = () => (S.lv.game && S.lv.game.intro) || null;
  const inWant = () => (S.lv.draft && S.lv.draft.intro) || inGame();
  const inDiff = () => !!inGame() && JSON.stringify(inWant()) !== JSON.stringify(inGame());
  const lvOpen = () => S.rows.find(r => r.levels && (r.status === 'pending' || r.status === 'building'));
  const lvPending = () => !lvOpen() && (lvDiff().some(d => d.length) || bnDiff() || inDiff());
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
    P.chars.replaceChildren(FR.card(cast), h('div', { class: 'castbar' }, q, n), grid);
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
  const STEP_PHASE = { reset: 'pull', 'git pull': 'pull', arb_compile: 'compile', levels: 'compile', game: 'compile', roster: 'compile', 'make sdk': 'build', make: 'build', bank_proof: 'checks', 'regress bleed': 'checks',
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
      h('span', { class: 'who', text: (fs.length || r.levels || r.game || r.roster ? fs.concat(['levels', 'game', 'roster'].filter(x => r[x])).join(', ') : 'rebuild (engine as pushed)') }),
      h('span', { class: 't', text: cur ? dur(end - start) : (r.closed_at ? hm(r.closed_at) + ' · ' + dur(end - start) : hm(r.at)) }),
      cur || r.status === 'failed' ? stepsEl(r) : null,
      (r.changes || []).length ? r.changes.map(c => h('p', { class: 'ch', text: c })) : null,
      h('p', { class: 'res' + (r.status === 'failed' ? ' bad' : ''), text: cur ? (r.result || 'starting') : res + (r.result && r.status !== 'done' || /left out/.test(r.result || '') ? ' — ' + r.result : '') }),
      r.status === 'dropped' || r.status === 'pending' ? null : h('div', { class: 'acts' }, logBtn),
      openLog === r.id ? logBox(r) : null);
  }
  function drawBuild() {
    const d = daemonState();
    const pend = pendingFighters(), lvp = lvPending();
    const gp = FG.pending(), rp = FR.pending();
    const all = pend.concat(lvp ? ['levels'] : [], gp ? ['game'] : [], rp ? ['roster'] : []);
    const building = S.rows.filter(r => r.status === 'building');
    const queued = S.rows.filter(r => r.status === 'pending');
    const hist = S.rows.filter(r => r.status === 'done' || r.status === 'failed').slice(-20).reverse();
    const shipAll = h('button', { type: 'button', class: 'primary', disabled: all.length ? null : '', text: all.length ? `Ship pending changes (${all.join(', ')})` : 'Ship pending changes (none)',
      onclick: () => ship({ fighters: pend, levels: lvp || undefined, game: gp || undefined, roster: rp || undefined, note: 'Ship pending changes (the Factory)' }, all.join(', ')) });
    const rebuild = h('button', { type: 'button', text: 'Rebuild & ship current', title: 'No data change: the game as pushed (e.g. after an engine merge), new version',
      onclick: () => { if (confirm('Rebuild and ship the game as pushed (no data change)?')) ship({ rebuild: true, note: 'Rebuild & ship current (the Factory)' }, 'rebuild'); } });
    const per = all.length > 1 ? h('div', { class: 'pend' }, 'One at a time:', all.map(f => h('button', { type: 'button', text: 'Ship ' + f,
      onclick: () => ship(f === 'levels' || f === 'game' || f === 'roster' ? { [f]: true, note: 'Ship ' + f + ' (the Factory)' } : { fighters: [f], note: 'Ship ' + f + ' (the Factory)' }, f) }))) : null;
    P.build.replaceChildren(...[
      h('div', { class: 'card' }, h('p', { class: 'dline' }, h('span', { class: 'pill ' + d.cls, text: d.text })), h('div', { class: 'btns' }, shipAll, rebuild), per, B.msg),
      building.length ? h('div', { class: 'card cur' }, h('h2', { text: 'Now building' }), building.map(r => shipRow(r, true))) : null,
      queued.length ? h('div', { class: 'card' }, h('h2', { text: 'Queue (' + queued.length + ')' }), queued.map(r => shipRow(r, false))) : null,
      h('div', { class: 'card' }, h('h2', { text: 'Last ' + hist.length + ' ships' }), hist.length ? hist.map(r => shipRow(r, false)) : h('p', { class: 'msg', text: 'None yet.' }))].filter(Boolean));
  }

  // ---- Levels: one row per stage, tap to edit its name / background / song ----
  let lvOpenStage = -1, lvEdit = null, lvScroll = null;   // the stage being edited, its unsaved values, the song list scroll
  const L = { msg: h('span', { class: 'msg', role: 'status', 'aria-live': 'polite' }) };
  const NAME_RE = /^[A-Z0-9 .!-]{1,12}$/;
  const audio = new Audio(); let playing = null;     // one preview at a time: the song's name
  audio.onended = () => { playing = null; drawLevels(); };
  function stopPreview() { audio.pause(); playing = null; }
  function preview(sg) {
    if (playing === sg.name) { stopPreview(); return drawLevels(); }
    audio.src = '/brawler-factory/' + sg.preview; playing = sg.name;
    audio.play().catch(() => { playing = null; L.msg.className = 'msg bad'; L.msg.textContent = 'No preview of ' + sg.name + ' yet (the build daemon makes them).'; drawLevels(); });
    drawLevels();
  }
  const bgImg = i => h('img', { class: 'lbg', src: 'stages/bg' + i + '.jpg', alt: 'background ' + i, loading: 'lazy' });
  async function saveLevels(stages, what, bonus, intro) {
    L.msg.className = 'msg'; L.msg.textContent = 'Saving…';
    const b = bonus || (bnDiff() ? bnWant() : undefined);          // (a stage's save keeps an unshipped bonus draft)
    const it = intro || (inDiff() ? inWant() : undefined);         // (and an unshipped intro draft)
    const body = { stages }; if (b) body.bonus = b; if (it) body.intro = it;
    try { S.lv = await postJ(LAB + 'levels', body); L.msg.textContent = what + ': saved. Ship it from the Build tab (Ship pending changes).'; lvEdit = null; }
    catch (e) { L.msg.className = 'msg bad'; L.msg.textContent = 'Not saved: ' + e.message; }
    drawLevels(); drawDaemon();
  }
  function drawLevels() {
    const G = S.lv.game;
    if (!G) { P.levels.replaceChildren(h('p', { class: 'note', text: 'The game\'s levels are not known yet: the build daemon reports them when it starts and after each ship.' })); return; }
    const want = lvWant(), diff = lvDiff(), open = lvOpen();
    const songOf = n => G.songs.find(x => x.name === n) || { name: n, source: '?' };
    const rows = want.map((st, i) => {
      const ed = diff[i].length, isOpen = lvOpenStage === i, bn = bnWant(), after = !!bn && bn.after.includes(i + 1);
      const row = h('button', { type: 'button', class: 'lrow' + (isOpen ? ' open' : ''), 'aria-expanded': isOpen ? 'true' : 'false',
        onclick: () => { lvOpenStage = isOpen ? -1 : i; lvEdit = null; lvScroll = null; L.msg.textContent = ''; drawLevels(); } },
        h('b', { class: 'ln', text: String(i + 1) }), bgImg(st.background),
        h('span', { class: 'lt' }, h('b', { text: st.name }), h('span', { text: '♪ ' + st.music + (i === 0 ? ' *' : '') })),
        after ? h('span', { class: 'tag', text: '+ bonus' }) : null,
        ed ? h('span', { class: 'tag ' + (open ? 'ship' : 'edit'), text: open ? (open.status === 'building' ? 'building' : 'queued') : 'unshipped' }) : null);
      return [row, isOpen ? editor(i, st, G) : null];
    });
    const bn = bnWant();
    if (bn) {                                                      // the bonus games: one row, tap to edit
      const isOpen = lvOpenStage === 'bonus';
      rows.push([h('button', { type: 'button', class: 'lrow' + (isOpen ? ' open' : ''), 'aria-expanded': isOpen ? 'true' : 'false',
        onclick: () => { lvOpenStage = isOpen ? -1 : 'bonus'; lvEdit = null; L.msg.textContent = ''; drawLevels(); } },
        h('b', { class: 'ln', text: 'B' }), h('span', {}),
        h('span', { class: 'lt' }, h('b', { text: 'Bonus games' }), h('span', { text: 'after stage ' + (bn.after.join(', ') || 'none') + ' · ' + bn.games.map(x => x.name).join(' / ') + (bn.fury_lock ? ' · fury locked' : '') })),
        bnDiff() ? h('span', { class: 'tag ' + (open ? 'ship' : 'edit'), text: open ? 'queued' : 'unshipped' }) : null),
        isOpen ? bonusEditor(bn, G) : null]);
    }
    const it = inWant();
    if (it) {                                                      // the stage intro: one row, tap to edit
      const isOpen = lvOpenStage === 'intro';
      rows.unshift([h('button', { type: 'button', class: 'lrow' + (isOpen ? ' open' : ''), 'aria-expanded': isOpen ? 'true' : 'false',
        onclick: () => { lvOpenStage = isOpen ? -1 : 'intro'; lvEdit = null; L.msg.textContent = ''; drawLevels(); } },
        h('b', { class: 'ln', text: 'I' }), h('span', {}),
        h('span', { class: 'lt' }, h('b', { text: 'Stage intro' }), h('span', { text: (it.title || 'no title') + ' · fade ' + it.fade + ' · walk ' + it.side + ' at ' + it.walk_at + ' · wave +' + it.wave_delay })),
        inDiff() ? h('span', { class: 'tag ' + (open ? 'ship' : 'edit'), text: open ? 'queued' : 'unshipped' }) : null),
        isOpen ? introEditor(it) : null]);
    }
    P.levels.replaceChildren(h('div', { class: 'card' },
      h('h2', {}, 'Levels', h('span', { class: 'sp' }), h('span', { class: 'gv', text: 'in game ' + (G.version || '?') })),
      h('div', { class: 'lrows' }, rows),
      h('p', { class: 'msg lfoot', text: '* Stage 1 plays P1\'s own theme when he has one (his roster music); this song otherwise. Waves are not edited here.' }),
      L.msg));
  }
  function editor(i, st, G) {
    const v = lvEdit || (lvEdit = { ...st }); const game = lvGame()[i];
    const name = h('input', { type: 'text', value: v.name, maxlength: '12', autocapitalize: 'characters', spellcheck: 'false', 'aria-label': 'Stage ' + (i + 1) + ' name' });
    const nmsg = h('span', { class: 'msg' });
    const nameOk = () => NAME_RE.test(v.name);
    name.oninput = () => { const p = name.selectionStart; name.value = name.value.toUpperCase(); name.setSelectionRange(p, p); v.name = name.value;
      nmsg.className = nameOk() ? 'msg' : 'msg bad'; nmsg.textContent = nameOk() ? '' : '1-12 characters: A-Z 0-9 space . ! -'; save.disabled = !nameOk() || same(); };
    const same = () => LF.every(k => v[k] === st[k]);
    const bgs = h('div', { class: 'lbgs' }, G.bgs.map(b => {
      const fits = b.w >= game.need_w;
      return h('button', { type: 'button', class: 'lbgb', 'aria-pressed': v.background === b.i ? 'true' : 'false', disabled: fits ? null : '',
        title: fits ? b.name + ', ' + b.w + ' px' : b.name + ': ' + b.w + ' px wide, this stage\'s waves need ' + game.need_w,
        onclick: () => { v.background = b.i; drawLevels(); } }, bgImg(b.i), h('span', { text: b.i + (fits ? '' : ' (too short)') }));
    }));
    const songs = h('div', { class: 'lsongs', role: 'listbox', 'aria-label': 'Song' }, G.songs.map(sg => h('div', { class: 'lsong' + (v.music === sg.name ? ' on' : '') },
      h('button', { type: 'button', class: 'play', 'aria-label': (playing === sg.name ? 'Stop ' : 'Play 20 s of ') + sg.name, text: playing === sg.name ? '■' : '▶', onclick: () => preview(sg) }),
      h('button', { type: 'button', class: 'pick', role: 'option', 'aria-selected': v.music === sg.name ? 'true' : 'false', title: sg.what,
        onclick: () => { v.music = sg.name; drawLevels(); } }, h('b', { text: sg.name }), h('small', { text: ' ' + sg.source })))));
    requestAnimationFrame(() => { const on = songs.querySelector('.lsong.on');     // the list where he left it, else the chosen song in view
      songs.scrollTop = lvScroll != null ? lvScroll : on ? on.offsetTop - songs.clientHeight / 2 : 0; songs.onscroll = () => { lvScroll = songs.scrollTop; }; });
    const save = h('button', { type: 'button', class: 'primary', text: 'Save stage ' + (i + 1), disabled: !nameOk() || same() ? '' : null,
      onclick: () => saveLevels(lvWant().map((x, k) => k === i ? { name: v.name, background: v.background, music: v.music } : { name: x.name, background: x.background, music: x.music }), 'Stage ' + (i + 1)) });
    const undo = LF.some(k => st[k] !== game[k]) ? h('button', { type: 'button', text: 'Back to the game\'s',
      onclick: () => saveLevels(lvWant().map((x, k) => { const y = k === i ? game : x; return { name: y.name, background: y.background, music: y.music }; }), 'Stage ' + (i + 1) + ' back to the game\'s') }) : null;
    return h('div', { class: 'ledit' },
      h('label', { class: 'lf' }, h('span', { text: 'Name' }), name), nmsg,
      h('div', { class: 'lf' }, h('span', { text: 'Background' })), bgs,
      h('div', { class: 'lf' }, h('span', { text: 'Music' }), h('small', { class: 'msg', text: i === 0 ? 'stage 1: P1\'s own theme when he has one, else this' : '' })), songs,
      bnAfterToggle(i, G),
      h('div', { class: 'btns' }, save, undo, h('button', { type: 'button', text: 'Close', onclick: () => { lvOpenStage = -1; lvEdit = null; drawLevels(); } })));
  }
  // a stage's "bonus games after it" switch (not the last stage: a bonus needs a stage after it); saved at once
  function bnAfterToggle(i, G) {
    const bn = bnWant();
    if (!bn || i + 1 >= G.stages.length) return null;
    const on = bn.after.includes(i + 1);
    return h('label', { class: 'lf' }, h('input', { type: 'checkbox', checked: on ? '' : null, onchange: () => {
      const after = on ? bn.after.filter(x => x !== i + 1) : bn.after.concat([i + 1]).sort((a, b) => a - b);
      saveLevels(lvWant().map(x => ({ name: x.name, background: x.background, music: x.music })), 'Bonus after stage ' + (i + 1) + (on ? ': off' : ': on'), { ...bn, after });
    } }), h('span', { text: 'Bonus games after this stage' }));
  }
  // the bonus games: the pick clock, the fury lock, each game's name / song / clock / posts or top-grade reward
  function bonusEditor(bn, G) {
    const v = lvEdit || (lvEdit = JSON.parse(JSON.stringify(bn)));
    const num = (o, k, lo, hi, label) => h('label', { class: 'lf' }, h('span', { text: label }),
      h('input', { type: 'number', min: String(lo), max: String(hi), value: String(o[k]), style: 'width:5em', onchange: e => { o[k] = Math.max(lo, Math.min(hi, parseInt(e.target.value, 10) || lo)); } }));
    const games = v.games.map(gm => h('div', { class: 'ledit' },
      h('label', { class: 'lf' }, h('span', { text: 'Name' }), h('input', { type: 'text', value: gm.name, maxlength: '18', autocapitalize: 'characters', spellcheck: 'false',
        oninput: e => { e.target.value = e.target.value.toUpperCase(); gm.name = e.target.value; } })),
      h('label', { class: 'lf' }, h('span', { text: 'Music' }), h('select', { onchange: e => { gm.music = e.target.value; } },
        G.songs.map(sg => h('option', { value: sg.name, selected: sg.name === gm.music ? '' : null, text: sg.name })))),
      h('label', { class: 'lf' }, h('span', { text: 'AOF2 slot' }), h('select', { onchange: e => { gm.slot = parseInt(e.target.value, 10); } },
        [[0, 'Spirit Training'], [2, 'Super Death Blow']].map(([s, t]) => h('option', { value: String(s), selected: s === gm.slot ? '' : null, text: t })))),
      num(gm, 'seconds', 5, 99, 'Clock (s)'),
      gm.kind === 'break' ? [num(gm, 'count', 1, 20, 'Posts'), num(gm, 'hp', 1, 30, 'Hits per post')] : num(gm, 'top', 0, 3, 'Meter chunks at PERFECT')));
    return h('div', { class: 'ledit' },
      num(v, 'pick_seconds', 3, 9, 'Pick screen clock (s)'),
      h('label', { class: 'lf' }, h('input', { type: 'checkbox', checked: v.fury_lock ? '' : null, onchange: e => { v.fury_lock = e.target.checked; } }),
        h('span', { text: 'Fury + MAX locked until the posts are won' })),
      games,
      h('div', { class: 'btns' },
        h('button', { type: 'button', class: 'primary', text: 'Save bonus games', onclick: () => saveLevels(lvWant().map(x => ({ name: x.name, background: x.background, music: x.music })), 'Bonus games', v) }),
        bnDiff() ? h('button', { type: 'button', text: 'Back to the game\'s', onclick: () => saveLevels(lvWant().map(x => ({ name: x.name, background: x.background, music: x.music })), 'Bonus games back to the game\'s', bnGame()) }) : null,
        h('button', { type: 'button', text: 'Close', onclick: () => { lvOpenStage = -1; lvEdit = null; drawLevels(); } })));
  }

  // the stage intro: every stage's start (ticks, 60 a second): fade, title, the walk in, the first wave
  function introEditor(it) {
    const v = lvEdit || (lvEdit = { ...it });
    const keep = () => lvWant().map(x => ({ name: x.name, background: x.background, music: x.music }));
    const num = (k, lo, hi, label) => h('label', { class: 'lf' }, h('span', { text: label }),
      h('input', { type: 'number', min: String(lo), max: String(hi), value: String(v[k]), style: 'width:5em', onchange: e => { v[k] = Math.max(lo, Math.min(hi, parseInt(e.target.value, 10) || 0)); } }));
    const pick = (k, opts, label) => h('label', { class: 'lf' }, h('span', { text: label }), h('select', { onchange: e => { v[k] = e.target.value; } },
      opts.map(o => h('option', { value: o, selected: o === v[k] ? '' : null, text: o }))));
    return h('div', { class: 'ledit' },
      h('label', { class: 'lf' }, h('span', { text: 'Title ({name} = stage name)' }), h('input', { type: 'text', value: v.title, maxlength: '38', spellcheck: 'false',
        oninput: e => { v.title = e.target.value.toUpperCase().replace('{NAME}', '{name}'); } })),
      num('fade', 0, 255, 'Fade-in (ticks)'), num('title_at', 0, 1000, 'Title at'), num('title_hold', 0, 1000, 'Title shown for'),
      num('walk_at', 0, 1000, 'Walk in at'), pick('side', ['left', 'right'], 'From the'), pick('gait', ['walk', 'run'], 'Gait'),
      num('from', 0, 120, 'Start px outside'), num('wave_delay', 0, 1000, 'First wave after (ticks)'),
      h('div', { class: 'btns' },
        h('button', { type: 'button', class: 'primary', text: 'Save stage intro', onclick: () => saveLevels(keep(), 'Stage intro', undefined, v) }),
        inDiff() ? h('button', { type: 'button', text: 'Back to the game\'s', onclick: () => saveLevels(keep(), 'Stage intro back to the game\'s', undefined, inGame()) }) : null,
        h('button', { type: 'button', text: 'Close', onclick: () => { lvOpenStage = -1; lvEdit = null; drawLevels(); } })));
  }

  // ---- start ----
  drawChars();
  show(tab);
  window.factoryReady = true;
})();
