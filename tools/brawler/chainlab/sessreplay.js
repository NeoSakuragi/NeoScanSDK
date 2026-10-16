/* Session replay engine (docs/feedback.md "Session recording", Player 0.0.41): a tester's play session, sent by the
 * Player in ~5 s chunks (Session.kt: the state at each chunk's start + the pads of its frames), replayed in the wasm
 * Geolith core through fbreplay.js's FeedbackReplay (one core per build). Used by the Lab's Sessions tab (sessions.js)
 * and by tools/feedback/session_replay_node.js (the determinism proof in Node).
 *   const S = new SessionReplay(R, getState)       R = a FeedbackReplay on the session's build; getState(seq) -> Promise<Uint8Array>
 *   S.addMeta(chunks)                              the server's chunk rows (seq, start_frame, frames, state, state_sha)
 *   S.addInputs(bytes)                             feedback-api/session/<id>/inputs: per chunk u32 seq + NSIN v1
 *   await S.seek(g)                                to the session's frame g (0 .. S.total): the latest chunk state at or
 *                                                  before it, then silent frames
 *   S.step()                                       one frame -> its audio (Int16Array), or null (the end, or the next
 *                                                  chunk's state is still loading: call S.ready() and step again)
 * Where a chunk follows the one played without a gap, its recorded state is compared byte for byte with the replay's
 * state at that frame (S.checked / S.mismatches): the session's determinism, chunk by chunk. */
(function (root) {
  'use strict';
  const FR = root.FeedbackReplay || (typeof require !== 'undefined' ? require('./fbreplay.js') : null);

  class SessionReplay {
    constructor(R, getState) {
      this.R = R; this.getState = getState;
      this.chunks = [];                     // by seq: { seq, W, P, pads, state (bool), sha, data (Uint8Array once fetched) }
      this.bySeq = new Map();
      this.cum = [0];                       // cum[i] = the session frame where chunk i starts
      this.i = -1;                          // the chunk being played
      this.checked = 0; this.mismatches = [];
      this.loading = new Map();
    }
    get total() { return this.cum[this.cum.length - 1]; }
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
    /** chunk k follows chunk k - 1 without a gap (same frame count; a gap = a test state loaded, a lost chunk) */
    joined(k) { return k > 0 && this.chunks[k].W === this.chunks[k - 1].P; }
    async state(c) {
      if (c.data) return c.data;
      if (!c.state) throw new Error('chunk ' + c.seq + ' has no state');
      if (!this.loading.has(c.seq)) this.loading.set(c.seq, this.getState(c.seq).then(d => { c.data = d; this.loading.delete(c.seq); return d; },
        e => { this.loading.delete(c.seq); throw e; }));
      return this.loading.get(c.seq);
    }
    /** the next chunks' states fetched ahead (play runs on without waiting) */
    prefetch() { for (let k = this.i + 1; k <= this.i + 2 && k < this.chunks.length; k++) if (this.chunks[k].state && !this.chunks[k].data) this.state(this.chunks[k]).catch(() => {}); }
    enter(k) { const c = this.chunks[k]; this.i = k; Object.assign(this.R, { W: c.W, P: c.P, pads: c.pads }); this.prefetch(); }
    /** to session frame g: the latest chunk with a state at or before it, joined to it, then silent frames */
    async seek(g) {
      g = Math.max(0, Math.min(this.total, g));
      let k = this.chunks.findIndex((c, j) => g < this.cum[j + 1]); if (k < 0) k = this.chunks.length - 1;
      let j = k; while (j > 0 && !this.chunks[j].state && this.joined(j)) j--;
      if (!this.chunks[j] || !this.chunks[j].state) throw new Error('no state to start from before frame ' + g);
      this.R.load(await this.state(this.chunks[j])); this.enter(j); this.R.frame = this.chunks[j].W;
      while (this.pos < g) { if (this.step() === null && !(await this.ready())) break; }
    }
    /** false = the end of what has arrived; true = step can go on (the next chunk's state, when it needs one, is here) */
    async ready() {
      const k = this.i + 1;
      if (this.R.frame < this.R.P) return true;
      if (k >= this.chunks.length) return false;
      if (this.chunks[k].state) await this.state(this.chunks[k]);
      return true;
    }
    step() {
      if (this.i < 0) return null;
      if (this.R.frame >= this.R.P) {                     // the chunk's end: on to the next one
        const k = this.i + 1, c = this.chunks[k];
        if (!c) return null;
        if (c.state && !c.data) { this.state(c).catch(() => {}); return null; }
        if (this.joined(k) && c.data) {                   // the replay's state here vs the one the Player recorded
          const got = this.R.save(); let same = got.length === c.data.length;
          for (let x = 0; same && x < got.length; x++) if (got[x] !== c.data[x]) same = false;
          this.checked++;
          if (!same) { this.mismatches.push(c.seq); this.R.load(c.data); }   // shown, then back on the recorded track
        } else if (!this.joined(k) && c.data) this.R.load(c.data);   // a gap: the chunk's own state
        this.enter(k); this.R.frame = c.W;
      }
      return this.R.step();
    }
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = SessionReplay; else root.SessionReplay = SessionReplay;
})(typeof globalThis !== 'undefined' ? globalThis : this);
