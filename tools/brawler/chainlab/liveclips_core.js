/* LIVE CLIPS, the simulation (Bruno 2026-10-10: "take the rendering of animations and specials in the assembly to the next
 * level"; "pre-rendering is no good: I can't adjust parameters"): the Assembly's clips are played by the real engine, again
 * after every change. One headless game per page: the Character Lab SHELL with the fighter's PACK swapped in (the Player's
 * and "Try in game"'s files: tryit.js), its own core instance (liveclips_worker.js runs this file in a Web Worker; the
 * Node proofs run it directly). The game is not changed for it: everything here is the page's driving of the practice
 * mode through RAM (lab.js: the TRY blob, the prac block) and reading back RAM, the picture and the video RAM.
 *
 *   const sim = await LiveSim.create(GeoCore, {bios, rom, pack, doc, slot, dummy})   (doc: the shell's anchor JSON)
 *   sim.clip(req) -> {w, h, n, bpp, data, pal, frames, fd, ms}
 *
 * The baseline (made once, a save state): the practice with one standing dummy (DUMMIES 1, STAND, infinite life), P1's
 * life refilled, the drive infinite, the fury gauge held full (a special / the fury always plays), the box viewer ON
 * (main.c dbg_draw: the hit test's own hurt / attack boxes as corner sprites 300-347). Each clip: that state again, P1
 * placed req.gap px from the dummy, the TRY blob written (apply now), the input pressed frame by frame, until P1 is back
 * in neutral, his projectiles gone and the dummy recovered (or req.cap frames). Per frame: the picture, P1 / the dummy /
 * the projectiles (state, animation, step, place), the boxes (read from the box viewer's sprites in video RAM, then
 * hidden before the next frame is drawn: the picture never shows them), the combo's hits and damage.
 * req: {blob (a TRY blob: lab.js encodeTry), gap (px, null = where the practice puts them), max (MAX ready), cap,
 *       script: [[keys, frames], ...] (lab.js KEYS letters: a b c d, U D L R) | {chain: N, stick} (A every other frame,
 *       the stick held from the last press on: the chain + a finisher), after (frames recorded after the end)} */
(function (root) {
  'use strict';
  const CL = root.ChainLab || (typeof require !== 'undefined' ? require('./lab.js') : null);
  // prac_t (fighter.h): +4 set[PS_*]
  const PS = { FURY: 0, MAX: 1, DRIVE: 2, LIFE: 3, DUMMIES: 4, MODE: 5, WAVES: 6, DLIFE: 7, BOXES: 8 };
  const DUMMY = 2;                                   // main.c LAB_DUMMY: the first dummy's fighter slot
  const NPJ = 8;                                     // fighter.h NPJ: projectile entities
  const DBG_SPR = 300, DBG_BOXES = 6;                // main.c dbg_draw: 6 hurt boxes (4 corner sprites each), then 6 attack
  const SCB3 = 0x8200, SCB4 = 0x8400;                // video RAM word indexes (neo_hw.h)
  const BAND = [24, 216];                            // the picture's rows a clip may use (the HUD above, the practice line below)
  const NEUTRAL = ['IDLE', 'WALK'];

  class LiveSim {
    constructor(lab, doc) {
      this.lab = lab; this.core = lab.core; this.doc = doc; this.L = doc.layout;
      this.prac = doc.ram.prac;
      this.base = null;
    }
    static async create(GeoCore, o) {
      const lab = await CL.Lab.create(GeoCore, { bios: o.bios, rom: o.rom }, o.doc.layout);
      try { lab.core.FS.unlink('/rom/game.neo'); } catch (e) { /* the core has its own copy */ }
      const sim = new LiveSim(lab, o.doc);
      if (o.pack) sim.swap(o.pack);
      sim.boot(o.slot, o.dummy);
      return sim;
    }
    swap(pack) {
      const c = this.core, p = c._malloc(pack.length);
      c.HEAPU8.set(pack, p);
      const e = c._wc_swap_pack(p, pack.length);
      c._free(p);
      if (e) { let m = '', q = c._wc_pack_error(e); for (let ch; (ch = c.HEAPU8[q++]);) m += String.fromCharCode(ch); throw new Error('the core refused the pack: ' + (m || e)); }
    }
    boot(slot, dummy) {
      const lab = this.lab, t0 = now();
      lab.boot(slot, dummy, null);
      this.slot = slot;
      this.setPrac({ FURY: 1, MAX: 0, DRIVE: 1, LIFE: 0, DUMMIES: 1, MODE: 0, WAVES: 0, DLIFE: 0, BOXES: 1 });
      lab.run(40);
      if (lab.stateName(0) !== 'IDLE' || lab.stateName(DUMMY) !== 'IDLE') throw new Error('the practice did not settle (P1 ' + lab.stateName(0) + ', dummy ' + lab.stateName(DUMMY) + ')');
      this.spawnGap = Math.round(Math.abs(lab.fget(DUMMY, 'x') - lab.fget(0, 'x')));
      this.base = lab.saveState();
      this.bootMs = Math.round(now() - t0);
    }
    setPrac(o) { for (const [k, v] of Object.entries(o)) this.lab.w8(this.prac + 4 + PS[k], v); }
    get vram() { return new Uint16Array(this.core.HEAPU8.buffer, this.core._wc_vram(), 0x8800); }
    // the box viewer's sprites -> boxes in picture coordinates [l, t, r, b) (main.c dbg_box: 4 corner sprites of 16 px;
    // picture x = sprite x - 8, picture y = 496 - the y field), then hidden (height 0: what dbg_init writes)
    boxes() {
      const V = this.vram, out = { hurt: [], atk: [] };
      for (let k = 0; k < 2 * DBG_BOXES; k++) {
        const s = DBG_SPR + 4 * k, y0 = V[SCB3 + s], y2 = V[SCB3 + s + 2];
        if (!(y0 & 63)) continue;
        const Y = w => { const v = (496 - (w >> 7)) & 0x1FF; return v > 400 ? v - 512 : v; }, X = w => { const v = (w >> 7) & 0x1FF; return v > 400 ? v - 512 : v; };
        const l = X(V[SCB4 + s]) - 8, r = X(V[SCB4 + s + 1]) + 16 - 8, t = Y(y0), b = Y(y2) + 16;
        (k < DBG_BOXES ? out.hurt : out.atk).push([l, t, r, b]);
      }
      for (let s = DBG_SPR; s < DBG_SPR + 8 * DBG_BOXES; s++) V[SCB3 + s] = 0;
      return out;
    }
    camX() { return (this.lab.r16(this.L.syms.cam_x) << 16) >> 16; }
    projs() {
      const lab = this.lab, L = this.L, base = L.syms.projectiles, PROJ = L.states.indexOf('PROJ'), out = [];
      if (base === undefined) return out;
      for (let i = 0; i < NPJ; i++) {
        const a = base + i * L.fsize;
        if (lab.r8(a + L.fields.state[0]) !== PROJ) continue;
        const fx = o => (lab.r32(a + L.fields[o][0]) | 0) / 65536;
        out.push({ i, x: fx('x'), y: fx('y'), z: fx('z') });
      }
      return out;
    }
    clip(req) {
      const t0 = now(), lab = this.lab, c = this.core, cap = Math.min(req.cap || 300, 600);
      lab.loadState(this.base); lab.pads = [0, 0];
      if (req.max) { this.setPrac({ MAX: 1 }); lab.run(3); }
      if (req.gap) {                                 // P1 req.gap px from the dummy, on its lane, facing it
        const L = this.L, dx = lab.fget(DUMMY, 'x') - req.gap, a = L.syms.fighters + L.fields.x[0];
        lab.w16(a, Math.round(dx) & 0xFFFF); lab.w16(a + 2, 0);
        lab.run(2);
      }
      this.boxes();                                   // (the box viewer's sprites of the frame before: hidden)
      const res = { error: null };
      if (req.blob) {
        lab.installTry(req.blob, true);
        let k = 0;
        for (; k < 30 && lab.r8(lab.lab + 7); k++) { lab.run(1); this.boxes(); }
        const st = lab.tryStatus();
        if (st.startsWith('refused') || st === 'sent') res.error = 'the game ' + (st === 'sent' ? 'did not take the TRY blob' : st);
      }
      // the input, frame by frame; the record: frame k = the state after tick k + the picture drawn from it (the next run's)
      const sc = req.script || [];
      const keysAt = (() => {
        if (Array.isArray(sc)) { const seq = []; for (const [k, n] of sc) for (let i = 0; i < n; i++) seq.push(k); return i => seq[i] || ''; }
        return null;                                  // a chain: A every other frame (below)
      })();
      const W = c._wc_fb_w(), H0 = BAND[0], H = BAND[1] - BAND[0];
      const pics = [], recs = [];
      const pal = new Map(); let palN = 0, lastC = -1, lastI = 0;
      const pic = () => {                              // the picture's band as colour indexes (16-bit), the palette on the fly
        const fb = new Uint32Array(c.HEAPU8.buffer, c._wc_fb(), W * c._wc_fb_h()), out = new Uint16Array(W * H);
        for (let i = 0, j = H0 * W; i < out.length; i++, j++) {
          const v = fb[j];
          if (v !== lastC) { lastC = v; let x = pal.get(v); if (x === undefined) { x = palN++; pal.set(v, x); } lastI = x; }
          out[i] = lastI;
        }
        return out;
      };
      const from = lab.nev(), combo0 = lab.combo();
      let left = -1, back = -1, endAt = -1, starts = 0, hits = 0, dmg = 0, prevC = combo0, evAt = from, chainDone = false;
      for (let k = 0; k <= cap; k++) {
        let keys = '';
        if (keysAt) keys = keysAt(k);
        else if (!chainDone) keys = (starts >= sc.chain - 1 ? (sc.stick || '') : '') + (k % 2 ? '' : 'a');
        lab.setPad(0, keys); lab.run(1);
        if (k) pics.push(pic());                       // (run k's picture shows tick k - 1)
        const B = this.boxes(), cam = this.camX();
        const ev = lab.eventsSince(evAt); evAt = ev.next;
        for (const e of ev.events) if (e.kind === 'START') starts++;
        const cb = lab.combo();
        if (cb.hits < prevC.hits || cb.dmg < prevC.dmg) { hits += cb.hits; dmg += cb.dmg; }      // a new combo
        else { hits += cb.hits - prevC.hits; dmg += cb.dmg - prevC.dmg; }
        const hitNow = cb.hits !== prevC.hits && cb.hits > 0;
        prevC = cb;
        const f0 = { st: lab.stateName(0), an: lab.fget(0, 'anim'), sp: lab.fget(0, 'step'), x: lab.fget(0, 'x') - cam - 8, y: lab.fget(0, 'y'), cur: lab.tryCur() };
        const d = { st: lab.stateName(DUMMY), x: lab.fget(DUMMY, 'x') - cam - 8, y: lab.fget(DUMMY, 'y'), hp: lab.fget(DUMMY, 'hp') };
        const pj = this.projs().map(p => ({ x: p.x - cam - 8, y: p.y }));
        // the boxes' owners: an attack box to P1 or the nearest of his projectiles; a hurt box to P1 or the dummy
        const atk = B.atk.map(b => { const cx = (b[0] + b[2]) / 2; let own = 0, best = Math.abs(cx - f0.x); pj.forEach(p => { const dd = Math.abs(cx - p.x); if (dd < best) { best = dd; own = 1; } }); return b.concat([own]); });
        const hurt = B.hurt.map(b => { const cx = (b[0] + b[2]) / 2; return b.concat([Math.abs(cx - f0.x) <= Math.abs(cx - d.x) ? 0 : 2]); });
        recs.push({ p1: f0, d, pj, atk, hurt, hits, dmg, hit: hitNow, keys });
        const neutral = NEUTRAL.includes(f0.st);
        if (!neutral && left < 0) left = k;
        if (neutral && left >= 0 && back < 0 && k > left) back = k;
        if (!keysAt && back >= 0) chainDone = true;
        const scriptOver = keysAt ? k >= (Array.isArray(sc) ? sc.reduce((a, s) => a + s[1], 0) : 0) : chainDone;
        if (endAt < 0 && scriptOver && k >= 4 && (left < 0 ? k >= 40 : back >= 0) && !pj.length && NEUTRAL.includes(d.st) && neutral) endAt = k;
        if (endAt >= 0 && k >= endAt + (req.after === undefined ? 4 : req.after)) break;
      }
      lab.setPad(0, ''); lab.run(1); pics.push(pic());
      // the crop: around both fighters, their boxes and the projectiles over the whole clip (whole game pixels)
      let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9;
      const grow = (a, b, c2, d2) => { x0 = Math.min(x0, a); x1 = Math.max(x1, b); y0 = Math.min(y0, c2); y1 = Math.max(y1, d2); };
      for (const r of recs) {
        for (const b of r.atk.concat(r.hurt)) grow(b[0], b[2], b[1], b[3]);
        grow(r.p1.x - 36, r.p1.x + 36, BAND[1] - 30, BAND[1] - 30); grow(r.d.x - 36, r.d.x + 36, BAND[1] - 30, BAND[1] - 30);
        for (const p of r.pj) grow(p.x - 24, p.x + 24, BAND[1] - 30, BAND[1] - 30);
      }
      x0 = Math.max(0, Math.floor(x0 - 20)); x1 = Math.min(W, Math.ceil(x1 + 20));
      y0 = Math.max(BAND[0], Math.floor(y0 - 28)); y1 = Math.min(BAND[1], Math.ceil(Math.max(y1 + 6, BAND[1] - 12)));
      if (x1 - x0 < 140) { const m = (x0 + x1) / 2; x0 = Math.max(0, Math.round(m - 70)); x1 = Math.min(W, x0 + 140); }
      if (y1 - y0 < 110) y0 = Math.max(BAND[0], y1 - 110);
      const cw = x1 - x0, ch = y1 - y0, n = recs.length, bpp = palN <= 256 ? 1 : 2;
      const data = bpp === 1 ? new Uint8Array(n * cw * ch) : new Uint16Array(n * cw * ch);
      for (let k = 0; k < n; k++) {
        const p = pics[k], o = k * cw * ch;
        for (let y = 0; y < ch; y++) { const s = (y + y0 - BAND[0]) * W + x0; data.set(p.subarray(s, s + cw), o + y * cw); }
      }
      const palOut = new Uint32Array(palN);           // canvas byte order (R, G, B, A) from XRGB8888
      for (const [v, i] of pal) palOut[i] = 0xFF000000 | ((v & 0xFF) << 16) | (v & 0xFF00) | ((v >> 16) & 0xFF);
      for (const r of recs) {                         // everything in clip coordinates
        const sh = b => [b[0] - x0, b[1] - y0, b[2] - x0, b[3] - y0, b[4]];
        r.atk = r.atk.map(sh); r.hurt = r.hurt.map(sh);
        r.p1.x -= x0; r.d.x -= x0; r.pj.forEach(p => { p.x -= x0; });
      }
      const fd = frameData(recs, left, back);
      fd.gap = Math.round(Math.abs(recs[0].d.x - recs[0].p1.x));
      return Object.assign(res, { w: cw, h: ch, n, bpp, data, pal: palOut, frames: recs, fd, crop: [x0, y0], ms: Math.round(now() - t0) });
    }
  }
  /* the frame data of a clip, from the simulation alone: P1's own move from the input (frame 0) to his return to neutral;
     active = a frame with an attack box of his (his body's or a projectile's); hits / damage = the combo counter's;
     reach = his body's attack boxes' farthest edge ahead of him; the projectile's speed (px a frame while it moves) and
     travel; the dummy's reaction (its states after the first hit, with their lengths) */
  function frameData(recs, left, back) {
    const n = recs.length, total = back >= 0 ? back : n;
    const act = recs.map(r => r.atk.length > 0);
    const wins = []; let a = -1;
    for (let k = 0; k <= n; k++) { const on = k < n && act[k]; if (on && a < 0) a = k; if (!on && a >= 0) { wins.push([a, k - 1]); a = -1; } }
    const first = wins.length ? wins[0][0] : -1, last = wins.length ? wins[wins.length - 1][1] : -1;
    let reach = 0;
    for (const r of recs) for (const b of r.atk) if (!b[4]) {
      const ahead = r.p1.x <= r.d.x ? b[2] - r.p1.x : r.p1.x - b[0];
      reach = Math.max(reach, Math.round(ahead));
    }
    // the projectile: one track per frame (the first alive), its speed while moving
    const xs = recs.map(r => r.pj.length ? r.pj[0].x : null), sp = [];
    let pfirst = -1, plast = -1;
    for (let k = 0; k < n; k++) if (xs[k] !== null) { if (pfirst < 0) pfirst = k; plast = k; if (k && xs[k - 1] !== null && xs[k] !== xs[k - 1]) sp.push(Math.abs(xs[k] - xs[k - 1])); }
    sp.sort((p, q) => p - q);
    const proj = pfirst >= 0 ? { from: pfirst, to: plast, speed: sp.length ? Math.round(sp[sp.length >> 1] * 100) / 100 : 0, travel: Math.round(Math.abs(xs[plast] - xs[pfirst])) } : null;
    // the dummy: its states from the first hit on
    const hitAt = recs.findIndex(r => r.hit);
    const react = [];
    if (hitAt >= 0) for (let k = hitAt; k < n; k++) {
      const s = recs[k].d.st;
      if (react.length && react[react.length - 1].st === s) react[react.length - 1].n++; else react.push({ st: s, n: 1, at: k });
      if (NEUTRAL.includes(s)) break;
    }
    const top = hitAt >= 0 ? Math.max(...recs.slice(hitAt).map(r => r.d.y)) : 0;
    return { total, startup: first >= 0 ? first + 1 : 0, active: first >= 0 ? last - first + 1 : 0, recovery: first >= 0 ? Math.max(0, total - 1 - last) : total,
             windows: wins.map(([p, q]) => [p + 1, q + 1]), hits: n ? recs[n - 1].hits : 0, damage: n ? recs[n - 1].dmg : 0, reach,
             hitFrames: recs.map((r, k) => r.hit ? k + 1 : 0).filter(x => x), proj, react, lift: Math.round(top), moved: left >= 0, ended: back >= 0, frames: n };
  }
  const now = () => (typeof performance !== 'undefined' ? performance.now() : Date.now());
  const api = { LiveSim, frameData, PS, DUMMY };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.LiveSim = api;
})(typeof self !== 'undefined' ? self : typeof window !== 'undefined' ? window : globalThis);
