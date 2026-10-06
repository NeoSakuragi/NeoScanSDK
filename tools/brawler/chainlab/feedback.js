/* Brawler Lab, Feedback tab: the NeoScan Player's voice / text feedback (docs/feedback.md). The list comes from the
 * feedback service's API (tools/feedback/server.py) at feedback-api/ (nginx, behind the same Oros login as the Lab):
 * date, versions, the note as sent (the raw transcript under it), status and release as text, the voice (play),
 * the screenshot; filters by status and category; category (dropdown) and fighters editable here. Status changes go
 * through tools/feedback/fb.py. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  while (!window.stagesTab && !window.labTab) await new Promise(r => setTimeout(r, 100));
  const API = 'feedback-api/';
  const STATUS_TEXT = { new: 'NEW', read: 'read', in_progress: 'IN PROGRESS', shipped: 'SHIPPED', wont_do: "won't do", duplicate: 'duplicate' };
  let rows = [], cats = [], filt = { status: '', category: '' }, msg = '';
  const col = $('fbcol');

  async function load() {
    try {
      const r = await fetch(API + 'list', { cache: 'no-store', credentials: 'same-origin' });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json(); rows = j.rows; cats = j.categories; msg = '';
    } catch (e) { msg = 'The feedback list is unavailable (' + e.message + ').'; }
    render();
  }

  async function set(id, body) {
    try {
      const r = await fetch(API + 'set', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
                                           body: JSON.stringify(Object.assign({ id }, body)) });
      const j = await r.json();
      if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      rows = rows.map(x => x.id === id ? j.row : x); msg = 'Saved ' + id + '.';
    } catch (e) { msg = 'Not saved: ' + e.message; }
    render();
  }

  function play(btn, r) {
    const old = btn.parentNode.querySelector('audio');
    if (old) { old.remove(); btn.textContent = '▶ Play'; return; }
    const a = h('audio', { controls: true, src: API + 'file/' + r.id + '/' + r.audio_path, preload: 'auto' });
    btn.after(a); btn.textContent = '■ Close'; a.play().catch(() => {});
  }

  function render() {
    if (!col) return;
    col.textContent = '';
    const sel = (key, opts) => h('select', { onchange: e => { filt[key] = e.target.value; render(); } },
      h('option', { value: '' }, 'all'), opts.map(o => h('option', { value: o, selected: filt[key] === o }, key === 'status' ? STATUS_TEXT[o] : o)));
    const shown = rows.filter(r => (!filt.status || r.status === filt.status) && (!filt.category || r.category === filt.category));
    col.append(h('div', { class: 'box' },
      h('h2', {}, 'Feedback from the player', h('span', { class: 'sp' }),
        h('label', {}, 'Status ', sel('status', Object.keys(STATUS_TEXT))), h('label', {}, 'Category ', sel('category', cats)),
        h('button', { onclick: load }, 'Reload')),
      h('div', { class: 'in' },
        msg ? h('p', { class: 'ok' }, msg) : null,
        h('p', { class: 'note' }, `${shown.length} of ${rows.length}. Status: NEW → read (pulled) → IN PROGRESS → SHIPPED (release) | won't do | duplicate; set with tools/feedback/fb.py.`),
        h('table', { class: 'fb' },
          h('tr', {}, ['When / id', 'Versions', 'Note', 'Status', 'Category / fighters', 'Voice / picture'].map(t => h('th', {}, t))),
          shown.map(r => h('tr', {},
            h('td', { class: 'mono' }, r.created.slice(0, 16).replace('T', ' '), h('br'), r.id),
            h('td', {}, 'player ' + r.apk_version, h('br'), 'game v' + r.game_version, h('br'), h('span', { class: 'small' }, r.device)),
            h('td', { class: 'txt' }, h('div', {}, r.final_text || '(no text typed)'),
              r.raw_transcript && !(r.final_text || '').includes(r.raw_transcript) ? h('div', { class: 'small' }, 'transcript: ' + r.raw_transcript) : null,
              r.notes ? h('div', { class: 'small' }, 'notes: ' + r.notes) : null),
            h('td', {}, h('b', {}, STATUS_TEXT[r.status] || r.status), r.status === 'shipped' ? h('div', {}, 'in ' + r.release) : null,
              r.status === 'duplicate' ? h('div', { class: 'small' }, 'of ' + r.duplicate_of) : null),
            h('td', {},
              h('select', { onchange: e => set(r.id, { category: e.target.value }) },
                h('option', { value: '' }, '(none)'), cats.map(c => h('option', { value: c, selected: r.category === c }, c))),
              h('br'),
              h('input', { type: 'text', value: r.fighters, placeholder: 'fighters: geese,terry', size: 16,
                           onchange: e => set(r.id, { fighters: e.target.value }) })),
            h('td', {},
              r.audio_path ? h('button', { onclick: e => play(e.target, r) }, '▶ Play') : h('span', { class: 'small' }, 'no voice'),
              h('br'), h('a', { href: API + 'file/' + r.id + '/screen.png', target: '_blank' }, 'screenshot'))))))));
  }

  const tab = $('tabFeedback');
  if (tab) tab.onclick = () => window.labTab('feedback');
  window.addEventListener('labtab', e => { if (e.detail === 'feedback') load(); });
})();
