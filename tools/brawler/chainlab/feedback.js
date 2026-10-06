/* Brawler Lab, Feedback tab: the NeoScan Player's voice / text feedback (docs/feedback.md). Since Player 0.0.22 the
 * notes are CARDS, the same as the player's list (Bruno): title / "44 min ago on 0.0.17" / the screenshot (a click =
 * Test it: the note's scenario state in the browser under the banner "Do / Expect", keyboard WASD + U I O P or the
 * arrows + Z X C V, Restart, Show expected, 👍 / 👎 = a test attempt that sets verified / reopened) / [FIX 0.0.x] / the
 * fix and its root cause / More (collapsed: the note, the voice, category + fighters, the bundle replay, the timeline,
 * the origin, the cost) / Fixed - Broken - Reply; filters Open / Shipped: test it / All. The list comes from the
 * feedback service's API (tools/feedback/server.py) at feedback-api/ (nginx, behind the same Oros login as the Lab):
 * date, the user (Oros account, Player 0.0.15+), versions, the note's title (my one-liner, fb.py set --title) as its headline, the note as sent (the raw transcript under it), status and release as text, the voice (play),
 * the screenshot; filters by status and category; category (dropdown) and fighters editable here. Status changes go
 * through tools/feedback/fb.py. Replay (fbreplay.js): the note's game build (feedback-api/rom/<sha>, cached by the
 * browser), the page's BIOS, the kept state before the last 10 s, then the logged inputs to the press with sound;
 * pause / step / slow motion / restart, the press screenshot beside, and the press state's SHA-256 checked. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  while (!window.stagesTab && !window.labTab) await new Promise(r => setTimeout(r, 100));
  const API = 'feedback-api/';
  const STATUS_TEXT = { new: 'NEW', read: 'read', in_progress: 'IN PROGRESS', fixed: 'FIXED', shipped: 'SHIPPED', wont_do: "won't do", duplicate: 'duplicate', verified: 'VERIFIED', reopened: 'REOPENED' };
  const REPLY_KIND = { up: '👍 verified fixed', down: '👎 still broken', voice: 'voice', text: 'text' };
  // the player's reply thread (Player 0.0.17): oldest first, the voice playable, a status change shown
  const thread = r => (r.replies || []).length ? h('div', { class: 'small', style: 'margin-top:6px;border-top:1px solid #000;padding-top:4px' },
    h('b', {}, 'Thread'), r.replies.map(x => h('div', {},
      x.at.slice(0, 16).replace('T', ' ') + ' ' + (x.user || '') + ' — ' + (REPLY_KIND[x.kind] || x.kind) +
        (x.status_to ? ' [' + x.status_from + ' → ' + x.status_to + ']' : '') + (x.text ? ': ' + x.text : ''),
      x.audio_path ? h('audio', { controls: true, preload: 'none', src: API + 'file/' + r.id + '/' + x.audio_path, style: 'display:block;height:28px' }) : null))) : null;
  let rows = [], cats = [], cost = null, filt = { status: '', category: '' }, msg = '';
  const col = $('fbcol');
  const rbox = h('div'), lbox = h('div');
  if (col) col.append(rbox, lbox);

  // ---- replay -------------------------------------------------------------------------------------------------------
  const cores = {}, roms = {};                          // rom sha + memory card -> the wasm core with that build loaded; rom sha -> the build
  let bios = null, R = null, raf = 0, playing = false, speed = 1, acc = 0, last = 0, ac = null, at = 0, startState = null, img = null;
  const get = async (url, what) => { const r = await fetch(url, { credentials: 'same-origin' }); if (!r.ok) throw new Error(what + ': HTTP ' + r.status); return new Uint8Array(await r.arrayBuffer()); };
  function stopLoop() { playing = false; cancelAnimationFrame(raf); }
  async function openReplay(r) {
    stopLoop();
    rbox.textContent = '';
    const st = h('p', { class: 'mono' }, 'Loading the note and the game build (12 MB the first time)…');
    const cv = h('canvas', { width: 304, height: 224, class: 'fbscreen' });
    // Player 0.0.15: his drawing over the press screenshot (screen_marked.png); the replay's check stays on the clean screen.png
    const shot = h('img', { src: API + 'file/' + r.id + (r.marked ? '/screen_marked.png' : '/screen.png'), class: 'fbscreen', alt: 'press screenshot' });
    const pos = h('span', { class: 'mono' }, '');
    const res = h('p', { class: 'mono' }, '');
    const bPlay = h('button', { onclick: () => toggle() }, 'Play');
    const toggle = () => { if (!R) return; if (playing) { stopLoop(); bPlay.textContent = 'Play'; } else if (R.frame < R.P) { playing = true; bPlay.textContent = 'Pause'; last = performance.now(); acc = 0; raf = requestAnimationFrame(tick); } };
    const draw = () => {
      const p = R.rgba(img && img.data); if (cv.width !== p.w) { cv.width = p.w; cv.height = p.h; }
      if (!img || img.width !== p.w) img = new ImageData(p.data, p.w, p.h); cv.getContext('2d').putImageData(img, 0, 0);
      const left = R.P - R.frame;
      pos.textContent = left ? `frame ${R.frame}, the press in ${left} frames (${(left / R.fps).toFixed(2)} s)` : `frame ${R.frame} = the press`;
    };
    const sound = a => {
      if (!a || !a.length || speed !== 1) return;
      if (!ac) { try { ac = new AudioContext({ sampleRate: Math.round(R.rate) }); } catch (e) { ac = new AudioContext(); } }
      const n = a.length / 2, b = ac.createBuffer(2, n, R.rate), L = b.getChannelData(0), Rt = b.getChannelData(1);
      for (let i = 0; i < n; i++) { L[i] = a[2 * i] / 32768; Rt[i] = a[2 * i + 1] / 32768; }
      const src = ac.createBufferSource(); src.buffer = b; src.connect(ac.destination);
      at = Math.max(at, ac.currentTime + 0.05); src.start(at); at += n / R.rate;
    };
    const atPress = async () => {
      stopLoop(); bPlay.textContent = 'Play';
      const c = await R.check();
      res.textContent = (c.same ? 'Press state: byte-identical to the player\'s' : 'Press state: DIFFERENT from the player\'s') +
        (c.sha ? ` (SHA-256 ${c.sha.slice(0, 16)}… vs ${c.want.slice(0, 16)}…)` : ' (compared byte for byte)') + (R.mismatch ? `; first differing kept state: frame ${R.mismatch.frame}` : '');
    };
    function tick(t) {
      if (!playing) return;
      acc += (t - last) / 1000 * R.fps * speed; last = t;
      let n = 0;
      while (acc >= 1 && R.frame < R.P && n < 4) { sound(R.step()); R.checkSnap(); acc -= 1; n++; }
      if (acc > 4) acc = 0;
      draw();
      if (R.frame >= R.P) { atPress(); return; }
      raf = requestAnimationFrame(tick);
    }
    const restart = () => { stopLoop(); bPlay.textContent = 'Play'; R.load(startState); R.frame = R.start; R.mismatch = null; res.textContent = ''; at = 0; draw(); };
    rbox.append(h('div', { class: 'box' },
      h('h2', {}, 'Replay ' + r.id + (r.title ? ' — ' + r.title : ''), h('span', { class: 'sp' }), h('button', { onclick: () => { stopLoop(); rbox.textContent = ''; } }, 'Close')),
      h('div', { class: 'in' },
        h('p', {}, (r.final_text || r.raw_transcript || '').slice(0, 300)),
        h('div', { class: 'fbpair' }, h('figure', {}, cv, h('figcaption', {}, 'replay (the last 10 s before the press)')),
                                      h('figure', {}, shot, h('figcaption', {}, r.marked ? 'the player\'s screen at the press, with his drawing' : 'the player\'s screen at the press'))),
        h('div', { class: 'row' }, bPlay,
          h('button', { onclick: () => { if (!R || playing || R.frame >= R.P) return; sound(null); R.step(); R.checkSnap(); draw(); if (R.frame >= R.P) atPress(); } }, 'Step 1 frame'),
          h('label', {}, 'Speed ', h('select', { onchange: e => { speed = +e.target.value; } },
            h('option', { value: 1 }, '1× (sound)'), h('option', { value: 0.5 }, '½×'), h('option', { value: 0.25 }, '¼×'), h('option', { value: 0.1 }, '1/10×'))),
          h('button', { onclick: restart }, 'Restart'), pos),
        st, res)));
    try {
      const [item, rom] = await Promise.all([
        fetch(API + 'item/' + r.id, { credentials: 'same-origin' }).then(x => x.json()),
        roms[r.rom_sha] ? null : get(API + 'rom/' + r.rom_sha, 'game build ' + r.game_version)]);
      if (!bios) bios = await get('neogeo.zip', 'BIOS');
      const snaps = {};
      const names = item.files.filter(f => /^snap_\d+\.state$/.test(f));
      const [inputs, press, meta, ...snapData] = await Promise.all([get(API + 'file/' + r.id + '/inputs.bin', 'inputs'), get(API + 'file/' + r.id + '/press.state', 'press state'),
        fetch(API + 'file/' + r.id + '/meta.json', { credentials: 'same-origin' }).then(x => x.json()), ...names.map(f => get(API + 'file/' + r.id + '/' + f, f))]);
      names.forEach((f, i) => { snaps[+f.slice(5, -6)] = snapData[i]; });
      const bundle = { inputs, snaps, press };
      const ck = r.rom_sha + ':' + (meta.memcard || 'on');            // a core per ROM and memory card setting
      if (rom) roms[r.rom_sha] = rom;
      if (!cores[ck]) cores[ck] = (await FeedbackReplay.create(window.GeoCore, { bios, rom: roms[r.rom_sha], systype: meta.system_type, hw: meta.hw, memcard: meta.memcard }, bundle)).core;
      R = new FeedbackReplay(cores[ck], bundle);
      const t0 = performance.now();
      R.start = Math.max(R.W, R.P - 600);
      R.seek(R.start); startState = R.save(); draw();
      if (r.autoplay) toggle();
      st.textContent = `Ready: fast-forwarded silently from the kept state at frame ${R.startFor(R.start)} in ${Math.round(performance.now() - t0)} ms; ` +
        `the window holds frames ${R.W}..${R.P} (${((R.P - R.W) / R.fps).toFixed(1)} s). Play runs the last ${((R.P - R.start) / R.fps).toFixed(1)} s to the press.`;
    } catch (e) { st.textContent = 'Replay unavailable: ' + e.message; R = null; }
  }

  // ---- cards (the player's layout, Player 0.0.22) ------------------------------------------------------------------
  const css = document.createElement('style');
  css.textContent = `
#fbcol .fbfilters { display: flex; gap: 8px; flex-wrap: wrap; margin: 6px 0; }
#fbcol .fbfilters button.on { font-weight: bold; outline: 3px solid #000; }
#fbcol .fbcard { border: 2px solid #000; background: #fff; color: #000; padding: 10px 12px; margin: 0 0 12px; max-width: 760px; }
#fbcol .fbcard h3 { margin: 0 0 2px; font-size: 18px; }
#fbcol .fbmeta { display: flex; gap: 8px; align-items: center; font-size: 13.5px; margin-bottom: 6px; }
#fbcol .fbmeta .sp { flex: 1; }
#fbcol .fbstatus { border: 2px solid #000; padding: 1px 6px; font-weight: bold; font-size: 12px; }
#fbcol .fbshot { position: relative; display: inline-block; cursor: pointer; }
#fbcol .fbshot img { display: block; width: 456px; max-width: 100%; image-rendering: pixelated; border: 1px solid #000; }
#fbcol .fbshot .lab { position: absolute; left: 6px; top: 6px; background: #fff; border: 2px solid #000; padding: 1px 6px; font-weight: bold; font-size: 13px; }
#fbcol .fbshot .lab.none { font-weight: normal; font-size: 11px; }
#fbcol .fbfix { font-family: ui-monospace, monospace; font-weight: bold; margin-top: 8px; }
#fbcol .fbcard details { margin-top: 8px; border-top: 1px solid #000; padding-top: 4px; }
#fbcol .fbcard summary { cursor: pointer; font-weight: bold; }
#fbcol .fbtl { font-size: 12.5px; border-collapse: collapse; margin-top: 4px; }
#fbcol .fbtl td { border-top: 1px solid #000; padding: 2px 6px 2px 0; vertical-align: top; }
#fbcol .fbacts { display: flex; gap: 8px; margin-top: 8px; }
#fbcol .fbacts button { flex: 1; }
#fbcol .fbbanner { border: 3px solid #000; padding: 6px 8px; margin-bottom: 8px; background: #fff; }
#fbcol .fbbanner b { font-size: 16px; }`;
  document.head.append(css);
  let view = 'open';
  try { view = localStorage.getItem('fbview') || 'open'; } catch (e) { /* no storage */ }
  const ago = iso => {
    const s = (Date.now() - Date.parse(iso)) / 1000;
    if (s < 60) return 'just now'; if (s < 3600) return Math.floor(s / 60) + ' min ago'; if (s < 86400) return Math.floor(s / 3600) + ' h ago';
    if (s < 2 * 86400) return 'yesterday'; if (s < 7 * 86400) return Math.floor(s / 86400) + ' days ago';
    return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  };
  const isOpen = r => !['shipped', 'wont_do', 'duplicate', 'verified'].includes(r.status);
  // the test queue (docs/feedback.md "The test queue"): the server's to_test = shipped and no 👍 / 👎 yet on that release
  // or a later build; a verdict takes it out (reopened stays in Open), a later ship with a newer release brings it back
  const wants = r => !!r.to_test;
  const testable = r => !!(r.scenario && (r.scenario_builds || []).some(b => b.endsWith('/mvs-mvs')));
  const FILTERS = { open: ['Open', isOpen], ready: ['Shipped: test it', wants], all: ['All', () => true] };

  async function load() {
    try {
      const r = await fetch(API + 'list', { cache: 'no-store', credentials: 'same-origin' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json(); rows = j.rows; cats = j.categories; cost = j.cost; msg = '';
    } catch (e) { msg = 'The feedback list is unavailable (' + e.message + ').'; }
    render();
  }

  async function post(path, body, ok) {
    try {
      const r = await fetch(API + path, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      if (j.row) rows = rows.map(x => x.id === body.id ? Object.assign({}, x, j.row) : x);
      msg = ok || 'Saved ' + body.id + '.'; await load(); return true;
    } catch (e) { msg = 'Not saved: ' + e.message; render(); return false; }
  }
  const set = (id, body) => post('set', Object.assign({ id }, body));

  function play(btn, r, path) {
    const old = btn.parentNode.querySelector('audio');
    if (old) { old.remove(); btn.textContent = '▶ Voice'; return; }
    const a = h('audio', { controls: true, src: API + 'file/' + r.id + '/' + (path || r.audio_path), preload: 'auto' });
    btn.after(a); btn.textContent = '■ Close'; a.play().catch(() => {});
  }

  function card(r) {
    const can = testable(r);
    const shot = r.marked ? 'screen_marked.png' : 'screen.png';
    const last = (r.replies || []).filter(x => x.text).slice(-1)[0];
    const tl = r.timeline || [];
    return h('div', { class: 'fbcard' },
      h('h3', {}, r.title || (r.final_text || r.raw_transcript || '(no text)').slice(0, 70)),
      h('div', { class: 'fbmeta' }, h('span', { title: r.created.replace('T', ' ').slice(0, 19) + ' UTC, ' + r.id }, `${ago(r.created)} on ${r.game_version}`),
        h('span', {}, '· ' + (r.user || '(before the login)')), h('span', { class: 'sp' }), h('span', { class: 'fbstatus' }, STATUS_TEXT[r.status] || r.status)),
      h('div', { class: 'fbshot', title: can ? 'Test it: the scenario state in the browser' : 'the screenshot (no test yet)',
                 onclick: () => { if (can) { testIt(r); col.scrollIntoView({ behavior: 'smooth' }); } else window.open(API + 'file/' + r.id + '/' + shot, '_blank'); } },
        h('img', { src: API + 'file/' + r.id + '/' + shot, alt: 'the screenshot at the press', loading: 'lazy' }),
        h('span', { class: 'lab' + (can ? '' : ' none') }, can ? '▶ TEST IT' : 'no test yet')),
      r.release && ['shipped', 'verified', 'reopened'].includes(r.status) ? h('div', { class: 'fbfix' }, `[FIX ${r.release}]`) : null,
      r.fix ? h('div', {}, 'Fix: ' + r.fix) : null,
      r.rca ? h('div', {}, 'Cause: ' + r.rca) : null,
      h('details', {}, h('summary', {}, 'More'),
        last ? h('p', {}, `His latest reply (${ago(last.at)}): ${last.text}`) : null,
        h('p', {}, 'The note: ' + (r.final_text || '(no text typed)')),
        r.raw_transcript && !(r.final_text || '').includes(r.raw_transcript) ? h('p', { class: 'small' }, 'transcript: ' + r.raw_transcript) : null,
        r.scenario ? h('p', { class: 'small' }, `Test: ${r.scenario.title}. Do: ${r.scenario.do} Expect: ${r.scenario.expect} States: ${(r.scenario_builds || []).map(b => b.slice(0, 12) + b.slice(64)).join(', ') || 'none yet'}`) : null,
        h('div', { class: 'row' },
          r.audio_path ? h('button', { onclick: e => play(e.target, r) }, '▶ Voice') : null,
          h('button', { onclick: () => { openReplay(r); col.scrollIntoView({ behavior: 'smooth' }); } }, 'Replay the note'),
          r.marked ? h('a', { href: API + 'file/' + r.id + '/screen.png', target: '_blank' }, 'clean screenshot') : null),
        h('div', { class: 'row' }, 'Category ',
          h('select', { onchange: e => set(r.id, { category: e.target.value }) }, h('option', { value: '' }, '(none)'), cats.map(c => h('option', { value: c, selected: r.category === c }, c))),
          ' fighters ', h('input', { type: 'text', value: r.fighters, size: 16, onchange: e => set(r.id, { fighters: e.target.value }) }),
          r.todo ? ' TODO #' + r.todo.split(',').join(', #') : null),
        r.notes ? h('p', { class: 'small' }, 'Developer\'s notes: ' + r.notes) : null,
        thread(r),
        h('b', {}, 'Timeline'),
        h('table', { class: 'fbtl' }, tl.map(e => h('tr', {}, h('td', { class: 'mono' }, e.at.slice(0, 16).replace('T', ' ')), h('td', {}, h('b', {}, e.kind.replace('_', ' '))),
          h('td', {}, e.by || '-'), h('td', {}, e.text)))),
        h('p', { class: 'small mono' }, `player ${r.apk_version}, ${r.device || '?'}${r.android ? ', Android ' + r.android : ''}, install ${(r.install_id || '-').slice(0, 8)}, IP ${r.ip || '-'}, ${r.user_agent || ''}` +
          (r.cost_usd == null ? '' : `, transcription $${r.cost_usd.toFixed(4)}${(r.cost_source || '').includes('duration') ? ' (estimated)' : ''}`))),
      h('div', { class: 'fbacts' },
        h('button', { onclick: () => { if (confirm('Verified fixed?')) post('test', { id: r.id, result: 'up' }, 'Verified ' + r.id); } }, '👍 Fixed'),
        h('button', { onclick: () => { const t = prompt('Still broken: what is wrong (optional)?'); if (t !== null) post('test', { id: r.id, result: 'down', note: t }, 'Reopened ' + r.id); } }, '👎 Broken'),
        h('button', { onclick: () => { const t = prompt('Reply (goes into the note\'s timeline):'); if (t) post('event', { id: r.id, kind: 'reply', text: t, ref: new Date().toISOString(), at: new Date().toISOString().slice(0, 19) + 'Z' }, 'Replied'); } }, 'Reply')));
  }

  function render() {
    if (!col) return;
    lbox.textContent = '';
    rows.sort((a, b) => (b.status === 'reopened') - (a.status === 'reopened') || (b.created > a.created ? 1 : -1));
    const shown = rows.filter(FILTERS[view][1]);
    const queue = rows.filter(r => wants(r) && testable(r)).reverse();
    lbox.append(h('div', { class: 'box' },
      h('h2', {}, 'Feedback from the player', h('span', { class: 'sp' }), h('button', { onclick: load }, 'Reload')),
      h('div', { class: 'in' },
        h('div', { class: 'fbfilters' }, Object.entries(FILTERS).map(([k, [t, f]]) => h('button', { class: view === k ? 'on' : '',
          onclick: () => { view = k; try { localStorage.setItem('fbview', k); } catch (e) { /* no storage */ } render(); } }, `${t} (${rows.filter(f).length})`)),
          queue.length ? h('button', { onclick: () => { testIt(queue[0], queue); col.scrollIntoView({ behavior: 'smooth' }); } }, `▶ Test queue (${queue.length})`) : null),
        msg ? h('p', { class: 'ok' }, msg) : null,
        cost ? h('p', { class: 'note' }, `Transcription cost: $${cost.usd.toFixed(4)} in all (${cost.transcriptions} transcriptions, ${Math.round(cost.audio_seconds)} s of audio). Status: NEW → read → IN PROGRESS → FIXED (commit) → SHIPPED (release) → 👍 VERIFIED / 👎 REOPENED; set with tools/feedback/fb.py.`) : null,
        shown.length ? shown.map(card) : h('p', {}, view === 'ready' ? 'Nothing shipped to test.' : 'No notes here.'))));
  }

  // ---- Test it: a note's scenario state in the browser (the player's VERIFY mode) ----------------------------------
  const KEYBITS = { U: 4, D: 5, L: 6, R: 7, a: 0, b: 8, c: 1, d: 9, s: 3, o: 2 };
  const TKEYS = { KeyW: 'U', KeyA: 'L', KeyS: 'D', KeyD: 'R', KeyU: 'a', KeyI: 'b', KeyO: 'c', KeyP: 'd', ArrowLeft: 'L', ArrowRight: 'R',
                  ArrowUp: 'U', ArrowDown: 'D', KeyZ: 'a', KeyX: 'b', KeyC: 'c', KeyV: 'd', Enter: 's' };
  const held = new Set();
  let T = null;                                       // the test running: {r, R, state, t0, queue, script}
  addEventListener('keydown', e => { if (!T || /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return; const k = TKEYS[e.code]; if (k) { held.add(k); e.preventDefault(); } });
  addEventListener('keyup', e => { const k = TKEYS[e.code]; if (k) held.delete(k); });
  const bits = s => [...s].reduce((m, k) => m | (KEYBITS[k] !== undefined ? 1 << KEYBITS[k] : 0), 0);
  function stopTest(verdict) {
    if (!T) return;
    stopLoop(); const t = T; T = null;
    if (!verdict && t.loaded) fetch(API + 'test', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: t.r.id, result: 'abandoned', rom_sha: t.sha, game_version: t.ver, system: 'mvs-mvs', seconds: (performance.now() - t.t0) / 1000 }) }).catch(() => {});
  }
  async function testIt(r, queue) {
    stopTest(false); stopLoop();
    rbox.textContent = '';
    const sc = r.scenario || {};
    const b = (r.scenario_builds || []).filter(x => x.endsWith('/mvs-mvs')).slice(-1)[0] || '';
    const sha = b.slice(0, 64);
    const ver = ((r.timeline || []).filter(e => e.kind === 'scenario' && e.ref === sha).map(e => (/v([\d.]+)/.exec(e.text) || [])[1]).filter(Boolean)[0]) || '?';
    const st = h('span', { class: 'mono' }, 'Loading the test state and build ' + ver + ' (12 MB the first time)…');
    const cv = h('canvas', { width: 304, height: 224, class: 'fbscreen', tabindex: 0 });
    const bPlay = h('button', {}, '▶ Play');
    const n = queue ? queue.indexOf(r) : -1;
    const verdict = res => async () => {
      let note = '';
      if (res === 'down') { note = prompt('Still broken: what is wrong (optional)?'); if (note === null) return; }
      const t = T; stopTest(true);
      await post('test', { id: r.id, result: res, rom_sha: sha, game_version: ver, system: 'mvs-mvs', note, seconds: t ? (performance.now() - t.t0) / 1000 : null },
                 res === 'up' ? 'Verified ' + r.id : 'Reopened ' + r.id);
      if (queue && n + 1 < queue.length) testIt(queue[n + 1], queue); else rbox.textContent = '';
    };
    rbox.append(h('div', { class: 'box' },
      h('h2', {}, 'Test it: ' + r.id + (queue ? ` (${n + 1} of ${queue.length})` : ''), h('span', { class: 'sp' }), h('button', { onclick: () => { stopTest(false); rbox.textContent = ''; } }, 'Close')),
      h('div', { class: 'in' },
        h('div', { class: 'fbbanner' }, h('b', {}, sc.title || r.title), h('div', {}, 'Do: ' + (sc.do || '')), h('div', {}, 'Expect: ' + (sc.expect || '')),
          h('div', { class: 'small' }, 'Keys: WASD + U I O P (A B C D), or the arrows + Z X C V. Build ' + ver + ' (' + sha.slice(0, 12) + '), arcade.')),
        cv,
        h('div', { class: 'row' }, bPlay,
          h('button', { onclick: () => { if (T && T.R) { T.R.load(T.state); T.script = null; T.t0 = performance.now(); start(); } } }, 'Restart'),
          h('button', { onclick: () => { if (T && T.R) { T.R.load(T.state); T.script = expand(r.scenario.do_keys, r.scenario.proof); start(); } } }, 'Show expected'),
          h('button', { onclick: verdict('up') }, '👍 Fixed'), h('button', { onclick: verdict('down') }, '👎 Broken'),
          queue && n + 1 < queue.length ? h('button', { onclick: () => { stopTest(false); testIt(queue[n + 1], queue); } }, 'Next') : null),
        st)));
    const ctx = cv.getContext('2d');
    let im = null;
    const draw = () => { const p = T.R.rgba(im && im.data); if (cv.width !== p.w) { cv.width = p.w; cv.height = p.h; } if (!im || im.width !== p.w) im = new ImageData(p.data, p.w, p.h); ctx.putImageData(im, 0, 0); };
    const expand = (s, proof) => { const out = []; for (const part of (s || '').split(',').filter(Boolean)) { const [k, v] = part.split(':'); for (let i = 0; i < +k; i++) out.push(v.replace('-', '')); }
      for (let i = 0; i < (proof || 90); i++) out.push(''); return out; };
    let ac = null, at = 0;
    const sound = a => {
      if (!a || !a.length) return;
      if (!ac) { try { ac = new AudioContext({ sampleRate: Math.round(T.R.rate) }); } catch (e) { ac = new AudioContext(); } }
      const k = a.length / 2, bf = ac.createBuffer(2, k, T.R.rate), L = bf.getChannelData(0), Rt = bf.getChannelData(1);
      for (let i = 0; i < k; i++) { L[i] = a[2 * i] / 32768; Rt[i] = a[2 * i + 1] / 32768; }
      const src = ac.createBufferSource(); src.buffer = bf; src.connect(ac.destination); at = Math.max(at, ac.currentTime + 0.05); src.start(at); at += k / T.R.rate;
    };
    const frame = () => {
      const c = T.R.core; const keys = T.script ? (T.script.length ? T.script.shift() : '') : [...held].join('');
      if (T.script && !T.script.length) T.script = null;
      c._wc_pad(0, bits(keys)); c._wc_pad(1, 0); c._wc_run();
      const k = c._wc_audio_n(), a = c._wc_audio() >> 1; sound(c.HEAP16.slice(a, a + 2 * k));
    };
    let accT = 0, lastT = 0;
    function tick(t) {
      if (!playing || !T) return;
      accT += (t - lastT) / 1000 * T.R.fps; lastT = t;
      let k = 0; while (accT >= 1 && k < 4) { frame(); accT -= 1; k++; }
      if (accT > 4) accT = 0;
      draw(); raf = requestAnimationFrame(tick);
    }
    const start = () => { stopLoop(); playing = true; bPlay.textContent = 'Pause'; st.textContent = T && T.script ? 'Showing the expected result with the recipe\'s own inputs…' : 'Playing: do it, then 👍 or 👎.'; lastT = performance.now(); accT = 0; at = 0; raf = requestAnimationFrame(tick); cv.focus(); };
    bPlay.onclick = () => { if (!T || !T.R) return; if (playing) { stopLoop(); bPlay.textContent = '▶ Play'; } else start(); };
    T = { r, sha, ver, t0: performance.now(), loaded: false, script: null };
    try {
      if (!sha) throw new Error('no state for the arcade system yet');
      const [state, rom] = await Promise.all([get(API + 'scenario/' + r.id + '/' + sha + '/mvs-mvs.state', 'test state'), roms[sha] ? null : get(API + 'rom/' + sha, 'game build ' + ver)]);
      if (!bios) bios = await get('neogeo.zip', 'BIOS');
      if (rom) roms[sha] = rom;
      const ck = sha + ':off';
      const fake = { inputs: new Uint8Array([78, 83, 73, 78, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]), snaps: {}, press: state };
      if (!cores[ck]) cores[ck] = (await FeedbackReplay.create(window.GeoCore, { bios, rom: roms[sha], systype: 'mvs', hw: 'mvs', memcard: 'off' }, fake)).core;
      if (!T || T.r !== r) return;
      T.R = new FeedbackReplay(cores[ck], fake); T.state = state; T.R.load(state); T.loaded = true; T.t0 = performance.now();
      frame(); draw();
      st.textContent = 'Paused at the scenario\'s first frame: press Play (or Show expected).';
    } catch (e) { st.textContent = 'Test unavailable: ' + e.message; }
  }

  const tab = $('tabFeedback');
  if (tab) tab.onclick = () => window.labTab('feedback');
  window.addEventListener('labtab', e => { if (e.detail === 'feedback') load(); });
  // a link to one note's replay: brawler-lab/#fb=<id> (#fb=<id>&play starts it)
  const m = /#fb=([0-9a-f-]+)(&play)?/.exec(location.hash);
  if (m) {
    window.labTab('feedback'); await load();
    const r = rows.find(x => x.id === m[1]);
    if (r) openReplay(Object.assign({}, r, { autoplay: !!m[2] }));
  }
})();
