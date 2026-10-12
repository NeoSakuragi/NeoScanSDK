// "Decisions" tab: question sets (decisions.json) Bruno answers in the Lab — outcome buttons, a note with the microphone
// (micnote.js -> /api/transcribe), saved to the feedback service (POST /api/decision, GET /api/decisions/<set>), which I
// read back. Black on white, solid borders; the chosen answer is filled AND marked ✓ (e-ink).
(async function () {
  const $ = id => document.getElementById(id);
  const tab = $('tabDecide'), col = $('decidecol');
  if (!tab || !col) return;
  const API = 'feedback-api/';
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else e.setAttribute(k, v); } for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  let loaded = false;
  // media of a question or an option (decisions.json "media": [{image | video | audio: URL, caption}]): pixel-exact
  // pictures, looping muted clips (tap: pause / play), audio players; files under decisions-media/<set>/
  const media = list => h('div', { class: 'dmedia' }, (Array.isArray(list) ? list : [list]).map(m => {
    let el;
    if (m.video) { el = h('video', { src: m.video, muted: '', loop: '', autoplay: '', playsinline: '', preload: 'auto' }); el.muted = true; el.onclick = () => el.paused ? el.play() : el.pause(); }
    else if (m.image) el = h('img', { src: m.image, alt: m.caption || '' });
    else if (m.audio) el = h('audio', { src: m.audio, controls: '', preload: 'none' });
    return h('figure', { class: m.audio ? 'daudio' : '' }, el, m.caption ? h('figcaption', { text: m.caption }) : null);
  }));
  const only = new URLSearchParams(location.search).get('set');   // game.html?set=<id>#decide: that set alone
  const NONE = 'None of these: my own answer in the note';
  async function post(set, body) {
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ set }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  }
  async function load() {
    if (loaded) return; loaded = true;
    let D;
    try { D = await (await fetch('decisions.json', { cache: 'no-cache' })).json(); } catch (e) { col.replaceChildren(h('p', { text: 'No decisions yet.' })); return; }
    const parts = [h('h2', { text: 'Decisions' })];
    for (const set of D.sets.filter(x => !only || x.id === only)) {
      let ans = {};
      try { const r = await fetch(API + 'decisions/' + set.id, { cache: 'no-store', credentials: 'same-origin' }); if (r.ok) ans = await r.json(); } catch (e) { /* offline */ }
      const total = set.sections.reduce((n, s) => n + s.questions.length, 0);
      const status = h('div', { class: 'dstatus' });
      const count = () => { status.textContent = `${Object.values(ans).filter(a => a && a.choice != null).length} of ${total} answered`; };
      const card = q => {
        const a = ans[q.id] || {};
        const saved = h('div', { class: 'dsaved', text: a.at ? 'Saved' : '' });
        const save = async body => {
          ans[q.id] = Object.assign({}, ans[q.id], body); count();
          try { await post(set.id, Object.assign({ id: q.id, question: q.title }, body)); saved.textContent = 'Saved'; }
          catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; }
        };
        // an option: a label, or {label, media}: media shown above its button (what that answer looks / sounds like)
        const opts = q.options.length ? q.options.concat([NONE]) : [];   // every question: a "none of these" way out (Bruno)
        const lab = o => typeof o === 'string' ? o : o.label;
        const btns = opts.map((o, i) => {
          const b = h('button', { type: 'button', 'aria-pressed': String(a.choice === i) }, h('span', { class: 'mark', text: a.choice === i ? '✓' : '○' }), h('span', { text: lab(o) }));
          b.onclick = () => {
            btns.forEach((x, j) => { x.setAttribute('aria-pressed', String(i === j)); x.querySelector('.mark').textContent = i === j ? '✓' : '○'; });
            save({ choice: i, label: lab(o) });
            if (o === NONE) ta.focus();
          };
          return b;
        });
        const optEls = opts.map((o, i) => o.media ? h('div', { class: 'dopt' }, media(o.media), btns[i]) : btns[i]);
        const ta = h('textarea', { 'aria-label': 'Note for: ' + q.title, placeholder: 'Note (type or speak)' });
        ta.value = a.note || '';
        let t; ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => save({ note: ta.value }), 700); });
        return h('section', { class: 'dq' }, h('h3', { text: q.title }), q.context ? h('p', { class: 'dctx', text: q.context }) : null,
          q.media ? media(q.media) : null, h('div', { class: opts.some(o => o.media && [].concat(o.media).some(m => m.video || m.image)) ? 'dopts dgrid' : 'dopts' }, optEls), h('div', { class: 'dnote' }, window.micNote ? window.micNote(ta) : ta), saved);
      };
      const general = { id: 'general', title: 'Anything else for this topic?', options: [] };
      // answered questions are hidden (Bruno 2026-10-12: "hide the questions that have been answered"); one button shows them
      const done = q => ans[q.id] && ans[q.id].choice != null;
      const nDone = set.sections.reduce((n, s) => n + s.questions.filter(done).length, 0);
      const old = h('div', { class: 'danswered', hidden: true },
        set.sections.map(s => s.questions.some(done) ? [h('h3', { class: 'dsec', text: s.title }), s.questions.filter(done).map(card)] : []));
      const showOld = nDone ? h('button', { type: 'button', class: 'dshowold', text: `Show the ${nDone} answered question${nDone > 1 ? 's' : ''}` }) : null;
      if (showOld) showOld.onclick = () => { old.hidden = !old.hidden; showOld.textContent = (old.hidden ? 'Show' : 'Hide') + ` the ${nDone} answered question${nDone > 1 ? 's' : ''}`; };
      const open = set.sections.map(s => s.questions.some(q => !done(q)) ? [h('h3', { class: 'dsec', text: s.title }), s.questions.filter(q => !done(q)).map(card)] : []);
      parts.push(h('section', { class: 'dset' }, h('h2', { text: set.title }), h('p', { text: set.intro || '' }),
        set.fighter ? h('p', {}, h('a', { href: 'lab.html?tab=review&f=' + set.fighter + '&q=' + set.id, text: 'Answer these with the clips (recommended)' })) : null, status,
        nDone === set.sections.reduce((n, s) => n + s.questions.length, 0) ? h('p', { text: 'Every question here is answered.' }) : null,
        open, card(general), showOld, old));
      count();
    }
    col.replaceChildren(...parts);
  }
  tab.onclick = () => window.labTab('decide');
  window.addEventListener('labtab', e => { if (e.detail === 'decide') load(); });
  // (game.html#decide opens this tab: game.js)
})();
