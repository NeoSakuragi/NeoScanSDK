#!/usr/bin/env node
/* A recorded play session (docs/feedback.md "Session recording", Player 0.0.41, keyframes 0.0.43) replayed in Node with
 * the Lab's wasm core and engine (chainlab/sessreplay.js on fbreplay.js), the page's path: from the first keyframe
 * through every chunk; at each chunk boundary that follows the previous chunk without a gap, the SHA-256 of the
 * replay's state is compared with the one the Player recorded there (the drift check); a difference or a gap resyncs at
 * the next keyframe. Prints the counts and the SHA-256 of the replay's state at the end.
 *   node tools/feedback/session_replay_node.js SESSION_DIR [ROM.neo] [SITE_DIR (core.js, core.wasm, neogeo.zip)] [--drop SEQ,SEQ]
 * SESSION_DIR = the storage layout (meta.json, <seq>.nsin, <seq>.sha256, <seq>.state.gz for keyframes:
 * /mnt/storagebox/brawler-sessions/<id> on the VPS; sessions of 0.0.41 / 0.0.42 have no .sha256: their states give it);
 * ROM default /data/feedback/_roms/<meta rom_sha256>.neo. --drop: those chunks left out (a lost chunk, for the proof).
 * Exit 0 = every boundary checked identical and no gap. */
const fs = require('fs'), path = require('path'), zlib = require('zlib'), crypto = require('crypto');
const args = process.argv.slice(2), di = args.indexOf('--drop');
const drop = di >= 0 ? args.splice(di, 2)[1].split(',').map(Number) : [];
const dir = args[0], site = args[2] || '/data/tmp/chainlab/site';
const CL = path.join(__dirname, '..', 'brawler', 'chainlab');
const FeedbackReplay = require(path.join(CL, 'fbreplay.js'));
const SessionReplay = require(path.join(CL, 'sessreplay.js'));
const GeoCore = require(path.join(site, 'core.js'));
(async () => {
  const meta = JSON.parse(fs.readFileSync(path.join(dir, 'meta.json')));
  const rom = fs.readFileSync(args[1] || path.join('/data/feedback/_roms', meta.rom_sha256 + '.neo'));
  const files = { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom, systype: meta.system_type || 'mvs', hw: meta.hw || 'mvs',
                  memcard: meta.memcard || 'off', moduleArgs: { locateFile: f => path.join(site, f) } };
  const R = await FeedbackReplay.create(GeoCore, files, { snaps: {} });
  const S = new SessionReplay(R, async seq => new Uint8Array(zlib.gunzipSync(fs.readFileSync(path.join(dir, String(seq).padStart(6, '0') + '.state.gz')))));
  const seqs = fs.readdirSync(dir).map(f => /^(\d{6})\.nsin$/.exec(f)).filter(Boolean).map(m => +m[1]).filter(q => !drop.includes(q)).sort((a, b) => a - b);
  const f6 = (q, ext) => path.join(dir, String(q).padStart(6, '0') + ext);
  const parts = [];
  for (const q of seqs) { const b = fs.readFileSync(path.join(dir, String(q).padStart(6, '0') + '.nsin')); const h = Buffer.alloc(4); h.writeUInt32LE(q); parts.push(h, b); }
  S.addInputs(new Uint8Array(Buffer.concat(parts)));
  S.addMeta(seqs.map(q => {
    const key = fs.existsSync(f6(q, '.state.gz'));
    const sha = fs.existsSync(f6(q, '.sha256')) ? fs.readFileSync(f6(q, '.sha256'), 'utf8').trim()
      : key ? crypto.createHash('sha256').update(zlib.gunzipSync(fs.readFileSync(f6(q, '.state.gz')))).digest('hex') : '';
    return { seq: q, state: key ? 1 : 0, state_sha: sha };
  }));
  const t = Date.now();
  await S.seek(0);
  while (true) { if (S.step() === null && !(await S.ready())) break; if (S.R.frame >= S.R.P && S.i === S.chunks.length - 1) break; }
  const last = S.chunks[S.chunks.length - 1];
  console.log(JSON.stringify({ session: meta.session, chunks: S.chunks.length, keyframes: S.keys, frames: S.total, seconds: +(S.total / R.fps).toFixed(1),
    checked: S.checked, mismatches: S.mismatches, gaps: S.gaps, resyncs: S.resyncs, last_chunk: last.seq, end_frame: S.R.frame,
    end_state_sha256: crypto.createHash('sha256').update(S.R.save()).digest('hex'), replay_fps: Math.round(S.total / ((Date.now() - t) / 1000)) }));
  process.exit(S.checked > 0 && !S.mismatches.length && !S.gaps.length ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
