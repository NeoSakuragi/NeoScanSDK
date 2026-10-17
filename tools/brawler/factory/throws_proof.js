// The Factory's THROWS tab (throws.js, the throw editor 2026-10-16), headless (puppeteer-core + Chrome, 390 px wide: the
// 6" split phone view): the page served from the repo (/brawler-factory/ = this folder, /brawler-lab/ = chainlab/, the
// throw review's captures from SITE/review/throws2/) with a stub of the feedback service that KEEPS the draft across
// reloads: GET lab/throws = {game: STATE (throwcfg.py state), draft}, POST lab/throws = the new draft, POST ship_batch =
// a queued ship. Through the page's own controls: Terry's back throw opened (its frame strip), a 2nd impact added on
// frame 28 with a 40 % share, the launch moved 49 -> 45 and sent AWAY, size big, held until 40; an invalid edit (launch
// before the last impact) refused inline with Save disabled, then fixed; Save; RELOAD: the row shows the draft +
// "unshipped"; "Ship throws to testers" queues {throws: true}. Writes OUT/draft.json (the last POST: what the ship service
// merges, throwcfg.py merge) and screens.
//   NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules node throws_proof.js STATE.json SITE OUT
const http = require('http'), fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [statePath, site, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const STATE = JSON.parse(fs.readFileSync(statePath, 'utf8'));
const FAC = __dirname, LABDIR = path.join(__dirname, '..', 'chainlab');
let draft = null; const posts = []; const ships = [];
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.css': 'text/css', '.webp': 'image/webp' };
const srv = http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'); let p = decodeURIComponent(u.pathname);
  const js = (code, o) => { r.writeHead(code, { 'Content-Type': 'application/json' }); r.end(JSON.stringify(o)); };
  if (p.startsWith('/brawler-lab/feedback-api/')) {
    p = p.slice('/brawler-lab/feedback-api/'.length);
    if (q.method === 'POST') {
      let b = ''; q.on('data', c => b += c); q.on('end', () => {
        const j = b ? JSON.parse(b) : {}; posts.push({ path: p, body: j });
        if (p === 'lab/throws') { draft = Object.assign({}, j, { rev: (draft ? draft.rev : 0) + 1, by: 'proof' }); return js(200, { game: STATE, draft }); }
        if (p === 'lab/ship_batch') { const s = Object.assign({ id: ships.length + 1, status: 'pending', fighters: [], at: new Date().toISOString() }, j, { throws: draft && draft.rev }); ships.push(s); return js(200, { ship: s }); }
        js(404, {});
      });
      return;
    }
    if (p === 'lab/throws') return js(200, { game: STATE, draft });
    if (p === 'lab/ship') return js(200, { requests: ships, now: new Date().toISOString() });
    if (p === 'lab/config') return js(200, { configs: [] });
    return js(404, {});
  }
  if (p === '/brawler-lab/cast.json') return js(200, { fighters: [] });
  let f = null;
  if (p.startsWith('/brawler-factory/')) f = path.join(FAC, p.slice('/brawler-factory/'.length) || 'index.html');
  else if (p.startsWith('/brawler-lab/review/')) f = path.join(site, p.slice('/brawler-lab/'.length));
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
    await pg.setViewport({ width: 390, height: 1400, deviceScaleFactor: 1 });
    const errs = []; pg.on('pageerror', e => errs.push(e.message));
    await pg.goto(base + '/brawler-factory/?tab=throws', { waitUntil: 'networkidle0' });
    await pg.waitForSelector('#pThrows .trw', { timeout: 20000 });
    const rowTxt = id => pg.$eval('#tr-' + id, e => e.textContent);
    const shot = async n => { await pg.screenshot({ path: path.join(out, n + '.png'), fullPage: true }); };
    check('one row per fighter x throw', (await pg.$$('#pThrows .trw')).length === STATE.rows.length, (await pg.$$('#pThrows .trw')).length);
    check('Terry back shows the game\'s events', /I34 L49↑m/.test(await rowTxt('terry-back')), await rowTxt('terry-back'));
    check('Terry forward (throws.timing) says old timing', /old timing/.test(await rowTxt('terry-fwd')), await rowTxt('terry-fwd'));
    await shot('throws_0_list');
    await pg.click('#tr-terry-back'); await sleep(500);
    const strip = await pg.$$('#pThrows .strip button');
    check('the frame strip of the capture', strip.length === 85 || strip.length > 40, strip.length);
    check('the strip tags the game\'s impact and launch', await pg.$eval('#pThrows .strip', s => s.children[33].textContent === '34 I' && s.children[48].textContent === '49 L↑'));
    const frame = async n => { await pg.click(`#pThrows .strip button[aria-label="Frame ${n}"]`); await sleep(80); };
    const btn = async sel => { await pg.click('#pThrows ' + sel); await sleep(80); };
    await frame(28); await btn('button[data-add="impact"]');
    await pg.$eval('#pThrows input[aria-label="Impact 1 damage share %"]', e => { e.value = '40'; e.dispatchEvent(new Event('change')); }); await sleep(80);
    for (let i = 0; i < 4; i++) await btn('button[aria-label="Launch one frame earlier"]');
    await btn('button[data-dir="away"]'); await btn('button[aria-label="big"]');
    await frame(40); await btn('button[aria-label="Held on the frame shown"]');
    const errsShown = () => pg.$eval('#pThrows .errs', e => e.hidden ? [] : [...e.children].map(x => x.textContent));
    const saveOff = () => pg.$eval('#pThrows .ted button.primary', b => b.disabled);
    check('a valid edit: no problem, Save on', !(await errsShown()).length && !(await saveOff()), await errsShown());
    await shot('throws_1_edited');
    await frame(30); await btn('button[aria-label="Launch on the frame shown"]');     // launch before impact 2 (34) and held (40)
    const bad = await errsShown();
    check('an invalid edit refused inline, Save off', bad.some(t => /impact frame 34 is after the launch \(frame 30\)/.test(t)) && bad.some(t => /held 40 is after the launch/.test(t)) && await saveOff(), bad);
    await shot('throws_2_invalid');
    await frame(45); await btn('button[aria-label="Launch on the frame shown"]');
    check('fixed: Save on again', !(await errsShown()).length && !(await saveOff()));
    await btn('.ted button.primary'); await sleep(600);
    const want = { impacts: [{ frame: 28, damage: 40 }, { frame: 34 }], held: 40, launch: { frame: 45, dir: 'away', size: 'big' } };
    const last = (posts.filter(x => x.path === 'lab/throws').pop() || {}).body;
    check('Save posted the draft {throws: {terry-back: ...}}', last && JSON.stringify(last.throws) === JSON.stringify({ 'terry-back': want }), last);
    await pg.goto(base + '/brawler-factory/?tab=throws', { waitUntil: 'networkidle0' });
    await pg.waitForSelector('#pThrows .trw', { timeout: 20000 });
    const t2 = await rowTxt('terry-back');
    check('after a reload the row shows the draft, unshipped, and the game\'s', /I28\(40%\)\+34 H40 L45→b/.test(t2) && /unshipped/.test(t2) && /in game: I34 L49↑m/.test(t2), t2);
    await pg.click('#tr-terry-back'); await sleep(400);
    check('reopened: the draft\'s marks', await pg.$eval('#pThrows .strip', s => s.children[27].textContent === '28 I1' && s.children[33].textContent === '34 I2' && s.children[39].textContent === '40 H' && s.children[44].textContent === '45 L→'));
    await btn('.ted .btns button:last-child'); await sleep(200);           // Close
    const sb = await pg.$('#pThrows .tcard > .btns button.primary');
    check('Ship throws to testers on (1 pending)', await sb.evaluate(b => !b.disabled && /\(1\)/.test(b.textContent)), await sb.evaluate(b => b.textContent));
    await sb.click(); await sleep(500);
    const sp = posts.find(x => x.path === 'lab/ship_batch');
    check('ship_batch {throws: true} queued', sp && sp.body.throws === true, sp && sp.body);
    check('the row says queued', /queued/.test(await rowTxt('terry-back')), await rowTxt('terry-back'));
    // THE BOSS THROWS (2026-10-17): the bosses' rows (throwcfg.py state "boss"), their captures from SITE/review/bossthrows/
    const bossRows = STATE.rows.filter(r => r.boss);
    if (bossRows.length) {
      const mb = bossRows.find(r => r.id === 'mr_big-fwd') || bossRows[0];
      check('boss rows listed, tagged boss', /boss: /.test(await rowTxt(mb.id)), await rowTxt(mb.id));
      await pg.click('#tr-' + mb.id); await sleep(600);
      const bs = await pg.$$('#pThrows .strip button');
      check('a boss row: the boss throw review\'s frame strip', bs.length > 40, bs.length);
      if (mb.id === 'mr_big-fwd') {
        check('Mr. Big: impacts 31 + 51, launch LAND on 51 (the old rule\'s landing)', await pg.$eval('#pThrows .strip', s => s.children[30].textContent === '31 I1' && s.children[50].textContent === '51 I2 L↓'),
          await pg.$eval('#pThrows .strip', s => [s.children[30].textContent, s.children[50].textContent]));
        check('LAND pressed; impact 2 silent (spark / sound / shake off), impact 1 without shake', await pg.evaluate(() => {
          const q = s => document.querySelector('#pThrows ' + s);
          const fx = j => [...document.querySelectorAll('#pThrows [data-mark="impact' + j + '"] button[data-fx]')].map(b => b.getAttribute('aria-pressed')).join();
          return q('button[data-dir="land"]').getAttribute('aria-pressed') === 'true' && fx(1) === 'true,true,false' && fx(2) === 'false,false,false'; }));
        await btn('[data-mark="impact1"] button[data-fx="shake"]');
        check('a boss edit (impact 1 shake on): Save on', !(await errsShown()).length && !(await saveOff()));
        await btn('.ted button.primary'); await sleep(600);
        const lb = (posts.filter(x => x.path === 'lab/throws').pop() || {}).body;
        check('the boss edit saved into the draft beside Terry\'s', lb && lb.throws['terry-back'] && JSON.stringify(lb.throws['mr_big-fwd']) ===
          JSON.stringify({ impacts: [{ frame: 31 }, { frame: 51, spark: false, sound: false, shake: false }], launch: { frame: 51, dir: 'land' } }), lb && lb.throws);
      }
    }
    check('no horizontal scroll at 390 px', await pg.evaluate(() => document.documentElement.scrollWidth <= 390), await pg.evaluate(() => document.documentElement.scrollWidth));
    check('no page errors', !errs.length, errs);
    await shot('throws_3_shipped');
    fs.writeFileSync(path.join(out, 'draft.json'), JSON.stringify(Object.assign({}, last, { rev: draft.rev, by: 'proof' }), null, 1));
  } catch (e) { check('ran', false, String(e && e.stack || e)); }
  finally { await browser.close(); srv.close(); console.log(ok ? 'ALL OK' : 'FAILED'); process.exit(ok ? 0 : 1); }
});
