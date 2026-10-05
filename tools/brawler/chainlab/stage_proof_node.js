// Stages tab proof in Node: the browser's core (core.wasm) plays "play from here" exactly as ramtrace.py's stage mode
// does on the desktop core (boot, the pack + lab req 4 in the same frame, then STAGE_SCRIPT), recording ramtrace.py's
// samples keyed by the game's tick counter, for ramtrace.py --diff.
//   node stage_proof_node.js SITE_DIR OUT.json STAGE WAVE FIGHTER FRAMES SCRIPT [PACK.bin]
const fs = require('fs'), path = require('path');
const [site, out, stage, wave, fighter, frames, script, packFile] = process.argv.slice(2);
const CL = require(path.join(__dirname, 'lab.js'));
const GeoCore = require(path.resolve(site, 'core.js'));
const layout = JSON.parse(fs.readFileSync(path.join(site, 'layout.json')));
(async () => {
  const lab = await CL.Lab.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom: fs.readFileSync(path.join(site, 'game.neo')),
                                             moduleArgs: { locateFile: p => path.resolve(site, p) } }, layout);
  lab.core._wc_reset(); lab.run(CL.BOOT_FRAMES);
  if (packFile) lab.installPack(new Uint8Array(fs.readFileSync(packFile)));
  lab.playStage(Number(fighter), Number(stage), Number(wave));
  const trace = [], ticks = [], parts = script.split(',').map(p => p.split(':'));
  lab.setPad(0, ''); lab.run(1); trace.push(lab.ramSnap()); ticks.push(lab.gameTicks());   // = stages.js play(): one frame, no key
  while (trace.length < Number(frames))
    for (const [n, k] of parts) for (let i = 0; i < Number(n) && trace.length < Number(frames); i++) {
      lab.setPad(0, k.replace('-', '')); lab.run(1); trace.push(lab.ramSnap()); ticks.push(lab.gameTicks());
    }
  fs.writeFileSync(out, JSON.stringify({ trace, ticks, pack_status: lab.packStatus() }));
  console.log('wasm core:', trace.length, 'frames, pack', lab.packStatus(), '->', out);
})();
