/* Chain tool (brawler revamp phase 5; docs/brawler_feel.md 9, docs/brawler_data_model.md "The chain tool"), in the
 * Chain Lab tab above the routes editor. A fighter's chain in the chain core's model (revamp 1A): its archetype (the
 * chain's length and damage total), the links picked from its piece catalogue (pieces.py: tags, appeal, reach), the
 * finishers by the stick (neutral, forward, up, down = sweep or slam, back = the throw), the hit-stop per link, and every
 * used move's segments (revamp 1C: startup, each active window and the recovery after it) dragged to 0.5x-2x. The readouts
 * (frames, damage on the archetype's total, advantage on hit, reach and spacing) follow every edit. "Push to the game"
 * writes the chain override into the running game's RAM (lab.js installChain: the tree, then the retime table, fighter.c
 * lab_install load 5): no rebuild, it plays on the dummy at once and in a real fight. "Send to Player" puts the same
 * override in the fighter's live config (tryit.js TryIt.send: lab.js liveBlob, the live TRY blob kept; the Player's
 * Character lab writes it as load 5 at neutral). "Save" sends the game.json entry to
 * the feedback service (decisions set "chain-tool", one per fighter); tools/brawler/chain_save.py applies it to game.json. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  while (!window.chainlab) await new Promise(r => setTimeout(r, 100));
  const CL = window.ChainLab, CLAB = window.chainlab, lab = CLAB.lab, data = CLAB.data;
  const F = data.fighters, RULES = data.chain;
  const col = $('treecol');
  if (!col || !RULES || !F[0].pieces) return;                  // a site without the tool's data (make_site.py)
  const API = 'feedback-api/';
  const PX = 6;                                                  // px a frame in the segment bars
  const HW = 16;                                                 // the dummy's half width (pieces.py spacing)
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) { if (k === 'text') e.textContent = v; else if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); } for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined && c !== false) e.append(c); return e; };
  const clone = x => JSON.parse(JSON.stringify(x));
  const up = n => n.toUpperCase().replace('_', ' ');

  const css = document.createElement('style');
  css.textContent = `
#chaintool { border: var(--line); margin: 0 0 12px; }
#chaintool > h2 { font-size: 15px; margin: 0; padding: 6px 8px; border-bottom: var(--line); }
#chaintool .ctbody { padding: 6px 8px; }
#chaintool table.ct { border-collapse: collapse; width: 100%; font-size: 13px; margin: 6px 0; }
#chaintool table.ct td, #chaintool table.ct th { border: var(--thin); padding: 3px 5px; text-align: left; vertical-align: top; }
#chaintool table.ct select { max-width: 270px; min-height: 30px; font-size: 13px; padding: 1px 4px; border-width: 1px; }
#chaintool table.ct input[type=number] { width: 52px; min-height: 28px; padding: 1px 4px; border-width: 1px; font-size: 13px; }
#chaintool .tag { font-size: 12px; }
#chaintool .segbar { display: flex; align-items: stretch; margin: 4px 0 2px; user-select: none; touch-action: none; }
#chaintool .seg { position: relative; height: 26px; border: var(--thin); margin-right: -1px; font: 11px/24px ui-monospace, monospace; text-align: center; overflow: visible; white-space: nowrap; }
#chaintool .seg.s { background: #fff; }
#chaintool .seg.a { background: #000; color: #fff; }
#chaintool .seg.r { background: repeating-linear-gradient(45deg, #fff 0 4px, #000 4px 5px); }
#chaintool .seg.r span { background: #fff; padding: 0 2px; }
#chaintool .seg .hd { position: absolute; right: -7px; top: -4px; width: 13px; height: 32px; border: 2px solid #000; background: #fff; cursor: ew-resize; z-index: 2; }
#chaintool .seg .hd:focus { outline: 3px solid #000; outline-offset: 1px; }
#chaintool .segnums { display: flex; flex-wrap: wrap; gap: 4px 8px; font-size: 12px; }
#chaintool .segnums label { display: inline-flex; gap: 3px; align-items: center; }
#chaintool .mono { font-family: ui-monospace, monospace; font-size: 12px; }
#chaintool .warn { font-weight: 700; }
#chaintool .ctmsg { font-size: 13px; border: var(--thin); padding: 4px 6px; margin: 6px 0; min-height: 1.4em; white-space: pre-wrap; }
#chaintool .ctmsg.bad { border: var(--line); font-weight: 700; }
#chaintool td.num { text-align: right; font-family: ui-monospace, monospace; }
`;
  document.head.append(css);
  const root = h('section', { id: 'chaintool' });
  col.prepend(root);

  // ---- state: a spec per fighter (lab.js chainTree), drafts kept in this browser ------------------------------------
  const DRAFT = 'chaintool-drafts';
  let drafts = {};
  try { drafts = JSON.parse(localStorage.getItem(DRAFT)) || {}; } catch (e) { drafts = {}; }
  const keep = () => { try { localStorage.setItem(DRAFT, JSON.stringify(drafts)); } catch (e) { /* private window */ } };
  const romSpec = f => CL.specOf(f, RULES, data.retime_rom);
  const fiNow = () => Number($('fighter').value) || 0;
  let fi = fiNow();
  let spec = drafts[F[fi].name] ? clone(drafts[F[fi].name]) : romSpec(F[fi]);
  let pushed = null;              // {fi, key: the spec pushed (JSON), bytes, nodes, rows}
  let lastPlay = null;            // the autoplay's links as the game played them

  const pieces = f => f.pieces.filter(p => p.kind === 'normal' || p.kind === 'command');
  const pieceOf = (f, m) => f.pieces.find(p => p.move === m) || null;
  const throwPiece = f => f.pieces.find(p => p.kind === 'throw') || null;
  const segsOf = m => CL.segsOf(F[fi], m);
  const targetsOf = m => { const s = segsOf(m); if (!s) return null; const t = spec.retime && spec.retime[m]; return t && t.length === s.length ? t : s.slice(); };
  const segName = (i, n) => i === 0 ? 'startup' : (i % 2 ? 'active' : 'recovery') + (n > 3 ? ' ' + Math.ceil(i / 2) : '');
  const bound = s => [Math.max(1, Math.ceil(s / 2)), Math.max(1, 2 * s)];   // the 0.5x-2x bound (retime.BOUND)

  function edited() { drafts[F[fi].name] = spec; keep(); render(); }
  function tree() { return CL.chainTree(F[fi], spec, RULES); }

  // ---- readouts ---------------------------------------------------------------------------------------------------------
  function frames(m) {             // startup / active / recovery (windows summed), total, at the targets and at the source
    const T = targetsOf(m), S = segsOf(m);
    if (!T) return null;
    const sum = (a, odd) => a.reduce((x, v, i) => x + (i > 0 && (i % 2 === 1) === odd ? v : 0), 0);
    return { su: T[0], ac: sum(T, true), re: sum(T, false), total: T.reduce((a, b) => a + b, 0),
             su0: S[0], total0: S.reduce((a, b) => a + b, 0), changed: T.some((t, i) => t !== S[i]) };
  }
  function readout(t) {            // per link and finisher: move, frames, damage, hit-stop, advantage, reach, spacing margin
    const N = t.chain_links, links = [];
    let nd = t.links.A;
    for (let k = 0; k < N - 1; k++) { links.push(nd); if (k < N - 2) nd = nd.links.A; }
    const L = nd.links, rows = [];
    const stun = w => w === 'strong' ? RULES.stun_heavy : RULES.stun_light;
    const push = n => n.push !== undefined ? n.push : CL.defaultDamage(n)[1];
    let d = null;
    const margin = (n) => {        // pieces.py spacing: the victim 8 px inside link 1's reach, pushed back, closed in by travel
      const p = pieceOf(F[fi], n.move); if (!p) return null;
      if (d === null) d = p.reach + HW - 8;
      const m = p.reach + HW - d;
      return { m, next: Math.max(2 * HW, d + push(n) - (p.travel || 0)) };
    };
    links.forEach((n, k) => {
      const fr = frames(n.move), mg = margin(n); d = mg ? mg.next : d;
      rows.push({ what: 'link ' + (k + 1), n, fr, adv: fr ? stun(n.weight) - (fr.total - fr.su - 1) : null, margin: mg ? mg.m : null });
    });
    const dBefore = d;
    for (const [k, what] of [['A', 'neutral'], ['fA', 'forward'], ['uA', 'up'], ['dA', 'down'], ['bA', 'back']]) {
      const n = L[k]; if (!n) continue;
      d = dBefore; const mg = n.throw ? null : margin(n), fr = n.throw ? null : frames(n.move);
      rows.push({ what: what + ' finisher', n, fr, adv: null, margin: n.throw ? null : (mg ? mg.m : null), fin: k });
    }
    return rows;
  }

  // ---- the segment editor: one bar per move, a handle at each segment's end ------------------------------------------------
  function segEditor(m) {
    const S = segsOf(m); if (!S) return h('div', { class: 'tag', text: 'no segments (not retimed)' });
    const T = targetsOf(m);
    const set = (i, v) => {
      const [lo, hi] = bound(S[i]); v = Math.max(lo, Math.min(hi, Math.round(v)));
      if (v === T[i]) return false;
      const nt = T.slice(); nt[i] = v; spec.retime = Object.assign({}, spec.retime, { [m]: nt });
      return true;
    };
    const bar = h('div', { class: 'segbar', role: 'group', 'aria-label': m + ' segments' });
    S.forEach((s, i) => {
      if (!s) return;
      const kind = i === 0 ? 's' : i % 2 ? 'a' : 'r';
      const hd = h('span', { class: 'hd', tabindex: 0, role: 'slider', 'aria-label': `${m} ${segName(i, S.length)}`, 'aria-valuenow': T[i],
                              'aria-valuemin': bound(s)[0], 'aria-valuemax': bound(s)[1], title: 'drag: 0.5x - 2x of the source; arrow keys: a frame' });
      const seg = h('div', { class: 'seg ' + kind, style: `width:${T[i] * PX}px` }, h('span', { text: `${segName(i, S.length)[0].toUpperCase()}${T[i]}` }), hd);
      hd.onpointerdown = ev => {
        ev.preventDefault(); hd.setPointerCapture(ev.pointerId);
        const x0 = ev.clientX, t0 = T[i];
        hd.onpointermove = e2 => { const v = t0 + (e2.clientX - x0) / PX; const [lo, hi] = bound(s); const c = Math.max(lo, Math.min(hi, Math.round(v))); seg.style.width = c * PX + 'px'; seg.firstChild.textContent = segName(i, S.length)[0].toUpperCase() + c; hd._v = c; };
        hd.onpointerup = () => { hd.onpointermove = hd.onpointerup = null; if (hd._v !== undefined && set(i, hd._v)) edited(); };
      };
      hd.onkeydown = e => { const k = { ArrowRight: 1, ArrowLeft: -1 }[e.key]; if (k && set(i, T[i] + k)) { e.preventDefault(); edited(); setTimeout(() => { const x = root.querySelector(`[aria-label="${m} ${segName(i, S.length)}"]`); if (x) x.focus(); }, 0); } };
      bar.append(seg);
    });
    const nums = h('div', { class: 'segnums' }, S.map((s, i) => s ? h('label', {}, segName(i, S.length),
      h('input', { type: 'number', min: bound(s)[0], max: bound(s)[1], value: T[i], onchange: e => { if (set(i, Number(e.target.value))) edited(); else e.target.value = T[i]; } }),
      h('span', { class: 'tag', text: `(${s})` })) : null),
      h('button', { style: 'min-height:26px;padding:0 6px;border-width:1px', onclick: () => { const r = Object.assign({}, spec.retime); delete r[m]; spec.retime = r; edited(); } }, 'source timing'));
    return h('div', {}, bar, nums);
  }

  // ---- the editor -----------------------------------------------------------------------------------------------------------
  const msgBox = h('div', { class: 'ctmsg', role: 'status' });
  const say = (t, bad) => { msgBox.textContent = t; msgBox.classList.toggle('bad', !!bad); };
  function pieceSelect(cur, onpick, filter) {
    const list = pieces(F[fi]).filter(filter || (() => true)).sort((a, b) => b.appeal - a.appeal);
    const s = h('select', { onchange: e => onpick(e.target.value) },
      list.map(p => h('option', { value: p.move, selected: p.move === cur },
        `${p.label} · ${p.limb} ${p.height} · ${p.reaction} · reach ${p.reach} · ${p.startup}/${p.active}/${p.recovery} · appeal ${p.appeal}`)));
    if (!list.some(p => p.move === cur)) s.prepend(h('option', { value: cur || '', selected: true }, cur ? cur + ' (not in the catalogue)' : '(none)'));
    return s;
  }
  function render() {
    const f = F[fi];
    let t = null, problem = null;
    try { t = tree(); } catch (e) { problem = e.message; }
    const N = RULES.lengths[spec.archetype];
    const archSel = h('select', { onchange: e => {
      const a = e.target.value, n = RULES.lengths[a] - 1, cur = spec.links.slice(0, n);
      while (cur.length < n) cur.push(cur[cur.length - 1] || pieces(f)[0].move);
      spec.archetype = a; spec.links = cur; spec.hitstop = null; edited(); } },
      CL.ARCHETYPES.map(a => h('option', { value: a, selected: a === spec.archetype }, `${a}: ${RULES.lengths[a]} links, ${RULES.totals[a]} damage`)));
    const hsDefault = CL.defaultHitstops(RULES, N), hs = spec.hitstop || hsDefault;
    const hsInput = k => h('input', { type: 'number', min: 1, max: 60, value: hs[k], 'aria-label': 'hit-stop frames', onchange: e => {
      const v = Math.max(1, Math.min(60, Math.round(Number(e.target.value)) || 1)), n = hs.slice(); n[k] = v;
      spec.hitstop = n.every((x, i) => x === hsDefault[i]) ? null : n; edited(); } });
    const rows = t ? readout(t) : [];
    const fin = spec.finishers;
    const finEdit = {
      A: () => pieceSelect(fin.neutral, m => { fin.neutral = m; edited(); }),
      fA: () => pieceSelect(fin.forward, m => { fin.forward = m; edited(); }),
      uA: () => pieceSelect(fin.up, m => { fin.up = m; edited(); }),
      dA: () => h('span', {}, h('select', { onchange: e => { fin.down = e.target.value === 'none' ? null : e.target.value; if (fin.down && !fin.down_move) fin.down_move = pieces(f)[0].move; edited(); } },
        ['sweep', 'slam', 'none'].map(k => h('option', { value: k, selected: (fin.down || 'none') === k }, k === 'sweep' ? 'sweep (trip)' : k === 'slam' ? 'slam (bounce)' : 'none'))),
        fin.down ? pieceSelect(fin.down_move, m => { fin.down_move = m; edited(); }) : null),
      bA: () => { const p = throwPiece(f); return h('span', { class: 'tag', text: p ? p.label + ' (the chain core\'s rule, not edited here)' : 'no throw: plays the neutral finisher' }); },
    };
    const table = h('table', { class: 'ct' },
      h('thead', {}, h('tr', {}, ['', 'piece', 'hit-stop', 'frames S / A / R = total (source)', 'damage', 'adv. on hit', 'reach', 'margin'].map(x => h('th', { text: x })))),
      h('tbody', {}, rows.map((r, idx) => {
        const n = r.n, fr = r.fr;
        const cell = r.fin ? finEdit[r.fin]() : pieceSelect(spec.links[idx], m => { spec.links[idx] = m; edited(); });
        const used = n.throw ? null : n.move;
        return [h('tr', {},
          h('th', { text: r.what + (r.fin === 'uA' && (fin.launcher || 'up') === 'up' ? ' (launcher)' : r.fin === 'fA' && fin.launcher === 'forward' ? ' (launcher)' : '') }),
          h('td', {}, cell, h('div', { class: 'tag', text: n.throw ? '' : `${n.move} · ${n.weight}${n.effect !== 'none' ? ' · ' + n.effect : ''}` })),
          h('td', {}, r.fin ? (r.fin === 'A' ? hsInput(N - 1) : h('span', { class: 'tag', text: String(n.hitstop) + ' (the neutral\'s)' })) : hsInput(idx)),
          h('td', { class: 'mono' }, fr ? `${fr.su} / ${fr.ac} / ${fr.re} = ${fr.total}` + (fr.changed ? `  (${fr.total0})` : '') : '-'),
          h('td', { class: 'num', text: n.throw ? 'throw' : String(n.damage) }),
          h('td', { class: 'num', text: r.adv === null ? (n.effect && n.effect !== 'none' ? n.effect : '-') : (r.adv >= 0 ? '+' : '') + r.adv }),
          h('td', { class: 'num', text: pieceOf(f, n.move) && !n.throw ? pieceOf(f, n.move).reach + ' px' : '-' }),
          h('td', { class: 'num' + (r.margin !== null && r.margin < 0 ? ' warn' : ''), text: r.margin === null ? '-' : r.margin + ' px' + (r.margin < 0 ? ' (may whiff)' : '') })),
          used && segsOf(used) ? h('tr', {}, h('td', {}), h('td', { colspan: 7 }, h('div', { class: 'tag', text: used + ': segments (drag a handle: 0.5x - 2x; the move\'s every use takes it)' }), segEditor(used))) : null];
      })));
    const total = t ? t.chain.damage.reduce((a, b) => a + b, 0) : 0;
    const dirty = pushed && pushed.fi === fi && pushed.key === JSON.stringify(spec) ? 'pushed: this chain is in the game' : pushed && pushed.fi === fi ? 'edited since the push' : 'not pushed';
    root.replaceChildren(
      h('h2', { text: `Chain tool: ${up(f.name)}'s chain (revamp 5): edit, push to the running game, play, save` }),
      h('div', { class: 'ctbody' },
        h('div', { class: 'row' }, h('label', {}, 'Archetype ', archSel),
          h('label', {}, 'Launcher on ', h('select', { onchange: e => { fin.launcher = e.target.value; if (!fin[fin.launcher]) fin[fin.launcher] = fin.neutral; edited(); } },
            ['up', 'forward'].map(k => h('option', { value: k, selected: (fin.launcher || 'up') === k }, k)))),
          h('button', { onclick: () => { spec = romSpec(f); delete drafts[f.name]; keep(); render(); } }, "The ROM's chain"),
          h('span', { class: 'mark', text: dirty })),
        problem ? h('div', { class: 'ctmsg bad', text: 'Not a valid chain: ' + problem }) : null,
        table,
        h('div', { class: 'tag', text: t ? `chain damage ${total} (the ${spec.archetype} total ${RULES.totals[spec.archetype]}), hit-stops ${t.chain.hitstop.join(' ')}; adv. on hit = the victim's stun (light ${RULES.stun_light}, heavy ${RULES.stun_heavy}) minus the frames after contact; margin < 0: the link may whiff from the previous one's spacing (pieces.py's estimate; Play shows what the game does)` : '' }),
        h('div', { class: 'row' },
          h('button', { onclick: push, disabled: !t }, 'Push to the game'),
          window.TryIt ? h('button', { onclick: sendPlayer, disabled: !t, title: 'This chain as ' + up(f.name) + '\'s live config: the Player applies it at neutral' }, 'Send to Player') : null,
          ...['neutral', 'forward', 'up', 'down', 'back'].map(d => h('button', { onclick: () => autoplay(d), disabled: !t }, 'Play ' + d)),
          h('button', { onclick: fight, disabled: !t }, 'Fight with it (stage 1)'),
          h('button', { onclick: unpush }, "ROM's tables back")),
        h('div', { class: 'row' },
          h('button', { onclick: save, disabled: !t }, 'Save (send to Claude)'),
          h('button', { onclick: download, disabled: !t }, 'Download the entry'),
          h('span', { class: 'tag', text: 'Save = this chain as a game.json entry in the feedback store; Claude applies it (tools/brawler/chain_save.py) and commits once you accept the diff.' })),
        msgBox,
        lastPlay ? playTable() : null));
  }

  // ---- push / play / fight ----------------------------------------------------------------------------------------------
  function build() {
    const f = F[fi], t = tree();
    const blob = CL.encodeTree(t, data.ba, f.has, f.default.entries);
    const rows = CL.retimeRows(data, f, spec);
    return { t, blob, rows, bytes: CL.encodeOverride(blob, rows) };
  }
  function push() {
    let b;
    try { b = build(); } catch (e) { say('Not pushed: ' + e.message, true); return false; }
    lab.installChain(fi, b.bytes); CLAB.stepFrames(1);
    const st = lab.overrideState(fi);
    pushed = { fi, key: JSON.stringify(spec), bytes: b.bytes.length, nodes: b.blob[3], rows: b.rows.length };
    const ok = st.treeInLab && (b.rows.length ? st.rtInLab : true);
    say((ok ? 'Pushed' : 'NOT TAKEN by the game') + `: ${b.blob[3]} nodes + ${b.rows.length} retime row${b.rows.length === 1 ? '' : 's'}, ${b.bytes.length} bytes in lab.buf; ` +
        `the game reads route_tab[${f_name()}] = $${hex(st.tree)} (${st.treeInLab ? 'the override' : 'the ROM'}), rt_tab = $${hex(st.rt)} (${st.rtInLab ? 'the override' : st.rt ? '?' : 'the ROM\'s'}).`, !ok);
    render();
    return ok;
  }
  // the Player's Character lab: the same override (load 5) in the fighter's live config, its TRY blob kept (tryit.js)
  async function sendPlayer() {
    let b;
    try { b = build(); } catch (e) { say('Not sent: ' + e.message, true); return null; }
    const f = F[fi], e = CL.saveEntry(f, spec, RULES);
    const text = `${spec.archetype}: ${spec.links.concat(spec.finishers.neutral).join(' > ')} (${b.blob[3]} nodes, ${b.rows.length} retime row${b.rows.length === 1 ? '' : 's'})`;
    const el = document.createElement('span');
    const j = await window.TryIt.send(f.name, { chain: { bytes: b.bytes, fighter: f.id, text, entry: e } }, el);
    say(el.textContent, !j);
    return j;
  }
  const hex = v => v === null ? '?' : v.toString(16).toUpperCase().padStart(6, '0');
  const f_name = () => F[fi].name;
  function unpush() { lab.installChain(fi, null); CLAB.stepFrames(1); pushed = null; const st = lab.overrideState(fi); say(`The ROM's tree and retime table: route_tab = $${hex(st.tree)}, rt_tab = $${hex(st.rt)}.`); render(); }
  function fight() {
    if (!push()) return;
    lab.playStage(fi, 0, 0); if (CLAB.paused) CLAB.togglePause(); CLAB.stepFrames(1);
    say(`${up(F[fi].name)} in stage 1 with this chain (the override stays until "ROM's tables back"). A = the chain, the stick on the last link = the finisher.`);
  }
  /* the chain played at once on the dummy: positions reset, A pressed every other frame (the core latches a press in the
     hit-stop and fires it on the first free frame), the stick held for the last link's press = the finisher */
  function autoplay(dir) {
    if (!(pushed && pushed.fi === fi && pushed.key === JSON.stringify(spec)) && !push()) return;
    if (lab.r8(lab.lab + 8) !== 1) { lab.request(1, fi, Number($('dummy').value)); CLAB.stepFrames(3); }
    lab.request(2); CLAB.stepFrames(2);
    const t = tree(), N = t.chain_links, idx = CL.nodeIndex(t);
    const linkOf = new Map(); let nd = t.links.A;
    for (let k = 0; k < N - 1; k++) { linkOf.set(idx.get(nd), 'link ' + (k + 1)); if (k === N - 2) for (const [kk, x] of Object.entries(nd.links)) if (['A', 'fA', 'uA', 'dA', 'bA'].includes(kk)) linkOf.set(idx.get(x), { A: 'neutral', fA: 'forward', uA: 'up', dA: 'down', bA: 'back' }[kk] + ' finisher'); nd = nd.links.A; }
    const fac = lab.fget(0, 'facing') > 0, stick = { neutral: '', forward: fac ? 'R' : 'L', up: 'U', down: 'D', back: fac ? 'L' : 'R' }[dir];
    const from = lab.nev(), out = [];
    let starts = 0, finAt = -1, i = 0;
    for (; i < 420; i++) {
      const ev = lab.eventsSince(from).events;
      starts = ev.filter(e => e.kind === 'START').length;
      if (finAt < 0 && starts >= N) finAt = i;
      CLAB.play('1:' + (CL.autoKeys(i, starts, N, stick, finAt >= 0) || '-'));
      if (finAt >= 0 && i - finAt > 100) break;
    }
    CLAB.play('1:-');
    const ev = lab.eventsSince(from).events;
    for (const e of ev) {
      if (e.kind === 'START') out.push({ node: e.node, what: linkOf.get(e.node) || 'node ' + e.node, start: e.frame, hits: [], dmg: 0 });
      else if (e.kind === 'HIT' && out.length) { out[out.length - 1].hits.push(e.frame); out[out.length - 1].dmg += e.val; }
    }
    lastPlay = { dir, links: out, t };
    say(`Played the chain with the ${dir} finisher: ${out.length} links started, ${out.filter(l => l.hits.length).length} hit, ${out.reduce((a, l) => a + l.dmg, 0)} damage.`);
    render();
  }
  function playTable() {
    const L = lastPlay.links;
    return h('table', { class: 'ct' }, h('caption', { style: 'text-align:left;font-weight:700', text: `As the game played it (${lastPlay.dir} finisher): frames from each link's start` }),
      h('thead', {}, h('tr', {}, ['', 'move', 'start', 'contact (frames after start)', 'expected startup', 'damage'].map(x => h('th', { text: x })))),
      h('tbody', {}, L.map(l => {
        const n = findNode(lastPlay.t, l.node), fr = n && !n.throw ? frames(n.move) : null;
        return h('tr', {}, h('th', { text: l.what }), h('td', { text: n ? (n.throw ? 'throw' : n.move) : '?' }), h('td', { class: 'num', text: String(l.start) }),
          h('td', { class: 'num', text: l.hits.length ? l.hits.map(x => x - l.start).join(', ') : 'WHIFF' }),
          h('td', { class: 'num', text: fr ? String(fr.su) : '-' }), h('td', { class: 'num', text: String(l.dmg) }));
      })));
  }
  function findNode(t, i) { const idx = CL.nodeIndex(t); for (const [nd, k] of idx) if (k === i) return nd; return null; }

  // ---- save: the game.json entry to the feedback store, or a file ---------------------------------------------------------
  function entry() {
    const f = F[fi];
    return { fighter: f.name, game_version: (document.getElementById('ver').textContent || '').replace('brawler ', ''), entry: CL.saveEntry(f, spec, RULES), spec };
  }
  async function save() {
    try { tree(); } catch (e) { say('Not saved: ' + e.message, true); return; }
    const e = entry();
    const label = `${e.entry.archetype}: ${e.entry.chain.links.join(' > ')} | ${Object.entries(e.entry.finishers).map(([k, v]) => k + ' ' + v).join(', ')}` + (e.entry.retime ? ` | retime ${Object.keys(e.entry.retime).join(', ')}` : '');
    try {
      const r = await fetch(API + 'decision', { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ set: 'chain-tool', id: e.fighter, choice: 'save', question: `Chain tool: ${up(e.fighter)}'s chain`, label, note: JSON.stringify(e) }) });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      say(`Saved for ${up(e.fighter)}: ${label}. Claude applies it to game.json (chain_save.py) and shows you the diff.`);
    } catch (err) { say('Not saved (' + err.message + '): use "Download the entry" and send the file.', true); }
  }
  function download() {
    const e = entry(), a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(e, null, 1)], { type: 'application/json' }));
    a.download = `chain-${e.fighter}.json`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // the fighter picker (header) drives the tool too
  $('fighter').addEventListener('change', () => {
    const n = fiNow(); if (n === fi) return;
    fi = n; spec = drafts[F[fi].name] ? clone(drafts[F[fi].name]) : romSpec(F[fi]); lastPlay = null; say('');
    render();
  });
  render();
  window.chaintool = { get spec() { return spec; }, set spec(s) { spec = s; render(); }, build, push, sendPlayer, autoplay, unpush, entry, get lastPlay() { return lastPlay; }, get fi() { return fi; } };
})();
