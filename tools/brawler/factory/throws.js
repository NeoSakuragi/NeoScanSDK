// The Brawler Factory's THROWS tab (?tab=throws[&t=<row id>]; the throw editor, 2026-10-16): every playable fighter's
// throws (forward, back, hold + B, the run grab) as game.json roster[].throws.events (docs/brawler_data_model.md "THE THROW
// EVENTS": 1-3 impacts {frame, damage share %}, held, launch {frame, dir up | away | back | none, size}; frame 1 = the throw's
// first frame). One row per fighter x throw with its events; tap = the throw's frames (the throw review's captures:
// /brawler-lab/review/throws2/, tools/brawler/throw_review.py) with the marks editable: impacts added / moved / removed
// with their share, held, launch frame + direction + size. Checked as build_tables does (throw_events / event_impacts,
// + the throw's length) before Save. Save = the "throws" draft section (feedback-api/lab/throws {throws: {row id:
// events}}: only the throws that differ from the game); "Ship throws to testers" = ship_batch {throws: true}: the ship
// service runs tools/brawler/throwcfg.py merge (the same checks against the game), builds, throw_regress.py ALL OK,
// publishes. The game's side (what the build plays): lab/throws "game" = throwcfg.py state, posted after each ship.
// factory.js: FactoryThrows.poll(lab/throws, ship rows, shown), .draw(), .pending().
(function () {
  'use strict';
  const LAB = 'feedback-api/lab/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v != null && v !== false) e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const P = document.getElementById('pThrows');
  const FX = ['spark', 'sound', 'shake'];
  const DIRS = [['up', 'UP ↑'], ['away', 'AWAY →'], ['back', 'BACK ←'], ['none', 'NONE ·']];
  const SIZES = [['small', 'S'], ['medium', 'M'], ['big', 'B']];
  const ARROW = { up: '↑', away: '→', back: '←', none: '·' };
  document.head.append(h('style', { text: `
#pThrows { color: #000; }
#pThrows .tcard { background: #fff; border: 2px solid #000; border-radius: 0; padding: 6px 8px; }
#pThrows h2 { color: #000; }
#pThrows button { color: #000; background: #fff; border: 2px solid #000; border-radius: 0; padding: 3px 8px; }
#pThrows button.primary { background: #000; color: #fff; }
#pThrows button[aria-pressed="true"] { background: #000; color: #fff; }
#pThrows button:disabled { opacity: .45; }
#pThrows .tag { border: 1px solid #000; background: #fff; color: #000; border-radius: 0; }
#pThrows .tag.edit { border-style: dashed; } #pThrows .tag.ship { background: #000; color: #fff; }
#pThrows .trw { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 0 8px; width: 100%; text-align: left; border: 0; border-top: 1px solid #000; padding: 6px 2px; }
#pThrows .trw:first-child { border-top: 0; }
#pThrows .trw[aria-expanded="true"] { border-bottom: 2px dashed #000; }
#pThrows .trw b { font-size: 14px; }
#pThrows .trw .ev { font: 12px ui-monospace, monospace; white-space: nowrap; }
#pThrows .trw .sub { grid-column: 1 / -1; font-size: 11.5px; }
#pThrows .ted { display: flex; flex-direction: column; gap: 6px; padding: 6px 0 10px; }
#pThrows canvas { display: block; width: 100%; max-width: 456px; height: auto; image-rendering: pixelated; border: 2px solid #000; background: #fff; }
#pThrows .fl { font: 12px ui-monospace, monospace; min-height: 1.4em; }
#pThrows .ctl { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
#pThrows input[type=range] { width: 100%; margin: 0; accent-color: #000; }
#pThrows .strip { display: flex; gap: 2px; overflow-x: auto; padding-bottom: 3px; }
#pThrows .strip button { flex: 0 0 auto; padding: 0; border: 1px solid #000; display: flex; flex-direction: column; align-items: center; }
#pThrows .strip button[aria-current="true"] { border: 3px solid #000; }
#pThrows .strip .th { display: block; width: 57px; height: 42px; background-repeat: no-repeat; image-rendering: pixelated; }
#pThrows .strip small { font: 10.5px ui-monospace, monospace; padding: 0 2px; white-space: nowrap; }
#pThrows .mk { display: flex; flex-wrap: wrap; gap: 3px 4px; align-items: center; border-top: 1px solid #000; padding-top: 4px; font-size: 13px; }
#pThrows .mk > b { min-width: 4.8em; }
#pThrows .mk .n { font: 700 14px ui-monospace, monospace; min-width: 2.2em; text-align: center; }
#pThrows .mk input[type=number] { width: 3.2em; font: inherit; border: 2px solid #000; border-radius: 0; padding: 2px; }
#pThrows .mk button { padding: 2px 7px; }
#pThrows .errs { margin: 0; padding: 4px 8px; border: 2px solid #000; font-size: 13px; font-weight: 700; list-style: none; }
#pThrows .errs li::before { content: "✗ "; }
#pThrows .ok { font-size: 13px; }
#pThrows .msg, #pThrows .msg.bad { color: #000; }
#pThrows .msg.bad { font-weight: 700; }` }));

  let D = {}, rows = [], IX = null, ixTried = false, open = null, msg = h('span', { class: 'msg', role: 'status', 'aria-live': 'polite' });
  const Q = new URLSearchParams(location.search);
  let want0 = Q.get('t');
  const G = () => D.game || null;
  const draftT = () => (D.draft && D.draft.throws) || {};
  const openShip = () => rows.find(r => r.throws && (r.status === 'pending' || r.status === 'building'));
  const capOf = id => IX && IX.rows.find(r => r.id === id) || null;

  // the events as the engine reads them (build_tables event_impacts / throw_events): for comparing
  function norm(e) {
    if (!e || !e.launch) return null;
    const I = e.impacts || (e.impact ? [{ frame: e.impact }] : []);
    return JSON.stringify({ i: I.map((x, k) => [x.frame, k + 1 < I.length ? (x.damage || 0) : -1, ...FX.map(f => x[f] !== false)]),
      h: e.held != null ? e.held : e.launch.frame, l: [e.launch.frame, e.launch.dir, e.launch.size || 'medium'] });
  }
  const gameEv = id => { const r = G() && G().rows.find(x => x.id === id); return r ? r.events : null; };
  const wantEv = id => draftT()[id] || gameEv(id);
  const differs = id => id in draftT() && norm(draftT()[id]) !== norm(gameEv(id));
  const evTxt = e => !e ? 'engine rule' : 'I' + (e.impacts || []).map((x, k, a) => x.frame + (k + 1 < a.length && x.damage ? '(' + x.damage + '%)' : '')).join('+') +
    (e.held != null && e.held !== e.launch.frame ? ' H' + e.held : '') + ' L' + e.launch.frame + (ARROW[e.launch.dir] || '?') + ((e.launch.size || 'medium')[0]);

  // the checks of build_tables throw_events / event_impacts, + the throw's length (throwcfg.py merge)
  function problems(E, top) {
    const out = [], I = E.impacts, inT = x => Number.isInteger(x) && x >= 1 && x <= top;
    if (!I.length) out.push('at least one impact');
    if (I.length > 3) out.push('3 impacts at most');
    I.forEach((x, k) => { if (!inT(x.frame)) out.push(`impact ${k + 1}: frame ${x.frame} is outside the throw (frames 1-${top})`);
      if (k && x.frame <= I[k - 1].frame) out.push(`impact ${k + 1}: frame ${x.frame} must come after impact ${k} (frame ${I[k - 1].frame})`);
      if (k + 1 < I.length && !(Number.isInteger(x.damage || 0) && (x.damage || 0) >= 0 && (x.damage || 0) <= 100)) out.push(`impact ${k + 1}: share 0-100 %`); });
    const tot = I.slice(0, -1).reduce((s, x) => s + (x.damage || 0), 0);
    if (tot > 100) out.push(`the shares before the last impact add up to ${tot} % (100 at most)`);
    const L = E.launch;
    if (!L || !L.frame) out.push('a launch frame');
    else {
      if (!inT(L.frame)) out.push(`launch: frame ${L.frame} is outside the throw (frames 1-${top})`);
      if (!L.dir) out.push('a launch direction (up, away, back or none)');
      if (I.length && I[I.length - 1].frame > L.frame) out.push(`impact frame ${I[I.length - 1].frame} is after the launch (frame ${L.frame})`);
      if (E.held != null) { if (!inT(E.held)) out.push(`held: frame ${E.held} is outside the throw`); else if (E.held > L.frame) out.push(`held ${E.held} is after the launch (frame ${L.frame})`); }
    }
    return out;
  }
  const clean = E => ({ impacts: E.impacts.map((x, k) => Object.assign({ frame: x.frame }, k + 1 < E.impacts.length && x.damage ? { damage: x.damage } : {},
      ...FX.filter(f => x[f] === false).map(f => ({ [f]: false })))),
    ...(E.held != null ? { held: E.held } : {}), launch: Object.assign({ frame: E.launch.frame, dir: E.launch.dir }, E.launch.size ? { size: E.launch.size } : {}) });

  async function saveDraft(T, what) {
    msg.className = 'msg'; msg.textContent = 'Saving…';
    try {
      const r = await fetch(LAB + 'throws', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ throws: T }) });
      const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      D = j; msg.textContent = what + ': saved to the draft (rev ' + D.draft.rev + '). "Ship throws to testers" builds it.';
      return true;
    } catch (e) { msg.className = 'msg bad'; msg.textContent = 'Not saved: ' + e.message; return false; }
  }
  async function ship(btn) {
    btn.disabled = true; msg.className = 'msg'; msg.textContent = 'Queuing the throws…';
    try {
      const r = await fetch(LAB + 'ship_batch', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ throws: true, note: 'Ship throws (the Factory\'s Throws tab)' }) });
      const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      rows = rows.concat([j.ship]);
      msg.textContent = `Queued #${j.ship.id}. The Build tab shows it; testers get the new build once the Players tab gives it to them.`;
    } catch (e) { msg.className = 'msg bad'; msg.textContent = 'Not queued: ' + e.message; }
    draw();
  }

  // ---- one throw's editor ----
  function editor(row) {
    const cap = capOf(row.id), top = row.frames || 400, nf = cap ? cap.frames : Math.min(top, 120);
    const src = wantEv(row.id);
    const E = src ? { impacts: (src.impacts || [{ frame: src.impact }]).map(x => Object.assign({}, x)), held: src.held != null ? src.held : null, launch: Object.assign({}, src.launch) }
      : { impacts: [], held: null, launch: { frame: null, dir: null } };
    const start = norm(clean(E));
    let k = E.impacts.length ? Math.min(nf - 1, E.impacts[0].frame - 1) : 0, playing = false, raf = 0, last = 0, acc = 0;
    const cv = h('canvas', { width: cap ? cap.w : 304, height: cap ? cap.h : 60, role: 'img', 'aria-label': row.display + ' ' + row.label + ': the throw frame by frame' });
    const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = false;
    const sheet = cap ? Object.assign(new Image(), { src: cap.sheet }) : null;
    const fl = h('div', { class: 'fl', 'aria-live': 'polite' });
    const slider = h('input', { type: 'range', min: '1', max: String(nf), value: String(k + 1), 'aria-label': 'Frame' });
    const marksAt = n => { const t = [];
      E.impacts.forEach((x, j) => { if (x.frame === n) t.push(E.impacts.length > 1 ? 'I' + (j + 1) : 'I'); });
      if (E.held != null && E.held === n) t.push('H');
      if (E.launch.frame === n) t.push('L' + (ARROW[E.launch.dir] || ''));
      return t.join(' '); };
    const strip = h('div', { class: 'strip', 'aria-label': 'Every frame: tap one' });
    function paintFrame() {
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, cv.width, cv.height);
      if (sheet && sheet.complete && sheet.naturalWidth) ctx.drawImage(sheet, (k % cap.cols) * cap.w, Math.floor(k / cap.cols) * cap.h, cap.w, cap.h, 0, 0, cap.w, cap.h);
      else if (!cap) { ctx.fillStyle = '#000'; ctx.font = '14px monospace'; ctx.fillText('No capture of this throw: frames by number', 8, 34); }
      const m = marksAt(k + 1);
      if (m) { ctx.font = 'bold 20px monospace'; const w = ctx.measureText(m).width + 12; ctx.fillStyle = '#fff'; ctx.fillRect(4, 4, w, 28);
        ctx.strokeStyle = '#000'; ctx.lineWidth = 3; ctx.strokeRect(4, 4, w, 28); ctx.fillStyle = '#000'; ctx.fillText(m, 10, 25); }
      if (addBtn) { addBtn.textContent = '+ Impact at frame ' + (k + 1); addBtn.disabled = E.impacts.length >= 3 || E.impacts.some(x => x.frame === k + 1); }
      fl.textContent = `frame ${k + 1} / ${nf}` + (row.frames ? ` (throw ${row.frames})` : '') + (m ? ' · ' + m : '');
      slider.max = String(nf); slider.value = String(k + 1);
      strip.querySelectorAll('button').forEach((b, j) => b.setAttribute('aria-current', String(j === k)));
      const cur = strip.children[k];
      if (cur && !playing) strip.scrollLeft = Math.max(0, cur.offsetLeft - strip.offsetLeft - strip.clientWidth / 2 + cur.offsetWidth / 2);
    }
    if (sheet) sheet.onload = paintFrame;
    if (cap) {
      const sc = 57 / cap.w;
      for (let j = 0; j < nf; j++) {
        const th = h('span', { class: 'th' });
        th.style.backgroundImage = `url(${cap.sheet})`; th.style.backgroundSize = `${cap.cols * cap.w * sc}px auto`;
        th.style.backgroundPosition = `-${(j % cap.cols) * cap.w * sc}px -${Math.floor(j / cap.cols) * cap.h * sc}px`;
        strip.append(h('button', { type: 'button', 'aria-label': 'Frame ' + (j + 1), onclick: () => { stop(); go(j); } }, th, h('small')));
      }
    }
    const retag = () => strip.querySelectorAll('small').forEach((s, j) => { s.textContent = [String(j + 1), marksAt(j + 1)].filter(Boolean).join(' '); });
    const go = j => { k = Math.max(0, Math.min(nf - 1, j)); paintFrame(); };
    slider.oninput = () => { stop(); go(+slider.value - 1); };
    const bPlay = h('button', { type: 'button', text: 'Play' });
    const tick = t => { if (!playing) return; acc += Math.min(250, t - last); last = t; const fms = 1000 / ((IX && IX.fps) || 59.18); let n = 0;
      while (acc >= fms) { acc -= fms; k = (k + 1) % nf; n++; } if (n) paintFrame(); raf = requestAnimationFrame(tick); };
    function stop() { playing = false; cancelAnimationFrame(raf); bPlay.textContent = 'Play'; }
    bPlay.onclick = () => { if (playing) { stop(); paintFrame(); return; } playing = true; acc = 0; last = performance.now(); bPlay.textContent = 'Pause'; raf = requestAnimationFrame(tick); };
    const step = d => h('button', { type: 'button', text: d < 0 ? '◀' + -d : d + '▶', 'aria-label': (d < 0 ? 'Back ' : 'Forward ') + Math.abs(d), onclick: () => { stop(); go(k + d); } });

    // the marks
    let addBtn = null;
    const marks = h('div', {}), errs = h('ul', { class: 'errs', role: 'alert' }), okEl = h('p', { class: 'ok' });
    const bSave = h('button', { type: 'button', class: 'primary', text: 'Save draft' });
    const changed = () => { paintMarks(); retag(); paintFrame(); };
    const num = (get, set, label) => [h('button', { type: 'button', text: '−', 'aria-label': label + ' one frame earlier', onclick: () => { if (get() > 1) { set(get() - 1); changed(); } } }),
      h('span', { class: 'n', text: get() == null ? '—' : String(get()) }),
      h('button', { type: 'button', text: '+', 'aria-label': label + ' one frame later', onclick: () => { set((get() || 0) + 1); changed(); } }),
      h('button', { type: 'button', text: 'here', 'aria-label': label + ' on the frame shown', onclick: () => { set(k + 1); changed(); } })];
    const sortI = () => E.impacts.sort((a, b) => a.frame - b.frame);
    function paintMarks() {
      const n = E.impacts.length;
      const tot = E.impacts.slice(0, -1).reduce((s, x) => s + (x.damage || 0), 0);
      marks.replaceChildren(...[
        E.impacts.map((x, j) => h('div', { class: 'mk', 'data-mark': 'impact' + (j + 1) }, h('b', { text: 'Impact ' + (n > 1 ? j + 1 : '') }),
          num(() => x.frame, v => { x.frame = v; sortI(); }, 'Impact ' + (j + 1)),
          j + 1 < n ? h('label', {}, 'share ', h('input', { type: 'number', min: '0', max: '100', step: '1', value: String(x.damage || 0), 'aria-label': 'Impact ' + (j + 1) + ' damage share %',
            onchange: e => { x.damage = Math.round(+e.target.value) || 0; changed(); } }), ' %') : h('span', { text: ' damage: ' + (100 - tot) + ' % (the rest)' }),
          h('button', { type: 'button', text: '✕', 'aria-label': 'Remove impact ' + (j + 1), onclick: () => { E.impacts.splice(j, 1); changed(); } }))),
        h('div', { class: 'mk' }, addBtn = h('button', { type: 'button', 'data-add': 'impact', onclick: () => { E.impacts.push({ frame: k + 1 }); sortI(); changed(); } }), n >= 3 ? h('span', { text: '3 at most' }) : null),
        h('div', { class: 'mk', 'data-mark': 'held' }, h('b', { text: 'Held until' }), num(() => E.held, v => { E.held = v; }, 'Held'),
          E.held != null ? h('button', { type: 'button', text: '✕', 'aria-label': 'Held: same as the launch', onclick: () => { E.held = null; changed(); } }) : h('span', { text: ' = the launch' })),
        h('div', { class: 'mk', 'data-mark': 'launch' }, h('b', { text: 'Launch' }), num(() => E.launch.frame, v => { E.launch.frame = v; }, 'Launch')),
        h('div', { class: 'mk' }, h('b', { text: 'Direction' }), DIRS.map(([d, t]) => h('button', { type: 'button', 'data-dir': d, 'aria-pressed': String(E.launch.dir === d), text: t, onclick: () => { E.launch.dir = d; changed(); } }))),
        h('div', { class: 'mk' }, h('b', { text: 'Size' }), SIZES.map(([z, t]) => h('button', { type: 'button', 'data-size': z, 'aria-label': z, 'aria-pressed': String((E.launch.size || 'medium') === z), text: t,
          onclick: () => { E.launch.size = z; changed(); } })))].flat());
      const pr = problems(E, top);
      errs.replaceChildren(...pr.map(t => h('li', { text: t }))); errs.hidden = !pr.length;
      const now = pr.length ? null : norm(clean(E));
      okEl.textContent = pr.length ? '' : now === start ? 'No change.' : now === norm(gameEv(row.id)) ? 'Same as the game.' : 'Checked: ' + evTxt(clean(E));
      bSave.disabled = !!pr.length || now === start;
    }
    bSave.onclick = async () => {
      const T = Object.assign({}, draftT()); const e = clean(E);
      if (norm(e) === norm(gameEv(row.id))) delete T[row.id]; else T[row.id] = e;
      if (await saveDraft(T, row.display + ' ' + row.label)) { open = null; draw(); }
    };
    const back = row.id in draftT() ? h('button', { type: 'button', text: 'Back to the game\'s', onclick: async () => {
      const T = Object.assign({}, draftT()); delete T[row.id]; if (await saveDraft(T, row.display + ' ' + row.label + ' back to the game\'s')) { open = null; draw(); } } }) : null;
    const ge = gameEv(row.id);
    paintMarks(); retag(); paintFrame();
    const el = h('div', { class: 'ted' },
      cv, fl, cap ? slider : null, h('div', { class: 'ctl' }, step(-10), step(-1), cap ? bPlay : null, step(1), step(10)), cap ? strip : null,
      h('p', { class: 'msg', text: 'In game ' + ((G() && G().version) || '?') + ': ' + evTxt(ge) + (row.timing ? ' (old timing rule: saving events replaces it)' : '') +
        (cap ? ' · frames: capture of ' + (IX.game_version || '?').split(' ')[0] : '') }),
      marks, errs, okEl,
      h('div', { class: 'btns' }, bSave, back, h('button', { type: 'button', text: 'Close', onclick: () => { stop(); open = null; draw(); } })));
    return { el, stop };
  }

  function draw() {
    if (!G() || !G().rows) { P.replaceChildren(h('div', { class: 'tcard' }, h('p', { class: 'msg', text: 'The game\'s throws are not known yet: the build daemon reports them when it starts and after each ship.' }))); return; }
    if (!IX && !ixTried) { ixTried = true; fetch('review/throws2/index.json', { cache: 'no-store', credentials: 'same-origin' }).then(r => r.ok ? r.json() : null).then(x => { IX = x; draw(); }, () => {}); }
    if (want0) { open = want0; want0 = null; }
    const o = openShip(), pend = G().rows.filter(r => differs(r.id));
    let cur = null;
    const list = h('div', {}, G().rows.map(r => {
      const isOpen = open === r.id, d = differs(r.id);
      const b = h('button', { type: 'button', class: 'trw', id: 'tr-' + r.id, 'aria-expanded': String(isOpen), onclick: () => { if (cur) cur.stop(); open = isOpen ? null : r.id; draw(); } },
        h('span', {}, h('b', { text: r.display }), ' ' + r.label),
        h('span', { class: 'ev', text: wantEv(r.id) ? evTxt(wantEv(r.id)) : r.timing ? 'old timing' : evTxt(null) }),
        d ? h('span', { class: 'sub' }, h('span', { class: 'tag ' + (o ? 'ship' : 'edit'), text: o ? (o.status === 'building' ? 'building' : 'queued') : 'unshipped' }), ' in game: ' + evTxt(gameEv(r.id))) : null);
      if (!isOpen) return b;
      cur = editor(r);
      return [b, cur.el];
    }));
    const bShip = h('button', { type: 'button', class: 'primary', disabled: pend.length && !o ? null : '', text: o ? 'Throws ' + (o.status === 'building' ? 'building…' : 'queued') : 'Ship throws to testers' + (pend.length ? ' (' + pend.length + ')' : ''),
      onclick: () => ship(bShip) });
    P.replaceChildren(h('div', { class: 'card tcard' },
      h('h2', {}, 'Throws', h('span', { class: 'sp' }), h('span', { text: (pend.length ? pend.length + ' unshipped · ' : '') + 'in game ' + (G().version || '?') })),
      h('div', { class: 'btns' }, bShip, msg),
      h('p', { class: 'msg', text: 'I impact (share %), H held until, L launch frame ↑ up → away ← back (away\'s flight the other way) · none, s / m / b size. Frame 1 = the throw\'s first frame.' }),
      list));
    if (open) { const el = document.getElementById('tr-' + open); if (el && el.scrollIntoView) el.scrollIntoView({ block: 'start' }); }
  }

  window.FactoryThrows = {
    poll(d, r, shown) {                                 // each poll: {draft, game}; an open editor is never redrawn
      rows = r || []; if (!d) return;
      const gv = D.game && D.game.version, dr = D.draft && D.draft.rev; D = d;
      if (shown && !open && (gv !== (D.game && D.game.version) || dr !== (D.draft && D.draft.rev))) draw();
    },
    draw,
    pending: () => !!G() && !openShip() && G().rows.some(r => differs(r.id)),
  };
})();
