/* Session replay engine (docs/feedback.md "Session recording", Player 0.0.41, keyframes 0.0.43): a tester's play
 * session, sent by the Player in ~2 s chunks (~5 s before app 0.0.44; any length replays) (Session.kt: the pads of each chunk's frames + the SHA-256 of the state at
 * its start; a KEYFRAME chunk, every ~30 s, also that state), replayed in the wasm Geolith core through fbreplay.js's
 * FeedbackReplay (one core per build). Used by the Lab's Sessions tab (sessions.js) and by
 * tools/feedback/session_replay_node.js (the determinism proof in Node). Sessions of 0.0.41 / 0.0.42 = every chunk a
 * keyframe: the same path.
 *   const S = new SessionReplay(R, getState)       R = a FeedbackReplay on the session's build; getState(seq) -> Promise<Uint8Array>
 *   S.addMeta(chunks)                              the server's chunk rows (seq, start_frame, frames, state = keyframe, state_sha)
 *   S.addInputs(bytes)                             feedback-api/session/<id>/inputs: per chunk u32 seq + NSIN v1
 *   await S.seek(g)                                to the session's frame g (0 .. S.total): the nearest keyframe at or
 *                                                  before it (the next one when a gap lies between), then silent frames
 *   S.step()                                       one frame -> its audio (Int16Array), or null (the end of what arrived,
 *                                                  or a keyframe's state is still loading: await S.ready() and step again)
 * THE DRIFT CHECK: at every chunk boundary that follows the chunk played without a gap, the SHA-256 of the replay's
 * state is compared with the one the Player recorded there (S.checked; S.mismatches = the chunks where the replay first
 * differed). A difference = drifting: the replay plays on (shown) and resyncs at the next keyframe (its recorded state
 * loaded; S.resyncs). A GAP (a chunk missing: dropped on the device or never arrived; a test state loaded) = the chunks
 * after it up to the next keyframe cannot be replayed: skipped, the replay goes on from that keyframe (S.gaps = the
 * chunks where a gap was found). */
(function (root) {
  'use strict';
  const FR = root.FeedbackReplay || (typeof require !== 'undefined' ? require('./fbreplay.js') : null);

  // SHA-256, synchronous (step() runs inside the page's frame loop; crypto.subtle is async and https-only)
  const nodeCrypto = (() => { try { return typeof process !== 'undefined' && process.versions && process.versions.node ? require('crypto') : null; } catch (e) { return null; } })();
  const K = new Uint32Array([0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
    0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa,
    0x5cb0a9dc, 0x76f988da, 0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138,
    0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624,
    0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f,
    0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2]);
  function sha256(b) {
    if (nodeCrypto) return nodeCrypto.createHash('sha256').update(b).digest('hex');
    const n = b.length, tot = ((n + 9 + 63) >> 6) << 6, m = new Uint8Array(tot);
    m.set(b); m[n] = 0x80;
    const dv = new DataView(m.buffer); dv.setUint32(tot - 4, n * 8 >>> 0); dv.setUint32(tot - 8, Math.floor(n / 0x20000000));
    const H = new Uint32Array([0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19]), w = new Uint32Array(64);
    for (let o = 0; o < tot; o += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(o + 4 * i);
      for (let i = 16; i < 64; i++) {
        const x = w[i - 15], y = w[i - 2];
        w[i] = (((x >>> 7 | x << 25) ^ (x >>> 18 | x << 14) ^ x >>> 3) + w[i - 7] + ((y >>> 17 | y << 15) ^ (y >>> 19 | y << 13) ^ y >>> 10) + w[i - 16]) | 0;
      }
      let a = H[0], b1 = H[1], c = H[2], d = H[3], e = H[4], f = H[5], g = H[6], h = H[7];
      for (let i = 0; i < 64; i++) {
        const t1 = (h + ((e >>> 6 | e << 26) ^ (e >>> 11 | e << 21) ^ (e >>> 25 | e << 7)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) | 0;
        const t2 = (((a >>> 2 | a << 30) ^ (a >>> 13 | a << 19) ^ (a >>> 22 | a << 10)) + ((a & b1) ^ (a & c) ^ (b1 & c))) | 0;
        h = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b1; b1 = a; a = (t1 + t2) | 0;
      }
      H[0] += a; H[1] += b1; H[2] += c; H[3] += d; H[4] += e; H[5] += f; H[6] += g; H[7] += h;
    }
    return [...H].map(x => x.toString(16).padStart(8, '0')).join('');
  }

  class SessionReplay {
    constructor(R, getState) {
      this.R = R; this.getState = getState;
      this.chunks = [];                     // by seq: { seq, W, P, pads, state (bool: a keyframe), sha, data (Uint8Array once fetched) }
      this.bySeq = new Map();
      this.cum = [0];                       // cum[i] = the session frame where chunk i starts
      this.i = -1;                          // the chunk being played
      this.checked = 0; this.mismatches = []; this.resyncs = []; this.gaps = [];
      this.drift = false;                   // the replay differs from the recording (since S.mismatches' last): resync at the next keyframe
      this.vk = -1;                         // the boundary (chunk index) already checked
      this.loading = new Map();
    }
    get total() { return this.cum[this.cum.length - 1]; }
    get keys() { return this.chunks.filter(c => c.state).length; }
    /** the session frame now */
    get pos() { return this.i < 0 ? 0 : this.cum[this.i] + (this.R.frame - this.chunks[this.i].W); }
    chunk(seq) {
      let c = this.bySeq.get(seq);
      if (!c) { c = { seq, W: 0, P: 0, pads: null, state: false, sha: '', data: null }; this.bySeq.set(seq, c); }
      return c;
    }
    addMeta(rows) { for (const r of rows) Object.assign(this.chunk(r.seq), { state: !!r.state, sha: r.state_sha || '', at: r.at, paused: !!r.paused }); this.index(); }
    addInputs(b) {
      const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
      for (let o = 0; o + 28 <= b.length;) {
        const seq = dv.getUint32(o, true), W = Number(dv.getBigUint64(o + 12, true)), P = Number(dv.getBigUint64(o + 20, true));
        const n = 24 + 4 * (P - W);
        const x = FR.parseInputs(b.subarray(o + 4, o + 4 + n));
        Object.assign(this.chunk(seq), { W: x.W, P: x.P, pads: x.pads });
        o += 4 + n;
      }
      this.index();
    }
    /** the chunks with their pads, in seq order, and where each starts in the session */
    index() {
      const cur = this.i >= 0 ? this.chunks[this.i] : null;
      this.chunks = [...this.bySeq.values()].filter(c => c.pads).sort((a, b) => a.seq - b.seq);
      this.cum = [0]; for (const c of this.chunks) this.cum.push(this.cum[this.cum.length - 1] + (c.P - c.W));
      if (cur) this.i = this.chunks.indexOf(cur);
    }
    /** chunk k follows chunk k - 1 without a gap (the next seq, the frame count going on; a gap = a lost chunk, a test state loaded) */
    joined(k) { return k > 0 && this.chunks[k].seq === this.chunks[k - 1].seq + 1 && this.chunks[k].W === this.chunks[k - 1].P; }
    async state(c) {
      if (c.data) return c.data;
      if (!c.state) throw new Error('chunk ' + c.seq + ' has no state');
      if (!this.loading.has(c.seq)) this.loading.set(c.seq, this.getState(c.seq).then(d => { c.data = d; this.loading.delete(c.seq); return d; },
        e => { this.loading.delete(c.seq); throw e; }));
      return this.loading.get(c.seq);
    }
    enter(k) { const c = this.chunks[k]; this.i = k; Object.assign(this.R, { W: c.W, P: c.P, pads: c.pads }); this.R.frame = c.W; }
    /** at the end of chunk i, joined to chunk k: the replay's state vs the recorded SHA-256 (once per boundary) */
    verify(k) {
      if (this.vk === k) return; this.vk = k;
      const c = this.chunks[k];
      if (this.drift || !c.sha) return;                    // drifting already: nothing to learn until the next keyframe
      this.checked++;
      if (sha256(this.R.save()) !== c.sha) { this.mismatches.push(c.seq); this.drift = true; }
    }
    /** where the replay goes at the end of chunk i: { k, load } (load = take chunk k's recorded state), or null = wait */
    plan() {
      const k = this.i + 1, c = this.chunks[k];
      if (!c) return null;
      if (this.joined(k)) { this.verify(k); return { k, load: this.drift && c.state }; }
      for (let m = k; m < this.chunks.length; m++) if (this.chunks[m].state) return { k: m, load: true, gap: k };
      return null;                                         // a gap and no keyframe after it yet (live: one comes within ~30 s)
    }
    /** the next keyframe's state fetched ahead while drifting (play runs on without waiting there) */
    prefetch() {
      if (!this.drift) return;
      const n = this.chunks.findIndex((c, m) => m > this.i && c.state);
      if (n > 0 && !this.chunks[n].data) this.state(this.chunks[n]).catch(() => {});
    }
    /** to session frame g: the nearest keyframe at or before it (joined to it), then silent frames */
    async seek(g) {
      g = Math.max(0, Math.min(this.total, g));
      let k = this.chunks.findIndex((c, j) => g < this.cum[j + 1]); if (k < 0) k = this.chunks.length - 1;
      let j = k; while (j > 0 && !this.chunks[j].state && this.joined(j)) j--;
      if (!this.chunks[j] || !this.chunks[j].state) {      // a gap before it: the next keyframe after it
        j = this.chunks.findIndex((c, m) => m > k && c.state);
        if (j < 0) throw new Error('no keyframe to start from near frame ' + g);
      }
      this.R.load(await this.state(this.chunks[j])); this.drift = false; this.vk = -1; this.enter(j);
      while (this.pos < g) { if (this.step() === null && !(await this.ready())) break; }
    }
    /** false = the end of what has arrived; true = step can go on (the keyframe state it needs is here) */
    async ready() {
      if (this.i < 0) return false;
      if (this.R.frame < this.R.P) return true;
      const p = this.plan();
      if (!p) return false;
      if (p.load) await this.state(this.chunks[p.k]);
      return true;
    }
    step() {
      if (this.i < 0) return null;
      if (this.R.frame >= this.R.P) {                      // the chunk's end: on to the next one
        const p = this.plan();
        if (!p) return null;
        const c = this.chunks[p.k];
        if (p.load) {
          if (!c.data) { this.state(c).catch(() => {}); return null; }
          this.R.load(c.data);
          if (p.gap !== undefined) { if (!this.gaps.includes(this.chunks[p.gap].seq)) this.gaps.push(this.chunks[p.gap].seq); }
          if (this.drift || p.gap !== undefined) { if (!this.resyncs.includes(c.seq)) this.resyncs.push(c.seq); }
          this.drift = false;
        }
        this.enter(p.k); this.prefetch();
      }
      return this.R.step();
    }
  }
  SessionReplay.sha256 = sha256;
  if (typeof module !== 'undefined' && module.exports) module.exports = SessionReplay; else root.SessionReplay = SessionReplay;
})(typeof globalThis !== 'undefined' ? globalThis : this);
