/* Brawler Lab, Select screen tab (Bruno 2026-10-07: "a page in the lab where I can actually position the characters
 * myself, and you will apply the positioning in the game"). The game's select screen drawn by selectrender.js from
 * select.json (select_images.py: the ROM's pictures, palettes, fix layer), pixel for pixel as our emulator shows it.
 * Drag a fighter (whole pixels; the arrow keys nudge the selected one 1 px, Shift 8 px), change its draw order, flip
 * it, pick its pose; drag the stick's order. Indicators: sprites per line (the LSPC's 96), what the cursor's arrow
 * lands on. Save = the feedback service (feedback-api/select_layout, server.py), which
 * tools/brawler/select_layout.py pulls into game.json "select_layout" for the build. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const R = window.SelectRender;
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  const clone = x => JSON.parse(JSON.stringify(x));
  const col = $('selcol'), tabBtn = $('tabSelect');
  if (!col || !tabBtn) return;
  let D;
  try { D = await (await fetch('select.json', { cache: 'no-cache' })).json(); } catch (e) { tabBtn.disabled = true; return; }
  R.prepare(D);
  const API = 'feedback-api/select_layout';
  const GAME = clone(D.layout);                  // the build's layout (select.json)
  const DRAFT = 'brawlerlab.select.' + D.version;
  let L = clone(GAME), sel = null, cursor = null, unlocked = false, last = null, scale = 3, saved = null;
  try { const d = JSON.parse(localStorage.getItem(DRAFT)); if (d && Object.keys(d).length === Object.keys(GAME).length && Object.keys(d).every(n => GAME[n])) L = d; } catch (e) { /* none */ }
  const undo = [];
  const keep = () => { try { localStorage.setItem(DRAFT, JSON.stringify(L)); } catch (e) { /* private window */ } };
  const snapshot = () => { undo.push(JSON.stringify(L)); if (undo.length > 100) undo.shift(); };
  const disp = n => D.fighters[n].name;
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

  // ---- the page -----------------------------------------------------------------------------------------------------
  const status = h('span', { id: 'selStatus', class: 'note' });
  const cv = h('canvas', { id: 'selScreen', width: 320, height: 224 });        // the game's pixels, 1:1 (the proof reads it)
  const view = h('canvas', { id: 'selView', tabindex: 0 });                     // scaled, + the editor's marks
  const strip = h('canvas', { id: 'selLines' });                                // sprites per line
  const side = h('div', { id: 'selSide' }), orderBox = h('div', { id: 'selOrder' }), checks = h('div', { id: 'selChecks' });
  const worstLine = h('div', { id: 'selWorst' });
  const cursorSel = h('select', { onchange: e => { cursor = e.target.value; draw(); } });
  const bossSel = h('select', { onchange: e => { unlocked = e.target.value === '1'; draw(); } },
    h('option', { value: '0' }, 'locked (a fresh game: silhouettes)'), h('option', { value: '1' }, 'beaten (in colour / grey)'));
  const scaleSel = h('select', { onchange: e => { scale = Number(e.target.value); draw(); } }, [2, 3, 4].map(s => h('option', { value: s }, s + 'x')));
  scaleSel.value = String(scale);
  col.append(
    h('div', { class: 'box' },
      h('h2', {}, h('span', {}, 'Select screen: the group photo'),
        h('span', { class: 'note' }, `build ${D.version} · drag a fighter; arrow keys nudge the selected one 1 px (Shift: 8 px)`), h('span', { class: 'sp' }),
        h('button', { id: 'selSave', onclick: save }, 'Save'), h('button', { onclick: loadSaved }, 'Load saved'),
        h('button', { onclick: () => { snapshot(); L = clone(GAME); edited(); } }, 'Load current game layout'),
        h('button', { onclick: () => { if (undo.length) { L = JSON.parse(undo.pop()); edited(); } } }, 'Undo')),
      h('div', { class: 'in' },
        h('div', { class: 'row' }, h('label', {}, 'Cursor on ', cursorSel), h('label', {}, 'Bosses ', bossSel), h('label', {}, 'Scale ', scaleSel), status),
        h('div', { id: 'selStage' }, h('div', { id: 'selWrap' }, view), h('div', { id: 'selStripWrap' }, strip)),
        worstLine,
        h('div', { class: 'note' }, 'The 8 px hatched at each side are outside a TV picture (the LSPC line is 320 px, a TV shows 304). ' +
          'The strip on the right counts the sprites on each line as the LSPC does (96 at most; past it the later sprites vanish): ' +
          'lines past 96 are hatched across the picture and the strip.'))),
    h('div', { class: 'box' }, h('h2', {}, h('span', {}, 'Selected fighter')), side),
    h('div', { class: 'box' }, h('h2', {}, h('span', {}, 'The stick\'s order'), h('span', { class: 'note' }, 'left / right step through this list (drag a row, or ↑ ↓); up / down go to the nearest fighter higher / lower')), orderBox),
    h('div', { class: 'box' }, h('h2', {}, h('span', {}, 'Where the cursor\'s arrow lands'), h('span', { class: 'note' }, '"1P" and the arrow are drawn over the sprites: a fighter listed here has part of him covered')), checks));
  cv.hidden = true; col.append(cv);

  // ---- drawing --------------------------------------------------------------------------------------------------------
  const hatch = (() => { const c = document.createElement('canvas'); c.width = c.height = 8; const x = c.getContext('2d');
    x.fillStyle = '#fff'; x.fillRect(0, 0, 8, 8); x.strokeStyle = '#000'; x.lineWidth = 2; x.beginPath(); x.moveTo(0, 8); x.lineTo(8, 0); x.moveTo(-2, 2); x.lineTo(2, -2); x.moveTo(6, 10); x.lineTo(10, 6); x.stroke(); return c; })();
  function draw() {
    const order = R.order(L);
    if (!cursor || !L[cursor]) cursor = R.firstCursor(D, L, { unlocked });
    cursorSel.replaceChildren(...order.map(n => h('option', { value: n }, disp(n) + (D.fighters[n].locked && !unlocked ? ' (locked: not selectable)' : ''))));
    cursorSel.value = cursor;
    last = R.render(D, L, { cursor, unlocked });
    const cx = cv.getContext('2d'); cx.putImageData(new ImageData(last.rgba, 320, 224), 0, 0);
    view.width = 320 * scale; view.height = 224 * scale;
    const v = view.getContext('2d'); v.imageSmoothingEnabled = false;
    v.drawImage(cv, 0, 0, 320 * scale, 224 * scale);
    const pat = v.createPattern(hatch, 'repeat');
    v.save(); v.globalAlpha = 0.55; v.fillStyle = pat; v.fillRect(0, 0, 8 * scale, 224 * scale); v.fillRect(312 * scale, 0, 8 * scale, 224 * scale); v.restore();
    for (let l = 0; l < 224; l++) if (last.counts[l] > D.line_max) { v.save(); v.globalAlpha = 0.6; v.fillStyle = pat; v.fillRect(0, l * scale, 320 * scale, scale); v.restore(); }
    if (sel) {                                   // the selected fighter: a box around its pixels, black and white dashes
      let x0 = 1e9, y0 = 1e9, x1 = -1, y1 = -1; const k = last.names.indexOf(sel);
      for (let i = 0; i < 320 * 224; i++) if (last.owner[i] === k) { const x = i % 320, y = (i / 320) | 0; if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
      if (x1 >= 0) for (const [c, off] of [['#fff', 0], ['#000', 4]]) { v.strokeStyle = c; v.lineWidth = 2; v.setLineDash([4, 4]); v.lineDashOffset = off; v.strokeRect(x0 * scale - 2, y0 * scale - 2, (x1 - x0 + 1) * scale + 4, (y1 - y0 + 1) * scale + 4); }
      v.setLineDash([]);
      const f = L[sel];                          // its feet: a cross
      v.strokeStyle = '#000'; v.lineWidth = 3; v.beginPath(); v.moveTo((f.x - 4) * scale, f.y * scale); v.lineTo((f.x + 4) * scale, f.y * scale); v.moveTo(f.x * scale, (f.y - 4) * scale); v.lineTo(f.x * scale, (f.y + 4) * scale); v.stroke();
      v.strokeStyle = '#fff'; v.lineWidth = 1; v.stroke();
    }
    // the strip: a bar per line, the 96 limit a solid line, lines past it hatched
    const SW = 120; strip.width = SW; strip.height = 224 * scale;
    const s = strip.getContext('2d'); s.fillStyle = '#fff'; s.fillRect(0, 0, SW, strip.height);
    const mx = Math.max(D.line_max + 8, ...last.counts), px = c => Math.round(c / mx * (SW - 4));
    for (let l = 0; l < 224; l++) {
      const c = last.counts[l]; if (!c) continue;
      s.fillStyle = c > D.line_max ? s.createPattern(hatch, 'repeat') : '#000';
      s.fillRect(0, l * scale, px(c), scale);
      if (c > D.line_max) { s.strokeStyle = '#000'; s.lineWidth = 1; s.strokeRect(0.5, l * scale + 0.5, px(c) - 1, scale - 1); }
    }
    s.strokeStyle = '#000'; s.lineWidth = 2; s.beginPath(); s.moveTo(px(D.line_max), 0); s.lineTo(px(D.line_max), strip.height); s.stroke();
    s.fillStyle = '#000'; s.font = '11px system-ui'; s.fillText('96', px(D.line_max) + 3, 12);
    const w = last.worst, over = [...last.counts].filter(c => c > D.line_max).length;
    worstLine.replaceChildren(h('b', {}, `Worst line: y ${w}, ${last.counts[w]} sprites of 96`),
      over ? h('span', { class: 'warn' }, ` · ${over} line${over > 1 ? 's' : ''} PAST 96: the game hides fighters there (line guard) or the LSPC drops sprites`) : ' · every line within 96');
    renderSide(); renderOrder(); renderChecks();
    const ch = same(L, GAME) ? 'the current game layout' : saved && same(L, saved.layout) ? `the saved layout (${saved.saved})` : 'edited (not saved)';
    status.textContent = ch;
  }
  function edited() { keep(); draw(); }

  // ---- the selected fighter: place, facing, draw order, pose -------------------------------------------------------------
  function poseThumb(n, P) {                    // the pose in colour, 1x, on the page's white
    const c = document.createElement('canvas'); c.width = P.w; c.height = P.h; const x = c.getContext('2d'), im = x.createImageData(P.w, P.h);
    for (let i = 0; i < P.w * P.h; i++) { const k = P.px[i]; if (!(k & 15)) continue; const [r, g, b] = R.rgb(D, P.pals[k]); im.data.set([r, g, b, 255], 4 * i); }
    x.putImageData(im, 0, 0);
    let out = c;
    if (L[n].facing === 'right') { out = document.createElement('canvas'); out.width = P.w; out.height = P.h; const y = out.getContext('2d'); y.translate(P.w, 0); y.scale(-1, 1); y.drawImage(c, 0, 0); }
    out.style.width = P.w * 1.5 + 'px'; out.style.height = P.h * 1.5 + 'px';
    return out;
  }
  function setZ(n, to) {                         // move n to draw rank `to`, the others closing up
    const ranks = Object.keys(L).sort((a, b) => L[a].z - L[b].z).filter(m => m !== n);
    ranks.splice(Math.max(0, Math.min(ranks.length, to)), 0, n);
    ranks.forEach((m, k) => { L[m].z = k; });
  }
  function renderSide() {
    if (!sel) { side.replaceChildren(h('div', { class: 'in note' }, 'Tap a fighter on the picture to select him.')); return; }
    const n = sel, f = L[n], N = Object.keys(L).length, F = D.fighters[n];
    const num = (k, lo, hi) => { const i = h('input', { type: 'number', value: f[k], min: lo, max: hi, step: 1 });
      i.onchange = () => { const v = Math.round(Number(i.value)); if (Number.isFinite(v)) { snapshot(); f[k] = Math.max(lo, Math.min(hi, v)); edited(); } }; return i; };
    const zb = (label, to) => h('button', { onclick: () => { snapshot(); setZ(n, to); edited(); } }, label);
    const poses = h('div', { class: 'poses' }, F.poses.map(P => h('button', { class: 'pose' + (P.alias.some(a => same(a, f.pose)) ? ' cur' : ''), title: `state ${P.pose[0]}, step ${P.pose[1]}`,
      onclick: () => { snapshot(); f.pose = P.pose.slice(); edited(); } }, poseThumb(n, P), h('span', {}, `${P.pose[0]} / ${P.pose[1] < 0 ? 'last' : P.pose[1]}`, P.rom ? h('b', {}, ' (in the ROM)') : null))));
    side.replaceChildren(h('div', { class: 'in' },
      h('div', { class: 'row' }, h('b', { style: 'font-size:16px' }, disp(n)), h('span', { class: 'note' }, F.locked ? 'a boss: locked until beaten' : 'always playable'),
        h('label', {}, 'x ', num('x', -64, 383)), h('label', {}, 'y (feet) ', num('y', 0, 300)),
        h('button', { onclick: () => { snapshot(); f.facing = f.facing === 'right' ? 'left' : 'right'; edited(); } }, `Flip (faces ${f.facing})`)),
      h('div', { class: 'row' }, h('span', {}, `Draw order: ${f.z + 1} of ${N} (1 = the back)`), zb('To the back', 0), zb('Back one', f.z - 1), zb('Forward one', f.z + 1), zb('To the front', N - 1)),
      h('div', { class: 'note' }, 'Pose: the frames he can hold (his intros, win poses, taunts). "(in the ROM)" = the frame this build draws; another one is exported at the next build ' +
        '(the picture here is that export\'s frame).' + (F.wide.length ? ` Left out (wider than the ${D.sel_cols} sprites of a select block, or too big for the head finder): ${F.wide.map(p => p.join(' / ')).join(', ')}.` : '')),
      poses));
  }

  // ---- the stick's order: drag rows --------------------------------------------------------------------------------------
  function move(n, to) {
    const o = R.order(L).filter(m => m !== n); o.splice(Math.max(0, Math.min(o.length, to)), 0, n);
    o.forEach((m, k) => { L[m].slot = k; });
  }
  let dragRow = null;
  function renderOrder() {
    const o = R.order(L);
    orderBox.replaceChildren(h('ol', { class: 'slots' }, o.map((n, k) => {
      const li = h('li', { draggable: 'true', class: (n === sel ? 'on' : '') + (n === cursor ? ' cur' : '') },
        h('span', { class: 'grip' }, '≡'), h('span', { class: 'nm', onclick: () => { sel = n; draw(); } }, disp(n)),
        D.fighters[n].locked ? h('span', { class: 'note' }, ' locked at the start') : null, h('span', { class: 'sp' }),
        h('button', { disabled: k === 0, onclick: () => { snapshot(); move(n, k - 1); edited(); } }, '↑'),
        h('button', { disabled: k === o.length - 1, onclick: () => { snapshot(); move(n, k + 1); edited(); } }, '↓'));
      li.ondragstart = e => { dragRow = n; e.dataTransfer.effectAllowed = 'move'; e.dataTransfer.setData('text/plain', n); };
      li.ondragover = e => { e.preventDefault(); li.classList.add('drop'); };
      li.ondragleave = () => li.classList.remove('drop');
      li.ondrop = e => { e.preventDefault(); if (dragRow && dragRow !== n) { snapshot(); move(dragRow, k); dragRow = null; edited(); } };
      return li;
    })));
  }
  // ---- the arrow: per fighter, what "1P" + the arrow cover with the cursor on him ---------------------------------------
  let checkTimer = null;
  function renderChecks() {
    clearTimeout(checkTimer);
    checkTimer = setTimeout(() => {
      const rows = R.order(L).map(n => { const r = R.render(D, L, { cursor: n, unlocked: true }).arrow; return [n, r]; });
      checks.replaceChildren(h('table', { class: 'sp' }, h('tr', {}, h('th', {}, 'Cursor on'), h('th', {}, 'Arrow cell (col, row)'), h('th', {}, 'Covers')),
        rows.map(([n, a]) => h('tr', { class: a.hits.length || a.text || a.off ? 'over' : '' }, h('td', {}, disp(n)), h('td', {}, `${a.col}, ${a.row}`),
          h('td', {}, [a.off ? 'PAST THE SCREEN EDGE' : null, a.text ? 'the screen\'s text' : null, a.hits.length ? a.hits.map(disp).join(', ') : null].filter(Boolean).join(' · ') || '-')))));
    }, 150);
  }

  // ---- dragging on the picture ------------------------------------------------------------------------------------------
  let drag = null;
  const at = e => { const r = view.getBoundingClientRect(); return [Math.floor((e.clientX - r.left) / r.width * 320), Math.floor((e.clientY - r.top) / r.height * 224)]; };
  view.onpointerdown = e => {
    const [x, y] = at(e); if (!last) return;
    const k = x >= 0 && x < 320 && y >= 0 && y < 224 ? last.owner[y * 320 + x] : -1;
    sel = k >= 0 ? last.names[k] : null; view.focus();
    if (sel) { drag = { n: sel, x0: e.clientX, y0: e.clientY, fx: L[sel].x, fy: L[sel].y, moved: false }; view.setPointerCapture(e.pointerId); }
    draw();
  };
  view.onpointermove = e => {
    if (!drag) return;
    const r = view.getBoundingClientRect(), dx = Math.round((e.clientX - drag.x0) / r.width * 320), dy = Math.round((e.clientY - drag.y0) / r.height * 224);
    const nx = drag.fx + dx, ny = drag.fy + dy;
    if (nx === L[drag.n].x && ny === L[drag.n].y) return;
    if (!drag.moved) { snapshot(); drag.moved = true; }
    L[drag.n].x = Math.max(-64, Math.min(383, nx)); L[drag.n].y = Math.max(0, Math.min(300, ny)); draw();
  };
  view.onpointerup = view.onpointercancel = () => { if (drag && drag.moved) keep(); drag = null; };
  addEventListener('keydown', e => {                // the arrows nudge (before the game's keys: app.js)
    if (window.labTabName !== 'select' || !sel) return;
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA') return;
    const d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.code];
    if (!d) return;
    e.preventDefault(); e.stopImmediatePropagation();
    const s = e.shiftKey ? 8 : 1; snapshot();
    L[sel].x = Math.max(-64, Math.min(383, L[sel].x + d[0] * s)); L[sel].y = Math.max(0, Math.min(300, L[sel].y + d[1] * s)); edited();
  }, true);

  // ---- save / load (the feedback service, behind the same Oros login as the Lab) ------------------------------------------
  async function save() {
    status.textContent = 'saving…';
    try {
      const r = await fetch(API, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ layout: L, game_version: D.version }) });
      const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status);
      saved = { layout: clone(L), saved: j.saved, by: j.by }; draw(); status.textContent = `saved ${j.saved} (${j.by}): tell Claude to apply it (select_layout.py pull, build)`;
    } catch (e) { status.textContent = 'Save failed: ' + e.message; }
  }
  async function loadSaved() {
    try {
      const r = await fetch(API, { cache: 'no-store', credentials: 'same-origin' }); const j = await r.json();
      if (!r.ok) throw new Error(j.error || r.status);
      const ok = Object.keys(GAME).every(n => j.layout[n]) && Object.keys(j.layout).length === Object.keys(GAME).length;
      if (!ok) throw new Error('the saved layout is for another roster');
      for (const n of Object.keys(j.layout)) if (!D.fighters[n].poses.some(P => P.alias.some(a => same(a, j.layout[n].pose)))) j.layout[n].pose = GAME[n].pose;   // a pose this build can't show
      snapshot(); saved = j; L = clone(j.layout); edited();
    } catch (e) { status.textContent = 'Load failed: ' + e.message; }
  }

  // ---- the tab ----------------------------------------------------------------------------------------------------------
  let pausedByUs = false;
  tabBtn.onclick = () => window.labTab('select');
  window.addEventListener('labtab', e => {
    const on = e.detail === 'select';
    $('gamecol').hidden = on;
    const C = window.chainlab;
    if (C) { if (on && !C.paused) { C.togglePause(); pausedByUs = true; } else if (!on && pausedByUs) { if (C.paused) C.togglePause(); pausedByUs = false; } }
    if (on) draw();
  });
  window.selectTab = { get layout() { return L; }, set layout(x) { L = clone(x); edited(); }, get result() { return last; }, draw,
    hash() { let a = 2166136261 >>> 0; for (const v of new Uint8Array(cv.getContext('2d').getImageData(0, 0, 320, 224).data.buffer)) { a ^= v; a = Math.imul(a, 16777619) >>> 0; } return a.toString(16); } };
})();
