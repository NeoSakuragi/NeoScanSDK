// sounds.html?f=kim: every hit of the fighter's chain / finishers / hold with the sound the game plays on it now
// (sounds/<f>/hits.json, tools/brawler/hitsounds.py), each sound of the ROM (sounds/sfx.json + sounds/sfx/<code>.wav).
// A pick is saved to the decisions store (POST feedback-api/decision, set "<f>-sounds", id = the hit's key, choice = the
// code, label = its name); notes the same way (micnote.js). One AudioContext, resumed on the first tap (Android Chrome).
(async function () {
  const col = document.getElementById('col');
  const F = (new URLSearchParams(location.search).get('f') || 'kim').replace(/[^a-z_]/g, '');
  const SET = F + '-sounds', API = 'feedback-api/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  let SFX, HITS, ans = {};
  try {
    [SFX, HITS] = await Promise.all([fetch('sounds/sfx.json', { cache: 'no-cache' }).then(r => r.json()), fetch(`sounds/${F}/hits.json`, { cache: 'no-cache' }).then(r => r.json())]);
  } catch (e) { col.replaceChildren(h('p', { text: `No hit sounds for "${F}" yet.` })); return; }
  try { const r = await fetch(API + 'decisions/' + SET, { cache: 'no-store', credentials: 'same-origin' }); if (r.ok) ans = await r.json(); } catch (e) { /* offline */ }
  const byCode = Object.fromEntries(SFX.map(s => [s.code, s]));
  const name = c => byCode[c] ? `$${c} ${byCode[c].name}` : `$${c}`;

  // audio: one context, buffers cached, one sound at a time; a button shows "Playing" while its sound plays
  let ctx = null, src = null, onBtn = null;
  const bufs = {};
  const unlock = () => {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume();
  };
  document.addEventListener('pointerdown', unlock, { once: true, capture: true });
  const load = c => bufs[c] || (bufs[c] = fetch(`sounds/sfx/${c}.wav`).then(r => r.arrayBuffer()).then(a => new Promise((ok, ko) => ctx.decodeAudioData(a, ok, ko))));
  const ICON_PLAY = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5v13l11-6.5z"/></svg>';
  const ICON_STOP = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="3" width="10" height="10"/></svg>';
  const mark = (b, on, label) => { b.dataset.on = on ? '1' : '0'; b.innerHTML = (on ? ICON_STOP : ICON_PLAY) + `<span>${on ? 'Playing' : label}</span>`; };
  async function play(code, btn, label) {
    unlock();
    if (src) { try { src.stop(); } catch (e) { } src = null; }
    if (onBtn) { mark(onBtn.b, false, onBtn.label); onBtn = null; }
    if (!code) return;
    try {
      const buf = await load(code);
      const s = ctx.createBufferSource(); s.buffer = buf; s.connect(ctx.destination);
      src = s; onBtn = { b: btn, label }; mark(btn, true, label);
      s.onended = () => { if (src === s) { src = null; mark(btn, false, label); onBtn = null; } };
      s.start();
    } catch (e) { btn.querySelector('span').textContent = 'Cannot play'; }
  }
  const playBtn = (label, get) => { const b = h('button', { type: 'button', class: 'play' }); mark(b, false, label); b.onclick = () => play(get(), b, label); return b; };

  async function post(body) {
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ set: SET }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  }
  const status = h('div', { class: 'status' });
  const count = () => { status.textContent = `${HITS.filter(x => ans[x.key] && ans[x.key].choice && ans[x.key].choice !== x.sound[0]).length} of ${HITS.length} hits changed`; };

  const opts = sel => {
    const grp = (label, list) => h('optgroup', { label }, list.map(s => h('option', { value: s.code, text: `$${s.code} ${s.name}` })));
    sel.append(grp('Hits and impacts', SFX.filter(s => s.impact)), grp('Other sounds (swings, throws, flashes)', SFX.filter(s => !s.impact)));
  };
  const card = x => {
    const a = ans[x.key] || {};
    const cur = x.sound[0] || '';
    const saved = h('div', { class: 'saved', 'aria-live': 'polite', text: a.choice ? `Saved: ${name(a.choice)}` : '' });
    const q = `${x.title}: hit ${x.hit} of ${x.move}`;
    const save = async body => {
      ans[x.key] = Object.assign({}, ans[x.key], body); count();
      try { await post(Object.assign({ id: x.key, question: q, current: cur }, body)); saved.textContent = body.choice !== undefined ? `Saved: ${name(body.choice)}${body.choice === cur ? ' (the current one)' : ''}` : 'Saved'; }
      catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; }
    };
    const sel = h('select', { 'aria-label': 'Sound for ' + q }); opts(sel);
    sel.value = a.choice || cur;
    sel.onchange = () => { save({ choice: sel.value, label: byCode[sel.value].name }); play(sel.value, tryBtn, 'Play choice'); };
    const tryBtn = playBtn('Play choice', () => sel.value);
    const ta = h('textarea', { 'aria-label': 'Note for ' + q, placeholder: 'Note (type or speak)' });
    ta.value = a.note || '';
    let t; ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => save({ note: ta.value }), 700); });
    return h('section', { class: 'hit', id: x.key },
      h('img', { src: `sounds/${F}/${x.img}`, alt: `${F}'s ${x.move} hitting the dummy (impact frame)`, width: 200, height: 164, loading: 'lazy' }),
      h('h4', { text: `Hit ${x.hit} of ${x.move}` + (x.of > 1 ? ` (${x.of} hits)` : '') }),
      h('p', { class: 'meta', text: `${x.title} · damage ${x.dmg} · the dummy: ${x.victim.toLowerCase()}` }),
      h('div', { class: 'cur' }, playBtn('Play current', () => cur), h('span', { text: 'Now: ' + (cur ? name(cur) : 'no sound') + (x.sound.length > 1 ? ` + ${x.sound.slice(1).map(name).join(' + ')}` : '') })),
      h('div', { class: 'row' }, sel, tryBtn),
      saved, window.micNote ? window.micNote(ta) : ta);
  };
  const GROUPS = [['Chain', ['chain']], ['Finishers', ['fwd', 'up', 'down', 'back']], ['Hold', ['hold']]];
  const parts = [h('h1', { text: `${F[0].toUpperCase() + F.slice(1)}: hit sounds` }),
    h('p', { class: 'intro', text: 'Every hit as the game plays it now: the impact frame, the sound sent on it. Play the current one; pick another in the list (it plays at once, and is saved). The note takes your voice.' }),
    status];
  for (const [g, keys] of GROUPS) {
    parts.push(h('h2', { class: 'grp', text: g }));
    for (const k of keys) {
      const hs = HITS.filter(x => x.group === k);
      if (!hs.length) continue;
      if (keys.length > 1) parts.push(h('h3', { class: 'sub', text: hs[0].title }));
      parts.push(hs.map(card));
    }
  }
  col.replaceChildren(...parts.flat());
  count();
})();
