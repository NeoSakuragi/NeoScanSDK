// The Factory's unlock ladder editor (roster.js, Roster & select; Bruno 2026-10-15 "make the ladder data driven so that I
// can modify it from the Factory"), headless (puppeteer-core + Chrome, 390 px wide: the 6" split phone view): the page
// served from the repo (/brawler-factory/ = this folder, /brawler-lab/ = chainlab/) with a stub of the feedback service:
// GET lab/roster = {game: STATE (roster.py state), draft}, POST lab/roster = the new draft (recorded). Edits, each one
// through the page's own controls: Kim's picker -> "New rung" (a rung of one), that rung's up arrow (before Haggar's),
// Kyo's picker -> Start. Checks: the ladder card after each edit (Start + one line a rung), the POSTed draft's unlocks
// {starters, rungs}, a rung left empty dropped, no horizontal scroll at 390 px. Writes OUT/draft.json (the last POST,
// what the ship service merges: roster.py merge) and screens.
//   NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules node ladder_proof.js STATE.json OUT
const http = require('http'), fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [statePath, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const STATE = JSON.parse(fs.readFileSync(statePath, 'utf8'));
const FAC = __dirname, LABDIR = path.join(__dirname, '..', 'chainlab');
let draft = null; const posts = [];
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.css': 'text/css' };
const cast = { fighters: STATE.fighters.map(f => ({ name: f.name, display: f.display, game_name: '', face: null })) };
const srv = http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'); let p = decodeURIComponent(u.pathname);
  const js = (code, o) => { r.writeHead(code, { 'Content-Type': 'application/json' }); r.end(JSON.stringify(o)); };
  if (p.startsWith('/brawler-lab/feedback-api/')) {
    p = p.slice('/brawler-lab/feedback-api/'.length);
    if (q.method === 'POST') {
      let b = ''; q.on('data', c => b += c); q.on('end', () => {
        const j = b ? JSON.parse(b) : {}; posts.push({ path: p, body: j });
        if (p === 'lab/roster') { draft = Object.assign({}, j, { rev: posts.length }); return js(200, { game: STATE, draft }); }
        js(404, {});
      });
      return;
    }
    if (p === 'lab/roster') return js(200, { game: STATE, draft });
    if (p === 'lab/ship') return js(200, { requests: [] });
    if (p === 'lab/config') return js(200, { configs: [] });
    return js(404, {});
  }
  if (p === '/brawler-lab/cast.json') return js(200, cast);
  let f = null;
  if (p.startsWith('/brawler-factory/')) f = path.join(FAC, p.slice('/brawler-factory/'.length) || 'index.html');
  else if (p.startsWith('/brawler-lab/')) f = path.join(LABDIR, p.slice('/brawler-lab/'.length));
  if (!f) { r.writeHead(404); r.end(); return; }
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
});
let ok = true;
const check = (name, cond, detail) => { ok = ok && !!cond; console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail !== undefined ? '  ' + JSON.stringify(detail) : '')); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
srv.listen(0, async () => {
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const pg = await browser.newPage();
    await pg.setViewport({ width: 390, height: 1100, deviceScaleFactor: 1 });
    const errs = []; pg.on('pageerror', e => errs.push(e.message));
    await pg.goto(base + '/brawler-factory/?tab=chars', { waitUntil: 'networkidle0' });
    await pg.waitForSelector('.ladder .lrung', { timeout: 20000 });
    const card = () => pg.$$eval('.ladder .lrung', l => l.map(e => e.querySelector('.lk').textContent + ': ' + e.querySelector('.lf').textContent));
    const shot = async n => { await pg.$eval('#roster', e => e.scrollIntoView()); const el = await pg.$('#roster'); await el.screenshot({ path: path.join(out, n + '.png') }); };
    const U0 = STATE.unlocks;
    check('the game\'s ladder shown', JSON.stringify(await card()) === JSON.stringify(['Start: ' + U0.starters.map(n => STATE.fighters.find(f => f.name === n).display).join(', ')].concat(U0.rungs.map((r, k) => 'Rung ' + (k + 1) + ': ' + r.map(n => STATE.fighters.find(f => f.name === n).display).join(', ')))), await card());
    await shot('ladder_0_game');
    const pick = async (disp, label) => {
      const sel = `select.rung[aria-label="Ladder: ${disp}"]`;
      const v = await pg.$eval(sel, (s, l) => [...s.options].find(o => o.textContent === l).value, label);
      await pg.select(sel, v); await sleep(600);
    };
    const last = () => (posts.filter(x => x.path === 'lab/roster').pop() || {}).body;
    await pick('KIM', 'New rung');
    check('Kim -> a new rung of one (Kyo stays in rung 2)', JSON.stringify(last().unlocks.rungs) === JSON.stringify([['haohmaru', 'hanzo_ss2'], ['kyo'], ['haggar'], ['kim']]), last().unlocks);
    await shot('ladder_1_kim_new_rung');
    await pg.click('.ladder button[aria-label="Rung 4 earlier"]'); await sleep(600);
    check('rung 4 (Kim) up: before Haggar', JSON.stringify(last().unlocks.rungs) === JSON.stringify([['haohmaru', 'hanzo_ss2'], ['kyo'], ['kim'], ['haggar']]), last().unlocks);
    await pick('KYO', 'Start');
    const U = last().unlocks;
    check('Kyo -> a starter, his emptied rung dropped', JSON.stringify(U) === JSON.stringify({ starters: ['terry', 'robert', 'kyo'], rungs: [['haohmaru', 'hanzo_ss2'], ['kim'], ['haggar']] }), U);
    check('the card follows the draft', JSON.stringify(await card()) === JSON.stringify(['Start: TERRY, ROBERT, KYO', 'Rung 1: HAOHMARU, HANZO', 'Rung 2: KIM', 'Rung 3: HAGGAR']),
      await card());
    check('an "unshipped" mark on the ladder', await pg.$eval('.ladder', e => !!e.querySelector('.tag.edit')));
    check('no horizontal scroll at 390 px', await pg.evaluate(() => document.documentElement.scrollWidth <= 390), await pg.evaluate(() => document.documentElement.scrollWidth));
    check('no page errors', !errs.length, errs);
    await shot('ladder_2_final');
    fs.writeFileSync(path.join(out, 'draft.json'), JSON.stringify(last(), null, 1));
  } catch (e) { check('ran', false, String(e && e.stack || e)); }
  finally { await browser.close(); srv.close(); console.log(ok ? 'ALL OK' : 'FAILED'); process.exit(ok ? 0 : 1); }
});
