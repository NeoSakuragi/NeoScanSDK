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
  async function post(set, body) {
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(Object.assign({ set }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
  }
  async function load() {
    if (loaded) return; loaded = true;
    let D;
    try { D = await (await fetch('decisions.json', { cache: 'no-cache' })).json(); } catch (e) { col.replaceChildren(h('p', { text: 'No decisions yet.' })); return; }
    const parts = [h('h2', { text: 'Decisions' })];
    for (const set of D.sets) {
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
        const btns = q.options.map((o, i) => {
          const b = h('button', { type: 'button', 'aria-pressed': String(a.choice === i) }, h('span', { class: 'mark', text: a.choice === i ? '✓' : '○' }), h('span', { text: o }));
          b.onclick = () => {
            btns.forEach((x, j) => { x.setAttribute('aria-pressed', String(i === j)); x.querySelector('.mark').textContent = i === j ? '✓' : '○'; });
            save({ choice: i, label: o });
          };
          return b;
        });
        const ta = h('textarea', { 'aria-label': 'Note for: ' + q.title, placeholder: 'Note (type or speak)' });
        ta.value = a.note || '';
        let t; ta.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => save({ note: ta.value }), 700); });
        return h('section', { class: 'dq' }, h('h3', { text: q.title }), q.context ? h('p', { class: 'dctx', text: q.context }) : null,
          h('div', { class: 'dopts' }, btns), h('div', { class: 'dnote' }, ta, window.micNote ? window.micNote(ta) : null), saved);
      };
      const general = { id: 'general', title: 'Anything else for this topic?', options: [] };
      parts.push(h('section', { class: 'dset' }, h('h2', { text: set.title }), h('p', { text: set.intro || '' }), status,
        set.sections.map(s => [h('h3', { class: 'dsec', text: s.title }), s.questions.map(card)]), card(general)));
      count();
    }
    col.replaceChildren(...parts);
  }
  tab.onclick = () => window.labTab('decide');
  window.addEventListener('labtab', e => { if (e.detail === 'decide') load(); });
  const deep = () => { if (location.hash === '#decide') { window.labTab('decide'); load(); } };
  window.addEventListener('hashchange', deep);
  if (document.readyState === 'complete') setTimeout(deep, 300); else window.addEventListener('load', () => setTimeout(deep, 300));
})();
