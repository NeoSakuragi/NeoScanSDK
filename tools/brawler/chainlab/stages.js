/* Brawler Lab, Stages tab: the campaign's stages (game.json `stages`) edited in the page, played in the in-page game
 * through the data pack (stagepack.js -> lab.installPack, lab.playStage: installed at the stage start, no reload).
 * Data: stages.json (make_site.py: build_tables.py labstages + the stage art + faces). */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const SP = window.StagePack;
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  const svg = (tag, attrs = {}, ...kids) => {
    const e = document.createElementNS('http://www.w3.org/2000/svg', tag);
    for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
    for (const c of kids.flat()) if (c !== null && c !== undefined) e.append(c);
    return e;
  };
  const clone = x => JSON.parse(JSON.stringify(x));
  const sel = (options, value, onchange, attrs = {}) => {
    const s = h('select', Object.assign({ onchange: () => onchange(s.value) }, attrs));
    for (const [v, t] of options) s.add(new Option(t, v)); s.value = String(value); return s;
  };
  const numIn = (value, onchange, attrs = {}) => {
    const i = h('input', Object.assign({ type: 'number', value }, attrs));
    i.onchange = () => { const v = Number(i.value); if (Number.isFinite(v)) onchange(Math.round(v)); };
    return i;
  };

  while (!window.chainlab) await new Promise(r => setTimeout(r, 100));     // app.js: the game is up
  const CLAB = window.chainlab, lab = CLAB.lab;
  let D;
  try { D = await (await fetch('stages.json', { cache: 'no-cache' })).json(); } catch (e) { $('tabStages').disabled = true; return; }
  const ED = () => window.enemiesTab ? window.enemiesTab.stageData(D) : { errors: [], D };   // the Enemies tab's enemies
  const EN = () => (ED().D || D).enemies;
  const ROSTER = D.roster, ORIG = clone(D.stages);
  const DRAFT = 'brawlerlab.stages.' + (lab.layout.version || '');
  let stages = clone(ORIG), si = 0;
  try { const d = JSON.parse(localStorage.getItem(DRAFT)); if (Array.isArray(d) && d.length === ORIG.length) stages = d; } catch (e) { /* none */ }
  const save = () => { try { localStorage.setItem(DRAFT, JSON.stringify(stages)); } catch (e) { /* private window */ } };

  // ---- tabs -------------------------------------------------------------------------------------------------------------
  // three tabs share the game column: the Chain Lab (its tree and readout), Stages, Enemies (enemies.js)
  let active = false;
  const TABS = { chain: ['tabChain', ['treecol', 'clhead', 'readout']], stages: ['tabStages', ['stagecol']], enemies: ['tabEnemies', ['enemycol']], chars: ['tabChars', ['charcol']], select: ['tabSelect', ['selcol']], feedback: ['tabFeedback', ['fbcol']], quirks: ['tabQuirks', ['quirkcol']], expose: ['tabExpose', ['exposecol']], decide: ['tabDecide', ['decidecol']] };
  window.labTab = name => {
    for (const [k, [b, els]] of Object.entries(TABS)) {
      if ($(b)) $(b).classList.toggle('on', k === name);
      for (const id of els) if ($(id)) $(id).hidden = k !== name;
    }
    window.labTabName = name; active = name === 'stages';
    if (active) render();
    window.dispatchEvent(new CustomEvent('labtab', { detail: name }));
    CLAB.draw();
  };
  function tab(on) { window.labTab(on ? 'stages' : 'chain'); }
  $('tabChain').onclick = () => tab(false);
  $('tabStages').onclick = () => tab(true);
  const PHASES = ['', 'GO', 'boss', 'boss beaten', 'stage clear'];
  const MODES = ['select', 'fight', 'title', 'boss unlocked', 'ending'];
  window.labStatus = () => {
    if (!active && window.labTabName !== 'enemies' && window.labTabName !== 'chars') return null;
    const y = lab.layout.syms, r8 = a => (a === undefined ? 0 : lab.r8(a)), cam = y.cam_x === undefined ? 0 : (lab.r16(y.cam_x) << 16 >> 16);
    const m = r8(y.mode), la = lab.r8(lab.lab + 8), act = la === 2 ? 'enemy test' : la ? 'Chain Lab training' : (r8(y.attract) ? 'attract demo' : MODES[m] || m);
    const where = m === 1 && !r8(y.attract) && !la ? `  stage ${r8(y.camp) + 1}  ${r8(y.phase) >= 2 ? 'boss' : 'wave ' + (r8(y.wave) + 1)}  ${PHASES[r8(y.phase)] || ''}  camera x ${cam}` : '';
    const rank = y.ai_rank === undefined ? '' : `  rank ${r8(y.ai_rank)}  attackers ${r8(y.ai_tokens)}`;   // revamp 1B: the hidden rank (only here)
    return `${act}${where}${rank}  pack: ${lab.packStatus()}`;
  };
  // the game.json stage form keeps build_tables.py format's key order: enemy, pick, not_boss, set, x / walk_in, z, tint
  function canon(d) {
    const o = { enemy: d.enemy, pick: d.pick || 0 };
    if (d.not_boss) o.not_boss = true;
    o.set = d.set || 0;
    if (d.walk_in) o.walk_in = { side: d.walk_in.side, rank: d.walk_in.rank || 0 }; else o.x = d.x || 0;
    o.z = d.z;
    if (d.tint && d.tint !== 'none') o.tint = d.tint;
    return o;
  }
  const W = () => D.bgs[stages[si].background] ? D.bgs[stages[si].background].w : 2560;
  function edited() { save(); render(); }

  // ---- faces --------------------------------------------------------------------------------------------------------
  function face(name, small) {
    const i = ROSTER.indexOf(name), s = small ? 16 : 32;
    return h('span', { class: 'face' + (small ? ' small' : ''), title: name, style: `background-image:url(stages/faces.png);background-position:${-i * s}px 0` + (small ? `;background-size:${ROSTER.length * 16}px 16px` : '') });
  }
  function enemyFace(en) {
    const e = EN().find(x => x.name === en);
    if (!e) return h('span', {}, '?');
    if (e.base !== 'pool') return face(e.base);
    return h('span', { class: 'pool', title: 'pool: ' + e.pool.join(', ') }, e.pool.slice(0, 4).map(n => face(n, true)));
  }
  const enemyLabel = e => `${e.name.replace(/_/g, ' ')} (${e.base === 'pool' ? 'pool of ' + e.pool.length : e.base}, ${e.life} life)`;
  const enemyOpts = () => EN().map(e => [e.name, enemyLabel(e)]);
  const songOpts = () => Object.keys(D.songs).map(n => [n, n.replace(/_/g, ' ')]);

  // ---- the pack and play --------------------------------------------------------------------------------------------
  function packNow() { const e = ED(); return e.errors.length ? { bytes: null, errors: ['Enemies tab: ' + e.errors.join('; ')] } : SP.pack(stages, e.D, window.charsTab && window.charsTab.spmap(), window.charsTab && window.charsTab.vtabs()); }
  function showErrors(errs) {
    const e = $('stErr'); e.textContent = errs.length ? 'Not valid (fix these before playing):\n' + errs.join('\n') : ''; e.classList.toggle('show', !!errs.length);
  }
  function soundOn() { if ($('btnSound').textContent.endsWith('off')) $('btnSound').click(); }
  function play(stage, wave) {
    const p = packNow();
    if (!p.bytes) { showErrors(p.errors); return; }
    lab.installPack(p.bytes);
    lab.playStage(Number($('stP1').value), stage, wave);
    if (CLAB.paused) CLAB.togglePause();
    CLAB.stepFrames(1);
  }
  function playSong(name) { soundOn(); lab.playMusic(D.songs[name]); }

  // ---- background picker ---------------------------------------------------------------------------------------------
  function bgPicker() {
    const s = stages[si];
    const close = () => m.remove();
    const m = h('div', { class: 'modal', onclick: e => { if (e.target === m) close(); } },
      h('div', { class: 'sheet' },
        h('div', { class: 'mhead' }, h('b', {}, `Background of ${s.name}`), h('span', {}, 'In this ROM (make_stage_ra.py: Robo Army\'s streets). The others need a ROM build.'), h('button', { onclick: close }, 'Close')),
        h('div', { style: 'overflow:auto' },
          h('div', { class: 'bggrid' }, D.bgs.map(b => h('button', { class: b.i === s.background ? 'cur' : '', onclick: () => {
            s.background = b.i; clampLocks(s); close(); edited(); } },
            h('img', { src: b.img, alt: b.name }), h('span', {}, h('b', {}, `${b.i}: ${b.name}`), ` ${b.w} px`, b.i === s.background ? ' (current)' : '')))),
          h('div', { style: 'padding:0 10px;font-weight:700' }, `Needs a ROM build (${D.other_bgs.length} extracted backgrounds, not in this ROM: a new stage = make_stage_*.py + make)`),
          h('div', { class: 'bggrid' }, D.other_bgs.map(b => h('div', { class: 'nb' }, h('img', { src: b.img, alt: b.name, loading: 'lazy' }),
            h('span', {}, h('b', {}, b.game), ` ${b.name}, ${b.size[0]} x ${b.size[1]} px`), h('span', {}, 'needs a build')))))));
    document.body.append(m);
  }
  function clampLocks(s) {                 // a narrower background: every lock inside it, still in order
    const mx = Math.max(0, (D.bgs[s.background] ? D.bgs[s.background].w : 2560) - 320);
    let prev = 0;
    for (const w of s.waves) { w.lock = Math.max(prev, Math.min(w.lock, mx)); prev = w.lock; }
    s.boss.lock = Math.max(prev, Math.min(s.boss.lock, mx));
    s.boss.x = Math.min(s.boss.x, mx + 320 - 16);
  }

  // ---- the strip: the stage at half size, its lock points as markers you drag ----------------------------------------
  function strip() {
    const s = stages[si], w = W(), bg = D.bgs[s.background], fs = Math.max(14, w / 70), LANE = Math.round(fs * 1.5), nl = s.waves.length + 1, H = 224 + 12 + LANE * nl;
    const root = svg('svg', { class: 'strip', viewBox: `0 0 ${w} ${H}`, preserveAspectRatio: 'xMinYMin meet' });
    root.append(svg('rect', { x: 0, y: 0, width: w, height: H, fill: '#fff' }));
    if (bg) root.append(svg('image', { href: bg.img, x: 0, y: 0, width: w, height: 224, preserveAspectRatio: 'none' }));
    root.append(svg('rect', { x: 0, y: 0, width: w, height: 224, fill: 'none', stroke: '#000', 'stroke-width': Math.max(2, w / 600) }));
    const marks = s.waves.map((wv, k) => ({ label: 'W' + (k + 1), get: () => wv.lock, set: v => { wv.lock = v; }, spawns: wv.spawns, lane: k }));
    marks.push({ label: 'BOSS', get: () => s.boss.lock, set: v => { s.boss.lock = v; }, spawns: s.boss.minions, lane: s.waves.length, boss: true });
    const sw = Math.max(2, w / 500);
    marks.forEach((mk, k) => {
      const x = mk.get(), y0 = 236 + mk.lane * LANE, g = svg('g', { class: 'mk' });
      // the screen at this lock point: a dashed box over the art, the lock line solid
      g.append(svg('rect', { x, y: 2 + (k % 2) * 4, width: 320, height: 216, fill: 'none', stroke: '#000', 'stroke-width': sw, 'stroke-dasharray': `${sw * 4} ${sw * 3}` }));
      g.append(svg('line', { x1: x, y1: 0, x2: x, y2: y0 + LANE - 4, stroke: '#000', 'stroke-width': sw * 2 }));
      const tw = fs * (mk.label.length * 0.62 + 0.8);
      g.append(svg('rect', { x, y: 0, width: tw, height: fs * 1.3, fill: '#fff', stroke: '#000', 'stroke-width': sw }));
      g.append(svg('text', { x: x + fs * 0.35, y: fs * 1.0, 'font-size': fs, 'font-weight': 700, 'font-family': 'system-ui, sans-serif' }, mk.label));
      // its lane: the lock, where each spawn enters (an arrow from its side; a square = placed at x)
      g.append(svg('text', { x: x + fs * 0.3, y: y0 + fs * 0.95, 'font-size': fs * 0.8, 'font-family': 'ui-monospace, monospace' }, `${mk.label} ${x}`));
      for (const d of mk.spawns) {
        const ex = SP.spawnX(d, x), r = fs * 0.45, cy = y0 + LANE / 2 + 2;
        if (!d.walk_in) g.append(svg('rect', { x: ex - r, y: cy - r, width: 2 * r, height: 2 * r, fill: '#000' }));
        else {
          const left = ex < x, tip = left ? ex + r : ex - r, back = left ? ex - r : ex + r;
          g.append(svg('path', { d: `M${back},${cy - r} L${tip},${cy} L${back},${cy + r} Z`, fill: '#fff', stroke: '#000', 'stroke-width': sw }));
        }
      }
      if (mk.boss) {
        const bx = s.boss.x, cy = y0 + LANE / 2 + 2, r = fs * 0.6;
        g.append(svg('circle', { cx: bx, cy, r, fill: '#000' }));
        g.append(svg('text', { x: bx - fs * 2.6, y: cy + fs * 0.35, 'font-size': fs * 0.8, 'font-weight': 700, 'font-family': 'system-ui, sans-serif' }, 'boss'));
      }
      // drag: the lock line, its label or its box
      g.addEventListener('pointerdown', e => {
        e.preventDefault(); g.setPointerCapture(e.pointerId);
        const lo = k ? marks[k - 1].get() : 0, hi = Math.min(k + 1 < marks.length ? marks[k + 1].get() : 1e9, Math.max(0, w - 320));
        const rect = root.getBoundingClientRect(), x0 = mk.get(), cx0 = e.clientX, scale = w / rect.width;
        const mv = ev => { mk.set(Math.max(lo, Math.min(hi, Math.round((x0 + (ev.clientX - cx0) * scale) / 8) * 8))); redrawStrip(); };
        const up = () => { g.removeEventListener('pointermove', mv); g.removeEventListener('pointerup', up); g.removeEventListener('pointercancel', up); edited(); };
        g.addEventListener('pointermove', mv); g.addEventListener('pointerup', up); g.addEventListener('pointercancel', up);
      });
      root.append(g);
    });
    return root;
  }
  function redrawStrip() { const old = $('stStrip'); if (old) old.replaceChildren(strip()); }

  // ---- spawns -------------------------------------------------------------------------------------------------------
  function spawnTable(list, isBoss) {
    const rows = list.map((d, k) => {
      const side = d.walk_in ? d.walk_in.side : 'placed';
      const set = (fn) => { fn(d); list[k] = canon(d); edited(); };
      return h('tr', {},
        h('td', {}, String(k + 1)), h('td', {}, enemyFace(d.enemy)),
        h('td', {}, sel(enemyOpts(), d.enemy, v => set(d => { d.enemy = v; }))),
        h('td', {}, sel([['left', 'from the left'], ['right', 'from the right'], ['placed', 'placed at x']], side, v => set(d => {
          if (v === 'placed') { d.x = d.walk_in ? 200 : d.x; delete d.walk_in; } else d.walk_in = { side: v, rank: d.walk_in ? d.walk_in.rank : 0 };
        }))),
        h('td', {}, d.walk_in ? numIn(d.walk_in.rank || 0, v => set(d => { d.walk_in.rank = v; }), { min: 0, max: 15, title: 'delay: 36 px further off screen per step (main.c spawn_x)' })
                              : numIn(d.x, v => set(d => { d.x = v; }), { title: 'world x' })),
        h('td', {}, numIn(d.z, v => set(d => { d.z = v; }), { min: 0, max: 63, title: 'depth' })),
        h('td', {}, numIn(d.set || 0, v => set(d => { d.set = v; }), { min: 0, max: 255, title: 'colour set (mod the fighter\'s sets)' })),
        h('td', {}, numIn(d.pick || 0, v => set(d => { d.pick = v; }), { min: 0, max: 255, title: 'pool pick (mod the pool left)' })),
        h('td', {}, sel(D.tints.map(t => [t, t]), d.tint || 'none', v => set(d => { d.tint = v; }))),
        isBoss ? h('td', {}, h('label', { title: 'a pool pick equal to the boss takes the next one' }, (() => { const c = h('input', { type: 'checkbox' }); c.checked = !!d.not_boss; c.onchange = () => set(d => { d.not_boss = c.checked; }); return c; })(), ' not boss')) : null,
        h('td', {}, h('button', { onclick: () => { list.splice(k, 1); edited(); }, title: 'remove' }, 'Remove')));
    });
    const head = h('tr', {}, ['#', '', 'Enemy', 'Side', 'Delay / x', 'z', 'Set', 'Pick', 'Tint'].map(t => h('th', {}, t)), isBoss ? h('th', {}, '') : null, h('th', {}, ''));
    return h('div', { style: 'overflow-x:auto' }, h('table', { class: 'sp' }, head, rows));
  }
  function adder(list, max, isBoss) {
    const en = sel(enemyOpts(), EN()[0].name, () => {}), side = sel([['right', 'from the right'], ['left', 'from the left']], 'right', () => {});
    const delay = h('input', { type: 'number', value: 0, min: 0, max: 15 }), count = h('input', { type: 'number', value: 1, min: 1, max: max });
    const free = max - list.length;
    const add = h('button', { disabled: free <= 0, onclick: () => {
      const n = Math.max(1, Math.min(Number(count.value) || 1, max - list.length)), r0 = Math.max(0, Math.min(15, Number(delay.value) || 0));
      const lastPick = list.length ? Math.max(...list.map(d => d.pick || 0)) + 1 : 0;
      for (let k = 0; k < n; k++)
        list.push(canon({ enemy: en.value, pick: lastPick + k, not_boss: isBoss, set: k, walk_in: { side: side.value, rank: Math.min(15, r0 + k) }, z: Math.min(60, 6 + 11 * list.length) }));
      edited();
    } }, 'Add');
    return h('div', { class: 'add' }, 'Add', count, 'x', en, side, 'delay', delay, '(each next one 1 step later)', add,
      h('span', { class: 'note' }, free > 0 ? `${list.length} of ${max}` : `full: ${max} at once (the engine's limit)`));
  }

  // ---- the timeline: per wave (in the order they come), who enters at the lock and who walks in later -----------------
  function timeline() {
    const s = stages[si];
    const groups = s.waves.map((w, k) => ({ name: `Wave ${k + 1}`, lock: w.lock, spawns: w.spawns }));
    groups.push({ name: 'Boss', lock: s.boss.lock, spawns: s.boss.minions, boss: s.boss.enemy });
    const steps = Math.max(1, ...groups.flatMap(g => g.spawns.map(d => d.walk_in ? (d.walk_in.rank || 0) + 1 : 1)));
    const chip = d => h('span', { class: 'chip' }, d.walk_in && d.walk_in.side === 'left' ? '→' : null, enemyFace(d.enemy), d.enemy.replace(/_/g, ' '),
      d.walk_in && d.walk_in.side === 'right' ? '←' : null, d.walk_in ? null : ` at x ${d.x}`);
    const head = h('tr', {}, h('th', {}, 'When'), h('th', {}, 'Camera'), ...Array.from({ length: steps }, (_, k) => h('th', {}, k ? `delay ${k} (+${k * 36} px)` : 'first (placed / delay 0)')));
    const rows = groups.map((g, gi) => h('tr', {}, h('td', {}, h('b', {}, g.name), gi ? h('div', { class: 'note' }, `after ${groups[gi - 1].name.toLowerCase()} is beaten: GO`) : h('div', { class: 'note' }, 'the stage start')),
      h('td', {}, `x ${g.lock}`),
      ...Array.from({ length: steps }, (_, k) => h('td', {}, k === 0 && g.boss ? h('span', { class: 'chip', style: 'border-width:3px' }, enemyFace(g.boss), h('b', {}, g.boss.replace(/_/g, ' ')), ` at x ${s.boss.x}`) : null,
        g.spawns.filter(d => (d.walk_in ? d.walk_in.rank || 0 : 0) === k).map(chip)))));
    return h('div', { style: 'overflow:auto' }, h('table', { class: 'tl' }, head, rows),
      h('div', { class: 'note', style: 'margin-top:4px' }, '→ walks in from the left, ← from the right; a delay step = 36 px further off screen (it arrives later). Time-based spawns: the triggers below.'));
  }

  // ---- triggers: when (camera x / a wave beaten / ticks since the stage or a wave came) -> do (spawn / lock / music /
  // drama / end the stage), game.json stages[].triggers (build_tables.py trigger(), main.c triggers()) ---------------------
  const WHEN = [['camera_x', 'camera x reaches'], ['wave_clear', 'wave beaten'], ['time', 'ticks after']];
  const DO = [['spawn', 'spawn'], ['lock', 'lock the camera at x'], ['music', 'music'], ['drama', 'drama scene'], ['end_stage', 'end the stage']];
  const DO_NEW = { spawn: () => ({ spawn: { enemy: EN()[0].name, side: 'right', count: 2, delay: 60, z: 20 } }), lock: () => ({ lock: 0 }),
                   music: () => ({ music: Object.keys(D.songs)[0] }), drama: () => ({ drama: (D.dramas || [])[0] || '' }), end_stage: () => 'end_stage' };
  function triggerTable(s) {
    const list = s.triggers || [];
    const waveOpts = (stageStart) => [...(stageStart ? [['', 'the stage start']] : []), ...s.waves.map((_, k) => [String(k), `wave ${k + 1}`]), ['boss', 'the boss']];
    const rows = list.map((t, k) => {
      const set = fn => { fn(t); edited(); };
      const kind = Object.keys(t.when).find(x => x !== 'wave'), act = t.do === 'end_stage' ? 'end_stage' : Object.keys(t.do)[0];
      const when = [sel(WHEN, kind, v => set(t => { t.when = v === 'wave_clear' ? { wave_clear: 0 } : { [v]: 0 }; }))];
      if (kind === 'wave_clear') when.push(sel(waveOpts(false), String(t.when.wave_clear), v => set(t => { t.when.wave_clear = v === 'boss' ? 'boss' : Number(v); })));
      else when.push(numIn(t.when[kind], v => set(t => { t.when[kind] = v; }), { min: 0, style: 'width:76px', title: kind === 'time' ? 'ticks (60 a second)' : 'camera x' }));
      if (kind === 'time') when.push(sel(waveOpts(true), t.when.wave === undefined ? '' : String(t.when.wave),
        v => set(t => { if (v === '') delete t.when.wave; else t.when.wave = v === 'boss' ? 'boss' : Number(v); })));
      const what = [sel(DO, act, v => set(t => { t.do = DO_NEW[v](); }))];
      const a = t.do[act];
      if (act === 'spawn') what.push(enemyFace(a.enemy), sel(enemyOpts(), a.enemy, v => set(() => { a.enemy = v; })),
        sel([['right', 'from the right'], ['left', 'from the left']], a.side || 'right', v => set(() => { a.side = v; })),
        ' x', numIn(a.count || 1, v => set(() => { a.count = v; }), { min: 1, max: D.max_enemies, title: 'how many' }),
        ' every', numIn(a.delay || 0, v => set(() => { a.delay = v; }), { min: 0, title: 'ticks between two' }), ' ticks, z',
        numIn(a.z === undefined ? 20 : a.z, v => set(() => { a.z = v; }), { min: 0, max: 61 }));
      else if (act === 'lock') what.push(numIn(a, v => set(t => { t.do.lock = v; }), { step: 8, style: 'width:76px', title: 'held until every enemy on screen is beaten' }));
      else if (act === 'music') what.push(sel(songOpts(), a, v => set(t => { t.do.music = v; })), h('button', { onclick: () => playSong(a) }, '▶'));
      else if (act === 'drama') what.push(sel((D.dramas || []).map(n => [n, n]), a, v => set(t => { t.do.drama = v; })));
      return h('tr', {}, h('td', {}, String(k + 1)), h('td', {}, when), h('td', {}, what),
        h('td', {}, h('button', { onclick: () => { list.splice(k, 1); if (!list.length) delete s.triggers; edited(); }, title: 'remove' }, 'Remove')));
    });
    return h('div', {}, h('div', { style: 'overflow-x:auto' }, h('table', { class: 'sp' }, h('tr', {}, ['#', 'When', 'Do', ''].map(x => h('th', {}, x))), rows)),
      h('div', { class: 'add' }, h('button', { disabled: list.length >= 32, onclick: () => { (s.triggers || (s.triggers = [])).push({ when: { time: 120, wave: 0 }, do: DO_NEW.spawn() }); edited(); } }, 'Add a trigger'),
        h('span', { class: 'note' }, `${list.length} of 32; each fires once a stage (not in the attract demo); a spawn's enemies come one every "delay" ticks into free slots`)));
  }

  // ---- the page -------------------------------------------------------------------------------------------------------
  function render() {
    if (!active) return;
    const s = stages[si], p = packNow();
    const same = JSON.stringify(stages) === JSON.stringify(ORIG);
    const col = $('stagecol');
    const p1 = $('stP1') ? $('stP1').value : String(Math.max(0, ROSTER.indexOf('terry')));
    const bg = D.bgs[s.background];
    col.replaceChildren(...[
      h('div', { class: 'row' },
        h('label', {}, 'P1 ', sel(ROSTER.map((n, i) => [i, n.toUpperCase().replace(/_/g, ' ')]), p1, () => {}, { id: 'stP1' })),
        h('button', { onclick: () => play(si, 0) }, `Play ${s.name}`),
        h('button', { onclick: () => play(si, s.waves.length) }, 'Play the boss'),
        h('button', { onclick: () => { lab.installPack(null); CLAB.stepFrames(1); }, title: 'lab.load 4: the ROM\'s own tables from the next safe point' }, "Back to the ROM's tables"),
        h('span', { class: 'ok' }, p.bytes ? `pack ${p.bytes.length} bytes${same ? ' = today\'s campaign (no edit)' : ', edited'}` : 'pack: not valid')),
      h('div', { class: 'row' },
        h('button', { onclick: () => download(`stage${si + 1}.json`, SP.fmt(s) + '\n') }, 'Export this stage'),
        h('button', { onclick: () => download('stages.json', SP.fmt({ stages }) + '\n'), title: 'game.json\'s "stages", in its layout: merge it into game.json' }, 'Export all stages'),
        h('button', { onclick: () => $('stFile').click() }, 'Import JSON'),
        h('button', { disabled: same, onclick: () => { if (confirm('Drop every edit and go back to today\'s campaign?')) { stages = clone(ORIG); edited(); } } }, "Today's campaign"),
        h('input', { id: 'stFile', type: 'file', accept: '.json,application/json', hidden: true, onchange: importFile })),
      h('div', { id: 'stErr' }),
      h('nav', { id: 'stList' }, stages.map((x, k) => h('button', { class: k === si ? 'on' : '', onclick: () => { si = k; render(); } },
        h('b', {}, x.name), h('br'), `bg ${x.background}, ${x.music.replace(/_/g, ' ').toLowerCase()}`, h('br'), `${x.waves.length} waves, boss ${x.boss.enemy.replace(/_/g, ' ')}`,
        JSON.stringify(x) === JSON.stringify(ORIG[k]) ? null : h('span', {}, h('br'), h('b', {}, 'edited'))))),
      h('div', { class: 'box' }, h('h2', {}, s.name, h('span', { class: 'sp' })),
        h('div', { class: 'in stg' },
          h('div', { style: 'flex:1 1 100%' }, h('div', {}, 'Background ', h('b', {}, bg ? `${bg.i}: ${bg.name}, ${bg.w} px` : `${s.background}: not in this ROM`), ' ', h('button', { onclick: bgPicker }, 'Change…')), bg ? h('img', { class: 'bgcur', src: bg.img, alt: bg.name, style: 'max-width:100%;height:auto;margin-top:4px' }) : null),
          h('label', {}, 'Music', sel(songOpts(), s.music, v => { s.music = v; edited(); }), h('button', { onclick: () => playSong(s.music), title: 'played by the game in the page (turns the sound on)' }, '▶ Play')),
          h('label', {}, 'Power', numIn(s.power || 0, v => { s.power = v; edited(); }, { min: 0, max: 255, title: 'its enemies\' extra damage a hit' })))),
      h('div', { class: 'box' }, h('h2', {}, 'Wave designer', h('span', { class: 'note', style: 'font-weight:400' }, 'drag a lock point (W1, W2, …, BOSS) along the stage; the dashed box is the screen there; ▶ walks in, ■ placed, ● the boss'), h('span', { class: 'sp' })),
        h('div', { class: 'in', id: 'stStrip' }, strip())),
      h('div', { class: 'box' }, h('h2', {}, 'Timeline: who comes in when'), h('div', { class: 'in' }, timeline())),
      h('div', { class: 'box' }, h('h2', {}, 'Triggers', h('span', { class: 'note', style: 'font-weight:400' }, 'time-delayed spawns, camera locks, music changes, drama scenes'), h('span', { class: 'sp' })),
        h('div', { class: 'in' }, triggerTable(s))),
      s.waves.map((w, k) => h('div', { class: 'wave' },
        h('div', { class: 'wh' }, h('b', {}, `Wave ${k + 1}`),
          h('label', {}, 'lock x ', numIn(w.lock, v => { w.lock = v; edited(); }, { step: 8, style: 'width:76px' })),
          h('label', {}, 'seed ', (() => { const i = h('input', { value: w.seed, style: 'width:80px' }); i.onchange = () => { w.seed = i.value; edited(); }; return i; })()),
          h('button', { onclick: () => play(si, k) }, '▶ Play from here'),
          h('button', { onclick: () => { s.waves.splice(k + 1, 0, { lock: w.lock, seed: '0x' + ((SP.num(w.seed) + 1) & 0xFFFF).toString(16).toUpperCase(), spawns: [canon({ enemy: EN()[0].name, pick: 0, set: 0, walk_in: { side: 'right', rank: 0 }, z: 6 })] }); edited(); } }, 'Insert a wave after'),
          h('button', { disabled: s.waves.length <= 1, onclick: () => { s.waves.splice(k, 1); edited(); } }, 'Remove wave')),
        spawnTable(w.spawns, false), adder(w.spawns, D.max_enemies, false))),
      h('div', { class: 'wave' },
        h('div', { class: 'wh' }, h('b', {}, 'Boss'), enemyFace(s.boss.enemy),
          sel(enemyOpts(), s.boss.enemy, v => { s.boss.enemy = v; edited(); }),
          h('label', {}, 'song ', sel(songOpts(), s.boss.song, v => { s.boss.song = v; edited(); }), h('button', { onclick: () => playSong(s.boss.song) }, '▶ Play')),
          h('label', {}, 'lock x ', numIn(s.boss.lock, v => { s.boss.lock = v; edited(); }, { step: 8, style: 'width:76px' })),
          h('label', {}, 'x ', numIn(s.boss.x, v => { s.boss.x = v; edited(); }, { style: 'width:76px' })),
          h('label', {}, 'z ', numIn(s.boss.z, v => { s.boss.z = v; edited(); }, { min: 0, max: 63 })),
          h('label', {}, 'seed ', (() => { const i = h('input', { value: s.boss.seed, style: 'width:80px' }); i.onchange = () => { s.boss.seed = i.value; edited(); }; return i; })()),
          h('label', { title: 'played as the boss walks in, before its song (game.json dramas)' }, 'scene ', sel([['', 'none'], ...(D.dramas || []).map(n => [n, n])], s.boss.drama || '', v => { if (v) s.boss.drama = v; else delete s.boss.drama; edited(); })),
          h('button', { onclick: () => play(si, s.waves.length) }, '▶ Play from here')),
        h('div', { class: 'note', style: 'padding:2px 8px' }, 'Minions with the boss:'),
        spawnTable(s.boss.minions, true), adder(s.boss.minions, D.max_enemies - 1, true))].flat());
    showErrors(p.errors);
  }
  function download(name, text) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' })); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  async function importFile() {
    const f = $('stFile').files[0]; if (!f) return;
    try {
      const j = JSON.parse(await f.text());
      if (Array.isArray(j) || (j && Array.isArray(j.stages))) {
        const list = Array.isArray(j) ? j : j.stages;
        if (list.length !== ORIG.length) throw new Error(`${list.length} stages: the ROM has ${ORIG.length}`);
        stages = list;
      } else if (j && Array.isArray(j.waves) && j.boss) stages[si] = j;
      else throw new Error('not a stage, a stages list or a game.json');
      edited();
    } catch (e) { showErrors(['Import: ' + e.message]); }
  }
  window.stagesTab = { get stages() { return stages; }, set stages(v) { stages = v; edited(); }, play, pack: packNow, select(k) { si = k; render(); }, tab, D };
})();
