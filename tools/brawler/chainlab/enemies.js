/* Brawler Lab, Enemies tab: game.json's `enemies` edited in the page (name, base fighter, life, power, colours, AI preset +
 * overrides, the trimmed move list) and tested live in the in-page game: the data pack (enemypack.js + stagepack.js ->
 * lab.installPack) with the enemy test (lab req 3: P1 against this enemy, its own AI), no reload.
 * Data: enemies.json (make_site.py: build_tables.py labenemies + move_images.enemy_images' index sprites). */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const EP = window.EnemyPack, SP = window.StagePack;
  const h = (tag, attrs = {}, ...kids) => {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) { if (k.startsWith('on')) e[k] = v; else if (v !== null && v !== false && v !== undefined) e.setAttribute(k, v === true ? '' : v); }
    for (const c of kids.flat()) if (c !== null && c !== undefined && c !== false) e.append(c);
    return e;
  };
  const clone = x => JSON.parse(JSON.stringify(x));
  const sel = (options, value, onchange, attrs = {}) => {
    const s = h('select', Object.assign({ onchange: () => onchange(s.value) }, attrs));
    for (const [v, t] of options) s.add(new Option(t, v)); s.value = String(value); return s;
  };
  const numIn = (value, onchange, attrs = {}) => {
    const i = h('input', Object.assign({ type: 'number', value }, attrs));
    i.onchange = () => { const v = Number(i.value); if (Number.isFinite(v)) onchange(Math.round(v)); };
    return i;
  };
  const hex4 = w => '0x' + w.toString(16).toUpperCase().padStart(4, '0');
  const css = w => 'rgb(' + EP.rgb8(w).join(',') + ')';
  const up = n => n.toUpperCase().replace(/_/g, ' ');

  while (!window.stagesTab || !window.chainlab) await new Promise(r => setTimeout(r, 100));
  const CLAB = window.chainlab, lab = CLAB.lab, ST = window.stagesTab, CHAIN = CLAB.data;
  let X;
  try { X = await (await fetch('enemies.json', { cache: 'no-cache' })).json(); } catch (e) { $('tabEnemies').disabled = true; return; }
  const ROSTER = X.roster, IMG = X.images, ORIG = clone(X.enemies), ORIG_FILES = clone(X.route_files), PRESETS = X.presets;
  const DRAFT = 'brawlerlab.enemies.' + (lab.layout.version || '');
  let enemies = clone(ORIG), files = clone(ORIG_FILES), ei = Math.max(0, enemies.findIndex(e => e.name === 'YAKUZA')), colour = 1;
  try { const d = JSON.parse(localStorage.getItem(DRAFT)); if (d && Array.isArray(d.enemies)) { enemies = d.enemies; files = d.files || files; } } catch (e) { /* none */ }
  const save = () => { try { localStorage.setItem(DRAFT, JSON.stringify({ enemies, files })); } catch (e) { /* private window */ } };
  function edited() { cache = null; save(); render(); }

  // ---- the pack: the edited enemies + the Stages tab's stages ----------------------------------------------------------
  let cache = null;
  function stageData(D) {                     // stagepack.js's data with this tab's enemies (cached until the next edit)
    if (!cache) cache = EP.stageData(enemies, PRESETS, Object.assign({}, X, { route_files: files }), CHAIN, D);
    return cache;
  }
  function packNow() {
    const e = stageData(ST.D);
    if (e.errors.length) return { bytes: null, errors: e.errors };
    const p = SP.pack(ST.stages, e.D);
    return p.bytes ? p : { bytes: null, errors: p.errors.map(m => 'Stages tab: ' + m) };
  }
  function test() {
    const p = packNow();
    if (!p.bytes) { showErrors(p.errors); return; }
    lab.installPack(p.bytes);
    lab.enemyTest(Number($('enP1').value), ei);
    if (CLAB.paused) CLAB.togglePause();
    CLAB.stepFrames(1);
  }

  // ---- tab -----------------------------------------------------------------------------------------------------------
  $('tabEnemies').onclick = () => window.labTab('enemies');
  addEventListener('labtab', ev => { if (ev.detail === 'enemies') render(); });

  // ---- sprites: index sheets recoloured here -----------------------------------------------------------------------
  const sheets = {};
  function sheet(name) {
    if (!sheets[name]) sheets[name] = new Promise((ok, no) => {
      const im = new Image();
      im.onload = () => { const c = h('canvas', { width: im.width, height: im.height }), g = c.getContext('2d'); g.drawImage(im, 0, 0);
        const d = g.getImageData(0, 0, im.width, im.height).data, ix = new Uint8Array(im.width * im.height);
        for (let i = 0; i < ix.length; i++) ix[i] = d[i * 4]; ok({ w: im.width, ix }); };
      im.onerror = no; im.src = IMG[name].sheet;
    });
    return sheets[name];
  }
  function sprite(name, cell, pals, scale = 2) {    // a canvas, painted when its sheet is in
    const I = IMG[name], c = h('canvas', { class: 'spr', title: cell }), r = I && I.cells[cell];
    if (!r) return c;
    c.width = r[2]; c.height = r[3]; c.style.width = r[2] * scale + 'px'; c.style.height = r[3] * scale + 'px';
    sheet(name).then(S => {
      const g = c.getContext('2d'), out = g.createImageData(r[2], r[3]), lut = pals.map(p => p.map(EP.rgb8));
      for (let y = 0; y < r[3]; y++) for (let x = 0; x < r[2]; x++) {
        const v = S.ix[(r[1] + y) * S.w + r[0] + x], o = (y * r[2] + x) * 4;
        if (!(v & 15) || !lut[v >> 4]) continue;
        const col = lut[v >> 4][v & 15]; out.data[o] = col[0]; out.data[o + 1] = col[1]; out.data[o + 2] = col[2]; out.data[o + 3] = 255;
      }
      g.putImageData(out, 0, 0);
    });
    return c;
  }
  const baseOf = e => e.base === 'pool' ? (e.pool || [])[0] : (ROSTER.includes(e.base) ? e.base : e.stand_in);
  /* the palettes the game loads for enemy e (set / tint of the spawn's: shown as set 0, no tint) */
  function palsOf(e) {
    const b = baseOf(e), I = IMG[b], p = e.palette || {};
    if (!I) return [];
    const t = p.tint && p.tint !== 'none' ? X.tints[p.tint] : null;
    return EP.enemyPals(I, p.set || 0, t, p.custom ? p.custom.map(EP.num) : null);
  }

  // ---- the AI schema, grouped by what Bruno tunes ---------------------------------------------------------------------
  const DEF = { follow_ups: 1, proj_chance: 512 };
  const presetVal = (p, k) => p[k] !== undefined ? p[k] : (DEF[k] !== undefined ? DEF[k] : 0);
  const bitsOf = list => (list || []).reduce((a, f) => a | X.ai_flags[f], 0);
  const FLAG_ONE = ['token', 'grab', 'projectile', 'reversal', 'specials', 'jump_in', 'full_speed'];
  const POW2 = n => [...Array(n)].map((_, i) => 1 << i);
  const CHOICE = { proj_chance: POW2(17), rev_chance: [0, ...POW2(8)], bspec_chance: [0, ...POW2(8)], follow_ups: [0, 1, 3, 7, 15] };
  const GROUPS = [
    ['Aggression: tokens and rests', 'a rest = (base >> rest_shift) + (random & rest_random) + rest_add frames', [
      ['token', 'always holds an attack token (attacks without waiting its turn)'], ['rest_shift', 'rest base shifted right'], ['rest_random', 'random part (a mask)'],
      ['rest_add', 'added to every rest'], ['rest_start', 'rest base at spawn'], ['rest_attack', 'after a punch string'], ['rest_special', 'after a D'], ['rest_throw', 'after a throw']]],
    ['Preferred range and depth', 'px', [
      ['attack_dx', 'the token holder\'s distance'], ['hover_dx', 'the others\' distance'], ['hover_go_dx', 'a hoverer sets off again this far out'], ['hover_go_dz', '... or this far in depth'],
      ['range_min', 'punch range from'], ['range_max', 'punch range to'], ['range_dz', 'punch depth'], ['full_speed', 'walks at full speed while positioning (else half)']]],
    ['Grab', '', [['grab', 'approaches may grab'], ['grab_plan', 'approaches of 8 that walk in to grab']]],
    ['Projectile (its D)', '', [['projectile', 'fires its D at mid range'], ['spec_min', 'range from (px)'], ['spec_max', 'range to (px)'], ['spec_dz', 'depth (px)'], ['proj_chance', '1 in N a frame in range']]],
    ['Strings', 'frames', [['follow_ups', 'follow-up presses: 0 to N'], ['press_gap', 'between presses'], ['hold_gap', 'between hits in a hold']]],
    ['Reaction to attacks (boss block)', '', [['reversal', 'down+D against an attack this close'], ['rev_dx', 'px'], ['rev_dz', 'depth px'], ['rev_chance', '1 in N (0 = never)'], ['rest_rev', 'rest after it']]],
    ['Specials (boss block)', '', [['specials', 'D or forward+D (the rush)'], ['bspec_min', 'range from'], ['bspec_max', 'range to'], ['bspec_dz', 'depth'], ['bspec_chance', '1 in N (0 = never)'], ['rush_dx', 'the rush when closer (1 in 2)'], ['rest_bspec', 'rest after it']]],
    ['Jump-in (boss block)', '', [['jump_in', 'jumps in'], ['jump_min', 'range from'], ['jump_max', 'range to'], ['jump_dz', 'depth'], ['jump_chance', 'of 256'], ['rest_jump', 'rest after it'], ['air_b_dx', 'air B this close']]]];

  function aiBox(e) {
    const P = PRESETS[e.ai] || {}, over = e.ai_over || {};
    const pbits = bitsOf(P.flags), ebits = over.flags ? bitsOf(over.flags) : pbits;
    const setOver = (k, v) => {
      const o = Object.assign({}, e.ai_over || {});
      if (k === 'flags') { if (v === pbits) delete o.flags; else o.flags = FLAG_ONE.filter(f => v & X.ai_flags[f]); }
      else if (v === null || v === presetVal(P, k)) delete o[k]; else o[k] = v;
      if (Object.keys(o).length) e.ai_over = o; else delete e.ai_over;
      edited();
    };
    const rows = [];
    for (const [title, unit, fields] of GROUPS) {
      rows.push(h('tr', {}, h('th', { colspan: 5, class: 'grp' }, title, unit ? h('span', { class: 'note' }, '  ' + unit) : null)));
      for (const [k, what] of fields) {
        let pv, ev, ctl, isOver;
        if (FLAG_ONE.includes(k)) {
          const bit = X.ai_flags[k]; pv = pbits & bit ? 'on' : 'off'; ev = ebits & bit; isOver = !!over.flags && (pbits & bit) !== (ebits & bit);
          ctl = h('label', {}, h('input', { type: 'checkbox', 'data-k': k, checked: !!ev, onchange: ev2 => setOver('flags', ev2.target.checked ? ebits | bit : ebits & ~bit) }), ev ? ' on' : ' off');
        } else {
          pv = presetVal(P, k); ev = over[k] !== undefined ? over[k] : pv; isOver = over[k] !== undefined;
          if (CHOICE[k]) ctl = sel(CHOICE[k].map(v => [v, k === 'follow_ups' ? `0-${v}` : v ? `1 in ${v}` : 'never']), ev, v => setOver(k, Number(v)), { 'data-k': k });
          else {
            const max = k === 'rest_shift' ? 7 : 255;
            const n = numIn(ev, v => setOver(k, Math.max(0, Math.min(max, v))), { min: 0, max, 'data-k': k });
            const r = h('input', { type: 'range', min: 0, max, value: ev, oninput: () => { n.value = r.value; }, onchange: () => setOver(k, Number(r.value)) });
            ctl = h('span', { class: 'sl' }, r, n);
          }
        }
        rows.push(h('tr', { class: isOver ? 'over' : '' },
          h('td', {}, h('b', {}, k), h('div', { class: 'note' }, what)),
          h('td', { class: 'pv', title: 'the preset\'s value' }, String(k === 'follow_ups' ? '0-' + pv : CHOICE[k] && k !== 'follow_ups' ? (pv ? '1 in ' + pv : 'never') : pv)),
          h('td', {}, ctl),
          h('td', { class: 'mk' }, isOver ? '● override' : ''),
          h('td', {}, h('button', { disabled: !isOver, onclick: () => FLAG_ONE.includes(k) ? setOver('flags', (ebits & ~X.ai_flags[k]) | (pbits & X.ai_flags[k])) : setOver(k, null) }, 'Reset'))));
      }
    }
    return h('div', { class: 'box' }, h('h2', {}, 'AI',
        h('label', {}, 'preset ', sel(Object.keys(PRESETS).map(n => [n, n]), e.ai, v => { e.ai = v; edited(); }, { id: 'enAi' })),
        h('label', {}, 'attract demo ', sel([['', 'same'], ...Object.keys(PRESETS).map(n => [n, n])], e.attract_ai || '', v => { if (v) e.attract_ai = v; else delete e.attract_ai; edited(); })),
        h('span', { class: 'sp' }), h('button', { disabled: !e.ai_over, onclick: () => { delete e.ai_over; edited(); } }, 'Reset all overrides')),
      h('div', { class: 'in', style: 'overflow-x:auto' }, h('table', { class: 'sp ai' },
        h('tr', {}, h('th', {}, 'field'), h('th', {}, `preset (${e.ai})`), h('th', {}, 'this enemy'), h('th', {}, ''), h('th', {}, '')), rows)));
  }

  // ---- colours ---------------------------------------------------------------------------------------------------------
  function colourBox(e) {
    const b = baseOf(e), I = IMG[b], p = e.palette || {}, pals = palsOf(e);
    const setPal = f => { const q = Object.assign({}, e.palette || {}); f(q); if (Object.keys(q).length) e.palette = q; else delete e.palette; edited(); };
    const spawnSet = p.custom === undefined && p.tint === undefined;
    const setOpts = [['', spawnSet ? "the spawn's (shown: set 0)" : '0 (default)'], ...[...Array(I ? I.nsets : 1)].map((_, i) => [i, 'set ' + i])];
    const tintOpts = [['', "the spawn's (shown: none)"], ['none', 'none'], ...Object.keys(X.tints).map(n => [n, n])];
    const T = p.tint && p.tint !== 'none' ? X.tints[p.tint] : null;
    const formula = T ? `channel = ((l × ${T.mix} + channel) × ${T.mul} >> ${T.shift}) + [${T.add.join(', ')}] (R, G, B), clamped 0-31; l = (5 R + 9 G + 2 B) / 16; colours 1-15 of every palette, the dark bit dropped`
                      : 'no tint: the colours as they are';
    const cu = p.custom ? p.custom.map(EP.num) : null;
    const grid = h('div', { class: 'swatches' }, pals[0] ? pals[0].map((w, k) => h('button', { class: 'sw' + (k === colour ? ' cur' : ''), 'data-i': k, onclick: () => { colour = k; render(); },
      title: k ? `colour ${k}` : 'colour 0: transparent (the game keeps it)' }, h('span', { class: 'chip', style: `background:${k ? css(w) : '#fff'}` }, k ? '' : '×'), h('span', {}, String(k)), h('span', { class: 'hx' }, hex4(w).slice(2)))) : []);
    let editor = null;
    if (cu && colour > 0) {
      const w = cu[colour], [r, g, bb] = EP.ch5(w), dark = !!(w & 0x8000);
      const put = (nr, ng, nb, nd) => setPal(q => { const c = q.custom.map(EP.num); c[colour] = EP.word(nr, ng, nb, nd); q.custom = c.map(hex4); });
      const ch = (lbl, v, f) => { const n = numIn(v, x => f(Math.max(0, Math.min(31, x))), { min: 0, max: 31, 'data-c': lbl });
        const s = h('input', { type: 'range', min: 0, max: 31, value: v, oninput: () => { n.value = s.value; }, onchange: () => f(Number(s.value)) });
        return h('label', {}, lbl + ' ', s, n); };
      const rgb = EP.rgb8(w), hexrgb = '#' + rgb.map(v => v.toString(16).padStart(2, '0')).join('');
      editor = h('div', { class: 'ced' },
        h('div', {}, h('b', {}, `Colour ${colour}`), ` = $${hex4(w).slice(2)}: R ${r} G ${g} B ${bb} (5 bits each), dark ${dark ? 'on' : 'off'}; shown as ${hexrgb}`, cu[colour] !== pals[0][colour] ? `; after the tint $${hex4(pals[0][colour]).slice(2)}` : ''),
        h('div', { class: 'stg' }, ch('R', r, v => put(v, g, bb, dark)), ch('G', g, v => put(r, v, bb, dark)), ch('B', bb, v => put(r, g, v, dark)),
          h('label', {}, h('input', { type: 'checkbox', checked: dark, 'data-c': 'dark', onchange: ev => put(r, g, bb, ev.target.checked) }), ' dark bit'),
          h('label', {}, 'pick ', h('input', { type: 'color', value: hexrgb, onchange: ev => { const v = ev.target.value.match(/\w\w/g).map(x => parseInt(x, 16) >> 3); put(v[0], v[1], v[2], dark); } }), h('span', { class: 'note' }, ' (8 bits per channel → 5: the low 3 bits dropped)'))));
    }
    return h('div', { class: 'box' }, h('h2', {}, 'Colours', h('span', { class: 'note', style: 'font-weight:400' }, `${I ? I.npal : 0} palettes in a set; palette 0 is the body`)),
      h('div', { class: 'in' },
        h('div', { class: 'stg' },
          h('label', {}, 'Colour set ', sel(setOpts, p.set === undefined ? '' : p.set, v => setPal(q => { if (v === '') delete q.set; else q.set = Number(v); }), { id: 'enSet' })),
          h('label', {}, 'Tint ', sel(tintOpts, p.tint === undefined ? '' : p.tint, v => setPal(q => { if (v === '') delete q.tint; else q.tint = v; }), { id: 'enTint' })),
          h('label', {}, h('input', { type: 'checkbox', id: 'enCustom', checked: !!cu, onchange: ev => setPal(q => {
            if (ev.target.checked) q.custom = I.pals.slice(((q.set || 0) % I.nsets) * I.npal * 16, ((q.set || 0) % I.nsets) * I.npal * 16 + 16).map(hex4); else delete q.custom; }) }), ' custom 16 colours for palette 0')),
        h('div', { class: 'note', style: 'margin:6px 0' }, 'Tint: ' + formula),
        h('div', { class: 'note' }, cu ? 'Custom: pick a colour below, then set it. The swatches show what the game loads (after the tint).' : 'Palette 0 as the game loads it (turn on custom colours to change them):'),
        grid, editor,
        h('div', { class: 'prev' }, ['watch', 'idle', 'attack'].map(c => h('figure', {}, sprite(b, c, pals), h('figcaption', {}, { watch: 'select pose', idle: 'idle', attack: 'close C' }[c], usesOther(b, c, cu) ? h('div', { class: 'note', style: 'max-width:180px' },
          `also palette ${usesOther(b, c, cu).join(', ')} of the set: the custom colours replace palette 0 only, so the game draws these parts in the set's colours too`) : null))),
        h('div', { class: 'note' }, 'The select pose is only shown on the select screen (roster fighters); an enemy never plays it.'))));
  }

  function usesOther(b, c, cu) {                // the palettes besides 0 a picture uses (only worth saying with custom colours)
    const r = IMG[b] && IMG[b].cells[c], o = r && r[4] ? r[4].filter(p => p) : [];
    return cu && o.length ? o : null;
  }

  // ---- moves -----------------------------------------------------------------------------------------------------------
  const IN = { A: 'A', B: 'B', dA: '↓A', dB: '↓B', fA: '→A', fB: '→B', dfA: '↘A', dfB: '↘B', AB: 'A+B', D: 'D', fD: '→D', dD: '↓D', uD: '↑D' };
  function routeLines(t) {
    const out = [];
    (function walk(links, path) {
      for (const [k, ch] of Object.entries(links || {})) {
        const step = `${IN[k]} ${ch.special ? ch.special + ' special' : (ch.move || '').replace('atk_', '').replace(/_/g, ' ')}${ch.speed && ch.speed !== 1 ? ' ×' + ch.speed : ''}${ch.effect && ch.effect !== 'none' ? ' (' + ch.effect + ')' : ''}`;
        const p = path.concat(step);
        if (ch.links && Object.keys(ch.links).length) walk(ch.links, p); else out.push(p.join('  →  '));
      }
    })(t.links, []);
    return out;
  }
  function editTree(e) {                        // the Chain Lab's tree editor on this enemy's tree, as its (first) fighter
    const b = baseOf(e), fi = CHAIN.fighters.findIndex(f => f.name === b);
    const m = e.moves || 'own', X2 = Object.assign({}, X, { route_files: files });
    const t = m === 'own' ? clone(CHAIN.fighters[fi].tree) : EP.treeFor(e, b, X2, CHAIN);
    window.labTab('chain');
    $('fighter').value = fi; $('fighter').onchange(); CLAB.tree = clone(t);
    const old = $('enemyEdit'); if (old) old.remove();
    const done = () => { const x = $('enemyEdit'); if (x) x.remove(); window.labTab('enemies'); };
    $('treecol').prepend(h('div', { id: 'enemyEdit', class: 'box', style: 'padding:6px 8px;margin-bottom:8px' },
      h('b', {}, `Editing ${e.name}'s move list (as ${up(b)}). `), 'Build it to try it on the dummy here, then: ',
      h('button', { onclick: () => {
        const path = String(e.moves || '').endsWith('.json') ? e.moves : `tools/brawler/routes/enemies/${e.name.toLowerCase()}.json`;
        const tr = clone(CLAB.tree); files[path] = { fighter: null, note: `${e.name}: edited in the Brawler Lab`, links: tr.links || {}, entries: tr.entries };
        e.moves = path; done(); edited();
      } }, `Use this tree for ${e.name}`), ' ', h('button', { onclick: done }, 'Back without it')));
  }
  function movesBox(e) {
    const m = e.moves || 'own', b = baseOf(e), X2 = Object.assign({}, X, { route_files: files });
    let lines = [], err = null;
    try { const t = m === 'own' ? CHAIN.fighters.find(f => f.name === b).tree : EP.treeFor(e, b, X2, CHAIN); lines = routeLines(t); } catch (x) { err = x.message; }
    const opts = [['own', 'its fighter\'s own tree'], ['jabs', 'jabs: A, A, strong close C'], ['no_specials', 'no_specials: its own tree, no special links'],
      ...Object.keys(files).map(p => [p, 'routes file ' + p])];
    return h('div', { class: 'box' }, h('h2', {}, 'Moves (its route tree)',
        sel(opts, m, v => { if (v === 'own') delete e.moves; else e.moves = v; edited(); }, { id: 'enMoves' }), h('span', { class: 'sp' }),
        h('button', { onclick: () => editTree(e) }, 'Edit in the Chain Lab…')),
      h('div', { class: 'in' }, err ? h('div', { class: 'note' }, err) : h('ol', { class: 'routes' }, lines.slice(0, 40).map(l => h('li', {}, l))),
        lines.length > 40 ? h('div', { class: 'note' }, `… ${lines.length - 40} more`) : null,
        h('div', { class: 'note' }, 'An edited tree is saved as a routes file (tools/brawler/routes/enemies/<name>.json): "Export this enemy" carries it.')));
  }

  // ---- base picker ----------------------------------------------------------------------------------------------------
  function basePicker(e) {
    const close = () => m.remove();
    const pick = v => { if (v === 'pool') { e.base = 'pool'; e.pool = e.pool && e.pool.length ? e.pool : ROSTER.slice(0, 1); delete e.stand_in; }
                        else { e.base = v; delete e.pool; delete e.stand_in; } close(); edited(); };
    const m = h('div', { class: 'modal', onclick: ev => { if (ev.target === m) close(); } },
      h('div', { class: 'sheet' }, h('div', { class: 'mhead' }, h('b', {}, `Base fighter for ${e.name}`), h('span', {}, 'its select pose, colour set 0'), h('button', { onclick: close }, 'Close')),
        h('div', { class: 'mgrid' }, ROSTER.map(n => h('button', { class: 'mv' + (baseOf(e) === n && e.base !== 'pool' ? ' cur' : ''), onclick: () => pick(n) },
          sprite(n, 'watch', IMG[n] ? EP.enemyPals(IMG[n], 0, null, null) : [], 1), h('span', { class: 'mname' }, up(n)))),
          h('button', { class: 'mv' + (e.base === 'pool' ? ' cur' : ''), onclick: () => pick('pool') }, h('span', { class: 'mname' }, 'A pool'), h('span', {}, 'one fighter picked per spawn')))));
    document.body.append(m);
  }

  // ---- the tab ---------------------------------------------------------------------------------------------------------
  function showErrors(errs) { const e = $('enErr'); if (!e) return; e.textContent = errs.length ? 'Not valid (fix these before testing):\n' + errs.join('\n') : ''; e.classList.toggle('show', !!errs.length); }
  function face(name) { const i = ROSTER.indexOf(name); return h('span', { class: 'face', title: name, style: `background-image:url(stages/faces.png);background-position:${-i * 32}px 0` }); }
  function uniqueName(base) { let n = base.slice(0, 10), k = 2; while (enemies.some(e => e.name === n)) n = base.slice(0, 10 - String(k).length - 1) + '_' + k++; return n; }
  function render() {
    if (window.labTabName !== 'enemies') return;
    if (ei >= enemies.length) ei = enemies.length - 1;
    const e = enemies[ei], p = packNow(), same = JSON.stringify(enemies) === JSON.stringify(ORIG) && JSON.stringify(files) === JSON.stringify(ORIG_FILES);
    const p1 = $('enP1') ? $('enP1').value : String(Math.max(0, ROSTER.indexOf('terry')));
    const nameOk = EP.NAME_RE.test(e.name) && enemies.filter(x => x.name === e.name).length === 1;
    const b = baseOf(e);
    $('enemycol').replaceChildren(...[
      h('div', { class: 'row' },
        h('label', {}, 'P1 ', sel(ROSTER.map((n, i) => [i, up(n)]), p1, () => {}, { id: 'enP1' })),
        h('button', { id: 'enTest', onclick: test, title: 'installs the pack and puts P1 against this enemy (its own AI); beaten, it comes back' }, `Test ${e.name.replace(/_/g, ' ')}`),
        h('button', { onclick: () => { lab.installPack(null); CLAB.stepFrames(1); }, title: 'lab.load 4: the ROM\'s own tables from the next safe point' }, "Back to the ROM's tables"),
        h('span', { class: 'ok' }, p.bytes ? `pack ${p.bytes.length} bytes${same ? ' = today\'s enemies (no edit)' : ', edited'}` : 'pack: not valid')),
      h('div', { class: 'row' },
        h('button', { onclick: () => download(`${e.name.toLowerCase()}.json`, exportOne(e)) }, 'Export this enemy'),
        h('button', { onclick: () => download('enemies.json', SP.fmt({ enemies: enemies.map(canon), routes_files: usedFiles(enemies) }) + '\n'), title: 'game.json\'s "enemies" in its layout (merge it), with the routes files they use' }, 'Export all'),
        h('button', { onclick: () => $('enFile').click() }, 'Import JSON'),
        h('button', { disabled: same, onclick: () => { if (confirm('Drop every edit and go back to today\'s enemies?')) { enemies = clone(ORIG); files = clone(ORIG_FILES); edited(); } } }, "Today's enemies"),
        h('input', { id: 'enFile', type: 'file', accept: '.json,application/json', hidden: true, onchange: importFile })),
      h('div', { id: 'enErr' }),
      h('nav', { id: 'enList' }, enemies.map((x, k) => h('button', { class: k === ei ? 'on' : '', onclick: () => { ei = k; render(); } },
        face(baseOf(x)), h('span', {}, h('b', {}, x.name), h('br'), `${x.base === 'pool' ? 'pool of ' + (x.pool || []).length : up(x.base)}, ${x.life} life`,
          JSON.stringify(x) === JSON.stringify(ORIG.find(o => o.name === x.name)) ? null : h('span', {}, h('br'), h('b', {}, 'edited')))))),
      h('div', { class: 'row' },
        h('button', { onclick: () => { enemies.push({ name: uniqueName('NEW'), base: 'terry', life: 60, power: 0, ai: 'minion' }); ei = enemies.length - 1; edited(); } }, 'Add'),
        h('button', { onclick: () => { const c = clone(e); c.name = uniqueName(e.name); enemies.splice(ei + 1, 0, c); ei++; edited(); } }, `Duplicate ${e.name}`),
        h('button', { disabled: enemies.length <= 1, onclick: () => { if (confirm(`Delete ${e.name}? Stages that use it stop being valid.`)) { enemies.splice(ei, 1); edited(); } } }, `Delete ${e.name}`)),
      h('div', { class: 'box' }, h('h2', {}, e.name, h('span', { class: 'sp' })),
        h('div', { class: 'in stg' },
          h('label', {}, 'Name ', (() => { const i = h('input', { id: 'enName', value: e.name, maxlength: 10, style: 'width:130px' }); i.onchange = () => { e.name = i.value.toUpperCase().replace(/ /g, '_'); edited(); }; return i; })(),
            h('span', { class: 'note' }, nameOk ? ' ✓ unique, valid' : ' ✗ 1-10 of A-Z 0-9 _, a letter first, unique')),
          h('label', {}, 'HUD shows ', sel([['own', `${e.name.replace(/_/g, ' ')} (its name)`], ['fighter', 'the fighter\'s name']], e.hud === 'fighter' ? 'fighter' : 'own', v => { if (v === 'fighter') e.hud = 'fighter'; else delete e.hud; edited(); })),
          h('span', {}, 'Base ', face(b), ' ', h('b', {}, e.base === 'pool' ? 'a pool' : up(b)), e.stand_in && e.stand_in !== e.base ? ` (stand-in ${up(e.stand_in)})` : '', ' ', h('button', { onclick: () => basePicker(e) }, 'Change…')),
          h('label', {}, 'Life ', numIn(e.life, v => { e.life = v; edited(); }, { id: 'enLife', min: 1, max: 32767, title: 'at NORMAL (EASY ×0.5, HARD ×1.5, MANIAC ×2)' })),
          h('label', {}, 'Power ', numIn(e.power || 0, v => { e.power = v; edited(); }, { id: 'enPower', min: 0, max: 255, title: 'extra damage a hit, on top of the stage\'s' }))),
        e.base === 'pool' ? h('div', { class: 'in' }, 'Pool (one picked per spawn, the players\' fighters left out): ', ROSTER.map(n => h('label', { class: 'chip' },
          h('input', { type: 'checkbox', checked: (e.pool || []).includes(n), onchange: ev => { const s = new Set(e.pool || []); if (ev.target.checked) s.add(n); else s.delete(n); e.pool = ROSTER.filter(x => s.has(x)); edited(); } }), ' ' + up(n)))) : null),
      colourBox(e), aiBox(e), movesBox(e)].flat());
    showErrors(p.errors);
  }
  // game.json's key order (build_tables.py format keeps it)
  function canon(e) {
    const o = {};
    for (const k of ['name', 'base', 'pool', 'stand_in', 'life', 'power', 'ai', 'attract_ai', 'hud', 'ai_over', 'palette', 'moves']) if (e[k] !== undefined) o[k] = e[k];
    return o;
  }
  const usedFiles = list => Object.fromEntries(Object.entries(files).filter(([p]) => list.some(e => e.moves === p)));
  const exportOne = e => SP.fmt({ enemy: canon(e), routes_files: usedFiles([e]) }) + '\n';
  function download(name, text) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'application/json' })); a.download = name; a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  async function importFile() {
    const f = $('enFile').files[0]; if (!f) return;
    try {
      const j = JSON.parse(await f.text());
      Object.assign(files, j.routes_files || {});
      const list = j.enemy ? [j.enemy] : Array.isArray(j.enemies) ? j.enemies : j.name && j.base ? [j] : null;
      if (!list) throw new Error('not an enemy, an enemies list or a game.json');
      for (const x of list) { const k = enemies.findIndex(y => y.name === x.name); if (k >= 0) enemies[k] = x; else enemies.push(x); ei = enemies.findIndex(y => y.name === x.name); }
      edited();
    } catch (x) { showErrors(['Import: ' + x.message]); }
    $('enFile').value = '';
  }
  window.enemiesTab = { get enemies() { return enemies; }, set enemies(v) { enemies = v; edited(); }, get files() { return files; },
    select(k) { ei = typeof k === 'number' ? k : enemies.findIndex(e => e.name === k); render(); }, pack: packNow, stageData, test, pals: () => palsOf(enemies[ei]),
    get colour() { return colour; }, set colour(k) { colour = k; render(); }, render, X, reset() { enemies = clone(ORIG); files = clone(ORIG_FILES); edited(); } };
})();
