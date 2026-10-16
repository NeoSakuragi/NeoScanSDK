/* Brawler Lab, Sessions tab (game.html #sessions; docs/feedback.md "Session recording", Player 0.0.41, keyframes 0.0.43): every tester's
 * recorded play sessions, one row each (player, build, date, length, ● LIVE when a chunk arrived in the last 15 s);
 * a tap opens the player: the session replayed in the wasm core (sessreplay.js on fbreplay.js, the build of that
 * session from feedback-api/rom/<sha> + the Lab's BIOS, as the Feedback tab), seek bar, play / pause, speed x1 / x2 / x4
 * (sound at x1). A seek starts from the nearest keyframe (a chunk with the full state, every ~30 s) at or before the
 * target and plays the inputs silently up to it. A live session starts at its latest keyframe, fast-forwards silently to
 * its newest chunk and plays the chunks as they arrive (polled every 1 s: ~2-3 s behind with the 2 s chunks of app 0.0.44, ~5-7 s with the older 5 s ones). At every chunk boundary the
 * replay's state SHA-256 is compared with the recorded one (the line under the picture: "N chunk boundaries checked:
 * all identical"; a difference or a missing chunk is shown, the replay resyncs at the next keyframe). Link: brawler-lab/game.html#sessions
 * (#sess=<id> opens one; ?user=NAME: that player's sessions only). API: feedback-api/sessions, session/<id>[?after=], session/<id>/inputs[?from=],
 * session/<id>/state/<seq> (tools/feedback/server.py sessions_api). */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  while (!window.labTab) await new Promise(r => setTimeout(r, 100));
  const API = 'feedback-api/';
  const col = $('sesscol'); if (!col) return;
  const css = document.createElement('style');
  css.textContent = `
#sesscol { padding: 12px 16px; min-width: 0; grid-column: 1 / -1; max-width: 900px; }
#sesscol h2 { font-size: 18px; margin: 4px 0 6px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
#sesscol .small { font-size: 13px; }
#sesscol table { border-collapse: collapse; width: 100%; font-size: 14px; }
#sesscol td, #sesscol th { border: 1px solid #000; padding: 6px; text-align: left; white-space: nowrap; }
#sesscol tr.srow { cursor: pointer; }
#sesscol tr.srow:active, #sesscol tr.srow.on { outline: 3px solid #000; }
#sesscol td.slive { font-weight: 700; }
#sesscol .box { border: 2px solid #000; margin: 10px 0; padding: 8px; background: #fff; color: #000; }
#sesscol canvas { display: block; width: 608px; max-width: 100%; image-rendering: pixelated; border: 2px solid #000; background: #000; }
#sesscol .ctl { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 6px 0; }
#sesscol .ctl button { min-height: 40px; min-width: 64px; font-size: 15px; }
#sesscol .ctl button.on { outline: 3px solid #000; font-weight: 700; }
#sesscol input[type=range] { width: 100%; height: 32px; }
#sesscol .mono { font-family: ui-monospace, monospace; font-size: 13px; }
#sesscol h3.sect { font-size: 14px; letter-spacing: .08em; margin: 14px 0 4px; border-bottom: 3px solid #000; }
@media (max-width: 600px) { #sesscol td.dev, #sesscol th.dev, #sesscol td.wide, #sesscol th.wide { display: none; } #sesscol td, #sesscol th { white-space: normal; } }`;
  document.head.append(css);

  const fps = 59.185606;
  const mmss = f => { const s = Math.floor(f / fps); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
  const when = iso => { try { const d = new Date(iso); return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) + ' ' + d.toTimeString().slice(0, 5); } catch (e) { return iso; } };
  const get = async (url, what) => { const r = await fetch(url, { credentials: 'same-origin', cache: 'no-store' }); if (!r.ok) throw new Error(what + ': HTTP ' + r.status); return new Uint8Array(await r.arrayBuffer()); };
  const json = async url => { const r = await fetch(url, { credentials: 'same-origin', cache: 'no-store' }); if (!r.ok) throw new Error(url + ': HTTP ' + r.status); return r.json(); };
  const cores = window.labCores = window.labCores || {}, roms = window.labRoms = window.labRoms || {};   // shared with feedback.js

  const head = h('h2', {}, 'Play sessions', h('button', { onclick: () => list() }, 'Refresh'));
  const info = h('p', { class: 'small' }, '');
  const pbox = h('div'), tbox = h('div');
  col.append(head, info, pbox, tbox);
  let rows = [], open = null, listTimer = 0;
  // ?user=NAME (the Factory's Players tab links here): that player's sessions only
  const UQ = new URLSearchParams(location.search).get('user');
  if (UQ) head.append(h('a', { href: location.pathname + location.hash.replace(/^#sess=.*/, '#sessions') }, 'Show every player'));

  async function list() {
    let j;
    try { j = await json(API + 'sessions' + (UQ ? '?user=' + encodeURIComponent(UQ) : '')); } catch (e) { info.textContent = 'Sessions unavailable: ' + e.message; return; }
    rows = j.sessions;
    const st = j.storage;
    info.textContent = (UQ ? UQ + ' only: ' : '') + `${rows.length} sessions, ${st.hours.toFixed(1)} h recorded, ${(st.bytes / 1e6).toFixed(1)} MB` +
      (st.mb_per_hour ? ` (${st.mb_per_hour} MB per hour of play)` : '') + '. Tap a row to watch it.';
    tbox.textContent = '';
    // two sections (Bruno 2026-10-16): LIVE NOW, then the past sessions; the character / screen / stage / life / drive
    // read from each session's latest keyframe (sessinfo.js; "(25 s)" = how old that keyframe is at the session's end)
    const liveRows = rows.filter(r => r.live), past = rows.filter(r => !r.live);
    const cells = r => {
      const c = { chars: h('td', {}, '…'), where: h('td', { class: 'wide' }, '…'), vitals: h('td', { class: 'wide' }, '…') };
      const put = v => { if (!window.SessInfo) return; const k = SessInfo.cols(v && v.info);
        c.chars.textContent = k.chars; c.vitals.textContent = k.vitals;
        c.where.textContent = k.where + (v && v.age !== null && k.where !== '—' ? ` (${v.age} s)` : ''); };
      if (window.SessInfo) { const q = SessInfo.forRow(r, API); if (q.now) put(q.now); q.next.then(put, () => put(null)); }
      return c;
    };
    const row = (r, isLive) => { const c = cells(r); return h('tr', { class: 'srow' + (open && open.id === r.id ? ' on' : ''), onclick: () => watch(r) },
      isLive ? h('td', { class: 'slive' }, '● LIVE') : null, h('td', {}, r.user), h('td', { class: 'wide' }, r.rom_version + (r.system !== 'mvs-mvs' ? ' (' + r.system + ')' : '')),
      c.chars, c.where, c.vitals, isLive ? null : h('td', {}, when(r.started) + (r.paused && r.last_ago < 60 ? ' (paused)' : '')), h('td', {}, mmss(r.frames)), h('td', { class: 'dev' }, r.device)); };
    const th = isLive => h('tr', {}, isLive ? h('th', {}, '') : null, h('th', {}, 'Player'), h('th', { class: 'wide' }, 'Build'), h('th', {}, 'Character'), h('th', { class: 'wide' }, 'Screen'),
      h('th', { class: 'wide' }, 'Life · drive'), isLive ? null : h('th', {}, 'Started'), h('th', {}, isLive ? 'So far' : 'Length'), h('th', { class: 'dev' }, 'Device'));
    tbox.append(h('h3', { class: 'sect' }, `LIVE NOW (${liveRows.length})`),
      liveRows.length ? h('table', {}, th(true), liveRows.map(r => row(r, true))) : h('p', { class: 'small' }, 'Nobody is playing right now.'),
      h('h3', { class: 'sect' }, 'Past sessions'), h('table', {}, th(false), past.map(r => row(r, false))));
  }

  // ---- the player ---------------------------------------------------------------------------------------------------
  let S = null, raf = 0, playing = false, speed = 1, acc = 0, last = 0, ac = null, at = 0, img = null, poll = 0, live = false, busy = false, waiting = false;
  function stop() { playing = false; cancelAnimationFrame(raf); }
  function close() { stop(); clearInterval(poll); open = null; S = null; pbox.textContent = ''; }

  async function watch(r) {
    close(); open = r; list();
    const cv = h('canvas', { width: 304, height: 224 });
    const st = h('p', { class: 'mono' }, 'Loading the session and its build (12 MB the first time)…');
    const chk = h('p', { class: 'mono' }, ''), inf = h('p', { class: 'mono' }, '');   // inf: sessinfo.js, every frame from the core
    const pos = h('span', { class: 'mono' }, '');
    const seek = h('input', { type: 'range', min: 0, max: 0, value: 0, step: 1 });
    const bPlay = h('button', { onclick: () => toggle() }, '▶ Play');
    const bLive = h('button', { onclick: () => goLive() }, '● LIVE');
    const sp = [1, 2, 4].map(x => h('button', { class: x === 1 ? 'on' : '', onclick: e => { speed = x; sp.forEach(b => b.classList.toggle('on', b === e.target)); } }, '×' + x));
    pbox.append(h('div', { class: 'box' },
      h('h2', {}, `${r.user} — ${r.rom_version} — ${when(r.started)}`, h('span', { style: 'flex:1' }), h('button', { onclick: close }, 'Close')),
      h('p', { class: 'small' }, `${r.device} · Android ${r.android} · app ${r.app_version} · ${r.system} · session ${r.id}`),
      cv, inf, seek, h('div', { class: 'ctl' }, bPlay, ...sp, bLive, pos), st, chk));
    if (window.SessInfo) SessInfo.syms(r.rom_sha);
    const ctx = cv.getContext('2d');
    const draw = () => {
      if (!S) return;
      const p = S.R.rgba(img && img.data); if (cv.width !== p.w) { cv.width = p.w; cv.height = p.h; }
      if (!img || img.width !== p.w) img = new ImageData(p.data, p.w, p.h); ctx.putImageData(img, 0, 0);
      seek.max = S.total; if (!busy) seek.value = S.pos;
      const lag = live && S.chunks.length ? ` · ${((S.total - S.pos) / fps).toFixed(1)} s behind the last chunk` : '';
      pos.textContent = `${mmss(S.pos)} / ${mmss(S.total)}${live ? ' · LIVE' : ''}${lag}${waiting ? ' · waiting for the next chunk' : ''}`;
      const ck = S.checked ? (S.mismatches.length ? `${S.checked} chunk boundaries checked (state SHA-256): DIFFERENT from the recording at chunk ${S.mismatches.slice(0, 8).join(', ')}`
        : `${S.checked} chunk boundaries checked (state SHA-256): all identical to the recording`) : '';
      const gp = S.gaps.length ? ` · missing chunks before ${S.gaps.slice(0, 8).join(', ')}` : '';
      const rs = S.resyncs.length ? ` · resynced at keyframe ${S.resyncs.slice(0, 8).join(', ')}` : '';
      chk.textContent = ck + gp + rs + (S.drift ? ' · drifting: resync at the next keyframe' : '');
      if (window.SessInfo) inf.textContent = SessInfo.text(SessInfo.fromCore(S.R.core, SessInfo.symsNow.get(r.rom_sha) || null));
    };
    const sound = a => {
      if (!a || !a.length || speed !== 1) return;
      if (!ac) { try { ac = new AudioContext({ sampleRate: Math.round(S.R.rate) }); } catch (e) { ac = new AudioContext(); } }
      const n = a.length / 2, b = ac.createBuffer(2, n, S.R.rate), L = b.getChannelData(0), R = b.getChannelData(1);
      for (let i = 0; i < n; i++) { L[i] = a[2 * i] / 32768; R[i] = a[2 * i + 1] / 32768; }
      const src = ac.createBufferSource(); src.buffer = b; src.connect(ac.destination);
      at = Math.max(at, ac.currentTime + 0.05); src.start(at); at += n / S.R.rate;
    };
    function tick(t) {
      if (!playing || !S) return;
      acc += (t - last) / 1000 * fps * speed; last = t;
      let n = 0; waiting = false;
      while (acc >= 1 && n < 4 * speed) {
        const a = S.step();
        if (a === null) {                                  // the end of what arrived, or the next state is loading
          acc = 0; waiting = true;
          S.ready().then(ok => { if (!ok && !live) { stop(); bPlay.textContent = '▶ Play'; draw(); } });
          break;
        }
        sound(a); acc -= 1; n++;
      }
      if (acc > 4 * speed) acc = 0;
      draw(); raf = requestAnimationFrame(tick);
    }
    const play = () => { if (!S || playing) return; playing = true; bPlay.textContent = '❚❚ Pause'; last = performance.now(); acc = 0; at = 0; raf = requestAnimationFrame(tick); };
    function toggle() { if (!S) return; if (playing) { stop(); bPlay.textContent = '▶ Play'; } else play(); }
    async function jump(g) { if (!S) return; busy = true; const was = playing; stop(); try { await S.seek(g); } catch (e) { st.textContent = e.message; } busy = false; draw(); if (was) play(); }
    seek.oninput = () => { busy = true; pos.textContent = mmss(+seek.value) + ' / ' + mmss(S ? S.total : 0); };
    seek.onchange = () => { live = false; bLive.classList.remove('on'); jump(+seek.value); };
    async function more() {                                  // the chunks that arrived since (a live session)
      if (!S || open !== r) return;
      const top = S.chunks.length ? S.chunks[S.chunks.length - 1].seq : -1;
      try {
        const j = await json(API + 'session/' + r.id + '?after=' + top);
        if (j.chunks.length) { S.addMeta(j.chunks); S.addInputs(await get(API + 'session/' + r.id + '/inputs?from=' + j.chunks[0].seq, 'inputs')); }
        r.live = j.session.live;
        bLive.disabled = !r.live; if (!r.live && live) { live = false; bLive.classList.remove('on'); }
        if (!playing) draw();
      } catch (e) { /* the next poll */ }
    }
    async function goLive() {                                // the latest keyframe, silently on to the newest chunk, then play as they arrive
      if (!S) return;
      await more();
      stop(); live = true; bLive.classList.add('on'); speed = 1; sp.forEach((b, i) => b.classList.toggle('on', i === 0));
      await jump(S.cum[S.chunks.length - 1]);
      for (let n = 0; n < 3 && S.chunks.length; n++) {      // chunks that arrived during the fast-forward: silently on to the newest
        await more(); const g = S.cum[S.chunks.length - 1]; if (S.pos >= g) break;
        busy = true; while (S.pos < g) { if (S.step() === null && !(await S.ready())) break; } busy = false;
      }
      play();
    }
    try {
      const [meta, inputs] = await Promise.all([json(API + 'session/' + r.id), get(API + 'session/' + r.id + '/inputs', 'inputs')]);
      if (!roms[r.rom_sha]) roms[r.rom_sha] = await get(API + 'rom/' + r.rom_sha, 'game build ' + r.rom_version);
      if (!window.labBios) window.labBios = await get('neogeo.zip', 'BIOS');
      if (open !== r) return;
      const [systype, hw] = (r.system || 'mvs-mvs').split('-');
      const ck = r.rom_sha + ':' + (r.memcard || 'off');
      if (!cores[ck]) cores[ck] = (await FeedbackReplay.create(window.GeoCore, { bios: window.labBios, rom: roms[r.rom_sha], systype, hw, memcard: r.memcard || 'off' }, { snaps: {} })).core;
      const R = new FeedbackReplay(cores[ck], { snaps: {} });
      S = new SessionReplay(R, async seq => get(API + 'session/' + r.id + '/state/' + seq, 'state ' + seq));
      S.addMeta(meta.chunks); S.addInputs(inputs);
      if (!S.chunks.length) throw new Error('no chunk yet');
      st.textContent = `${S.chunks.length} chunks (${S.keys} keyframes), ${mmss(S.total)} of play.` + (systype !== 'mvs' ? ' (A console session: the Lab has only the MVS BIOS, it may not replay.)' : '');
      bLive.disabled = !r.live;
      poll = setInterval(more, 1000);                      // 2 s chunks (app 0.0.44): ~2-3 s behind
      if (r.live) await goLive(); else { await jump(0); draw(); }
    } catch (e) { st.textContent = 'Session unavailable: ' + e.message; }
  }

  window.labSess = { watch: r => watch(r), close: () => close(), list: () => list(), API };   // the live wall (wall.js): a tile at full size
  const tab = $('tabSessions');
  if (tab) tab.onclick = () => window.labTab('sessions');
  window.addEventListener('labtab', e => {
    clearInterval(listTimer);
    if (e.detail === 'sessions') { list(); listTimer = setInterval(() => { if (!document.hidden) list(); }, 5000); }
    else stop();
  });
  const m = /#sess=([0-9a-f]{8}-\d{8}-\d{6})/.exec(location.hash);
  if (m) { window.labTab('sessions'); await list(); const r = rows.find(x => x.id === m[1]); if (r) watch(r); }
})();
