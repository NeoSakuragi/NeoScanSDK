// A fighter's WORKSHOP (workshop.html?f=robert): part 1 of the Brawler Lab, the token-bound side (conversation, unlock
// requests, decoding); part 2 is the arbitration sheet (arbitrage.html, compiled by tools/brawler/arb_compile.py).
// Data: review/<f>_workshop.json (tools/brawler/workshop.py: the piece library + the piece-id registry
// tools/brawler/arb_pieces/<f>_ids.json + KOF's hit classes) and the dictionary review/<f>_anims.json (anims_core.js).
// Sections: Specials (UNLOCKED = an S- id: id, name, input, clips, what it does; LOCKED = not decoded: greyed, clips
// still play, "Unlock this" with a mic note), Throws (T- ids, the same), Animations (every $NN, each attack frame's hit
// class). Threads: decisions store, set "<f>-workshop", one entry per message: id "<key>--<time>", choice = the piece
// key (S-001 / T-001 / sp-<input> / th-<…> / anim-<hex>), label request (Bruno) | reply | unlocked (me), note = text.
(async function () {
  const AD = window.AnimDict, h = AD.h, API = 'feedback-api/';
  const root = document.getElementById('ws');
  const f = new URLSearchParams(location.search).get('f') || 'robert';
  const SET = f + '-workshop';
  const SC = 0.6;
  const [D, W] = await Promise.all([AD.load(f).catch(() => null),
    fetch('review/' + f + '_workshop.json', { cache: 'no-cache', credentials: 'same-origin' }).then(r => r.ok ? r.json() : null, () => null)]);
  if (!D || !W) { root.replaceChildren(h('p', { text: 'No workshop for "' + f + '" (it needs an animation dictionary and a piece library).' })); return; }
  let msgs = {};
  try { const r = await fetch(API + 'decisions/' + SET, { cache: 'no-store', credentials: 'same-origin' }); if (r.ok) msgs = await r.json(); } catch (e) { /* offline: sends will say so */ }
  const byKey = {};
  for (const [mid, a] of Object.entries(msgs)) if (a && a.choice) (byKey[a.choice] = byKey[a.choice] || []).push(Object.assign({ mid }, a));

  const clips = [];
  AD.clock(clips);
  const io = new IntersectionObserver(es => { for (const e of es) { const st = e.target._clip; if (!st) continue; st.visible = e.isIntersecting; if (e.isIntersecting) st.load(); } }, { rootMargin: '200px' });
  const watch = st => { clips.push(st); io.observe(st.cv); };

  // ---- hit classes: an attack box's id (KOF: animdict key 0x10 | t, or 0x100 | t) -> W.classes ----
  const KOF = /^kof9[6-9]$/.test(W.game || '');
  const boxId = k => KOF ? (k >= 0x100 ? k - 0x100 : k & 0x0F) : null;
  const hex2 = n => '$' + n.toString(16).toUpperCase().padStart(2, '0');
  const classOf = id => { if (id == null || !W.classes) return null; return W.classes[hex2(id)] || null; };
  // per animation: runs of steps with the same attack box -> [{from, to, box, label}]
  function hitRuns(a) {
    const out = [];
    (a.steps || []).forEach((s, i) => {
      const b = (s.b || []).find(x => x[0] === 'a');
      if (!b) return;
      const id = boxId(b[1]), c = classOf(id);
      const box = id != null ? hex2(id) : 'key ' + b[1];
      const label = c ? c.label + (c.juggled !== c.label ? ' (juggled: ' + c.juggled + ')' : '') : 'class not decoded';
      const last = out[out.length - 1];
      if (last && last.to === i - 1 && last.box === box) last.to = i; else out.push({ from: i, to: i, box, label });
    });
    return out;
  }
  const runText = r => 'step ' + (r.from + 1) + (r.to > r.from ? '–' + (r.to + 1) : '') + ': ' + r.box + ' ' + r.label;
  const animName = x => { const a = D.by[x]; return '$' + x + (a && a.moves && a.moves[0] ? ' ' + a.moves[0] : ''); };

  // ---- a clip (tap: ¼ speed) ----
  function clip(x, extra) {
    const a = D.by[x];
    const fig = h('figure', { class: 'clip' });
    const cap = h('figcaption', { text: '$' + x + (extra ? ' ' + extra : '') });
    if (a && a.status === 'ok' && a.f.length) {
      const { cv, st } = AD.player(D, a, SC, { lazy: true });
      st.cv = cv; watch(st);
      cv.title = 'Tap: ¼ speed';
      cv.onclick = () => { st.speed = st.speed === 1 ? 0.25 : 1; cap.textContent = '$' + x + (extra ? ' ' + extra : '') + (st.speed !== 1 ? ' · ¼' : ''); };
      fig.append(cv);
    }
    fig.append(cap);
    return fig;
  }

  // ---- a piece's thread + its request box ----
  const fmtAt = s => (s || '').slice(0, 16).replace('T', ' ');
  function thread(keys, opt) {
    const box = h('div', { class: 'thread' });
    const list = h('div', { class: 'msgs' });
    const draw = () => {
      const all = keys.flatMap(k => byKey[k] || []).sort((p, q) => (p.at || '').localeCompare(q.at || ''));
      list.replaceChildren(...all.map(m => h('div', { class: 'msg' + (m.label === 'request' ? ' mine' : '') },
        h('b', { text: m.label === 'request' ? 'You' : m.label === 'unlocked' ? 'Claude · unlocked' : 'Claude' }),
        h('span', { text: m.note || '' }), h('span', { class: 'at', text: fmtAt(m.at) }))));
      list.hidden = !all.length;
    };
    draw();
    const ta = h('textarea', { rows: '2', 'aria-label': opt.label, placeholder: opt.placeholder });
    const saved = h('div', { class: 'saved', 'aria-live': 'polite' });
    const send = h('button', { type: 'button', text: opt.button });
    send.onclick = async () => {
      const text = ta.value.trim();
      if (!text && !opt.empty) { saved.textContent = 'Write or speak something first.'; return; }
      const key = keys[0], id = (key + '--' + Date.now().toString(36)).slice(0, 40);
      const body = { set: SET, id, choice: key, label: 'request', note: text || opt.empty, question: opt.question };
      saved.textContent = 'Sending…'; send.disabled = true;
      try {
        const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        const j = await r.json().catch(() => ({}));
        (byKey[key] = byKey[key] || []).push(Object.assign({ mid: id }, j.answer || body, { at: (j.answer && j.answer.at) || new Date().toISOString() }));
        ta.value = ''; draw(); saved.textContent = 'Sent to Claude.';
      } catch (e) { saved.textContent = 'Not sent (' + e.message + '): try again'; }
      send.disabled = false;
    };
    const field = window.micNote ? window.micNote(ta) : ta;
    box.append(list, h('div', { class: 'ask' }, h('label', { text: opt.label }), field, h('div', { class: 'row' }, send, saved)));
    return box;
  }

  // ---- a special / throw card ----
  function pieceCard(p, kind) {
    const on = !!p.id;
    const tag = on ? h('span', { class: 'tag on', text: 'UNLOCKED ' + p.id }) : h('span', { class: 'tag off', text: p.pending ? 'DECODED · ID PENDING' : 'LOCKED' });
    const card = h('section', { class: 'piece' + (on ? '' : ' locked'), id: p.keys[0], 'aria-label': (on ? p.id + ' ' : 'Locked: ') + p.name });
    const inp = h('p', { class: 'pin' }, 'Input: ', h('code', { text: p.input }), p.air ? ' · in the air' : '',
      !on && kind === 'special' ? ' · not decoded yet: its program is not read from the ROM' : '');
    const row = h('div', { class: 'clips' });
    p.anims.forEach(x => row.append(clip(x)));
    (p.projectile || []).forEach(x => row.append(clip(x, '(projectile)')));
    if (!p.anims.length && !(p.projectile || []).length) row.append(h('span', { class: 'pin', text: 'No animation in the dictionary.' }));
    // "Try in game" (tryit.js): an unlocked special plays as its whole program; a throw goes on the hold's forward throw
    // (walk into the dummy, then forward + C); a locked special's animations play back to back
    const TI = window.TryIt;
    // (+ "Send to Player": the same TRY blob as the fighter's live config, tryit.js)
    const tryB = !TI ? null : on && kind === 'throw' ? TI.button(f, 'Try in game (grab, then forward + C)', () => TI.sheet(f, { slots: { grab_fwd: [p.id] } }), () => ({ sheet: { slots: { grab_fwd: [p.id] } } }))
      : on ? TI.button(f, 'Try in game', () => TI.queue(f, [p.id]), () => ({ queue: [p.id], loop: TI.loop() }))
      : p.anims.length ? TI.button(f, 'Try its animations in game', () => TI.queue(f, p.anims), () => ({ queue: p.anims, loop: TI.loop() })) : null;
    const runs = p.anims.flatMap(x => hitRuns(D.by[x] || {}).map(r => '$' + x + ' ' + runText(r)));
    const kids = [h('div', { class: 'phead' }, h('span', { class: 'pname', text: p.name }), tag), inp, h('p', { class: 'what', text: 'What it does: ' + p.what }), row, tryB];
    if (runs.length) kids.push(h('details', {}, h('summary', { text: 'Hit class per attack frame (' + runs.length + ')' }), h('ul', { class: 'hits' }, runs.map(t => h('li', { text: t })))));
    const q = (on ? p.id + ' ' : '') + p.name + ' (' + p.input + ')';
    kids.push(thread(p.keys, on
      ? { label: 'Ask or tell Claude about ' + p.id, placeholder: 'A change, a question…', button: 'Send', question: W.display + ': ' + q }
      : { label: 'Unlock this: what should it do? (optional)', placeholder: 'e.g. "the C version, for down + C"', button: 'Unlock this',
          empty: 'Please unlock ' + p.name + ' (' + p.input + ').', question: W.display + ': unlock request, ' + q }));
    card.append(...kids);
    return card;
  }

  // an animation's thread, built when opened (433 note fields up front would weigh on the tablet)
  function askAbout(a) {
    const n = (byKey['anim-' + a.id] || []).length;
    const d = h('details', {}, h('summary', { text: n ? 'Thread (' + n + ')' : 'Ask about $' + a.id }));
    d.addEventListener('toggle', () => { if (d.open && !d._built) { d._built = true; d.append(thread(['anim-' + a.id], { label: 'About $' + a.id, placeholder: 'A question, a use for it…', button: 'Send', question: W.display + ': animation ' + animName(a.id) })); } });
    return d;
  }
  // ---- the animations: every $NN, attack frames' classes, a thread each (collapsed) ----
  function animSection() {
    const wrap = h('div', {});
    const q = h('input', { type: 'search', placeholder: 'Find $ id or move', 'aria-label': 'Find an animation by id or move name' });
    let atkOnly = true;
    const bAtk = h('button', { type: 'button', 'aria-pressed': 'true', text: '✓ Attacks only' });
    const shown = h('span', { class: 'shown' });
    const grid = h('div', { class: 'agrid' });
    const cards = D.anims.filter(a => a.status === 'ok' && a.f.length).map(a => {
      const { cv, st } = AD.player(D, a, SC, { lazy: true });
      st.cv = cv; watch(st);
      cv.title = 'Tap: ¼ speed'; cv.onclick = () => { st.speed = st.speed === 1 ? 0.25 : 1; };
      const runs = hitRuns(a);
      const card = h('div', { class: 'acard', id: 'anim-' + a.id }, cv, h('div', { class: 'cap', text: AD.caption(a) }),
        runs.length ? h('ul', { class: 'hits' }, runs.map(r => h('li', { text: runText(r) }))) : null,
        window.TryIt ? window.TryIt.button(f, 'Try in game', () => window.TryIt.queue(f, [a.id]), () => ({ queue: [a.id], loop: window.TryIt.loop() })) : null,
        askAbout(a));
      card._a = a;
      return card;
    });
    const apply = () => {
      const s = q.value.trim().replace(/^\$/, '').toUpperCase(); let n = 0;
      for (const c of cards) {
        const a = c._a, txt = (a.id + ' ' + (a.exported || []).join(' ') + ' ' + (a.moves || []).join(' ')).toUpperCase();
        const ok = (!atkOnly || a.attack || !!s) && (!s || a.id === s || txt.includes(s));
        c.hidden = !ok; if (ok) n++;
      }
      shown.textContent = n + ' of ' + cards.length + ' shown';
    };
    q.oninput = apply;
    bAtk.onclick = () => { atkOnly = !atkOnly; bAtk.setAttribute('aria-pressed', String(atkOnly)); bAtk.textContent = (atkOnly ? '✓ ' : '') + 'Attacks only'; apply(); };
    grid.append(...cards);
    wrap.append(h('div', { class: 'filters' }, q, bAtk, shown), grid);
    apply();
    return wrap;
  }

  const S = W.specials, T = W.throws, C = W.counts;
  const out = [h('h1', { text: W.display + ': workshop' }),
    h('p', { class: 'intro', text: 'Part 1 of the Lab: what ' + W.display + ' can do today and what still needs decoding. Unlocked pieces (S- specials, T- throws) are in the arbitration sheet\'s picker and link into the game with no agent; a locked special needs its program read from the ROM first: ask with "Unlock this". Every piece has a thread with Claude. Tap a clip for ¼ speed.' }),
    h('div', { class: 'links' }, h('a', { href: 'arbitrage.html?f=' + f, text: 'Arbitration sheet' }), h('a', { href: 'anims.html?f=' + f, text: 'Animation dictionary' }), h('a', { href: 'review.html?f=' + f, text: 'Fighter review' })),
    window.TryIt ? window.TryIt.liveLine(f) : null,
    h('p', { class: 'counts', text: `Specials: ${C.unlocked} unlocked, ${C.locked} locked · Throws: ${C.throws_unlocked} unlocked, ${C.throws_locked} locked` + (W.class_note ? ' · ' + W.class_note : '') }),
    h('nav', { class: 'jump', 'aria-label': 'Sections' }, h('a', { href: '#specials', text: 'Specials' }), h('a', { href: '#throws', text: 'Throws' }), h('a', { href: '#animations', text: 'Animations' }))];
  out.push(h('h2', { id: 'specials', text: 'Specials' }), h('p', { class: 'about', text: 'Every special version of ' + W.display + '\'s move list (light / heavy / EX / MAX, ground and air: each version is its own piece). ' + (W.source || '') }));
  const su = S.filter(p => p.id), sl = S.filter(p => !p.id);
  out.push(h('h3', { text: 'Unlocked (' + su.length + ')' }), su.length ? su.map(p => pieceCard(p, 'special')) : h('p', { class: 'about', text: 'None yet.' }));
  out.push(h('h3', { text: 'Locked (' + sl.length + ')' }), sl.length ? sl.map(p => pieceCard(p, 'special')) : h('p', { class: 'about', text: 'None: every special is decoded.' }));
  out.push(h('h2', { id: 'throws', text: 'Throws' }), h('p', { class: 'about', text: 'Throws, grabs and command grabs: paired scripts (the victim\'s side decoded with them).' }));
  out.push(T.length ? T.map(p => pieceCard(p, 'throw')) : h('p', { class: 'about', text: 'No throw in the dictionary.' }));
  out.push(h('h2', { id: 'animations', text: 'Animations' }), h('p', { class: 'about', text: 'Every animation of ' + W.display + '\'s table by its $NN. Under each attack animation: the hit class of each attack step (' + (W.classes ? 'KOF\'s reaction for its attack box id, standing, and juggled when different' : 'class not decoded for this game') + ').' }), animSection());
  root.replaceChildren(...out.flat().filter(x => x));
  if (location.hash) { const el = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (el) { if (el.hidden) el.hidden = false; const d = el.querySelector('details:last-child'); if (el.classList.contains('acard') && d) d.open = true; el.scrollIntoView(); } }
  window.workshopReady = { unlocked: C.unlocked, locked: C.locked, throws: T.length, anims: D.anims.length };
})();
