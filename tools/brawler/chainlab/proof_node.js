// Chain Lab proof in Node: (1) the page's encoder gives the ROM's own route tables byte for byte (build/bm_chars.c);
// (2) the browser's core (core.wasm) plays labdrive.py's scripted route: the per-frame trace and the lab events, written
// to OUT.json for compare.py against the desktop core's.
//   node proof_node.js SITE_DIR GAME_DIR OUT.json [TREE.json FIGHTER]
const fs = require('fs'), path = require('path');
const [site, game, out, treeFile, treeFighter] = process.argv.slice(2);
const CL = require(path.join(__dirname, 'lab.js'));
const GeoCore = require(path.resolve(site, 'core.js'));
const data = JSON.parse(fs.readFileSync(path.join(site, 'chainlab.json')));
const layout = JSON.parse(fs.readFileSync(path.join(site, 'layout.json')));
const SCRIPT = '14:R,3:a,9:-,3:a,9:-,3:La,12:-,3:Ra,90:-';            // = labdrive.py SCRIPT

const src = fs.readFileSync(path.join(game, 'build', 'bm_chars.c'), 'utf8');
let same = 0;
for (const f of data.fighters) {
  const m = src.match(new RegExp(`static const uint8_t ${f.name}_routes\\[\\] = \\{([^}]*)\\}`));
  const rom = Uint8Array.from(m[1].split(',').map(Number));
  const js = CL.encodeTree(f.tree, data.ba, f.has, f.default.entries);
  const ok = rom.length === js.length && rom.every((v, i) => v === js[i]);
  if (!ok) console.log('ENCODER MISMATCH', f.name, rom.length, js.length); else same++;
}
console.log(`encoder: ${same}/${data.fighters.length} fighters' trees encode to the ROM's bytes`);

(async () => {
  const t0 = Date.now();
  const lab = await CL.Lab.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom: fs.readFileSync(path.join(site, 'game.neo')),
                                             moduleArgs: { locateFile: p => path.resolve(site, p) } }, layout);
  let blob = null, fi = 0;
  if (treeFile) {
    fi = Number(treeFighter || 0); const f = data.fighters[fi];
    blob = CL.encodeTree(JSON.parse(fs.readFileSync(treeFile)), data.ba, f.has, f.default.entries);
  }
  const tb = Date.now();
  lab.boot(fi, 1, blob);
  const tBoot = (Date.now() - tb) / lab.frame;
  const snap = () => [0, 2].map(i => [lab.stateName(i), lab.fget(i, 'anim'), lab.fget(i, 'step'), Math.round(lab.fget(i, 'x') * 1000) / 1000, lab.fget(i, 'hp')]);
  const trace = [];
  for (const part of SCRIPT.split(',')) {
    const [n, k] = part.split(':'); lab.setPad(0, k.replace('-', ''));
    for (let i = 0; i < Number(n); i++) { lab.run(1); trace.push([lab.labFrame(), ...snap()]); }
  }
  lab.setPad(0, '');
  const ev = lab.eventsSince(0).events.map(e => [e.frame, e.kind, e.node, e.how, e.val]);
  const c = lab.combo();
  fs.writeFileSync(out, JSON.stringify({ script: SCRIPT, trace, events: ev, combo: [c.hits, c.dmg] }));
  ev.forEach(e => console.log(JSON.stringify(e)));
  console.log('combo hits / damage:', c.hits, c.dmg);
  // speed: frames per second the core runs flat out
  const n = 600, ts = Date.now(); lab.run(n);
  console.log(`speed: ${(n / ((Date.now() - ts) / 1000)).toFixed(0)} frames/s (${((Date.now() - ts) / n).toFixed(2)} ms a frame; boot ${tBoot.toFixed(2)} ms a frame); load ${(tb - t0)} ms`);
})();
