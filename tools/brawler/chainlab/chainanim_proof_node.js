// THE CHAIN SECTION of the TRY blob (version 3; docs/character_lab.md "The chain"; note 20261010-210158-5d29: Bruno's
// Hanzo chain of dictionary animations went nowhere): a pack swapped into the shell, a TRY blob whose chain names each
// press (a move of his, an animation $NN, an S- piece; null = the game's), then A pressed every other frame on the
// dummy: the game's own event log says which press started when (LE_START node, the entry playing: lab.cur, P1's
// animation), and each press's piece must be the one named, in order.
//   node chainanim_proof_node.js SITE_DIR SHELL.neo PACK OUT.json PRESS1,PRESS2,... [HITSTOP1,...]
//   (PRESSES 'q:$15C,...' = the Try queue instead, the reference path; a press: '-' the game's, '$15C' an animation, 'move:atk_b_far' a move of his, 'S-004' needs the Workshop data: not here)
const fs = require('fs'), path = require('path');
const [site, shellPath, packPath, outPath, pressArg, hsArg] = process.argv.slice(2);
const CL = require(path.join(__dirname, 'lab.js'));
const GeoCore = require(path.resolve(site, 'core.js'));

(async () => {
  const shell = fs.readFileSync(shellPath), A = CL.readAnchor(shell), layout = A.doc.layout, SJ = A.doc;
  const lab = await CL.Lab.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom: shell,
                                             moduleArgs: { locateFile: p => path.resolve(site, p) } }, layout);
  const core = lab.core, y = layout.syms, SLOT = A.slot;
  const frame = keys => { lab.setPad(0, keys || ''); lab.run(1); };
  const pk = fs.readFileSync(packPath), M = CL.packManifest(pk), X = M.page || {};
  const p = core._malloc(pk.length); core.HEAPU8.set(pk, p); const e = core._wc_swap_pack(p, pk.length); core._free(p);
  if (e) throw new Error('swap refused ' + e);
  lab.boot(SLOT, SJ.fighters.indexOf('ryo'), null);      // (as tryit.js: P1 = the slot vs Ryo, the training)
  const ba = SJ.ba, hexOf = {};
  for (const [m, x] of Object.entries(X.moves || {})) hexOf[ba.indexOf(m)] = String(x).replace(/^\$/, '').toUpperCase();
  const queue = pressArg.startsWith('q:');                // ('q:$15C,...': the Try queue instead, the reference path)
  const presses = pressArg.replace(/^q:/, '').split(',').map(s => s === '-' ? null : s.startsWith('move:') ? CL.LE_MOVE | ba.indexOf(s.slice(5)) : parseInt(s.replace(/^\$/, ''), 16));
  const hs = hsArg ? hsArg.split(',').map(Number) : presses.map(() => 0);
  const blob = queue ? CL.encodeTry({ fighter: SLOT, queue: presses }) : CL.encodeTry({ fighter: SLOT, chain: { entries: presses, hitstop: hs } });
  lab.request(2); for (let i = 0; i < 20; i++) frame('');
  lab.installTry(blob, true); frame(''); frame('');
  const rep = { shell: path.basename(shellPath), pack: path.basename(packPath), blob: Buffer.from(blob).toString('hex'), status: lab.tryStatus(), starts: [], frames: [] };
  lab.request(2); for (let i = 0; i < 30; i++) frame('');
  for (let i = 0; i < +(process.env.WALK || 0); i++) frame('R');   // (WALK=n: n frames walking in first)
  rep.gap = Math.round(Math.abs(lab.fget(2, 'x') - lab.fget(0, 'x')));
  const from = lab.nev(), f0 = lab.labFrame();
  let prevKey = '';
  for (let i = 0; i < 260; i++) {
    frame(i % 2 ? '' : 'a');
    const st = lab.stateName(0), cur = lab.tryCur(), an = lab.fget(0, 'anim');
    const piece = st === 'SPECIAL' && cur !== 0xFFFF ? '$' + cur.toString(16).toUpperCase() : st === 'ATTACK' ? '$' + (hexOf[an] || '?') + ' ' + ba[an] : st;
    if (piece !== prevKey) rep.frames.push([lab.labFrame() - f0, piece]);
    prevKey = piece;
  }
  for (const ev of lab.eventsSince(from).events) if (ev.kind === 'START' || ev.kind === 'HIT' || ev.kind === 'CHAINWIN') rep.starts.push(Object.assign({}, ev, { frame: ev.frame - f0 }));
  rep.combo = lab.combo();
  fs.writeFileSync(outPath, JSON.stringify(rep, null, 1));
  console.log(JSON.stringify({ gap: rep.gap, status: rep.status, combo: rep.combo, frames: rep.frames.slice(0, 30) }));
})().catch(e => { console.error(e); process.exit(1); });
