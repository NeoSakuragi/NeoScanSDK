// A fighter's ARBITRATION sheet (the Fighter Lab's Assembly tab, lab.html?f=kim&tab=assembly, + &embed=1 in the Player: fighterlab.js loads this script into its #arb panel; arbitrage.html?f= redirects there): the web version of Bruno's A4 sheet for Kim
// (/data/scans/brawler/kim_notes_231734.png -> docs/brawler_gold.md "Kim (fast)"). The workflow for every new fighter,
// in this order: chain combo, alternate finishers, Blitz, air Blitz, specials, air specials, air, hold / throws, fury.
// TOKEN FREE (Bruno 2026-10-10, binding): the sheet has no channel to Claude. Every change here is compiled by the tooling
// alone (tools/brawler/arb_compile.py: links, knobs, build, per-slot check; it refuses and says why, never guesses). A
// question or a request goes to the Workshop (part 1, the token side): each slot's "Ask in the Workshop" opens it with a
// request pre-filled for that slot and piece. Old notes saved in <f>-arb stay on the server, never shown or read.
// Each slot: its input in game terms, the animation(s) it plays (small looping clips, tap = ¼ speed), "Pick animation"
// (the fighter's whole animation dictionary, attacks first, flag filter), "+ add after" (played back to back), "Clear",
// "Ask in the Workshop". Pre-filled with what the game plays now (review/<fighter>_arb.json, tools/brawler/arbitrage.py).
// Answers: the decisions store, set "<fighter>-arb", one id per slot: choice 1 = his (pieces "anim-<hex>" in order,
// knobs); id "presses" = the chain's length (its note = the count). "Ship to game" (admin): POST lab/ship/<f> (the ship
// queue, docs/character_lab.md "Character Lab") naming the live config's revision: the compiler builds, checks every slot and
// publishes, or says why it refused.
// Renamed slots: an answer saved under an old id is read under its new one while the new id has none (OLD_IDS).
// Piece ids (Workshop, review/<fighter>_workshop.json, tools/brawler/piece_ids.py): the picker offers the animations
// ($NN, saved "anim-<hex>") and the UNLOCKED pieces (S- specials, T- throws, saved as their id: arb_compile.py links an
// S- id as that special's input); locked specials are listed greyed with a link to the Workshop. "Now" shows the S- ids
// of the decoded specials a slot plays.
// PIECE KNOBS (knobui.js, tools/brawler/knobs.py): under each picked S- piece its knobs (W.specials[].knobs: name, unit,
// default, range); the values save in the slot's answer as knobs {S- id: {knob id: value}} (a default left out), travel
// with "Try this sheet" / "Send to Player" (the TRY blob's knob rows) and ship through arb_compile.py (game.json
// roster[].knobs). An overridden knob: bold value, "changed from N", solid border, "Back to default"; "Reset all knobs"
// per piece, per slot and for the whole sheet.
// CHAIN TIMING (the Chain Lab's chain tool folded in, 2026-10-10): under the chain's presses, per press its hit-stop and
// its move's segments (0.5x-2x) as knobs; saved as "chain_timing", sent in the chain override (load 5), shipped by
// arb_compile.py (game.json chain.hitstop + retime). See drawTiming.
(async function () {
  const AD = window.AnimDict, h = AD.h, API = 'feedback-api/';
  const root = document.getElementById('arb');
  const f = new URLSearchParams(location.search).get('f') || 'kim';
  const SET = f + '-arb';
  const SC = 0.6;                                  // one scale for every clip of the page (the picker's too)
  const getJ = u => fetch(u, { cache: 'no-cache', credentials: 'same-origin' }).then(r => r.ok ? r.json() : null, () => null);
  const [D, NOW, W] = await Promise.all([AD.load(f).catch(() => null), getJ('review/' + f + '_arb.json'), getJ('review/' + f + '_workshop.json')]);
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
    { id: 'fury', title: '9. Fury', about: 'A decoded fury / MAX version (S- piece) links here; a fury script of its own is a Workshop request ("Ask in the Workshop").', slots: [
      { id: 'fury', label: 'fury (D, gauge full)' }, { id: 'max', label: 'MAX (down + D, low life)' }] },
  ];
  const allSlots = () => SECTIONS.flatMap(s => s.chain ? range(presses()).map(i => press(i + 1)) : s.slots);
  const range = n => [...Array(n).keys()];
  const presses = () => { const a = ans.presses; const n = a && a.choice === 1 ? parseInt(a.note, 10) : NaN; return n >= 1 && n <= 8 ? n : Math.max(N0, NOW.now._presses || 0); };

  // ---- the Workshop's pieces: S- / T- id -> {id, name, input, anims, ...} ----
  const PIECES = {};
  for (const p of ((W && W.specials) || []).concat((W && W.throws) || [])) if (p.id) PIECES[p.id] = p;
  const isId = p => /^[ST]-\d{3,}$/.test(p);
  const fmtP = p => isId(p) ? p : '$' + p;
  // ---- a slot's state: his answer (choice 1) else what the game plays now ----
  const mine = id => !!(ans[id] && ans[id].choice === 1);
  const knobsOf = id => (mine(id) && ans[id].knobs) || {};
  const drawers = {};                              // slot id -> its draw (the sheet's "Reset all knobs" redraws them)
  const nowOf = id => NOW.now[id] || { pieces: [], text: '', moves: [] };
  const stateOf = id => mine(id) ? { pieces: (ans[id].pieces || []).map(p => p.replace(/^anim-/, '')).filter(p => D.by[p] || PIECES[p]) }
                                 : { pieces: nowOf(id).pieces.filter(p => D.by[p]), note: '' };
  const name = id => { if (PIECES[id]) return id + ' ' + PIECES[id].name; const a = D.by[id]; return a ? '$' + id + (a.exported[0] ? ' ' + a.exported[0] : a.moves && a.moves[0] ? ' ' + a.moves[0] : '') : '$' + id; };
  async function post(id, body) {
    const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(Object.assign({ set: SET, id }, body)) });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const j = await r.json().catch(() => ({}));
    ans[id] = j.answer || Object.assign({}, ans[id], body);
    if (id === 'presses' || /^a\d$/.test(id)) drawTiming();   // the chain's moves changed: its timing knobs follow
    autoLive(); goLive();
  }
  // NOTHING DROPPED SILENTLY (2026-10-10, note 20261010-210158-5d29): each slot whose pick cannot go live (Try in game, the
  // Player) says so next to it, "Can't go live: why" (TryIt.issues: the same checks the Send makes); the live line lists
  // what the last Send left out
  let goSeq = 0;
  async function goLive() {
    if (!window.TryIt || !window.TryIt.issues) return;
    const seq = ++goSeq;
    let is;
    try { is = await window.TryIt.issues(f, sheetNow()); } catch (e) { is = { _all: 'the game data could not be read (' + e.message + ')' }; }
    if (seq !== goSeq) return;
    root.querySelectorAll('.golive').forEach(e => e.remove());
    for (const [id, why] of Object.entries(is)) {
      const box = root.querySelector('#slot-' + id) || (id === 'knobs' || id === '_all' ? root.querySelector('.livego') : null);
      if (box) box.append(h('p', { class: 'golive', role: 'status', text: (id === 'knobs' ? 'Knobs that can\'t go live: ' : 'Can\'t go live: ') + why }));
    }
    window.arbIssues = is;
  }
  // every saved change goes live to the Player by itself (Bruno 2026-10-10: "the Assembly is read in real time by the lab";
  // a pick saved without "Send to Player" never reached it): 1.5 s after the last change, the whole sheet as the live config
  // (TryIt.send: admin only; a viewer just sees why). The "Send to Player" button stays for a manual resend.
  let liveT = null;
  const liveMsg = h('span', { class: 'saved', 'aria-live': 'polite' });
  function autoLive() {
    if (!window.TryIt || !window.TryIt.send) return;
    clearTimeout(liveT); liveMsg.textContent = 'Going live to the Player…';
    liveT = setTimeout(() => window.TryIt.send(f, () => ({ sheet: window.arbSheet() }), liveMsg), 1500);
  }

  // ---- a clip: tap toggles ¼ speed (an S- / T- piece: its first animation, captioned with its id and name) ----
  function clip(hex, onRemove) {
    const a = D.by[PIECES[hex] ? PIECES[hex].anims[0] : hex];
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
    if (onRemove) fig.append(h('button', { type: 'button', class: 'rm', text: 'Remove', 'aria-label': 'Remove ' + fmtP(hex), onclick: onRemove }));
    return fig;
  }

  // ---- "Ask in the Workshop": the Workshop (its threads, its mic) with a request pre-filled for this slot and piece ----
  function askLink(def, pieces) {
    const p = pieces[0], key = !p ? null : isId(p) ? p : 'anim-' + p;
    const text = `Arbitration sheet, slot "${def.label}"` + (pieces.length ? ` (${pieces.map(fmtP).join(' then ')})` : ' (empty)') + ': ';
    const q = new URLSearchParams({ f, tab: 'workshop' }); if (key) q.set('ask', key); q.set('text', text);
    return h('a', { class: 'ask', href: 'lab.html?' + q.toString() + (key ? '#' + encodeURIComponent(key) : ''), target: '_blank',
      text: 'Ask in the Workshop' + (p ? ' about ' + fmtP(p) : '') });
  }
  // ---- one slot row ----
  function slotRow(def) {
    const id = def.id;
    const box = h('div', { class: 'slot', id: 'slot-' + id });
    const saved = h('div', { class: 'saved', 'aria-live': 'polite', text: mine(id) ? 'Saved' : '' });
    let shown = [];
    let tag = null;
    const save = async (pieces, quiet) => {
      saved.textContent = 'Saving…';
      try {
        await post(id, Object.assign({ question: `${D.display}: ${def.label}`, choice: 1, label: pieces.length ? 'picked' : 'empty',
          pieces: pieces.map(p => isId(p) ? p : 'anim-' + p) }));
        saved.textContent = 'Saved';
      } catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; }
      if (quiet) { tag.textContent = 'yours'; tag.className = 'tag mine'; } else draw();
    };
    const draw = () => {
      shown.forEach(unwatch); shown = [];
      const st = stateOf(id), his = mine(id), nw = nowOf(id);
      tag = h('span', { class: his ? 'tag mine' : 'tag', text: his ? 'yours' : 'now' });
      const kids = [h('div', { class: 'shead' }, h('span', { class: 'lab', text: def.label }), tag)], side = [];
      let left = null;
      if (!def.noAnim) {
        const nids = (nw.ids || []).map(i => i + (PIECES[i] ? ' ' + PIECES[i].name : ''));
        const nowLine = 'Now: ' + (nids.length ? nids.join(', ') + ' (' : '') + (nw.pieces.length ? nw.pieces.map(p => '$' + p).join(' then ') : 'nothing') + (nids.length ? ')' : '') + (nw.text ? ' · ' + nw.text : '');
        if (his || nw.text || nids.length) kids.push(h('p', { class: 'nowtxt', text: nowLine }));
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
          h('button', { type: 'button', text: 'Clear', onclick: () => save([]) }),
          his ? h('button', { type: 'button', text: 'Back to now', onclick: async () => {
            saved.textContent = 'Saving…';
            try { await post(id, { choice: null, label: null, pieces: null, knobs: null }); saved.textContent = 'Saved (back to now)'; } catch (e) { saved.textContent = 'Not saved (' + e.message + ')'; }
            draw(); } }) : null));
        const kp = st.pieces.filter(p => PIECES[p] && (PIECES[p].knobs || []).length);
        if (his && kp.length) {
          const all = Object.assign({}, knobsOf(id));
          let kt;
          const saveK = () => { clearTimeout(kt); saved.textContent = '…'; kt = setTimeout(async () => {
            saved.textContent = 'Saving…';
            try { await post(id, { knobs: all }); saved.textContent = 'Saved'; } catch (e) { saved.textContent = 'Not saved (' + e.message + '): try again'; }
            slotReset.hidden = !Object.keys(knobsOf(id)).length; }, 500); };
          const panels = kp.map(p => window.KnobUI.panel({ defs: PIECES[p].knobs, values: all[p] || {}, label: p + ' ' + PIECES[p].name + ': knobs',
            onChange: v => { if (Object.keys(v).length) all[p] = v; else delete all[p]; saveK(); } }));
          const slotReset = h('button', { type: 'button', class: 'kreset-slot', text: 'Reset all knobs of this slot', hidden: Object.keys(all).length ? null : '' });
          slotReset.onclick = () => panels.forEach(pn => pn.reset());
          left = h('div', { class: 'sleft' }, row, ...panels, slotReset);
        } else left = row;
      }
      side.push(askLink(def, st.pieces), saved);
      kids.push(left ? h('div', { class: 'sbody' }, left, h('div', { class: 'side' }, side)) : h('div', { class: 'side' }, side));
      box.replaceChildren(...kids);
    };
    drawers[id] = draw;
    draw();
    return box;
  }

  // ---- the chain: its presses + add / remove, then its timing ----
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
          n > 1 ? h('button', { type: 'button', text: 'Remove press ' + n, onclick: () => setN(n - 1) }) : null),
        timingBox);
    };
    draw();
    return wrap;
  }

  // ---- the chain's TIMING (the old Chain Lab's chain tool folded in, Bruno 2026-10-10): per press its hit-stop and its
  // move's segments (startup, each active window, the recovery after it) retimed 0.5x-2x of the source (gretime_t), as
  // knobs (knobui.js: the default = what the game plays now, an override marked, "Back to default"). The plan (tryit.js
  // TryIt.plan: his pack's / Lab build's chain data) gives each press's move, its source segments and the ROM's values.
  // Saved as the answer "chain_timing" of <f>-arb, its note = JSON {hitstop: {a1..aN: frames}, retime: {move: [frames
  // per segment]}} (overrides only); it rides in the sheet (sheetNow().timing) to Try in game / the live config (the chain
  // override, load 5: hit-stops in the tree, the retime rows after it) and ships with arb_compile.py (game.json roster
  // chain.hitstop + retime). A move pressed twice has one timing (retime is per move: every use of it takes it).
  const TID = 'chain_timing';
  const timingOf = () => { const a = ans[TID]; if (!(a && a.choice === 1 && a.note)) return {}; try { const t = JSON.parse(a.note); return t && typeof t === 'object' ? t : {}; } catch (e) { return {}; } };
  const timingNow = () => { const t = timingOf(), hs = t.hitstop || {}, rt = t.retime || {}; return Object.keys(hs).length || Object.keys(rt).length ? { hitstop: hs, retime: rt } : null; };
  const timingBox = h('div', { class: 'timing', role: 'group', 'aria-label': 'Chain timing' });
  const segName = (i, n) => i === 0 ? 'Startup' : (i % 2 ? 'Active' : 'Recovery') + (n > 3 ? ' ' + Math.ceil(i / 2) : '');
  let timingSeq = 0, timingT = null;
  async function saveTiming(t, msg) {
    const empty = !Object.keys(t.hitstop || {}).length && !Object.keys(t.retime || {}).length;
    msg.textContent = 'Saving…';
    try {
      await post(TID, empty ? { choice: null, label: null, note: null }
                            : { question: `${D.display}: chain timing`, choice: 1, label: 'chain timing', note: JSON.stringify(t) });
      msg.textContent = empty ? 'Saved: every press at the game\'s timing' : 'Saved';
    } catch (e) { msg.textContent = 'Not saved (' + e.message + '): try again'; }
  }
  async function drawTiming() {
    const seq = ++timingSeq;
    if (!window.TryIt || !window.TryIt.plan) { timingBox.replaceChildren(h('p', { class: 'empty', text: 'Chain timing: this page has no game data (tryit.js).' })); return; }
    const sh = sheetNow(), P = await window.TryIt.plan(f, sh.chain);
    if (seq !== timingSeq) return;                           // (a newer draw is on its way)
    const head = h('h3', { text: 'Chain timing' });
    if (!P.spec) { timingBox.replaceChildren(head, h('p', { class: 'empty', text: 'Chain timing needs his pack or his Lab build: ' + P.why + '.' })); return; }
    const t = timingOf(), msg = h('span', { class: 'saved', 'aria-live': 'polite' });
    const reset = h('button', { type: 'button', text: 'Reset the chain timing', hidden: timingNow() ? null : '' });
    const panels = P.moves.map((m, k) => {
      const key = 'a' + (k + 1), S = P.segs[m] || null, D0 = S ? P.defaults.retime[m] : null;
      const defs = [{ id: 'hitstop', name: 'Hit-stop (both freeze on contact)', unit: 'frames', default: P.defaults.hitstop[k], min: 1, max: 60, step: 1 }];
      if (S) S.forEach((s, i) => { if (!s) return; const lo = Math.max(1, Math.ceil(s / 2)), hi = Math.max(1, 2 * s);
        defs.push({ id: 's' + i, name: `${segName(i, S.length)} (source ${s})`, unit: 'frames', default: D0[i], min: Math.min(lo, D0[i]), max: Math.max(hi, D0[i]), step: 1 }); });
      const vals = {};
      if (Number.isInteger((t.hitstop || {})[key])) vals.hitstop = t.hitstop[key];
      const T = (t.retime || {})[m];
      if (S && Array.isArray(T) && T.length === S.length) T.forEach((v, i) => { if (S[i] && v !== D0[i]) vals['s' + i] = v; });
      // folded per press (a fast chain is 5 presses x 4-6 knobs): the summary says the press's timing and whether it
      // is changed, in words; a changed press starts open
      const sumText = v => {
        const hs = 'hitstop' in v ? v.hitstop : P.defaults.hitstop[k];
        const T = S ? D0.map((d, i) => ('s' + i) in v ? v['s' + i] : d) : null;
        return `Press ${k + 1}: ${m} · hit-stop ${hs} · ` + (T ? `${T.filter((x, i) => S[i]).join(' / ')} = ${T.reduce((a, b) => a + b, 0)} frames` : 'not retimed (no segments)') +
          (k === P.N - 1 ? ' · the last hit (its hit-stop is every finisher\'s)' : '') + (Object.keys(v).length ? ' · CHANGED' : ' · as the game');
      };
      const summary = h('summary', { text: sumText(vals) });
      const panel = window.KnobUI.panel({ defs, values: vals, label: `Press ${k + 1}: ${m}` + (S ? '' : ' (no segments: only its hit-stop)'), onChange: v => {
        summary.textContent = sumText(v);
        const x = timingOf(); x.hitstop = Object.assign({}, x.hitstop); x.retime = Object.assign({}, x.retime);
        if ('hitstop' in v) x.hitstop[key] = v.hitstop; else delete x.hitstop[key];
        if (S) { const nt = D0.map((d, i) => ('s' + i) in v ? v['s' + i] : d); if (nt.some((y, i) => y !== D0[i])) x.retime[m] = nt; else delete x.retime[m]; }
        if (!Object.keys(x.hitstop).length) delete x.hitstop;
        if (!Object.keys(x.retime).length) delete x.retime;
        ans[TID] = Object.assign({}, ans[TID], { choice: 1, note: JSON.stringify(x) });   // (now: the next panel reads it)
        reset.hidden = !timingNow();
        clearTimeout(timingT); msg.textContent = '…';
        timingT = setTimeout(async () => { await saveTiming(timingOf(), msg); if (P.moves.filter(y => y === m).length > 1) drawTiming(); }, 500);
      } });
      return h('details', { class: 'tpress', 'data-press': key, open: Object.keys(vals).length ? '' : null }, summary, panel);
    });
    reset.onclick = async () => { ans[TID] = {}; await saveTiming({}, msg); drawTiming(); };
    timingBox.replaceChildren(head,
      h('p', { class: 'about', text: `Per press (tap one to open it): the hit-stop, and the move's segments from 0.5x to 2x of the source (every use of the move takes them). The defaults are what the game plays now (build ${NOW.version}).` +
        (P.why ? ` Your presses cannot play as a chain (${P.why}): this is the game's own chain, timed.` : '') }),
      ...panels, h('div', { class: 'tryrow' }, reset, msg));
    window.arbTiming = { moves: P.moves, N: P.N, defaults: P.defaults, why: P.why };
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
    // the Workshop's pieces: unlocked S- / T- (pickable), locked specials (greyed, a link to ask for them)
    const wsP = W ? [...W.specials, ...W.throws] : [];
    const unl = wsP.filter(p => p.id), lck = wsP.filter(p => !p.id);
    const pcards = unl.map(p => {
      const a = D.by[p.anims[0]];
      const kids = [];
      if (a && a.status === 'ok' && a.f.length) { const { cv, st } = AD.player(D, a, SC, { lazy: true }); st.cv = cv; own.push(st); watch(st); cv.onclick = () => { st.speed = st.speed === 1 ? 0.25 : 1; }; kids.push(cv); }
      kids.push(h('div', { class: 'cap', text: p.id + ' · ' + p.name + ' · ' + p.input + (cur.includes(p.id) ? ' · IN THIS SLOT' : '') }),
        h('button', { type: 'button', class: 'use', text: (adding ? 'Add ' : 'Use ') + p.id, onclick: () => { close(); onPick(p.id); } }));
      return h('div', { class: 'pcard' + (cur.includes(p.id) ? ' cur' : '') }, kids);
    });
    const lockedList = lck.length ? h('details', { class: 'plocked' }, h('summary', { text: 'Locked specials (' + lck.length + '): not decoded yet' }),
      h('ul', {}, lck.map(p => h('li', {}, h('span', { text: p.name + ' (' + p.input + ') ' }),
        h('a', { href: 'lab.html?tab=workshop&f=' + f + '#' + encodeURIComponent(p.keys[0]), target: '_blank', text: 'Ask in the Workshop' }))))) : null;
    const piecesBox = W ? h('div', { class: 'ppieces' }, h('b', { text: 'Decoded pieces (Workshop ids): a special plays as its whole program' }),
      pcards.length ? h('div', { class: 'pgrid' }, pcards) : h('span', { text: 'None unlocked yet.' }), lockedList,
      h('b', { text: 'Animations' })) : null;
    const tog = (txt, on, fn) => { const b = h('button', { type: 'button', 'aria-pressed': String(on), text: (on ? '✓ ' : '') + txt }); b.onclick = () => { const v = fn(); b.setAttribute('aria-pressed', String(v)); b.textContent = (v ? '✓ ' : '') + txt; }; return b; };
    const bSlow = tog('¼ speed', pSlow, () => { pSlow = !pSlow; cards.forEach(c => { c._st.speed = pSlow ? 0.25 : 1; }); return pSlow; });
    const bAtk = tog('Attacks only', pAtk, () => { pAtk = !pAtk; apply(); return pAtk; });
    const flagBtns = AD.FLAGS.map(fg => tog(fg.id, pFlags.has(fg.id), () => { pFlags.has(fg.id) ? pFlags.delete(fg.id) : pFlags.add(fg.id); apply(); return pFlags.has(fg.id); }));
    const dlg = h('div', { class: 'pmodal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Pick an animation' },
      h('div', { class: 'pbox' },
        h('div', { class: 'phead' }, h('b', { text: (adding ? 'Add after the current ones in ' : 'Pick for ') + def.label }), q, bSlow, bAtk,
          h('button', { type: 'button', text: 'Close', onclick: close })),
        h('div', { class: 'frow', role: 'group', 'aria-label': 'Flags' }, h('span', { class: 'fl', text: 'With every flag (yours in the dictionary, else my suggestion)' }), flagBtns),
        piecesBox, shown, h('div', { class: 'pgrid' }, cards)));
    dlg.onclick = e => { if (e.target === dlg) close(); };
    document.addEventListener('keydown', esc);
    document.body.append(dlg);
    apply();
    window.arbPicker = def.id;
  }

  // ---- Ship to game (admin): the ship queue (feedback-api/lab/ship/<f>) with the live config's revision -------------
  const LAB_API = API + 'lab/';
  const shipMsg = h('div', { class: 'saved', 'aria-live': 'polite' });
  const shipBtn = h('button', { type: 'button', class: 'done', text: 'Ship to game' });
  fetch(LAB_API + 'me', { cache: 'no-store', credentials: 'same-origin' }).then(r => r.ok ? r.json() : null, () => null).then(w => {
    if (w && w.user && w.role !== 'admin') { shipBtn.disabled = true; shipMsg.textContent = `Ship to game needs the Oros admin role (signed in as ${w.user}).`; }
  });
  shipBtn.onclick = async () => {
    shipMsg.textContent = 'Queueing…'; shipBtn.disabled = true;
    try {
      const hr = await fetch(LAB_API + 'config/' + f + '/hash', { cache: 'no-store', credentials: 'same-origin' });
      if (hr.status === 404) throw new Error('no live config yet: press "Send to Player" first (the ship names that revision)');
      if (!hr.ok) throw new Error('the live config: HTTP ' + hr.status);
      const live = await hr.json();
      const r = await fetch(LAB_API + 'ship/' + f, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rev: live.version, note: 'Ship to game from the arbitration sheet' }) });
      const j = await r.json().catch(() => ({}));
      if (r.status === 403) throw new Error('Ship to game needs the Oros admin role');
      if (!r.ok) throw new Error(j.error || 'HTTP ' + r.status);
      shipMsg.textContent = `Queued (request ${j.ship.id}, live config r${j.ship.rev}): the compiler builds, checks every slot and publishes, or says why it refused.`;
    } catch (e) { shipMsg.textContent = 'Not queued: ' + e.message; }
    shipBtn.disabled = false;
  };

  // ---- "Try this sheet in game" (tryit.js): every slot of his answers (the slots still "now" keep the game's own move) on
  // his pack in the shell, live; the chain's presses (any piece each: a move, an animation, an S- piece) and their timing
  // in the TRY blob's chain section (version 3). "Send to Player": the same TRY blob as his live config (tryit.js)
  const sheetNow = () => {
    const slots = {};
    const knobs = {};
    for (const s of SECTIONS) if (!s.chain) for (const d of s.slots) if (!d.noAnim && mine(d.id)) {
      slots[d.id] = stateOf(d.id).pieces;
      const k = knobsOf(d.id); if (Object.keys(k).length) knobs[d.id] = k;
    }
    const pr = range(presses()).map(i => 'a' + (i + 1));
    return { slots, knobs, chain: pr.some(mine) ? pr.map(id => stateOf(id).pieces) : null, timing: timingNow() };
  };
  const tryBtn = () => window.TryIt ? window.TryIt.button(f, 'Try this sheet in game', () => window.TryIt.sheet(f, sheetNow()), () => ({ sheet: sheetNow() })) : null;
  window.arbSheet = sheetNow;
  const out = [h('h1', { text: `${D.display}: arbitration sheet` }),
    h('p', { class: 'intro', text: `What each input plays, section by section: chain (and its timing), alternate finishers, Blitz, air Blitz, specials, air specials, air, grab, fury. Every slot starts with what the game plays now (build ${NOW.version}, marked NOW); pick an animation from ${D.display}'s dictionary, add more to play back to back, tune a decoded piece's knobs; a question goes to the Workshop. Everything saves as you go. Tap a clip for ¼ speed.` }),
    h('div', { class: 'links' }, h('a', { href: 'lab.html?tab=workshop&f=' + f, text: 'Workshop (unlock specials)' }), h('a', { href: 'lab.html?tab=dictionary&f=' + f, text: 'Animation dictionary' }), h('a', { href: 'lab.html?tab=review&f=' + f, text: 'Fighter review' })),
    window.TryIt ? window.TryIt.liveLine(f) : null];
  out.push(h('div', { class: 'tryrow' }, tryBtn(), h('span', { class: 'about', text: 'Your answers, slot by slot, in the game now (the slots still "now" play the game\'s own move); play them on their own inputs.' })));
  out.push(h('div', { class: 'tryrow livego' }, h('span', { class: 'about', text: 'Live: every change is sent to the Player\'s Character lab by itself (about 2 s later; admin only). A pick that cannot go live says why next to it.' }), liveMsg));
  const sheetMsg = h('span', { class: 'saved', 'aria-live': 'polite' });
  const sheetReset = h('button', { type: 'button', class: 'kreset-sheet', text: 'Reset all knobs of the sheet' });
  sheetReset.onclick = async () => {
    const ids = Object.keys(ans).filter(id => mine(id) && ans[id].knobs && Object.keys(ans[id].knobs).length);
    if (!ids.length) { sheetMsg.textContent = 'Every knob is at its default already.'; return; }
    sheetMsg.textContent = 'Resetting…';
    try { for (const id of ids) { await post(id, { knobs: {} }); delete ans[id].knobs; if (drawers[id]) drawers[id](); } sheetMsg.textContent = `Every knob back to its default (${ids.length} slot${ids.length === 1 ? '' : 's'}).`; }
    catch (e) { sheetMsg.textContent = 'Not reset (' + e.message + '): try again'; }
  };
  out.push(h('div', { class: 'tryrow' }, sheetReset, sheetMsg));
  for (const s of SECTIONS) {
    out.push(h('h2', { text: s.title }), h('p', { class: 'about', text: s.about }));
    out.push(s.chain ? chainBlock() : s.slots.map(slotRow));
  }
  out.push(h('div', { class: 'final' }, tryBtn(), h('span', { text: 'When the whole sheet is how you want it (no agent: the compiler links every pick and knob, builds, checks each slot in the game and publishes, or refuses and says why):' }), shipBtn, shipMsg));
  root.replaceChildren(...out.flat().filter(x => x));
  drawTiming(); goLive();
  // on open: answers newer than the live config (or no live config yet) go live at once — a sheet edited before the
  // auto-send existed, or while the page was closed, still reaches the Player (2026-10-10)
  (async () => {
    const last = Object.values(ans).filter(x => x && x.at && x.choice !== undefined).map(x => Date.parse(x.at)).filter(x => x).sort().pop();
    if (!last) return;
    try {
      const r = await fetch(API + 'lab/config/' + f, { cache: 'no-store', credentials: 'same-origin' });
      const rec = r.ok ? await r.json() : null;
      const upd = rec && Date.parse(rec.updated || rec.at || 0);
      if (!rec || !upd || upd < last) autoLive();
    } catch (e) { /* offline: the next change sends */ }
  })();
  window.arbReady = { unlocked: Object.keys(PIECES).length, locked: W ? W.specials.filter(p => !p.id).length : null };
})();
