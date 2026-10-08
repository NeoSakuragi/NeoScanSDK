// "Classic Brawlers' Exposé" tab: the beat 'em up encyclopedia (/data/study/encyclopedia/<set>.json, copied by
// make_site.py into expose/ with expose/index.json). Side-by-side system rules and archetypes, then one section per game:
// characters (movement, jump arc, every move's frame data and boxes), enemies and their AI. Black on white (e-ink).
(async function () {
  const $ = id => document.getElementById(id);
  const tab = $('tabExpose'), col = $('exposecol');
  if (!tab || !col) return;
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) e.setAttribute(k, v); for (const c of kids.flat(Infinity)) if (c != null && c !== false) e.append(c); return e; };
  const svg = (t, a) => { const e = document.createElementNS('http://www.w3.org/2000/svg', t); for (const [k, v] of Object.entries(a || {})) e.setAttribute(k, v); return e; };
  // readable text from any value: nested objects as "key: value" lines, source tags (src*) dropped
  const fmt = (v, d = 0) => {
    if (v == null) return '–';
    if (Array.isArray(v)) return v.map(x => fmt(x, d + 1)).join(', ');
    if (typeof v !== 'object') return String(v);
    const e = Object.entries(v).filter(([k]) => !/^src/.test(k));
    if (d > 0) return e.map(([k, x]) => k.replace(/_/g, ' ') + ' ' + fmt(x, d + 1)).join(', ');
    return e.map(([k, x]) => (k === 'rule' ? '' : k.replace(/_/g, ' ') + ': ') + fmt(x, d + 1)).join(' · ');
  };
  const txt = v => fmt(v);
  const short = v => { const s = (v && typeof v === 'object' && v.rule != null) ? String(v.rule) : fmt(v); return s.length > 260 ? h('details', {}, h('summary', {}, s.slice(0, 220) + '…'), s) : s; };
  const RULES = [['hit_stop', 'Hit-stop'], ['hit_stun', 'Hit-stun'], ['freeze', 'Other freezes'], ['damage', 'Damage'], ['link_system', 'Link system'],
    ['input_buffer', 'Input buffer'], ['knockdown', 'Knockdown / get-up'], ['throws', 'Throws'], ['juggle', 'Juggles'], ['specials_cost', 'Specials cost']];
  let loaded = false, G = [];

  function arc(j) {                                              // the jump's per-frame height as a line (y up), forward x if any
    const ys = (j && (j.trajectory_y || j.trajectory_y_neutral)) || null;
    if (!ys || !ys.length) return null;
    const xs = j.trajectory_x_fwd || j.trajectory_x || null;
    const W = 220, H = 80, n = ys.length, top = Math.max(1, ...ys.map(Math.abs));
    const s = svg('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'jump arc' });
    s.append(svg('rect', { x: 0.5, y: 0.5, width: W - 1, height: H - 1, fill: 'none', stroke: '#000' }));
    const pts = ys.map((y, i) => `${(6 + i * (W - 12) / Math.max(1, n - 1)).toFixed(1)},${(H - 6 - Math.abs(y) * (H - 12) / top).toFixed(1)}`).join(' ');
    s.append(svg('polyline', { points: pts, fill: 'none', stroke: '#000', 'stroke-width': 2 }));
    return h('figure', { class: 'arc' }, s, h('figcaption', {}, `${n} f, peak ${top} px` + (xs && xs.length ? `, forward ${Math.abs(xs[xs.length - 1] - xs[0])} px` : '')));
  }
  function hitsText(m) {
    const hs = m.hits || [];
    if (!hs.length) return '–';
    return hs.map(x => [x.damage ?? x.base_damage, x.hit_stop != null ? 'hs ' + x.hit_stop : null, x.knockdown ? 'KD' : null].filter(v => v != null).join(' ')).join(' / ');
  }
  function boxText(m) {
    const b = (m.attackboxes && m.attackboxes[0]) || (m.hits && m.hits[0] && m.hits[0].box);
    if (!b) return '–';
    return ['x', 'y', 'w', 'h'].map(k => b[k] != null ? `${k}${Math.round(b[k])}` : null).filter(Boolean).join(' ');
  }
  function movesTable(moves) {
    const head = h('tr', {}, ['Move', 'Input', 'Start', '1st act.', 'Active', 'Recov.', 'Total', 'Damage / hit-stop', 'Adv.', 'Invinc.', 'Attack box (from feet)'].map(t => h('th', {}, t)));
    const rows = (moves || []).map(m => h('tr', {},
      h('td', {}, m.name + (m.context ? ' ' : ''), m.context ? h('small', {}, '(' + m.context + ')') : null),
      h('td', {}, txt(m.input)), h('td', {}, txt(m.startup)), h('td', {}, txt(m.first_active)), h('td', {}, txt(m.active)), h('td', {}, txt(m.recovery)),
      h('td', {}, txt(m.total)), h('td', {}, hitsText(m)), h('td', {}, txt(m.advantage_on_hit)), h('td', {}, txt(m.invincible)), h('td', {}, boxText(m))));
    return h('div', { class: 'scroll' }, h('table', {}, h('thead', {}, head), h('tbody', {}, rows)));
  }
  function character(c) {
    const mv = c.movement || {}, j = mv.jump || {};
    const ht = c.height_px ? (typeof c.height_px === 'object' ? `${txt(c.height_px.idle)} px idle` : c.height_px + ' px') : null;
    const facts = [['Archetype', c.archetype], ['Height', ht], ['Walk', mv.walk_px_f != null ? mv.walk_px_f + ' px/f' : null], ['Depth', mv.depth_px_f != null ? mv.depth_px_f + ' px/f' : null],
      ['Run / dash', mv.run_note || mv.dash || (typeof mv.run_px_f === 'number' ? mv.run_px_f + ' px/f' : null)],
      ['Jump', j.air_f != null ? `${j.prejump_f ?? '?'} f crouch, ${j.air_f} f air, ${j.peak_px} px peak, forward ${j.fwd_dx_px ?? '?'} px` : null], ['Life', c.hp ?? c.life]]
      .filter(([, v]) => v != null && v !== '');
    return h('details', { class: 'chr' }, h('summary', {}, h('b', {}, c.name), ' — ', String(c.archetype || ''), ` · ${(c.moves || []).length} moves`),
      h('div', { class: 'in' }, h('dl', { class: 'facts' }, facts.map(([k, v]) => [h('dt', {}, k), h('dd', {}, String(v))])), arc(j), movesTable(c.moves)));
  }
  function enemy(e) {
    const ai = e.ai || {};
    const keys = ['states', 'approach', 'attack_decision', 'attack_selection', 'group_behaviour', 'reactions', 'grabs_on_player', 'health_phases', 'pickups_weapons', 'spawn'];
    return h('details', { class: 'chr' }, h('summary', {}, h('b', {}, e.name || '?'), (e.moves ? ` · ${e.moves.length} attacks` : '')),
      h('div', { class: 'in' }, h('dl', { class: 'facts' }, keys.filter(k => ai[k] != null).map(k => [h('dt', {}, k.replace(/_/g, ' ')), h('dd', {}, txt(ai[k]))])),
        e.moves && e.moves.length ? movesTable(e.moves) : null));
  }
  async function load() {
    if (loaded) return; loaded = true;
    let idx;
    try { idx = await (await fetch('expose/index.json', { cache: 'no-cache' })).json(); } catch (e) { col.replaceChildren(h('p', {}, 'No studies yet.')); return; }
    G = [];
    for (const f of idx.games) { try { G.push(await (await fetch('expose/' + f, { cache: 'no-cache' })).json()); } catch (e) { /* skip */ } }
    G.sort((a, b) => (a.year || 0) - (b.year || 0));
    const name = g => `${g.game} (${g.year})`;
    const rules = h('div', { class: 'scroll' }, h('table', { class: 'cmp' },
      h('thead', {}, h('tr', {}, h('th', {}, 'Rule'), G.map(g => h('th', {}, name(g))))),
      h('tbody', {}, RULES.map(([k, l]) => h('tr', {}, h('th', {}, l), G.map(g => h('td', {}, short((g.system_rules || {})[k]))))))));
    const arch = h('div', { class: 'scroll' }, h('table', { class: 'cmp' },
      h('thead', {}, h('tr', {}, ['Game', 'Character', 'Archetype', 'Height', 'Walk px/f', 'Jump air f / peak px', 'Moves'].map(t => h('th', {}, t)))),
      h('tbody', {}, G.flatMap(g => (g.characters || []).map(c => { const mv = c.movement || {}, j = mv.jump || {};
        return h('tr', {}, h('td', {}, g.game), h('td', {}, c.name), h('td', {}, txt(c.archetype)), h('td', {}, c.height_px ? txt(typeof c.height_px === 'object' ? c.height_px.idle : c.height_px) : '–'),
          h('td', {}, txt(mv.walk_px_f)), h('td', {}, j.air_f != null ? `${j.air_f} / ${j.peak_px}` : '–'), h('td', {}, String((c.moves || []).length))); })))));
    const games = G.map(g => h('section', { class: 'game' },
      h('h2', {}, name(g), ' ', h('small', {}, [g.system, g.version, g.set].filter(Boolean).join(' · '))),
      h('h3', {}, 'System rules'), h('dl', { class: 'facts' }, Object.entries(g.system_rules || {}).map(([k, v]) => [h('dt', {}, k.replace(/_/g, ' ')), h('dd', {}, txt(v))])),
      h('h3', {}, 'Playable characters'), (g.characters || []).map(character),
      g.enemies && g.enemies.length ? [h('h3', {}, 'Enemies'), g.enemies.map(enemy)] : null,
      g.bosses && g.bosses.length ? [h('h3', {}, 'Bosses'), g.bosses.map(enemy)] : null,
      g.open && g.open.length ? h('details', {}, h('summary', {}, `Not decoded yet (${g.open.length})`), h('ul', {}, g.open.slice(0, 200).map(o => h('li', {}, txt(o))))) : null));
    let syn = null;
    try { syn = await (await fetch('expose/synthesis.json', { cache: 'no-cache' })).json(); } catch (e) { /* none */ }
    const synth = syn ? h('section', { class: 'game' }, h('h2', {}, syn.title), h('p', {}, syn.intro),
      h('h3', {}, 'Universal (all 8)'), h('ul', {}, syn.universal.map(x => h('li', {}, x))),
      h('h3', {}, 'How Capcom evolved'), h('div', { class: 'scroll' }, h('table', { class: 'cmp' },
        h('thead', {}, h('tr', {}, ['Topic', 'Early (Final Fight 1989)', 'Later (1992-96)'].map(t => h('th', {}, t)))),
        h('tbody', {}, syn.evolution.map(r => h('tr', {}, h('th', {}, r[0]), h('td', {}, r[1]), h('td', {}, r[2])))))),
      h('h3', {}, 'The brakes on depth'), h('p', {}, syn.brakes),
      h('h3', {}, 'Numbers proposed for the brawler (to agree)'), h('ol', {}, syn.proposals.map(x => h('li', {}, x)))) : null;
    col.replaceChildren(h('h2', {}, "Classic Brawlers' Exposé"),
      h('p', {}, (idx.intro || '') + ' Numbers come from each game\'s program and from emulator captures; frames are game frames (the press = frame 1), pixels are each game\'s own.'),
      synth, h('h3', {}, 'System rules side by side'), rules, h('h3', {}, 'Archetypes side by side'), arch, ...games);
  }
  // the two document tabs use the full width: the game column hides while they show
  window.addEventListener('labtab', e => { const g = $('gamecol'); if (g) g.style.display = (e.detail === 'expose' || e.detail === 'quirks') ? 'none' : ''; });
  tab.onclick = () => window.labTab('expose');
  window.addEventListener('labtab', e => { if (e.detail === 'expose') load(); });
  const deep = () => { if (location.hash === '#expose') { window.labTab('expose'); load(); } };
  window.addEventListener('hashchange', deep);
  if (document.readyState === 'complete') setTimeout(deep, 300); else window.addEventListener('load', () => setTimeout(deep, 300));
})();
