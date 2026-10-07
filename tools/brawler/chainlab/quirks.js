// "Oldies quirks" tab: glitches and odd mechanics found while studying old games (quirks.json, written from the studies
// under /data/study). Each quirk: game, title, what the player does, what happens, why (the code), the brawler angle,
// screenshots. Black on white, solid borders (e-ink).
(async function () {
  const $ = id => document.getElementById(id);
  const tab = $('tabQuirks'), col = $('quirkcol');
  if (!tab || !col) return;
  const h = (t, a, ...kids) => { const e = document.createElement(t); for (const [k, v] of Object.entries(a || {})) e.setAttribute(k, v); for (const c of kids.flat()) if (c != null) e.append(c); return e; };
  let loaded = false;
  async function load() {
    if (loaded) return; loaded = true;
    let Q;
    try { Q = await (await fetch('quirks.json', { cache: 'no-cache' })).json(); }
    catch (e) { col.replaceChildren(h('p', {}, 'No quirks yet.')); return; }
    const intro = h('p', {}, Q.intro || '');
    const cards = (Q.quirks || []).map(q => h('div', { class: 'q' },
      h('h2', {}, q.title, ' ', h('small', {}, '— ' + q.game)),
      h('div', { class: 'in' },
        h('dl', {},
          q.do ? [h('dt', {}, 'What the player does'), h('dd', {}, q.do)] : null,
          q.happens ? [h('dt', {}, 'What happens'), h('dd', {}, q.happens)] : null,
          q.why ? [h('dt', {}, 'Why (in the code)'), h('dd', {}, q.why)] : null,
          q.brawler ? [h('dt', {}, 'For the brawler'), h('dd', {}, q.brawler)] : null),
        q.shots && q.shots.length ? h('div', { class: 'shots' }, q.shots.map(s =>
          h('figure', {}, h('img', { src: 'quirks/' + s.src, alt: s.caption || '', loading: 'lazy' }), h('figcaption', {}, s.caption || '')))) : null)));
    col.replaceChildren(h('h2', {}, 'Oldies quirks'), intro, ...cards);
  }
  tab.onclick = () => window.labTab('quirks');
  window.addEventListener('labtab', e => { if (e.detail === 'quirks') load(); });
  if (location.hash === '#quirks') { window.labTab('quirks'); load(); }
})();
