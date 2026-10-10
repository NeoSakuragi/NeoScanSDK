// The animation dictionary page (anims.html?f=kim, ?f=krauser, ?f=robert; data tools/brawler/animdict.py): every animation of a fighter's table as a small looping clip at the
// game's speed (one scale for all), filters, and a larger view per animation (¼ speed, step by step, the boxes, the
// step / box / sound data) with "I want this one", the flags (anims_core.js FLAGS) and a note with the microphone.
// Answers: the decisions store, set "<fighter>-anims", id = the animation's hex.
(async function () {
  const AD = window.AnimDict, h = AD.h;
  const root = document.getElementById('dict');
  const f = new URLSearchParams(location.search).get('f') || 'kim';
  const D = await AD.load(f).catch(() => null);
  if (!D) { root.replaceChildren(h('p', { text: 'No animation dictionary for "' + f + '".' })); return; }
  const SC = 0.75;                                    // one scale for every card (Kim standing about 84 css px)
  const clips = [];
  AD.clock(clips);
  const io = new IntersectionObserver(es => { for (const e of es) { const st = e.target._clip; st.visible = e.isIntersecting; if (e.isIntersecting) st.load(); } }, { rootMargin: '200px' });
  const wanted = a => { const x = D.ans[a.id]; return !!(x && x.choice === 0); };
  const FILTERS = [
    ['all', 'All', () => true], ['attack', 'Attacks', a => a.attack], ['used', 'Used by a move', a => a.moves && a.moves.length],
    ['notexp', 'Not exported', a => a.status === 'ok' && !a.exported.length], ['unused', 'Unused', a => !(a.moves && a.moves.length) && !a.exported.length && !(a.reactions && a.reactions.length)],
    ['want', 'I want these', wanted]];
  // "Try in game" (tryit.js): the queue, animations back to back (kept in this browser per fighter)
  const QK = 'tryit-queue-' + f;
  let tq = []; try { tq = JSON.parse(localStorage.getItem(QK) || '[]'); } catch (e) { tq = []; }
  const qbar = h('div', { class: 'bar', role: 'group', 'aria-label': 'Queue for the game' });
  const drawQ = () => {
    try { localStorage.setItem(QK, JSON.stringify(tq)); } catch (e) { /* private window */ }
    qbar.replaceChildren(h('span', { class: 'lbl', text: 'Queue for the game (back to back): add from an animation\'s larger view' }),
      h('span', { class: 'shown', text: tq.length ? tq.map(x => '$' + x).join(' > ') : 'empty' }),
      window.TryIt && tq.length ? window.TryIt.button(f, 'Try the queue in game', () => window.TryIt.queue(f, tq), () => ({ queue: tq.slice(), loop: window.TryIt.loop() })) : null,
      tq.length ? h('button', { type: 'button', text: 'Remove the last', onclick: () => { tq.pop(); drawQ(); } }) : null,
      tq.length ? h('button', { type: 'button', text: 'Clear the queue', onclick: () => { tq = []; drawQ(); } }) : null);
    window.dictQueue = tq.slice();
  };
  drawQ();
  let filt = 'all';
  const flagOn = new Set();
  const shown = h('span', { class: 'shown' });

  const cards = D.anims.map(a => {
    const fl = h('div', { class: 'fl' });
    const card = h('button', { type: 'button', class: 'card', 'aria-label': 'Animation $' + a.id + ': open the larger view' });
    if (a.status === 'ok' && a.f.length) {
      const { cv, st } = AD.player(D, a, SC, { lazy: true });
      clips.push(st); io.observe(cv);
      card.append(cv);
    }
    card.append(h('div', { class: 'cap', text: AD.caption(a) }), fl);
    const mark = () => {
      const { list, mine } = AD.flagsOf(D, a);
      fl.textContent = (wanted(a) ? '✓ WANT · ' : '') + (list.length ? (mine ? 'suggested: ' : 'flags: ') + list.join(' ') : '');
      card.classList.toggle('want', wanted(a));
    };
    mark();
    card.onclick = () => open(a, mark);
    return { a, card, mark };
  });
  const grid = h('div', { class: 'grid' }, cards.map(c => c.card));
  const apply = () => {
    const fn = FILTERS.find(x => x[0] === filt)[2];
    let n = 0;
    for (const c of cards) {
      const fls = new Set(AD.flagsOf(D, c.a).list);
      const ok = !!fn(c.a) && [...flagOn].every(x => fls.has(x));
      c.card.hidden = !ok; if (ok) n++;
    }
    shown.textContent = `${n} of ${D.anims.length} shown`;
    fbtns.forEach((b, i) => { const [k, t, fn] = FILTERS[i]; b.textContent = (k === filt ? '✓ ' : '') + `${t} (${D.anims.filter(fn).length})`; });
  };
  const fbtns = FILTERS.map(([k, t, fn]) => {
    const b = h('button', { type: 'button', 'aria-pressed': String(k === filt), text: `${k === filt ? '✓ ' : ''}${t} (${D.anims.filter(fn).length})` });
    b.onclick = () => { filt = k; fbtns.forEach((x, i) => { const on = FILTERS[i][0] === k; x.setAttribute('aria-pressed', String(on)); x.textContent = (on ? '✓ ' : '') + x.textContent.replace(/^✓ /, ''); }); apply(); };
    return b;
  });
  const flbtns = AD.FLAGS.map(fg => {
    const b = h('button', { type: 'button', 'aria-pressed': 'false', text: fg.id });
    b.onclick = () => { const on = !flagOn.has(fg.id); on ? flagOn.add(fg.id) : flagOn.delete(fg.id); b.setAttribute('aria-pressed', String(on)); b.textContent = (on ? '✓ ' : '') + fg.id; apply(); };
    return b;
  });
  const st = D.anims, cnt = fn => st.filter(fn).length;
  root.replaceChildren(
    h('h1', { text: `${D.display}: animation dictionary` }),
    h('p', { class: 'intro' }, `All ${D.count} animations of ${D.display}'s table in ${D.source}, ${D.drawn || `drawn from the ROM at the game's zoom $${D.zoom} (×${D.scale}, the size the brawler shows him)`}. ` +
      (/^kof9[68]$/.test(D.game || '') ? 'Flags suggested from KOF\'s buttons (A / B light, C / D heavy; A / C punch, B / D kick), a projectile, a knockdown the capture saw, a throw. ' : '') +
      `${cnt(a => a.attack)} have attack boxes, ${cnt(a => a.moves && a.moves.length)} are played by a move I captured or named, ${cnt(a => a.exported.length)} are in the brawler. ` +
      'Each clip loops at the game speed; tap one for the larger view (¼ speed, step by step, boxes, data), "I want this one", flags and a note. ',
      h('a', { href: 'review.html?f=' + f, text: 'Back to the fighter review' }), ' · ', h('a', { href: 'arbitrage.html?f=' + f, text: 'The arbitration sheet (chain, finishers, Blitz, air Blitz, specials, air specials, air, grab, fury)' })),
    h('div', { class: 'bar', role: 'group', 'aria-label': 'Show' }, h('span', { class: 'lbl', text: 'Show' }), fbtns),
    h('div', { class: 'bar', role: 'group', 'aria-label': 'Flags (yours, else my suggestion)' }, h('span', { class: 'lbl', text: 'With every flag (yours, else my suggestion)' }), flbtns),
    qbar, shown, grid);
  apply();
  window.dictReady = true;

  // ---- the larger view ----
  function open(a, onChange) {
    const close = () => { dlg.remove(); document.removeEventListener('keydown', esc); if (st2) clips.splice(clips.indexOf(st2), 1); onChange(); apply(); };
    const esc = e => { if (e.key === 'Escape') close(); };
    const [x0, x1] = AD.bounds(D, a);
    const S = Math.max(1, Math.min(3, Math.floor((Math.min(window.innerWidth, 760) - 44) / (x1 - x0) * 2) / 2));
    const kids = [];
    let st2 = null;
    if (a.status === 'ok' && a.f.length) {
      const pl = AD.player(D, a, S, { boxes: true });
      st2 = pl.st; st2.visible = true; clips.push(st2);
      pl.cv.classList.add('big');
      const fc = h('span', { class: 'fcount' });
      const rows = [];
      st2.onDraw = s => {
        const k = a.f[st2.i];
        fc.textContent = `frame ${st2.i + 1} / ${a.f.length} · step ${k} (${s.t} f)` + (s.s ? ' · sound ' + s.s : '') + (s.b.some(b => b[0] === 'a') ? ' · ATTACK' : '') + (s.m ? ' · ' + s.m : '');
        rows.forEach((r, j) => r.classList.toggle('cur', j === k));
      };
      const bPlay = h('button', { type: 'button', 'aria-pressed': 'false', text: 'Pause' });
      const setPlay = p => { st2.playing = p; bPlay.textContent = p ? 'Pause' : 'Play'; bPlay.setAttribute('aria-pressed', String(!p)); };
      bPlay.onclick = () => setPlay(!st2.playing);
      const bSlow = h('button', { type: 'button', 'aria-pressed': 'false', text: '¼ speed' });
      bSlow.onclick = () => { st2.speed = st2.speed === 1 ? 0.25 : 1; bSlow.setAttribute('aria-pressed', String(st2.speed !== 1)); bSlow.textContent = (st2.speed !== 1 ? '✓ ' : '') + '¼ speed'; };
      // step = the next / previous animation STEP (its first frame), frame = one game frame
      const goStep = d => { setPlay(false); const ks = [...new Set(a.f)]; const p = (ks.indexOf(a.f[st2.i]) + d + ks.length) % ks.length; st2.i = a.f.indexOf(ks[p]); st2.draw(); };
      const goFrame = d => { setPlay(false); st2.i = (st2.i + d + a.f.length) % a.f.length; st2.draw(); };
      const bBox = h('button', { type: 'button', 'aria-pressed': 'true', text: '✓ Boxes' });
      bBox.onclick = () => { st2.boxes = !st2.boxes; bBox.setAttribute('aria-pressed', String(st2.boxes)); bBox.textContent = (st2.boxes ? '✓ ' : '') + 'Boxes'; st2.draw(); };
      const tbl = h('table', {}, h('thead', {}, h('tr', {}, ['#', 'addr', 'ticks', 'boxes [type left right bottom top] px', 'sound', 'command'].map(t => h('th', { text: t })))),
        h('tbody', {}, a.steps.map((s, j) => { const r = h('tr', {}, [String(j), s.a, String(s.t), s.b.map(b => ({ a: 'ATK', h: 'body', p: 'push', x: 'other' })[b[0]] + ' $' + b[1].toString(16).toUpperCase() + ' ' + b.slice(2).join(' ')).join('; ') || '-', s.s || '-', s.m || '-'].map(t => h('td', { text: t }))); r.onclick = () => { setPlay(false); const i = a.f.indexOf(j); if (i >= 0) { st2.i = i; st2.draw(); } }; rows.push(r); return r; })));
      kids.push(pl.cv, h('div', { class: 'ctl' }, bPlay, bSlow, h('button', { type: 'button', text: '◀ Step', onclick: () => goStep(-1) }), h('button', { type: 'button', text: 'Step ▶', onclick: () => goStep(1) }),
        h('button', { type: 'button', text: '◀ Frame', onclick: () => goFrame(-1) }), h('button', { type: 'button', text: 'Frame ▶', onclick: () => goFrame(1) }), bBox), fc,
        h('div', { class: 'ctl' }, window.TryIt ? window.TryIt.button(f, 'Try in game', () => window.TryIt.queue(f, [a.id]), () => ({ queue: [a.id], loop: window.TryIt.loop() })) : null,
          h('button', { type: 'button', text: '+ Add to the queue', onclick: e => { tq.push(a.id); drawQ(); e.target.textContent = '+ Add to the queue (' + tq.length + ' in it)'; } })),
        h('p', { class: 'legend', text: 'Boxes: attack = thick solid line, body = dashed, push = dotted, other ($33) = dash-dot. The floor line is under the feet; x forward, up positive.' }));
      st2.draw();
      kids.push(h('h3', { text: 'Steps' }), h('div', { class: 'steps' }, tbl));
    } else kids.push(h('p', { text: a.status === 'ok' ? 'No frames.' : 'This animation is ' + a.status + (a.error ? ': ' + a.error : '') + '.' }));
    const row = (k, v) => [h('dt', { text: k }), h('dd', { text: v })];
    kids.push(h('h3', { text: 'Data' }), h('dl', { class: 'meta' },
      row('Index', '$' + a.id + ' (' + a.n + ')' + (a.slots && a.slots.length > 1 ? ', also slots ' + a.slots.slice(1).join(' ') : '')), a.states ? row('Game states', a.states.join(' ') || 'none') : null, row('What', a.desc || '-'), row('Frames', a.frames + ' (' + (a.steps || []).length + ' steps' + (a.end ? ', ' + a.end : '') + ')'),
      row('Moves', (a.moves || []).join(', ') || 'none captured'), row('Reactions', (a.reactions || []).join(', ') || '-'),
      row('In the brawler', (a.exported || []).join(', ') || 'not exported'), row('Sounds', (a.sounds || []).join(' ') || '-'),
      row('Palettes', (a.pals || []).join(', ')), row('Travel', (a.travel || 0) + ' px by step commands' + (a.rises ? ', rises' : ''))));
    // the answer: I want this one + flags + note
    const ans = D.ans[a.id] || {};
    const saved = h('div', { class: 'dsaved', text: ans.at ? 'Saved' : '' });
    const sv = async body => { saved.textContent = 'Saving…'; try { await AD.save(D, a.id, body); saved.textContent = 'Saved'; } catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; } };
    const want = h('button', { type: 'button', class: 'want', 'aria-pressed': String(ans.choice === 0) });
    const wtxt = () => { const on = (D.ans[a.id] || {}).choice === 0; want.setAttribute('aria-pressed', String(on)); want.textContent = (on ? '✓ ' : '○ ') + 'I want this one'; };
    wtxt();
    want.onclick = () => { const on = (D.ans[a.id] || {}).choice === 0; D.ans[a.id] = Object.assign({}, D.ans[a.id], { choice: on ? null : 0 }); wtxt(); sv({ choice: on ? null : 0, label: on ? null : 'I want this one' }); };
    const ta = h('textarea', { 'aria-label': 'Note for animation $' + a.id, placeholder: 'Note (type or speak)' }); ta.value = ans.note || '';
    let t; ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => { D.ans[a.id] = Object.assign({}, D.ans[a.id], { note: ta.value }); sv({ note: ta.value }); }, 700); });
    kids.push(h('h3', { text: 'Your answer' }), want, h('h3', { text: 'Flags' }), AD.flagEditor(D, a), h('div', { class: 'dnote' }, window.micNote ? window.micNote(ta) : ta), saved);
    const dlg = h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Animation $' + a.id },
      h('div', { class: 'mbox' }, h('div', { class: 'mhead' }, h('b', { text: AD.caption(a) }), h('button', { type: 'button', text: 'Close', onclick: close })), kids));
    dlg.onclick = e => { if (e.target === dlg) close(); };
    document.addEventListener('keydown', esc);
    document.body.append(dlg);
    window.dictOpen = a.id;
  }
})();
