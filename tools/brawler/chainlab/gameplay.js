/* The game in a page: the Brawler Lab's player around the wasm core (lab.js Lab: core.wasm, web_core.c) — keyboard,
 * gamepad, touch pad, sound, the picture, the frame loop, pause / step. One copy for every page that plays the game:
 * the Chain Lab (app.js) and the "Try in game" panel (tryit.js: the Workshop, the dictionary, the arbitration sheet).
 *   const gp = GamePlay.attach({ lab, canvas, ... })    (options below)
 *   gp.stepFrames(n), gp.togglePause(), gp.draw(), gp.fit(), gp.paused, gp.override = 'aR' | null (scripted pads),
 *   gp.stats() -> {frames, ms} (frames run and the time spent in the core), gp.stop()
 * Options: lab; canvas; fit(canvas) (else scaleSel + col: a whole number of screen pixels per game pixel); soundBtn,
 * pauseBtn, stepBtn (buttons it drives); touch (an element with button[data-k] keys: shown on touch screens); status(paused)
 * -> the status line's text (statusEl), undefined = none; onFrame() after every frame; running() -> false: the loop
 * idles (a closed panel); keyActive() -> false: the keys are the page's (default: always the game's); escPause: Escape /
 * Backspace pause (default true; the panel keeps Escape for the page's dialogs). */
(function (root) {
  'use strict';
  // by physical key (KeyboardEvent.code), so the layout is the same on QWERTZ / AZERTY / QWERTY (Bruno, 2026-10-05):
  // WASD stick, U I O P = A B C D; the arrows and Z X C V (QWERTY positions) also work
  const KEYMAP = { KeyW: 'U', KeyA: 'L', KeyS: 'D', KeyD: 'R', KeyU: 'a', KeyI: 'b', KeyO: 'c', KeyP: 'd',
                   ArrowLeft: 'L', ArrowRight: 'R', ArrowUp: 'U', ArrowDown: 'D', KeyZ: 'a', KeyX: 'b', KeyC: 'c', KeyV: 'd',
                   Enter: 's', NumpadEnter: 's' };
  function attach(o) {
    const lab = o.lab, canvas = o.canvas, ctx = canvas.getContext('2d');
    const running = o.running || (() => true), keyActive = o.keyActive || (() => true), escPause = o.escPause !== false;
    let img = null, paused = false, acc = 0, last = 0, override = null, stopped = false, nframes = 0, ms = 0;
    const fps = lab.core._wc_fps();
    const keys = new Set(), touch = new Set();
    const typing = e => e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT' || e.target.tagName === 'TEXTAREA');
    addEventListener('keydown', e => {
      if (stopped || !keyActive() || typing(e)) return;
      if (escPause && (e.code === 'Escape' || e.code === 'Backspace')) { togglePause(); e.preventDefault(); return; }
      if (e.code === 'Period' && paused) { stepFrames(1); e.preventDefault(); return; }
      const k = KEYMAP[e.code]; if (k) { keys.add(k); e.preventDefault(); }
    });
    addEventListener('keyup', e => { const k = KEYMAP[e.code]; if (k) keys.delete(k); });
    addEventListener('blur', () => keys.clear());
    function padKeys() {
      if (override !== null) return override;
      const s = new Set([...keys, ...touch]);
      for (const gp of (navigator.getGamepads ? navigator.getGamepads() : [])) {
        if (!gp) continue;
        const b = i => gp.buttons[i] && gp.buttons[i].pressed;
        if (b(0)) s.add('a'); if (b(1)) s.add('b'); if (b(2)) s.add('c'); if (b(3)) s.add('d'); if (b(9)) s.add('s');
        if (b(12) || gp.axes[1] < -0.5) s.add('U'); if (b(13) || gp.axes[1] > 0.5) s.add('D');
        if (b(14) || gp.axes[0] < -0.5) s.add('L'); if (b(15) || gp.axes[0] > 0.5) s.add('R');
      }
      return [...s].join('');
    }
    // touch pad (shown on touch screens)
    if (o.touch) {
      if (matchMedia('(pointer: coarse)').matches) o.touch.classList.add('show');
      for (const b of o.touch.querySelectorAll('button[data-k]')) {
        const ks = [b.dataset.k];
        b.addEventListener('pointerdown', e => { ks.forEach(k => touch.add(k)); b.classList.add('on'); e.preventDefault(); });
        for (const t of ['pointerup', 'pointercancel', 'pointerleave']) b.addEventListener(t, () => { ks.forEach(k => touch.delete(k)); b.classList.remove('on'); });
      }
    }

    // audio: the core's frames into a ring, a ScriptProcessor pulls them (resampled when the context's rate differs)
    let audio = null;
    const RING = 1 << 15, ring = new Float32Array(RING * 2); let rw = 0, rr = 0;
    const coreRate = lab.core._wc_sample_rate();
    function pushAudio() {
      if (!audio) return;
      const n = lab.core._wc_audio_n(), p = lab.core._wc_audio() >> 1, h = lab.core.HEAP16;
      for (let i = 0; i < n; i++) {
        if (((rw + 1) & (RING - 1)) === rr) break;
        ring[rw * 2] = h[p + i * 2] / 32768; ring[rw * 2 + 1] = h[p + i * 2 + 1] / 32768; rw = (rw + 1) & (RING - 1);
      }
    }
    async function sound(on) {
      if (!on) { if (audio) await audio.close(); audio = null; if (o.soundBtn) o.soundBtn.textContent = 'Sound: off'; return; }
      if (audio) return;
      let ac; try { ac = new AudioContext({ sampleRate: coreRate }); } catch (e) { ac = new AudioContext(); }
      const sp = ac.createScriptProcessor(2048, 0, 2), step = coreRate / ac.sampleRate; let frac = 0;
      sp.onaudioprocess = ev => {
        const L = ev.outputBuffer.getChannelData(0), R = ev.outputBuffer.getChannelData(1);
        for (let i = 0; i < L.length; i++) {
          if (rr === rw) { L[i] = R[i] = 0; continue; }
          L[i] = ring[rr * 2]; R[i] = ring[rr * 2 + 1];
          frac += step; while (frac >= 1 && rr !== rw) { rr = (rr + 1) & (RING - 1); frac -= 1; }
        }
        const fill = (rw - rr) & (RING - 1); if (fill > 8192) rr = (rw - 2048) & (RING - 1);   // never lag behind the picture
      };
      sp.connect(ac.destination); audio = ac; rr = rw; if (o.soundBtn) o.soundBtn.textContent = 'Sound: on';
    }
    if (o.soundBtn) o.soundBtn.onclick = () => sound(!audio);

    function draw() {
      const w = lab.core._wc_fb_w(), h = lab.core._wc_fb_h();
      if (canvas.width !== w || canvas.height !== h || !img) { canvas.width = w; canvas.height = h; img = ctx.createImageData(w, h); fit(); }
      const src = new Uint8Array(lab.core.HEAPU8.buffer, lab.core._wc_fb(), w * h * 4), d = img.data;
      for (let i = 0; i < w * h * 4; i += 4) { d[i] = src[i + 2]; d[i + 1] = src[i + 1]; d[i + 2] = src[i]; d[i + 3] = 255; }
      ctx.putImageData(img, 0, 0);
      const t = o.status ? o.status(paused) : undefined;
      if (t !== undefined && o.statusEl) o.statusEl.textContent = t;
    }
    function fit() {                        // pixel-exact: a whole number of screen pixels per game pixel
      if (o.fit) { o.fit(canvas); return; }
      if (!o.scaleSel || !o.col) return;
      const want = Number(o.scaleSel.value), avail = o.col.clientWidth - 36;
      const s = want || Math.max(1, Math.floor(Math.min(avail / canvas.width, (innerHeight * 0.62) / canvas.height)));
      canvas.style.width = canvas.width * s + 'px'; canvas.style.height = canvas.height * s + 'px';
    }
    addEventListener('resize', fit); if (o.scaleSel) o.scaleSel.onchange = fit;
    function stepFrames(n) {
      const t0 = performance.now();
      for (let i = 0; i < n; i++) { lab.setPad(0, padKeys()); lab.run(1); pushAudio(); if (o.onFrame) o.onFrame(); }
      ms += performance.now() - t0; nframes += n;
      draw();
    }
    function togglePause() {
      paused = !paused;
      if (o.pauseBtn) { o.pauseBtn.textContent = paused ? 'Resume' : 'Pause'; o.pauseBtn.classList.toggle('on', paused); }
      if (o.stepBtn) o.stepBtn.disabled = !paused;
      draw();
    }
    if (o.pauseBtn) o.pauseBtn.onclick = togglePause;
    if (o.stepBtn) o.stepBtn.onclick = () => stepFrames(1);
    function loop(ts) {
      if (stopped) return;
      requestAnimationFrame(loop);
      if (!last) last = ts;
      acc += (ts - last) / 1000 * fps; last = ts;
      if (paused || !running()) { acc = 0; return; }
      let n = Math.floor(acc); acc -= n;
      if (n > 4) { n = 4; acc = 0; }       // a tab in the background: no catch-up burst
      if (n) stepFrames(n);
    }
    requestAnimationFrame(loop);
    return {
      stepFrames, togglePause, draw, fit, sound, padKeys,
      get paused() { return paused; }, get fps() { return fps; },
      get override() { return override; }, set override(v) { override = v; },
      stats() { return { frames: nframes, ms }; },
      stop() { stopped = true; sound(false); }
    };
  }
  const api = { attach, KEYMAP };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.GamePlay = api;
})(typeof window !== 'undefined' ? window : globalThis);
