// Chain tool proof in Node (revamp phase 5): the page's code (lab.js) and the browser's core (core.wasm) on a built site.
//   node chaintool_proof_node.js SITE_DIR GAME_DIR OUT_DIR [SPEC.json FIGHTER] [--rom-only]
// (1) the page's encoder = the ROM's route tables byte for byte (every fighter); its chain assembly from each fighter's
//     own chain (specOf -> chainTree) = the ROM's tree (every fighter);
// (2) FIGHTER (default terry) vs the dummy, the autoplay (lab.js autoKeys) with every finisher: once on the ROM's tables
//     ("rom") and once with SPEC pushed into RAM (lab.installChain, fighter.c load 5) ("edit"); per frame a RAM trace
//     (P1 state / anim / step / node / freeze / rt_flags, the dummy's state / hp / freeze, route_tab[f], rt_tab) and the
//     game's lab events; checks: the override is what the game reads, each link's contact comes at its target startup
//     (the ROM run's offset), the hit-stops are the spec's, the damage the chain's; then load 2: the ROM's tables back;
// (3) OUT/edit_entry.json (the game.json entry "Save" sends), OUT/edit_override.bin (the pushed bytes), OUT/<run>.json
//     (traces), PNG frames of each link's contact in OUT/shots/. --rom-only: only the "rom" run (a rebuilt ROM with the
//     saved entry: its trace must equal the "edit" run's).
const fs = require('fs'), path = require('path'), zlib = require('zlib');
const args = process.argv.slice(2), romOnly = args.includes('--rom-only');
const [site, game, out, specFile, fname] = args.filter(a => a !== '--rom-only');
const CL = require(path.join(__dirname, 'lab.js'));
const GeoCore = require(path.resolve(site, 'core.js'));
const data = JSON.parse(fs.readFileSync(path.join(site, 'chainlab.json')));
const layout = JSON.parse(fs.readFileSync(path.join(site, 'layout.json')));
fs.mkdirSync(path.join(out, 'shots'), { recursive: true });
const RULES = data.chain;
let fail = 0;
const check = (ok, what) => { console.log((ok ? 'ok   ' : 'FAIL ') + what); if (!ok) fail++; };

// ---- (1) encoder + chain assembly vs the ROM -------------------------------------------------------------------------
const src = fs.readFileSync(path.join(game, 'build', 'bm_chars.c'), 'utf8');
const romTree = name => Uint8Array.from(src.match(new RegExp(`static const uint8_t ${name}_routes\\[\\] = \\{([^}]*)\\}`))[1].split(',').map(Number));
const eq = (a, b) => a.length === b.length && a.every((v, i) => v === b[i]);
let enc = 0, asm = 0; const asmBad = [];
for (const f of data.fighters) {
  const rom = romTree(f.name);
  if (eq(rom, CL.encodeTree(f.tree, data.ba, f.has, f.default.entries))) enc++; else console.log('  encoder differs:', f.name);
  let t = null; try { t = CL.chainTree(f, CL.specOf(f, RULES), RULES); } catch (e) { asmBad.push(f.name + ' (' + e.message + ')'); continue; }
  if (eq(rom, CL.encodeTree(t, data.ba, f.has, f.default.entries))) asm++; else asmBad.push(f.name);
}
check(enc === data.fighters.length, `encoder: ${enc}/${data.fighters.length} fighters' trees encode to the ROM's bytes`);
console.log(`info chain assembly (specOf -> chainTree, the links named): ${asm}/${data.fighters.length} = the ROM's tree` + (asmBad.length ? `; differ (a named link takes the base tree's first node of its move, the generator another): ${asmBad.join(', ')}` : ''));

// ---- (2) the runs ----------------------------------------------------------------------------------------------------------
function png(file, w, h, rgb) {                                // a plain RGB PNG
  const raw = Buffer.alloc((w * 3 + 1) * h);
  for (let y = 0; y < h; y++) { raw[y * (w * 3 + 1)] = 0; rgb.copy(raw, y * (w * 3 + 1) + 1, y * w * 3, (y + 1) * w * 3); }
  const crcT = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; crcT[n] = c >>> 0; }
  const crc = b => { let c = 0xFFFFFFFF; for (const x of b) c = crcT[(c ^ x) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  const chunk = (t, d) => { const l = Buffer.alloc(4); l.writeUInt32BE(d.length); const td = Buffer.concat([Buffer.from(t), d]); const c = Buffer.alloc(4); c.writeUInt32BE(crc(td)); return Buffer.concat([l, td, c]); };
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(w, 0); ihdr.writeUInt32BE(h, 4); ihdr[8] = 8; ihdr[9] = 2;
  fs.writeFileSync(file, Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]));
}
function shot(lab, file) {
  const c = lab.core, w = c._wc_fb_w(), h = c._wc_fb_h(), p = c._wc_fb(), H = c.HEAPU8, rgb = Buffer.alloc(w * h * 3);
  for (let i = 0; i < w * h; i++) { rgb[i * 3] = H[p + i * 4 + 2]; rgb[i * 3 + 1] = H[p + i * 4 + 1]; rgb[i * 3 + 2] = H[p + i * 4]; }
  png(file, w, h, rgb);
}

(async () => {
  const lab = await CL.Lab.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom: fs.readFileSync(path.join(site, 'game.neo')),
                                             moduleArgs: { locateFile: p => path.resolve(site, p) } }, layout);
  const fi = Math.max(0, data.fighters.findIndex(f => f.name === (fname || 'terry'))), f = data.fighters[fi];
  const di = data.fighters.findIndex(x => x.name === (f.name === 'ryo' ? 'terry' : 'ryo'));
  lab.boot(fi, di, null);
  const start = lab.saveState();
  const romSpec = CL.specOf(f, RULES, data.retime_rom);
  const spec = specFile && specFile !== '-' ? JSON.parse(fs.readFileSync(specFile)) : null;
  if (spec) spec.retime = spec.retime || {};

  function run(name, sp, push) {                               // every finisher from the same start
    lab.loadState(start);
    let ov = null;
    if (push) {
      const t = CL.chainTree(f, sp, RULES), blob = CL.encodeTree(t, data.ba, f.has, f.default.entries), rows = CL.retimeRows(data, f, sp);
      const bytes = CL.encodeOverride(blob, rows);
      lab.installChain(fi, bytes); lab.run(1);
      ov = { st: lab.overrideState(fi), bytes, blob, rows };
      fs.writeFileSync(path.join(out, name + '_override.bin'), bytes);
    }
    const t = CL.chainTree(f, sp, RULES), N = t.chain_links, idx = CL.nodeIndex(t);
    const res = { name, override: ov && { tree: ov.st.tree, rt: ov.st.rt, buf: ov.st.buf, treeInLab: ov.st.treeInLab, rtInLab: ov.st.rtInLab, bytes: ov.bytes.length, rows: ov.rows }, finishers: {} };
    for (const dir of ['neutral', 'forward', 'up', 'down', 'back']) {
      const after = lab.saveState();
      lab.request(2); lab.run(2);
      const fac = lab.fget(0, 'facing') > 0, stick = { neutral: '', forward: fac ? 'R' : 'L', up: 'U', down: 'D', back: fac ? 'L' : 'R' }[dir];
      const from = lab.nev(), trace = []; let finAt = -1, shots = 0;
      for (let i = 0; i < 420; i++) {
        const ev = lab.eventsSince(from).events, starts = ev.filter(e => e.kind === 'START').length;
        if (finAt < 0 && starts >= N) finAt = i;
        if (finAt >= 0 && i - finAt > 100) break;
        lab.setPad(0, CL.autoKeys(i, starts, N, stick, finAt >= 0)); lab.run(1);
        const hits = lab.eventsSince(from).events.filter(e => e.kind === 'HIT').length;
        trace.push([lab.labFrame(), lab.stateName(0), lab.fget(0, 'anim'), lab.fget(0, 'step'), lab.fget(0, 'node'), lab.fget(0, 'freeze'), lab.fget(0, 'rt_flags'),
                    lab.stateName(2), lab.fget(2, 'hp'), lab.fget(2, 'freeze'), lab.r32(layout.syms.route_tab + 4 * fi), lab.r32(layout.syms.rt_tab)]);
        if (hits > shots && dir === 'neutral') { shot(lab, path.join(out, 'shots', `${name}_hit${hits}.png`)); shots = hits; }
      }
      lab.setPad(0, '');
      const ev = lab.eventsSince(from).events, links = [];
      for (const e of ev) {
        if (e.kind === 'START') { const nd = [...idx].find(([, k]) => k === e.node); links.push({ node: e.node, move: nd ? (nd[0].throw ? 'throw' : nd[0].move) : null, hitstop: nd ? nd[0].hitstop : null, start: e.frame, hits: [], dmg: 0 }); }
        else if (e.kind === 'HIT' && links.length) { links[links.length - 1].hits.push(e.frame); links[links.length - 1].dmg += e.val; }
      }
      for (const l of links) {                                   // the hit-stop the game froze the dummy for at each hit
        l.freeze = l.hits.map(hf => { const rs = trace.filter(x => x[0] >= hf && x[0] <= hf + 1); return rs.length ? Math.max(...rs.map(x => x[9])) : null; });
      }
      res.finishers[dir] = { links, trace, events: ev.map(e => [e.frame, e.kind, e.node, e.how, e.val]) };
      lab.loadState(after);
    }
    if (push) { lab.installChain(fi, null); lab.run(1); res.after_unpush = lab.overrideState(fi); }
    fs.writeFileSync(path.join(out, name + '.json'), JSON.stringify(res));
    return { res, t };
  }

  const R = run('rom', romSpec, false);
  const romRT = R.res.finishers.neutral.trace[0];
  console.log(`rom run: route_tab[${f.name}] = $${romRT[10].toString(16)} (ROM), rt_tab = ${romRT[11]}`);
  const show = (r, t, sp) => {
    for (const [dir, x] of Object.entries(r.res.finishers))
      console.log(`  ${dir.padEnd(7)} ` + x.links.map(l => `${l.move}@${l.start}${l.hits.length ? ' contact +' + (l.hits[0] - l.start) + ' hs ' + l.freeze[0] + ' dmg ' + l.dmg : ' whiff'}`).join(' | '));
  };
  show(R);
  if (romOnly || !spec) { console.log(fail ? `${fail} FAILED` : 'ALL OK'); return; }

  const E = run('edit', spec, true);
  show(E);
  const o = E.res.override;
  check(o.treeInLab && o.tree === o.buf, `override read: route_tab[${f.name}] = $${o.tree.toString(16)} = lab.buf`);
  check(o.rows.length === 0 || o.rtInLab, `override read: rt_tab = $${o.rt.toString(16)} inside lab.buf (${o.rows.length} retime rows)`);
  const ua = E.res.after_unpush;
  check(!ua.treeInLab && ua.rt === 0, `load 2: the ROM's tree ($${ua.tree.toString(16)}) and rt_tab 0 back`);
  // every link's contact: (contact - start) - its target startup = the ROM run's (contact - start) - its source startup
  const off = l => { const T = (spec.retime[l.move] || CL.segsOf(f, l.move)); return l.hits.length ? l.hits[0] - l.start - T[0] : null; };
  const offR = l => { const S = CL.segsOf(f, l.move); return l.hits.length ? l.hits[0] - l.start - S[0] : null; };
  const c0 = new Set(Object.values(R.res.finishers).flatMap(x => x.links.filter(l => l.move !== 'throw' && l.hits.length).map(offR)));
  console.log(`info the rom run's contact offset (contact - start - source startup): ${[...c0].join(', ')}`);
  const c = [...c0][0];
  const tE = E.t, N = tE.chain_links;
  for (const [dir, x] of Object.entries(E.res.finishers)) {
    const L = x.links.slice(0, N);
    check(L.length === N && L.every(l => l.move === 'throw' || l.hits.length), `edit ${dir}: ${L.length}/${N} links, every one hit: ${L.map(l => l.move).join(' > ')}`);
    check(L.every(l => l.move === 'throw' || off(l) === c), `edit ${dir}: each contact at its target startup (+${c}): ` + L.filter(l => l.move !== 'throw').map(l => `${l.move} ${l.hits[0] - l.start} (target ${(spec.retime[l.move] || CL.segsOf(f, l.move))[0]}, source ${CL.segsOf(f, l.move)[0]})`).join(', '));
    check(L.every(l => l.move === 'throw' || l.freeze[0] === l.hitstop), `edit ${dir}: hit-stops = the spec's: ${L.filter(l => l.move !== 'throw').map(l => l.freeze[0] + '/' + l.hitstop).join(' ')}`);
    const rt = x.trace.filter(r => r[6]).length;
    if (Object.keys(spec.retime).length) check(rt > 0, `edit ${dir}: P1 played retimed (rt_flags set) on ${rt} frames`);
    if (dir === 'neutral') check(L.reduce((a, l) => a + l.dmg, 0) === RULES.totals[spec.archetype], `edit neutral: damage ${L.reduce((a, l) => a + l.dmg, 0)} = the ${spec.archetype} total ${RULES.totals[spec.archetype]}`);
  }
  fs.writeFileSync(path.join(out, 'edit_entry.json'), JSON.stringify({ fighter: f.name, entry: CL.saveEntry(f, spec, RULES), spec }, null, 1));
  fs.writeFileSync(path.join(out, 'edit_tree.bin'), Buffer.from(CL.encodeTree(E.t, data.ba, f.has, f.default.entries)));
  console.log(fail ? `${fail} FAILED` : 'ALL OK');
})();
