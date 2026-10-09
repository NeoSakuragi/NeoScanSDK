/* Brawler Lab, Select screen tab: the game's select screen drawn from a layout, pixel for pixel, in the page (and in
 * Node for the proof, tools/brawler/select_proof.py). The same rules as examples/brawler/main.c (select_start,
 * slot_show, fighter_pals, col_dark, select_arrows, select_name, depth_sort) and draw.s (fighter_place: the ROM sprites
 * face left, facing right mirrors x -> 2 ox - 1 - x; a sprite column's height = its trim), and Geolith's LSPC (the
 * resnet palette LUT, the fix layer over the sprites, a sprite counted on the lines of its height) on select.json
 * (chainlab/select_images.py). Layout: {fighter: {x, y, z, facing, pose, slot}} (build_tables.py select_layout).
 *
 * Since 2026-10-09 the screen is a street in front of SNK's Neo Geo Land (KOF95's stage 2, D.land: make_stage_land.py):
 * the layout's x is a street x (0 .. D.land.w - 1), the camera follows the cursor (main.c sel_cam_goal: its x - 160,
 * inside 0 .. cam_max), the layers scroll as the game's (far 64 + 5/7, facade and crowd 1:1, barriers 10/7: land_draw),
 * the barriers drawn over the fighters.
 *
 * render(D, L, {cursor, unlocked, cam, full}) -> {rgba (W x 224: the screen, 320 = the whole LSPC line, a TV shows x
 * 8-311, at camera cam (default: the cursor's); full: the whole street, W = D.land.w, no fix layer), W, cam, counts
 * (sprites per screen line, the land's and the fighters' on the screen), worst, owner (the fighter drawn on each pixel,
 * -1 none), names (owner's index -> fighter), arrow {col, row, hits: fighters under "1P" / the arrow, text: true when it
 * lands on the screen's text, off: off the screen}} */
(function (root) {
  'use strict';
  const SW = 320, H = 224, ROWS = 28;
  const b64 = s => typeof atob === 'function' ? Uint8Array.from(atob(s), c => c.charCodeAt(0)) : new Uint8Array(Buffer.from(s, 'base64'));

  function prepare(D) {                          /* select.json -> its pictures decoded, once */
    if (D._ready) return D;
    for (const f of Object.values(D.fighters)) for (const p of f.poses) p.px = b64(p.pix);
    D.fixTiles = {};
    for (const [t, s] of Object.entries(D.fix.tiles)) D.fixTiles[t] = b64(s);
    if (D.land) for (const ly of Object.values(D.land.layers)) { const u = b64(ly.pix); ly.px = new Uint16Array(u.buffer, u.byteOffset, u.length >> 1); }
    D._ready = true;
    return D;
  }
  function rgb(D, w) {                           /* a palette word -> [r, g, b]: geo_lspc_palconv + the resnet LUT */
    const r = ((w >> 6) & 0x3C) | ((w >> 13) & 2) | ((w >> 15) & 1), g = ((w >> 2) & 0x3C) | ((w >> 12) & 2) | ((w >> 15) & 1),
          b = ((w << 2) & 0x3C) | ((w >> 11) & 2) | ((w >> 15) & 1);
    return [D.lut[r], D.lut[g], D.lut[b]];
  }
  const RGB5 = (r, g, b) => ((r & 1) << 14) | ((r >> 1) << 8) | ((g & 1) << 13) | ((g >> 1) << 4) | ((b & 1) << 12) | (b >> 1);
  function dark(c) {                             /* main.c col_dark: its own colour, each 5-bit channel halved */
    const r = ((c >> 7) & 0x1E) | ((c >> 14) & 1), g = ((c >> 3) & 0x1E) | ((c >> 13) & 1), b = ((c << 1) & 0x1E) | ((c >> 12) & 1);
    return RGB5(r >> 1, g >> 1, b >> 1);
  }
  const SILHOUETTE = RGB5(4, 4, 5);
  const samePose = (a, b) => a[0] === b[0] && a[1] === b[1];
  function poseOf(D, n, pose) {                  /* the fighter's picture for a pose (alias: every [state, step] showing it) */
    const ps = D.fighters[n].poses;
    return ps.find(p => p.alias.some(a => samePose(a, pose))) || ps[0];
  }
  const order = L => Object.keys(L).sort((a, b) => L[a].slot - L[b].slot);   /* the stick's order */
  const locked = (D, n, o) => D.fighters[n].locked && !o.unlocked;
  /* select_start: the cursor starts on the first selectable slot */
  function firstCursor(D, L, o) { return order(L).find(n => !locked(D, n, o || {})) || order(L)[0]; }
  /* main.c sel_cam_goal (P1 alone): the camera centred on fighter n, inside the street */
  function camFor(D, L, n) { return D.land ? Math.max(0, Math.min(D.land.cam_max, L[n].x - 160)) : 0; }
  /* land_draw: each layer's scroll at camera cam (the far layer and its lights 64 + 5/7, the barriers 10/7) */
  function scrollOf(name, cam) { return name === 'top' || name === 'lights' ? 64 + ((cam * 731) >> 10) : name === 'front' ? (cam * 1463 + 512) >> 10 : cam; }
  /* the full street's picture: main + crowd 1:1, the far layer where the right end shows it (its only view), the
   * barriers where the middle camera shows them (stage2_composite.png's rule) */
  const FULL_CAM = { top: 'max', lights: 'max', front: 'mid' };
  /* select_arrows (P1): the arrow's fix cell over the head point, "1P" one row above; off the screen: none (off) */
  function arrowCell(D, L, n, cam) {
    const v = L[n], hd = poseOf(D, n, v.pose).head;
    const sx = v.x - (cam || 0) + (v.facing === 'right' ? -hd[0] : hd[0]) - 4, sy = v.y + hd[1] - 10;
    return { col: sx < 0 ? 0 : (sx + 4) >> 3, row: sy < 32 ? 4 : (sy + 4) >> 3, off: D.land ? sx < 0 || sx > 304 : false };
  }
  /* the land's sprites on each screen line at camera cam (land_draw: the rings' columns on the screen, the far columns
   * on the screen, the lights when shown) */
  function landCounts(D, cam, counts) {
    if (!D.land) return;
    for (const [name, ly] of Object.entries(D.land.layers)) {
      const sc = scrollOf(name, cam), ring = name === 'main' || name === 'mid' || name === 'front';
      const c0 = ring ? sc >> 4 : 0, c1 = ring ? c0 + 21 : ly.cols.length;
      let shown = false;
      for (let c = c0; c < c1 && c < ly.cols.length; c++) {
        const [first, n] = ly.cols[c], x = ly.x0 + c * 16 - sc;
        if (!n || (!ring && (x <= -16 || x >= 320))) continue;
        if (name === 'lights') { shown = true; continue; }
        for (let l = ly.y + first * 16; l < ly.y + (first + n) * 16; l++) if (l >= 0 && l < H) counts[l]++;
      }
      if (name === 'lights' && ly.x0 - sc > -96 && ly.x0 - sc < 320) for (let l = ly.y; l < ly.y + ly.h; l++) if (l >= 0 && l < H) counts[l] += ly.cols.length;
    }
  }
  /* a layer onto the picture: its pixel x at screen x x0 + px - sc; alpha 0.5 for the lights (shown every other frame) */
  function landBlit(D, rgba, W, name, sc, alpha) {
    const ly = D.land.layers[name], lut = D.land._lut || (D.land._lut = D.land.pals.map(w => rgb(D, w)));
    for (let py = 0; py < ly.h; py++) {
      const sy = ly.y + py; if (sy < 0 || sy >= H) continue;
      for (let px = 0; px < ly.w; px++) {
        const sx = ly.x0 + px - sc; if (sx < 0 || sx >= W) continue;
        const k = ly.px[py * ly.w + px]; if (!k) continue;
        const c = lut[k], q = (sy * W + sx) * 4;
        if (alpha < 1) { rgba[q] = (rgba[q] + c[0]) >> 1; rgba[q + 1] = (rgba[q + 1] + c[1]) >> 1; rgba[q + 2] = (rgba[q + 2] + c[2]) >> 1; }
        else { rgba[q] = c[0]; rgba[q + 1] = c[1]; rgba[q + 2] = c[2]; }
      }
    }
  }

  /* the cursor graph (TODO #187): build_tables.py select_stick, the same rules (select_proof.py checks both agree):
   * each fighter's body centre = the middle of its feet and its pose's head point (doubled: whole numbers); rows by
   * centre y, a new row past a ROW_GAP px gap; right / left = the next / previous by centre x along the row, on to the
   * next row (one loop through everyone); up / down = the nearest by x (then y, then the list) in the row above /
   * below, wrapping; ups / downs = the preference behind it (every other row that way, each by distance: a locked one is
   * passed over). override 'order' (game.json select.stick): left / right through the list instead.
   * -> {graph: {fighter: {right, left, up, down}}, rows: [[fighter]], centre: {fighter: [x2, y2]}} */
  const ROW_GAP = 16, DIRS = ['right', 'left', 'up', 'down'];
  function stick(D, L, override) {
    const ord = order(L), C = {};
    for (const n of ord) {
      const v = L[n], hd = poseOf(D, n, v.pose).head;
      C[n] = [2 * v.x + (v.facing === 'right' ? -hd[0] : hd[0]), 2 * v.y + hd[1]];
    }
    const cmp = (...keys) => (a, b) => { for (const k of keys) { const d = k(a) - k(b); if (d) return d; } return 0; };
    const rows = [];
    for (const n of ord.slice().sort(cmp(n => C[n][1], n => L[n].slot))) {
      if (rows.length && C[n][1] - C[rows[rows.length - 1][rows[rows.length - 1].length - 1]][1] <= 2 * ROW_GAP) rows[rows.length - 1].push(n);
      else rows.push([n]);
    }
    rows.forEach(r => r.sort(cmp(n => C[n][0], n => C[n][1], n => L[n].slot)));
    const loop = override === 'order' ? ord : rows.flat(), rowOf = {};
    rows.forEach((r, k) => r.forEach(n => { rowOf[n] = k; }));
    const graph = {}, N = loop.length, R = rows.length;
    loop.forEach((n, i) => {
      const pref = step => {                     // the other rows that way (wrapping), each by distance
        const out = [];
        for (let j = 1; j < R; j++) out.push(...rows[((rowOf[n] + step * j) % R + R) % R].slice().sort(cmp(m => Math.abs(C[m][0] - C[n][0]), m => Math.abs(C[m][1] - C[n][1]), m => L[m].slot)));
        return out;
      };
      const ups = pref(-1), downs = pref(1);
      graph[n] = { right: loop[(i + 1) % N], left: loop[(i + N - 1) % N], up: ups.length ? ups[0] : n, down: downs.length ? downs[0] : n, ups, downs };
    });
    return { graph, rows, centre: C };
  }
  /* main.c sel_move: right / left followed on past locked fighters, up / down the first selectable of ups / downs; none: stay */
  function stickMove(D, G, n, dir, o) {
    if (dir === 'up' || dir === 'down') return G[n][dir + 's'].find(t => !locked(D, t, o || {})) || n;
    let t = n;
    for (let k = 0; k < Object.keys(G).length; k++) { t = G[t][dir]; if (t === n) break; if (!locked(D, t, o || {})) return t; }
    return n;
  }

  function render(D, L, o) {
    o = o || {};
    prepare(D);
    const cursor = o.cursor && L[o.cursor] ? o.cursor : firstCursor(D, L, o);
    const full = !!(o.full && D.land), W = full ? D.land.w : SW, cam = full ? 0 : o.cam !== undefined ? o.cam : camFor(D, L, cursor);
    const rgba = new Uint8ClampedArray(W * H * 4), owner = new Int8Array(W * H).fill(-1), counts = new Int32Array(H);
    const bd = rgb(D, D.land ? D.land.backdrop : D.fix.backdrop);
    for (let i = 0; i < W * H; i++) { rgba[4 * i] = bd[0]; rgba[4 * i + 1] = bd[1]; rgba[4 * i + 2] = bd[2]; rgba[4 * i + 3] = 255; }
    const lsc = name => !full ? scrollOf(name, cam) : FULL_CAM[name] ? scrollOf(name, FULL_CAM[name] === 'max' ? D.land.cam_max : D.land.cam_max >> 1) - (FULL_CAM[name] === 'max' ? D.land.cam_max : D.land.cam_max >> 1) : 0;
    if (D.land) { for (const n of ['top', 'main', 'mid']) { landBlit(D, rgba, W, n, lsc(n), 1); if (n === 'top') landBlit(D, rgba, W, 'lights', lsc('lights'), 0.5); } if (!full) landCounts(D, cam, counts); }
    const names = Object.keys(L).sort((a, b) => L[a].z - L[b].z);   /* depth_sort: the layout's z, the back first */
    names.forEach((n, k) => {
      const v = L[n], P = poseOf(D, n, v.pose);
      const look = locked(D, n, o) ? 2 : n === cursor ? 1 : 0;     /* slot_look: silhouette, colour, dark */
      const cols = [], vx = v.x - cam;
      if (D.land && !full && (vx + P.w <= 0 && vx - P.w <= 0 || vx - P.w >= W && vx + P.w >= W)) return;   /* off the screen */
      for (let i = 0; i < P.pals.length; i++) {
        const w = i % 16 === 0 ? P.pals[i] : look === 2 ? SILHOUETTE : look ? P.pals[i] : dark(P.pals[i]);
        cols.push(rgb(D, w));
      }
      const right = v.facing === 'right';
      for (let py = 0; py < P.h; py++) {
        const sy = v.y - P.oy + py;
        if (sy < 0 || sy >= H) continue;
        for (let px = 0; px < P.w; px++) {
          const ix = P.px[py * P.w + px];
          if (!(ix & 15)) continue;
          const lx = vx - P.ox + px, sx = right ? 2 * vx - 1 - lx : lx;
          if (sx < 0 || sx >= W) continue;
          const c = cols[ix] || [255, 0, 255], q = (sy * W + sx) * 4;
          rgba[q] = c[0]; rgba[q + 1] = c[1]; rgba[q + 2] = c[2]; owner[sy * W + sx] = k;
        }
      }
      if (full) return;
      for (const [top, rows, cx] of P.cols) {    /* the LSPC: a sprite on line l when (l - its top line) & 511 < its height */
        if (!rows) continue;
        if (D.land && cx !== undefined) {        /* main.c land_clip: a column off the screen gets height 0 */
          const left = right ? vx - cx - 16 : vx + cx;
          if (left <= -16 || left >= W) continue;
        }
        const tl = (v.y + top + 16) & 0x1FF;
        for (let l = 16; l < 240; l++) if (((l - tl) & 0x1FF) < rows * 16) counts[l - 16]++;
      }
    });
    if (D.land) landBlit(D, rgba, W, 'front', lsc('front'), 1);   /* the barriers: over the fighters */
    if (full) return { rgba, W, cam, counts, worst: 0, owner, names, cursor, arrow: null };
    /* the fix layer: the game's own text, the name row (select_name) and P1's "1P" + arrow (select_arrows) */
    const map = D.fix.map.slice(), put = (c, r, w) => { if (c >= 0 && c < 40 && r >= 0 && r < ROWS) map[c * ROWS + r] = w; };
    const name = D.fighters[cursor].name;
    for (let i = 0; i < name.length; i++) put(20 - (name.length >> 1) + i, 2, name.charCodeAt(i));
    const a = arrowCell(D, L, cursor, cam), cells = a.off ? [] : [[a.col, a.row - 1, 0x31], [a.col + 1, a.row - 1, 0x50], [a.col, a.row, D.fix.arrow]];
    const text = cells.some(([c, r]) => c < 40 && r < ROWS && (D.fix.map[c * ROWS + r] & 0xFFF) > 0x20);
    for (const [c, r, t] of cells) put(c, r, t);
    const hits = new Set();
    for (let c = 0; c < 40; c++) for (let r = 0; r < ROWS; r++) {
      const w = map[c * ROWS + r], t = D.fixTiles[w & 0xFFF];
      if (!t) continue;
      const pal = w >> 12, isArrow = cells.some(([cc, rr]) => cc === c && rr === r);
      for (let y = 0; y < 8; y++) for (let x = 0; x < 8; x++) {
        const pen = t[y * 8 + x];
        if (!pen) continue;
        const sx = c * 8 + x, sy = r * 8 + y;
        if (isArrow && owner[sy * W + sx] >= 0 && names[owner[sy * W + sx]] !== cursor) hits.add(names[owner[sy * W + sx]]);
        const col = rgb(D, D.fix.pals[pal * 16 + pen]), q = (sy * W + sx) * 4;
        rgba[q] = col[0]; rgba[q + 1] = col[1]; rgba[q + 2] = col[2];
      }
    }
    let worst = 0;
    for (let l = 1; l < H; l++) if (counts[l] > counts[worst]) worst = l;
    return { rgba, W, cam, counts, worst, owner, names, cursor,
             arrow: { col: a.col, row: a.row, hits: [...hits], text, off: a.off || a.col > 38 || a.row >= ROWS } };
  }

  const api = { render, prepare, rgb, dark, poseOf, order, firstCursor, arrowCell, camFor, scrollOf, stick, stickMove, DIRS, W: SW, H };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.SelectRender = api;
})(typeof window !== 'undefined' ? window : globalThis);
