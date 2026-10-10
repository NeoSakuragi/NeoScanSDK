// The FIGHTER LAB (lab.html; Bruno 2026-10-10: "the Chain Lab is obsolete; the Workshop and the Assembly for the whole cast,
// data driven: pick a character, then Workshop tab, Assembly tab, a general Info tab"; "the template must be standard":
// ONE page parameterized by the fighter, never per-fighter files).
//   lab.html                        the cast grid: every roster fighter of cast.json (fighterlab.py: game.json's roster +
//                                   what the site holds for him) as his HUD face, name and status lines; the pack and the
//                                   live config read live (feedback-api/lab/catalogue, feedback-api/lab/config)
//   lab.html?f=<f>&tab=info         Info: name, faces, source game, bank, scale, archetype, chain, music theme, decoded vs
//                                   locked counts, pack + Lab build versions, live config, links, "Play him in game"
//   lab.html?f=<f>&tab=workshop     the Workshop: workshop.js itself, loaded into #ws on the tab's first opening
//   lab.html?f=<f>&tab=dictionary   his animation dictionary: anims.js, loaded into #dict (anims.html?f= redirects here)
//   lab.html?f=<f>&tab=workshop     the Workshop: workshop.js itself, loaded into #ws on the tab's first opening
//   lab.html?f=<f>&tab=assembly     the Assembly: arbitrage.js itself (sheet, chain timing, knobs, Try in game, Send to
//                                   Player, live, In the game: no staging), loaded into #arb
//   lab.html?f=<f>&tab=review       the fighter review (revamp phase 4, &q=<set>: a visual follow-up): review.js in #rev
//                                   (review.html?f= redirects here)
//   &embed=1                        the Player's WebView beside the game: no chrome, compact, the Assembly only
// A fighter whose source game has no dictionary builder (cast.json engine_note: SS2, WHP, Double Dragon today) gets his
// Info and that sentence in the Dictionary / Workshop / Assembly, never an empty page. The page is also the site's front
// page (make_site.py writes it as index.html too): an old front-page link (index.html#fb=..., #decide, #stages ...) goes
// to the Game tools (game.html), which hold the tools that are not one fighter's. body[data-tab] scopes each tab's CSS
// (lab.html), its pop-ups included. A link to another tab of the same fighter (lab.html?f=<f>&tab=...) switches tabs.
(async function () {
  'use strict';
  const AD = window.AnimDict, h = AD.h;
  const Q = new URLSearchParams(location.search);
  const f = Q.get('f'), embed = Q.get('embed') === '1';
  // the old front page's links (the Chain Lab's tabs, brawler-lab/#fb=<id> replays): the Game tools now
  if (!f && /^#(fb=|decide|quirks|expose|stages|enemies|chars|select|feedback|impacts|sounds)/.test(location.hash)) { location.replace('game.html' + location.search + location.hash); return; }
  const root = document.getElementById('lab');
  if (embed) document.body.classList.add('embed');
  const getJ = u => fetch(u, { cache: 'no-cache', credentials: 'same-origin' }).then(r => r.ok ? r.json() : null, () => null);
  const [cast, cat, cfg] = await Promise.all([getJ('cast.json'), getJ('feedback-api/lab/catalogue'), getJ('feedback-api/lab/config')]);
  if (!cast) { root.replaceChildren(h('p', { text: 'The cast (cast.json) could not be read: the site was built without fighterlab.py.' })); return; }
  const packOf = n => cat && (cat.packs || []).find(p => p.fighter === n) || null;
  const liveOf = n => cfg && (cfg.configs || []).find(c => c.fighter === n) || null;
  const when = iso => iso ? iso.slice(0, 16).replace('T', ' ') + ' UTC' : '?';
  const packLine = n => {
    const p = packOf(n);
    if (!cat) return 'pack: catalogue not read';
    if (!p) return 'no pack';
    return 'pack ' + p.version + (cat.shell && p.engine !== cat.shell.engine ? ' (built for another shell: not loadable)' : '');
  };
  const liveLine = n => { const c = liveOf(n); return !cfg ? 'live config: not read' : c ? `live config r${c.version}` : 'no live config'; };
  const dictLine = c => c.dictionary ? `dictionary: ${c.dictionary.anims} animations` : c.engine_decoded ? 'dictionary: not built yet' : `no dictionary: ${c.game} engine not decoded`;
  const wsLine = c => c.workshop ? `S pieces: ${c.workshop.unlocked} unlocked, ${c.workshop.locked} locked` : 'no workshop yet';

  // ---- the cast grid ----
  if (!f) {
    document.title = 'Fighter Lab: the cast';
    const q = h('input', { type: 'search', placeholder: 'Find a fighter', 'aria-label': 'Find a fighter by name or game' });
    const shown = h('span', { class: 'muted' });
    const cards = cast.fighters.map(c => {
      const a = h('a', { class: 'ccard' + (c.dictionary ? '' : ' nodict'), href: 'lab.html?f=' + encodeURIComponent(c.name), 'aria-label': c.display + ', ' + c.game_name },
        c.face ? h('img', { src: c.face, alt: c.display + "'s HUD portrait", width: '64', height: '64', loading: 'lazy' }) : h('span', { class: 'noface', text: 'no face' }),
        h('span', { class: 'cbody' }, h('span', { class: 'cname', text: c.display }), h('span', { class: 'cgame', text: c.game_name + ' · ' + (c.archetype || '?') }),
          h('ul', {}, [dictLine(c), wsLine(c), c.workshop ? 'knobs: ' + c.workshop.knobs : null, packLine(c.name), liveLine(c.name)].filter(Boolean).map(t => h('li', { text: t })))));
      a._txt = (c.name + ' ' + c.display + ' ' + c.game_name + ' ' + c.game).toLowerCase();
      return a;
    });
    const apply = () => { const s = q.value.trim().toLowerCase(); let n = 0; for (const a of cards) { a.hidden = !!s && !a._txt.includes(s); if (!a.hidden) n++; } shown.textContent = n + ' of ' + cards.length + ' fighters'; };
    q.oninput = apply;
    const nd = cast.fighters.filter(c => c.dictionary).length, np = cat ? (cat.packs || []).length : null;
    root.replaceChildren(
      h('h1', { text: 'The cast' }),
      h('p', { class: 'muted', text: `Every fighter of the roster (game.json, build ${cast.version}). Pick one: Info, Dictionary (every animation), Workshop (decode / unlock his moves), Assembly (what each input plays, the chain's timing; Try in game, Send to Player, Ship), Review. ${nd} of ${cast.fighters.length} have an animation dictionary` +
        (np !== null ? `; ${np} have a pack in the Character Lab catalogue` + (cat.shell ? ` (shell ${cat.shell.version})` : ', no shell published') : '; the catalogue could not be read') + '. A dashed card: no dictionary yet.' }),
      h('div', { class: 'castbar' }, q, shown),
      h('div', { class: 'cast' }, cards));
    apply();
    window.fighterLabReady = { cast: cards.length };
    return;
  }

  // ---- one fighter ----
  const C = cast.fighters.find(c => c.name === f);
  if (!C) { root.replaceChildren(h('p', {}, 'No fighter "' + f + '" in the roster. ', h('a', { href: 'lab.html', text: 'The cast' }))); return; }
  const TABS = [['info', 'Info'], ['dictionary', 'Dictionary'], ['workshop', 'Workshop'], ['assembly', 'Assembly'], ['review', 'Review']];
  let tab = embed ? 'assembly' : TABS.some(t => t[0] === Q.get('tab')) ? Q.get('tab') : 'info';
  const P = { info: h('div', { id: 'info' }), dictionary: h('section', { id: 'dict', 'aria-label': 'Animation dictionary' }), workshop: h('section', { id: 'ws', 'aria-label': 'Workshop' }),
              assembly: h('section', { id: 'arb', 'aria-label': 'Assembly' }), review: h('section', { id: 'rev', 'aria-label': 'Fighter review' }) };
  const tabLinks = TABS.map(([k, t]) => {
    const a = h('a', { href: `lab.html?f=${encodeURIComponent(f)}&tab=${k}`, text: t });
    a.onclick = e => { if (e.metaKey || e.ctrlKey || e.shiftKey) return; e.preventDefault(); show(k); };
    return a;
  });
  const loaded = {};
  const SCRIPT = { dictionary: 'anims.js', workshop: 'workshop.js', assembly: 'arbitrage.js', review: 'review.js' };
  function load(k) {
    if (loaded[k]) return;
    loaded[k] = true;
    if (k === 'dictionary' && !C.dictionary) { P[k].replaceChildren(h('p', { class: 'note', text: C.engine_decoded ? `No animation dictionary for ${C.display} yet (his engine is decoded: animdict.py can build it).` : C.engine_note })); return; }
    if (k === 'review' && !C.review) { P[k].replaceChildren(h('p', { class: 'note', text: `No fighter review for ${C.display} (review_build.py).` })); return; }
    if ((k === 'workshop' || k === 'assembly') && !C.engine_decoded) { P[k].replaceChildren(h('p', { class: 'note', text: C.engine_note })); return; }
    P[k].replaceChildren(h('p', { text: 'Loading…' }));
    const s = document.createElement('script'); s.src = SCRIPT[k];
    s.onerror = () => P[k].replaceChildren(h('p', { class: 'note', text: SCRIPT[k] + ' could not be loaded.' }));
    document.body.append(s);
  }
  function show(k) {
    tab = k; document.body.dataset.tab = k;
    for (const [n] of TABS) P[n].hidden = n !== k;
    tabLinks.forEach((a, i) => { if (TABS[i][0] === k) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    const u = new URL(location.href); u.searchParams.set('tab', k); history.replaceState(null, '', u.pathname + u.search + u.hash);
    document.title = C.display + ': ' + TABS.find(t => t[0] === k)[1] + ' · Fighter Lab';
    if (k !== 'info') load(k);
  }

  // ---- Info ----
  const p = packOf(f), live = liveOf(f);
  const row = (k, ...v) => h('tr', {}, h('th', { scope: 'row', text: k }), h('td', {}, ...v));
  const mus = C.music;
  const W = C.workshop;
  const facts = h('table', { class: 'facts' }, h('tbody', {},
    row('Name', C.display + ' ', h('code', { text: '(' + C.name + ')' })),
    row('Source game', C.game_name + ' (bank ' + C.bank + ')'),
    row('Size', C.scale === 1 ? 'scale 1.0: the source game\'s size' : 'scale ' + C.scale + ' of the source game\'s size'),
    row('Archetype', C.archetype || 'not set'),
    row('Chain', `${C.chain_len} presses` + (C.chain_custom ? ' (his own chain: game.json roster chain.links)' : ` (the ${C.archetype} archetype's length)`)),
    row('Music theme', mus ? `${mus.name}` + (mus.source ? ` (${mus.source} $${mus.cmd})` : '') + (mus.what ? ': ' + mus.what.replace(/^TODO #\d+: /, '') : '') + (mus.set_in === 'songs.json' ? ' [songs.json, not yet set as his in game.json]' : '') : 'none prepared yet'),
    row('On the select screen', C.selectable ? 'yes' + (C.unlock && C.unlock !== 'always' ? ', unlock: ' + JSON.stringify(C.unlock) : '') : 'no (a form of another fighter)'),
    row('Animation dictionary', C.dictionary ? `${C.dictionary.anims} animations (${C.dictionary.game})` : C.engine_decoded ? 'not built yet for him (his engine is decoded)' : `none: ${C.game_name}'s engine is not decoded for the Lab`),
    row('Specials (S pieces)', W ? `${W.unlocked} decoded (unlocked), ${W.locked} locked` : 'no Workshop yet'),
    row('Throws (T pieces)', W ? `${W.throws_unlocked} decoded, ${W.throws_locked} locked` : 'no Workshop yet'),
    row('Knobs', W ? `${W.knobs} on his decoded specials` : '-'),
    row('Character Lab pack', !cat ? 'the catalogue could not be read' : p ? `${p.version}, published ${when(p.published)}, ${(p.size / 1024).toFixed(0)} KB, engine ${p.engine}, ${p.versions} version${p.versions === 1 ? '' : 's'} published` +
      (cat.shell && p.engine !== cat.shell.engine ? ` — NOT loadable: the catalogue's shell ${cat.shell.version} is engine ${cat.shell.engine}` : '') : 'no pack yet'),
    row('Character Lab shell', cat && cat.shell ? `${cat.shell.version} (engine ${cat.shell.engine})` : 'none published'),
    row('This site', `game ${cast.version}, built ${when(cast.built)}`),
    row('Live config', !cfg ? 'not read' : live ? `r${live.version}, updated ${when(live.updated)} by ${live.by}` : 'none yet (the Player plays the game\'s own moves)')));
  const pics = h('div', { class: 'pics' },
    C.face ? h('figure', {}, h('img', { src: C.face, alt: C.display + "'s HUD portrait", width: '128', height: '128' }), h('figcaption', { text: 'HUD portrait (the game\'s pixels, x4)' })) : h('p', { class: 'note', text: 'No HUD portrait could be made (' + (C.face_error || 'no source picture') + ').' }),
    C.win ? h('figure', {}, h('img', { src: C.win, alt: C.display + "'s win-screen portrait" }), h('figcaption', { text: 'Win-screen / drama portrait (' + C.win_source + ')' })) : h('p', { class: 'note', text: 'No win-screen portrait yet.' }));
  const links = h('div', { class: 'links' },
    C.engine_decoded ? [h('a', { href: `lab.html?f=${f}&tab=workshop`, text: 'Workshop' }), h('a', { href: `lab.html?f=${f}&tab=assembly`, text: 'Assembly (chain, timing, specials)' })] : null,
    C.dictionary ? h('a', { href: `lab.html?f=${f}&tab=dictionary`, text: 'Animation dictionary' }) : null,
    C.review ? h('a', { href: `lab.html?f=${f}&tab=review`, text: 'Fighter review' }) : null,
    h('a', { href: 'howto.html', text: 'How to' }));
  // any link to another tab of this fighter (the tabs' own links too, e.g. "Ask in the Workshop" keeps its new window):
  // a tab switch, not a page load
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[href^="lab.html?"]');
    if (!a || a.target || e.metaKey || e.ctrlKey || e.shiftKey || e.button) return;
    const u = new URL(a.href), k = u.searchParams.get('tab');
    if (u.searchParams.get('f') !== f || !TABS.some(t => t[0] === k) || [...u.searchParams.keys()].some(x => x !== 'f' && x !== 'tab')) return;
    e.preventDefault(); show(k); if (u.hash) location.hash = u.hash; else scrollTo(0, 0);
  });
  const TI = window.TryIt;
  P.info.append(h('div', { class: 'info' },
    h('div', {}, facts, C.about ? h('details', {}, h('summary', { text: 'Notes in game.json' }), h('p', { class: 'muted', text: C.about })) : null),
    h('div', {}, pics, links,
      TI ? TI.button(f, 'Play him in game (his own moves)', () => TI.sheet(f, { slots: {} })) : null,
      TI ? h('p', { class: 'muted', text: 'Plays the Character Lab shell with his pack (the Player\'s files), else his Lab build; the button shows when one of them exists.' }) : null,
      TI ? TI.liveLine(f) : null)));
  if (!C.engine_decoded) P.info.prepend(h('p', { class: 'note', text: C.engine_note }));

  root.replaceChildren(
    h('div', { class: 'fhead' },
      C.face ? h('img', { src: C.face, alt: '', width: '64', height: '64' }) : null,
      h('div', { class: 'who' }, h('b', { text: C.display }), h('span', { text: C.game_name + ' · ' + (C.archetype || '?') + ' · ' + packLine(f) + ' · ' + liveLine(f) })),
      h('a', { href: 'lab.html', text: '← The cast' })),
    h('nav', { class: 'tabs', 'aria-label': 'Tabs' }, tabLinks),
    P.info, P.dictionary, P.workshop, P.assembly, P.review);
  show(tab);
  window.fighterLabReady = { fighter: f, tab };
})();
