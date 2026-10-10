// The Character Lab's shell + packs, proven on the Lab's wasm core (web_core.c wc_swap_pack = pack_swap.c, the Player's
// path too): boot lab-shell.neo (it starts the practice by itself, P1 = the slot fighter), play his chain and a special,
// swap in another pack (the core's ROM then equals that fighter's own build byte for byte), play his, swap back.
// Screens and a JSON report to OUT.
//   node packs_proof_node.js SITE_DIR SHELL.neo LAYOUT.json OUT_DIR  A.pack:A.neo[:IX]  B.pack:B.neo[:IX] ...
//   (IX: the fighter's own roster index: the same run with him, frame for frame against the slot's)
//   (SITE_DIR: core.js / core.wasm / neogeo.zip; LAYOUT: harness._layout of build_shell; X.neo: the build the pack was
//    taken from, whose ROM the swapped core must equal)
const fs = require('fs'), path = require('path'), zlib = require('zlib'), crypto = require('crypto');
const [site, shellPath, layoutPath, out, ...steps] = process.argv.slice(2);
const CL = require(path.join(__dirname, 'lab.js'));
const GeoCore = require(path.resolve(site, 'core.js'));
const layout = JSON.parse(fs.readFileSync(layoutPath));
fs.mkdirSync(out, { recursive: true });

function png(file, rgba32, w, h) {           // XRGB8888 (little-endian words) -> PNG
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) {
    raw[y * (w * 3 + 1)] = 0;
    for (let x = 0; x < w; x++) {
      const v = rgba32[y * w + x], o = y * (w * 3 + 1) + 1 + x * 3;
      raw[o] = (v >> 16) & 255; raw[o + 1] = (v >> 8) & 255; raw[o + 2] = v & 255;
    }
  }
  const crcT = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; crcT[n] = c >>> 0; }
  const crc = b => { let c = 0xFFFFFFFF; for (const x of b) c = crcT[(c ^ x) & 255] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
  const ih = Buffer.alloc(13); ih.writeUInt32BE(w, 0); ih.writeUInt32BE(h, 4); ih[8] = 8; ih[9] = 2;
  fs.writeFileSync(file, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ih), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]));
}

function neoRegions(buf) {                     // the .neo's P S M V1 V2 C (4096-byte header)
  const names = ['P', 'S', 'M', 'V1', 'V2', 'C'], o = {}; let off = 0x1000;
  names.forEach((n, i) => { const sz = buf.readUInt32LE(4 + 4 * i); o[n] = buf.subarray(off, off + sz); off += sz; });
  return o;
}

(async () => {
  const shell = fs.readFileSync(shellPath);
  const lab = await CL.Lab.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom: shell,
                                             moduleArgs: { locateFile: p => path.resolve(site, p) } }, layout);
  const core = lab.core, y = layout.syms;
  const rep = { steps: [] };
  // the sound queue (sound.c q[32], qh, qt): every byte the game queues, read each frame (voices: prefix $1B / $17 = the
  // overflow pair, codes $C0-$EF = the slot's, build_snd.py SLOT_*)
  let lastQt = lab.r8(y.qt) & 31, stream = [];
  const frame = (keys) => {
    lab.setPad(0, keys || ''); lab.run(1);
    const qt = lab.r8(y.qt) & 31;               // (during the BIOS: not the game's yet)
    while (lastQt !== qt) { stream.push(lab.r8(y.q + lastQt)); lastQt = (lastQt + 1) & 31; }
    if (stream.length > 100000) stream = [];
  };
  const p1ch = () => (lab.fget(0, 'ch') - y.bm_chars) / layout.sizeof_bchar;
  const romEquals = (neo) => {                  // the core's loaded ROM vs a .neo's (P: Geolith keeps it byte-swapped)
    const R = neoRegions(neo), names = ['P', 'S', 'M', 'V1', 'V2', 'C'], res = {};
    names.forEach((n, i) => {
      if (!R[n].length) return;
      const p = core._wc_rom(i), sz = core._wc_rom_size(i), mem = Buffer.from(core.HEAPU8.subarray(p, p + sz));
      let src = R[n];
      if (n === 'P') { src = Buffer.from(src); for (let k = 0; k < src.length; k += 2) { const t = src[k]; src[k] = src[k + 1]; src[k + 1] = t; } }
      res[n] = sz === src.length && crypto.createHash('sha256').update(mem).digest('hex') === crypto.createHash('sha256').update(src).digest('hex');
    });
    return res;
  };
  // after a reset the work RAM keeps the last practice's mailbox until the game's crt0 clears it: off first, then on
  const waitPractice = () => { let k = 0; for (; k < 4000 && lab.active(); k++) frame(''); for (; k < 8000 && !lab.active(); k++) frame(''); for (let i = 0; i < 30; i++) frame(''); return k; };
  const shot = name => { const p = core._wc_fb() >> 2, w = core._wc_fb_w(), h = core._wc_fb_h(); const f = path.join(out, name); png(f, core.HEAPU32.subarray(p, p + w * h), w, h); return f; };
  // every frame of a run: P1's state, animation, step, x, height, the dummy's life and state (a slot fighter and the
  // roster's own copy of him must give the same rows)
  const row = () => [lab.stateName(0), lab.fget(0, 'anim'), lab.fget(0, 'step'), Math.round(lab.fget(0, 'x')), Math.round(lab.fget(0, 'y')),
                     lab.fget(2, 'hp'), lab.stateName(2)];
  const play = (tag, shots = true) => {
    const r = { tag, p1: p1ch() }, trace = [];
    lab.request(2); for (let i = 0; i < 20; i++) frame('');
    stream = [];
    // walk in, then the chain: A pressed every 6 frames
    for (let i = 0; i < 16; i++) { frame('R'); trace.push(row()); }
    const states = [];
    for (let i = 0; i < 90; i++) { frame(i % 6 < 2 ? 'a' : ''); states.push(lab.stateName(0)); trace.push(row()); if (i === 14 && shots) r.shot_chain = shot(`${tag}_chain.png`); }
    r.chain_states = [...new Set(states)]; r.chain_hits = lab.combo().hits;
    for (let i = 0; i < 90; i++) frame('');
    lab.request(2); for (let i = 0; i < 20; i++) frame('');
    // a special: C (the D slot's special, fighter.c spec_tab)
    const sp = []; let shotAt = -1;
    for (let i = 0; i < 120; i++) {
      frame(i < 3 ? 'c' : '');
      const st = lab.stateName(0); sp.push(st); trace.push(row());
      if (st === 'SPECIAL' && shotAt < 0 && lab.fget(0, 'srow') > 8 && shots) { shotAt = i; r.shot_special = shot(`${tag}_special.png`); }
    }
    r.special_states = [...new Set(sp)]; r.spec_ix = lab.fget(0, 'spec_ix'); r.frames_special = sp.filter(s => s === 'SPECIAL').length;
    r.combo_after_special = lab.combo();
    const v = []; for (let i = 0; i + 1 < stream.length; i++) if ((stream[i] === 0x1B || stream[i] === 0x17) && stream[i + 1] >= 0xC0 && stream[i + 1] <= 0xEF) v.push('$' + stream[i].toString(16).toUpperCase() + ' $' + stream[i + 1].toString(16).toUpperCase());
    r.slot_voices_sent = v;
    for (let i = 0; i < 60; i++) frame('');
    if (shots) r.shot_idle = shot(`${tag}_idle.png`);
    r.trace = trace;
    return r;
  };
  // the same run with the roster's own copy of the fighter (bm_chars index f, his own tables outside the slot)
  const control = (f, slotRun) => {
    lab.request(1, f, 1); for (let i = 0; i < 5; i++) frame('');
    const c = play('control', false);
    const same = JSON.stringify(c.trace) === JSON.stringify(slotRun.trace);
    const first = same ? null : c.trace.findIndex((x, i) => JSON.stringify(x) !== JSON.stringify(slotRun.trace[i]));
    lab.request(1, 25, 1); for (let i = 0; i < 5; i++) frame('');   // (back to the slot fighter)
    return { roster_index: f, p1: c.p1, frames: c.trace.length, identical: same, first_difference: first,
             at: same ? null : [slotRun.trace[first], c.trace[first]], chain_hits: c.chain_hits, voices: c.slot_voices_sent.length };
  };
  core._wc_reset();
  rep.boot_frames = waitPractice();
  const s0 = play('0_shell');
  rep.steps.push(Object.assign({ rom: 'lab-shell.neo', rom_equals_shell: romEquals(shell) }, s0, { vs_roster: control(3, s0) }));
  let n = 1;
  for (const s of steps) {
    const [pk, neo, rosterIx] = s.split(':'), b = fs.readFileSync(pk), p = core._malloc(b.length);
    core.HEAPU8.set(b, p);
    const t0 = Date.now(), e = core._wc_swap_pack(p, b.length), ms = Date.now() - t0; core._free(p);
    const st = { pack: path.basename(pk), swap: e === 0 ? 'ok' : e, swap_ms: ms };
    if (e !== 0) { st.error = e; rep.steps.push(st); break; }
    lastQt = lab.r8(y.qt) & 31; st.boot_frames = waitPractice();
    st.rom_equals_build = romEquals(fs.readFileSync(neo)); st.build = path.basename(neo);
    const run = play(`${n++}_${path.basename(pk, '.pack')}`);
    rep.steps.push(Object.assign(st, run, rosterIx ? { vs_roster: control(+rosterIx, run) } : {}));
  }
  for (const st of rep.steps) delete st.trace;
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rep, null, 1));
  console.log(JSON.stringify(rep, null, 1));
})();
