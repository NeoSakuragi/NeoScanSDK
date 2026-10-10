// A fighter's ANIMATION DICTIONARY (tools/kizuna/anim_dict.py -> review/<fighter>_anims.json + sheets), shared by the
// dictionary page (anims.html + anims.js) and the review pages' move picker (review.js, tab "All animations").
// Flags: Bruno's tags per animation, saved with the rest of his answer to the decisions store, set "<fighter>-anims"
// (id = the animation's hex, field `flags`: a list of FLAGS ids). Extend FLAGS here: both pages read it.
window.AnimDict = (function () {
  // ---- the flags Bruno can set on an animation (several at once). group: the row it sits in; needs: shown only while
  // that flag is on (and dropped when it goes off) ----
  const FLAGS = [
    { id: 'light', group: 'Weight' }, { id: 'medium', group: 'Weight' }, { id: 'heavy', group: 'Weight' },
    { id: 'punch', group: 'Limb' }, { id: 'kick', group: 'Limb' }, { id: 'weapon', group: 'Limb' },
    { id: 'stick', group: 'Weapon kind', needs: 'weapon' }, { id: 'blade', group: 'Weapon kind', needs: 'weapon' },
    { id: 'launcher', group: 'Effect' }, { id: 'knockdown', group: 'Effect' }, { id: 'crumple', group: 'Effect' },
    { id: 'projectile', group: 'Effect' }, { id: 'throw', group: 'Effect' },
  ];
  const API = 'feedback-api/';
  const FMS = 1000 / 59.18;
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v != null) e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const loaded = {};

  // the dictionary of a fighter (null when it has none); its answers ride along (D.ans: id -> answer)
  function load(fighter) {
    if (!loaded[fighter]) loaded[fighter] = (async () => {
      const r = await fetch('review/' + fighter + '_anims.json', { cache: 'no-cache', credentials: 'same-origin' });
      if (!r.ok) return null;
      const D = await r.json();
      D.by = Object.fromEntries(D.anims.map(a => [a.id, a]));
      D.imgs = []; D.ans = {}; D.set = fighter + '-anims';
      try { const q = await fetch(API + 'decisions/' + D.set, { cache: 'no-store', credentials: 'same-origin' }); if (q.ok) D.ans = await q.json(); } catch (e) { /* offline */ }
      return D;
    })();
    return loaded[fighter];
  }
  // a sheet's image, fetched the first time a clip of it is shown; cb runs once it is there
  function sheet(D, k, cb) {
    let im = D.imgs[k];
    if (!im) { im = D.imgs[k] = new Image(); im._cbs = []; im.onload = () => { im._cbs.forEach(f => f()); im._cbs = []; }; im.src = D.sheets[k].src; }
    if (im.complete && im.naturalWidth) cb && cb(); else if (cb) im._cbs.push(cb);
    return im;
  }
  // the clip: one entry per game frame = the step shown
  function bounds(D, a) {
    const cells = D.sheets[a.sheet].cells;
    let x0 = -2, x1 = 2, y0 = -4, y1 = 0;                       // y down from the feet
    for (const s of a.steps) {
      if (s.d >= 0) { const [, , w, hh, ox, oy] = cells[s.d]; x0 = Math.min(x0, -ox); x1 = Math.max(x1, w - ox); y0 = Math.min(y0, -oy); y1 = Math.max(y1, hh - oy); }
      for (const b of s.b) { x0 = Math.min(x0, b[2]); x1 = Math.max(x1, b[3]); y0 = Math.min(y0, -b[5]); y1 = Math.max(y1, -b[4]); }
    }
    return [x0 - 4, x1 + 4, y0 - 4, Math.max(y1, 0) + 4];
  }
  const DASH = { a: [], h: [4, 3], p: [1, 3], x: [6, 2, 1, 2] };
  const WIDTH = { a: 2, h: 1, p: 1, x: 1 };
  // a player: {cv, st}; st = {frames, i, speed, playing, visible, boxes, H, draw()} (review.js's clock drives it too)
  function player(D, a, S, opt) {
    opt = opt || {};
    const [x0, x1, y0, y1] = bounds(D, a), W = x1 - x0, H = y1 - y0;
    const cv = h('canvas', { width: Math.ceil(W * S), height: Math.ceil(H * S), role: 'img', 'aria-label': 'Animation $' + a.id + ', ' + a.frames + ' frames' });
    const ctx = cv.getContext('2d');
    const cells = D.sheets[a.sheet].cells;
    const st = { key: 'anim-' + a.id, frames: a.f, i: 0, acc: 0, played: 0, ms: 0, speed: 1, playing: true, visible: false, boxes: !!opt.boxes, H, W, a };
    let im = null;
    st.step = () => a.steps[a.f[st.i]];
    st.draw = () => {
      ctx.setTransform(S, 0, 0, S, 0, 0); ctx.imageSmoothingEnabled = false;
      ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#000'; ctx.fillRect(0, -y0, W, 1 / S); ctx.fillRect(-x0, -y0, 1 / S, 4);   // floor, the feet
      const s = st.step();
      if (s && s.d >= 0 && im && im.complete) { const [sx, sy, w, hh, ox, oy] = cells[s.d]; ctx.drawImage(im, sx, sy, w, hh, -x0 - ox, -y0 - oy, w, hh); }
      if (st.boxes && s) for (const b of s.b) {
        ctx.setLineDash(DASH[b[0]].map(v => v / S)); ctx.lineWidth = WIDTH[b[0]] / S; ctx.strokeStyle = '#000';
        ctx.strokeRect(b[2] - x0, -b[5] - y0, b[3] - b[2], b[5] - b[4]);
      }
      ctx.setLineDash([]);
      st.onDraw && st.onDraw(s);
    };
    st.load = () => { if (!im) im = sheet(D, a.sheet, () => st.draw()); };
    if (!opt.lazy) st.load();
    cv._clip = st;
    st.draw();
    return { cv, st };
  }
  // the clock for pages without their own (anims.js): every visible, playing clip advances one game frame a FMS
  function clock(list) {
    let last = performance.now();
    const tick = now => {
      const dt = Math.min(250, now - last); last = now;
      for (const c of list) {
        if (!c.playing || !c.visible) continue;
        c.acc += dt * c.speed; let n = 0;
        while (c.acc >= FMS) { c.acc -= FMS; c.i = (c.i + 1) % c.frames.length; n++; }
        if (n) c.draw();
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
  // Bruno's flags if he set any, else my suggestion
  const flagsOf = (D, a) => { const x = D.ans[a.id]; return x && Array.isArray(x.flags) ? { list: x.flags, mine: false } : { list: a.suggest || [], mine: true }; };
  async function save(D, id, body) {
    const a = D.by[id];
    D.ans[id] = Object.assign({}, D.ans[id], body);
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ set: D.set, id, question: `${D.display} animation $${id}` + (a && a.moves && a.moves.length ? ' (' + a.moves.slice(0, 2).join(', ') + ')' : '') }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  }
  // the flag toggles of one animation: pressed = filled + a check mark; my guess shown pressed and marked "suggested"
  // until Bruno taps (any tap, or "Confirm", saves the whole set as his)
  function flagEditor(D, a, onChange) {
    const wrap = h('div', { class: 'flags' });
    const saved = h('div', { class: 'dsaved' });
    const draw = () => {
      const { list, mine } = flagsOf(D, a);
      const on = new Set(list);
      const groups = [...new Set(FLAGS.map(f => f.group))];
      const rows = groups.map(g => {
        const fs = FLAGS.filter(f => f.group === g && (!f.needs || on.has(f.needs)));
        if (!fs.length) return null;
        return h('div', { class: 'frow', role: 'group', 'aria-label': g }, h('span', { class: 'fgroup', text: g }), fs.map(f => {
          const b = h('button', { type: 'button', class: 'flag' + (mine && on.has(f.id) ? ' sugg' : ''), 'aria-pressed': String(on.has(f.id)) },
            h('span', { class: 'mark', text: on.has(f.id) ? '✓' : '○' }), ' ' + f.id);
          b.onclick = () => {
            const nx = new Set(on);
            if (nx.has(f.id)) { nx.delete(f.id); FLAGS.filter(x => x.needs === f.id).forEach(x => nx.delete(x.id)); } else nx.add(f.id);
            put([...nx]);
          };
          return b;
        }));
      });
      const head = mine ? h('div', { class: 'fsugg' }, h('span', { text: list.length ? 'Suggested from the data (not yet yours): ' + list.join(', ') : 'No suggestion: tap the flags that fit' }),
        list.length ? h('button', { type: 'button', class: 'flag', text: 'Confirm as is', onclick: () => put(list.slice()) }) : null) : null;
      wrap.replaceChildren(...[head, ...rows, saved].filter(Boolean));
    };
    const put = async list => {
      const ord = FLAGS.map(f => f.id).filter(id => list.includes(id));
      D.ans[a.id] = Object.assign({}, D.ans[a.id], { flags: ord }); draw();
      saved.textContent = 'Saving…';
      try { await save(D, a.id, { flags: ord }); saved.textContent = 'Saved'; } catch (e) { saved.textContent = 'Not saved (' + e.message + '): tap again'; }
      onChange && onChange();
    };
    draw();
    return wrap;
  }
  const CSS = `
.flags { display: flex; flex-direction: column; gap: 6px; }
.frow { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }
.fgroup { font-size: 12px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; flex: 0 0 100%; }
button.flag { font: inherit; font-size: 15px; background: #fff; color: #000; border: 2px solid #000; padding: 5px 9px; cursor: pointer; }
button.flag[aria-pressed="true"] { background: #000; color: #fff; font-weight: 700; }
button.flag.sugg[aria-pressed="true"] { outline: 2px dashed #000; outline-offset: 2px; }
.fsugg { border: 2px dashed #000; padding: 5px 8px; font-size: 14px; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }`;
  if (!document.getElementById('animdict-css')) { const s = document.createElement('style'); s.id = 'animdict-css'; s.textContent = CSS; document.head.append(s); }
  // "$6E · 40 f · attack · used by BC (exported)"
  const caption = a => a.status !== 'ok' ? `$${a.id} · ${a.status}` :
    `$${a.id} · ${a.frames ? a.frames + ' f' : 'still'} · ${a.kind}` + (a.moves.length ? ' · used by ' + a.moves.slice(0, 2).join(', ') + (a.moves.length > 2 ? ' …' : '') : '') + (a.exported.length ? ' (exported)' : '');
  return { FLAGS, load, sheet, bounds, player, clock, flagsOf, save, flagEditor, caption, h };
})();
