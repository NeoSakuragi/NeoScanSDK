#!/usr/bin/env node
/* Live wall proof (wall.js): a recorded session's pads played again in the wasm core into a NEW session in the storage
 * layout (meta.json, <seq>.nsin, <seq>.sha256, <seq>.state.gz every keyframe), with the chunk size and keyframe interval
 * chosen (the Player's 300-frame chunks, or 120-frame ones), on the same build or another one (from power on: the
 * pads drive whatever that build does with them). wall_feed.py posts such a session to a LOCAL feedback service in real
 * time, as a fake live one. Never post them to the live server.
 *   node wall_synth_node.js SRC_SESSION_DIR ROM.neo OUT_DIR [--chunk 120] [--key-s 30] [--minutes 10] [--from-key]
 *   SITE env: core.js / core.wasm / neogeo.zip (default /data/tmp/livewall/site)
 *   --from-key: start from the source's first keyframe (the same build only); default: power on */
const fs = require('fs'), path = require('path'), zlib = require('zlib'), crypto = require('crypto');
const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); if (i < 0) return d; const v = a[i + 1]; a.splice(i, 2); return v; };
const flag = k => { const i = a.indexOf(k); if (i < 0) return false; a.splice(i, 1); return true; };
const CH = +opt('--chunk', 120), KEY_S = +opt('--key-s', 30), MIN = +opt('--minutes', 10), fromKey = flag('--from-key');
const [src, romPath, out] = a, site = process.env.SITE || '/data/tmp/livewall/site';
const FR = require(path.join(__dirname, 'fbreplay.js'));
const GeoCore = require(path.join(site, 'core.js'));
(async () => {
  const meta0 = JSON.parse(fs.readFileSync(path.join(src, 'meta.json')));
  const rom = fs.readFileSync(romPath), sha = crypto.createHash('sha256').update(rom).digest('hex');
  const R = await FR.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom, systype: 'mvs', hw: 'mvs', memcard: meta0.memcard || 'off',
    moduleArgs: { locateFile: f => path.join(site, f) } }, { snaps: {} });
  const seqs = fs.readdirSync(src).map(f => /^(\d{6})\.nsin$/.exec(f)).filter(Boolean).map(m => +m[1]).sort((x, y) => x - y);
  if (fromKey) R.load(new Uint8Array(zlib.gunzipSync(fs.readFileSync(path.join(src, String(seqs[0]).padStart(6, '0') + '.state.gz')))));
  const pads = [];                                       // the source's pads, frame after frame (P1, P2)
  for (const q of seqs) { const x = FR.parseInputs(new Uint8Array(fs.readFileSync(path.join(src, String(q).padStart(6, '0') + '.nsin')))); for (const p of x.pads) pads.push(p); }
  const total = Math.min(pads.length / 2, Math.round(MIN * 60 * R.fps)), keyEvery = Math.max(1, Math.round(KEY_S * R.fps / CH));
  fs.mkdirSync(out, { recursive: true });
  const ver = (/brawler-([0-9.]+)\.neo$/.exec(romPath) || [])[1] || process.env.ROM_VERSION || meta0.rom_version;
  fs.writeFileSync(path.join(out, 'meta.json'), JSON.stringify(Object.assign({}, meta0, { session: path.basename(out), rom_sha256: sha, rom_version: ver, frames: CH,
    synth: { from: meta0.session, chunk: CH, key_s: KEY_S, from_key: fromKey } }), null, 1));
  let f = 0, seq = 0;
  while (f < total) {
    const n = Math.min(CH, total - f), st = R.save(), f6 = e => path.join(out, String(seq).padStart(6, '0') + e);
    fs.writeFileSync(f6('.sha256'), crypto.createHash('sha256').update(st).digest('hex'));
    if (seq % keyEvery === 0) fs.writeFileSync(f6('.state.gz'), zlib.gzipSync(st, { level: 6 }));
    const b = Buffer.alloc(24 + 4 * n); b.write('NSIN', 0); b.writeUInt32LE(1, 4); b.writeBigUInt64LE(BigInt(f), 8); b.writeBigUInt64LE(BigInt(f + n), 16);
    R.W = f; R.P = f + n; R.pads = new Uint16Array(2 * n); R.frame = f;
    for (let i = 0; i < n; i++) { R.pads[2 * i] = pads[2 * (f + i)]; R.pads[2 * i + 1] = pads[2 * (f + i) + 1]; b.writeUInt16LE(R.pads[2 * i], 24 + 4 * i); b.writeUInt16LE(R.pads[2 * i + 1], 26 + 4 * i); }
    while (R.frame < R.P) R.step();
    fs.writeFileSync(f6('.nsin'), b);
    f += n; seq++;
  }
  console.log(JSON.stringify({ out, rom_sha256: sha, chunks: seq, chunk: CH, keyframe_every: keyEvery, frames: total }));
})().catch(e => { console.error(e); process.exit(1); });
