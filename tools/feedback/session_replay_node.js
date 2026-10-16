#!/usr/bin/env node
/* A recorded play session (docs/feedback.md "Session recording", Player 0.0.41) replayed in Node with the Lab's wasm
 * core and engine (chainlab/sessreplay.js on fbreplay.js): from the first chunk's state through every chunk; at each
 * chunk that follows the previous one without a gap, the replay's state is compared byte for byte with the state the
 * Player recorded there (the determinism check), and the SHA-256 of the last one is printed.
 *   node tools/feedback/session_replay_node.js SESSION_DIR [ROM.neo] [SITE_DIR (core.js, core.wasm, neogeo.zip)]
 * SESSION_DIR = the storage layout (meta.json, <seq>.nsin, <seq>.state.gz: /mnt/storagebox/brawler-sessions/<id> on the
 * VPS); ROM default /data/feedback/_roms/<meta rom_sha256>.neo. Exit 0 = every compared chunk byte-identical. */
const fs = require('fs'), path = require('path'), zlib = require('zlib'), crypto = require('crypto');
const dir = process.argv[2], site = process.argv[4] || '/data/tmp/chainlab/site';
const CL = path.join(__dirname, '..', 'brawler', 'chainlab');
const FeedbackReplay = require(path.join(CL, 'fbreplay.js'));
const SessionReplay = require(path.join(CL, 'sessreplay.js'));
const GeoCore = require(path.join(site, 'core.js'));
(async () => {
  const meta = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json')));
  const rom = fs.readFileSync(process.argv[3] || path.join('/data/feedback/_roms', meta.rom_sha256 + '.neo'));
  const files = { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom, systype: meta.system_type || 'mvs', hw: meta.hw || 'mvs',
                  memcard: meta.memcard || 'off', moduleArgs: { locateFile: f => path.join(site, f) } };
  const R = await FeedbackReplay.create(GeoCore, files, { snaps: {} });
  const S = new SessionReplay(R, async seq => new Uint8Array(zlib.gunzipSync(fs.readFileSync(path.join(dir, String(seq).padStart(6, '0') + '.state.gz')))));
  const seqs = fs.readdirSync(dir).map(f => /^(\d{6})\.nsin$/.exec(f)).filter(Boolean).map(m => +m[1]).sort((a, b) => a - b);
  const parts = [];
  for (const q of seqs) { const b = fs.readFileSync(path.join(dir, String(q).padStart(6, '0') + '.nsin')); const h = Buffer.alloc(4); h.writeUInt32LE(q); parts.push(h, b); }
  S.addInputs(new Uint8Array(Buffer.concat(parts)));
  S.addMeta(seqs.map(q => ({ seq: q, state: fs.existsSync(path.join(dir, String(q).padStart(6, '0') + '.state.gz')) ? 1 : 0 })));
  const t = Date.now();
  await S.seek(0);
  while (true) { if (S.step() === null && !(await S.ready())) break; if (S.R.frame >= S.R.P && S.i === S.chunks.length - 1) break; }
  const last = S.chunks[S.chunks.length - 1];
  const lastSha = last.data ? crypto.createHash('sha256').update(last.data).digest('hex') : '';
  const gaps = S.chunks.filter((c, k) => k > 0 && !S.joined(k)).map(c => c.seq);
  console.log(JSON.stringify({ session: meta.session, chunks: S.chunks.length, frames: S.total, seconds: +(S.total / R.fps).toFixed(1),
    compared: S.checked, mismatches: S.mismatches, gaps, last_chunk: last.seq, last_state_sha256: lastSha,
    replay_fps: Math.round(S.total / ((Date.now() - t) / 1000)) }));
  process.exit(S.checked > 0 && !S.mismatches.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
