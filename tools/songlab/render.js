// Renders a song's write stream through the YM2610 WebAssembly module. Shared by song.html and the Node test.
// opts.mute: set of channel names whose key-ons are dropped (FM1-4, A1-6, B).
const PERIOD = 333;                       // samples per timer-A interrupt at 55555.6 Hz
const RATE = 8000000 / 144;
const FMKEY = { 1: 'FM1', 2: 'FM2', 5: 'FM3', 6: 'FM4' };
function keep(p, r, v, mute) {
  if (!mute || !mute.size) return [true, v];
  if (p === 0 && r === 0x28) return [!(v & 0xF0) || !mute.has(FMKEY[v & 7]), v];
  if (p === 1 && r === 0x00 && !(v & 0x80)) {
    let m = v;
    for (let c = 0; c < 6; c++) if (v >> c & 1 && mute.has('A' + (c + 1))) m &= ~(1 << c);
    return [m !== 0, m];
  }
  if (p === 0 && r === 0x10 && v & 0x80) return [!mute.has('B'), v];
  return [true, v];
}
function render(ym, song, which, opts) {
  opts = opts || {};
  const ex = ym.exports, mem = () => new Uint8Array(ex.memory.buffer);
  const vbase = ex.yw_vrom();
  if (!ym.loaded || ym.loaded !== song.cmd) {
    const m = mem(); m.fill(0, vbase, vbase + (16 << 20));
    for (const [addr, b64] of song.samples) {
      const bin = typeof atob === 'function' ? Uint8Array.from(atob(b64), c => c.charCodeAt(0)) : Buffer.from(b64, 'base64');
      m.set(bin, vbase + addr);
    }
    ym.loaded = song.cmd;
  }
  ex.yw_init();
  for (const [p, r, v] of song.pre) ex.yw_write(p, r, v);
  // times are in samples; from / to too
  const ws = song[which], from = opts.from || 0, to = Math.min(opts.to || song.length, song.length);
  const n = to - from, L = new Float32Array(n), R = new Float32Array(n);
  let i = 0, t = 0;
  while (t < to) {
    for (; i < ws.length && ws[i][0] <= t; i++) {
      const [, p, r, v] = ws[i];
      const [k, val] = keep(p, r, v, opts.mute);
      if (k) ex.yw_write(p, r, val);
    }
    const next = Math.min(to, i < ws.length ? ws[i][0] : to, t + 8192);
    const len = Math.max(1, next - t);
    ex.yw_run(len);
    const o = new Int16Array(ex.memory.buffer, ex.yw_out(), 2 * len);
    for (let j = 0; j < len; j++, t++) if (t >= from && t < to) { L[t - from] = o[2 * j] / 32768; R[t - from] = o[2 * j + 1] / 32768; }
  }
  return { L, R, rate: RATE };
}
if (typeof module !== 'undefined') module.exports = { render, PERIOD, RATE };
