/* Brawler Lab, Characters tab: game.json's `roster` (docs/brawler_data_model.md "Layer 1"). Per fighter: its bank
 * fighter, unlock rule, colour sets, the select pose (picked from every intro / win / walk-in frame, tap-to-pick; a ROM
 * build change: exported), the specials by role (D, forward+D, down+D, up+D, each picked from the fighter's captured
 * specials; live: the data pack's roster section, version 2, played in the in-page game against the dummy), its chain
 * routes (the Chain Lab, one click). Export / import in game.json's roster layout.
 * Data: chars.json (make_site.py: game.json's roster, chainlab.json's pools, char_images.py pictures). */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const SP = window.StagePack;
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  const clone = x => JSON.parse(JSON.stringify(x));
  const up = n => n.toUpperCase().replace(/_/g, ' ');
  const ROLES = [['D', 'D', 'projectile'], ['fD', 'forward+D', 'rush'], ['dD', 'down+D', 'rising reversal (invincible)'], ['uD', 'up+D', 'another special']];

  while (!window.stagesTab || !window.chainlab) await new Promise(r => setTimeout(r, 100));
  const CLAB = window.chainlab, lab = CLAB.lab;
  let X;
  try { X = await (await fetch('chars.json', { cache: 'no-cache' })).json(); } catch (e) { $('tabChars').disabled = true; return; }
  const ORIG = clone(X.roster), NAMES = ORIG.map(r => r.name);
  const DRAFT = 'brawlerlab.chars.' + (lab.layout.version || '');
  let roster = clone(ORIG), ci = 0, dummy = Math.max(0, NAMES.indexOf('ryo'));
  try { const d = JSON.parse(localStorage.getItem(DRAFT)); if (Array.isArray(d) && d.length === ORIG.length && d.every((r, i) => r.name === NAMES[i])) roster = d; } catch (e) { /* none */ }
  const save = () => { try { localStorage.setItem(DRAFT, JSON.stringify(roster)); } catch (e) { /* private window */ } };
  function edited() { save(); render(); }

  // ---- the pack's roster section: per roster fighter (bm_chars order) its four roles as indices in its pool ----------
  function spmap() {
    const out = [];
    roster.forEach(r => { const pool = X.pool[r.name].map(p => p.input); for (const [k] of ROLES) { const i = r.specials[k] ? pool.indexOf(r.specials[k]) : -1; out.push(i < 0 ? 0xFF : i); } });
    return out;
  }
  function test() {                             // the pack (stages, enemies, this map) + the Chain Lab training, one tick
    const p = window.stagesTab.pack();
    if (!p.bytes) { msg('pack not valid: ' + p.errors.join('; ')); return; }
    lab.installPack(p.bytes);
    lab.request(1, ci, dummy);
    if (CLAB.paused) CLAB.togglePause();
    CLAB.stepFrames(1);
    msg(`${up(roster[ci].name)} against ${up(NAMES[dummy])} with these specials: play D, forward+D, down+D, up+D (W A S D + P).`);
  }
  let note = '';
  const msg = t => { note = t; const e = $('chMsg'); if (e) e.textContent = t; };

  $('tabChars').onclick = () => window.labTab('chars');
  addEventListener('labtab', ev => { if (ev.detail === 'chars') render(); });

  // ---- labels ---------------------------------------------------------------------------------------------------------
  function stateName(game, st) {
    if (game === 'kof96') return `state ${st}`;
    if (st >= 336 && st <= 343) return `win pose (${st})`;
    if (st === 347) return `walk-in (${st})`;
    if (st === 348) return `intro (${st})`;
    if (st >= 349) return `special intro (${st})`;
    return `state ${st}`;
  }
  const poseText = (game, [st, step]) => `${stateName(game, st)}, ${step === 0 ? 'first' : step === -1 ? 'last' : 'step ' + step} frame`;
  const unlockText = u => u === 'always' || !u ? 'always playable' : `unlocked by beating stage ${u.boss_of_stage}'s boss`;
  const samePose = (a, b) => a.frame === b.frame && a.step === b.step;
  const face = i => h('span', { class: 'face', style: `background-image:url(stages/faces.png);background-position:-${32 * i}px 0` });
  function pic(P, x, w, H, scale = 2) {         // a picture from a 1x sheet, at `scale`
    return h('span', { class: 'shot', style: `display:inline-block;width:${w * scale}px;height:${H * scale}px;background-image:url(${P.sheet});` +
      `background-size:auto ${H * scale}px;background-position:-${x * scale}px 0;background-repeat:no-repeat;image-rendering:pixelated` });
  }
  function specData(sp) {
    if (!sp) return 'no special: the role falls back to the nearest one the fighter has';
    const hits = sp.hits.length, dmg = sp.hits.reduce((a, x) => a + x[1], 0);
    return [`${sp.rows} frames`, sp.first !== null ? `first hit frame ${sp.first + 1}` : 'no hit box',
      sp.proj ? `projectile from frame ${sp.proj.row + 1} (${sp.proj.kind === 1 ? 'travelling' : 'eruption'}, ${sp.proj.travel} px)` : `${hits} hit${hits === 1 ? '' : 's'}, damage ${dmg}`,
      `moves ${sp.travel} px forward, ${sp.height} px up`, sp.cont ? `follow-up on hit from frame ${sp.cont + 1}` : null].filter(Boolean).join(' · ');
  }

  // ---- render ---------------------------------------------------------------------------------------------------------
  const order = X.slots.map((s, k) => [s, k]).sort((a, b) => a[0].row - b[0].row || a[0].x - b[0].x);
  function render() {
    if (window.labTabName !== 'chars') return;
    const r = roster[ci], o = ORIG[ci], game = r.bank.split(':')[0], name = r.name;
    const list = h('div', { id: 'chList' }, order.filter(([s]) => s.fighter).map(([s, k]) => {
      const i = NAMES.indexOf(s.fighter), rr = roster[i], ed = JSON.stringify(rr) !== JSON.stringify(ORIG[i]);
      return h('button', { class: i === ci ? 'on' : '', onclick: () => { ci = i; render(); }, title: `select slot ${k + 1}` },
        face(i), h('span', {}, h('b', {}, `${k + 1}. ${up(rr.name)}${ed ? ' ●' : ''}`), h('br'), `${rr.bank} · ${rr.unlock === 'always' ? 'always' : 'boss ' + rr.unlock.boss_of_stage}`));
    }));
    // fighter head + unlock + colour sets
    const S = X.sets[name];
    const unlockSel = h('select', { onchange: e => { r.unlock = e.target.value === '0' ? 'always' : { boss_of_stage: Number(e.target.value) }; edited(); } },
      [h('option', { value: 0 }, 'always playable'), ...Array.from({ length: X.stages }, (_, s) => h('option', { value: s + 1 }, `beat stage ${s + 1}'s boss (${X.boss_of[s]})`))]);
    unlockSel.value = r.unlock === 'always' ? 0 : r.unlock.boss_of_stage;
    const head = h('div', { class: 'box' }, h('h2', {}, face(ci), h('span', {}, `${up(name)}`), h('span', { class: 'note' }, `bank ${r.bank} · roster ${ci + 1} of ${roster.length}`), h('span', { class: 'sp' }),
        h('button', { onclick: () => { roster[ci] = clone(ORIG[ci]); edited(); } }, 'Reset this fighter')),
      h('div', { class: 'in' },
        h('div', { class: 'stg' }, h('label', {}, 'Unlock ', unlockSel), JSON.stringify(r.unlock) !== JSON.stringify(o.unlock) ? h('span', { class: 'ok' }, 'NEEDS A BUILD (ROM table)') : h('span', { class: 'note' }, unlockText(r.unlock))),
        h('div', { class: 'note', style: 'margin-top:8px' }, 'Colour sets (the select pose in each):'),
        h('div', { class: 'prev' }, S.sets.map(([x, w], s) => h('figure', {}, pic(S, x, w, S.h), h('figcaption', {}, `set ${s}`))))));
    // select pose picker
    const P = X.poses[name], romTile = P.current;
    const cur = P.tiles.findIndex(t => t.poses.some(([st, sp]) => st === r.watch.frame && (sp === r.watch.step || (sp === -1 && P.states[st] - 1 === r.watch.step))));
    const poseBox = h('div', { class: 'box' }, h('h2', {}, 'Select pose', h('span', { class: 'note' }, 'tap the frame this fighter holds on the select screen'), h('span', { class: 'sp' }),
        samePose(r.watch, o.watch) ? h('span', { class: 'note' }, 'the ROM\'s pose') : h('span', { class: 'ok' }, 'NEEDS A BUILD: export, then make')),
      h('div', { class: 'in' }, h('div', { class: 'poses' }, P.tiles.map((t, k) => h('button', {
        class: 'pose' + (k === cur ? ' cur' : '') + (k === romTile && k !== cur ? ' rom' : ''), 'aria-pressed': k === cur ? 'true' : 'false',
        onclick: () => { if (k === cur) return; const [st, sp] = k === romTile ? [o.watch.frame, o.watch.step] : t.poses[0]; r.watch = { frame: st, step: sp }; edited(); } },
        pic(P, t.x, t.w, P.h),
        h('span', { class: 'pl' }, k === cur ? h('b', {}, 'CURRENT') : null, k === romTile && k !== cur ? h('b', {}, 'IN THE ROM') : null,
          t.poses.slice(0, 3).map(p => h('span', {}, poseText(game, p))), t.poses.length > 3 ? h('span', {}, `+ ${t.poses.length - 3} more states`) : null))))));
    // specials
    const pool = X.pool[name], sug = X.suggest[name], SPP = X.specpics[name];
    const spCard = (sp, k) => sp ? h('div', { class: 'spc' }, h('div', { class: 'shots' }, (SPP ? SPP.specials[k] : []).map(([x, w]) => pic(SPP, x, w, SPP.h, 1))),
      h('div', { class: 'mname' }, sp.input), h('div', { class: 'mfd' }, specData(sp))) : h('div', { class: 'spc' }, h('div', { class: 'mname' }, 'none'), h('div', { class: 'mfd' }, specData(null)));
    const rows = ROLES.map(([k, label, role], ri) => {
      const v = r.specials[k], k_ = v ? pool.findIndex(p => p.input === v) : -1;
      return h('tr', { class: v !== o.specials[k] ? 'over' : '' },
        h('th', {}, label, h('br'), h('span', { class: 'note' }, role)),
        h('td', {}, spCard(k_ >= 0 ? pool[k_] : null, k_)),
        h('td', { class: 'mk' }, v !== o.specials[k] ? h('b', {}, '● edited (ROM: ' + (o.specials[k] || 'none') + ')') : 'as the ROM', h('br'),
          sug[ri] === v ? 'the suggestion' : h('span', {}, 'suggested: ' + (sug[ri] || 'none') + ' ', h('button', { onclick: () => { r.specials[k] = sug[ri]; edited(); } }, 'use it'))),
        h('td', {}, h('button', { onclick: () => pickSpecial(k, label) }, 'Change…')));
    });
    const specBox = h('div', { class: 'box' }, h('h2', {}, 'Specials', h('span', { class: 'note' }, 'live: the data pack carries them; test them on the dummy'), h('span', { class: 'sp' })),
      h('div', { class: 'in' }, h('table', { class: 'sp ai' }, h('tbody', {}, rows)),
        h('div', { class: 'row' }, h('label', {}, 'Dummy ', (() => { const s = h('select', { onchange: e => { dummy = Number(e.target.value); } }); NAMES.forEach((n, i) => s.add(new Option(up(n), i))); s.value = dummy; return s; })()),
          h('button', { onclick: test }, 'Test on the dummy'), h('span', { id: 'chMsg', class: 'note' }, note))));
    // chains
    const chainBox = h('div', { class: 'box' }, h('h2', {}, 'Chains'), h('div', { class: 'in stg' },
      h('span', {}, r.routes === 'default' ? 'the default route tree' : 'own route tree: ' + r.routes),
      h('button', { onclick: () => { $('fighter').value = ci; window.labTab('chain'); $('fighter').onchange(); } }, `Open ${up(name)} in the Chain Lab`)));
    // export / import
    const nEd = roster.filter((x, i) => JSON.stringify(x) !== JSON.stringify(ORIG[i])).length;
    const io = h('div', { class: 'box' }, h('h2', {}, 'Export / import', h('span', { class: 'note' }, `${nEd} fighter${nEd === 1 ? '' : 's'} edited; game.json's roster layout`)),
      h('div', { class: 'in row' }, h('button', { onclick: () => download(`${name}.json`, SP.fmt(r)) }, 'Export this fighter'),
        h('button', { onclick: () => download('roster.json', SP.fmt({ roster })) }, 'Export the roster'),
        h('button', { onclick: () => $('chFile').click() }, 'Import JSON'),
        h('input', { id: 'chFile', type: 'file', accept: '.json,application/json', hidden: true, onchange: e => importFile(e.target.files[0]) }),
        h('button', { onclick: () => { roster = clone(ORIG); edited(); } }, 'Reset all')));
    $('charcol').replaceChildren(h('div', { class: 'box' }, h('h2', {}, 'Roster', h('span', { class: 'note' }, 'in select-screen order (slot table)')), h('div', { class: 'in' }, list)),
      head, poseBox, specBox, chainBox, io);
  }
  function pickSpecial(k, label) {
    const r = roster[ci], pool = X.pool[r.name], SPP = X.specpics[r.name], sug = X.suggest[r.name][ROLES.findIndex(x => x[0] === k)];
    const close = () => dlg.remove();
    const choose = v => { close(); r.specials[k] = v; edited(); };
    const tile = (sp, i) => { const on = (sp ? sp.input : null) === r.specials[k];
      return h('button', { class: 'mv' + (on ? ' cur' : ''), onclick: () => choose(sp ? sp.input : null) },
        sp ? h('div', { class: 'shots' }, (SPP ? SPP.specials[i] : []).map(([x, w]) => pic(SPP, x, w, SPP.h, 1))) : null,
        h('div', { class: 'mname' }, (on ? 'CURRENT: ' : '') + (sp ? sp.input : 'none') + ((sp ? sp.input : null) === sug ? ' (suggested)' : '')),
        h('div', { class: 'mfd' }, specData(sp))); };
    const dlg = h('div', { class: 'modal', onclick: e => { if (e.target === dlg) close(); } },
      h('div', { class: 'sheet', role: 'dialog' }, h('div', { class: 'mhead' }, h('b', {}, `${up(r.name)}: ${label}`),
        h('span', {}, 'pictures: where it hits (first, last) or throws, and its projectile'), h('button', { onclick: close }, 'Close')),
        h('div', { class: 'mgrid' }, pool.map(tile), tile(null, -1))));
    document.body.append(dlg);
  }
  function download(file, text) {
    const a = h('a', { href: URL.createObjectURL(new Blob([text + '\n'], { type: 'application/json' })), download: file }); document.body.append(a); a.click(); a.remove();
  }
  async function importFile(f) {
    if (!f) return;
    try {
      const j = JSON.parse(await f.text()), list = Array.isArray(j) ? j : j.roster || [j];
      for (const e of list) {
        const i = NAMES.indexOf(e.name);
        if (i < 0) throw new Error(`no roster fighter ${e.name} (a new fighter needs a build)`);
        if (e.bank !== ORIG[i].bank) throw new Error(`${e.name}: bank ${e.bank} is not this ROM's (${ORIG[i].bank})`);
        for (const [k] of ROLES) if (e.specials[k] && !X.pool[e.name].some(p => p.input === e.specials[k])) throw new Error(`${e.name}: no special ${e.specials[k]}`);
        roster[i] = clone(e);
      }
      msg(`imported ${list.length} fighter(s)`); edited();
    } catch (e) { msg('import: ' + e.message); render(); }
  }
  window.charsTab = { spmap, test, render, get roster() { return roster; }, set roster(v) { roster = v; edited(); },
    select(k) { ci = typeof k === 'number' ? k : NAMES.indexOf(k); render(); }, set dummy(v) { dummy = v; }, X, reset() { roster = clone(ORIG); edited(); } };
})();
