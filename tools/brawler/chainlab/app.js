/* Chain Lab page: the route-tree editor around the real game (lab.js + core.wasm). The page only edits data and presses
 * buttons; the brawler's own 68000 code plays the routes (fighter.c), reading the tree "Build" writes into its RAM. */
(async function () {
  'use strict';
  const CL = window.ChainLab;
  const $ = id => document.getElementById(id);
  const IN_LABEL = { A: 'A', B: 'B', dA: '↓A', dB: '↓B', fA: '→A', fB: '→B', dfA: '↘A', dfB: '↘B', AB: 'A+B', D: 'D', fD: '→D', dD: '↓D', uD: '↑D' };
  const MOVE_LABEL = {
    atk_a_close: 'close A', atk_a_far: 'far A', atk_a_crouch: 'crouch A', atk_b_close: 'close B', atk_b_far: 'far B',
    atk_b_crouch: 'crouch B', atk_c_close: 'close C', atk_c_far: 'far C', atk_c_crouch: 'crouch C', atk_d_close: 'close D',
    atk_d_far: 'far D', atk_d_crouch: 'crouch D (sweep)', body_toss: 'C+D (blowback)', cmd_fwd_a: 'forward+A (command)',
    cmd_fwd_b: 'forward+B (command)', cmd_df_c: 'down-forward+C (command)', cmd_df_d: 'down-forward+D (command)',
    atk_c_jump: 'air C', atk_d_jump: 'air D', atk_cd_jump: 'air C+D' };
  const SPECIAL_LABEL = { D: 'D special', fD: 'forward+D special', dD: 'down+D special', uD: 'up+D special' };
  const ENTRY_LABEL = { dash: 'Dash attack (run + A)', nospecial: 'D without a special for it', hold: "The hold's third hit (C+D)",
                        air_a: 'Air A', air_b: 'Air B', air_cd: 'Air C (C+D)' };
  const HOW_LABEL = ['start (from neutral)', 'after the move ended', 'cancel on hit', 'tapped in the chain window'];
  const clone = x => JSON.parse(JSON.stringify(x));
  const err = msg => { const e = $('err'); e.textContent = msg || ''; e.style.display = msg ? 'block' : 'none'; };

  // ---- load ----------------------------------------------------------------------------------------------------------
  const get = async (p, kind) => { const r = await fetch(p, { cache: 'no-cache' }); if (!r.ok) throw new Error(p + ': ' + r.status); return kind === 'json' ? r.json() : new Uint8Array(await r.arrayBuffer()); };
  let data, layout, lab;
  try {
    [data, layout] = await Promise.all([get('chainlab.json', 'json'), get('layout.json', 'json')]);
    const [bios, rom] = await Promise.all([get('neogeo.zip'), get('game.neo')]);
    lab = await CL.Lab.create(window.GeoCore, { bios, rom }, layout);
  } catch (e) { $('loading').textContent = 'Could not load: ' + e.message; throw e; }
  $('loading').hidden = true; $('main').hidden = false;
  $('ver').textContent = 'brawler ' + layout.version;

  const F = data.fighters;
  let fi = Math.max(0, F.findIndex(f => f.name === 'terry')), di = F.findIndex(f => f.name === 'ryo');
  if (di < 0 || di === fi) di = (fi + 1) % F.length;
  for (const [sel, v] of [[$('fighter'), fi], [$('dummy'), di]]) {
    F.forEach((f, i) => sel.add(new Option(f.name.toUpperCase().replace('_', ' ') + (sel.id === 'fighter' && f.routes_file ? ' (own routes)' : ''), i)));
    sel.value = v;
  }
  let tree = clone(F[fi].tree);          // the tree in the editor
  let built = null;                      // {fi, tree (snapshot), info: index -> {path, node}}
  let labTreeFor = -1;                   // the fighter whose route_tab entry points at the lab buffer

  // ---- the game loop -------------------------------------------------------------------------------------------------
  const canvas = $('screen'), ctx = canvas.getContext('2d');
  let img = null, paused = false, acc = 0, last = 0, evNext = 0;
  const fps = lab.core._wc_fps();
  lab.boot(fi, di, null);
  evNext = lab.nev();

  const keys = new Set(), touch = new Set();
  // by physical key (KeyboardEvent.code), so the layout is the same on QWERTZ / AZERTY / QWERTY (Bruno, 2026-10-05):
  // WASD stick, U I O P = A B C D; the arrows and Z X C V (QWERTY positions) also work
  const KEYMAP = { KeyW: 'U', KeyA: 'L', KeyS: 'D', KeyD: 'R', KeyU: 'a', KeyI: 'b', KeyO: 'c', KeyP: 'd',
                   ArrowLeft: 'L', ArrowRight: 'R', ArrowUp: 'U', ArrowDown: 'D', KeyZ: 'a', KeyX: 'b', KeyC: 'c', KeyV: 'd',
                   Enter: 's', NumpadEnter: 's' };
  addEventListener('keydown', e => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    if (e.code === 'Escape' || e.code === 'Backspace') { togglePause(); e.preventDefault(); return; }
    if (e.code === 'Period' && paused) { stepFrames(1); e.preventDefault(); return; }
    const k = KEYMAP[e.code]; if (k) { keys.add(k); e.preventDefault(); }
  });
  addEventListener('keyup', e => { const k = KEYMAP[e.code]; if (k) keys.delete(k); });
  addEventListener('blur', () => keys.clear());
  let override = null;                   // a scripted input (chainlab.play: tests, the proof)
  function padKeys() {
    if (override !== null) return override;
    const s = new Set([...keys, ...touch]);
    for (const gp of (navigator.getGamepads ? navigator.getGamepads() : [])) {
      if (!gp) continue;
      const b = i => gp.buttons[i] && gp.buttons[i].pressed;
      if (b(0)) s.add('a'); if (b(1)) s.add('b'); if (b(2)) s.add('c'); if (b(3)) s.add('d'); if (b(9)) s.add('s');
      if (b(12) || gp.axes[1] < -0.5) s.add('U'); if (b(13) || gp.axes[1] > 0.5) s.add('D');
      if (b(14) || gp.axes[0] < -0.5) s.add('L'); if (b(15) || gp.axes[0] > 0.5) s.add('R');
    }
    return [...s].join('');
  }
  // touch pad (shown on touch screens)
  if (matchMedia('(pointer: coarse)').matches) $('touch').classList.add('show');
  for (const b of document.querySelectorAll('#touch button')) {
    const ks = b.dataset.k === 'ab' ? ['a', 'b'] : [b.dataset.k];
    b.addEventListener('pointerdown', e => { ks.forEach(k => touch.add(k)); b.classList.add('on'); e.preventDefault(); });
    for (const t of ['pointerup', 'pointercancel', 'pointerleave']) b.addEventListener(t, () => { ks.forEach(k => touch.delete(k)); b.classList.remove('on'); });
  }

  // audio: the core's frames into a ring, a ScriptProcessor pulls them (resampled when the context's rate differs)
  let audio = null;
  const RING = 1 << 15, ring = new Float32Array(RING * 2); let rw = 0, rr = 0;
  const coreRate = lab.core._wc_sample_rate();
  function pushAudio() {
    if (!audio) return;
    const n = lab.core._wc_audio_n(), p = lab.core._wc_audio() >> 1, h = lab.core.HEAP16;
    for (let i = 0; i < n; i++) {
      if (((rw + 1) & (RING - 1)) === rr) break;
      ring[rw * 2] = h[p + i * 2] / 32768; ring[rw * 2 + 1] = h[p + i * 2 + 1] / 32768; rw = (rw + 1) & (RING - 1);
    }
  }
  $('btnSound').onclick = async () => {
    if (audio) { await audio.close(); audio = null; $('btnSound').textContent = 'Sound: off'; return; }
    let ac; try { ac = new AudioContext({ sampleRate: coreRate }); } catch (e) { ac = new AudioContext(); }
    const sp = ac.createScriptProcessor(2048, 0, 2), step = coreRate / ac.sampleRate; let frac = 0;
    sp.onaudioprocess = ev => {
      const L = ev.outputBuffer.getChannelData(0), R = ev.outputBuffer.getChannelData(1);
      for (let i = 0; i < L.length; i++) {
        if (rr === rw) { L[i] = R[i] = 0; continue; }
        L[i] = ring[rr * 2]; R[i] = ring[rr * 2 + 1];
        frac += step; while (frac >= 1 && rr !== rw) { rr = (rr + 1) & (RING - 1); frac -= 1; }
      }
      const fill = (rw - rr) & (RING - 1); if (fill > 8192) rr = (rw - 2048) & (RING - 1);   // never lag behind the picture
    };
    sp.connect(ac.destination); audio = ac; rr = rw; $('btnSound').textContent = 'Sound: on';
  };

  function draw() {
    const w = lab.core._wc_fb_w(), h = lab.core._wc_fb_h();
    if (canvas.width !== w || canvas.height !== h || !img) { canvas.width = w; canvas.height = h; img = ctx.createImageData(w, h); fit(); }
    const src = new Uint8Array(lab.core.HEAPU8.buffer, lab.core._wc_fb(), w * h * 4), d = img.data;
    for (let i = 0; i < w * h * 4; i += 4) { d[i] = src[i + 2]; d[i + 1] = src[i + 1]; d[i + 2] = src[i]; d[i + 3] = 255; }
    ctx.putImageData(img, 0, 0);
    const c = lab.combo();
    $('status').textContent = `frame ${lab.labFrame()}  P1 ${lab.stateName(0)}  dummy ${lab.stateName(2)}  combo ${c.hits} hits ${c.dmg} damage${paused ? '  PAUSED' : ''}`;
  }
  function fit() {                        // pixel-exact: a whole number of screen pixels per game pixel
    const want = Number($('scale').value), col = $('gamecol');
    const avail = col.clientWidth - 36, s = want || Math.max(1, Math.floor(Math.min(avail / canvas.width, (innerHeight * 0.62) / canvas.height)));
    canvas.style.width = canvas.width * s + 'px'; canvas.style.height = canvas.height * s + 'px';
  }
  addEventListener('resize', fit); $('scale').onchange = fit;
  function stepFrames(n) {
    for (let i = 0; i < n; i++) { lab.setPad(0, padKeys()); lab.run(1); pushAudio(); collect(); }
    draw();
  }
  function togglePause() { paused = !paused; $('btnPause').textContent = paused ? 'Resume' : 'Pause'; $('btnPause').classList.toggle('on', paused); $('btnStep').disabled = !paused; draw(); }
  $('btnPause').onclick = togglePause; $('btnStep').onclick = () => stepFrames(1);
  function loop(ts) {
    requestAnimationFrame(loop);
    if (!last) last = ts;
    acc += (ts - last) / 1000 * fps; last = ts;
    if (paused) { acc = 0; return; }
    let n = Math.floor(acc); acc -= n;
    if (n > 4) { n = 4; acc = 0; }       // a tab in the background: no catch-up burst
    if (n) stepFrames(n);
  }
  requestAnimationFrame(loop);

  // ---- requests -------------------------------------------------------------------------------------------------------
  function runUntil(cond, max = 120) { for (let i = 0; i < max && !cond(); i++) { lab.run(1); } }
  function restoreLabFighter() {          // the fighter that used the lab buffer gets its own tree back
    if (labTreeFor >= 0) { lab.installTree(labTreeFor, null); lab.run(1); labTreeFor = -1; }
  }
  $('btnStart').onclick = () => {
    const nf = Number($('fighter').value), nd = Number($('dummy').value);
    if (nf !== fi) { restoreLabFighter(); fi = nf; $('btnRom').onclick(); }
    di = nd; lab.request(1, fi, di); runUntil(() => lab.r8(lab.lab + 4) === 0);
    evNext = lab.nev(); chains = []; showReadout(); draw();
  };
  $('fighter').onchange = () => $('btnStart').onclick();
  $('dummy').onchange = () => $('btnStart').onclick();
  $('btnPlace').onclick = () => { lab.request(2); lab.run(1); draw(); };

  function build() {
    let blob;
    try { blob = CL.encodeTree(tree, data.ba, F[fi].has, F[fi].default.entries); } catch (e) { err('The tree cannot be built: ' + e.message); return; }
    err('');
    if (labTreeFor >= 0 && labTreeFor !== fi) restoreLabFighter();
    lab.installTree(fi, blob); lab.run(1); labTreeFor = fi;
    const snap = clone(tree); built = { fi, tree: snap, info: indexInfo(snap), bytes: blob.length };
    builtLabel = $('built').textContent = `built: ${blob[3]} nodes, ${blob.length} bytes in the game's RAM`;
    render();
  }
  $('btnBuild').onclick = build;
  $('btnRom').onclick = () => {
    restoreLabFighter(); tree = clone(F[fi].tree); { const snap = clone(tree); built = { fi, tree: snap, info: indexInfo(snap) }; }
    builtLabel = $('built').textContent = F[fi].routes_file ? 'the fighter\'s own tree (routes file, in the ROM)' : 'the default tree (in the ROM)';
    render();
  };
  $('btnDefault').onclick = () => { tree = clone(F[fi].default); tree.fighter = F[fi].name; markDirty(); render(); };
  $('btnExport').onclick = () => {
    const out = { fighter: F[fi].name, links: tree.links, entries: tree.entries };
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(out, null, 1)], { type: 'application/json' }));
    a.download = F[fi].name + '.json'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  };
  $('btnImport').onclick = () => $('file').click();
  $('file').onchange = async () => {
    const f = $('file').files[0]; if (!f) return;
    try {
      const t = JSON.parse(await f.text());
      t.entries = Object.assign({}, F[fi].default.entries, t.entries || {});
      CL.encodeTree(t, data.ba, F[fi].has, F[fi].default.entries);
      tree = t; markDirty(); render(); err('');
    } catch (e) { err('Import: ' + e.message); }
    $('file').value = '';
  };
  let builtLabel = '';
  function markDirty() { $('built').textContent = built && CL.pyjson(built.tree) === CL.pyjson(tree) ? builtLabel : 'edited: not built yet'; }

  // ---- the readout: P1's route steps from the game's event log ---------------------------------------------------------
  function indexInfo(t) {                // node index -> {path (inputs from neutral), node}
    const map = CL.nodeIndex(t), info = new Map();
    (function walk(links, path) {
      for (const [k, ch] of Object.entries(links || {})) {
        const p = path.concat(IN_LABEL[k]), i = map.get(ch);
        if (i !== undefined && !info.has(i)) info.set(i, { path: p, node: ch });
        walk(ch.links, p);
      }
    })(t.links, []);
    return info;
  }
  let chains = [];                       // [{links: [{idx, label, how, start, hits: [frames], dmg, end}]}]
  function collect() {
    const { events, next } = lab.eventsSince(evNext); evNext = next;
    if (!events.length) return;
    for (const e of events) {
      let ch = chains[chains.length - 1], ln = ch && ch.links[ch.links.length - 1];
      if (e.kind === 'START' || e.kind === 'SPECIAL') {
        if (e.how === 0 || !ch) { ch = { links: [] }; chains.push(ch); if (chains.length > 8) chains.shift(); }
        ch.links.push({ idx: e.node, special: e.kind === 'SPECIAL' ? e.val : null, how: e.how, start: e.frame, hits: [], dmg: 0, end: null });
      } else if (e.kind === 'HIT' && ln) { ln.hits.push(e.frame); ln.dmg += e.val; }
      else if (e.kind === 'END' && ln) ln.end = e.frame;
      else if (e.kind === 'CHAINWIN' && ln) ln.window = true;
    }
    showReadout();
  }
  function linkLabel(l) {
    const info = built && built.fi === fi ? built.info.get(l.idx) : null;
    if (l.special !== null) return { input: info ? info.path.join(' ') : 'D', move: SPECIAL_LABEL[CL.SPECIALS[l.special]] + (F[fi].specials[CL.SPECIALS[l.special]] ? ' ' + F[fi].specials[CL.SPECIALS[l.special]] : '') };
    if (!info) return { input: '?', move: 'node ' + l.idx + (built ? '' : ' (press Build or "own tree" to name the nodes)') };
    return { input: info.path.join(' '), move: MOVE_LABEL[info.node.move] || info.node.move };
  }
  function showReadout() {
    const ch = chains[chains.length - 1];
    if (!ch) { $('readbody').innerHTML = '<div class="empty">Play a route on the dummy: each link shows here.</div>'; markTree(null); return; }
    let prevHit = null, rows = '';
    ch.links.forEach((l, k) => {
      const lb = linkLabel(l), first = l.hits[0];
      const gap = first !== undefined && prevHit !== null ? (first - prevHit) + ' f' : '-';
      const res = l.hits.length ? `HIT x${l.hits.length} (${l.dmg} dmg)` : (l.special !== null ? 'special (its hits: see combo)' : 'WHIFF');
      rows += `<tr><td>${k + 1}</td><td><b>${lb.input}</b></td><td>${lb.move}</td><td>${HOW_LABEL[l.how]}</td><td>${res}</td>` +
              `<td>${first !== undefined ? first - l.start + 1 : '-'}</td><td>${gap}</td></tr>`;
      if (l.hits.length) prevHit = l.hits[l.hits.length - 1];
    });
    const last = ch.links[ch.links.length - 1];
    const tail = last.end !== null && !last.window ? 'The route ended here (no link from this move, or it missed).' :
                 last.window ? 'The chain window opened after the last move: a later tap could still continue.' : '';
    $('readbody').innerHTML = `<table><tr><th>#</th><th>input path</th><th>move</th><th>link went</th><th>result</th><th>to 1st hit</th><th>since prev. hit</th></tr>${rows}</table>` +
      `<div class="empty">${tail} Frames are game frames (60 a second), hit-stop included.</div>`;
    markTree(ch);
  }
  $('btnClear').onclick = () => { chains = []; showReadout(); };
  function markTree(ch) {
    const hit = new Map();
    if (ch && built && built.fi === fi && CL.pyjson(built.tree) === CL.pyjson(tree))
      ch.links.forEach((l, k) => { if (l.special === null) hit.set(l.idx, (l.hits.length ? 'hit ' : 'whiff ') + '#' + (k + 1)); });
    for (const el of document.querySelectorAll('.card[data-idx]')) {
      const m = hit.get(Number(el.dataset.idx)), s = el.querySelector('.res');
      el.classList.toggle('hit', !!m && m.startsWith('hit')); if (s) s.textContent = m ? (m.startsWith('hit') ? '✓ ' : '✗ ') + m : '';
    }
  }

  // ---- the tree editor ------------------------------------------------------------------------------------------------
  const fd = m => (F[fi].moves[m] || null);
  function fdText(m) {                   // startup / active / recovery = total, hits, travel
    const d = fd(m); if (!d) return '';
    return `${d.startup}/${d.active}/${d.recovery} = ${d.total}f · ${d.hits} hit${d.hits > 1 ? 's' : ''}${d.travel ? ' · ' + d.travel + ' px' : ''}`;
  }
  function fdBar(m) { const d = fd(m); return d ? d.frames.replace(/-/g, '·').replace(/x/g, '█') : ''; }
  const h = (tag, attrs = {}, ...kids) => { const e = document.createElement(tag); for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false) e.setAttribute(k, v === true ? '' : v); } for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c); return e; };
  function sel(options, value, onchange) {
    const s = h('select', { onchange: () => onchange(s.value) });
    for (const [v, t] of options) s.add(new Option(t, v)); s.value = value; return s;
  }
  function freeInputs(nd) { return CL.INPUTS.filter(k => !(nd.links && nd.links[k])); }
  function newChild(k) {
    if (CL.SPECIAL_INPUTS.includes(k)) return { special: k };
    const has = F[fi].has;
    const pref = k === 'AB' ? ['body_toss'] : k.endsWith('A') ? (k.startsWith('d') && !k.startsWith('df') ? ['atk_a_crouch', 'atk_c_crouch'] : k.startsWith('df') ? ['cmd_df_c', 'atk_c_close'] : k.startsWith('f') ? ['cmd_fwd_a', 'atk_c_close'] : ['atk_a_close'])
                                    : (k.startsWith('d') && !k.startsWith('df') ? ['atk_b_crouch', 'atk_d_crouch'] : k.startsWith('df') ? ['cmd_df_d', 'atk_d_close'] : k.startsWith('f') ? ['cmd_fwd_b', 'atk_d_close'] : ['atk_b_close']);
    const move = pref.find(m => has.includes(m)) || 'atk_a_close';
    return { move, weight: /atk_[ab]_/.test(move) ? 'light' : 'strong', effect: 'none', cancel: false };
  }
  function edited() { markDirty(); render(); }
  function card(nd, parent, key, idxMap, air) {
    const idx = idxMap.get(nd);
    if (nd.special !== undefined) {
      const kof = F[fi].specials[nd.special];
      return h('div', { class: 'card special', 'data-idx': idx },
        h('div', { class: 't' }, h('span', {}, SPECIAL_LABEL[nd.special]), h('span', { class: 'res' })),
        h('div', { class: 'fd' }, kof ? 'KOF ' + kof + ' (route ender)' : 'none: the nearest special plays'),
        h('div', { class: 'acts' }, h('button', { onclick: () => { delete parent.links[key]; edited(); } }, 'Delete')));
    }
        const [dd, dp] = CL.defaultDamage(nd);
    const num = (field, def) => h('input', { type: 'number', value: nd[field] !== undefined ? nd[field] : '', placeholder: String(def),
      onchange: ev => { const v = ev.target.value; if (v === '') delete nd[field]; else nd[field] = Number(v); edited(); } });
    const acts = [];
    const free = freeInputs(nd);
    if (!air && free.length)
      acts.push(sel([['', '+ link'], ...free.map(k => [k, 'on ' + IN_LABEL[k]])], '', k => { if (!k) return; nd.links = nd.links || {}; nd.links[k] = newChild(k); edited(); }));
    if (parent) {
      const keys = Object.keys(parent.links), i = keys.indexOf(key);
      const move = (d) => { const j = i + d; if (j < 0 || j >= keys.length) return; [keys[i], keys[j]] = [keys[j], keys[i]]; const o = {}; for (const k of keys) o[k] = parent.links[k]; parent.links = o; edited(); };
      acts.push(h('button', { onclick: () => move(-1), title: 'move up' }, '↑'), h('button', { onclick: () => move(1), title: 'move down' }, '↓'),
        h('button', { onclick: () => { delete parent.links[key]; edited(); }, title: 'delete this hit and its links' }, '✕'));
    }
    const dmg = nd.damage !== undefined ? nd.damage : dd, push = nd.push !== undefined ? nd.push : dp;
    return h('div', { class: 'card', 'data-idx': idx },
      h('div', { class: 't' },
        air ? h('span', {}, MOVE_LABEL[nd.move] || nd.move)
            : h('button', { class: 'pick', title: 'choose the move (pictures)', onclick: () => picker(nd.move, v => { nd.move = v; edited(); }) }, (MOVE_LABEL[nd.move] || nd.move) + ' ▸'),
        h('span', { class: 'res' })),
      h('div', { class: 'fd' }, fdText(nd.move), ' ', h('span', { class: 'bar' }, fdBar(nd.move))),
      h('div', { class: 'f2' },
        sel(CL.WEIGHTS.map(w => [w, w + ' hit']), nd.weight || 'light', v => { nd.weight = v; edited(); }),
        sel(CL.EFFECTS.map(w => [w, w === 'none' ? 'no effect' : w]), nd.effect || 'none', v => { nd.effect = v; edited(); })),
      h('div', { class: 'f2' },
        h('button', { class: 'tog' + (nd.cancel ? ' on' : ''), title: 'on hit: cancel into the next link / play the move to its end',
          onclick: () => { nd.cancel = !nd.cancel; edited(); } }, nd.cancel ? 'cancel on hit' : 'plays to end'),
        h('details', {}, h('summary', {}, `${dmg} dmg · push ${push}`),
          h('div', { class: 'adv' }, h('label', {}, 'damage ', num('damage', dd)), h('label', {}, 'push px ', num('push', dp))))),
      acts.length ? h('div', { class: 'acts' }, acts) : null);
  }
  // the move picker: every move the fighter has, as its impact frame(s) drawn from the game's own data (make_site.py,
  // move_images.py), its name and frame data; the current one marked (thick border + "current")
  function picker(current, choose) {
    const P = data.pics && data.pics[F[fi].name], moves = CL.MOVE_NAMES.filter(m => F[fi].has.includes(m));
    const close = () => { dlg.remove(); removeEventListener('keydown', esc, true); };
    const esc = e => { if (e.code === 'Escape') { close(); e.stopImmediatePropagation(); e.preventDefault(); } };
    addEventListener('keydown', esc, true);
    const shots = m => (P && P.moves[m] || []).map(c => h('div', { class: 'shot', style:
      `width:${c.w / 2}px;height:${c.h / 2}px;background-image:url(${P.sheet});background-size:${P.w / 2}px ${P.h / 2}px;background-position:-${c.x / 2}px 0` }));
    const dlg = h('div', { class: 'modal', onclick: e => { if (e.target === dlg) close(); } },
      h('div', { class: 'sheet', role: 'dialog', 'aria-label': 'choose a move' },
        h('div', { class: 'mhead' }, h('b', {}, F[fi].name.toUpperCase() + ': choose the move'), h('span', {}, 'pictures = the frame(s) where it hits'),
          h('button', { onclick: close }, 'Close')),
        h('div', { class: 'mgrid' }, moves.map(m => h('button', { class: 'mv' + (m === current ? ' cur' : ''), onclick: () => { close(); if (m !== current) choose(m); } },
          h('div', { class: 'shots' }, shots(m)),
          h('div', { class: 'mname' }, (m === current ? '● ' : '') + (MOVE_LABEL[m] || m) + (m === current ? ' (current)' : '')),
          h('div', { class: 'mfd' }, fdText(m)))))));
    document.body.append(dlg);
    const cur = dlg.querySelector('.cur'); if (cur) cur.scrollIntoView({ block: 'nearest' });
  }
  function branch(nd, parent, key, idxMap, air) {
    const links = Object.entries(nd.links || {});
    const b = h('div', { class: 'branch' }, card(nd, parent, key, idxMap, air));
    if (links.length) {
      b.append(h('div', { class: 'kids' }, links.map(([k, ch]) => h('div', { class: 'kid' },
        h('div', { class: 'edge' }, h('b', { title: 'the input that reaches it (change it below)' }, IN_LABEL[k])),
        branch(ch, nd, k, idxMap, false)))));
    }
    return b;
  }
  function render() {
    tree.links = tree.links || {};
    const idxMap = CL.nodeIndex(tree), rootNode = { links: tree.links };
    const free = freeInputs(rootNode).filter(k => !CL.SPECIAL_INPUTS.includes(k));
    const rootCard = h('div', { class: 'card root' }, h('div', { class: 't' }, 'Neutral'), h('div', { class: 'fd' }, 'where every route starts'),
      h('div', { class: 'acts' }, free.length ? sel([['', '+ link…'], ...free.map(k => [k, 'on ' + IN_LABEL[k]])], '', k => { if (!k) return; tree.links[k] = newChild(k); edited(); }) : null));
    const links = Object.entries(tree.links);
    const top = h('div', { class: 'branch' }, rootCard,
      links.length ? h('div', { class: 'kids' }, links.map(([k, ch]) => h('div', { class: 'kid' }, h('div', { class: 'edge' }, h('b', {}, IN_LABEL[k])), branch(ch, tree, k, idxMap, false)))) : null);
    $('tree').replaceChildren(top);
    tree.entries = tree.entries || clone(F[fi].default.entries);
    $('entrytree').replaceChildren(...CL.ENTRIES.map(k => h('div', { style: 'margin:10px 0' }, h('div', { style: 'font-weight:700;margin-bottom:4px' }, ENTRY_LABEL[k]),
      branch(tree.entries[k], null, k, new Map(), !!CL.AIR_MOVES[k]))));
    $('fighter').value = fi;
    showReadout();
  }
  // the editor's "Reset positions" etc. done; first view: the fighter's own tree, as the ROM has it
  { const snap = clone(tree); built = { fi, tree: snap, info: indexInfo(snap) }; }
  builtLabel = $('built').textContent = F[fi].routes_file ? "the fighter's own tree (routes file, in the ROM)" : 'the default tree (in the ROM)';
  render(); draw();
  window.chainlab = { lab, play(script) { for (const part of script.split(',')) { const [n, k] = part.split(':'); override = k.replace('-', ''); stepFrames(Number(n)); } override = null; }, get tree() { return tree; }, set tree(t) { tree = t; render(); }, build, render, stepFrames, data, chains: () => chains };
})();
