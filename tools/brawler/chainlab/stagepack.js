/* Brawler Lab, Stages tab: game.json's `stages` -> the stage part of a data pack, in the page (and in Node for the proof).
 * The same rules and bytes as tools/brawler/build_tables.py (model()'s stage half, pack_stages); the AI rows and enemies
 * come pre-built from the site's stages.json (build_tables.py labstages: pack_base's bytes), so an unedited campaign
 * packs to build_tables.py pack's file byte for byte. */
(function (root) {
  'use strict';
  const SP_WALK_IN = 1, SP_LEFT = 2, SP_NOT_BOSS = 4, GD_VERSION = 3, PACK_HEAD = 18, ST_SIZE = 24;

  function num(v) { return typeof v === 'string' ? parseInt(v, v.startsWith('0x') || v.startsWith('0X') ? 16 : 10) : v; }
  const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;

  /* stages (game.json form) -> {stages: model rows, errors: [messages]} (build_tables.py model(): the stage checks, plus
     the byte ranges the binary needs) */
  function model(stages, D) {
    const errors = [], en = new Map(D.enemies.map((e, i) => [e.name, i])), tints = new Map(D.tints.map((t, i) => [t, i]));
    const out = [];
    const err = m => errors.push(m);
    function spawn(d, where) {
      if (!en.has(d.enemy)) err(`${where}: no enemy ${d.enemy}`);
      let fl = 0;
      const x = d.x === undefined ? 0 : d.x;
      if (d.walk_in) {
        const w = d.walk_in, r = w.rank === undefined ? 0 : w.rank;
        if (w.side !== 'left' && w.side !== 'right') err(`${where}: side ${w.side}`);
        if (!isInt(r, 0, 15)) err(`${where}: delay (rank) ${r} outside 0-15`);
        fl |= SP_WALK_IN | (w.side === 'left' ? SP_LEFT : 0) | ((r & 15) << 4);
      } else if (!isInt(x, -32768, 32767)) err(`${where}: x ${x}`);
      if (d.not_boss) fl |= SP_NOT_BOSS;
      const t = d.tint === undefined ? 'none' : d.tint;
      if (!tints.has(t)) err(`${where}: no tint ${t}`);
      const pick = d.pick === undefined ? 0 : d.pick, set = d.set === undefined ? 0 : d.set;
      if (!isInt(pick, 0, 255) || !isInt(set, 0, 255)) err(`${where}: pick / set 0-255`);
      if (!isInt(d.z, 0, 255)) err(`${where}: z ${d.z} outside 0-255`);
      return { enemy: en.get(d.enemy) || 0, pick, set, tint: tints.get(t) || 0, x, z: d.z, flags: fl };
    }
    if (stages.length !== D.stages.length) err(`${stages.length} stages: the ROM has ${D.stages.length} (a pack replaces all of them)`);
    stages.forEach((s, si) => {
      const S = `stage ${si + 1}`;
      const ww = D.widths ? D.widths[s.background] : null;
      if (D.widths && ww === undefined) err(`${S}: background ${s.background} is not in this ROM`);
      const sp = [], wv = [];
      if (!s.waves.length) err(`${S}: at least one wave`);
      s.waves.forEach((w, wi) => {
        const W = `${S} wave ${wi + 1}`;
        if (w.spawns.length < 1 || w.spawns.length > D.max_enemies) err(`${W}: 1-${D.max_enemies} spawns (${w.spawns.length})`);
        if (ww && !(w.lock >= 0 && w.lock <= ww - 320)) err(`${W}: lock ${w.lock} outside 0-${ww - 320}`);
        if (wi && w.lock < s.waves[wi - 1].lock) err(`${S}: lock points go forward (wave ${wi + 1} at ${w.lock} < ${s.waves[wi - 1].lock})`);
        const seed = num(w.seed);
        if (!isInt(seed, 0, 0xFFFF)) err(`${W}: seed ${w.seed}`);
        wv.push({ lock: w.lock, seed, first: sp.length, n: w.spawns.length });
        w.spawns.forEach((d, k) => sp.push(spawn(d, `${W} spawn ${k + 1}`)));
      });
      const b = s.boss, nb = sp.length;
      if (b.minions.length > D.max_enemies - 1) err(`${S}: at most ${D.max_enemies - 1} minions with the boss`);
      if (ww && b.lock > ww - 320) err(`${S}: boss lock ${b.lock} past the end (${ww - 320})`);
      if (s.waves.length && b.lock < s.waves[s.waves.length - 1].lock) err(`${S}: the boss's lock point is before the last wave's`);
      if (!isInt(b.x, -32768, 32767) || !isInt(b.z, 0, 255)) err(`${S}: boss x / z`);
      b.minions.forEach((d, k) => sp.push(spawn(d, `${S} boss minion ${k + 1}`)));
      if (!en.has(b.enemy)) err(`${S}: no enemy ${b.enemy}`);
      const bi = en.get(b.enemy) || 0;
      if (!(s.music in D.songs)) err(`${S}: no song ${s.music}`);
      if (!(b.song in D.songs)) err(`${S}: no song ${b.song}`);
      const bseed = num(b.seed);
      if (!isInt(bseed, 0, 0xFFFF)) err(`${S}: boss seed ${b.seed}`);
      const power = s.power === undefined ? 0 : s.power;
      if (!isInt(power, 0, 255)) err(`${S}: power 0-255`);
      out.push({ bg: s.background, music: D.songs[s.music], power, waves: wv, spawns: sp, boss: bi, boss_song: D.songs[b.song],
                 unlock: D.enemies[bi] && D.enemies[bi].unlock_of === si + 1 ? 1 : 0, boss_lock: b.lock, boss_x: b.x, boss_z: b.z,
                 boss_seed: bseed, boss_first: nb, nmin: b.minions.length });
    });
    return { stages: out, errors };
  }

  /* the whole pack: stages.json's base bytes + the stages + the roster section (build_tables.py pack_stages); spmap: the
     specials by role, 4 bytes per roster fighter (the Characters tab's, else stages.json's = game.json's); vtabs: per
     roster fighter its voice table (bytes) when it differs from the ROM's, else null (version 3) */
  function pack(stages, D, spmap, vtabs) {
    const M = model(stages, D);
    if (M.errors.length) return { bytes: null, errors: M.errors };
    const base = D.base.match(/../g).map(h => parseInt(h, 16)), out = base.slice();
    const put = (bytes, align = 2) => { while (out.length % align) out.push(0); const o = out.length; out.push(...bytes); return o; };
    const be16 = v => [(v >> 8) & 0xFF, v & 0xFF];
    const nsp = Math.max(...M.stages.map(s => s.spawns.length));
    const rows = [];
    for (const s of M.stages) {
      const sp = s.spawns.concat(Array(nsp - s.spawns.length).fill(s.spawns[s.spawns.length - 1]));
      const spo = put(sp.flatMap(d => [d.enemy, d.pick, d.set, d.tint, ...be16(d.x), d.z, d.flags]));
      const wvo = put(s.waves.flatMap(w => [...be16(w.lock), ...be16(w.seed), w.first, w.n]));
      const r = new Array(ST_SIZE).fill(0);
      r[0] = s.bg; r[1] = s.music; r[2] = s.power; r[3] = s.waves.length;
      r.splice(4, 4, 0, 0, ...be16(wvo)); r.splice(8, 4, 0, 0, ...be16(spo));
      r[12] = s.boss; r[13] = s.boss_song; r[14] = s.unlock; r[15] = s.boss_z;
      r.splice(16, 2, ...be16(s.boss_lock)); r.splice(18, 2, ...be16(s.boss_x)); r.splice(20, 2, ...be16(s.boss_seed));
      r[22] = s.boss_first; r[23] = s.nmin;
      rows.push(...r);
    }
    const sto = put(rows);
    const sm = spmap || D.spmap, vt = vtabs || Array(sm.length / 4).fill(null);
    const roo = put(sm.concat(Array(2 * vt.length).fill(0)));   // version 3: + per fighter its voice table's offset
    vt.forEach((t, i) => { if (t) { const o = put(t, 1); out[roo + sm.length + 2 * i] = o >> 8; out[roo + sm.length + 2 * i + 1] = o & 0xFF; } });
    while (out.length % 2) out.push(0);
    if (out.length > D.gd_max) return { bytes: null, errors: [`pack: ${out.length} bytes (at most ${D.gd_max})`] };
    const head = [71, 68, GD_VERSION, M.stages.length, D.enemies.length, D.nai, ...be16(out.length), ...be16(sto), ...be16(D.en_o),
                  ...be16(D.ai_o), ...be16(nsp), ...be16(roo)];
    head.forEach((v, i) => { out[i] = v; });
    return { bytes: Uint8Array.from(out), errors: [], model: M.stages };
  }

  /* build_tables.py fmt(): game.json's layout (a container that fits 120 characters on one line, the others open) */
  function dumps(o) {
    if (o === null) return 'null';
    if (Array.isArray(o)) return '[' + o.map(dumps).join(', ') + ']';
    if (typeof o === 'object') return '{' + Object.entries(o).map(([k, v]) => JSON.stringify(k) + ': ' + dumps(v)).join(', ') + '}';
    return JSON.stringify(o);
  }
  function fmt(o, depth = 0) {
    const open = o && typeof o === 'object' && (Array.isArray(o) ? o.length : Object.keys(o).length);
    if (open && [...dumps(o)].length + depth > 120) {
      const pad = ' '.repeat(depth + 1);
      if (Array.isArray(o)) return '[\n' + o.map(v => pad + fmt(v, depth + 1)).join(',\n') + '\n' + ' '.repeat(depth) + ']';
      return '{\n' + Object.entries(o).map(([k, v]) => `${pad}${JSON.stringify(k)}: ${fmt(v, depth + 1)}`).join(',\n') + '\n' + ' '.repeat(depth) + '}';
    }
    return dumps(o);
  }

  /* where a spawn enters (main.c spawn_x): world x at a camera position */
  function spawnX(d, cam) {
    if (!d.walk_in) return d.x;
    const r = (d.walk_in.rank || 0) * 36;
    if (d.walk_in.side === 'left' && cam >= 64) return cam - 24 - r;
    return cam + 340 + r;
  }

  const api = { model, pack, fmt, dumps, spawnX, num };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.StagePack = api;
})(typeof window !== 'undefined' ? window : globalThis);
