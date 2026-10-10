/* "Try in game" (Bruno 2026-10-10: "a per-fighter build that embeds everything, reassigned live from the web page by RAM
 * injection, to see how an animation and a combination of animations look in game"). One panel shared by the Workshop
 * (workshop.js), the animation dictionary (anims.js) and the arbitration sheet (arbitrage.js): the fighter's Lab build
 * (rom/lab-<f>.neo, make LAB_FIGHTER=<f>: every animation of his dictionary in his LAB special; rom/lab-<f>.json its
 * manifest, tryit_site.py) in the Chain Lab's player (core.wasm + lab.js + gameplay.js, loaded on the first "Try"),
 * P1 = the fighter against a standing dummy (the Chain Lab's training, req 1). The game reads lab entries (fighter.c
 * "Lab: try in game"): an animation $NN, a special of the pool (an S- piece), a throw (a T- piece).
 *   TryIt.has(f)                        -> Promise<bool>: a Lab build of f exists
 *   TryIt.button(f, label, fn)          a "Try in game" button (hidden while f has no Lab build), fn() on click
 *   TryIt.queue(f, pieces, {loop})      a TRY blob (load 6): the pieces back to back, now; A from neutral again
 *   TryIt.sheet(f, {slots, chain})      a TRY blob: each arbitration slot's pieces (slot id: arbitrage.js) + the chain's
 *                                       presses as a chain override (load 5) when every press is a brawler move
 *   pieces: '$A9' / 'A9' (an animation), 'S-004' (a special), 'T-001' (a throw: a grab slot only)
 * SEND TO PLAYER (the Character Lab, docs/feedback.md "Character Lab: the web pages"): the same TRY blob (lab.js encodeTry,
 * the bytes the preview installs) PUT as the fighter's live config (feedback-api/lab/config/<f>, If-Match = the hash this
 * page last saw: a 412 = someone else changed it, reloaded and said); the Player polls it and applies it at neutral. The
 * blob is lab.js liveBlob: the TRY blob, + the chain override when one is set (a sheet's chain, the chain tool's), which
 * the Player writes as load 5 first. A queue keeps the live config's chain, the chain tool keeps its TRY blob, a sheet
 * sets both (as the preview: a sheet clears the chain it does not set).
 *   TryIt.button(f, label, fn, send)    + a "Send to Player" button when send is given: send() -> {queue, loop} | {sheet}
 *                                       | {chain: {bytes, entry, text}}
 *   TryIt.send(f, what, el)             the Send itself (el: where it says what happened)
 *   TryIt.liveLine(f)                   "Live config: rN, updated when / by, History, Revert" (kept up to date)
 * window.tryit (tests): {state, lab, gp, ready, live} */
(function () {
  'use strict';
  const h = (t, a, ...kids) => {
    const e = document.createElement(t);
    for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== undefined) e.setAttribute(k, v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c);
    return e;
  };
  const get = async (p, kind) => {
    const r = await fetch(p, { cache: 'no-cache', credentials: 'same-origin' });
    if (!r.ok) throw new Error(p + ': HTTP ' + r.status);
    return kind === 'json' ? r.json() : new Uint8Array(await r.arrayBuffer());
  };
  const script = src => new Promise((ok, ko) => {
    if (document.querySelector(`script[data-tryit="${src}"]`)) { ok(); return; }
    const s = document.createElement('script'); s.src = src; s.dataset.tryit = src; s.onload = ok; s.onerror = () => ko(new Error(src + ': not loaded'));
    document.head.append(s);
  });
  const hex = v => '$' + v.toString(16).toUpperCase();
  let index = null;                                   // rom/index.json: the fighters with a Lab build
  const has = f => (index = index || get('rom/index.json', 'json').catch(() => [])).then(l => l.includes(f));

  // ---- the panel ---------------------------------------------------------------------------------------------------
  const CSS = `
#tryit { position: fixed; right: 8px; bottom: 8px; z-index: 60; width: min(660px, calc(100vw - 16px)); max-height: calc(100vh - 16px);
  overflow: auto; background: #fff; color: #000; border: 3px solid #000; padding: 8px; box-sizing: border-box; font: 15px/1.4 "Atkinson Hyperlegible", system-ui, sans-serif; }
#tryit[hidden] { display: none !important; }
#tryit .thead { display: flex; gap: 8px; align-items: center; border-bottom: 2px solid #000; padding-bottom: 6px; margin-bottom: 6px; }
#tryit .thead b { flex: 1 1 auto; font-size: 16px; }
#tryit button, #tryit select { font: inherit; font-size: 14px; background: #fff; color: #000; border: 2px solid #000; padding: 5px 9px; cursor: pointer; }
#tryit button[aria-pressed="true"], #tryit button.on { background: #000; color: #fff; font-weight: 700; }
#tryit button:disabled { border-style: dashed; cursor: default; }
#tryit button:focus-visible { outline: 3px dashed #000; outline-offset: 2px; }
#tryit canvas { display: block; image-rendering: pixelated; image-rendering: crisp-edges; border: 2px solid #000; background: #000; margin: 0 auto; touch-action: none; }
#tryit .trow { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 6px 0; }
#tryit .tnow { border: 2px solid #000; padding: 5px 7px; font-size: 14px; overflow-wrap: anywhere; }
#tryit .tstat { font: 12px/1.35 ui-monospace, monospace; min-height: 2.7em; overflow-wrap: anywhere; }
#tryit .terr { border: 3px double #000; padding: 5px 7px; font-weight: 700; }
#tryit .terr:empty { display: none; }
#tryit .tkeys { font-size: 12px; }
#tryit kbd { border: 1px solid #000; padding: 0 3px; font: 12px ui-monospace, monospace; }
#tryit .ttouch { display: none; justify-content: space-between; gap: 10px; user-select: none; -webkit-user-select: none; margin-top: 6px; }
#tryit .ttouch.show { display: flex; }
#tryit .ttouch .pad { display: grid; grid-template-columns: repeat(3, 48px); grid-template-rows: repeat(3, 48px); gap: 4px; }
#tryit .ttouch .btns { display: grid; grid-template-columns: repeat(2, 64px); gap: 5px; }
#tryit .ttouch button { min-height: 48px; touch-action: none; padding: 2px; }
.tryit-btn { font: inherit; font-size: 14px; background: #fff; color: #000; border: 2px solid #000; padding: 5px 9px; cursor: pointer; font-weight: 700; }
.tryit-btn::before { content: '▶ '; }
.tryit-btn[hidden] { display: none !important; }
.tryit-pair { display: inline-flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.tryit-pair[hidden] { display: none !important; }
.tryit-send { font: inherit; font-size: 14px; background: #fff; color: #000; border: 2px dashed #000; padding: 5px 9px; cursor: pointer; font-weight: 700; }
.tryit-send::before { content: '⇪ '; }
.tryit-send[aria-disabled="true"] { border-style: dotted; }
.tryit-said { font-size: 13px; overflow-wrap: anywhere; }
.tryit-said:empty { display: none; }
.tryit-said.bad { border: 2px solid #000; padding: 2px 6px; font-weight: 700; }
.tryit-live { border: 2px solid #000; padding: 5px 8px; margin: 6px 0; font-size: 14px; display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
.tryit-live button { font: inherit; font-size: 13px; background: #fff; color: #000; border: 2px solid #000; padding: 3px 8px; cursor: pointer; }
.tryit-live ol { flex-basis: 100%; margin: 4px 0 0; padding-left: 22px; font: 12px/1.5 ui-monospace, monospace; }
.tryit-live ol button { font-size: 12px; padding: 1px 6px; margin-left: 6px; }
@media (max-width: 520px) { #tryit { right: 0; bottom: 0; width: 100vw; max-height: 70vh; border-width: 3px 0 0; } }`;
  const S = { f: null, man: null, W: null, lab: null, gp: null, open: false, what: null, loading: null, dummy: 0 };
  let P = null;                                        // the panel's elements
  let styled = false;
  const css = () => { if (!styled) { styled = true; document.head.append(h('style', { text: CSS })); } };
  function panel() {
    if (P) return P;
    css();
    const touchBtn = (k, t) => h('button', { type: 'button', 'data-k': k, text: t });
    P = {};
    P.root = h('section', { id: 'tryit', role: 'region', 'aria-label': 'Try in game', hidden: '' },
      h('div', { class: 'thead' }, P.title = h('b', { text: 'Try in game' }), P.close = h('button', { type: 'button', text: 'Close' })),
      P.load = h('p', { class: 'tnow', text: 'Loading the Lab build and the emulator…' }),
      P.err = h('div', { class: 'terr', role: 'alert' }),
      P.canvas = h('canvas', { width: '304', height: '224', 'aria-label': 'The game' }),
      h('div', { class: 'trow' },
        P.pause = h('button', { type: 'button', text: 'Pause' }), P.step = h('button', { type: 'button', text: 'Step 1 frame', disabled: '' }),
        P.again = h('button', { type: 'button', text: 'Play again' }), P.loop = h('button', { type: 'button', 'aria-pressed': 'false', text: 'Loop' }),
        P.place = h('button', { type: 'button', text: 'Reset positions' }), P.sound = h('button', { type: 'button', text: 'Sound: off' }),
        P.own = h('button', { type: 'button', text: 'The game\'s own moves' })),
      P.now = h('div', { class: 'tnow', 'aria-live': 'polite', text: '-' }),
      P.stat = h('div', { class: 'tstat' }),
      P.touch = h('div', { class: 'ttouch' },
        h('div', { class: 'pad' }, h('span'), touchBtn('U', '↑'), h('span'), touchBtn('L', '←'), h('span'), touchBtn('R', '→'), h('span'), touchBtn('D', '↓'), h('span')),
        h('div', { class: 'btns' }, touchBtn('a', 'A attack'), touchBtn('b', 'B jump'), touchBtn('c', 'C special'), touchBtn('d', 'D fury'), touchBtn('s', 'START'))),
      h('p', { class: 'tkeys' }, 'Keys: ', h('kbd', { text: 'W' }), h('kbd', { text: 'A' }), h('kbd', { text: 'S' }), h('kbd', { text: 'D' }),
        ' stick, ', h('kbd', { text: 'U' }), ' A, ', h('kbd', { text: 'I' }), ' B jump, ', h('kbd', { text: 'O' }), ' C special, ', h('kbd', { text: 'P' }),
        ' D fury (arrows and Z X C V too), ', h('kbd', { text: 'Enter' }), ' START (the practice menu: dummies, AI, waves, MAX ready, boxes...), ', h('kbd', { text: '.' }),
        ' a frame while paused. Gamepad: d-pad or stick, face buttons A B C D. A from neutral plays the queue again; the sheet\'s slots play on their own inputs.'));
    document.body.append(P.root);
    P.close.onclick = () => show(false);
    P.again.onclick = () => { if (S.what && S.what.kind === 'queue') applyQueue(); };
    P.loop.onclick = () => { const on = P.loop.getAttribute('aria-pressed') !== 'true'; P.loop.setAttribute('aria-pressed', String(on)); P.loop.textContent = (on ? '✓ ' : '') + 'Loop'; if (S.what && S.what.kind === 'queue') { S.what.loop = on; applyQueue(); } };
    P.place.onclick = () => { if (S.lab) { S.lab.request(2); S.gp.stepFrames(1); } };
    P.own.onclick = () => { if (!S.lab) return; clearAll(); S.what = null; nowText('The game\'s own moves: nothing set from the page.'); };
    return P;
  }
  function show(on) { panel(); S.open = on; P.root.hidden = !on; if (!on && S.gp) S.gp.sound(false); if (on && S.gp) S.gp.fit(); }
  const err = t => { panel(); P.err.textContent = t || ''; };
  const nowText = t => { panel(); P.now.textContent = t; };
  function fitCanvas(cv) {                                  // a whole number of screen pixels per game pixel when it fits
    const avail = P.root.clientWidth - 24, s = avail >= cv.width ? Math.floor(avail / cv.width) : avail / cv.width;
    const k = Math.min(s, Math.max(1, Math.floor(innerHeight * 0.5 / cv.height)));
    cv.style.width = Math.round(cv.width * k) + 'px'; cv.style.height = Math.round(cv.height * k) + 'px';
  }

  // ---- f's Lab data without the emulator (the preview and Send to Player): lab.js, rom/lab-<f>.json, the Workshop ids --
  const ctxs = {};
  function ctxOf(f) {
    if (!ctxs[f]) ctxs[f] = (async () => {
      if (!window.ChainLab) await script('lab.js');
      const [man, W] = await Promise.all([get('rom/lab-' + f + '.json', 'json'), get('review/' + f + '_workshop.json', 'json').catch(() => null)]);
      return { f, man, W };
    })().catch(e => { delete ctxs[f]; throw e; });
    return ctxs[f];
  }

  // ---- loading the Lab build of f (once per page and fighter) ---------------------------------------------------------
  async function ensure(f) {
    panel(); show(true);
    if (S.f === f && S.lab) return S;
    if (S.loading && S.loading.f === f) return S.loading.p;
    const p = (async () => {
      P.load.hidden = false; P.load.textContent = 'Loading the Lab build of ' + f.toUpperCase() + ' and the emulator…'; err('');
      const { man, W } = await ctxOf(f);
      await script('gameplay.js'); await script('core.js');
      P.load.textContent = `Loading the Lab build of ${f.toUpperCase()} (${(man.size / 1048576).toFixed(0)} MB) and the emulator…`;
      const [bios, rom] = await Promise.all([get('neogeo.zip'), get(man.rom)]);
      if (S.gp) S.gp.stop();
      const lab = await window.ChainLab.Lab.create(window.GeoCore, { bios, rom }, man.layout);
      const dn = ['ryo', 'terry', 'ralf'].find(n => n !== f && man.fighters.includes(n)) || man.fighters.find(n => n !== f);
      Object.assign(S, { f, man, W, lab, dummy: man.fighters.indexOf(dn) });
      lab.boot(man.id, S.dummy, null);
      S.gp = window.GamePlay.attach({
        lab, canvas: P.canvas, fit: fitCanvas, soundBtn: P.sound, pauseBtn: P.pause, stepBtn: P.step, touch: P.touch, statusEl: P.stat,
        escPause: false, running: () => S.open, keyActive: () => S.open, status: statusLine });
      P.title.textContent = `Try in game: ${f.toUpperCase()} (Lab build ${man.layout.version}, ${man.anims.length} animations)`;
      P.load.hidden = true;
      window.tryit.ready = true;
      return S;
    })();
    S.loading = { f, p };
    try { return await p; } catch (e) { P.load.textContent = 'Could not load the Lab build: ' + e.message; throw e; } finally { S.loading = null; }
  }
  function statusLine(paused) {
    const lab = S.lab; if (!lab) return '';
    const cur = lab.tryCur(), c = lab.combo();
    const play = cur === 0xFFFF ? 'nothing from the page' : describe(cur) + (S.what && S.what.kind === 'queue' ? ` (${lab.tryPos() + 1} of ${S.what.entries.length})` : '');
    return `P1 ${lab.stateName(0)} · playing: ${play} · combo ${c.hits} hits ${c.dmg} damage · load: ${lab.tryStatus()}${paused ? ' · PAUSED' : ''}`;
  }


  // ---- pieces -> lab entries (c = {f, man, W}: the preview's state S, or ctxOf(f) for a Send) ---------------------------
  const CL = () => window.ChainLab;
  function entry(p, c) {
    c = c || S;
    const s = String(p).trim().replace(/^anim-/, '');
    if (/^S-\d+$/.test(s)) {
      const w = c.W && (c.W.specials || []).find(x => x.id === s);
      if (!w) throw new Error(s + ': not an unlocked special of ' + c.f);
      const k = c.man.pool.indexOf(w.input);
      if (k < 0) throw new Error(`${s} (${w.input}) is not in the Lab build's pool`);
      return CL().LE_SPEC | k;
    }
    if (/^T-\d+$/.test(s)) {
      const w = c.W && (c.W.throws || []).find(x => x.id === s);
      const k = w ? c.man.throws.indexOf(w.move) : -1;
      if (k < 0) throw new Error(s + ': not a throw of the Lab build');
      return CL().LE_THROW | k;
    }
    const x = s.replace(/^\$/, '').toUpperCase();
    if (!/^[0-9A-F]+$/.test(x) || !c.man.anims.includes(x)) throw new Error('$' + x + ': not an animation of the Lab build');
    return parseInt(x, 16);
  }
  function describe(e, c) {
    c = c || S;
    if (e & 0x2000) return 'throw ' + (c.man.throws[e & 0xFF] || e & 0xFF);
    if (e & 0x1000) { const inp = c.man.pool[e & 0xFF], w = c.W && (c.W.specials || []).find(x => x.input === inp); return (w ? w.id + ' ' : '') + inp; }
    return hex(e);
  }
  function settle(n) {                               // step until the game answers (taken / pending / refused), up to
    let st = 'sent';                                  // half a second: only a refusal or no answer at all is an error
    for (let i = 0; i < 30 && st === 'sent'; i++) { S.gp.stepFrames(1); st = S.lab.tryStatus(); }   // (n: unused, kept for callers)
    if (st.startsWith('refused') || st === 'sent') throw new Error('The game ' + (st === 'sent' ? 'did not answer' : st));
  }
  // the live config: ONE TRY blob (lab.js encodeTry, the same bytes the server / the Player send), load 6
  function send(cfg) { S.lab.installTry(CL().encodeTry(Object.assign({ fighter: S.man.id }, cfg)), true); }   // (the preview: apply now)
  function clearAll() {                                    // no queue, no slot, the ROM's tree back (load 2)
    send({}); S.gp.stepFrames(1);
    if (S.chainPushed) { S.lab.installChain(S.man.id, null); S.gp.stepFrames(1); S.chainPushed = false; }
  }
  function applyQueue() {
    const w = S.what;
    send({ queue: w.entries, now: true, loop: w.loop });
    settle(2);
    nowText(`Queue: ${w.entries.map(e => describe(e)).join(' > ')}${w.loop ? ' (loop)' : ''}. It plays now; A from neutral plays it again.`);
  }

  // ---- what a queue / a sheet is in TRY terms (the preview and the Send build the same cfg from these) ----------------
  function queueEntries(c, pieces) {
    const entries = pieces.map(p => entry(p, c));
    if (!entries.length) throw new Error('nothing to play');
    if (entries.some(e => e & 0x2000)) throw new Error('a throw plays only in a grab slot (the arbitration sheet\'s "Grab")');
    if (entries.length > CL().LQ_MAX) throw new Error(`at most ${CL().LQ_MAX} back to back`);
    return entries;
  }
  const loopOn = () => !!P && P.loop.getAttribute('aria-pressed') === 'true';
  // a sheet's slots -> {slots: {slot id: [entries]}, bad: [what was left out, why]}
  function sheetSlots(c, sh) {
    const slots = {}, bad = [];
    for (const [k, ps] of Object.entries(sh.slots || {})) {
      if (!ps || !ps.length) continue;
      if (!CL().LAB_SLOTS.includes(k)) { bad.push(k + ' (no such slot in the game)'); continue; }
      const es = [];
      for (const p of ps) { try { es.push(entry(p, c)); } catch (e) { bad.push(k + ': ' + e.message); } }
      if (es.length) slots[k] = es.slice(0, CL().LO_MAX);
    }
    return { slots, bad };
  }
  // the sheet's chain (presses: [[pieces]] per press) -> {bytes: a chain override (load 5), or null = the ROM's chain; text}
  function chainOf(c, presses) {
    if (!presses || !presses.length) return { bytes: null, text: 'chain: the ROM\'s' };
    const C = c.man.chain, fe = C.fighter, rules = C.rules;
    const byHex = {}; for (const [m, x] of Object.entries(c.man.moves)) (byHex[x] = byHex[x] || []).push(m);
    const moves = [];
    for (let i = 0; i < presses.length; i++) {
      const ps = presses[i] || [];
      if (ps.length !== 1) return { bytes: null, text: `chain: press ${i + 1} ${ps.length ? 'plays ' + ps.length + ' pieces' : 'is empty'}: the ROM's chain kept` };
      const x = String(ps[0]).replace(/^anim-/, '').replace(/^\$/, '').toUpperCase(), m = (byHex[x] || []).find(m_ => fe.has.includes(m_) && CL().MOVE_NAMES.includes(m_));
      if (!m) return { bytes: null, text: `chain: press ${i + 1} ($${x}) is not one of ${c.f}'s brawler moves: the ROM's chain kept` };
      moves.push(m);
    }
    const arch = Object.keys(rules.lengths).find(a => rules.lengths[a] === moves.length);
    if (!arch) return { bytes: null, text: `chain: ${moves.length} presses (the archetypes have ${Object.values(rules.lengths).join(' / ')}): the ROM's chain kept` };
    const base = CL().specOf(fe, rules, C.retime_rom);
    const spec = Object.assign({}, base, { archetype: arch, links: moves.slice(0, -1), finishers: Object.assign({}, base.finishers, { neutral: moves[moves.length - 1] }), hitstop: null });
    if (CL().sameChain(spec, base)) return { bytes: null, text: 'chain: the same as the ROM\'s' };
    const t = CL().chainTree(fe, spec, rules);
    return { bytes: CL().encodeOverride(CL().encodeTree(t, C.ba, fe.has, fe.default.entries), CL().retimeRows(C, fe, spec)), text: `chain: ${moves.join(' > ')}` };
  }

  // ---- the preview API ----------------------------------------------------------------------------------------------
  async function queue(f, pieces, opt) {
    await ensure(f); err('');
    try {
      const entries = queueEntries(S, pieces);
      S.what = { kind: 'queue', entries, loop: (opt && opt.loop !== undefined) ? !!opt.loop : loopOn() };
      if (S.lab.stateName(0) !== 'IDLE' && S.lab.stateName(0) !== 'WALK') { S.lab.request(2); S.gp.stepFrames(1); }
      applyQueue();
    } catch (e) { err('Not played: ' + e.message); }
  }
  async function sheet(f, sh) {
    await ensure(f); err('');
    try {
      const { slots, bad } = sheetSlots(S, sh);
      clearAll();
      send({ slots }); settle(2);
      const ch = chainOf(S, sh.chain);
      if (ch.bytes) { S.lab.installChain(S.man.id, ch.bytes); S.gp.stepFrames(1); S.chainPushed = true; }
      S.what = { kind: 'sheet', slots };
      const names = Object.keys(slots);
      nowText(`Sheet: ${names.length} slot${names.length === 1 ? '' : 's'} set (${names.map(k => k + ' = ' + slots[k].map(e => describe(e)).join(' > ')).join('; ') || 'none'}); ${ch.text}${ch.bytes ? ' (pushed, load 5)' : ''}.` +
        (bad.length ? ' Left out: ' + bad.join('; ') + '.' : ''));
    } catch (e) { err('Not applied: ' + e.message); }
  }

  // ---- Send to Player: the fighter's live config on the server (docs/feedback.md "Character Lab") -----------------------
  const API = 'feedback-api/lab/';
  const LV = {};                                           // f -> {rec: the live record in full (null: none, undefined: not read), err, lines, timer}
  let me = null;                                           // GET lab/me: {user, role}
  const whoami = () => me = me || fetch(API + 'me', { cache: 'no-store', credentials: 'same-origin' })
    .then(r => r.ok ? r.json() : { user: null, role: null, status: r.status }, () => ({ user: null, role: null, status: 0 }));
  const isAdmin = w => !w.user || w.role === 'admin';      // (not known: the server decides, a 403 says it)
  const b64 = u8 => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
  const unb64 = s => Uint8Array.from(atob(s), ch => ch.charCodeAt(0));
  const sha256 = async u8 => [...new Uint8Array(await crypto.subtle.digest('SHA-256', u8))].map(x => x.toString(16).padStart(2, '0')).join('');
  const when = iso => iso ? iso.slice(0, 16).replace('T', ' ') + ' UTC' : '?';
  const slot = f => LV[f] = LV[f] || { rec: undefined, err: null, lines: new Set(), timer: null };
  async function loadLive(f) {
    const L = slot(f);
    try {
      const r = await fetch(API + 'config/' + f, { cache: 'no-store', credentials: 'same-origin' });
      if (r.status === 404) L.rec = null;
      else if (!r.ok) throw new Error('HTTP ' + r.status);
      else L.rec = await r.json();
      L.err = null;
    } catch (e) { L.err = e.message; }
    drawLines(f);
    return L;
  }
  async function poll(f) {                                 // the line follows other pages / Players (15 s, If-None-Match)
    const L = slot(f);
    if (document.hidden || L.rec === undefined) return;
    try {
      const r = await fetch(API + 'config/' + f + '/hash', { cache: 'no-store', credentials: 'same-origin', headers: L.rec ? { 'If-None-Match': '"' + L.rec.hash + '"' } : {} });
      if (r.status === 200) { const j = await r.json(); if (!L.rec || j.version !== L.rec.version) await loadLive(f); }
      else if (r.status === 404 && L.rec) await loadLive(f);
    } catch (e) { /* offline: the next poll */ }
  }

  /* the Send: what = {queue: pieces, loop} | {sheet: {slots, chain}} | {chain: {bytes, fighter, text, entry}} (or a function
     giving it); el = where it says what happened. -> the server's answer (the new head), or null */
  async function sendTo(f, what, el) {
    const say = (t, bad) => { if (el) { el.textContent = t; el.classList.toggle('bad', !!bad); } };
    const who = await whoami();
    if (!isAdmin(who)) { say(`Send to Player needs the Oros admin role (signed in as ${who.user}, role ${who.role || 'none'}): the Player only takes configs written by an admin.`, true); return null; }
    say('Sending…');
    try {
      if (typeof what === 'function') what = what();
      const c = what.chain ? null : await ctxOf(f);
      const L = slot(f).rec !== undefined && !slot(f).err ? slot(f) : await loadLive(f);
      if (L.err) throw new Error('the live config could not be read (' + L.err + ')');
      let cur = null;
      if (L.rec) try { cur = CL().liveParts(unb64(L.rec.blob)); } catch (e) { cur = null; }   // (a desktop blob of another shape: replaced whole)
      const prev = (L.rec && L.rec.json && L.rec.json.lab_try) || {};
      let tryBlob, chain, tj = prev.try || null, cj = prev.chain || null, said;
      if (what.queue) {
        const entries = queueEntries(c, what.queue), loop = !!what.loop;
        tryBlob = CL().encodeTry({ fighter: c.man.id, queue: entries, now: true, loop });
        chain = cur && cur.chain && cur.tryBlob[3] === c.man.id ? cur.chain : null;
        tj = { kind: 'queue', pieces: what.queue.map(String), loop };
        said = `the queue ${entries.map(e => describe(e, c)).join(' > ')}${loop ? ' (loop)' : ''}` + (chain ? ', the live chain kept' : '');
      } else if (what.sheet) {
        const { slots, bad } = sheetSlots(c, what.sheet), ch = chainOf(c, what.sheet.chain);
        tryBlob = CL().encodeTry({ fighter: c.man.id, slots });
        chain = ch.bytes;
        tj = Object.assign({ kind: 'sheet', slots: what.sheet.slots || {} }, bad.length ? { left_out: bad } : {});
        cj = ch.bytes ? { kind: 'sheet', presses: what.sheet.chain, text: ch.text } : null;
        said = `the sheet, ${Object.keys(slots).length} slot${Object.keys(slots).length === 1 ? '' : 's'}; ${ch.text}` + (bad.length ? '; left out: ' + bad.join('; ') : '');
      } else if (what.chain) {
        const w = what.chain;
        tryBlob = cur ? Uint8Array.from(cur.tryBlob) : CL().encodeTry({ fighter: w.fighter });
        tryBlob[3] = w.fighter;                                     // the chain's retime rows name this fighter (the Player: -> the slot)
        chain = w.bytes;
        cj = { kind: 'chain tool', text: w.text, entry: w.entry || null };
        said = 'the chain ' + w.text + (cur ? ', the live slots / queue kept' : '');
      } else throw new Error('nothing to send');
      const blob = CL().liveBlob(tryBlob, chain);
      const body = { blob: b64(blob), hash: await sha256(blob), note: ('Send to Player: ' + said).slice(0, 300),
        json: { name: f, lab_try: { page: location.pathname.split('/').pop() || 'index.html', try: tj, chain: chain ? cj : null } } };
      const hd = { 'Content-Type': 'application/json' };
      if (L.rec) hd['If-Match'] = '"' + L.rec.hash + '"';
      const r = await fetch(API + 'config/' + f, { method: 'PUT', credentials: 'same-origin', headers: hd, body: JSON.stringify(body) });
      const j = await r.json().catch(() => ({}));
      if (r.status === 412) {
        await loadLive(f);
        const n = j.current || slot(f).rec || {};
        say(`Not sent: someone else changed ${f.toUpperCase()}'s live config meanwhile (now r${n.version} by ${n.by}, ${when(n.updated)}). This page has reloaded it: check it, then press Send again.`, true);
        return null;
      }
      if (r.status === 403) { say('Not sent: Send to Player needs the Oros admin role (' + (j.error || 'refused') + ').', true); return null; }
      if (r.status === 401) { say('Not sent: sign in again (the Oros login), then press Send.', true); return null; }
      if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      await loadLive(f);
      say(j.changed ? `Sent: ${f.toUpperCase()} live config r${j.version} (${said}). The Player applies it at neutral.`
                    : `Unchanged: ${f.toUpperCase()}'s live config is already this (r${j.version}).`);
      return j;
    } catch (e) { say('Not sent: ' + e.message, true); return null; }
  }
  async function revert(f, rev, el) {
    const say = t => { if (el && el._said) { el._said.textContent = t; } };
    const who = await whoami();
    if (!isAdmin(who)) { say(`Revert needs the Oros admin role (signed in as ${who.user}).`); return null; }
    if (!confirm(`Make ${f.toUpperCase()}'s live config revision ${rev} again? (a new revision; nothing is deleted)`)) return null;
    try {
      const r = await fetch(API + 'config/' + f + '/revert', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ rev, note: 'revert to rev ' + rev + ' (web)' }) });
      const j = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      await loadLive(f);
      say(`Reverted: r${j.version} = r${rev}'s config. The Player applies it at neutral.`);
      return j;
    } catch (e) { say('Not reverted: ' + e.message); return null; }
  }

  // ---- the "Live config" line --------------------------------------------------------------------------------------
  function liveLine(f) {
    css();
    const L = slot(f);
    const el = h('div', { class: 'tryit-live' });
    el._said = h('span', { class: 'tryit-said', role: 'status', 'aria-live': 'polite' });
    L.lines.add(el);
    if (L.rec === undefined) { if (!L.loading) L.loading = loadLive(f).finally(() => { L.loading = null; }); drawLine(f, el); }
    else drawLine(f, el);
    if (!L.timer) L.timer = setInterval(() => poll(f), 15000);
    return el;
  }
  function drawLines(f) { for (const el of slot(f).lines) drawLine(f, el); }
  function drawLine(f, el) {
    const L = slot(f), r = L.rec;
    const kids = [h('b', { text: 'Live config (the Player):' })];
    if (L.err) kids.push(h('span', { text: 'not read (' + L.err + ')' }));
    else if (r === undefined) kids.push(h('span', { text: 'reading…' }));
    else if (r === null) kids.push(h('span', { text: 'none yet for ' + f.toUpperCase() + ' (the Player plays the game\'s own moves)' }));
    else {
      kids.push(h('span', { class: 'lrev', text: `r${r.version}, updated ${when(r.updated)} by ${r.by}` + (r.reverted_from ? ` (revision ${r.reverted_from} again)` : '') }));
      const list = h('ol', { hidden: '', reversed: '' });
      const hist = h('button', { type: 'button', 'aria-expanded': 'false', text: 'History' });
      hist.onclick = async () => {
        const open = list.hidden; list.hidden = !open; hist.setAttribute('aria-expanded', String(open));
        if (!open) return;
        list.replaceChildren(h('li', { text: 'reading…' }));
        try {
          const j = await get(API + 'config/' + f + '/history', 'json');
          list.replaceChildren(...j.revisions.slice().reverse().map(x => h('li', { value: String(x.version) },
            `r${x.version} · ${when(x.updated)} · ${x.by} · ${x.size} B · ${x.hash.slice(0, 12)}` + (x.reverted_from ? ` · = r${x.reverted_from}` : '') + (x.note ? ' · ' + x.note : ''),
            x.version === r.version ? h('b', { text: ' (live)' }) : h('button', { type: 'button', text: 'Revert to r' + x.version, onclick: () => revert(f, x.version, el) }))));
        } catch (e) { list.replaceChildren(h('li', { text: 'History not read: ' + e.message })); }
      };
      kids.push(hist);
      if (r.version > 1) kids.push(h('button', { type: 'button', text: 'Revert to r' + (r.version - 1), onclick: () => revert(f, r.version - 1, el) }));
      kids.push(list);
    }
    kids.push(el._said);
    el.replaceChildren(...kids);
  }

  function button(f, label, fn, sendWhat) {
    css();
    const b = h('button', { type: 'button', class: 'tryit-btn', text: label || 'Try in game', hidden: '' });
    b.onclick = e => { e.stopPropagation(); fn(); };
    if (!sendWhat) { has(f).then(ok => { if (ok) b.hidden = false; }); return b; }
    b.hidden = false;
    const said = h('span', { class: 'tryit-said', role: 'status', 'aria-live': 'polite' });
    const sb = h('button', { type: 'button', class: 'tryit-send', text: 'Send to Player', title: `Make it ${f.toUpperCase()}'s live config: the Player's Character lab applies it at neutral` });
    sb.onclick = async e => { e.stopPropagation(); sb.disabled = true; try { await sendTo(f, sendWhat, said); } finally { sb.disabled = false; } };
    whoami().then(w => { if (!isAdmin(w)) { sb.setAttribute('aria-disabled', 'true'); sb.title = 'Needs the Oros admin role'; } });
    const pair = h('span', { class: 'tryit-pair', hidden: '' }, b, sb, said);
    has(f).then(ok => { if (ok) pair.hidden = false; });
    return pair;
  }
  window.TryIt = { has, button, queue, sheet, entry: (p, c) => entry(p, c), show, send: sendTo, liveLine, loop: loopOn, ctx: ctxOf };
  window.tryit = { get state() { return S; }, get lab() { return S.lab; }, get gp() { return S.gp; }, ready: false, get live() { return LV; } };
})();
