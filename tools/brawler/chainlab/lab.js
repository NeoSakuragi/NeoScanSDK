/* Chain Lab: the game in the page (core.wasm, web_core.c) and the lab mailbox (fighter.h lab_t), shared by the page
 * (index.html) and the Node proof (proof_node.js). Nothing here plays the game: the 68000 code does; this only presses
 * the pads, writes route trees into the game's RAM and reads its state back. */
(function (root) {
  'use strict';
  // pads: libretro joypad ids (web_core.c): Neo A = 0, B = 8, C = 1, D = 9, START = 3, coin (SELECT) = 2, U D L R = 4-7
  const KEYS = { a: 0, b: 8, c: 1, d: 9, s: 3, o: 2, U: 4, D: 5, L: 6, R: 7 };
  const RAM_BASE = 0x100000;
  // lab_t (fighter.h): magic 0, req 4, fighter 5, dummy 6, load 7, active 8, nev 9, frame 10, combo_hits 12, combo_dmg 14,
  // ev[64] at 16 (6 bytes: frame u16, kind, node, how, val), buf at 400 (rt_head_t + 128 nodes of 24 bytes), pack_stat at
  // 3488, pack at 3490 (a data pack, gamedata.h gdpack_t, at most GD_MAX bytes: build_tables.py pack)
  // wave 13 (req 4's first wave)
  const LAB = { magic: 0, req: 4, fighter: 5, dummy: 6, load: 7, active: 8, nev: 9, frame: 10, hits: 12, wave: 13, dmg: 14, ev: 16, buf: 400,
                packStat: 3488, pack: 3490 };
  const GD_MAX = 4096, GD_STAT = ['none', 'pending', 'installed', 'rom'];   // lab.pack_stat (gamedata.h GD_*; 0x80 | n: check n failed)
  const EV_N = 64, EV_SIZE = 6;
  const KINDS = ['START', 'HIT', 'END', 'SPECIAL', 'CHAINWIN'];
  const HOW = ['neutral', 'after end', 'cancel', 'window'];
  const BOOT_FRAMES = 400;
  const RAM_FIELDS = ['state', 'x', 'z', 'y', 'hp', 'hp_max', 'facing', 'anim', 'step', 'set', 'power', 'tint'];   // ramtrace.py FIELDS

  // ---- route trees (tools/brawler/routes.py: the same format and the same encoder) ----------------------------------
  // TODO #71 (tree version 4): A the only attack button (cA = close: an opponent within 40 px), B a jump-cancel (its
  // node is an air move, its A links an air sub-route), C + the stick the specials (slots D fD dD uD dfD ufD; inputs AB .. ufAB, the old names)
  const INPUTS = ['A', 'B', 'dA', 'cA', 'fA', 'bA', 'dfA', 'AB', 'fAB', 'dAB', 'uAB', 'dfAB', 'ufAB'];
  const SPECIAL_INPUTS = INPUTS.slice(7);
  const RI = k => { const i = INPUTS.indexOf(k); return i < 7 ? i : i + 2; };   // fighter.h RI_* (slots 7, 8 unused)
  const SPECIALS = ['D', 'fD', 'dD', 'uD', 'dfD', 'ufD'];
  const SLOT_OF = Object.fromEntries(SPECIAL_INPUTS.map((k, i) => [k, SPECIALS[i]]));
  const MOVE_NAMES = ['atk_a_close', 'atk_a_far', 'atk_a_crouch', 'atk_b_close', 'atk_b_far', 'atk_b_crouch',
    'atk_c_close', 'atk_c_far', 'atk_c_crouch', 'atk_d_close', 'atk_d_far', 'atk_d_crouch', 'body_toss',
    'cmd_fwd_a', 'cmd_fwd_b', 'cmd_df_c', 'cmd_df_d',
    // World Heroes Perfect's six buttons (routes.py MOVE_NAMES)
    'atk_ab_close', 'atk_ab_far', 'atk_ab_crouch', 'atk_cd_close', 'atk_cd_crouch', 'cmd_fwd_c', 'cmd_fwd_cd',
    'atk_a_run', 'atk_b_run', 'atk_ab_run', 'atk_c_run', 'atk_d_run', 'atk_cd_run',
    'atk_a_run_low', 'atk_b_run_low', 'atk_ab_run_low', 'atk_c_run_low', 'atk_d_run_low', 'atk_cd_run_low'];
  const AIR_MOVES = { air_a: 'atk_c_jump', air_b: 'atk_d_jump', air_cd: 'atk_cd_jump' };
  const AIR_MOVE_NAMES = Object.values(AIR_MOVES).concat(['atk_a_jump', 'atk_b_jump', 'atk_ab_jump']);   // routes.py
  const ENTRIES = ['dash', 'nospecial', 'hold', 'air_a', 'air_b', 'air_cd'];
  const WEIGHTS = ['light', 'strong'];
  const EFFECTS = ['none', 'knockdown', 'launch', 'trip', 'blowback'];
  const NODE_SIZE = 24, HEAD_SIZE = 16, RI_N = 15, TREE_VERSION = 4, MAX_NODES = 128, SPEED_MIN = 0x40, SPEED_MAX = 0x400;
  // a node's speed as the game's 8.8 (routes.speed_fx: round half up)
  function speedFx(nd) { const v = Math.floor((nd.speed === undefined ? 1 : Number(nd.speed)) * 256 + 0.5); if (!(v >= SPEED_MIN && v <= SPEED_MAX)) throw new Error('speed outside 0.25-4'); return v; }
  // the steps shown frame by frame at a speed (routes.play_steps = fighter.c anim_tick): sf = [[ticks, active, opens], ...]
  function playSteps(sf, speed) {
    const shown = [0]; let step = 0, acc = 0;
    for (let guard = 0; guard < 4000; guard++) {
      acc += speed; let done = false;
      for (;;) {
        let d = (sf[step][0] + 1) << 8;
        if (acc < d) break;
        if (step + 1 < sf.length) { acc -= d; step++; } else { done = true; break; }
        if (sf[step][1]) { d = (sf[step][0] + 1) << 8; if (acc >= d) acc = d - 1; break; }
      }
      if (done) return shown;
      shown.push(step);
    }
    return shown;
  }
  // frame data at a speed (routes.frame_data): startup, active, recovery, total, hits, frames ('x' active)
  function frameData(sf, speed) {
    const shown = playSteps(sf, speed), fr = shown.map(k => !!sf[k][1]);
    const first = fr.indexOf(true), last = fr.lastIndexOf(true), hits = new Set(shown.filter(k => sf[k][2])).size;
    return { startup: first >= 0 ? first + 1 : 0, active: first >= 0 ? last - first + 1 : 0, recovery: first >= 0 ? fr.length - 1 - last : fr.length,
             total: fr.length, hits, frames: fr.map(a => a ? 'x' : '-').join('') };
  }

  function defaultDamage(n) {
    const e = n.effect || 'none';
    if (e !== 'none') return [{ knockdown: 8, launch: 9, trip: 7, blowback: 10 }[e], 0];
    return n.weight === 'strong' ? [6, 4] : [3, 3];
  }
  // Python's json.dumps(x, sort_keys=True): the memo key that shares identical subtrees (same order as routes.py)
  function pyjson(x) {
    if (x === null || x === undefined) return 'null';
    if (typeof x === 'boolean') return x ? 'true' : 'false';
    if (typeof x === 'number') return String(x);
    if (typeof x === 'string') return JSON.stringify(x).replace(/[\u007f-￿]/g, c => '\\u' + c.charCodeAt(0).toString(16).padStart(4, '0'));
    if (Array.isArray(x)) return '[' + x.map(pyjson).join(', ') + ']';
    return '{' + Object.keys(x).sort().map(k => pyjson(k) + ': ' + pyjson(x[k])).join(', ') + '}';
  }
  /* tree -> Uint8Array (fighter.h rt_head_t + rnode_t[]); moves: the BA_* order (chainlab.json "ba"); has: the moves the
     fighter has; defaults: the default tree's entries. Throws with the node's path on an invalid tree. */
  function encodeTree(tree, moves, has, defaults) {
    const nodes = [new Uint8Array(NODE_SIZE)], memo = new Map();
    function node(nd, where, air) {
      const key = pyjson([nd, !!air]);
      if (memo.has(key)) return memo.get(key);
      const i = nodes.length; nodes.push(null); memo.set(key, i);
      const nxt = new Array(RI_N).fill(0);
      for (const [k, ch] of Object.entries(nd.links || {})) {
        if (!INPUTS.includes(k)) throw new Error(`${where}: unknown input ${k}`);
        if (SPECIAL_INPUTS.includes(k)) {
          if (!('special' in ch)) throw new Error(`${where} ${k}: a C input leads to a special`);
          if (air) throw new Error(`${where} ${k}: no special in the air`);
        } else if (!('move' in ch)) throw new Error(`${where} ${k}: an A / B input leads to a move`);
        if (air && k === 'B') throw new Error(`${where}: no jump-cancel in the air`);
        if (where === 'root' && (k === 'B' || SPECIAL_INPUTS.includes(k))) throw new Error(`root ${k}: a route starts with an A`);
        nxt[RI(k)] = node(ch, `${where} ${k}`, air || k === 'B');
      }
      let anim, flags;
      if ('special' in nd) {
        if (!SPECIALS.includes(nd.special)) throw new Error(`${where}: unknown special ${nd.special}`);
        if (nd.links && Object.keys(nd.links).length) throw new Error(`${where}: a special ends the route (no links)`);
        anim = SPECIALS.indexOf(nd.special); flags = 1;
      } else if (nd.move === undefined || nd.move === null) { anim = 0; flags = 0; }
      else {
        if (!moves.includes(nd.move)) throw new Error(`${where}: unknown move ${nd.move}`);
        if (!(air ? AIR_MOVE_NAMES : MOVE_NAMES).includes(nd.move)) throw new Error(`${where}: ${nd.move} is not an ${air ? 'air' : 'ground'} move`);
        if (has && !air && !has.includes(nd.move)) throw new Error(`${where}: the fighter has no ${nd.move}`);
        anim = moves.indexOf(nd.move); flags = (air ? 2 : 0) | (nd.keep ? 4 : 0);
      }
      const w = nd.weight || 'light', e = nd.effect || 'none';
      if (!WEIGHTS.includes(w) || !EFFECTS.includes(e)) throw new Error(`${where}: weight ${w} / effect ${e}`);
      const [dd, dp] = defaultDamage(nd);
      const dmg = nd.damage !== undefined ? nd.damage : dd, push = nd.push !== undefined ? nd.push : dp;
      if (!(dmg >= 0 && dmg <= 255 && push >= -128 && push <= 127)) throw new Error(where + ': damage / push');
      const sp = speedFx(nd);
      nodes[i] = Uint8Array.from([anim, flags, WEIGHTS.indexOf(w), EFFECTS.indexOf(e), dmg, push & 0xFF, sp >> 8, sp & 0xFF, ...nxt, 0]);
      return i;
    }
    const rootI = node({ links: tree.links || {} }, 'root', false);
    const ents = tree.entries || {};
    const ent = ENTRIES.map(k => {
      return node(ents[k] || defaults[k], k, !!AIR_MOVES[k]);   // an air entry: its own move (any of the three)
    });
    if (nodes.length > MAX_NODES) throw new Error(`${nodes.length} nodes (at most ${MAX_NODES})`);
    const out = new Uint8Array(HEAD_SIZE + nodes.length * NODE_SIZE);
    out.set([82, 84, TREE_VERSION, nodes.length, rootI, ...ent, 0, 0, 0, 0, 0]);
    nodes.forEach((n, i) => out.set(n, HEAD_SIZE + i * NODE_SIZE));
    return out;
  }
  // the node index encodeTree gives each node object of the tree (the readout maps the game's events back to the tree)
  function nodeIndex(tree) {
    const map = new Map(), memo = new Map(); let n = 1;
    function node(nd, air) {
      const key = pyjson([nd, !!air]);
      if (memo.has(key)) { map.set(nd, memo.get(key)); return; }
      const i = n++; memo.set(key, i); map.set(nd, i);
      for (const [k, ch] of Object.entries(nd.links || {})) node(ch, air || k === 'B');
    }
    node({ links: tree.links || {} }, false);
    return map;
  }

  // ---- the core ---------------------------------------------------------------------------------------------------
  class Lab {
    constructor(core, layout) {
      this.core = core; this.layout = layout;
      this.lab = layout.syms.lab; this.fighters = layout.syms.fighters;
      this.pads = [0, 0]; this.frame = 0;
      this.state = null;                         // a save state of the training start (quick restart)
    }
    static async create(GeoCore, files, layout) {   // files: {bios: Uint8Array, rom: Uint8Array}
      const core = await GeoCore(files.moduleArgs || {});
      core.FS.mkdir('/sys'); core.FS.mkdir('/rom'); core.FS.mkdir('/save');
      core.FS.writeFile('/sys/neogeo.zip', files.bios);
      core.FS.writeFile('/rom/game.neo', files.rom);
      if (!core._wc_init()) throw new Error('the core did not load the game');
      return new Lab(core, layout);
    }
    get heap() { return this.core.HEAPU8; }      // re-read: memory growth replaces the buffer
    ramAddr(a) { return this.core._wc_ram() + (a - RAM_BASE); }
    r8(a) { return this.heap[this.ramAddr(a)]; }
    r16(a) { const p = this.ramAddr(a); return (this.heap[p] << 8) | this.heap[p + 1]; }
    r32(a) { const p = this.ramAddr(a), h = this.heap; return ((h[p] << 24) | (h[p + 1] << 16) | (h[p + 2] << 8) | h[p + 3]) >>> 0; }
    w8(a, v) { this.heap[this.ramAddr(a)] = v & 0xFF; }
    wbytes(a, bytes) { this.heap.set(bytes, this.ramAddr(a)); }
    setPad(port, keys) { let b = 0; for (const k of keys) if (k in KEYS) b |= 1 << KEYS[k]; this.pads[port] = b; }
    run(n = 1) {
      for (let i = 0; i < n; i++) {
        this.core._wc_pad(0, this.pads[0]); this.core._wc_pad(1, this.pads[1]);
        this.core._wc_run(); this.frame++;
      }
    }
    fget(i, field) {
      const [off, sz] = this.layout.fields[field], a = this.fighters + i * this.layout.fsize + off;
      let v = sz === 1 ? this.r8(a) : sz === 2 ? this.r16(a) : this.r32(a);
      if (['x', 'z', 'y', 'vx', 'vz', 'vy'].includes(field)) return ((v | 0)) / 65536;
      if (field === 'facing' || field === 'hp') { const bits = 8 * sz; if (v >> (bits - 1)) v -= 2 ** bits; }
      return v;
    }
    stateName(i) { return this.layout.states[this.fget(i, 'state')]; }
    // the mailbox
    active() { return this.r8(this.lab + LAB.active) === 1; }
    labFrame() { return this.r16(this.lab + LAB.frame); }
    combo() { return { hits: this.r8(this.lab + LAB.hits), dmg: this.r16(this.lab + LAB.dmg) }; }
    request(req, fighter, dummy) {
      this.wbytes(this.lab + LAB.magic, [76, 65, 66, 49]);
      if (fighter !== undefined) this.w8(this.lab + LAB.fighter, fighter);
      if (dummy !== undefined) this.w8(this.lab + LAB.dummy, dummy);
      this.w8(this.lab + LAB.req, req);
    }
    installTree(fighter, blob) {                 // the game takes it on its next tick (lab_install)
      this.wbytes(this.lab + LAB.buf, blob);
      this.w8(this.lab + LAB.fighter, fighter);
      this.w8(this.lab + LAB.load, blob ? 1 : 2);
    }
    /* a data pack (stages, enemies, AI rows): checked on the game's next tick, installed at its next safe point (a wave,
       the boss, a stage start, the enemy test's respawn); null = back to the ROM's tables */
    installPack(bytes) {
      if (bytes) { if (bytes.length > GD_MAX) throw new Error('pack too big'); this.wbytes(this.lab + LAB.pack, bytes); }
      this.wbytes(this.lab + LAB.magic, [76, 65, 66, 49]);
      this.w8(this.lab + LAB.load, bytes ? 3 : 4);
    }
    /* req 4: P1 = fighter alone in campaign stage `stage` (0-based) from wave `wave` (>= its waves: the boss), on the game's
       next tick; a pack sent just before is installed first (the stage start is a safe point) */
    playStage(fighter, stage, wave) { this.w8(this.lab + LAB.wave, wave); this.request(4, fighter, stage); }
    playMusic(cmd) { this.request(5, undefined, cmd); }     // req 5: snd_music(cmd), a songs.h MUS_* command
    /* tools/brawler/ramtrace.py snap(): the flow and each fighter, the same values and rounding (the proofs compare them) */
    ramSnap() {
      const y = this.layout.syms, s16 = a => (this.r16(a) << 16) >> 16, OFF = this.layout.states.indexOf('OFF');
      const flow = [this.r8(y.mode), this.r8(y.attract), this.r8(y.phase), this.r8(y.wave), s16(y.cam_x), s16(y.lock_x)];
      const fs = [];
      for (let i = 0; i < 8; i++) {
        if (this.fget(i, 'state') === OFF) { fs.push(null); continue; }
        fs.push([...RAM_FIELDS.map(f => (f === 'x' || f === 'z' || f === 'y') ? this.round2(i, f) : this.fget(i, f)),
                 (this.fget(i, 'ch') - y.bm_chars) / this.layout.sizeof_bchar]);
      }
      return [flow, fs];
    }
    round2(i, f) {                                  // Python round(v, 2) of a 16.16 field: exact, half to even
      const n = (this.r32(this.fighters + i * this.layout.fsize + this.layout.fields[f][0]) | 0) * 100;
      let q = Math.floor(n / 65536); const r = n - q * 65536;
      if (r > 32768 || (r === 32768 && (q & 1))) q++;
      return q / 100;
    }
    /* palette `slot` (bank 0) as the game wrote it: 16 colour words (web_core.c wc_palram, geolith's palette RAM) */
    palette(slot) { const p = (this.core._wc_palram() >> 1) + slot * 16; return Array.from(this.core.HEAP16.subarray(p, p + 16), v => v & 0xFFFF); }
    /* req 3: P1 = fighter against enemy definition `enemy` (EN_* / the pack's order) with its own AI; a pack sent just
       before is installed first */
    enemyTest(fighter, enemy) { this.request(3, fighter, enemy); }
    gameTicks() { return this.r32(this.layout.syms.game_ticks); }
    packStatus() { const v = this.r8(this.lab + LAB.packStat); return v & 0x80 ? 'bad (check ' + (v & 0x7F) + ')' : GD_STAT[v]; }
    nev() { return this.r8(this.lab + LAB.nev); }
    eventsSince(from) {                          // [from, nev) of the ring (at most its 64 latest)
      const n = this.nev(), out = [];
      let k = (n - from) & 0xFF; if (k > EV_N) { from = (n - EV_N) & 0xFF; k = EV_N; }
      for (let j = 0; j < k; j++) {
        const i = (from + j) & (EV_N - 1), a = this.lab + LAB.ev + i * EV_SIZE;
        out.push({ frame: this.r16(a), kind: KINDS[this.r8(a + 2)], node: this.r8(a + 3), how: this.r8(a + 4), val: this.r8(a + 5) });
      }
      return { events: out, next: n };
    }
    /* power on -> the BIOS hands over -> the training (fighter vs dummy): the same steps as labdrive.py */
    boot(fighter, dummy, blob) {
      this.core._wc_reset(); this.frame = 0; this.pads = [0, 0];
      this.run(BOOT_FRAMES);
      if (blob) this.installTree(fighter, blob);
      this.request(1, fighter, dummy);
      for (let k = 0; k < 3000 && !this.active(); k++) this.run(1);
      if (!this.active()) throw new Error('the training did not start');
      this.run(2);
    }
    saveState() { const n = this.core._wc_state_size(), p = this.core._malloc(n); this.core._wc_save(p, n); const s = this.heap.slice(p, p + n); this.core._free(p); return s; }
    loadState(s) { const p = this.core._malloc(s.length); this.heap.set(s, p); this.core._wc_load(p, s.length); this.core._free(p); }
  }

  // ---- routes as the source (routes.py merge_routes / tree_to_routes: the same merge) ---------------------------------
  const HIT_FIELDS = ['move', 'special', 'weight', 'effect', 'keep', 'speed', 'damage', 'push'];
  function hitOf(nd) {                 // a step's hit as the game plays it (defaults applied)
    if ('special' in nd) return { special: nd.special, speed: speedFx(nd) };
    const [dd, dp] = defaultDamage(nd);
    return { move: nd.move, weight: nd.weight || 'light', effect: nd.effect || 'none', keep: !!nd.keep, speed: speedFx(nd),
             damage: nd.damage !== undefined ? nd.damage : dd, push: nd.push !== undefined ? nd.push : dp };
  }
  function pick(o, fields) { const r = {}; for (const f of fields) if (f in o) r[f] = o[f]; return r; }
  function treeToRoutes(tree) {
    const out = [];
    (function walk(links, path) {
      for (const [k, ch] of Object.entries(links || {})) {
        const st = Object.assign(pick(ch, HIT_FIELDS), { input: k });
        if (ch.links && Object.keys(ch.links).length) walk(ch.links, path.concat([st])); else out.push(path.concat([st]).map(x => Object.assign({}, x)));   // each route its own steps
      }
    })(tree.links, []);
    return out;
  }
  // routes -> {tree: {links}, conflicts: [{routes: [i, j] 1-based, step 1-based, inputs, differs {field: [a, b]}}],
  // paths: per route the tree nodes its steps reached (up to a conflict)}
  function mergeRoutes(routes) {
    const root = { links: {} }, owner = new Map(), conflicts = [], paths = [];
    routes.forEach((r, ri) => {
      let nd = root; const path = [];
      for (let si = 0; si < r.length; si++) {
        const st = r[si], k = st.input, hit = pick(st, HIT_FIELDS);
        if (!INPUTS.includes(k)) throw new Error(`route ${ri + 1} step ${si + 1}: unknown input ${k}`);
        if (!si && (k === 'B' || SPECIAL_INPUTS.includes(k))) throw new Error(`route ${ri + 1}: a route starts with an A (B from neutral jumps, C is the special)`);
        let ch = nd.links && nd.links[k];
        if (!ch) {
          if ('special' in nd) throw new Error(`route ${ri + 1} step ${si + 1}: a special ends its route`);
          ch = Object.assign({}, hit); nd.links = nd.links || {}; nd.links[k] = ch; owner.set(ch, ri);
        } else {
          const a = hitOf(ch), b = hitOf(hit);
          if (pyjson(a) !== pyjson(b)) {
            const differs = {};
            for (const f of new Set([...Object.keys(a), ...Object.keys(b)])) if (pyjson(a[f]) !== pyjson(b[f])) differs[f] = [a[f], b[f]];
            conflicts.push({ routes: [owner.get(ch) + 1, ri + 1], step: si + 1, inputs: r.slice(0, si + 1).map(x => x.input), differs });
            break;
          }
        }
        path.push(ch); nd = ch;
      }
      paths.push(path);
    });
    return { tree: root, conflicts, paths };
  }

  const api = { Lab, speedFx, hitOf, treeToRoutes, mergeRoutes, HIT_FIELDS, playSteps, frameData, KEYS, KINDS, HOW, INPUTS, SPECIAL_INPUTS, SPECIALS, SLOT_OF, AIR_MOVE_NAMES, MOVE_NAMES, ENTRIES, WEIGHTS, EFFECTS, AIR_MOVES,
    encodeTree, nodeIndex, defaultDamage, pyjson, BOOT_FRAMES };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.ChainLab = api;
})(typeof window !== 'undefined' ? window : globalThis);
