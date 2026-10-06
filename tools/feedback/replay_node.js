#!/usr/bin/env node
/* The Lab's in-browser feedback replay, run in Node on a pulled bundle: the same wasm core and engine
 * (tools/brawler/chainlab/fbreplay.js), from the window state to the press, every kept state compared, the press
 * state's SHA-256 compared. Also the browser's path: from the latest kept state before press - 600 frames.
 *   node tools/feedback/replay_node.js /data/feedback/<id> [SITE_DIR (core.js, core.wasm, neogeo.zip)] */
const fs = require('fs'), path = require('path');
const dir = process.argv[2], site = process.argv[3] || '/data/tmp/chainlab/site';
const FeedbackReplay = require(path.join(__dirname, '..', 'brawler', 'chainlab', 'fbreplay.js'));
const GeoCore = require(path.join(site, 'core.js'));
(async () => {
  const meta = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json')));
  const rom = fs.readFileSync(path.join('/data/feedback/_roms', meta.rom_sha256 + '.neo'));
  const snaps = {};
  for (const f of fs.readdirSync(dir)) { const m = /^snap_(\d+)\.state$/.exec(f); if (m) snaps[+m[1]] = new Uint8Array(fs.readFileSync(path.join(dir, f))); }
  const bundle = { inputs: new Uint8Array(fs.readFileSync(path.join(dir, 'inputs.bin'))), snaps, press: new Uint8Array(fs.readFileSync(path.join(dir, 'press.state'))) };
  const files = { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom, systype: meta.system_type || 'mvs', hw: meta.hw || 'mvs', memcard: meta.memcard || 'on',
                  moduleArgs: { locateFile: f => path.join(site, f) } };
  const r = await FeedbackReplay.create(GeoCore, files, bundle);
  let t = Date.now();
  r.seek(r.P, r.W);                                        // the whole window, every checkpoint
  const full = await r.check(), dt = (Date.now() - t) / 1000;
  const r2 = await FeedbackReplay.create(GeoCore, files, bundle);
  const start = Math.max(r2.W, r2.P - 600);
  t = Date.now(); r2.seek(start); while (r2.frame < r2.P) { r2.step(); r2.checkSnap(); }
  const tail = await r2.check();
  console.log(JSON.stringify({ id: meta.id, W: r.W, P: r.P, full_window: full.same, checkpoints_ok: !r.mismatch, mismatch: r.mismatch,
    fps: Math.round((r.P - r.W) / dt), from: r2.startFor(start), last10s: tail.same, sha: tail.sha, press_sha: tail.want }));
  process.exit(full.same && tail.same && !r.mismatch ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
