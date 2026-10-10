// The Game tools' "Impact sounds" tab (game.html#impacts, loaded by game.js; impacts.html redirects there): the impact sound library (impacts/impacts.json, tools/brawler/impacts.py). One card per distinct sample;
// Keep / Discard saved to the decisions store (POST feedback-api/decision, set "impact-sounds", id = the sample's id,
// choice "keep" / "discard"), the note the same way (micnote.js). Filters: game, judged state. One AudioContext,
// created and resumed on the first tap (Android Chrome), one sound at a time.
(async function () {
  const col = document.getElementById('impactcol');
  const SET = 'impact-sounds', API = 'feedback-api/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  let J, ans = {};
  try { J = await (await fetch('impacts/impacts.json', { cache: 'no-cache' })).json(); }
  catch (e) { col.replaceChildren(h('p', { text: 'The impact sound list is not on the site yet.' })); return; }
  try { const r = await fetch(API + 'decisions/' + SET, { cache: 'no-store', credentials: 'same-origin' }); if (r.ok) ans = await r.json(); } catch (e) { /* offline */ }
  const GAMES = { kof94: "KOF '94", kof95: "KOF '95", kof96: "KOF '96", kizuna: 'Kizuna Encounter' };
  const S = J.sounds;

  // audio
  let ctx = null, src = null, onBtn = null;
  const bufs = {};
  const unlock = () => {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    if (ctx.state === 'suspended') ctx.resume();
  };
  document.addEventListener('pointerdown', unlock, { once: true, capture: true });
  const load = id => bufs[id] || (bufs[id] = fetch(`impacts/wav/${id}.wav`).then(r => { if (!r.ok) throw new Error(r.status); return r.arrayBuffer(); }).then(a => new Promise((ok, ko) => ctx.decodeAudioData(a, ok, ko))));
  const ICON_PLAY = '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3 1.5v13l11-6.5z"/></svg>';
  const ICON_STOP = '<svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3" y="3" width="10" height="10"/></svg>';
  const mark = (b, on) => { b.dataset.on = on ? '1' : '0'; b.innerHTML = (on ? ICON_STOP : ICON_PLAY) + `<span>${on ? 'Playing' : 'Play'}</span>`; };
  async function play(id, btn) {
    unlock();
    const again = onBtn && onBtn === btn;
    if (src) { try { src.stop(); } catch (e) { } src = null; }
    if (onBtn) { mark(onBtn, false); onBtn = null; }
    if (again) return;                                   // a second tap stops it
    try {
      const buf = await load(id);
      const s = ctx.createBufferSource(); s.buffer = buf; s.connect(ctx.destination);
      src = s; onBtn = btn; mark(btn, true);
      s.onended = () => { if (src === s) { src = null; mark(btn, false); onBtn = null; } };
      s.start();
    } catch (e) { btn.querySelector('span').textContent = 'Cannot play'; }
  }

  async function post(body) {
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ set: SET }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  }
  const state = id => (ans[id] && ans[id].choice) || 'unjudged';
  const status = h('div', { class: 'status', 'aria-live': 'polite' });
  const count = () => {
    const k = S.filter(s => state(s.id) === 'keep').length, d = S.filter(s => state(s.id) === 'discard').length;
    status.textContent = `${S.length} sounds: ${k} kept, ${d} discarded, ${S.length - k - d} to judge`;
  };

  const title = s => s.entries[0].uses[0].what.replace(/ \(pan [LCR]\)$/, '').replace(/ \(random \d+ of \d+\)$/, '');
  const card = s => {
    const a = ans[s.id] || {};
    const q = `${title(s)} (${s.games.map(g => GAMES[g]).join(', ')})`;
    const saved = h('div', { class: 'saved', 'aria-live': 'polite', text: a.choice ? `Saved: ${a.choice === 'keep' ? 'Keep' : 'Discard'}` : '' });
    const sec = h('section', { class: 'card', id: 's-' + s.id });
    const save = async body => {
      ans[s.id] = Object.assign({}, ans[s.id], body); count();
      sec.dataset.state = state(s.id);
      try { await post(Object.assign({ id: s.id, question: q, words: s.entries.map(x => `${x.game} ${x.word}`) }, body)); saved.textContent = body.choice ? `Saved: ${body.label}` : 'Note saved'; }
      catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; }
      applyFilter();
    };
    const judge = (val, label) => {
      const on = a.choice === val;
      const b = h('button', { type: 'button', class: 'judge', 'aria-pressed': String(on) }, h('span', { class: 'mark', text: on ? '✓' : '○' }), h('span', { text: label }));
      b.onclick = () => {
        for (const x of jb) { const me = x === b; x.setAttribute('aria-pressed', String(me)); x.querySelector('.mark').textContent = me ? '✓' : '○'; }
        save({ choice: val, label });
      };
      return b;
    };
    const jb = [judge('keep', 'Keep'), judge('discard', 'Discard')];
    const pb = h('button', { type: 'button', class: 'play', 'aria-label': 'Play ' + q }); mark(pb, false); pb.onclick = () => play(s.id, pb);
    const byGame = {};
    for (const x of s.entries) (byGame[x.game] = byGame[x.game] || []).push(x);
    const codes = Object.entries(byGame).map(([g, xs]) => `${GAMES[g]}: ` + xs.map(x => '$' + x.word).join(' ')).join(' · ');
    const vrom = s.ssg ? 'none (an SSG sequence, captured in our emulator)' : Object.entries(byGame).map(([g, xs]) => `${GAMES[g]}: ` + xs[0].vrom.map(v => `${v[0]}-${v[1]}`).join(' + ')).join(' · ');
    const uses = [];
    for (const x of s.entries) for (const u of x.uses) uses.push(h('li', {}, `${GAMES[x.game]} `, h('span', { class: 'w', text: '$' + x.word }), `: ${u.what}. `, h('span', { class: 'w', text: u.where + (u.sites.length ? ' (sent at ' + u.sites.slice(0, 4).join(' ') + (u.sites.length > 4 ? ' …' : '') + ')' : '') })));
    const list = uses.length > 3 ? [h('ul', { class: 'uses' }, uses.slice(0, 3)), h('details', {}, h('summary', { text: `${uses.length - 3} more uses` }), h('ul', { class: 'uses' }, uses.slice(3)))] : h('ul', { class: 'uses' }, uses);
    const ta = h('textarea', { 'aria-label': 'Note for ' + q, placeholder: 'Comment (type or speak)' });
    ta.value = a.note || '';
    let t; ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => save({ note: ta.value }), 700); });
    sec.dataset.state = state(s.id); sec.dataset.games = s.games.join(' ');
    sec.append(...[h('h2', { text: title(s) }),
      s.kof98 ? h('p', { class: 'k98', text: `Same sample as ${s.kof98} (the brawler's name)` }) : null,
      h('div', { class: 'row' }, pb, jb),
      h('dl', { class: 'facts' }, h('dt', { text: 'Game' }), h('dd', { text: s.games.map(g => GAMES[g]).join(', ') }),
        h('dt', { text: 'Driver code' }), h('dd', { text: codes }),
        h('dt', { text: 'V ROM' }), h('dd', { text: vrom }),
        h('dt', { text: 'Length' }), h('dd', { text: `${s.ms} ms` })),
      list, saved, window.micNote ? window.micNote(ta) : ta].flat().filter(Boolean));
    return sec;
  };

  const fGame = h('select', { 'aria-label': 'Game' }, h('option', { value: '', text: 'All games' }), Object.entries(GAMES).map(([k, v]) => h('option', { value: k, text: v })));
  const fState = h('select', { 'aria-label': 'Judged' }, [['', 'All'], ['unjudged', 'To judge'], ['keep', 'Kept'], ['discard', 'Discarded']].map(([v, t]) => h('option', { value: v, text: t })));
  try { const p = JSON.parse(localStorage.getItem('impacts-filter') || '{}'); fGame.value = p.g || ''; fState.value = p.s || ''; } catch (e) { }
  const shown = h('p', { class: 'shown', 'aria-live': 'polite' });
  const cards = S.map(card);
  function applyFilter() {
    let n = 0;
    for (const c of cards) {
      const ok = (!fGame.value || c.dataset.games.split(' ').includes(fGame.value)) && (!fState.value || c.dataset.state === fState.value);
      c.hidden = !ok; n += ok;
    }
    shown.textContent = `Showing ${n} of ${cards.length}`;
    try { localStorage.setItem('impacts-filter', JSON.stringify({ g: fGame.value, s: fState.value })); } catch (e) { }
  }
  fGame.onchange = applyFilter; fState.onchange = applyFilter;
  const per = Object.entries(J.words_per_game).map(([g, n]) => `${GAMES[g]} ${n}`).join(', ');
  col.replaceChildren(h('h1', { text: 'Impact sounds' }),
    h('p', { class: 'intro', text: `Every hit and impact sound of KOF '94, KOF '95, KOF '96 and Kizuna Encounter, found in each game's program (the code that sends a sound on a hit, a guard, a fall, a throw, a KO) and decoded straight from the sound ROM. Driver codes per game: ${per}; identical samples are one card. Play, then Keep or Discard; the comment takes your voice.` }),
    status,
    h('div', { class: 'filters' }, h('label', {}, 'Game', fGame), h('label', {}, 'Show', fState)),
    shown, ...cards);
  count(); applyFilter();
})();
