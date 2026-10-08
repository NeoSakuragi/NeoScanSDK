// Fighter review (brawler revamp phase 4): one fighter's pieces (tags + appeal from tools/brawler/pieces.py) and my chain
// proposal, each as a looping clip at the game's speed (59.18 frames a second: every entry of a clip is one game
// frame, review_build.py), with Keep / Drop / "None of these" + a note with the microphone (micnote.js). Answers go to
// the feedback service's decisions store (POST feedback-api/decision, set "review-<fighter>"; GET
// feedback-api/decisions/review-<fighter>), the same store as the Decisions page.
(async function () {
  const API = 'feedback-api/';
  const NONE = 'None of these: my own answer in the note';
  const OPTS = ['Keep', 'Drop', NONE];
  const SHOWN = 8;                                        // pieces shown before "Show all"
  const root = document.getElementById('rev');
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const get = async (u, o) => { const r = await fetch(u, Object.assign({ cache: 'no-cache', credentials: 'same-origin' }, o)); if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); };

  let index;
  try { index = await get('review/index.json'); } catch (e) { root.replaceChildren(h('p', { text: 'No review data (' + e.message + ').' })); return; }
  const want = new URLSearchParams(location.search).get('f') || (location.hash.match(/^#f=(\w+)/) || [])[1];
  const who = index.fighters.find(f => f.fighter === want) || index.fighters[0];
  const D = await get('review/' + who.fighter + '.json');
  const SET = 'review-' + D.fighter;
  let ans = {};
  try { ans = await get(API + 'decisions/' + SET, { cache: 'no-store' }); } catch (e) { /* offline: answers can't load */ }
  const sheet = new Image(); sheet.src = D.sheet;
  await new Promise((ok, ko) => { sheet.onload = ok; sheet.onerror = () => ko(new Error('sheet')); }).catch(() => {});
  const P = Object.fromEntries(D.pieces.map(p => [p.id, p]));

  // ---- the frame player: every visible clip on one clock, one game frame = 1000 / fps ms ----
  const FMS = 1000 / D.fps;
  const clips = [];
  window.reviewStats = () => Object.fromEntries(clips.map(c => [c.key, { len: c.frames.length, played: c.played, ms: c.ms, i: c.i }]));
  function bounds(frames) {
    let x0 = 0, x1 = 1, y0 = -1, y1 = 0;
    for (const [, spr, b] of frames) {
      for (const [ci, x, y, m] of spr) {
        const [, , w, hh, ox, oy] = D.cells[ci];
        const l = m ? x - (w - 1 - ox) : x - ox;
        x0 = Math.min(x0, l); x1 = Math.max(x1, l + w); y0 = Math.min(y0, -y - oy); y1 = Math.max(y1, -y - oy + hh);
      }
      if (b) { x0 = Math.min(x0, b[0]); x1 = Math.max(x1, b[2]); y0 = Math.min(y0, b[1]); y1 = Math.max(y1, b[3]); }
    }
    return [x0 - 6, x1 + 6, y0 - 4, Math.max(y1, 0) + 6];
  }
  function drawSprite(ctx, ci, fx, fy, m) {
    const [sx, sy, w, hh, ox, oy] = D.cells[ci];
    if (!m) ctx.drawImage(sheet, sx, sy, w, hh, fx - ox, fy - oy, w, hh);
    else { ctx.save(); ctx.translate(fx, 0); ctx.scale(-1, 1); ctx.drawImage(sheet, sx, sy, w, hh, -ox, fy - oy, w, hh); ctx.restore(); }
  }
  function makeClip(key, title) {
    const C = D.clips[key];
    if (!C) return null;
    const frames = C.frames, [x0, x1, y0, y1] = bounds(frames);
    const W = x1 - x0, H = y1 - y0, S = 2;
    const cv = h('canvas', { width: W * S, height: H * S, role: 'img', 'aria-label': 'Clip: ' + title + ', ' + frames.length + ' frames' });
    const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = false;
    const fc = h('span', { class: 'fcount' });
    const st = { key, frames, i: 0, acc: 0, played: 0, ms: 0, speed: 1, playing: true, visible: false, boxes: false, links: C.links || null };
    st.draw = () => {
      const [fl, spr, b] = frames[st.i];
      ctx.setTransform(S, 0, 0, S, 0, 0); ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = '#000'; ctx.fillRect(0, -y0, W, 1);                          // the floor line at the feet
      ctx.fillRect(-x0, -y0, 1, 4);                                                // the start's feet
      for (const [ci, x, y, m] of spr) drawSprite(ctx, ci, x - x0, -y - y0, m);
      if (st.boxes && b) { ctx.setLineDash([3, 2]); ctx.lineWidth = 1; ctx.strokeStyle = '#000'; ctx.strokeRect(b[0] - x0 + .5, b[1] - y0 + .5, b[2] - b[0], b[3] - b[1]); ctx.setLineDash([]); }
      const link = st.links ? st.links.filter(v => v <= st.i).length : 0;
      fc.textContent = `frame ${st.i + 1} / ${frames.length}` + (link ? ` · link ${link}` : '') + (fl & 4 ? ' · hit-stop' : fl & 2 ? ' · contact' : fl & 1 ? ' · hitting' : '');
    };
    const bPlay = h('button', { type: 'button', 'aria-pressed': 'false', text: 'Pause' });
    bPlay.onclick = () => { st.playing = !st.playing; bPlay.textContent = st.playing ? 'Pause' : 'Play'; bPlay.setAttribute('aria-pressed', String(!st.playing)); };
    const bSlow = h('button', { type: 'button', 'aria-pressed': 'false', text: '¼ speed' });
    bSlow.onclick = () => { st.speed = st.speed === 1 ? 0.25 : 1; bSlow.setAttribute('aria-pressed', String(st.speed !== 1)); };
    const bStep = h('button', { type: 'button', text: 'Step' });
    bStep.onclick = () => { st.playing = false; bPlay.textContent = 'Play'; bPlay.setAttribute('aria-pressed', 'true'); st.i = (st.i + 1) % frames.length; st.draw(); };
    const bBox = h('button', { type: 'button', 'aria-pressed': 'false', text: 'Hit boxes' });
    bBox.onclick = () => { st.boxes = !st.boxes; bBox.setAttribute('aria-pressed', String(st.boxes)); st.draw(); };
    clips.push(st); io.observe(cv); cv._clip = st;
    sheet.complete && st.draw();
    return h('div', { class: 'clip' }, cv, h('div', { class: 'ctl' }, bPlay, bSlow, bStep, bBox, fc));
  }
  const io = new IntersectionObserver(es => { for (const e of es) e.target._clip.visible = e.isIntersecting; }, { rootMargin: '100px' });
  let last = performance.now();
  function tick(now) {
    const dt = Math.min(250, now - last); last = now;
    for (const c of clips) {
      if (!c.playing || !c.visible) continue;
      c.acc += dt * c.speed; c.ms += dt;
      let n = 0;
      while (c.acc >= FMS) { c.acc -= FMS; c.i = (c.i + 1) % c.frames.length; c.played++; n++; }
      if (n) c.draw();
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);

  // the drawings of a piece, in order, with the frames each is held (the contact drawing outlined: e-ink's still view)
  function strip(p) {
    const C = D.clips[p.id]; if (!C) return null;
    const runs = [];
    for (const [fl, spr] of C.frames) {
      const ci = spr[spr.length > 1 ? spr.length - 1 : 0][0], key = spr.map(s => s[0] + ':' + s[3]).join(',');
      const r = runs[runs.length - 1];
      if (r && r.key === key) { r.n++; r.hit = r.hit || !!(fl & 2); } else runs.push({ key, spr, n: 1, hit: !!(fl & 2) });
    }
    return h('div', { class: 'strip', 'aria-label': 'Drawings in order with the frames each is held' }, runs.map(r => {
      const own = r.spr.find(s => true);
      const [, , w, hh] = D.cells[r.spr[0][0]];
      const sc = Math.min(1, 64 / hh);
      const cv = h('canvas', { width: Math.max(8, Math.round(w * sc)), height: Math.round(hh * sc) });
      const ctx = cv.getContext('2d'); ctx.imageSmoothingEnabled = false;
      ctx.save(); ctx.scale(sc, sc);
      const [sx, sy, ww, hh2] = D.cells[own[0]];
      if (own[3]) { ctx.translate(ww, 0); ctx.scale(-1, 1); }
      ctx.drawImage(sheet, sx, sy, ww, hh2, 0, 0, ww, hh2); ctx.restore();
      return h('figure', { class: r.hit ? 'hit' : '' }, cv, h('figcaption', { text: (r.hit ? 'HIT ' : '') + r.n + 'f' }));
    }));
  }

  // ---- answers ----
  const total = [];
  const status = h('div', { class: 'status' });
  const count = () => { status.textContent = `${total.filter(id => ans[id] && ans[id].choice != null).length} of ${total.length} answered`; };
  async function post(body) {
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ set: SET }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  }
  function answer(id, question) {
    total.push(id);
    const a = ans[id] || {};
    const saved = h('div', { class: 'dsaved', text: a.at ? 'Saved' : '' });
    const save = async body => {
      ans[id] = Object.assign({}, ans[id], body); count();
      try { await post(Object.assign({ id, question }, body)); saved.textContent = 'Saved'; }
      catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; }
    };
    const ta = h('textarea', { 'aria-label': 'Note for: ' + question, placeholder: 'Note (type or speak)' });
    ta.value = a.note || '';
    let t; ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => save({ note: ta.value }), 700); });
    const btns = OPTS.map((o, i) => {
      const b = h('button', { type: 'button', 'aria-pressed': String(a.choice === i), 'data-opt': String(i) }, h('span', { class: 'mark', text: a.choice === i ? '✓' : '○' }), h('span', { text: o }));
      b.onclick = () => {
        btns.forEach((x, j) => { x.setAttribute('aria-pressed', String(i === j)); x.querySelector('.mark').textContent = i === j ? '✓' : '○'; });
        save({ choice: i, label: o });
        if (o === NONE) ta.focus();
      };
      return b;
    });
    return [h('div', { class: 'dopts', role: 'group', 'aria-label': 'Answer for: ' + question }, btns), h('div', { class: 'dnote' }, window.micNote ? window.micNote(ta) : ta), saved];
  }

  // ---- tags ----
  const segTxt = p => p.kind === 'throw' ? '-' : `${p.startup} / ${p.active} / ${p.recovery} f` + (p.hits > 1 ? ` (${p.hits} hits)` : '');
  function tags(p) {
    const row = (k, v) => [h('dt', { text: k }), h('dd', { text: v })];
    return h('dl', { class: 'tags' },
      row('Input', p.kind === 'special' ? p.special + ' on ' + p.label.split('(on ')[1].split(')')[0] : p.kind === 'throw' ? 'back + A on the last link' : p.label + (p.button ? ` (button ${p.button})` : '')),
      row('Limb', p.limb), row('Height', p.height || '-'), row('Victim', p.reaction),
      row('Reach', p.kind === 'throw' ? 'a grab' : p.reach + ' px'),
      row('Startup / active / recovery', segTxt(p)),
      row('Damage', p.kind === 'throw' ? 'the throw\'s own' : String(p.damage)));
  }
  function parts(p) {
    const r = p.raw, q = p.parts;
    return h('ul', { class: 'parts' },
      h('li', { text: `Drawings ${q.drawings}: ${r.drawings} distinct` }),
      h('li', { text: `Evenness ${q.evenness}: longest hold ${r.longest_hold} f, median ${r.median_hold} f` }),
      h('li', { text: `Pose travel ${q.travel}: ${r.travel}x the idle silhouette changes` }),
      h('li', { text: `Contact ${q.contact}: ${r.contact.length ? r.contact.join(', ') : 'no clear contact frame'}` }),
      h('li', { text: `Joins with idle ${q.joins}: start ${r.join_start}, end ${r.join_end} overlap` }));
  }
  function pieceCard(p, rank) {
    const q = (p.kind === 'special' ? p.special + ' first hit' : p.label);
    return h('section', { class: 'card', id: 'p-' + p.id },
      h('header', {}, h('span', { class: 'rank', text: '#' + rank }), h('h3', { text: p.label }),
        h('span', { class: 'score' }, 'appeal ', h('b', { text: String(p.appeal) }), ' / 100')),
      makeClip(p.id, q), strip(p), tags(p),
      h('details', {}, h('summary', { text: 'Why this appeal score' }), parts(p)),
      answer(p.id, `${D.display}: keep ${q} as a chain piece?`));
  }

  // ---- the page ----
  const pr = D.proposal, ch = pr.chain, fin = pr.finishers;
  const name = id => (P[id] || {}).label || id;
  const parts_ = [];
  parts_.push(h('nav', { class: 'who', 'aria-label': 'Fighters' }, index.fighters.map(f => h('a', { href: '?f=' + f.fighter, 'aria-current': f.fighter === D.fighter ? 'page' : 'false', text: f.display + ' (' + f.archetype + ')' }))));
  parts_.push(h('h1', { text: `${D.display}: pieces and chain` }));
  parts_.push(status);
  parts_.push(h('p', { class: 'intro', text: `Every piece ${D.display} could use in a chain, from the game's data: its tags and my appeal score, ranked; then my proposal for the ${pr.archetype} archetype (${ch.length} links). Each clip loops at the game's speed (¼ speed, Step and the hit boxes are under it); the strip under it shows each drawing with the frames it is held, the contact drawing outlined. Keep, Drop, or "None of these" with your own answer in the note.` }));
  parts_.push(h('details', { class: 'formula' }, h('summary', { text: 'How the appeal score is made (0-100)' }),
    h('p', { text: '20 points each, read from the animation itself:' }),
    h('ul', {},
      h('li', { text: 'Drawings: distinct drawings shown; 9 or more = full.' }),
      h('li', { text: 'Evenness: no drawing held far longer than the rest; longest hold / median hold, 2x or less = full, 6x or more = none.' }),
      h('li', { text: 'Pose travel: how much the silhouette changes from drawing to drawing, summed, against the idle silhouette; 6x = full.' }),
      h('li', { text: 'Contact: the hit lands on a new drawing (35 %), that drawing snaps forward (up to 35 % for 24 px), an effect or a voice on it (30 %).' }),
      h('li', { text: 'Joins: how much the first and last drawings overlap the idle pose; 25 % overlap = none, 75 % = full.' })),
    h('p', { text: 'Tags: limb by the source button, height from the attack box on the standing body, victim reaction as the brawler plays it, reach = the attack box\'s front edge, startup / active / recovery = the retiming segments.' })));

  parts_.push(h('h2', { text: `Pieces (${D.pieces.length}), my ranking` }));
  const rest = [];
  D.pieces.forEach((p, i) => { const c = pieceCard(p, i + 1); if (i < SHOWN) parts_.push(c); else { c.hidden = true; rest.push(c); parts_.push(c); } });
  if (rest.length) {
    const more = h('button', { type: 'button', class: 'more', text: `Show all ${D.pieces.length} pieces (${rest.length} more)` });
    more.onclick = () => { rest.forEach(c => { c.hidden = false; }); more.remove(); };
    parts_.push(more);
  }

  parts_.push(h('h2', { text: 'My proposal' }));
  parts_.push(h('section', { class: 'card', id: 'p-archetype' }, h('header', {}, h('h3', { text: `Archetype: ${pr.archetype}` })),
    h('p', { class: 'ctx', text: `${ch.length} links (fast 5, balanced 4, heavy 3), as set in 1A. ${pr.archetype === 'heavy' ? 'Fewer, slower, stronger hits.' : pr.archetype === 'fast' ? 'A snappy first hit, more links, less damage per hit.' : 'The all-rounder.'}` }),
    answer('archetype', `${D.display}: keep the ${pr.archetype} archetype?`)));
  const cur = ch.current || {};
  parts_.push(h('section', { class: 'card', id: 'p-chain' },
    h('header', {}, h('h3', { text: 'The chain: ' + ch.links.map(name).join(' > ') + ' > ' + name(fin.neutral.pick) }), h('span', { class: 'rank', text: ch.purpose })),
    makeClip('chain', 'the chain'),
    h('p', { class: 'ctx', text: `Played with each press on the first possible frame: every link to its hit, its hit-stop (${D.hitstops.join(', ')} f), then the next; the neutral finisher at the end.` }),
    h('ul', { class: 'parts' }, ch.links.map((id, k) => {
      const p = P[id];
      return h('li', { text: `Link ${k + 1}: ${p.label}, ${p.limb} ${p.height}, startup ${p.startup} f, appeal ${p.appeal}; victim margin ${ch.margins[k]} px` + (k < ch.joins.length ? `; join into the next ${ch.joins[k]}` : '') });
    })),
    h('p', { class: 'ctx', text: 'Why: picked for appeal and flow: the contact pose leads into the next start pose, the victim stays in reach (margin = px of reach left; it slides back a little each hit), strong hits never fall back to light ones, varied limbs and heights' + (pr.archetype === 'heavy' ? ', strong hits first (heavy).' : ', the quickest first hit (feel principle 1).') }),
    cur.links ? h('p', { class: 'ctx', text: 'Today\'s chain (1A\'s generator): ' + cur.links.join(' > ') + ' > ' + (cur.finishers || {}).neutral }) : null,
    answer('chain', `${D.display}: keep this chain?`)));
  const STICK = { neutral: 'Neutral (A)', forward: 'Forward + A', up: 'Up + A', down: 'Down + A', back: 'Back + A' };
  for (const k of ['neutral', 'forward', 'up', 'down', 'back']) {
    const f = fin[k]; if (!f || !f.pick) continue;
    const p = P[f.pick];
    parts_.push(h('section', { class: 'card', id: 'p-fin-' + k },
      h('header', {}, h('h3', { text: `${STICK[k]} finisher: ${p.label}` }), h('span', { class: 'rank', text: f.purpose })),
      makeClip('fin-' + k, STICK[k] + ' finisher'),
      h('p', { class: 'ctx', text: `Shown after the last link (${name(ch.links[ch.links.length - 1])}). ` + (f.alternatives.length ? `${f.alternatives[0].why}; reach margin ${f.alternatives[0].margin} px, join ${f.alternatives[0].join}. My next picks: ${f.alternatives.slice(1).map(a => name(a.id)).join(', ') || 'none'}.` : (k === 'back' ? (p.mirrored ? 'Its throw played mirrored (no throw of its own ends behind).' : 'The throw whose victim ends behind.') + ' Invincible for the whole throw.' : '')) }),
      tags(p),
      answer('fin-' + k, `${D.display}: keep ${p.label} as the ${STICK[k].toLowerCase()} finisher?`)));
  }
  const gen = { id: 'general', q: 'Anything else for this fighter?' };
  parts_.push(h('section', { class: 'card', id: 'p-general' }, h('header', {}, h('h3', { text: gen.q })), answer('general', `${D.display}: ${gen.q}`).filter((x, i) => i > 0)));
  total.splice(total.indexOf('general'), 1);
  root.replaceChildren(...parts_);
  count();
  clips.forEach(c => c.draw());
  window.reviewReady = true;
})();
