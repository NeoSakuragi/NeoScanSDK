/* Brawler Lab, Feedback tab: the NeoScan Player's voice / text feedback (docs/feedback.md). The list comes from the
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
  const STATUS_TEXT = { new: 'NEW', read: 'read', in_progress: 'IN PROGRESS', shipped: 'SHIPPED', wont_do: "won't do", duplicate: 'duplicate', verified: 'VERIFIED', reopened: 'REOPENED' };
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

  async function load() {
    try {
      const r = await fetch(API + 'list', { cache: 'no-store', credentials: 'same-origin' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json(); rows = j.rows; cats = j.categories; cost = j.cost; msg = '';
    } catch (e) { msg = 'The feedback list is unavailable (' + e.message + ').'; }
    render();
  }

  async function set(id, body) {
    try {
      const r = await fetch(API + 'set', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                                           body: JSON.stringify(Object.assign({ id }, body)) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      rows = rows.map(x => x.id === id ? j.row : x); msg = 'Saved ' + id + '.';
    } catch (e) { msg = 'Not saved: ' + e.message; }
    render();
  }

  function play(btn, r) {
    const old = btn.parentNode.querySelector('audio');
    if (old) { old.remove(); btn.textContent = '▶ Play'; return; }
    const a = h('audio', { controls: true, src: API + 'file/' + r.id + '/' + r.audio_path, preload: 'auto' });
    btn.after(a); btn.textContent = '■ Close'; a.play().catch(() => {});
  }

  function render() {
    if (!col) return;
    lbox.textContent = '';
    const sel = (key, opts) => h('select', { onchange: e => { filt[key] = e.target.value; render(); } },
      h('option', { value: '' }, 'all'), opts.map(o => h('option', { value: o, selected: filt[key] === o }, key === 'status' ? STATUS_TEXT[o] : o)));
    rows.sort((a, b) => (b.status === 'reopened') - (a.status === 'reopened'));   // reopened first
    const shown = rows.filter(r => (!filt.status || r.status === filt.status) && (!filt.category || r.category === filt.category));
    lbox.append(h('div', { class: 'box' },
      h('h2', {}, 'Feedback from the player', h('span', { class: 'sp' }),
        h('label', {}, 'Status ', sel('status', Object.keys(STATUS_TEXT))), h('label', {}, 'Category ', sel('category', cats)),
        h('button', { onclick: load }, 'Reload')),
      h('div', { class: 'in' },
        msg ? h('p', { class: 'ok' }, msg) : null,
        cost ? h('p', { class: 'note' }, `Transcription cost: $${cost.usd.toFixed(4)} in all (${cost.transcriptions} transcriptions, ${Math.round(cost.audio_seconds)} s of audio; $${cost.usd_in_notes.toFixed(4)} in sent notes, the rest cancelled). Prices: ${cost.prices.source}, checked ${cost.prices.checked}.`) : null,
        h('p', { class: 'note' }, `${shown.length} of ${rows.length}. Status: NEW → read (pulled) → IN PROGRESS → SHIPPED (release) | won't do | duplicate; set with tools/feedback/fb.py. The player's 👍 = VERIFIED, 👎 = REOPENED (his thread under the note).`),
        h('table', { class: 'fb' },
          h('tr', {}, ['When / id', 'Versions', 'Note', 'Status', 'Category / fighters', 'Replay / voice / picture', 'Cost'].map(t => h('th', {}, t))),
          shown.map(r => h('tr', {},
            h('td', { class: 'mono' }, r.created.slice(0, 16).replace('T', ' '), h('br'), r.id),
            h('td', {}, r.user ? h('b', {}, r.user) : h('span', { class: 'small' }, '(before the login)'), h('br'), 'player ' + r.apk_version, h('br'), 'game v' + r.game_version, h('br'),
              h('span', { class: 'small' }, (r.device || '?') + (r.android ? ', Android ' + r.android : '')), h('br'),
              h('span', { class: 'small mono', title: 'install id / client IP as nginx saw it / user agent (internal: behind the Lab login)' },
                'install ' + (r.install_id || '-').slice(0, 8) + ', IP ' + (r.ip || '-'), h('br'), r.user_agent || '')),
            h('td', { class: 'txt' }, r.title ? h('div', { style: 'font-weight:bold;font-size:1.05em;margin-bottom:4px' }, r.title) : null,
              h('div', {}, r.final_text || '(no text typed)'),
              r.raw_transcript && !(r.final_text || '').includes(r.raw_transcript) ? h('div', { class: 'small' }, 'transcript: ' + r.raw_transcript) : null,
              r.notes ? h('div', { class: 'small' }, 'notes: ' + r.notes) : null, thread(r)),
            h('td', {}, h('b', {}, STATUS_TEXT[r.status] || r.status), r.status === 'shipped' ? h('div', {}, 'in ' + r.release) : null,
              r.status === 'duplicate' ? h('div', { class: 'small' }, 'of ' + r.duplicate_of) : null),
            h('td', {},
              h('select', { onchange: e => set(r.id, { category: e.target.value }) },
                h('option', { value: '' }, '(none)'), cats.map(c => h('option', { value: c, selected: r.category === c }, c))),
              h('br'),
              h('input', { type: 'text', value: r.fighters, placeholder: 'fighters: geese,terry', size: 16,
                           onchange: e => set(r.id, { fighters: e.target.value }) })),
            h('td', {},
              h('button', { onclick: () => { openReplay(r); col.scrollIntoView({ behavior: 'smooth' }); } }, 'Replay'), h('br'),
              r.audio_path ? h('button', { onclick: e => play(e.target, r) }, '▶ Voice') : h('span', { class: 'small' }, 'no voice'),
              h('br'), r.marked
                ? h('a', { href: API + 'file/' + r.id + '/screen_marked.png', target: '_blank' },
                    h('img', { src: API + 'file/' + r.id + '/screen_marked.png', alt: 'marked screenshot', loading: 'lazy', style: 'width:152px;display:block;border:1px solid #000' }), 'marked screenshot')
                : h('a', { href: API + 'file/' + r.id + '/screen.png', target: '_blank' }, 'screenshot'),
              r.marked ? h('a', { href: API + 'file/' + r.id + '/screen.png', target: '_blank', class: 'small' }, ' (clean)') : null),
            h('td', { class: 'mono' }, r.cost_usd == null ? '-' : '$' + r.cost_usd.toFixed(4), (r.cost_source || '').includes('duration') ? h('div', { class: 'small' }, 'estimated') : null)))))));
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
