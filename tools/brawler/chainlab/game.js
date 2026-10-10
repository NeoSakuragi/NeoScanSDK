/* The GAME TOOLS page (game.html; Bruno 2026-10-10: "consolidate ... one path"): the tabs that are not one fighter's.
 * The tab switch itself is stages.js labTab (it waits for the game, app.js); here: the two tabs that were pages of their
 * own (Impact sounds: impacts.js, Hit sounds: sounds.js ?f=<fighter>), loaded on their first opening; the game column
 * hidden on the reading tabs; the URL's hash = the tab (#stages #enemies #chars #select #feedback #quirks #expose #decide
 * #impacts #sounds; #fb=<id> = a feedback note's replay, feedback.js), so the old pages' links land on their tab. */
(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const LAZY = { impacts: 'impacts.js', sounds: 'sounds.js' };
  const READING = ['expose', 'quirks', 'decide', 'impacts', 'sounds'];   // full width: no game column
  const NAMES = ['stages', 'enemies', 'chars', 'select', 'feedback', 'quirks', 'expose', 'decide', 'impacts', 'sounds'];
  const loaded = {};
  window.addEventListener('labtab', e => {
    const k = e.detail, g = $('gamecol');
    if (g) g.style.display = READING.includes(k) ? 'none' : '';
    if (LAZY[k] && !loaded[k]) { loaded[k] = true; const s = document.createElement('script'); s.src = LAZY[k]; document.body.append(s); }
    if (NAMES.includes(k) && !/^#fb=/.test(location.hash) && location.hash !== '#' + k) history.replaceState(null, '', location.pathname + location.search + '#' + k);
  });
  $('tabImpacts').onclick = () => window.labTab('impacts');
  $('tabSounds').onclick = () => window.labTab('sounds');
  while (!window.labTab) await new Promise(r => setTimeout(r, 100));   // (stages.js: once the game is up)
  const route = () => {
    if (/^#fb=/.test(location.hash)) return;                           // (feedback.js opens the replay)
    const k = location.hash.slice(1);
    window.labTab(NAMES.includes(k) ? k : 'stages');
  };
  window.addEventListener('hashchange', route);
  route();
  window.gameToolsReady = true;
})();
