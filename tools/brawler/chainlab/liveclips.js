/* LIVE CLIPS in the Assembly (Bruno 2026-10-10: "take the rendering of animations and specials in the assembly to the next
 * level"; "pre-rendering is no good: I can't adjust parameters"): every clip of the sheet is played by the real engine in
 * the page, again ~300 ms after any change to its pick, its knobs or the chain timing. The simulation runs in a Web Worker
 * (liveclips_worker.js + liveclips_core.js: its own core with the Character Lab shell + the fighter's pack, the same files
 * as "Try in game" and the Player); the TRY blob of each clip is made here with tryit.js's own pieces -> entries, knobs ->
 * rows, chain -> chain section (one encoder: lab.js encodeTry). Nothing is saved or sent by a clip.
 *   const LC = await LiveClips.attach(f)            -> null when f has no pack the shell loads (the static clips stay)
 *   const el = LC.clip({key, label, req: () => spec, cls: () => text})   a figure: the clip, its frame-data strip, its gap toggle
 *   LC.refresh(key | null)                          re-simulate that clip (null: every clip) ~300 ms later, if its request changed
 *   LC.forget(key)                                  its figure left the page (the Assembly's row collapsed): not simulated
 *   o.compact (the Assembly's rows, 2026-10-10 "cut the fluff out"): no title, ONE line of frame data ("8/18/20 f · 1 hit ·
 *   2 dmg · reach 93"; the full text in its tooltip), the canvas fits the width (and ~1/3 of a phone screen), a short bar,
 *   two tiny controls: gap and boxes
 *   spec = {kind: 'slot', slot, pieces, knobs, sheet} | {kind: 'press', k, sheet} | {kind: 'chain', sheet}   (sheet:
 *          arbitrage.js sheetNow(): {slots, knobs, chain, timing}); pieces null = the game's own move on that input
 * The HITBOX toggle (one for the page, LC.boxesButton()): the hit test's attack boxes (solid) and hurt boxes (dashed) on
 * every clip, the active frames tagged. E-ink: black on white, line style and words, never colour alone.
 * window.liveclips (tests): {stats, clips, LC} */
(function () {
  'use strict';
  const h = (t, a, ...kids) => {
    const e = document.createElement(t);
    for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== undefined) e.setAttribute(k, v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c);
    return e;
  };
  const FMS = 1000 / 59.18, NEAR = 44, FAR = 150, DEBOUNCE = 300;
  const PHONE = matchMedia('(pointer: coarse)').matches || innerWidth < 600;
  const STICK = { fin_fwd: 'R', fin_up: 'U', fin_down: 'D', fin_df: 'DR', fin_back: 'L' };
  const TAP = { ff: ['R', 'R'], dd: ['D', 'D'], uu: ['U', 'U'], du: ['D', 'U'] };
  const JUMP = [['b', 2], ['', 10]];
  // the input that plays a slot (P1 faces the dummy, on his right: forward = R): main.c read_player's terms
  function scriptOf(slot) {
    let m;
    if ((m = /^bz_(ff|dd|uu|du)$/.exec(slot))) { const [a, b] = TAP[m[1]]; return [[a, 2], ['', 2], [b + 'a', 3]]; }
    if ((m = /^air_bz_(ff|dd|uu|du)$/.exec(slot))) { const [a, b] = TAP[m[1]]; return JUMP.concat([[a, 2], ['', 2], [b + 'a', 3]]); }
    if (slot === 'sp_c') return [['c', 3]];
    if (slot === 'sp_fc') return [['Rc', 3]];
    if (slot === 'sp_dc') return [['Dc', 3]];
    if (slot === 'air_sp_c') return JUMP.concat([['c', 3]]);
    if (slot === 'air_sp_fc') return JUMP.concat([['Rc', 3]]);
    if (slot === 'air_sp_dc') return JUMP.concat([['Dc', 3]]);
    if (slot === 'air_a') return JUMP.concat([['a', 3]]);
    if (slot === 'air_da') return JUMP.concat([['Da', 3]]);
    if (slot === 'grab_hit') return [['R', 30], ['', 4], ['a', 2]];
    if (slot === 'grab_fin') return [['R', 30], ['', 4], ['a', 2], ['', 16], ['a', 2], ['', 16], ['a', 2], ['', 16], ['a', 2]];
    if (slot === 'grab_fwd') return [['R', 30], ['', 4], ['Rc', 3]];
    if (slot === 'grab_back') return [['R', 30], ['', 4], ['Lc', 3]];
    if (slot === 'fury') return [['d', 3]];
    if (slot === 'max') return [['Dd', 3]];
    return null;
  }
  const KT = { R: '→', L: '←', U: '↑', D: '↓', a: 'A', b: 'B', c: 'C', d: 'D' };
  const keysText = k => [...k].map(ch => KT[ch] || ch).join('+');
  const INPUT_TEXT = s => ({ sp_c: 'C', sp_fc: 'forward + C', sp_dc: 'down + C', fury: 'D', max: 'down + D (MAX ready)' })[s] || null;

  const CSS = `
.lclip { margin: 0; border: 2px solid #000; padding: 4px; display: flex; flex-direction: column; gap: 4px; background: #fff; color: #000; max-width: 100%; box-sizing: border-box; }
.lclip .lchead { display: flex; flex-wrap: wrap; gap: 4px 8px; align-items: center; font-size: 13px; }
.lclip .lchead b { flex: 1 1 auto; font-size: 13px; overflow-wrap: anywhere; }
.lclip .lchead button { font: inherit; font-size: 12px; background: #fff; color: #000; border: 2px solid #000; padding: 2px 7px; cursor: pointer; }
.lclip canvas.lpic { display: block; image-rendering: pixelated; image-rendering: crisp-edges; cursor: pointer; max-width: 100%; height: auto; border: 1px solid #000; background: #fff; }
.lclip .lstate { font: 12px/1.3 ui-monospace, monospace; min-height: 1.3em; }
.lclip .lstate.busy::before { content: "\\21BB  "; }
.lclip .lstate.bad { border: 2px solid #000; padding: 2px 6px; font-weight: 700; }
.lclip canvas.lbar { display: block; width: 100%; height: 34px; }
.lclip .lfd { font: 12px/1.45 ui-monospace, monospace; overflow-wrap: anywhere; margin: 0; }
.lclip .lfd b { font-weight: 700; }
.lclip[data-busy="1"] canvas.lpic { opacity: .55; }
.lclip-boxes { font: inherit; font-size: 14px; background: #fff; color: #000; border: 2px solid #000; padding: 5px 9px; cursor: pointer; font-weight: 700; }
.lclip-boxes[aria-pressed="true"] { background: #000; color: #fff; }
.lclip-legend { font-size: 13px; }
.lclip.compact { border-width: 1px; padding: 2px; gap: 2px; }
.lclip.compact .lchead { gap: 3px; font-size: 12px; justify-content: flex-end; }
.lclip.compact .lchead button { font-size: 12px; padding: 1px 6px; border-width: 1px; }
.lclip.compact .lchead button[aria-pressed="true"] { background: #000; color: #fff; }
.lclip.compact canvas.lpic { align-self: center; }
.lclip.compact .lstate { font-size: 12px; min-height: 0; }
.lclip.compact .lstate:empty { display: none; }
.lclip.compact canvas.lbar { height: 20px; }
.lclip.compact .lfd { font-size: 13px; line-height: 1.3; font-weight: 700; }`;
  let styled = false;
  const css = () => { if (!styled) { styled = true; document.head.append(h('style', { text: CSS })); } };

  // ---- the worker (one per page) ------------------------------------------------------------------------------------
  let W = null, wready = null, wkey = null, wseq = 0;
  const waiting = new Map();
  function worker() {
    if (W) return W;
    W = new Worker('liveclips_worker.js');
    W.onmessage = ev => {
      const m = ev.data;
      if (m.type === 'ready' || m.type === 'error') { const w = waiting.get('init:' + m.key); if (w) { waiting.delete('init:' + m.key); m.type === 'ready' ? w.ok(m) : w.ko(new Error(m.error)); } }
      else if (m.type === 'clip') { const w = waiting.get(m.id); if (w) { waiting.delete(m.id); w.ok(m.result); } }
    };
    W.onerror = e => { for (const [, w] of waiting) w.ko(new Error('the simulation worker failed: ' + (e.message || 'error'))); waiting.clear(); };
    return W;
  }
  function init(c) {
    const key = c.man.shell.sha256 + ':' + c.man.pack.sha256;
    if (wready && wkey === key) return wready;
    wkey = key;
    const dn = ['ryo', 'terry', 'ralf'].find(n => n !== c.f && c.man.fighters.includes(n)) || c.man.fighters.find(n => n !== c.f && n !== 'slot');
    wready = new Promise((ok, ko) => {
      waiting.set('init:' + key, { ok, ko });
      worker().postMessage({ type: 'init', key, shellUrl: c.man.shell.url, shellSha: c.man.shell.sha256, pack: c.man.packBytes.slice().buffer, slot: c.man.id, dummy: c.man.fighters.indexOf(dn) });
    });
    wready.catch(() => { wready = null; });
    return wready;
  }
  const simulate = req => new Promise((ok, ko) => {
    const id = 'c' + (++wseq);
    waiting.set(id, { ok, ko });
    worker().postMessage({ type: 'clip', id, req: Object.assign({}, req, { blob: req.blob ? req.blob.buffer.slice(0) : null }) });
  });

  // ---- one controller per page and fighter -------------------------------------------------------------------------
  async function attach(f) {
    if (typeof Worker === 'undefined' || !window.TryIt || !window.TryIt.ctx) return null;
    let c;
    try { c = await window.TryIt.ctx(f); } catch (e) { return null; }
    if (!(c.man.features || []).includes('try3')) return null;
    css();
    const CL = window.ChainLab, TI = window.TryIt;
    const clips = new Map();                          // key -> clip state
    const stats = { clips: 0, ms: 0, frames: 0, list: [], boot: null, slow: false, evicted: 0 };
    let boxes = false;
    try { boxes = localStorage.getItem('lclip-boxes') === '1'; } catch (e) { /* private window */ }
    const boxBtns = new Set();
    const BUDGET = (PHONE ? 40 : 160) * 1048576;

    // a clip's request: the TRY blob (encodeTry, apply now), the input, the gap, MAX ready
    function request(st) {
      const s = st.spec(), sh = s.sheet || {}, plan = st.plan;
      const out = { cap: 300, gap: NEAR, script: null, blob: null, max: false, text: '' };
      if (s.kind === 'chain' || s.kind === 'press') {
        if (!plan || !plan.press) return { why: 'his pack has no chain data' + (plan && plan.why ? ' (' + plan.why + ')' : '') };
        const ch = TI.chainOf(c, sh.chain, sh.timing);
        if (s.kind === 'chain') {
          out.blob = CL.encodeTry({ fighter: c.man.id, chain: ch.chain || { entries: plan.press.map(() => null), hitstop: plan.press.map(() => 0) }, retime: ch.retime });
          out.script = { chain: plan.N, stick: '' }; out.cap = 420;
          out.text = 'A on every other frame: presses 1-' + plan.N + ' (the last = the neutral finisher)';
        } else {
          const k = s.k, p = plan.press[k];
          if (!p) return { why: 'no press ' + (k + 1) + ' in his chain' };
          const e = p.entry !== null ? p.entry : p.move && CL.MOVE_NAMES.includes(p.move) && plan.C.ba.indexOf(p.move) >= 0 ? CL.LE_MOVE | plan.C.ba.indexOf(p.move) : null;
          if (e === null) return { why: 'press ' + (k + 1) + ' plays nothing the game can start alone' };
          const th = (sh.timing && sh.timing.hitstop) || {}, hs = Number.isInteger(th['a' + (k + 1)]) ? th['a' + (k + 1)] : plan.defaults.hitstop[k];
          const entries = plan.press.map((_, i) => i ? null : e), hitstop = plan.press.map((_, i) => i ? 0 : hs);
          out.blob = CL.encodeTry({ fighter: c.man.id, chain: { entries, hitstop }, retime: ch.retime });
          out.script = [['a', 2]];
          out.text = `press ${k + 1} alone: one A (${p.label}, hit-stop ${hs})`;
        }
      } else {
        const slot = s.slot, sc = scriptOf(slot) || (STICK[slot] !== undefined ? null : undefined);
        const slots = {}, kn = TI.knobsOf(c, s.pieces && s.knobs && Object.keys(s.knobs).length ? { [slot]: s.knobs } : {});
        if (s.pieces && s.pieces.length) {
          const es = [];
          for (const p of s.pieces) { try { es.push(TI.entry(p, c)); } catch (e) { return { why: e.message }; } }
          slots[slot] = es.slice(0, CL.LO_MAX);
        }
        if (STICK[slot] !== undefined) {                // a finisher: the sheet's chain, its last press with the stick
          if (!plan || !plan.press) return { why: 'his pack has no chain data' };
          const ch = TI.chainOf(c, sh.chain, sh.timing);
          out.blob = CL.encodeTry({ fighter: c.man.id, slots, knobs: kn.rows, chain: ch.chain, retime: ch.retime });
          out.script = { chain: plan.N, stick: STICK[slot] }; out.cap = 420;
          out.text = `the chain (A every other frame), ${STICK[slot] === 'L' ? 'back' : STICK[slot] === 'R' ? 'forward' : STICK[slot] === 'U' ? 'up' : STICK[slot] === 'D' ? 'down' : 'down-forward'} held from press ${plan.N} on`;
        } else {
          if (!sc) return { why: 'no input for this slot' };
          out.blob = CL.encodeTry({ fighter: c.man.id, slots, knobs: kn.rows });
          out.script = sc; out.max = slot === 'max';
          out.gap = /^grab_/.test(slot) ? NEAR : 80;
          out.text = 'input: ' + sc.filter(x => x[0]).map(x => keysText(x[0])).join(', ');
        }
      }
      return out;
    }
    const hashOf = r => r.why ? 'why:' + r.why : [Array.from(r.blob || []).join(','), JSON.stringify(r.script), r.gap, r.max, r.cap].join('|');

    // ---- the queue: one simulation at a time, visible clips first, the newest change first ----
    let running = false;
    function pump() {
      if (running) return;
      const cand = [...clips.values()].filter(st => st.dirty && st.visible && !st.wait).sort((a, b) => b.asked - a.asked);
      const st = cand[0];
      if (!st) return;
      running = true; st.dirty = false;
      go(st).finally(() => { running = false; pump(); });
    }
    async function go(st) {
      st.el.dataset.busy = '1'; say(st, 'Re-rendering… (the game plays it)', 'busy');
      let r;
      try { st.plan = await TI.plan(f, (st.spec().sheet || {}).chain); r = request(st); } catch (e) { r = { why: e.message }; }
      if (r.why) { st.el.dataset.busy = '0'; st.res = null; st.hash = hashOf(r); say(st, 'Not simulated: ' + r.why, 'bad'); drawFd(st); return; }
      const g = st.gapMode === 'near' ? NEAR : st.gapMode === 'far' ? FAR : (st.autoGap || r.gap);
      r.gap = g;
      const hash = hashOf(r);
      if (hash === st.hash && st.res) { st.el.dataset.busy = '0'; say(st, ''); return; }
      try {
        const b = await init(c);
        if (stats.boot === null) stats.boot = b.bootMs;
        const t0 = performance.now(), res = await simulate(r);
        if (res.fatal) throw new Error(res.error);
        res.wall = Math.round(performance.now() - t0);
        // the automatic gap: a projectile far enough to see it travel; a whiff with a reach: the tip on the dummy
        if (st.gapMode === 'auto' && !st.autoGap && res.fd) {
          let ng = 0;
          if (res.fd.proj && g < FAR) ng = FAR;
          else if (!res.fd.hits && res.fd.reach > 0 && res.fd.reach + 12 < g) ng = Math.max(30, res.fd.reach + 12);
          if (ng) { st.autoGap = ng; st.dirty = true; st.asked = Date.now(); st.el.dataset.busy = '0'; return; }
        }
        stats.clips++; stats.ms += res.ms; stats.frames += res.n; stats.list.push({ key: st.key, ms: res.ms, wall: res.wall, n: res.n });
        stats.slow = stats.clips >= 3 && stats.ms / stats.frames > 12;
        st.res = res; st.hash = hash; st.req = r; st.i = 0; st.acc = 0; st.used = Date.now();
        st.el.dataset.busy = '0';
        say(st, res.error ? 'The game: ' + res.error : '', res.error ? 'bad' : '');
        layout(st); drawFd(st); drawFrame(st);
        if (st.hash !== hashOf(Object.assign(request(st), { gap: g }))) st.dirty = true;   // changed while it ran
        evict();
      } catch (e) { st.el.dataset.busy = '0'; say(st, 'Not simulated: ' + e.message, 'bad'); }
    }
    function evict() {                                 // the frames kept in memory: the least recently seen clips go first
      const bytes = st => st.res && st.res.data ? st.res.data.byteLength : 0;
      let total = [...clips.values()].reduce((a, st) => a + bytes(st), 0);
      for (const st of [...clips.values()].filter(x => !x.visible && x.res).sort((a, b) => a.used - b.used)) {
        if (total <= BUDGET) break;
        total -= bytes(st); st.res = null; st.hash = null; st.dirty = true; stats.evicted++;
      }
    }
    const say = (st, t, cls) => { st.stateEl.textContent = t; st.stateEl.className = 'lstate' + (cls ? ' ' + cls : ''); };

    // ---- drawing ----
    const SC = 2;                                       // the canvas draws each game pixel as 2 x 2 (crisp box lines)
    function layout(st) {
      const r = st.res;
      if (!r) return;
      st.off = st.off && st.off.width === r.w && st.off.height === r.h ? st.off : Object.assign(document.createElement('canvas'), { width: r.w, height: r.h });
      st.img = st.off.getContext('2d').createImageData(r.w, r.h);
      st.cv.width = r.w * SC; st.cv.height = r.h * SC;
      if (st.compact) {                                 // fit the width, at most ~1/3 of a phone's height (190 px; 260 on a desktop)
        const W = (st.el.clientWidth || r.w) - 6, z = Math.min(W / r.w, (PHONE ? 190 : 260) / r.h, 2);
        st.cv.style.width = Math.round(r.w * z) + 'px';
      } else st.cv.style.width = Math.min(r.w * (PHONE ? 1.3 : 1.5), st.el.clientWidth - 10 || r.w) + 'px';
    }
    function drawFrame(st) {
      const r = st.res; if (!r || !st.img) return;
      const k = Math.min(st.i, r.n - 1), px = r.w * r.h, o = k * px, d32 = new Uint32Array(st.img.data.buffer), pal = r.pal, src = r.data;
      for (let i = 0; i < px; i++) d32[i] = pal[src[o + i]];
      st.off.getContext('2d').putImageData(st.img, 0, 0);
      const g = st.cv.getContext('2d');
      g.imageSmoothingEnabled = false;
      g.drawImage(st.off, 0, 0, r.w * SC, r.h * SC);
      const fr = r.frames[k], active = fr.atk.length > 0;
      if (boxes) {
        const rect = (b, dash) => {
          const x = b[0] * SC, y = b[1] * SC, w = (b[2] - b[0]) * SC, hh = (b[3] - b[1]) * SC;
          g.setLineDash([]); g.lineWidth = 4; g.strokeStyle = '#fff'; g.strokeRect(x, y, w, hh);
          g.setLineDash(dash); g.lineWidth = 2; g.strokeStyle = '#000'; g.strokeRect(x, y, w, hh);
        };
        for (const b of fr.hurt) rect(b, [6, 4]);
        for (const b of fr.atk) rect(b, []);
        g.setLineDash([]);
        const zb = Math.max(1, st.cv.width / Math.max(1, st.cv.clientWidth || st.cv.width)), fb = Math.round(11 * zb);
        for (const b of fr.atk) { g.font = `bold ${fb}px ui-monospace, monospace`; const w = g.measureText('ATK').width + fb * .5; g.fillStyle = '#000'; g.fillRect(b[0] * SC, b[1] * SC - fb * 1.3, w, fb * 1.3); g.fillStyle = '#fff'; g.fillText('ATK', b[0] * SC + fb * .25, b[1] * SC - fb * .3); }
      }
      // the frame, ACTIVE / HIT tags (words, black on white)
      const zs = Math.max(1, st.cv.width / Math.max(1, st.cv.clientWidth || st.cv.width)), fs = Math.round(12 * zs), th = Math.round(fs * 1.35);   // (12 px on screen)
      const tag = (t, x, inv) => { g.font = `bold ${fs}px ui-monospace, monospace`; const w = g.measureText(t).width + fs * .6; g.fillStyle = inv ? '#000' : '#fff'; g.fillRect(x, 0, w, th); g.strokeStyle = '#000'; g.lineWidth = Math.max(1, zs); g.setLineDash([]); g.strokeRect(x + .5, .5, w - 1, th - 1); g.fillStyle = inv ? '#fff' : '#000'; g.fillText(t, x + fs * .3, th - fs * .35); return w; };
      let x = 0;
      x += tag(`f ${k + 1}/${r.n}${st.speed !== 1 ? ' ¼' : ''}`, x) + 2;
      if (active) x += tag('ACTIVE', x, true) + 2;
      if (fr.hit) tag('HIT', x, true);
      drawCaret(st, k);
    }
    // the frame-data strip: one cell a frame (startup white, active black, recovery hatched, after his move dotted),
    // the hits marked above, the frame shown marked below
    function drawFd(st) {
      const r = st.res, el = st.fdEl, bar = st.bar;
      if (!r || !r.fd) { el.textContent = ''; bar.hidden = true; return; }
      bar.hidden = false;
      const fd = r.fd, rows = [];
      const wins = fd.windows.map(([a, b]) => a === b ? String(a) : a + '-' + b).join(', ');
      rows.push(h('span', {}, h('b', { text: 'Startup ' + (fd.startup || '-') }), ' · ', h('b', { text: 'Active ' + (fd.active || 0) }), fd.windows.length > 1 || fd.active ? ` (frames ${wins})` : ' (no attack box)', (fd.hits && fd.active ? ' (hit-stop frames included)' : '') + ' · ', h('b', { text: 'Recovery ' + fd.recovery }), ' · ', h('b', { text: 'Total ' + fd.total + ' f' }), fd.ended ? '' : ' (not back in neutral: cut at ' + r.n + ')'));
      rows.push(h('br'), `Hits ${fd.hits} · damage ${fd.damage}` + (fd.hitFrames.length ? ` (on frame${fd.hitFrames.length > 1 ? 's' : ''} ${fd.hitFrames.slice(0, 8).join(', ')}${fd.hitFrames.length > 8 ? '…' : ''})` : ' (WHIFF)') + ` · reach ${fd.reach ? fd.reach + ' px' : '-'} · gap ${fd.gap} px`);
      if (fd.proj) rows.push(h('br'), `Projectile: ${fd.proj.speed} px a frame, ${fd.proj.travel} px travelled (frames ${fd.proj.from + 1}-${fd.proj.to + 1})`);
      const RN = { HITSTUN: 'reel', KNOCKDOWN: 'knocked down', DOWN: 'lying', GETUP: 'getting up', GRABBED: 'held', THROWN: 'thrown', IDLE: 'standing', WALK: 'walking' };
      const rx = fd.react.filter(x => x.st !== 'IDLE' && x.st !== 'WALK').map(x => `${RN[x.st] || x.st.toLowerCase()} ${x.n} f`);
      rows.push(h('br'), 'Dummy: ' + (rx.length ? rx.join(' → ') + (fd.lift > 4 ? ` (up to ${fd.lift} px high)` : '') : 'not hit'));
      const cls = st.cls ? st.cls() : '';
      if (cls) rows.push(h('br'), 'Hit class (data): ' + cls);
      rows.push(h('br'), `Played: ${st.req ? st.req.text : ''} · simulated in ${r.ms} ms`);
      if (st.compact) {                                 // ONE line; the rest in its tooltip
        const one = `${fd.startup || '-'}/${fd.active || 0}/${fd.recovery} f` + (fd.ended ? '' : ' (cut)') + ' · ' +
          (fd.hits ? `${fd.hits} hit${fd.hits > 1 ? 's' : ''} · ${fd.damage} dmg` : 'whiff') + (fd.reach ? ` · reach ${fd.reach}` : '') +
          (fd.proj ? ` · proj ${fd.proj.speed} px/f` : '');
        el.textContent = one;
        el.title = h('span', {}, ...rows).textContent.replace(/^\s+/, '');
        el.setAttribute('aria-label', 'Startup / active / recovery: ' + one);
      } else el.replaceChildren(...rows);
      drawCaret(st, st.i);
    }
    function drawCaret(st, k) {
      const r = st.res, bar = st.bar; if (!r || !r.fd || bar.hidden) return;
      const W = Math.max(120, Math.round(bar.clientWidth || 300)), H = st.compact ? 20 : 34, n = r.n, fd = r.fd;
      if (bar.width !== W * 2) { bar.width = W * 2; bar.height = H * 2; }
      const g = bar.getContext('2d'); g.setTransform(2, 0, 0, 2, 0, 0);
      g.fillStyle = '#fff'; g.fillRect(0, 0, W, H);
      const cw = W / n, y0 = st.compact ? 5 : 8, y1 = st.compact ? 15 : 24;
      for (let i = 0; i < n; i++) {
        const x = i * cw, act = r.frames[i].atk.length > 0, mine = i < fd.total;
        if (act) { g.fillStyle = '#000'; g.fillRect(x, y0, Math.max(cw, 1), y1 - y0); }
        else if (mine && fd.startup && i >= fd.startup - 1) {                 // recovery (and gaps between windows): hatched
          g.strokeStyle = '#000'; g.lineWidth = 1; g.beginPath();
          for (let yy = y0; yy < y1; yy += 4) { g.moveTo(x, yy + 4); g.lineTo(x + Math.max(cw, 1), yy); }
          g.stroke();
        } else if (!mine) { g.fillStyle = '#000'; for (let yy = y0 + 2; yy < y1; yy += 4) g.fillRect(x + cw / 2, yy, 1, 1); }
      }
      g.strokeStyle = '#000'; g.lineWidth = 1; g.strokeRect(.5, y0 + .5, Math.min(W, fd.total * cw) - 1, y1 - y0 - 1);
      g.fillStyle = '#000';
      for (const fh of fd.hitFrames) { const x = (fh - 1) * cw + cw / 2; g.beginPath(); g.moveTo(x - 4, 0); g.lineTo(x + 4, 0); g.lineTo(x, y0 - 1); g.fill(); }
      const xk = k * cw + cw / 2; g.beginPath(); g.moveTo(xk - 4, H); g.lineTo(xk + 4, H); g.lineTo(xk, y1 + 2); g.fill();
    }

    // ---- the clock: every visible clip with frames advances one game frame each FMS (tap = ¼ speed) ----
    let last = performance.now();
    (function tick(now) {
      const dt = Math.min(250, now - last); last = now;
      for (const st of clips.values()) {
        if (!st.visible || !st.res || !document.body.contains(st.el)) continue;
        st.acc += dt * st.speed; let n = 0;
        while (st.acc >= FMS) { st.acc -= FMS; st.i = (st.i + 1) % st.res.n; n++; }
        if (n) drawFrame(st);
      }
      requestAnimationFrame(tick);
    })(last);
    const io = new IntersectionObserver(es => {
      for (const e of es) {
        const st = e.target._lclip; if (!st) continue;
        st.visible = e.isIntersecting;
        if (st.visible) { st.used = Date.now(); if (!st.res) { st.dirty = true; st.asked = st.asked || Date.now(); } pump(); }
      }
    }, { rootMargin: '150px' });

    function clip(o) {
      const old = clips.get(o.key);
      if (old) { io.unobserve(old.el); }
      const st = Object.assign(old || { res: null, hash: null, i: 0, acc: 0, speed: 1, gapMode: 'auto', autoGap: 0, used: 0 },
        { key: o.key, spec: o.req, cls: o.cls, visible: false, dirty: true, asked: Date.now(), compact: !!o.compact });
      st.cv = h('canvas', { class: 'lpic', width: '280', height: '160', role: 'img', 'aria-label': 'Live clip: ' + o.label + ' (the game plays it); tap for ¼ speed' });
      st.cv.onclick = () => { st.speed = st.speed === 1 ? 0.25 : 1; drawFrame(st); };
      st.stateEl = h('div', { class: 'lstate', role: 'status', 'aria-live': 'polite', text: o.compact ? 'Waiting…' : 'Waiting to render (the game plays it when it is on screen)…' });
      const gapBtn = h('button', { type: 'button', class: 'lgap', title: 'Where the dummy stands: Auto (the piece\'s reach, a projectile far), Near (44 px), Far (150 px)' });
      const gapText = () => { gapBtn.textContent = (o.compact ? 'gap ' : 'Gap: ') + { auto: 'auto', near: 'near ' + NEAR, far: 'far ' + FAR }[st.gapMode]; };
      gapBtn.onclick = () => { st.gapMode = { auto: 'near', near: 'far', far: 'auto' }[st.gapMode]; st.autoGap = 0; gapText(); st.dirty = true; st.asked = Date.now(); pump(); };
      gapText();
      st.bar = h('canvas', { class: 'lbar', role: 'img', 'aria-label': 'Frame data bar: startup white, active black, recovery hatched, after his move dotted; hits marked above, the frame shown below' });
      st.fdEl = h('p', { class: 'lfd' });
      st.el = o.compact
        ? h('figure', { class: 'lclip compact', 'data-key': o.key, 'aria-label': o.label },
          h('div', { class: 'lchead' }, gapBtn, boxesButton(true)), st.cv, st.stateEl, st.fdEl, st.bar)
        : h('figure', { class: 'lclip', 'data-key': o.key },
          h('div', { class: 'lchead' }, h('b', { text: o.label }), gapBtn), st.cv, st.stateEl, st.bar, st.fdEl);
      st.el._lclip = st;
      clips.set(o.key, st);
      io.observe(st.el);
      if (st.res) { requestAnimationFrame(() => { layout(st); drawFd(st); drawFrame(st); }); }
      return st.el;
    }
    const timers = new Map();
    function refresh(key) {
      const go1 = st => { st.dirty = true; st.asked = Date.now(); };
      const k = key || '*';
      clearTimeout(timers.get(k));
      timers.set(k, setTimeout(() => {
        if (key) { const st = clips.get(key); if (st) go1(st); } else clips.forEach(go1);
        pump();
      }, DEBOUNCE));
    }
    const LEGEND = 'Boxes: solid outline + "ATK" = attack box (it hits), dashed = hurt box (it can be hit). The bar: white = startup, black = active, hatched = recovery, dotted = after his move; ▼ = a hit, ▲ = the frame shown.';
    function boxesButton(tiny) {
      const b = h('button', { type: 'button', class: tiny ? 'lboxes' : 'lclip-boxes', 'aria-pressed': String(boxes), title: LEGEND });
      const txt = () => { b.textContent = tiny ? (boxes ? '✓ boxes' : 'boxes') : (boxes ? '✓ ' : '') + 'Hit boxes on the clips'; b.setAttribute('aria-pressed', String(boxes)); };
      b.onclick = () => { boxes = !boxes; try { localStorage.setItem('lclip-boxes', boxes ? '1' : '0'); } catch (e) { /* no storage */ } boxBtns.forEach(x => x.isConnected ? x._txt() : boxBtns.delete(x)); clips.forEach(st => drawFrame(st)); };
      b._txt = txt; txt(); boxBtns.add(b);
      if (tiny) return b;
      return h('span', { class: 'tryrow' }, b, h('span', { class: 'lclip-legend', text: 'Boxes: solid outline + "ATK" = attack box (it hits), dashed = hurt box (it can be hit). The bar: white = startup, black = active, hatched = recovery, dotted = after his move; ▼ = a hit, ▲ = the frame shown.' }));
    }
    function forget(key) { const st = clips.get(key); if (st) { io.unobserve(st.el); st.visible = false; st.dirty = !st.res || st.dirty; } }
    const api = { clip, refresh, forget, boxesButton, stats, clips, get boxes() { return boxes; }, set boxes(v) { boxes = !!v; boxBtns.forEach(x => x._txt()); clips.forEach(st => drawFrame(st)); }, phone: PHONE, ctx: c };
    window.liveclips = { stats, clips, LC: api };
    return api;
  }
  window.LiveClips = { attach, scriptOf, INPUT_TEXT };
})();
