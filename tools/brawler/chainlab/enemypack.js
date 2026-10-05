/* Brawler Lab, Enemies tab: game.json's `enemies` + AI presets -> the pack's first part (AI rows, enemies with pools,
 * names, palettes, trees), in the page (and in Node for the proof). The same rules and bytes as build_tables.py model()'s
 * enemy half and pack_base; the stages are appended by stagepack.js, so an unedited game.json packs to build_tables.py
 * pack's file byte for byte. Colours: the Neo Geo colour word (gamedata / neo_types.h RGB, fighter.c tint_colour). */
(function (root) {
  'use strict';
  const CL = root.ChainLab || (typeof require !== 'undefined' ? require('./lab.js') : null);
  const PACK_HEAD = 20, EN_SIZE = 26, GE_SPAWN = 0xFF, GE_FIGHTER_NAME = 1;
  const HUD_RE = /^[A-Z0-9_ .!-]{1,10}$/, NAME_RE = /^[A-Z][A-Z0-9_]{0,9}$/;

  // ---- colours ------------------------------------------------------------------------------------------------------
  const ch5 = w => [((w >> 7) & 0x1E) | ((w >> 14) & 1), ((w >> 3) & 0x1E) | ((w >> 13) & 1), ((w << 1) & 0x1E) | ((w >> 12) & 1)];
  const word = (r, g, b, dark) => ((r & 1) << 14) | ((r >> 1) << 8) | ((g & 1) << 13) | ((g >> 1) << 4) | ((b & 1) << 12) | (b >> 1) | (dark ? 0x8000 : 0);
  function rgb8(w) {                                  // move_images._colour: what the page shows for a word
    let [r, g, b] = ch5(w).map(v => (v << 3) | (v >> 2));
    if (w & 0x8000) { r = Math.max(0, r - 4); g = Math.max(0, g - 4); b = Math.max(0, b - 4); }
    return [r, g, b];
  }
  function tint(t, c) {                               // fighter.c tint_colour (int16 maths, clamped 0-31, no dark bit)
    const v = ch5(c), l = (v[0] * 5 + v[1] * 9 + v[2] * 2) >> 4;
    for (let k = 0; k < 3; k++) {
      const m = (l * t.mix + v[k]) << 16 >> 16, p = (m * t.mul) << 16 >> 16;
      v[k] = Math.max(0, Math.min(31, (p >> t.shift) + t.add[k]));
    }
    return word(v[0], v[1], v[2], 0);
  }
  /* the palettes the game loads for an enemy (main.c enemy_init, fighter.c fighter_load_pals): set `set` of the fighter
     (img: enemy_images' npal / nsets / pals), palette 0 replaced by the custom colours, colours 1-15 tinted */
  function enemyPals(img, set, tintDef, custom) {
    const s = set % img.nsets, out = [];
    for (let i = 0; i < img.npal; i++) {
      const src = i === 0 && custom ? custom : img.pals.slice((s * img.npal + i) * 16, (s * img.npal + i + 1) * 16);
      out.push(src.map((c, j) => j && tintDef ? tint(tintDef, c) : c));
    }
    return out;
  }
  const num = v => typeof v === 'number' ? v : parseInt(String(v), String(v).match(/^0x/i) ? 16 : 10);

  // ---- AI rows (build_tables.py ai_row) -------------------------------------------------------------------------------
  function aiRow(n, p, X) {
    let fl = 0;
    for (const f of p.flags || []) { if (!(f in X.ai_flags)) throw new Error(`AI ${n}: no flag ${f}`); fl |= X.ai_flags[f]; }
    const v = { flags: fl };
    for (const k of X.ai_fields) v[k] = p[k] === undefined ? 0 : p[k];
    for (const [k, m] of Object.entries(X.chance_masks)) {
      const ch = p[k] === undefined ? (k === 'follow_ups' ? 1 : 0) : p[k];
      if (k === 'follow_ups') v[m] = ch ? (1 << (32 - Math.clz32(ch))) - 1 : 0;
      else { if (ch !== 0 && (ch & (ch - 1))) throw new Error(`AI ${n}: ${k} must be 1 in a power of two`); v[m] = ch ? ch - 1 : 0; }
    }
    const pc = p.proj_chance === undefined ? 512 : p.proj_chance;
    if (!(pc >= 1 && !(pc & (pc - 1)) && pc <= 65536)) throw new Error(`AI ${n}: proj_chance must be a power of two`);
    v.proj_mask = Math.min(pc, 256) - 1; v.proj_mask2 = Math.max(pc >> 8, 1) - 1;
    for (const [k, x] of Object.entries(v)) if (!(Number.isInteger(x) && x >= 0 && x <= 255)) throw new Error(`AI ${n}: ${k} = ${x} (0-255)`);
    return X.ai_order.map(k => v[k]);
  }

  // ---- move lists (routes.py enemy_preset, build_tables.py enemy_tree) ------------------------------------------------
  function stripSpecials(nd) {
    const out = {};
    for (const [k, v] of Object.entries(nd)) if (k !== 'links') out[k] = v;
    const links = {};
    for (const [k, v] of Object.entries(nd.links || {})) if (!CL.SPECIAL_INPUTS.includes(k)) links[k] = stripSpecials(v);
    if (Object.keys(links).length) out.links = links;
    return out;
  }
  function enemyPreset(name, own) {
    if (name === 'no_specials') {
      const ents = {}; for (const [k, v] of Object.entries(own.entries || {})) ents[k] = stripSpecials(v);
      return Object.assign(stripSpecials(own), { entries: ents });
    }
    if (name !== 'jabs') throw new Error(`no enemy move preset ${name}`);
    const c = { move: 'atk_c_close', weight: 'strong', effect: 'none' };
    const a2 = { move: 'atk_a_far', weight: 'light', effect: 'none', links: { A: c } };
    return { fighter: own.fighter, links: { A: { move: 'atk_a_close', weight: 'light', effect: 'none', links: { A: a2 } } } };
  }
  /* the tree an enemy plays as fighter `b` (routes.py form, entries filled), or null = its own (the ROM's route_tab) */
  function treeFor(e, b, X, chain) {
    const m = e.moves === undefined ? 'own' : e.moves, F = chain.fighters.find(f => f.name === b);
    if (m === 'own') return null;
    if (!F) throw new Error(`no fighter ${b}`);
    if (!String(m).endsWith('.json')) return enemyPreset(m, F.tree);
    const t = X.route_files[m];
    if (!t) throw new Error(`no routes file ${m}`);
    return Object.assign({}, JSON.parse(JSON.stringify(t)), { entries: Object.assign({}, F.default.entries, t.entries || {}), fighter: b });
  }
  const basesOf = (e, idx) => e.base === 'pool' ? (e.pool || []) : [idx.has(e.base) ? e.base : e.stand_in];
  function enemyTree(e, X, chain, idx) {
    if ((e.moves === undefined ? 'own' : e.moves) === 'own') return null;
    let blob = null;
    for (const b of basesOf(e, idx)) {
      const F = chain.fighters.find(f => f.name === b);
      const x = CL.encodeTree(treeFor(e, b, X, chain), chain.ba, F.has, F.default.entries);
      if (blob && (blob.length !== x.length || blob.some((v, i) => v !== x[i]))) throw new Error('its tree differs between its fighters');
      blob = x;
    }
    return blob;
  }

  /* enemies + presets (game.json form) -> {ai: [[name, bytes]], enemies: [rows], errors} (build_tables.py model()) */
  function model(enemies, presets, X, chain) {
    const errors = [], idx = new Map(X.roster.map((n, i) => [n, i])), tints = ['none', ...Object.keys(X.tints)];
    const ai = [], rows = [];
    for (const [n, p] of Object.entries(presets)) { try { ai.push([n, aiRow(n, p, X)]); } catch (e) { errors.push(e.message); ai.push([n, X.ai_order.map(() => 0)]); } }
    const names = enemies.map(e => e.name);
    names.forEach((n, i) => { if (names.indexOf(n) !== i) errors.push(`enemies: ${n} twice`); });
    function row(name, preset, over) {
      if (!(preset in presets)) throw new Error(`no AI preset ${preset}`);
      if (!over || !Object.keys(over).length) return Object.keys(presets).indexOf(preset);
      const v = aiRow(name, Object.assign({}, presets[preset], over), X), key = v.join(',');
      const i = ai.findIndex(([, w]) => w.join(',') === key);
      if (i >= 0) return i;
      ai.push([`${name}_${preset}`, v]); return ai.length - 1;
    }
    for (const e of enemies) {
      const n = e.name, E = `enemy ${n}`;
      try {
        if (!NAME_RE.test(n)) throw new Error('its name: 1-10 characters A-Z 0-9 _, a letter first (EN_' + n + ' in the C tables)');
        const hud = e.hud === undefined ? n : e.hud;
        if (hud !== 'fighter' && !HUD_RE.test(hud)) throw new Error('HUD name 1-10 characters (A-Z 0-9 _ . ! -)');
        for (const k of Object.keys(e)) if (!['name', 'base', 'pool', 'stand_in', 'life', 'power', 'ai', 'attract_ai', 'ai_over', 'palette', 'moves', 'hud'].includes(k)) throw new Error(`unknown field ${k}`);
        let base, pl;
        if (e.base === 'pool') {
          pl = (e.pool || []).map(x => { if (!idx.has(x)) throw new Error(`pool: no fighter ${x}`); return idx.get(x); });
          if (!pl.length) throw new Error('an empty pool');
          if (pl.some((v, i) => i && v < pl[i - 1])) throw new Error('list the pool in roster order');
          base = GE_SPAWN;
        } else {
          const b = idx.has(e.base) ? e.base : e.stand_in;
          if (!idx.has(b)) throw new Error(`neither ${e.base} nor its stand-in is in the roster`);
          base = idx.get(b); pl = [];
        }
        const over = e.ai_over || {};
        for (const k of Object.keys(over)) if (!X.ai_fields.includes(k) && !(k in X.chance_masks) && k !== 'flags' && k !== 'proj_chance') throw new Error(`ai_over ${k}`);
        const pal = e.palette || {};
        for (const k of Object.keys(pal)) if (!['set', 'tint', 'custom'].includes(k)) throw new Error(`palette ${k}`);
        let cu = pal.custom === undefined || pal.custom === null ? null : pal.custom.map(num);
        if (cu && !(cu.length === 16 && cu.every(c => Number.isInteger(c) && c >= 0 && c <= 0xFFFF))) throw new Error('custom = 16 Neo Geo colours (0-$FFFF)');
        const st = pal.set !== undefined ? pal.set : (cu === null && !('tint' in pal) ? GE_SPAWN : 0);
        const ti = pal.tint === undefined ? null : pal.tint;
        if (ti !== null && !tints.includes(ti)) throw new Error(`no tint ${ti}`);
        if (!(st === GE_SPAWN || (Number.isInteger(st) && st >= 0 && st < 255))) throw new Error(`palette set ${st}`);
        const power = e.power === undefined ? 0 : e.power;
        if (!(Number.isInteger(e.life) && e.life >= 1 && e.life <= 32767 && Number.isInteger(power) && power >= 0 && power <= 255)) throw new Error('life 1-32767, power 0-255');
        rows.push({ name: n, base, pool: pl, ai: row(n, e.ai, over), attract_ai: row(n, e.attract_ai === undefined ? e.ai : e.attract_ai, over), power,
                    set: st, tint: ti === null ? GE_SPAWN : tints.indexOf(ti), flags: hud === 'fighter' ? GE_FIGHTER_NAME : 0, life: e.life,
                    hud: hud === 'fighter' ? null : hud.replace(/_/g, ' '), pal: cu, moves: enemyTree(e, X, chain, idx) });
      } catch (err) { errors.push(`${E}: ${err.message}`); }
    }
    if (ai.length > 255) errors.push('at most 255 AI rows');
    return { ai, enemies: rows, errors };
  }

  /* build_tables.py pack_base: the header's room, the AI rows, the enemies with their pools, names, palettes, trees */
  function packBase(M) {
    const out = new Array(PACK_HEAD).fill(0);
    const put = (bytes, align = 2) => { while (out.length % align) out.push(0); const o = out.length; for (const b of bytes) out.push(b); return o; };
    const be16 = v => [(v >> 8) & 0xFF, v & 0xFF], be32 = v => [0, 0, ...be16(v)];
    const ai_o = put(M.ai.flatMap(([, v]) => v));
    const recs = [];
    for (const e of M.enemies) {
      const pool = e.pool.length ? put(e.pool, 1) : 0;
      const name = e.hud ? put([...[...e.hud].map(c => c.charCodeAt(0)), 0], 1) : 0;
      const pal = e.pal ? put(e.pal.flatMap(be16)) : 0;
      const moves = e.moves ? put(e.moves) : 0;
      recs.push([e.base, e.ai, e.attract_ai, e.power, e.pool.length, e.set, e.tint, e.flags, ...be16(e.life & 0xFFFF), ...be32(pool), ...be32(name), ...be32(pal), ...be32(moves)]);
    }
    const en_o = put(recs.flat());
    return { bytes: out, en_o, ai_o };
  }

  /* what stagepack.js needs in place of stages.json's pre-built part: the base bytes (hex), offsets, the enemies */
  function stageData(enemies, presets, X, chain, D) {
    const M = model(enemies, presets, X, chain);
    if (M.errors.length) return { errors: M.errors };
    const B = packBase(M), idx = new Map(X.roster.map((n, i) => [n, i]));
    const ens = enemies.map(e => {
      const b = e.base === 'pool' || idx.has(e.base) ? e.base : e.stand_in;
      return { name: e.name, base: b, pool: e.pool || [], life: e.life, unlock_of: idx.has(b) ? X.unlock[idx.get(b)] : 0 };
    });
    return { errors: [], model: M, D: Object.assign({}, D, { base: B.bytes.map(v => v.toString(16).padStart(2, '0')).join(''), en_o: B.en_o, ai_o: B.ai_o, nai: M.ai.length, enemies: ens }) };
  }

  const api = { model, packBase, stageData, aiRow, enemyPreset, stripSpecials, treeFor, enemyPals, tint, rgb8, word, ch5, num, NAME_RE, HUD_RE, GE_SPAWN };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.EnemyPack = api;
})(typeof window !== 'undefined' ? window : globalThis);
