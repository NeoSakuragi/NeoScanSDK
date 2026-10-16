/* Brawler Lab, Sessions tab: the LIVE WALL (game.html#wall; docs/feedback.md "Session recording", "The live wall").
 * Every LIVE session (a chunk in the last 15 s) in a grid of tiles: auto (1 / 2x2 / 3x3 by how many play; 1 column of
 * up to 2 on a phone) or chosen. New live sessions join by themselves; a session that ended leaves 5 s later unless it
 * is pinned. Each tile = one Web Worker (wall_worker.js) with its own wasm core, so the tiles run in parallel on the
 * machine's cores: it joins at the latest keyframe, fast-forwards silently and follows the chunks as they arrive (the
 * single view's live path), drift-checked at every chunk boundary (state SHA-256). Tile header: player, build, LIVE /
 * ENDED, the drift check, how far behind the newest chunk; then what the game shows (sessinfo.js, from the tile's RAM
 * every frame). Tap a tile = hear it (only one tile sounds); double-tap = full size (the single view, sessions.js);
 * "Back to the wall" returns. The page compiles core.wasm once and hands the module to every worker. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  while (!window.labTab || !window.labSess) await new Promise(r => setTimeout(r, 100));
  const col = $('sesscol'); if (!col) return;
  const API = window.labSess.API, ABS = new URL(API, location.href).href;
  const GONE_MS = 5000, POLL_MS = 2000, TILE_POLL_MS = 1000;
  const css = document.createElement('style');
  css.textContent = `
#sesscol.walling { max-width: none; }
#sesscol.walling > .listpart { display: none; }
#sesscol .wall .wbar { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; margin: 4px 0 8px; font-size: 14px; }
#sesscol .wall .wbar button { min-height: 36px; min-width: 44px; font-size: 14px; border: 2px solid #000; background: #fff; color: #000; }
#sesscol .wall .wbar button.on { background: #000; color: #fff; font-weight: 700; }
#sesscol .wall .grid { display: grid; gap: 6px; }
#sesscol .wall .tile { border: 2px solid #000; background: #fff; color: #000; min-width: 0; cursor: pointer; user-select: none; }
#sesscol .wall .tile.heard { outline: 4px solid #000; outline-offset: -1px; }
#sesscol .wall .tile .th { display: flex; gap: 6px; align-items: baseline; padding: 2px 4px; font: 12px/1.3 ui-monospace, monospace; border-bottom: 1px solid #000; flex-wrap: wrap; }
#sesscol .wall .tile .th b { font-size: 13px; }
#sesscol .wall .tile .th .sp { flex: 1; }
#sesscol .wall .tile .th button { font-size: 12px; min-height: 26px; padding: 0 6px; border: 1px solid #000; background: #fff; color: #000; }
#sesscol .wall .tile .th button.on { background: #000; color: #fff; }
#sesscol .wall .tile .ti { padding: 1px 4px; font: 12px/1.3 ui-monospace, monospace; min-height: 1.3em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
#sesscol .wall .tile canvas { display: block; width: 100%; height: auto; aspect-ratio: 320 / 224; image-rendering: pixelated; background: #000; border: 0; max-width: none; }
#sesscol .wall .more { font-size: 13px; margin: 6px 0; }`;
  document.head.append(css);

  // the Sessions tab's own parts (the list, the player) hide while the wall shows
  for (const el of [...col.children]) el.classList.add('listpart');
  const head = col.querySelector('h2'); if (head) head.classList.remove('listpart');
  const bOpen = h('button', { onclick: () => (opened ? closeWall() : openWall()) }, 'Live wall');
  if (head) head.append(bOpen);

  const phone = () => innerWidth < 700;
  let limitSel = 'auto';
  const sel = [['auto', 'Auto'], ['1', '1'], ['4', '2×2'], ['9', '3×3']].map(([k, t]) => h('button', { class: k === 'auto' ? 'on' : '', onclick: () => { limitSel = k; sel.forEach(b => b.classList.toggle('on', b.dataset.k === k)); layout(); poll(); } }, t));
  sel.forEach((b, i) => { b.dataset.k = ['auto', '1', '4', '9'][i]; });
  const bMute = h('button', { onclick: () => hear(null) }, 'Mute');
  const bBack = h('button', { hidden: true, onclick: () => back() }, '← Back to the wall');
  const sum = h('span', { class: 'mono' }, '');
  const grid = h('div', { class: 'grid' }), more = h('p', { class: 'more' });
  const wall = h('div', { class: 'wall', hidden: true }, h('div', { class: 'wbar' }, 'Tiles', ...sel, bMute, bBack, sum), grid, more);
  (head || col.firstChild).after(wall);

  let opened = false, full = null, listT = 0, statT = 0, module = null, ac = null, at = 0, heard = null;
  const tiles = new Map();                                 // session id -> tile
  const limit = () => { const n = limitSel === 'auto' ? 9 : +limitSel; return phone() ? Math.min(n, 2) : n; };
  function layout() {
    const n = Math.max(1, Math.min(tiles.size, limit()));
    const cols = phone() ? 1 : limitSel === 'auto' ? (n <= 1 ? 1 : n <= 4 ? 2 : 3) : Math.round(Math.sqrt(+limitSel));
    grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
    const rows = Math.ceil(n / cols), tw = Math.max(240, ((innerHeight - 160) / rows - 46) / 0.7);   // every row in the window (a tile: 2 text lines + 320x224)
    grid.style.maxWidth = phone() ? '' : Math.round(Math.min(cols === 1 ? 640 : 1e4, tw) * cols + 6 * (cols - 1)) + 'px';
  }
  const get = async (url, what) => { const r = await fetch(url, { credentials: 'same-origin', cache: 'no-store' }); if (!r.ok) throw new Error(what + ': HTTP ' + r.status); return new Uint8Array(await r.arrayBuffer()); };
  async function wasm() {
    if (!module) module = (async () => {
      try { return await WebAssembly.compileStreaming(fetch('core.wasm', { credentials: 'same-origin' })); }
      catch (e) { return WebAssembly.compile(await (await fetch('core.wasm', { credentials: 'same-origin' })).arrayBuffer()); }
    })();
    return module;
  }
  const roms = window.labRoms = window.labRoms || {}, romLoad = {};
  async function rom(r) {
    if (roms[r.rom_sha]) return roms[r.rom_sha];
    if (!romLoad[r.rom_sha]) romLoad[r.rom_sha] = get(API + 'rom/' + r.rom_sha, 'game build ' + r.rom_version).then(b => (roms[r.rom_sha] = b));
    return romLoad[r.rom_sha];
  }

  function addTile(r) {
    const cv = h('canvas', { width: 320, height: 224 });
    const live = h('b', {}, '● LIVE'), drift = h('span', {}, 'loading…'), lag = h('span', {}, '');
    const bPin = h('button', { onclick: e => { e.stopPropagation(); t.pinned = !t.pinned; bPin.classList.toggle('on', t.pinned); bPin.textContent = t.pinned ? 'Pinned' : 'Pin'; } }, 'Pin');
    const inf = h('div', { class: 'ti' }, '—');
    const el = h('div', { class: 'tile', title: 'Tap: hear this one · double-tap: full size' },
      h('div', { class: 'th' }, live, h('b', {}, r.user), h('span', {}, r.rom_version), drift, lag, h('span', { class: 'sp' }), bPin), inf, cv);
    const t = { row: r, el, cv, inf, live, drift, lag, pinned: false, gone: 0, st: null, worker: null, err: null, lastTap: 0 };
    el.onclick = () => {
      const now = performance.now();
      if (now - t.lastTap < 350) { t.lastTap = 0; goFull(t); return; }
      t.lastTap = now; hear(t);
    };
    tiles.set(r.id, t); grid.append(el); layout();
    start(t).catch(e => { t.err = e.message; drift.textContent = 'unavailable: ' + e.message; });
    return t;
  }
  async function start(t) {
    const r = t.row;
    const [mod, romBytes] = await Promise.all([wasm(), rom(r), window.labBios ? null : get('neogeo.zip', 'BIOS').then(b => (window.labBios = b))]);
    if (!tiles.has(r.id)) return;
    const syms = window.SessInfo ? await SessInfo.syms(r.rom_sha) : null;
    const off = t.cv.transferControlToOffscreen();
    const w = t.worker = new Worker('wall_worker.js');
    w.onmessage = ev => {
      const m = ev.data;
      if (m.type === 'status') { t.st = m; paint(t); }
      else if (m.type === 'audio') { t.audioN = (t.audioN || 0) + 1; play(t, m); }   // (audioN: the proof's count of what this worker sent)
      else if (m.type === 'error') { t.err = m.error; t.drift.textContent = 'unavailable: ' + m.error; }
    };
    w.onerror = e => { t.err = e.message || 'worker error'; t.drift.textContent = t.err; };
    w.postMessage({ type: 'init', id: r.id, row: r, api: ABS, module: mod, bios: window.labBios, rom: romBytes, canvas: off, syms, poll: TILE_POLL_MS }, [off]);
    if (heard === t) w.postMessage({ type: 'sound', on: true });
    if (full || document.hidden) w.postMessage({ type: 'pause' });
  }
  function paint(t) {
    const s = t.st; if (!s) return;
    t.live.textContent = s.live ? '● LIVE' : 'ENDED';
    t.drift.textContent = s.checked ? (s.mismatches.length ? `✗ differs at ${s.mismatches[0]}` : `✓ ${s.checked} same`) : 'checking…';
    if (s.gaps.length) t.drift.textContent += ' · gap';
    if (s.drift) t.drift.textContent += ' · drifting';
    t.lag.textContent = s.paused ? 'paused' : s.catching ? 'catching up' : `${s.lag.toFixed(1)} s behind`;
    t.inf.textContent = window.SessInfo ? SessInfo.text(s.info) : '';
  }
  function removeTile(t) {
    if (t.worker) t.worker.postMessage({ type: 'stop' });
    if (t.worker) setTimeout(() => t.worker.terminate(), 200);
    t.el.remove(); tiles.delete(t.row.id); if (heard === t) heard = null; layout();
  }
  function hear(t) {
    if (t && !ac) ac = new AudioContext();
    if (ac && ac.state === 'suspended') ac.resume();
    heard = t; at = 0;
    for (const x of tiles.values()) { x.el.classList.toggle('heard', x === t); if (x.worker) x.worker.postMessage({ type: 'sound', on: x === t }); }
  }
  function play(t, m) {
    if (heard !== t || !ac) return;
    const a = m.pcm, n = a.length / 2, b = ac.createBuffer(2, n, m.rate), L = b.getChannelData(0), R = b.getChannelData(1);
    for (let i = 0; i < n; i++) { L[i] = a[2 * i] / 32768; R[i] = a[2 * i + 1] / 32768; }
    const src = ac.createBufferSource(); src.buffer = b; src.connect(ac.destination);
    if (at < ac.currentTime || at > ac.currentTime + 0.3) at = ac.currentTime + 0.06;   // (behind or too far ahead: re-anchor)
    src.start(at); at += n / m.rate;
  }
  function pauseAll(p) { for (const t of tiles.values()) if (t.worker) t.worker.postMessage({ type: p ? 'pause' : 'resume' }); }
  function goFull(t) {
    full = t; hear(null); pauseAll(true);
    grid.hidden = true; more.hidden = true; bBack.hidden = false; sel.forEach(b => (b.hidden = true)); bMute.hidden = true;
    col.classList.remove('walling');
    window.labSess.watch(t.row);
    scrollTo({ top: col.offsetTop, behavior: 'instant' });
  }
  function back() {
    window.labSess.close(); full = null;
    grid.hidden = false; more.hidden = false; bBack.hidden = true; sel.forEach(b => (b.hidden = false)); bMute.hidden = false;
    col.classList.add('walling'); pauseAll(false);
  }

  async function poll() {
    if (!opened) return;
    let j;
    try { j = await (await fetch(API + 'sessions?limit=60', { credentials: 'same-origin', cache: 'no-store' })).json(); }
    catch (e) { sum.textContent = 'Sessions unavailable: ' + e.message; return; }
    const now = Date.now(), byId = new Map(j.sessions.map(r => [r.id, r]));
    for (const t of [...tiles.values()]) {                 // ended: leave GONE_MS later (not a pinned one)
      const r = byId.get(t.row.id);
      if (r && r.live) { t.gone = 0; Object.assign(t.row, r); continue; }
      t.gone = t.gone || now;
      if (!t.pinned && now - t.gone > GONE_MS && full !== t) removeTile(t);
    }
    const lv = j.sessions.filter(r => r.live && !tiles.has(r.id));
    while (lv.length && tiles.size < limit()) addTile(lv.shift());
    while (tiles.size > limit()) {                          // fewer tiles chosen: the unpinned, then the oldest go
      const t = [...tiles.values()].sort((a, b) => (a.pinned - b.pinned) || (a.row.last_at - b.row.last_at))[0]; removeTile(t);
    }
    const nlive = j.sessions.filter(r => r.live).length;
    more.textContent = lv.length ? `+${lv.length} more live: ${lv.slice(0, 6).map(r => r.user).join(', ')}${lv.length > 6 ? '…' : ''} (more tiles: 3×3, or unpin one)` : '';
    sum.textContent = `${nlive} live · ${tiles.size} shown`;
    if (!tiles.size && !nlive) more.textContent = 'Nobody is playing right now: a session joins here as soon as its first chunk arrives.';
  }
  function openWall() {
    opened = true; bOpen.classList.add('on'); bOpen.textContent = 'Close the wall';
    window.labSess.close(); wall.hidden = false; col.classList.add('walling'); layout();
    poll(); listT = setInterval(poll, POLL_MS);
    if (location.hash !== '#wall') history.replaceState(null, '', '#wall');
  }
  function closeWall() {
    opened = false; bOpen.classList.remove('on'); bOpen.textContent = 'Live wall';
    if (full) { window.labSess.close(); full = null; }
    clearInterval(listT); for (const t of [...tiles.values()]) removeTile(t);
    wall.hidden = true; col.classList.remove('walling'); bBack.hidden = true; grid.hidden = false; more.hidden = false; sel.forEach(b => (b.hidden = false)); bMute.hidden = false;
    if (location.hash === '#wall') history.replaceState(null, '', '#sessions');
  }
  window.addEventListener('labtab', e => { if (e.detail !== 'sessions' && opened) closeWall(); });
  document.addEventListener('visibilitychange', () => { if (opened && !full) pauseAll(document.hidden); });
  addEventListener('resize', () => { if (opened) { layout(); poll(); } });
  /** for the measurements (wall_measure.js): every tile's last status */
  window.labWall = { open: openWall, close: closeWall, tiles: () => [...tiles.values()].map(t => ({ id: t.row.id, err: t.err, audio: t.audioN || 0, ...(t.st || {}) })) };
  if (location.hash === '#wall') { window.labTab('sessions'); openWall(); }
})();
