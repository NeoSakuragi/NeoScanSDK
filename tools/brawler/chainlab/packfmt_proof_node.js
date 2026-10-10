// THE PACK FORMAT proven on the Lab's wasm core (web_core.c wc_swap_pack = pack_swap.c, the Player's path too; docs/
// character_lab.md "The pack format"): a shell rebuilt after an engine change plays the packs built for the OLD shell
// exactly as packs rebuilt for it: per fighter the old pack swapped in, his chain (A every 6 frames) and his C special
// played, every frame recorded (P1's state, animation, step, x, height, the dummy's life and state); the new pack the
// same; the two runs must be frame for frame identical, and the same run with the roster's own copy of him (outside the
// slot) too. Then the refusals, by the C path's own words: a pack from before the format, and a pack whose needs the
// shell lacks (the shell's anchor in the core's ROM with one feature taken out: an older shell without it).
//   node packfmt_proof_node.js SITE_DIR SHELL.neo OUT_DIR  f:OLD.pack:NEW.pack[:IX] ...  [--old X.pack] [--lacks f:feature]
//   (SITE_DIR: core.js / core.wasm / neogeo.zip; the layout comes from the shell's own anchor; IX: his roster index)
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const args = process.argv.slice(2);
const [site, shellPath, out] = args;
const steps = [], olds = [], lacks = [];
for (let i = 3; i < args.length; i++) {
  if (args[i] === '--old') olds.push(args[++i]); else if (args[i] === '--lacks') lacks.push(args[++i]); else steps.push(args[i]);
}
const CL = require(path.join(__dirname, 'lab.js'));
const GeoCore = require(path.resolve(site, 'core.js'));
fs.mkdirSync(out, { recursive: true });

(async () => {
  const shell = fs.readFileSync(shellPath), A = CL.readAnchor(shell), layout = A.doc.layout;
  const lab = await CL.Lab.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom: shell,
                                             moduleArgs: { locateFile: p => path.resolve(site, p) } }, layout);
  const core = lab.core, y = layout.syms, SLOT = A.slot;
  const rep = { shell: path.basename(shellPath), shell_sha256: crypto.createHash('sha256').update(shell).digest('hex'),
                format: A.format, features: A.features.length, slot: SLOT, game_version: A.doc.game_version, fighters: [], refusals: [] };
  let lastQt = lab.r8(y.qt) & 31, stream = [];
  const frame = keys => {
    lab.setPad(0, keys || ''); lab.run(1);
    const qt = lab.r8(y.qt) & 31;
    while (lastQt !== qt) { stream.push(lab.r8(y.q + lastQt)); lastQt = (lastQt + 1) & 31; }
    if (stream.length > 100000) stream = [];
  };
  const p1ch = () => (lab.fget(0, 'ch') - y.bm_chars) / layout.sizeof_bchar;
  const waitPractice = () => { let k = 0; for (; k < 4000 && lab.active(); k++) frame(''); for (; k < 8000 && !lab.active(); k++) frame(''); for (let i = 0; i < 30; i++) frame(''); return k; };
  const romSha = () => ['P', 'S', 'M', 'V1', 'C'].map((n, i) => { const k = [0, 1, 2, 3, 5][i], p = core._wc_rom(k), sz = core._wc_rom_size(k);
    return n + ':' + crypto.createHash('sha256').update(Buffer.from(core.HEAPU8.subarray(p, p + sz))).digest('hex').slice(0, 12); }).join(' ');
  const row = () => [lab.stateName(0), lab.fget(0, 'anim'), lab.fget(0, 'step'), Math.round(lab.fget(0, 'x')), Math.round(lab.fget(0, 'y')),
                     lab.fget(2, 'hp'), lab.stateName(2)];
  const play = () => {
    const r = { p1: p1ch() }, trace = [];
    lab.request(2); for (let i = 0; i < 20; i++) frame('');
    stream = [];
    for (let i = 0; i < 16; i++) { frame('R'); trace.push(row()); }
    const states = [];
    for (let i = 0; i < 90; i++) { frame(i % 6 < 2 ? 'a' : ''); states.push(lab.stateName(0)); trace.push(row()); }
    r.chain_states = [...new Set(states)]; r.chain_hits = lab.combo().hits;
    for (let i = 0; i < 90; i++) frame('');
    lab.request(2); for (let i = 0; i < 20; i++) frame('');
    const sp = [];
    for (let i = 0; i < 120; i++) { frame(i < 3 ? 'c' : ''); sp.push(lab.stateName(0)); trace.push(row()); }
    r.special_frames = sp.filter(s => s === 'SPECIAL').length; r.spec_ix = lab.fget(0, 'spec_ix');
    const v = []; for (let i = 0; i + 1 < stream.length; i++) if ((stream[i] === 0x1B || stream[i] === 0x17) && stream[i + 1] >= 0xC0 && stream[i + 1] <= 0xEF) v.push(stream[i + 1]);
    r.slot_voices = v.length;
    for (let i = 0; i < 60; i++) frame('');
    r.trace = trace;
    return r;
  };
  const swap = file => {
    const b = fs.readFileSync(file), p = core._malloc(b.length);
    core.HEAPU8.set(b, p); const e = core._wc_swap_pack(p, b.length); core._free(p);
    let m = ''; if (e) { let q = core._wc_pack_error(e); for (let c; (c = core.HEAPU8[q++]);) m += String.fromCharCode(c); }
    if (!e) { lastQt = lab.r8(y.qt) & 31; waitPractice(); }
    return { code: e, message: m };
  };
  const diff = (a, b) => { const i = a.findIndex((x, k) => JSON.stringify(x) !== JSON.stringify(b[k])); return i < 0 && a.length === b.length ? null : { frame: i, a: a[i], b: b[i] }; };
  core._wc_reset(); rep.boot_frames = waitPractice();
  for (const s of steps) {
    const [f, oldPk, newPk, ix] = s.split(':'), F = { fighter: f, old: path.basename(oldPk), new: path.basename(newPk) };
    const so = swap(oldPk); F.old_swap = so; if (so.code) { rep.fighters.push(F); continue; }
    F.old_rom = romSha(); const ro = play(); F.old_p1 = ro.p1;
    const sn = swap(newPk); F.new_swap = sn; if (sn.code) { rep.fighters.push(F); continue; }
    F.new_rom = romSha(); const rn = play(); F.new_p1 = rn.p1;
    F.rom_identical = F.old_rom === F.new_rom;
    F.frames = ro.trace.length; F.identical = !diff(ro.trace, rn.trace); F.first_difference = diff(ro.trace, rn.trace);
    F.chain_hits = [ro.chain_hits, rn.chain_hits]; F.special_frames = [ro.special_frames, rn.special_frames];
    F.spec_ix = [ro.spec_ix, rn.spec_ix]; F.slot_voices = [ro.slot_voices, rn.slot_voices]; F.chain_states = ro.chain_states;
    if (ix) {                                          // the roster's own copy of him, in the same shell (his tables outside the slot)
      lab.request(1, +ix, 1); for (let i = 0; i < 5; i++) frame('');
      const rc = play(); F.vs_roster = { index: +ix, p1: rc.p1, identical: !diff(ro.trace, rc.trace), first_difference: diff(ro.trace, rc.trace) };
      lab.request(1, SLOT, 1); for (let i = 0; i < 5; i++) frame('');
    }
    rep.fighters.push(F);
    console.log(`${f}: old ${F.old} -> P1 ${F.old_p1}, new ${F.new} -> P1 ${F.new_p1}: ${F.frames} frames ${F.identical ? 'IDENTICAL' : 'DIFFER at ' + JSON.stringify(F.first_difference)}` +
                `, ROM after the swaps ${F.rom_identical ? 'identical' : 'differs'}, chain hits ${F.chain_hits}, special frames ${F.special_frames}` +
                (F.vs_roster ? `, vs the roster's own ${f}: ${F.vs_roster.identical ? 'identical' : 'DIFFER ' + JSON.stringify(F.vs_roster.first_difference)}` : ''));
  }
  for (const o of olds) {                              // a pack of the old (absolute-address) kind
    const r = swap(o); rep.refusals.push({ pack: path.basename(o), case: 'from before the pack format', ...r });
    console.log(`refused ${path.basename(o)}: ${r.code} ${r.message}`);
  }
  for (const l of lacks) {                             // the shell without one feature: its anchor's token blanked in the core's ROM
    const [pk, feat] = l.split(':'), p = core._wc_rom(0), P = core.HEAPU8, at = i => p + 0xDC000 + i;   // (the core keeps P in the 68000's order)
    const flen = P[at(10)] << 8 | P[at(11)], nreg = P[at(6)] << 8 | P[at(7)], f0 = 20 + 12 * nreg;
    let s = ''; for (let i = 0; i < flen - 1; i++) s += String.fromCharCode(P[at(f0 + i)]);
    const toks = s.split(' '), k = toks.indexOf(feat); if (k < 0) throw new Error('the shell has no feature ' + feat);
    let o = toks.slice(0, k).join(' ').length + (k ? 1 : 0); const keep = [];
    for (let i = 0; i < feat.length; i++) { keep.push(P[at(f0 + o + i)]); P[at(f0 + o + i)] = 'x'.charCodeAt(0); }
    const r = swap(pk);
    for (let i = 0; i < feat.length; i++) P[at(f0 + o + i)] = keep[i];
    rep.refusals.push({ pack: path.basename(pk), case: `a shell without "${feat}"`, ...r });
    console.log(`refused ${path.basename(pk)} by a shell without ${feat}: ${r.code} ${r.message}`);
  }
  for (const F of rep.fighters) for (const k of ['first_difference']) if (F[k] === null) delete F[k];
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rep, null, 1));
  const ok = rep.fighters.every(F => F.identical && (!F.vs_roster || F.vs_roster.identical) && F.old_p1 === SLOT) &&
             rep.refusals.every(r => r.code < 0);
  console.log(ok ? 'ALL OK' : 'FAILED'); process.exit(ok ? 0 : 1);
})();
