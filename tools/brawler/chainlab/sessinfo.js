/* What a play session shows, read from the game's RAM (docs/feedback.md "Session recording"; the Sessions tab's
 * columns, the live wall's tiles, the single view's line): the screen (title / select / fight / demo / bonus / ending /
 * game over), the stage and the wave (or BOSS), each player's fighter, life (%) and drive chunks, the difficulty.
 * Read from a keyframe's state (Geolith save state v3 of the Lab's core: the 68000 RAM and the VRAM sit at fixed
 * offsets in it, no core needed) or from a running core (every frame). The RAM addresses are the build's own:
 * ramsyms/<rom sha256>.json (ramsyms.py, published with every build by tools/brawler/publish_vps.sh). A build without
 * one: the players' names as the HUD shows them (the fix layer) and the difficulty (BIOS RAM); the rest unknown (null).
 *   SessInfo.fromState(stateBytes, syms|null)   -> info | null (another core's state: unknown)
 *   SessInfo.fromCore(core, syms|null)          -> info (core = a FeedbackReplay's .core)
 *   SessInfo.text(info) / SessInfo.cols(info)   the line / the list's cells ('—' unknown)
 *   SessInfo.syms(sha) (browser)                -> Promise<syms|null> (cached)
 * info = { screen, stage, wave, level, two, players: [{ name, life, drive, chunks, out }] } */
(function (root) {
  'use strict';
  const STATE_SIZE = 222789, STATE_RAM = 153777, STATE_VRAM = 67625;   // the deployed core (2026-10-16); measured: probe
  const RAM = 0x100000, FIX = 0x7000;
  const SCREENS = ['select', 'fight', 'title', 'boss unlocked', 'ending', 'game over', 'bonus', 'ladder'];
  const LEVELS = ['EASY', 'NORMAL', 'HARD', 'MANIAC'];

  function readerState(st) {
    if (!st || st.length !== STATE_SIZE) return null;
    const dv = new DataView(st.buffer, st.byteOffset, st.byteLength);
    return { r8: a => st[STATE_RAM + (a - RAM)], fix: (c, r) => dv.getUint16(STATE_VRAM + 2 * (FIX + c * 32 + r), true) };
  }
  function readerCore(core) {
    const H = core.HEAPU8, ram = core._wc_ram(), v = core._wc_vram() >> 1, V = core.HEAPU16 || new Uint16Array(H.buffer);
    return { r8: a => H[ram + (a - RAM)], fix: (c, r) => V[v + FIX + c * 32 + r] };
  }
  function decode(R, S) {
    const r16 = a => R.r8(a) << 8 | R.r8(a + 1), r32 = a => (r16(a) * 65536 + r16(a + 2)) >>> 0;
    const s16 = a => { const v = r16(a); return v & 0x8000 ? v - 0x10000 : v; };
    const out = { screen: null, stage: null, wave: null, level: null, two: false, players: [] };
    // the difficulty: MVS = the soft DIP LEVEL 1-8 (BIOS RAM $10FD84 + 6), AES = the game's own (save.difficulty)
    if (R.r8(0x10FD82)) { const l = R.r8(0x10FD8A); const lv = l > 7 ? 4 : l + 1; out.level = 'LEVEL-' + lv + ' ' + LEVELS[(lv - 1) >> 1]; }
    else if (S && S.syms.difficulty !== undefined) { const d = R.r8(S.syms.difficulty) & 3; out.level = 'LEVEL-' + (2 * d + 2) + ' ' + LEVELS[d]; }
    const pmod = [R.r8(0x10FDB6), R.r8(0x10FDB7)];      // BIOS: 0 never played, 1 playing, 2 continue, 3 over
    if (S) {
      const y = S.syms, m = R.r8(y.mode);
      out.screen = m === 1 && R.r8(y.attract) ? 'demo' : SCREENS[m] || 'mode ' + m;
      if (m === 1 || m === 6) {
        const camp = R.r8(y.camp), st = S.stages[camp], ph = R.r8(y.phase), w = R.r8(y.wave);
        if (m === 1) { out.stage = st ? st.name : 'stage ' + (camp + 1); out.wave = ph >= 2 ? (ph === 4 ? 'CLEAR' : 'BOSS') : 'wave ' + (w + 1) + (st && st.nwaves ? '/' + st.nwaves : ''); }
        const F = S.fields, off = S.states.indexOf('OFF'), chunks = y.drive_chunks !== undefined ? R.r8(y.drive_chunks) : S.meter && S.meter.chunks;
        out.two = pmod[1] === 1 || pmod[1] === 2;
        for (let p = 0; p < (out.two ? 2 : 1); p++) {
          const b = y.fighters + p * S.fsize, ch = r32(b + F.ch[0]), k = (ch - y.bm_chars) / S.sizeof_bchar;
          const hp = s16(b + F.hp[0]), max = s16(b + F.hp_max[0]) || 60, dr = r16(b + F.drive[0]);
          out.players.push({ name: Number.isInteger(k) && S.chars[k] !== undefined ? S.chars[k] : null,
            life: max > 0 ? Math.max(0, Math.round(100 * hp / max)) : null,
            drive: S.meter && S.meter.chunk ? Math.floor(dr / S.meter.chunk) : null, chunks: chunks || null,
            out: out.screen === 'fight' && R.r8(b + F.state[0]) === off });   // (out: dead, waiting to continue)
        }
      }
      return out;
    }
    // no RAM map: the HUD (main.c hud(): P1's name at row 0 col 5, its lives "x n" at row 2 col 5; two players: P2's
    // lives at row 2 col 32 and its name ending at col 34; the fix layer's rows are the HUD's + 2)
    const ch = (c, r) => { const t = R.fix(c, r) & 0xFFF; return t >= 0x20 && t < 0x7F ? String.fromCharCode(t) : ' '; };
    const txt = (c0, c1, r) => { let s = ''; for (let c = c0; c <= c1; c++) s += ch(c, r); return s.trim(); };
    const digit = c => c >= '0' && c <= '9';
    if (ch(5, 4) === 'x' && digit(ch(6, 4))) {
      out.screen = 'fight';
      out.two = ch(32, 4) === 'x' && digit(ch(33, 4));
      out.players.push({ name: txt(5, 14, 2) || null, life: null, drive: null, chunks: null, out: false });
      if (out.two) out.players.push({ name: txt(25, 34, 2) || null, life: null, drive: null, chunks: null, out: false });
    }
    return out;
  }
  const fromState = (st, syms) => { const R = readerState(st); return R ? decode(R, syms) : null; };
  const fromCore = (core, syms) => decode(readerCore(core), syms);
  const D = '—';
  function who(p) { return p.name ? p.name + (p.out ? ' (out)' : '') : D; }
  function vitals(p) {
    const l = p.life === null ? '' : p.life + '%', d = p.drive === null ? '' : 'D' + p.drive + (p.chunks ? '/' + p.chunks : '');
    return [l, d].filter(Boolean).join(' ');
  }
  /** the list's cells: character(s), where (screen / stage / wave), life + drive per player, the difficulty */
  function cols(i) {
    if (!i) return { chars: D, where: D, vitals: D, level: D };
    const ps = i.players;
    return { chars: ps.length ? ps.map(who).join(' + ') : D,
      where: i.screen === 'fight' && i.stage ? i.stage + ' · ' + i.wave : i.screen || D,
      vitals: ps.length ? ps.map(vitals).map(v => v || D).join(' · ') : D, level: i.level || D };
  }
  function text(i) {
    if (!i) return D;
    const c = cols(i), ps = i.players.map(p => who(p) + (vitals(p) ? ' ' + vitals(p) : ''));
    return [c.where, ps.join(' · '), i.level].filter(x => x && x !== D).join(' · ') || D;
  }
  const symsCache = new Map();
  function syms(sha) {                                   // ramsyms/<sha>.json next to the page (null: the build has none)
    if (!sha) return Promise.resolve(null);
    if (!symsCache.has(sha)) symsCache.set(sha, fetch('ramsyms/' + sha + '.json', { credentials: 'same-origin' })
      .then(r => r.ok ? r.json() : null).then(j => (j && j.format === 1 ? j : null)).catch(() => null)
      .then(j => { symsCache.set(sha, Promise.resolve(j)); symsNow.set(sha, j); return j; }));
    return symsCache.get(sha);
  }
  const symsNow = new Map();                             // sha -> syms | null once loaded (a synchronous read in a frame loop)
  /** a list row's info from its latest keyframe (a session that ended: the latest one showing a fighter, up to 4 back):
   *  -> Promise<{ info, age (s: the keyframe's distance to the session's newest chunk), seq }>; cached per session
   *  (live: read again when a newer keyframe arrived; ended: kept in localStorage) */
  const rowCache = new Map(), queue = []; let running = 0;
  const LS = 'sessinfo1:';
  function forRow(row, API) {                         // -> { now: the last result (or null), next: Promise of a fresh one }
    let e = rowCache.get(row.id);
    if (!e && !row.live) { try { const v = JSON.parse(localStorage.getItem(LS + row.id) || 'null'); if (v && v.chunks === row.chunks) e = { chunks: v.chunks, t: Date.now(), r: v.r, p: Promise.resolve(v.r) }; } catch (x) { /* none */ } if (e) rowCache.set(row.id, e); }
    if (e && (e.chunks === row.chunks || (row.live && Date.now() - e.t < 10000))) return { now: e.r || null, next: e.p };
    const p = new Promise((res, rej) => { queue.push([row, API, res, rej]); pump(); });
    const n = { chunks: row.chunks, t: Date.now(), r: e ? e.r : null, p };
    rowCache.set(row.id, n);
    p.then(r => { n.r = r; if (!row.live) { try { localStorage.setItem(LS + row.id, JSON.stringify({ chunks: row.chunks, r })); } catch (x) { /* full / blocked */ } } },
      () => { n.chunks = -1; });
    return { now: n.r, next: p };
  }
  function pump() {
    while (running < 2 && queue.length) {
      const [row, API, res, rej] = queue.shift(); running++;
      readRow(row, API).then(res, rej).finally(() => { running--; pump(); });
    }
  }
  async function readRow(row, API) {
    const j = await (await fetch(API + 'session/' + row.id + '?after=' + Math.max(-1, (row.chunks || 0) - 60), { credentials: 'same-origin', cache: 'no-store' })).json();
    const S = await syms(row.rom_sha), keys = (j.keys || []).slice().reverse(), ch = j.chunks || [];
    const end = ch.length ? ch[ch.length - 1].start_frame + ch[ch.length - 1].frames : null;
    let best = null;
    for (let n = 0; n < Math.min(keys.length, row.live ? 1 : 4); n++) {
      const r = await fetch(API + 'session/' + row.id + '/state/' + keys[n], { credentials: 'same-origin' });
      if (!r.ok) continue;
      const info = fromState(new Uint8Array(await r.arrayBuffer()), S), k = ch.find(x => x.seq === keys[n]);
      const v = { info, seq: keys[n], age: k && end !== null ? Math.round((end - k.start_frame) / 59.185606) : null, syms: !!S };
      if (!best) best = v;
      if (info && info.players.length) { best = v; break; }
    }
    return best || { info: null, seq: null, age: null, syms: !!S };
  }
  const api = { fromState, fromCore, cols, text, syms, symsNow, forRow, STATE_SIZE, STATE_RAM, STATE_VRAM };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.SessInfo = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
