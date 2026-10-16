/* LIVE WALL, one tile (wall.js starts one Web Worker per tile): its own wasm Geolith core (core.js, the module compiled
 * once by the page and shared), the session replayed by sessreplay.js on fbreplay.js exactly as the single view does
 * (sessions.js): join at the latest keyframe, fast-forward silently to the newest chunk, then follow the chunks as
 * they arrive (its own poll of feedback-api/session/<id>?after=); the drift check at every chunk boundary (state
 * SHA-256 vs the recorded one). The picture goes straight to the tile's canvas (OffscreenCanvas transferred here); the
 * sound to the page only while this tile is the one heard. Falling more than CATCH_S behind the newest chunk (a stall,
 * a hidden tab): silent catch-up at up to x4 until LAG_S. Messages:
 *   in  {type: 'init', id, row, api, module (WebAssembly.Module), bios, rom (ArrayBuffer), canvas, syms, poll}
 *   in  {type: 'sound', on} | {type: 'pause'} | {type: 'resume'} (= join live again) | {type: 'stop'}
 *   out {type: 'status', ...every 500 ms: pos, total, lag, live, ended, checked, mismatches, gaps, resyncs, drift,
 *        waiting, info (sessinfo.js), cpu (busy fraction of one core), fps, heap (bytes)} | {type: 'audio', pcm, rate}
 *   out {type: 'error', error} */
importScripts('core.js', 'fbreplay.js', 'sessreplay.js', 'sessinfo.js');
const FPS = 59.185606, CATCH_S = 8, LAG_S = 3;
let S = null, R = null, ctx = null, img = null, cfg = null, sound = false, paused = false, stopped = false;
let pollT = 0, timer = 0, acc = 0, last = 0, busy = 0, busyFrom = 0, frames = 0, live = true, ended = false, waiting = false, catching = false, info = null;
const get = async (u, what) => { const r = await fetch(u, { credentials: 'same-origin', cache: 'no-store' }); if (!r.ok) throw new Error((what || u) + ': HTTP ' + r.status); return new Uint8Array(await r.arrayBuffer()); };
const json = async u => { const r = await fetch(u, { credentials: 'same-origin', cache: 'no-store' }); if (!r.ok) throw new Error(u + ': HTTP ' + r.status); return r.json(); };

async function more() {                                   // the chunks that arrived since
  if (!S || stopped) return;
  const top = S.chunks.length ? S.chunks[S.chunks.length - 1].seq : -1;
  try {
    const j = await json(cfg.api + 'session/' + cfg.id + '?after=' + top);
    if (j.chunks.length) { S.addMeta(j.chunks); S.addInputs(await get(cfg.api + 'session/' + cfg.id + '/inputs?from=' + j.chunks[0].seq, 'inputs')); }
    live = j.session.live; ended = !live;
  } catch (e) { /* the next poll */ }
}
async function join() {                                   // the latest keyframe, silently on to the newest chunk
  await more();
  if (!S.chunks.length) return;
  await S.seek(S.cum[S.chunks.length - 1]);
  for (let n = 0; n < 3; n++) {
    await more(); const g = S.cum[S.chunks.length - 1]; if (S.pos >= g) break;
    while (S.pos < g) { if (S.step() === null && !(await S.ready())) break; }
  }
}
function draw() {
  const p = R.rgba(img && img.data);
  if (ctx.canvas.width !== p.w) { ctx.canvas.width = p.w; ctx.canvas.height = p.h; }
  if (!img || img.width !== p.w) img = new ImageData(p.data, p.w, p.h);
  ctx.putImageData(img, 0, 0);
}
function tick() {
  if (stopped) return;
  timer = setTimeout(tick, 8);
  if (paused || !S) { last = performance.now(); return; }
  const t0 = performance.now();
  const lag = (S.total - S.pos) / FPS;
  if (lag > CATCH_S) catching = true; else if (lag < LAG_S) catching = false;
  const speed = catching ? 4 : 1;
  acc += (t0 - last) / 1000 * FPS * speed; last = t0;
  let n = 0; waiting = false;
  while (acc >= 1 && n < 4 * speed) {
    const a = S.step();
    if (a === null) { acc = 0; waiting = true; S.ready(); break; }
    if (sound && !catching && a.length) postMessage({ type: 'audio', pcm: a, rate: R.rate }, [a.buffer]);
    acc -= 1; n++; frames++;
  }
  if (acc > 4 * speed) acc = 0;
  if (n) { draw(); info = SessInfo.fromCore(R.core, cfg.syms); }
  busy += performance.now() - t0;
}
function status() {
  if (!S) return;
  const now = performance.now(), span = now - busyFrom;
  postMessage({ type: 'status', pos: S.pos, total: S.total, lag: (S.total - S.pos) / FPS, live, ended, waiting, catching,
    checked: S.checked, mismatches: S.mismatches.slice(0, 8), gaps: S.gaps.slice(0, 8), resyncs: S.resyncs.slice(0, 8), drift: S.drift,
    info, cpu: span > 0 ? busy / span : 0, fps: span > 0 ? frames * 1000 / span : 0, heap: R.core.HEAPU8.length, paused });
  busy = 0; frames = 0; busyFrom = now;
}
onmessage = async ev => {
  const m = ev.data;
  if (m.type === 'init') {
    cfg = m;
    try {
      const moduleArgs = { instantiateWasm: (imports, done) => { WebAssembly.instantiate(m.module, imports).then(i => done(i, m.module)); return {}; } };
      const [systype, hw] = (m.row.system || 'mvs-mvs').split('-');
      R = await FeedbackReplay.create(self.GeoCore, { bios: m.bios instanceof Uint8Array ? m.bios : new Uint8Array(m.bios), rom: m.rom instanceof Uint8Array ? m.rom : new Uint8Array(m.rom), systype, hw, memcard: m.row.memcard || 'off', moduleArgs }, { snaps: {} });
      try { R.core.FS.unlink('/rom/game.neo'); } catch (e) { /* the core keeps its own copy */ }
      cfg.rom = null; cfg.bios = null;
      S = new SessionReplay(R, seq => get(m.api + 'session/' + m.id + '/state/' + seq, 'state ' + seq));
      ctx = m.canvas.getContext('2d');
      await join();
      if (!S.chunks.length) throw new Error('no chunk yet');
      last = busyFrom = performance.now();
      pollT = setInterval(more, m.poll || 1000);
      setInterval(status, 500);
      tick();
    } catch (e) { postMessage({ type: 'error', error: e.message }); }
    return;
  }
  if (m.type === 'sound') sound = m.on;
  if (m.type === 'pause') paused = true;
  if (m.type === 'resume' && S) { paused = true; try { await join(); } catch (e) { /* plays on from where it is */ } paused = false; last = performance.now(); }
  if (m.type === 'stop') { stopped = true; clearTimeout(timer); clearInterval(pollT); close(); }
};
