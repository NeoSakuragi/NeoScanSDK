// A fighter's ARBITRATION sheet (arbitrage.html?f=kim, ?f=krauser, ?f=robert): the web version of Bruno's A4 sheet for Kim
// (/data/scans/brawler/kim_notes_231734.png -> docs/brawler_gold.md "Kim (fast)"). The workflow for every new fighter,
// in this order: chain combo, alternate finishers, Blitz, air Blitz, specials, air specials, air, hold / throws; the fury is
// a separate script (a note).
// Each slot: its input in game terms, the animation(s) it plays (small looping clips, tap = ¼ speed), "Pick animation"
// (the fighter's whole animation dictionary, attacks first, flag filter), "+ add after" (played back to back), a note
// with the microphone, "Clear". Pre-filled with what the game plays now (review/<fighter>_arb.json, tools/brawler/arbitrage.py).
// Answers: the decisions store, set "<fighter>-arb", one id per slot: choice 1 = his (pieces "anim-<hex>" in order, note);
// id "presses" = the chain's length; id "done" = "Done — send to Claude" (note = the whole sheet as text).
// Renamed slots: an answer saved under an old id is read under its new one while the new id has none (OLD_IDS).
(async function () {
  const AD = window.AnimDict, h = AD.h, API = 'feedback-api/';
  const root = document.getElementById('arb');
  const f = new URLSearchParams(location.search).get('f') || 'kim';
  const SET = f + '-arb';
  const SC = 0.6;                                  // one scale for every clip of the page (the picker's too)
  const [D, NOW] = await Promise.all([AD.load(f).catch(() => null),
    fetch('review/' + f + '_arb.json', { cache: 'no-cache', credentials: 'same-origin' }).then(r => r.ok ? r.json() : null, () => null)]);
  if (!D || !NOW) { root.replaceChildren(h('p', { text: 'No arbitration sheet for "' + f + '" (it needs an animation dictionary).' })); return; }
  let ans = {};
  try { const r = await fetch(API + 'decisions/' + SET, { cache: 'no-store', credentials: 'same-origin' }); if (r.ok) ans = await r.json(); } catch (e) { /* offline: the page still works, saves will say so */ }
  const OLD_IDS = { air_dda: 'air_bz_dd' };       // 2026-10-10: "down, down + A in the air" moved into the air Blitz section
  for (const [o, n] of Object.entries(OLD_IDS)) if (ans[o] && !ans[n]) ans[n] = ans[o];

  const clips = [];
  AD.clock(clips);
  const io = new IntersectionObserver(es => { for (const e of es) { const st = e.target._clip; if (!st) continue; st.visible = e.isIntersecting; if (e.isIntersecting) st.load(); } }, { rootMargin: '200px' });
  const watch = st => { clips.push(st); io.observe(st.cv); };
  const unwatch = st => { const i = clips.indexOf(st); if (i >= 0) clips.splice(i, 1); io.unobserve(st.cv); };

  // ---- the sheet's structure (the order is the workflow) ----
  const N0 = NOW.chain_len;
  const press = n => ({ id: 'a' + n, label: 'A press ' + n + (n === 1 ? ' (starter)' : '') });
  const SECTIONS = [
    { id: 'chain', title: '1. Chain combo', about: `A, A, A… on hits. ${NOW.archetype[0].toUpperCase() + NOW.archetype.slice(1)} archetype: ${N0} presses (fast 5, balanced 4, heavy 3). The last press is the neutral finisher.`, chain: true },
    { id: 'fin', title: '2. Alternate finishers', about: 'The last hit with a direction instead of the neutral one. A slot may play several animations back to back ("+ add after").', slots: [
      { id: 'fin_fwd', label: 'last hit + forward' }, { id: 'fin_up', label: 'last hit + up (launcher)' },
      { id: 'fin_down', label: 'last hit + down' }, { id: 'fin_df', label: 'last hit + down-forward' }, { id: 'fin_back', label: 'last hit + back (throw)' }] },
    { id: 'bz', title: '3. Blitz (free)', about: 'Double direction + A: free, no drive, a little recovery, not invincible. A slot may stay empty.', slots: [
      { id: 'bz_ff', label: 'forward, forward + A' }, { id: 'bz_dd', label: 'down, down + A' },
      { id: 'bz_uu', label: 'up, up + A' }, { id: 'bz_du', label: 'down, up + A' }] },
    { id: 'abz', title: '4. Air Blitz', about: 'Double direction + A while airborne: the ground Blitz\'s inputs in a jump. A slot may stay empty.', slots: [
      { id: 'air_bz_ff', label: 'forward, forward + A in the air' }, { id: 'air_bz_dd', label: 'down, down + A in the air' },
      { id: 'air_bz_uu', label: 'up, up + A in the air' }, { id: 'air_bz_du', label: 'down, up + A in the air' }] },
    { id: 'sp', title: '5. Specials (C, 1 drive chunk)', about: 'C or A+B with a direction; invincible. C neutral is also the combo breaker (C while being hit).', slots: [
      { id: 'sp_c', label: 'C (neutral, also the combo breaker)' }, { id: 'sp_fc', label: 'forward + C' }, { id: 'sp_dc', label: 'down + C' }] },
    { id: 'asp', title: '6. Air specials (C in the air, 1 drive chunk)', about: 'C with a direction while airborne, like the ground C specials.', slots: [
      { id: 'air_sp_c', label: 'C in the air' }, { id: 'air_sp_fc', label: 'forward + C in the air' }, { id: 'air_sp_dc', label: 'down + C in the air' }] },
    { id: 'air', title: '7. Air', about: 'The two air normals: the jump attack (knocks down), down + A (flinches, active the rest of the jump).', slots: [
      { id: 'air_a', label: 'jump + A' }, { id: 'air_da', label: 'jump + down + A' }] },
    { id: 'grab', title: '8. Grab', about: 'Walk into an enemy: the hold. A hits him in the hold; the finisher throws him out; forward / back + C in the hold = the throws.', slots: [
      { id: 'grab_hit', label: 'hold hit (A in the hold)' }, { id: 'grab_fin', label: 'hold finisher (the throw-out)' },
      { id: 'grab_fwd', label: 'throw forward' }, { id: 'grab_back', label: 'throw back' }] },
    { id: 'fury', title: '9. Fury', about: 'The fury is a separate script: say what it should do here; point at its animations if you want.', slots: [
      { id: 'fury_note', label: 'fury: what it does', noAnim: true }, { id: 'fury', label: 'fury (D, gauge full)' }, { id: 'max', label: 'MAX (down + D, low life)' }] },
  ];
  const allSlots = () => SECTIONS.flatMap(s => s.chain ? range(presses()).map(i => press(i + 1)) : s.slots);
  const range = n => [...Array(n).keys()];
  const presses = () => { const a = ans.presses; const n = a && a.choice === 1 ? parseInt(a.note, 10) : NaN; return n >= 1 && n <= 8 ? n : Math.max(N0, NOW.now._presses || 0); };

  // ---- a slot's state: his answer (choice 1) else what the game plays now ----
  const mine = id => !!(ans[id] && ans[id].choice === 1);
  const nowOf = id => NOW.now[id] || { pieces: [], text: '', moves: [] };
  const stateOf = id => mine(id) ? { pieces: (ans[id].pieces || []).map(p => p.replace(/^anim-/, '')).filter(p => D.by[p]), note: ans[id].note || '' }
                                 : { pieces: nowOf(id).pieces.filter(p => D.by[p]), note: '' };
  const name = id => { const a = D.by[id]; return a ? '$' + id + (a.exported[0] ? ' ' + a.exported[0] : a.moves && a.moves[0] ? ' ' + a.moves[0] : '') : '$' + id; };
  async function post(id, body) {
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ set: SET, id }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json().catch(() => ({}));
    ans[id] = j.answer || Object.assign({}, ans[id], body);
  }

  // ---- a clip: tap toggles ¼ speed ----
  function clip(hex, onRemove) {
    const a = D.by[hex];
    const fig = h('figure', { class: 'clip' });
    if (a && a.status === 'ok' && a.f.length) {
      const { cv, st } = AD.player(D, a, SC, { lazy: true });
      st.cv = cv; watch(st); fig._st = st;
      cv.title = 'Tap: ¼ speed';
      cv.onclick = () => { st.speed = st.speed === 1 ? 0.25 : 1; cap.textContent = name(hex) + (st.speed !== 1 ? ' · ¼' : ''); };
      fig.append(cv);
    }
    const cap = h('figcaption', { text: name(hex) });
    fig.append(cap);
    if (onRemove) fig.append(h('button', { type: 'button', class: 'rm', text: 'Remove', 'aria-label': 'Remove $' + hex, onclick: onRemove }));
    return fig;
  }

  // ---- one slot row ----
  function slotRow(def) {
    const id = def.id;
    const box = h('div', { class: 'slot', id: 'slot-' + id });
    const saved = h('div', { class: 'saved', 'aria-live': 'polite', text: mine(id) ? 'Saved' : '' });
    const ta = h('textarea', { rows: '1', 'aria-label': 'Note for ' + def.label, placeholder: def.noAnim ? 'What the fury does (type or speak)' : 'Info: "2 hits", "reset, no eject", "same as Blitz"…' });
    ta.value = stateOf(id).note;
    let shown = [];
    let tag = null;
    const save = async (pieces, quiet) => {
      saved.textContent = 'Saving…';
      try {
        await post(id, Object.assign({ question: `${D.display}: ${def.label}`, choice: 1, label: pieces.length ? 'picked' : 'empty',
          pieces: pieces.map(p => 'anim-' + p), note: ta.value }));
        saved.textContent = 'Saved';
      } catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; }
      if (quiet) { tag.textContent = 'yours'; tag.className = 'tag mine'; } else draw();     // a note: no redraw (keeps the focus)
    };
    const draw = () => {
      shown.forEach(unwatch); shown = [];
      const st = stateOf(id), his = mine(id), nw = nowOf(id);
      tag = h('span', { class: his ? 'tag mine' : 'tag', text: his ? 'yours' : 'now' });
      const kids = [h('div', { class: 'shead' }, h('span', { class: 'lab', text: def.label }), tag)], side = [];
      let left = null;
      if (!def.noAnim) {
        const nowLine = 'Now: ' + (nw.pieces.length ? nw.pieces.map(p => '$' + p).join(' then ') : 'nothing') + (nw.text ? ' · ' + nw.text : '');
        if (his || nw.text) kids.push(h('p', { class: 'nowtxt', text: nowLine }));
        const row = h('div', { class: 'clips' });
        if (!st.pieces.length) row.append(h('span', { class: 'empty', text: his ? 'Empty' : 'Nothing today' }));
        st.pieces.forEach((p, i) => {
          if (i) row.append(h('span', { class: 'then', text: '→', 'aria-label': 'then' }));
          const fg = clip(p, st.pieces.length > 1 ? () => save(st.pieces.filter((_, j) => j !== i)) : null);
          if (fg._st) shown.push(fg._st);
          row.append(fg);
        });
        side.push(h('div', { class: 'acts' },
          h('button', { type: 'button', text: 'Pick animation', onclick: () => picker(def, st.pieces, hex => save([hex])) }),
          h('button', { type: 'button', text: '+ add after', onclick: () => picker(def, st.pieces, hex => save(st.pieces.concat(hex)), true) }),
          h('button', { type: 'button', text: 'Clear', onclick: () => { ta.value = ''; save([]); } }),
          his ? h('button', { type: 'button', text: 'Back to now', onclick: async () => {
            saved.textContent = 'Saving…'; ta.value = '';
            try { await post(id, { choice: null, label: null, pieces: null, note: '' }); saved.textContent = 'Saved (back to now)'; } catch (e) { saved.textContent = 'Not saved (' + e.message + ')'; }
            draw(); } }) : null));
        left = row;
      }
      side.push(h('div', { class: 'note' }, noteField), saved);
      kids.push(left ? h('div', { class: 'sbody' }, left, h('div', { class: 'side' }, side)) : h('div', { class: 'side' }, side));
      box.replaceChildren(...kids);
    };
    let t;
    ta.addEventListener('input', () => { clearTimeout(t); saved.textContent = '…'; t = setTimeout(() => save(stateOf(id).pieces, true), 700); });
    const noteField = window.micNote ? window.micNote(ta) : ta;
    draw();
    return box;
  }

  // ---- the chain: its presses + add / remove ----
  function chainBlock() {
    const wrap = h('div', {});
    const draw = () => {
      const n = presses();
      const setN = async k => {
        try { await post('presses', { question: `${D.display}: chain length`, choice: 1, label: k + ' presses', note: String(k) }); } catch (e) { alert('Not saved: ' + e.message); }
        draw();
      };
      wrap.replaceChildren(...range(n).map(i => slotRow(press(i + 1))),
        h('div', { class: 'count' }, h('span', { text: `${n} presses` + (n !== N0 ? ` (the ${NOW.archetype} archetype has ${N0})` : '') }),
          n < 8 ? h('button', { type: 'button', text: '+ add a press', onclick: () => setN(n + 1) }) : null,
          n > 1 ? h('button', { type: 'button', text: 'Remove press ' + n, onclick: () => setN(n - 1) }) : null));
    };
    draw();
    return wrap;
  }

  // ---- the picker: every animation of the dictionary, attacks first ----
  const ORDER = D.anims.filter(a => a.status === 'ok' && a.f.length).sort((x, y) => (y.attack - x.attack) || (x.n - y.n));
  let pSlow = false, pAtk = true;
  const pFlags = new Set();
  function picker(def, cur, onPick, adding) {
    const own = [];
    const close = () => { dlg.remove(); document.removeEventListener('keydown', esc); own.forEach(unwatch); };
    const esc = e => { if (e.key === 'Escape') close(); };
    const shown = h('span', { class: 'pshown' });
    const q = h('input', { type: 'search', placeholder: 'Find $ id or move', 'aria-label': 'Find by animation id or move name' });
    const cards = ORDER.map(a => {
      const { cv, st } = AD.player(D, a, SC, { lazy: true });
      st.cv = cv; st.speed = pSlow ? 0.25 : 1; own.push(st); watch(st);
      cv.title = 'Tap: ¼ speed / full speed';
      cv.onclick = () => { st.speed = st.speed === 1 ? 0.25 : 1; };
      const card = h('div', { class: 'pcard' + (cur.includes(a.id) ? ' cur' : '') }, cv,
        h('div', { class: 'cap', text: AD.caption(a) + (cur.includes(a.id) ? ' · IN THIS SLOT' : '') }),
        h('button', { type: 'button', class: 'use', text: (adding ? 'Add $' : 'Use $') + a.id, onclick: () => { close(); onPick(a.id); } }));
      card._a = a; card._st = st;
      return card;
    });
    const apply = () => {
      const s = q.value.trim().replace(/^\$/, '').toUpperCase();
      let n = 0;
      for (const c of cards) {
        const a = c._a, fl = new Set(AD.flagsOf(D, a).list);
        const txt = (a.id + ' ' + a.exported.join(' ') + ' ' + (a.moves || []).join(' ')).toUpperCase();
        const ok = (!pAtk || a.attack || !!s) && [...pFlags].every(x => fl.has(x)) && (!s || a.id === s || txt.includes(s));
        c.hidden = !ok; if (ok) n++;
      }
      shown.textContent = `${n} of ${cards.length} shown`;
    };
    q.oninput = apply;
    const tog = (txt, on, fn) => { const b = h('button', { type: 'button', 'aria-pressed': String(on), text: (on ? '✓ ' : '') + txt }); b.onclick = () => { const v = fn(); b.setAttribute('aria-pressed', String(v)); b.textContent = (v ? '✓ ' : '') + txt; }; return b; };
    const bSlow = tog('¼ speed', pSlow, () => { pSlow = !pSlow; cards.forEach(c => { c._st.speed = pSlow ? 0.25 : 1; }); return pSlow; });
    const bAtk = tog('Attacks only', pAtk, () => { pAtk = !pAtk; apply(); return pAtk; });
    const flagBtns = AD.FLAGS.map(fg => tog(fg.id, pFlags.has(fg.id), () => { pFlags.has(fg.id) ? pFlags.delete(fg.id) : pFlags.add(fg.id); apply(); return pFlags.has(fg.id); }));
    const dlg = h('div', { class: 'pmodal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Pick an animation' },
      h('div', { class: 'pbox' },
        h('div', { class: 'phead' }, h('b', { text: (adding ? 'Add after the current ones in ' : 'Pick for ') + def.label }), q, bSlow, bAtk,
          h('button', { type: 'button', text: 'Close', onclick: close })),
        h('div', { class: 'frow', role: 'group', 'aria-label': 'Flags' }, h('span', { class: 'fl', text: 'With every flag (yours in the dictionary, else my suggestion)' }), flagBtns),
        shown, h('div', { class: 'pgrid' }, cards)));
    dlg.onclick = e => { if (e.target === dlg) close(); };
    document.addEventListener('keydown', esc);
    document.body.append(dlg);
    apply();
    window.arbPicker = def.id;
  }

  // ---- done ----
  const summary = () => allSlots().map(s => {
    const st = stateOf(s.id);
    return `${s.label}: ${s.noAnim ? '' : (st.pieces.map(p => '$' + p).join(' then ') || 'empty') + (mine(s.id) ? '' : ' (now)')}${st.note ? ' — ' + st.note : ''}`;
  }).join('\n');
  const doneMsg = h('div', { class: 'saved', 'aria-live': 'polite', text: ans.done && ans.done.choice === 0 ? 'Sent to Claude (' + (ans.done.at || '') + '). Changes after this are saved too; press again to resend.' : '' });
  const doneBtn = h('button', { type: 'button', class: 'done', text: 'Done — send to Claude' });
  doneBtn.onclick = async () => {
    doneMsg.textContent = 'Sending…';
    try { await post('done', { question: `${D.display}: arbitration sheet finished`, choice: 0, label: 'Done — send to Claude', note: summary() }); doneMsg.textContent = 'Sent to Claude. Changes after this are saved too; press again to resend.'; }
    catch (e) { doneMsg.textContent = 'Not sent (' + e.message + '): try again'; }
  };

  const out = [h('h1', { text: `${D.display}: arbitration sheet` }),
    h('p', { class: 'intro', text: `What each input plays, section by section: chain, alternate finishers, Blitz, air Blitz, specials, air specials, air, grab, fury. Every slot starts with what the game plays now (build ${NOW.version}, marked NOW); pick an animation from ${D.display}'s dictionary, add more to play back to back, or write / speak the info. Everything saves as you go. Tap a clip for ¼ speed.` }),
    h('div', { class: 'links' }, h('a', { href: 'anims.html?f=' + f, text: 'Animation dictionary' }), h('a', { href: 'review.html?f=' + f, text: 'Fighter review' }))];
  for (const s of SECTIONS) {
    out.push(h('h2', { text: s.title }), h('p', { class: 'about', text: s.about }));
    out.push(s.chain ? chainBlock() : s.slots.map(slotRow));
  }
  out.push(h('div', { class: 'final' }, h('span', { text: 'When the whole sheet is how you want it:' }), doneBtn, doneMsg));
  root.replaceChildren(...out.flat());
  window.arbReady = true;
})();
