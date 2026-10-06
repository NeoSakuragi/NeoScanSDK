/* Feedback replay engine (docs/feedback.md "In the browser"): a NeoScan Player bundle replayed in the Geolith core
 * compiled to WebAssembly (build_wasm.sh, the same tree as the APK and the desktop .so, save states v3). Used by the
 * Lab's Feedback tab (feedback.js) and by tools/feedback/replay_node.js (the same proof in Node).
 *   const r = await FeedbackReplay.create(GeoCore, { bios, rom, systype, hw }, bundle)
 *   bundle = { inputs: Uint8Array (inputs.bin), snaps: {frame: Uint8Array}, press: Uint8Array }
 *   r.seek(frame)            fast-forward (silent) from the latest kept state at or before frame; checkpoints checked
 *   r.step()                 one frame of the log: picture in r.core's fb, audio frames returned (Int16Array, stereo)
 *   r.check()                at the press: the state now vs press.state -> { same, sha, want } (SHA-256, hex) */
(function (root) {
  'use strict';
  const RESET_BIT = 0x8000;
  const hex = buf => Array.from(new Uint8Array(buf), b => b.toString(16).padStart(2, '0')).join('');
  async function sha256(bytes) {
    if (root.crypto && root.crypto.subtle) return hex(await root.crypto.subtle.digest('SHA-256', bytes));
    return require('crypto').createHash('sha256').update(bytes).digest('hex');
  }
  function parseInputs(b) {
    const dv = new DataView(b.buffer, b.byteOffset, b.byteLength);
    const magic = String.fromCharCode(b[0], b[1], b[2], b[3]);
    if (magic !== 'NSIN' || dv.getUint32(4, true) !== 1) throw new Error('inputs.bin: unknown format');
    const W = Number(dv.getBigUint64(8, true)), P = Number(dv.getBigUint64(16, true));
    const pads = new Uint16Array(2 * (P - W));
    for (let i = 0; i < pads.length; i++) pads[i] = dv.getUint16(24 + 2 * i, true);
    return { W, P, pads };
  }

  class FeedbackReplay {
    static async create(GeoCore, files, bundle) {
      const core = await GeoCore(files.moduleArgs || {});
      core.FS.mkdir('/sys'); core.FS.mkdir('/rom'); core.FS.mkdir('/save');
      core.FS.writeFile('/sys/neogeo.zip', files.bios);
      core.FS.writeFile('/rom/game.neo', files.rom);
      const str = s => { const n = core.lengthBytesUTF8 ? core.lengthBytesUTF8(s) + 1 : s.length + 1; const p = core._malloc(n);
        for (let i = 0; i < s.length; i++) core.HEAPU8[p + i] = s.charCodeAt(i); core.HEAPU8[p + s.length] = 0; return p; };
      const a = str(files.systype || 'mvs'), b = str(files.hw || 'mvs');
      core._wc_system(a, b); core._free(a); core._free(b);
      if (!core._wc_init()) throw new Error('the core did not load the game');
      return new FeedbackReplay(core, bundle);
    }
    constructor(core, bundle) {
      this.core = core;
      Object.assign(this, parseInputs(bundle.inputs));
      this.snaps = bundle.snaps; this.pressState = bundle.press;
      this.size = core._wc_state_size();
      this.buf = core._malloc(this.size);
      this.frame = this.W; this.mismatch = null;
      this.rate = core._wc_sample_rate(); this.fps = core._wc_fps();
    }
    save() { this.core._wc_save(this.buf, this.size); return this.core.HEAPU8.slice(this.buf, this.buf + this.size); }
    load(bytes) {
      if (bytes.length !== this.size) throw new Error(`state size ${bytes.length}, the core's ${this.size}: another core build`);
      this.core.HEAPU8.set(bytes, this.buf);
      if (!this.core._wc_load(this.buf, this.size)) throw new Error('the core refused the state (another system / region)');
    }
    /** the latest kept state at or before f */
    startFor(f) { return Math.max(...Object.keys(this.snaps).map(Number).filter(s => s <= f && s >= this.W), this.W); }
    /** silent fast-forward to frame f (from the latest kept state at or before it); each kept state passed is compared */
    seek(f, from) {
      f = Math.max(this.W, Math.min(this.P, f));
      const s = from !== undefined ? from : this.startFor(f);
      this.load(this.snaps[s] || this.pressState); this.frame = s;
      while (this.frame < f) { this.step(); this.checkSnap(); }
    }
    checkSnap() {
      const want = this.snaps[this.frame];
      if (!want || this.mismatch) return;
      const got = this.save();
      for (let i = 0; i < got.length; i++) if (got[i] !== want[i]) { this.mismatch = { frame: this.frame, byte: i }; return; }
    }
    /** one logged frame (pads, a soft reset where the log has one); returns its audio (stereo Int16, a copy) */
    step() {
      if (this.frame >= this.P) return null;
      const i = 2 * (this.frame - this.W), p0 = this.pads[i], p1 = this.pads[i + 1];
      if (p0 & RESET_BIT) this.core._wc_reset();
      this.core._wc_pad(0, p0 & 0x7FFF); this.core._wc_pad(1, p1);
      this.core._wc_run(); this.frame++;
      const n = this.core._wc_audio_n(), a = this.core._wc_audio() >> 1;
      return this.core.HEAP16.slice(a, a + 2 * n);
    }
    /** the state now vs press.state: compared byte for byte; the SHA-256s too where the page can hash (https) */
    async check() {
      const got = this.save(), want = this.pressState;
      let same = got.length === want.length;
      for (let i = 0; same && i < got.length; i++) if (got[i] !== want[i]) same = false;
      let sha = '', wsha = '';
      try { [sha, wsha] = await Promise.all([sha256(got), sha256(want)]); } catch (e) { /* no crypto.subtle (http) */ }
      return { same, sha, want: wsha, frame: this.frame };
    }
    /** the picture now as RGBA (for a canvas ImageData) */
    rgba(out) {
      const w = this.core._wc_fb_w(), h = this.core._wc_fb_h(), p = this.core._wc_fb() >> 2, px = this.core.HEAPU32;
      out = out && out.length === w * h * 4 ? out : new Uint8ClampedArray(w * h * 4);
      for (let i = 0; i < w * h; i++) { const v = px[p + i]; out[4 * i] = v >> 16 & 255; out[4 * i + 1] = v >> 8 & 255; out[4 * i + 2] = v & 255; out[4 * i + 3] = 255; }
      return { data: out, w, h };
    }
  }
  FeedbackReplay.sha256 = sha256;
  if (typeof module !== 'undefined' && module.exports) module.exports = FeedbackReplay; else root.FeedbackReplay = FeedbackReplay;
})(typeof globalThis !== 'undefined' ? globalThis : this);
