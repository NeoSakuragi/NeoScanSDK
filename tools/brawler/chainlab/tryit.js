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
 * window.tryit (tests): {state, lab, gp, ready} */
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
@media (max-width: 520px) { #tryit { right: 0; bottom: 0; width: 100vw; max-height: 70vh; border-width: 3px 0 0; } }`;
  const S = { f: null, man: null, W: null, lab: null, gp: null, open: false, what: null, loading: null, dummy: 0 };
  let P = null;                                        // the panel's elements
  function panel() {
    if (P) return P;
    document.head.append(h('style', { text: CSS }));
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

  // ---- loading the Lab build of f (once per page and fighter) ---------------------------------------------------------
  async function ensure(f) {
    panel(); show(true);
    if (S.f === f && S.lab) return S;
    if (S.loading && S.loading.f === f) return S.loading.p;
    const p = (async () => {
      P.load.hidden = false; P.load.textContent = 'Loading the Lab build of ' + f.toUpperCase() + ' and the emulator…'; err('');
      await script('lab.js'); await script('gameplay.js'); await script('core.js');
      const [man, W] = await Promise.all([get('rom/lab-' + f + '.json', 'json'), get('review/' + f + '_workshop.json', 'json').catch(() => null)]);
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

  // ---- pieces -> lab entries ------------------------------------------------------------------------------------------
  const CL = () => window.ChainLab;
  function entry(p) {
    const s = String(p).trim().replace(/^anim-/, '');
    if (/^S-\d+$/.test(s)) {
      const w = S.W && (S.W.specials || []).find(x => x.id === s);
      if (!w) throw new Error(s + ': not an unlocked special of ' + S.f);
      const k = S.man.pool.indexOf(w.input);
      if (k < 0) throw new Error(`${s} (${w.input}) is not in the Lab build's pool`);
      return CL().LE_SPEC | k;
    }
    if (/^T-\d+$/.test(s)) {
      const w = S.W && (S.W.throws || []).find(x => x.id === s);
      const k = w ? S.man.throws.indexOf(w.move) : -1;
      if (k < 0) throw new Error(s + ': not a throw of the Lab build');
      return CL().LE_THROW | k;
    }
    const x = s.replace(/^\$/, '').toUpperCase();
    if (!/^[0-9A-F]+$/.test(x) || !S.man.anims.includes(x)) throw new Error('$' + x + ': not an animation of the Lab build');
    return parseInt(x, 16);
  }
  function describe(e) {
    if (e & 0x2000) return 'throw ' + (S.man.throws[e & 0xFF] || e & 0xFF);
    if (e & 0x1000) { const inp = S.man.pool[e & 0xFF], w = S.W && (S.W.specials || []).find(x => x.input === inp); return (w ? w.id + ' ' : '') + inp; }
    return hex(e);
  }
  function settle(n) { S.gp.stepFrames(n || 2); const st = S.lab.tryStatus(); if (st !== 'taken') throw new Error('The game ' + st); }
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
    nowText(`Queue: ${w.entries.map(describe).join(' > ')}${w.loop ? ' (loop)' : ''}. It plays now; A from neutral plays it again.`);
  }

  // ---- the API ----------------------------------------------------------------------------------------------------
  async function queue(f, pieces, opt) {
    await ensure(f); err('');
    try {
      const entries = pieces.map(entry);
      if (!entries.length) throw new Error('nothing to play');
      if (entries.some(e => e & 0x2000)) throw new Error('a throw plays only in a grab slot (the arbitration sheet\'s "Grab")');
      if (entries.length > CL().LQ_MAX) throw new Error(`at most ${CL().LQ_MAX} back to back`);
      S.what = { kind: 'queue', entries, loop: (opt && opt.loop !== undefined) ? !!opt.loop : P.loop.getAttribute('aria-pressed') === 'true' };
      if (S.lab.stateName(0) !== 'IDLE' && S.lab.stateName(0) !== 'WALK') { S.lab.request(2); S.gp.stepFrames(1); }
      applyQueue();
    } catch (e) { err('Not played: ' + e.message); }
  }
  // the sheet's chain (presses: [[pieces]] per press) -> a chain override when every press is one brawler move; -> a note
  function chainOverride(presses) {
    const C = S.man.chain, fe = C.fighter, rules = C.rules;
    const byHex = {}; for (const [m, x] of Object.entries(S.man.moves)) (byHex[x] = byHex[x] || []).push(m);
    const moves = [];
    for (let i = 0; i < presses.length; i++) {
      const ps = presses[i] || [];
      if (ps.length !== 1) return `chain: press ${i + 1} ${ps.length ? 'plays ' + ps.length + ' pieces' : 'is empty'}: the ROM's chain kept`;
      const x = String(ps[0]).replace(/^anim-/, '').replace(/^\$/, '').toUpperCase(), m = (byHex[x] || []).find(m_ => fe.has.includes(m_) && CL().MOVE_NAMES.includes(m_));
      if (!m) return `chain: press ${i + 1} ($${x}) is not one of ${S.f}'s brawler moves: the ROM's chain kept`;
      moves.push(m);
    }
    const arch = Object.keys(rules.lengths).find(a => rules.lengths[a] === moves.length);
    if (!arch) return `chain: ${moves.length} presses (the archetypes have ${Object.values(rules.lengths).join(' / ')}): the ROM's chain kept`;
    const base = CL().specOf(fe, rules, C.retime_rom);
    const spec = Object.assign({}, base, { archetype: arch, links: moves.slice(0, -1), finishers: Object.assign({}, base.finishers, { neutral: moves[moves.length - 1] }), hitstop: null });
    if (CL().sameChain(spec, base)) return 'chain: the same as the ROM\'s';
    const t = CL().chainTree(fe, spec, rules);
    const bytes = CL().encodeOverride(CL().encodeTree(t, C.ba, fe.has, fe.default.entries), CL().retimeRows(C, fe, spec));
    S.lab.installChain(S.man.id, bytes); S.gp.stepFrames(1); S.chainPushed = true;
    return `chain: ${moves.join(' > ')} (pushed, load 5)`;
  }
  async function sheet(f, sh) {
    await ensure(f); err('');
    try {
      const slots = {}, bad = [];
      for (const [k, ps] of Object.entries(sh.slots || {})) {
        if (!ps || !ps.length) continue;
        if (!CL().LAB_SLOTS.includes(k)) { bad.push(k + ' (no such slot in the game)'); continue; }
        const es = [];
        for (const p of ps) { try { es.push(entry(p)); } catch (e) { bad.push(k + ': ' + e.message); } }
        if (es.length) slots[k] = es.slice(0, CL().LO_MAX);
      }
      clearAll();
      send({ slots }); settle(2);
      const ch = sh.chain && sh.chain.length ? chainOverride(sh.chain) : 'chain: the ROM\'s';
      S.what = { kind: 'sheet', slots };
      const names = Object.keys(slots);
      nowText(`Sheet: ${names.length} slot${names.length === 1 ? '' : 's'} set (${names.map(k => k + ' = ' + slots[k].map(describe).join(' > ')).join('; ') || 'none'}); ${ch}.` +
        (bad.length ? ' Left out: ' + bad.join('; ') + '.' : ''));
    } catch (e) { err('Not applied: ' + e.message); }
  }
  function button(f, label, fn) {
    const b = h('button', { type: 'button', class: 'tryit-btn', text: label || 'Try in game', hidden: '' });
    b.onclick = e => { e.stopPropagation(); fn(); };
    has(f).then(ok => { if (ok) b.hidden = false; });
    return b;
  }
  window.TryIt = { has, button, queue, sheet, entry: p => entry(p), show };
  window.tryit = { get state() { return S; }, get lab() { return S.lab; }, get gp() { return S.gp; }, ready: false };
})();
