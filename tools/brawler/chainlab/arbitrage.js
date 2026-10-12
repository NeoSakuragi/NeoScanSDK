// A fighter's ARBITRATION sheet (the Fighter Lab's Assembly tab, lab.html?f=kim&tab=assembly, + &embed=1 in the Player: fighterlab.js loads this script into its #arb panel; arbitrage.html?f= redirects there): the web version of Bruno's A4 sheet for Kim
// (/data/scans/brawler/kim_notes_231734.png -> docs/brawler_gold.md "Kim (fast)"). The workflow for every new fighter,
// in this order: chain combo, alternate finishers, Blitz, air Blitz, specials, air specials, air, hold / throws, fury.
// TOKEN FREE (Bruno 2026-10-10, binding): the sheet has no channel to Claude. Every change here is compiled by the tooling
// alone (tools/brawler/arb_compile.py: links, knobs, build, per-slot check; it refuses and says why, never guesses). A
// question or a request goes to the Workshop (part 1, the token side): each slot's "Ask in the Workshop" opens it with a
// request pre-filled for that slot and piece. Old notes saved in <f>-arb stay on the server, never shown or read.
// COMPACT (Bruno 2026-10-10: "I spend my time scrolling and scrolling… Curate the information shown… Make it compact and
// usable, even on the split mobile phone that is only 6 inches. Cut the fluff out."): one template for every fighter.
//   - a sticky bar: his name, ONE status line (saving · "Live r21 ✓" · "In game 0.10.31"), ⋯ = the sheet's tools (Try in
//     game, Send to Player, the live config's History / Revert, the full live / game lines, reset knobs / chain timing,
//     links), and a one-line section jump bar;
//   - sections as collapsible headers (the chain's length and "▶ chain", the whole-chain clip, in the Chain header);
//   - one ROW per slot: its input ("f,f+A", "C", "A2"), the pick as a chip ($5B or S-012 + a short name; ● and bold =
//     yours, not what the game plays now), "pick" (the picker). Tap the row: it opens in place (one at a time) with the live
//     clip, one line of frame data, its knobs (a chain press: its timing), "now: …" when yours differs, ⋯ = add after,
//     clear, back to now, Ask in the Workshop. A pick that cannot go live says so on its row ("Can't go live: why").
// Pre-filled with what the game plays now (review/<fighter>_arb.json, tools/brawler/arbitrage.py).
// Answers: the decisions store, set "<fighter>-arb", one id per slot: choice 1 = his (pieces "anim-<hex>" in order,
// knobs); id "presses" = the chain's length (its note = the count). SHIP ON BRUNO'S WORD (2026-10-12): every change
// saves the live config (the Player's Character lab plays it at once); the sheet's "Ship to the game" button queues a
// ship (POST lab/ship/<f>) that the desktop's ship service (brawler-ship.service, labcfg.py ship-worker) builds, checks,
// publishes and commits (docs/character_lab.md "Ship service"): the bar says queued / building / shipped / failed.
// Renamed slots: an answer saved under an old id is read under its new one while the new id has none (OLD_IDS).
// Piece ids (Workshop, review/<fighter>_workshop.json, tools/brawler/piece_ids.py): the picker offers the animations
// ($NN, saved "anim-<hex>") and the UNLOCKED pieces (S- specials, T- throws, saved as their id: arb_compile.py links an
// S- id as that special's input); locked specials are listed greyed with a link to the Workshop.
// PIECE KNOBS (knobui.js compact, tools/brawler/knobs.py): in an open row, its picked S- pieces' knobs (W.specials[].knobs);
// the values save in the slot's answer as knobs {S- id: {knob id: value}} (a default left out), travel with "Try this
// sheet" / "Send to Player" (the TRY blob's knob rows) and ship through arb_compile.py (game.json roster[].knobs).
// CHAIN TIMING (the Chain Lab's chain tool folded in, 2026-10-10): in an open chain press, its hit-stop and its move's
// segments (0.5x-2x) as knobs; saved as "chain_timing", sent in the TRY blob's chain (version 3), shipped by
// arb_compile.py (game.json chain.hitstop + retime). See drawTiming.
// LIVE CLIPS (liveclips.js, 2026-10-10: "pre-rendering is no good: I can't adjust parameters"): the open row's clip (and
// the whole chain's) is played by the real engine in a Web Worker, again ~300 ms after a change to the pick, its knobs or
// the chain timing. Without a pack (or a shell without try3) the dictionary's static clips stay.
// window.arbOpen(id) opens a row (proofs); window.arbSheet / arbIssues / arbTiming / arbLive / arbReady as before.
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

  // the live clips (liveclips.js): null = the static clips (no pack, no worker)
  const LC = window.LiveClips && new URLSearchParams(location.search).get('live') !== '0' ? await window.LiveClips.attach(f).catch(() => null) : null;
  const liveKnobs = {};                            // slot id -> its knob values as edited (the clip follows them before the save returns)
  const clips = [];
  AD.clock(clips);
  const io = new IntersectionObserver(es => { for (const e of es) { const st = e.target._clip; if (!st) continue; st.visible = e.isIntersecting; if (e.isIntersecting) st.load(); } }, { rootMargin: '200px' });
  const watch = st => { clips.push(st); io.observe(st.cv); };
  const unwatch = st => { const i = clips.indexOf(st); if (i >= 0) clips.splice(i, 1); io.unobserve(st.cv); };

  // ---- the sheet's structure (the order is the workflow); short = the row's input label, label = the long one (saved
  // questions, the picker's title, the Workshop request) ----
  const N0 = NOW.chain_len;
  const press = n => ({ id: 'a' + n, short: 'A' + n, label: 'A press ' + n + (n === 1 ? ' (starter)' : '') });
  const SECTIONS = [
    { id: 'chain', title: 'Chain', chain: true },
    { id: 'fin', title: 'Finishers', slots: [
      { id: 'fin_fwd', short: 'last+f', label: 'last hit + forward' }, { id: 'fin_up', short: 'last+u', label: 'last hit + up (launcher)' },
      { id: 'fin_down', short: 'last+d', label: 'last hit + down' }, { id: 'fin_df', short: 'last+df', label: 'last hit + down-forward' }, { id: 'fin_back', short: 'last+b', label: 'last hit + back (throw)' }] },
    { id: 'bz', title: 'Blitz', slots: [
      { id: 'bz_ff', short: 'f,f+A', label: 'forward, forward + A' }, { id: 'bz_dd', short: 'd,d+A', label: 'down, down + A' },
      { id: 'bz_uu', short: 'u,u+A', label: 'up, up + A' }, { id: 'bz_du', short: 'd,u+A', label: 'down, up + A' }] },
    { id: 'abz', title: 'Air Blitz', slots: [
      { id: 'air_bz_ff', short: 'f,f+A', label: 'forward, forward + A in the air' }, { id: 'air_bz_dd', short: 'd,d+A', label: 'down, down + A in the air' },
      { id: 'air_bz_uu', short: 'u,u+A', label: 'up, up + A in the air' }, { id: 'air_bz_du', short: 'd,u+A', label: 'down, up + A in the air' }] },
    { id: 'sp', title: 'Specials', slots: [
      { id: 'sp_c', short: 'C', label: 'C (neutral, also the combo breaker)' }, { id: 'sp_fc', short: 'f+C', label: 'forward + C' }, { id: 'sp_dc', short: 'd+C', label: 'down + C' }] },
    { id: 'asp', title: 'Air specials', slots: [
      { id: 'air_sp_c', short: 'C', label: 'C in the air' }, { id: 'air_sp_fc', short: 'f+C', label: 'forward + C in the air' }, { id: 'air_sp_dc', short: 'd+C', label: 'down + C in the air' }] },
    { id: 'air', title: 'Air', slots: [
      { id: 'air_a', short: 'j+A', label: 'jump + A' }, { id: 'air_da', short: 'j+d+A', label: 'jump + down + A' },
      { id: 'air_ba', short: 'j.4A', label: 'jump + back + A' }] },
    { id: 'grab', title: 'Grab', slots: [
      { id: 'grab_hit', short: 'hold A', label: 'hold hit (A in the hold)' }, { id: 'grab_fin', short: 'hold fin', label: 'hold finisher (the throw-out)' },
      { id: 'grab_fwd', short: 'f+C', label: 'throw forward' }, { id: 'grab_back', short: 'b+C', label: 'throw back' }] },
    { id: 'fury', title: 'Fury', slots: [
      { id: 'fury', short: 'D', label: 'fury (D, gauge full)' }, { id: 'max', short: 'd+D', label: 'MAX (down + D, low life)' }] },
  ];
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
  const name = id => { if (isId(id)) return id + (PIECES[id] ? ' ' + PIECES[id].name : ''); const a = D.by[id]; return a ? '$' + id + (a.exported[0] ? ' ' + a.exported[0] : a.moves && a.moves[0] ? ' ' + a.moves[0] : '') : '$' + id; };
  // the chip's text: the id + at most 3 words of its name (the full name in its tooltip)
  const short = id => { const n = name(id), m = /^(\S+)\s*(.*)$/.exec(n); const w = m[2].split(/[\s_]+/).filter(Boolean).slice(0, 3).join(' '); return m[1] + (w ? ' ' + w : ''); };

  // ---- the one status line (top bar): saving · live · game ----
  const stSave = h('span', { class: 'ss' }), stLive = h('span', { class: 'sl' }), stGame = h('span', { class: 'sg' });
  let saveT = null;
  const saving = (t, bad) => { clearTimeout(saveT); stSave.textContent = t; stSave.classList.toggle('bad', !!bad); if (!bad && /^Saved/.test(t)) saveT = setTimeout(() => { stSave.textContent = ''; }, 2500); };
  async function post(id, body) {
    saving('Saving…');
    try {
      const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(Object.assign({ set: SET, id }, body)) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const j = await r.json().catch(() => ({}));
      ans[id] = j.answer || Object.assign({}, ans[id], body);
    } catch (e) { saving('Not saved (' + e.message + '): try again', true); throw e; }
    saving('Saved ✓');
    if (id === 'presses' || /^a\d$/.test(id)) drawTiming();   // the chain's moves changed: its timing knobs follow
    if (LC) LC.refresh(null);                       // (a clip whose request did not change is not simulated again)
    marks(); autoLive(); goLive();
  }
  // NOTHING DROPPED SILENTLY (2026-10-10, note 20261010-210158-5d29): each slot whose pick cannot go live (Try in game, the
  // Player) says so on its row, "Can't go live: why" (TryIt.issues: the same checks the Send makes); the ⋯ live line lists
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
  // every saved change goes live to the Player by itself (Bruno 2026-10-10: "the Assembly is read in real time by the lab"):
  // 1.5 s after the last change, the whole sheet as the live config (TryIt.send: admin only; a viewer sees why, in ⋯)
  let liveT = null;
  const liveMsg = h('span', { class: 'saved', 'aria-live': 'polite' });
  function autoLive() {
    if (!window.TryIt || !window.TryIt.send) return;
    clearTimeout(liveT); liveMsg.textContent = 'Going live to the Player…'; liveMsg.classList.remove('bad'); liveStat();
    liveT = setTimeout(() => window.TryIt.send(f, () => ({ sheet: window.arbSheet() }), liveMsg), 1500);
  }
  // the short live status from the live config (tryit.js) and the auto-send's message
  function liveStat() {
    const L = window.tryit && window.tryit.live && window.tryit.live[f], rec = L ? L.rec : undefined, m = liveMsg.textContent;
    stLive.classList.toggle('bad', liveMsg.classList.contains('bad'));
    stLive.textContent = liveMsg.classList.contains('bad') ? 'Live ✗ (see ⋯)'
      : /^(Going live|Sending)/.test(m) ? 'Live: sending…'
      : rec ? `Live r${rec.version}` + (/^(Sent|Unchanged)/.test(m) ? ' ✓' : '') : rec === null ? 'Live: none yet' : 'Live: …';
  }
  new MutationObserver(liveStat).observe(liveMsg, { childList: true, characterData: true, subtree: true, attributes: true });

  // ---- a static clip (no live clips): tap toggles ¼ speed (an S- / T- piece: its first animation) ----
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
  // ---- a clip's hit class, from the data (the Workshop's: each attack box's KOF reaction class, workshop.py hit_classes) ----
  const boxId = k => !/^kof9[6-9]$/.test(W && W.game || '') ? null : k >= 0x100 ? k - 0x100 : k & 0x0F;
  function classOf(pieces) {
    if (!W || !W.classes) return W && W.class_note ? W.class_note : '';
    const labs = [];
    for (const p of pieces) for (const x of (PIECES[p] ? PIECES[p].anims.concat(PIECES[p].projectile || []) : [p])) for (const s of ((D.by[x] || {}).steps || [])) for (const b of s.b) {
      if (b[0] !== 'a') continue;
      const k = boxId(b[1]), c = k !== null ? W.classes['$' + k.toString(16).toUpperCase().padStart(2, '0')] : null;
      const l = c ? c.label : 'class not decoded';
      if (!labs.includes(l)) labs.push(l);
    }
    return labs.join(', ') || 'no attack box';
  }

  // ---- one slot ROW: input · chip · pick; tapped: it opens in place (one at a time) ----
  let openId = null;
  const rowMarks = {};                             // slot id -> () => redraws its ● (yours / timing changed)
  const marks = () => Object.values(rowMarks).forEach(fn => fn());
  window.arbOpen = id => { if (drawers[id]) { if (openId !== id) toggle(id); return true; } return false; };
  function toggle(id) {
    const was = openId;
    openId = openId === id ? null : id;
    if (was && drawers[was]) drawers[was]();
    if (openId && drawers[openId]) drawers[openId]();
  }
  function slotRow(def) {
    const id = def.id;
    const box = h('div', { class: 'slot', id: 'slot-' + id });
    let shown = [];
    const save = async pieces => {
      try { await post(id, { question: `${D.display}: ${def.label}`, choice: 1, label: pieces.length ? 'picked' : 'empty', pieces: pieces.map(p => isId(p) ? p : 'anim-' + p) }); } catch (e) { /* said in the bar */ }
      draw();
    };
    const pressK = /^a(\d)$/.exec(id);
    const timed = () => { if (!pressK) return false; const t = timingOf(), m = window.arbTiming && window.arbTiming.moves[+pressK[1] - 1];
      return Number.isInteger((t.hitstop || {})[id]) || !!(m && (t.retime || {})[m]); };
    const draw = () => {
      shown.forEach(unwatch); shown = [];
      const st = stateOf(id), his = mine(id), nw = nowOf(id), open = openId === id;
      if (LC && !open) LC.forget(id);
      // the row
      const nowP = nw.pieces.filter(p => D.by[p]);
      const disp = !his && (nw.ids || []).length ? nw.ids : st.pieces;      // (the game's S- piece by its id, not its animations)
      const chipText = disp.length ? disp.map(short).join(' → ') : '— ' + (!his && nw.text ? nw.text : 'empty');
      const mark = h('span', { class: 'mk', 'aria-hidden': 'true' });
      const chip = h('span', { class: 'chip' + (st.pieces.length ? '' : ' none'), title: disp.map(name).join(' then ') + (disp !== st.pieces ? ' (' + st.pieces.map(p => '$' + p).join(' → ') + ')' : '') || (his ? 'emptied by you' : 'nothing today') }, mark, chipText);
      const setMark = () => { const y = his || timed(); mark.textContent = y ? '● ' : ''; chip.classList.toggle('yours', y); row.setAttribute('aria-label', `${def.label}: ${chipText}` + (his ? ' (yours)' : timed() ? ' (timing changed)' : ' (the game\'s)') + (open ? ', open' : '')); };
      const pick = h('button', { type: 'button', class: 'pick', text: st.pieces.length ? 'pick' : '+', 'aria-label': 'Pick for ' + def.label,
        onclick: e => { e.stopPropagation(); picker(def, st.pieces, hex => save([hex]), false, nowP); } });
      const row = h('div', { class: 'srow', role: 'button', tabindex: '0', 'aria-expanded': String(open) },
        h('span', { class: 'in', text: def.short }), chip, h('span', { class: 'tw', 'aria-hidden': 'true', text: open ? '▾' : '▸' }), pick);
      row.onclick = () => toggle(id);
      row.onkeydown = e => { if ((e.key === 'Enter' || e.key === ' ') && e.target === row) { e.preventDefault(); toggle(id); } };
      rowMarks[id] = setMark; setMark();
      if (!open) { box.classList.remove('open'); box.replaceChildren(row); return; }
      // open: the clip, one line of data, the knobs / timing, "now", ⋯
      box.classList.add('open');
      const x = h('div', { class: 'sx' });
      if (st.pieces.length > 1) x.append(h('div', { class: 'pieces' }, st.pieces.map((p, i) => [i ? h('span', { class: 'then', text: '→' }) : null,
        h('span', { class: 'pc' }, h('span', { text: name(p) }), h('button', { type: 'button', class: 'rm', text: '×', 'aria-label': 'Remove ' + fmtP(p), onclick: () => save(st.pieces.filter((_, j) => j !== i)) }))])));
      if (LC) {
        x.append(LC.clip({ key: id, compact: true, label: def.label + (his ? ' (yours)' : ' (now: the game\'s)'),
          req: pressK ? () => ({ kind: 'press', k: +pressK[1] - 1, sheet: sheetNow() })
                      : () => ({ kind: 'slot', slot: id, pieces: his ? stateOf(id).pieces : null, knobs: liveKnobs[id] || knobsOf(id), sheet: sheetNow() }),
          cls: () => classOf(his ? st.pieces : nowP) }));
      } else if (st.pieces.length) {
        const cl = h('div', { class: 'clips' });
        st.pieces.forEach((p, i) => { if (i) cl.append(h('span', { class: 'then', text: '→' })); const fg = clip(p); if (fg._st) shown.push(fg._st); cl.append(fg); });
        x.append(cl);
      }
      if (his && st.pieces.join() !== nowP.join()) {            // (yours differs from the game's: say what it plays now)
        const nids = (nw.ids || []);
        x.append(h('p', { class: 'nowtxt', text: 'now: ' + (nids.length ? nids.join(', ') + ' ' : '') + (nowP.length ? nowP.map(p => '$' + p).join(' → ') : nids.length ? '' : 'nothing') + (nw.text ? ' · ' + nw.text : '') }));
      } else if (nw.text && st.pieces.length) x.append(h('p', { class: 'nowtxt', text: nw.text }));
      // knobs of its S- pieces
      const kp = st.pieces.filter(p => PIECES[p] && (PIECES[p].knobs || []).length);
      let slotReset = null;
      if (his && kp.length) {
        const all = Object.assign({}, knobsOf(id));
        let kt;
        const saveK = () => { clearTimeout(kt); saving('…'); kt = setTimeout(async () => {
          try { await post(id, { knobs: all }); } catch (e) { /* said in the bar */ }
          slotReset.hidden = !Object.keys(knobsOf(id)).length; }, 500); };
        const panels = kp.map(p => window.KnobUI.panel({ compact: true, defs: PIECES[p].knobs, values: all[p] || {}, label: kp.length > 1 ? p + ' knobs' : '',
          onChange: v => { if (Object.keys(v).length) all[p] = v; else delete all[p]; liveKnobs[id] = JSON.parse(JSON.stringify(all)); if (LC) LC.refresh(id); saveK(); } }));
        slotReset = h('button', { type: 'button', class: 'kreset-slot', text: 'Reset knobs', hidden: Object.keys(all).length ? null : '' });
        slotReset.onclick = () => panels.forEach(pn => pn.reset());
        x.append(...panels);
      }
      if (pressK) { const tb = h('div', { class: 'tslot', 'data-press': id }); x.append(tb); timingInto(tb, +pressK[1] - 1); }
      // ⋯ the rest
      const more = h('details', { class: 'more' }, h('summary', { text: '⋯ more', 'aria-label': 'More for ' + def.label }),
        h('div', { class: 'mbody' },
          h('button', { type: 'button', text: '+ add after', onclick: () => picker(def, st.pieces, hex => save(st.pieces.concat(hex)), true, nowP) }),
          h('button', { type: 'button', text: 'Clear', onclick: () => save([]) }),
          his ? h('button', { type: 'button', text: 'Back to now', onclick: async () => {
            try { await post(id, { choice: null, label: null, pieces: null, knobs: null }); } catch (e) { /* said in the bar */ }
            draw(); } }) : null,
          slotReset, askLink(def, st.pieces)));
      x.append(more);
      box.replaceChildren(row, x);
      goLiveRow(id);
    };
    drawers[id] = draw;
    draw();
    return box;
  }
  // a redrawn row gets its "can't go live" back (goLive's last answer) without asking again
  function goLiveRow(id) {
    const why = window.arbIssues && window.arbIssues[id], box = root.querySelector('#slot-' + id);
    if (!why || !box) return;
    box.querySelectorAll('.golive').forEach(e => e.remove());
    box.append(h('p', { class: 'golive', role: 'status', text: 'Can\'t go live: ' + why }));
  }

  // ---- the chain: its presses; the length and the whole-chain clip in its header ----
  const chainRows = h('div', { class: 'rows' });
  const chainMsg = h('div', { class: 'cmsg' });
  let wholeOpen = false;
  const wholeBox = h('div', { class: 'slot whole', id: 'slot-chain', hidden: '' });
  const wholeBtn = h('button', { type: 'button', class: 'hbtn', 'aria-pressed': 'false', text: '▶ chain', 'aria-label': 'The whole chain, played', hidden: LC ? null : '' });
  wholeBtn.onclick = e => {
    e.stopPropagation(); wholeOpen = !wholeOpen; wholeBtn.setAttribute('aria-pressed', String(wholeOpen));
    if (wholeOpen) { secOpen('chain', true); wholeBox.hidden = false; wholeBox.replaceChildren(LC.clip({ key: 'chain', compact: true, label: `The whole chain: presses 1-${presses()} on hits (the last = the neutral finisher)`, req: () => ({ kind: 'chain', sheet: sheetNow() }),
      cls: () => classOf(range(presses()).flatMap(i => stateOf('a' + (i + 1)).pieces.length ? stateOf('a' + (i + 1)).pieces : nowOf('a' + (i + 1)).pieces.filter(p => D.by[p]))) })); }
    else { LC.forget('chain'); wholeBox.hidden = true; wholeBox.replaceChildren(); }
  };
  const lenTxt = h('span', { class: 'len' });
  const lenMinus = h('button', { type: 'button', class: 'hbtn', text: '−' }), lenPlus = h('button', { type: 'button', class: 'hbtn', text: '+' });
  function drawChain() {
    const n = presses();
    lenTxt.textContent = n + ' presses';          // (2-8, saved as the "presses" answer: live + shipped like any pick)
    lenMinus.hidden = n <= 2; lenPlus.hidden = n >= 8;
    lenMinus.setAttribute('aria-label', 'Remove press ' + n); lenPlus.setAttribute('aria-label', 'Add a press');
    for (const k of Object.keys(drawers)) if (/^a\d$/.test(k) && +k.slice(1) > n) { delete drawers[k]; delete rowMarks[k]; if (LC) LC.forget(k); if (openId === k) openId = null; }
    chainRows.replaceChildren(...range(n).map(i => slotRow(press(i + 1))));
  }
  const setN = async (e, k) => { e.stopPropagation(); try { await post('presses', { question: `${D.display}: chain length`, choice: 1, label: k + ' presses', note: String(k) }); } catch (er) { /* said in the bar */ } drawChain(); };
  lenMinus.onclick = e => setN(e, presses() - 1); lenPlus.onclick = e => setN(e, presses() + 1);

  // ---- the chain's TIMING (the old Chain Lab's chain tool folded in, Bruno 2026-10-10): per press its hit-stop and its
  // move's segments (startup, each active window, the recovery after it) retimed 0.5x-2x of the source (gretime_t), as
  // compact knobs in the open press (the default = what the game plays now, an override marked, "reset"). The plan (tryit.js
  // TryIt.plan: his pack's / Lab build's chain data) gives each press's move, its source segments and the ROM's values.
  // Saved as the answer "chain_timing" of <f>-arb, its note = JSON {hitstop: {a1..aN: frames}, retime: {move: [frames
  // per segment]}} (overrides only); it rides in the sheet (sheetNow().timing) to Try in game / the live config and ships
  // with arb_compile.py (game.json roster chain.hitstop + retime). A move pressed twice has one timing (retime is per
  // move: every use of it takes it).
  const TID = 'chain_timing';
  const timingOf = () => { const a = ans[TID]; if (!(a && a.choice === 1 && a.note)) return {}; try { const t = JSON.parse(a.note); return t && typeof t === 'object' ? t : {}; } catch (e) { return {}; } };
  const timingNow = () => { const t = timingOf(), hs = t.hitstop || {}, rt = t.retime || {}; return Object.keys(hs).length || Object.keys(rt).length ? { hitstop: hs, retime: rt } : null; };
  const segName = (i, n) => i === 0 ? 'Startup' : (i % 2 ? 'Active' : 'Recovery') + (n > 3 ? ' ' + Math.ceil(i / 2) : '');
  let timingSeq = 0, timingT = null, PLAN = null;
  async function saveTiming(t) {
    const empty = !Object.keys(t.hitstop || {}).length && !Object.keys(t.retime || {}).length;
    try { await post(TID, empty ? { choice: null, label: null, note: null } : { question: `${D.display}: chain timing`, choice: 1, label: 'chain timing', note: JSON.stringify(t) }); } catch (e) { /* said in the bar */ }
  }
  async function drawTiming() {
    const seq = ++timingSeq;
    if (!window.TryIt || !window.TryIt.plan) { PLAN = { why: 'this page has no game data (tryit.js)' }; chainMsg.replaceChildren(h('p', { class: 'golive', text: 'Chain timing: ' + PLAN.why + '.' })); return; }
    const P = await window.TryIt.plan(f, sheetNow().chain);
    if (seq !== timingSeq) return;                           // (a newer draw is on its way)
    PLAN = P;
    chainMsg.replaceChildren(...(!P.spec ? [h('p', { class: 'golive', text: 'Chain timing needs his pack or his Lab build: ' + P.why + '.' })]
      : P.why ? [h('p', { class: 'golive', text: `Your presses can't play as a chain (${P.why}): the timing is the game's own chain's.` })] : []));
    if (P.spec) window.arbTiming = { moves: P.moves, N: P.N, defaults: P.defaults, why: P.why };
    root.querySelectorAll('.tslot').forEach(tb => timingInto(tb, +tb.dataset.press.slice(1) - 1));
    marks();
  }
  function timingInto(tb, k) {
    const P = PLAN;
    if (!P) { tb.replaceChildren(h('p', { class: 'nowtxt', text: 'timing: reading the game data…' })); return; }
    if (!P.spec || !P.moves[k]) { tb.replaceChildren(); return; }
    const m = P.moves[k], key = 'a' + (k + 1), S = P.segs[m] || null, D0 = S ? P.defaults.retime[m] : null, t = timingOf();
    const defs = [{ id: 'hitstop', name: 'Hit-stop', unit: 'f', default: P.defaults.hitstop[k], min: 1, max: 60, step: 1 }];
    if (S) S.forEach((s, i) => { if (!s) return; const lo = Math.max(1, Math.ceil(s / 2)), hi = Math.max(1, 2 * s);
      defs.push({ id: 's' + i, name: `${segName(i, S.length)} (src ${s})`, unit: 'f', default: D0[i], min: Math.min(lo, D0[i]), max: Math.max(hi, D0[i]), step: 1 }); });
    const vals = {};
    if (Number.isInteger((t.hitstop || {})[key])) vals.hitstop = t.hitstop[key];
    const T = (t.retime || {})[m];
    if (S && Array.isArray(T) && T.length === S.length) T.forEach((v, i) => { if (S[i] && v !== D0[i]) vals['s' + i] = v; });
    const panel = window.KnobUI.panel({ compact: true, defs, values: vals, label: `Timing · ${m}` + (S ? '' : ' (hit-stop only)') + (k === P.N - 1 ? ' · last (finishers too)' : ''), onChange: v => {
      const x = timingOf(); x.hitstop = Object.assign({}, x.hitstop); x.retime = Object.assign({}, x.retime);
      if ('hitstop' in v) x.hitstop[key] = v.hitstop; else delete x.hitstop[key];
      if (S) { const nt = D0.map((d, i) => ('s' + i) in v ? v['s' + i] : d); if (nt.some((y, i) => y !== D0[i])) x.retime[m] = nt; else delete x.retime[m]; }
      if (!Object.keys(x.hitstop).length) delete x.hitstop;
      if (!Object.keys(x.retime).length) delete x.retime;
      ans[TID] = Object.assign({}, ans[TID], { choice: 1, note: JSON.stringify(x) });   // (now: the next panel reads it)
      timingReset.hidden = !timingNow(); marks();
      if (LC) LC.refresh(null);
      clearTimeout(timingT); saving('…');
      timingT = setTimeout(async () => { await saveTiming(timingOf()); if (P.moves.filter(y => y === m).length > 1) drawTiming(); }, 500);
    } });
    tb.replaceChildren(h('div', { class: 'tpress', 'data-press': key }, panel));
  }
  const timingReset = h('button', { type: 'button', text: 'Reset the chain timing', hidden: '' });
  timingReset.onclick = async () => { ans[TID] = {}; if (LC) LC.refresh(null); await saveTiming({}); timingReset.hidden = true; drawTiming(); };

  // ---- the picker: every animation of the dictionary, attacks first (now: what the game plays on that input) ----
  const ORDER = D.anims.filter(a => a.status === 'ok' && a.f.length).sort((x, y) => (y.attack - x.attack) || (x.n - y.n));
  let pSlow = false, pAtk = true;
  const pFlags = new Set();
  function picker(def, cur, onPick, adding, nowP) {
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
        h('div', { class: 'cap', text: AD.caption(a) + (cur.includes(a.id) ? ' · IN THIS SLOT' : '') + ((nowP || []).includes(a.id) ? ' · NOW' : '') }),
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
    const lockedList = lck.length ? h('details', { class: 'plocked' }, h('summary', { text: 'Locked specials (' + lck.length + ')' }),
      h('ul', {}, lck.map(p => h('li', {}, h('span', { text: p.name + ' (' + p.input + ') ' }),
        h('a', { href: 'lab.html?tab=workshop&f=' + f + '#' + encodeURIComponent(p.keys[0]), target: '_blank', text: 'Ask in the Workshop' }))))) : null;
    const piecesBox = W ? h('div', { class: 'ppieces' }, h('b', { text: 'Decoded pieces' }),
      pcards.length ? h('div', { class: 'pgrid' }, pcards) : h('span', { text: 'None unlocked yet.' }), lockedList,
      h('b', { text: 'Animations' })) : null;
    const tog = (txt, on, fn) => { const b = h('button', { type: 'button', 'aria-pressed': String(on), text: (on ? '✓ ' : '') + txt }); b.onclick = () => { const v = fn(); b.setAttribute('aria-pressed', String(v)); b.textContent = (v ? '✓ ' : '') + txt; }; return b; };
    const bSlow = tog('¼ speed', pSlow, () => { pSlow = !pSlow; cards.forEach(c => { c._st.speed = pSlow ? 0.25 : 1; }); return pSlow; });
    const bAtk = tog('Attacks only', pAtk, () => { pAtk = !pAtk; apply(); return pAtk; });
    const flagBtns = AD.FLAGS.map(fg => tog(fg.id, pFlags.has(fg.id), () => { pFlags.has(fg.id) ? pFlags.delete(fg.id) : pFlags.add(fg.id); apply(); return pFlags.has(fg.id); }));
    const nowTxt = (nowP || []).length ? ' · now: ' + nowP.map(p => '$' + p).join(' → ') : '';
    const dlg = h('div', { class: 'pmodal', role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Pick an animation' },
      h('div', { class: 'pbox' },
        h('div', { class: 'phead' }, h('b', { text: (adding ? 'Add after: ' : 'Pick: ') + def.label + nowTxt }), q, bSlow, bAtk,
          h('button', { type: 'button', text: 'Close', onclick: close })),
        h('details', { class: 'frow' }, h('summary', { text: 'Flags' }), h('div', { role: 'group', 'aria-label': 'Flags' }, flagBtns)),
        piecesBox, shown, h('div', { class: 'pgrid' }, cards)));
    dlg.onclick = e => { if (e.target === dlg) close(); };
    document.addEventListener('keydown', esc);
    document.body.append(dlg);
    apply();
    window.arbPicker = def.id;
  }

  // ---- SHIP ON BRUNO'S WORD (2026-10-12): live saves go to the Player's Character lab at once; the game (the Player's
  // brawler, the VPS download) changes only when he presses "Ship to the game": POST lab/ship/<f> (admin; the server takes
  // the live revision), the desktop's ship service (labcfg.py ship-worker as brawler-ship.service) builds it: pull, arb_compile,
  // VERSION +1, make, bank_proof, bleed regress, publish, commit + push. The bar: Queued / Building 0.10.N / Shipped 0.10.N /
  // FAILED (the reason in ⋯).
  const LAB_API = API + 'lab/';
  const gameLine = h('p', { class: 'ingame', 'aria-live': 'polite', text: 'In the game: …' });
  const shipBtn = h('button', { type: 'button', class: 'shipbtn', text: 'Ship to the game' });
  const gameSay = (long, shortT, bad) => { gameLine.textContent = long; gameLine.classList.toggle('bad', !!bad); stGame.textContent = shortT; stGame.classList.toggle('bad', !!bad); };
  let shipBusy = false;
  shipBtn.onclick = async () => {
    if (shipBusy) return;
    shipBusy = true; shipBtn.disabled = true; gameSay('Queuing the ship…', 'Queuing…');
    try {
      const r = await fetch(LAB_API + 'ship/' + f, { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: 'Ship to the game (the Assembly)' }) });
      if (!r.ok) { const j = await r.json().catch(() => ({})); gameSay('Not queued: ' + (r.status === 403 ? 'it needs the Oros admin role' : j.error || 'HTTP ' + r.status), 'Not queued ✗', true); }
    } catch (e) { gameSay('Not queued: ' + e.message, 'Not queued ✗', true); }
    shipBusy = false; gameStatus();
  };
  async function gameStatus() {
    let rs;
    try { const r = await fetch(LAB_API + 'ship?fighter=' + f, { cache: 'no-store', credentials: 'same-origin' }); if (!r.ok) return; rs = (await r.json()).requests || []; }
    catch (e) { return; }
    const mine = rs.filter(x => x.fighter === f && x.status !== 'dropped').sort((x, y) => y.id - x.id);
    const cur = mine[0], done = mine.find(x => x.status === 'done' && /(?:shipped|build) \d/.test(x.result || ''));
    const inGame = done ? (/(?:shipped|build) (\d\S*)/.exec(done.result) || [])[1] : null;
    const had = inGame ? `In the game: ${inGame}` : 'In the game: nothing shipped from this sheet yet';
    const busy = cur && (cur.status === 'pending' || cur.status === 'building');
    shipBtn.disabled = shipBusy || !!busy;
    if (!cur) gameSay(had + '.', inGame ? 'In game ' + inGame : 'Not shipped yet');
    else if (cur.status === 'pending') gameSay(`Queued (request ${cur.id}): the ship service takes it within 30 s. ${had}.`, 'Queued');
    else if (cur.status === 'building') { const v = (/building ([\d.]+)/.exec(cur.result || '') || [])[1] || ''; gameSay(`Building ${v} (request ${cur.id}): ${(cur.result || '').replace(/^building [^:]*:? ?/, '')}. ${had}.`, `Building ${v}…`); }
    else if (cur.status === 'failed') gameSay(`FAILED (request ${cur.id}): ${(cur.result || '').replace(/^failed: /, '')}. Nothing changed in the game. ${had}.`, 'FAILED ✗ (⋯)', true);
    else gameSay(cur === done ? `Shipped ${inGame} (request ${cur.id}).` : `In the game: ${cur.result || 'done'}`, inGame ? 'Shipped ' + inGame : 'Shipped');
  }
  gameStatus();
  setInterval(() => { if (!document.hidden && document.body.contains(gameLine)) gameStatus(); }, 10000);

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

  // ---- the page: the sticky bar (name, status, ⋯, jump), then the sections ----
  const sheetReset = h('button', { type: 'button', class: 'kreset-sheet', text: 'Reset all knobs of the sheet' });
  sheetReset.onclick = async () => {
    const ids = Object.keys(ans).filter(id => mine(id) && ans[id].knobs && Object.keys(ans[id].knobs).length);
    if (!ids.length) { saving('Every knob is at its default already.'); return; }
    try { for (const id of ids) { delete liveKnobs[id]; await post(id, { knobs: {} }); delete ans[id].knobs; if (drawers[id]) drawers[id](); } saving(`Saved ✓ every knob back to its default (${ids.length} slot${ids.length === 1 ? '' : 's'})`); }
    catch (e) { /* said in the bar */ }
  };
  const liveLineEl = window.TryIt ? window.TryIt.liveLine(f) : null;
  if (liveLineEl) new MutationObserver(liveStat).observe(liveLineEl, { childList: true, subtree: true });
  const menuBody = h('div', { class: 'amenu', hidden: '' },
    h('div', { class: 'tryrow' }, tryBtn()),
    h('div', { class: 'tryrow livego' }, h('b', { text: 'Live: ' }), liveMsg),
    liveLineEl, gameLine,
    h('div', { class: 'tryrow' }, sheetReset, timingReset),
    h('div', { class: 'links' }, h('a', { href: 'lab.html?tab=workshop&f=' + f, text: 'Workshop' }), h('a', { href: 'lab.html?tab=dictionary&f=' + f, text: 'Dictionary' }), h('a', { href: 'lab.html?tab=review&f=' + f, text: 'Review' })));
  const menuBtn = h('button', { type: 'button', class: 'abtn', 'aria-expanded': 'false', text: '⋯', 'aria-label': 'The sheet\'s tools: Try in game, Send to Player, live config history, reset' });
  menuBtn.onclick = () => { const o = menuBody.hidden; menuBody.hidden = !o; menuBtn.setAttribute('aria-expanded', String(o)); };
  const stat = h('span', { class: 'astat', role: 'status', 'aria-live': 'polite' }, stSave, stLive, stGame);
  stat.onclick = () => { if (menuBody.hidden) menuBtn.click(); };
  // collapsible sections (a per-viewer convenience, remembered in this browser)
  const COLL = (() => { try { return JSON.parse(localStorage.getItem('arb-collapsed') || '{}'); } catch (e) { return {}; } })();
  const secEls = {};
  function secOpen(sid, open) {
    const s = secEls[sid]; if (!s) return;
    s.body.hidden = !open; s.btn.setAttribute('aria-expanded', String(open)); s.btn.firstChild.textContent = (open ? '▾ ' : '▸ ');
    if (open) delete COLL[sid]; else COLL[sid] = 1;
    try { localStorage.setItem('arb-collapsed', JSON.stringify(COLL)); } catch (e) { /* no storage */ }
    if (!open && openId && secEls[sid].body.contains(root.querySelector('#slot-' + openId))) toggle(openId);
  }
  const jump = h('nav', { class: 'ajump', 'aria-label': 'Sections' }, SECTIONS.map(s => h('button', { type: 'button', text: s.title,
    onclick: () => { secOpen(s.id, true); secEls[s.id].sec.scrollIntoView({ block: 'start' }); } })));
  const bar = h('div', { class: 'abar' }, h('div', { class: 'arow' }, h('h1', { text: D.display }), stat, shipBtn, menuBtn), jump, menuBody);
  const out = [bar, h('div', { class: 'livego' })];
  for (const s of SECTIONS) {
    const btn = h('button', { type: 'button', class: 'stog', 'aria-expanded': 'true' }, h('span', { text: '▾ ' }), s.title);
    const extra = s.chain ? h('span', { class: 'hx' }, lenMinus, lenTxt, lenPlus, wholeBtn) : null;
    const body = h('div', { class: 'sbody' }, s.chain ? [chainMsg, wholeBox, chainRows] : h('div', { class: 'rows' }, s.slots.map(slotRow)));
    const sec = h('section', { class: 'sec', id: 'sec-' + s.id }, h('h2', { class: 'shd' }, btn, extra), body);
    btn.onclick = () => secOpen(s.id, body.hidden);
    secEls[s.id] = { sec, body, btn };
    out.push(sec);
  }
  drawChain();
  root.replaceChildren(...out.filter(x => x));
  for (const sid of Object.keys(COLL)) secOpen(sid, false);
  liveStat();
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
  window.arbLive = !!LC;
  window.arbReady = { unlocked: Object.keys(PIECES).length, locked: W ? W.specials.filter(p => !p.id).length : null };
})();
