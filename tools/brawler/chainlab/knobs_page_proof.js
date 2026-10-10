// Piece knobs in the Assembly pages, headless (puppeteer-core + Chrome, 420 px wide: Bruno's tablet / phone width):
// the arbitration sheet (arbitrage.html?f=robert) and the Workshop (workshop.html?f=robert) served from SITE with a stub
// of the feedback service (decisions store, lab/me, lab/config/<f>/hash, lab/ship/<f>; every POST recorded). Checks:
// the knob panel under the picked S-012 (its knobs, defaults), an overridden knob (bold, "changed from 7", solid border,
// "Back to default"), Back to default, the slot's / the sheet's "Reset all knobs", what was POSTed (knobs per slot),
// no note box / mic / "send to Claude" on the sheet, "Ask in the Workshop" (pre-filled request), "Ship to game" (queued),
// no horizontal scroll. Screens to OUT.
//   NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules node knobs_page_proof.js SITE OUT
const http = require('http'), fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [site, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const store = { 'robert-arb': { sp_fc: { choice: 1, label: 'picked', pieces: ['S-012'], knobs: { 'S-012': { speed: 9 } } }, sp_c: { choice: 1, label: 'picked', pieces: ['S-012'] } }, 'robert-workshop': {} };
const posts = [];
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.css': 'text/css' };
const srv = http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'); let p = decodeURIComponent(u.pathname);
  const js = (code, o) => { r.writeHead(code, { 'Content-Type': 'application/json' }); r.end(JSON.stringify(o)); };
  if (p.startsWith('/feedback-api/')) {
    p = p.slice('/feedback-api/'.length);
    if (q.method === 'POST') {
      let b = ''; q.on('data', c => b += c); q.on('end', () => {
        const j = b ? JSON.parse(b) : {}; posts.push({ path: p, body: j });
        if (p === 'decision') {
          const s = store[j.set] = store[j.set] || {}, a = s[j.id] = s[j.id] || {};
          for (const k of ['choice', 'label', 'note', 'question', 'pieces', 'knobs']) if (k in j) { if (j[k] === null || (k === 'knobs' && !Object.keys(j[k]).length)) delete a[k]; else a[k] = j[k]; }
          return js(200, { ok: true, answer: a });
        }
        if (p === 'lab/ship/robert') return js(200, { ship: { id: 7, fighter: 'robert', rev: j.rev, status: 'pending' } });
        js(404, {});
      });
      return;
    }
    if (p.startsWith('decisions/')) return js(200, store[p.slice(10)] || {});
    if (p === 'lab/me') return js(200, { user: 'bruno', role: 'admin' });
    if (p === 'lab/config/robert/hash') return js(200, { hash: 'abc', version: 4, updated: '2026-10-10T12:00:00Z' });
    if (p === 'lab/config/robert') return js(404, {});
    return js(404, {});
  }
  const f = path.join(site, p === '/' ? 'index.html' : p);
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
});
const rep = {}; let ok = true;
const check = (name, cond, detail) => { rep[name] = { pass: !!cond, detail }; ok = ok && !!cond; console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail !== undefined ? '  ' + JSON.stringify(detail) : '')); };
srv.listen(0, async () => {
  const base = `http://127.0.0.1:${srv.address().port}/`;
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const pg = await browser.newPage();
    await pg.setViewport({ width: 420, height: 900, deviceScaleFactor: 1 });
    const errs = []; pg.on('pageerror', e => errs.push(e.message));
    await pg.goto(base + 'arbitrage.html?f=robert', { waitUntil: 'networkidle0' });
    await pg.waitForFunction(() => window.arbReady, { timeout: 20000 });
    const slot = '#slot-sp_fc';
    const info = await pg.$eval(slot, el => ({ rows: [...el.querySelectorAll('.krow')].map(r => ({ id: r.dataset.knob, over: r.classList.contains('over'), chg: r.querySelector('.kchg').textContent, def: r.querySelector('.kdef').textContent, back: !r.querySelector('.kback').hidden, bold: getComputedStyle(r.querySelector('.kval')).fontWeight, border: getComputedStyle(r).borderTopStyle + ' ' + getComputedStyle(r).borderTopWidth })) }));
    check('sheet: S-012 knobs under forward + C', info.rows.map(r => r.id).join() === 'speed,hits,damage', info.rows.map(r => r.id));
    const sp = info.rows[0];
    check('sheet: saved speed 9 shown overridden', sp.over && sp.chg === 'changed from 7' && sp.back && +sp.bold >= 700 && sp.border === 'solid 3px', sp);
    check('sheet: defaults shown', info.rows[0].def.startsWith('Default 7 px/frame') && info.rows[1].def.startsWith('Default 1 hits'), info.rows.map(r => r.def));
    check('sheet: no note box, no mic, no "send to Claude"', await pg.evaluate(() => !document.querySelector('#arb textarea') && !document.querySelector('.micfield, .mic') && !/send to Claude/i.test(document.body.innerText)));
    // hits + 2 (the + button twice)
    const plus = async (k, n) => { for (let i = 0; i < n; i++) await pg.click(`${slot} .krow[data-knob="${k}"] .kctl button:nth-of-type(2)`); };
    await plus('hits', 2); await new Promise(r => setTimeout(r, 900));
    const lastKn = () => { const p = posts.filter(x => x.body.id === 'sp_fc' && 'knobs' in x.body).pop(); return p && p.body.knobs; };
    check('sheet: hits 3 saved with speed 9 (one slot, its pieces)', JSON.stringify(lastKn()) === JSON.stringify({ 'S-012': { speed: 9, hits: 3 } }), lastKn());
    await pg.$eval(slot, el => el.scrollIntoView());
    await pg.screenshot({ path: path.join(out, 'sheet_overridden_420.png'), fullPage: false });
    await pg.click(`${slot} .krow[data-knob="speed"] .kback`); await new Promise(r => setTimeout(r, 900));
    const sp2 = await pg.$eval(`${slot} .krow[data-knob="speed"]`, r => ({ over: r.classList.contains('over'), chg: r.querySelector('.kchg').textContent, val: r.querySelector('input[type=number]').value }));
    check('sheet: Back to default -> 7, marker gone', !sp2.over && sp2.chg === '' && sp2.val === '7' && JSON.stringify(lastKn()) === JSON.stringify({ 'S-012': { hits: 3 } }), [sp2, lastKn()]);
    await pg.click(`${slot} .kreset-slot`); await new Promise(r => setTimeout(r, 900));
    check('sheet: Reset all knobs of this slot', JSON.stringify(lastKn()) === '{}' && await pg.$$eval(`${slot} .krow.over`, l => l.length) === 0, lastKn());
    // the other slot with the same piece: its own values (the same piece, independent knobs)
    await plus.call(null, 'speed', 0);
    await pg.click('#slot-sp_c .krow[data-knob="speed"] .kctl button:nth-of-type(2)'); await new Promise(r => setTimeout(r, 900));
    const cK = posts.filter(x => x.body.id === 'sp_c' && 'knobs' in x.body).pop();
    check('sheet: the same piece on C keeps its own value', cK && JSON.stringify(cK.body.knobs) === JSON.stringify({ 'S-012': { speed: 8 } }) && await pg.$$eval('#slot-sp_fc .krow.over', l => l.length) === 0, cK && cK.body.knobs);
    const sheet = await pg.evaluate(() => window.arbSheet());
    check('sheet: Try / Send carry the knobs per slot', JSON.stringify(sheet.knobs) === JSON.stringify({ sp_c: { 'S-012': { speed: 8 } } }), sheet.knobs);
    await pg.click('.kreset-sheet'); await new Promise(r => setTimeout(r, 900));
    check('sheet: Reset all knobs of the sheet', !(store['robert-arb'].sp_c.knobs) && await pg.$$eval('.krow.over', l => l.length) === 0);
    const ask = await pg.$eval('#slot-sp_fc a.ask', a => ({ href: a.getAttribute('href'), text: a.textContent }));
    check('sheet: "Ask in the Workshop" link', /workshop\.html\?f=robert&ask=S-012&text=/.test(ask.href), ask);
    await pg.click('.final .done'); await pg.waitForFunction(() => /Queued|Not queued/.test(document.querySelector('.final .saved').textContent), { timeout: 5000 });
    const shipTxt = await pg.$eval('.final .saved', e => e.textContent);
    const shipPost = posts.find(x => x.path === 'lab/ship/robert');
    check('sheet: Ship to game queued with the live revision', shipTxt.startsWith('Queued') && shipPost && shipPost.body.rev === 4, shipTxt);
    check('sheet: no horizontal scroll at 420 px', await pg.evaluate(() => document.documentElement.scrollWidth <= 420), await pg.evaluate(() => document.documentElement.scrollWidth));
    await pg.screenshot({ path: path.join(out, 'sheet_final_420.png'), fullPage: false });
    await pg.$eval('#slot-sp_fc', el => el.scrollIntoView());
    await pg.screenshot({ path: path.join(out, 'sheet_reset_420.png'), fullPage: false });
    check('sheet: no page error', !errs.length, errs);
    // the Workshop: knobs under S-012, a change, the pre-filled request
    const pw = await browser.newPage(); await pw.setViewport({ width: 420, height: 900 });
    const werrs = []; pw.on('pageerror', e => werrs.push(e.message));
    await pw.goto(base + 'workshop.html?f=robert&ask=S-012&text=' + encodeURIComponent('Arbitration sheet, slot "forward + C" (S-012): '), { waitUntil: 'networkidle0' });
    await pw.waitForFunction(() => window.workshopReady, { timeout: 20000 });
    const wta = await pw.$eval('#S-012 .thread textarea', t => t.value);
    check('workshop: request pre-filled from the sheet', wta.startsWith('Arbitration sheet, slot "forward + C"'), wta);
    check('workshop: S-012 knobs', await pw.$$eval('#S-012 .krow', l => l.map(r => r.dataset.knob).join()) === 'speed,hits,damage');
    for (let i = 0; i < 5; i++) await pw.click('#S-012 .krow[data-knob="speed"] .kctl button:nth-of-type(2)');
    await new Promise(r => setTimeout(r, 900));
    const wk = posts.filter(x => x.body.id === 'knobs-S-012').pop();
    check('workshop: speed 12 saved (knobs-S-012, no thread message)', wk && JSON.stringify(wk.body.knobs) === JSON.stringify({ 'S-012': { speed: 12 } }) && !wk.body.choice, wk && wk.body);
    await pw.$eval('#S-012 .knobs', el => el.scrollIntoView());
    await pw.screenshot({ path: path.join(out, 'workshop_knobs_420.png') });
    check('workshop: no horizontal scroll at 420 px', await pw.evaluate(() => document.documentElement.scrollWidth <= 420), await pw.evaluate(() => document.documentElement.scrollWidth));
    check('workshop: no page error', !werrs.length, werrs);
  } catch (e) { check('ran', false, e.message); }
  await browser.close(); srv.close();
  fs.writeFileSync(path.join(out, 'knobs_page_proof.json'), JSON.stringify({ rep, posts }, null, 1));
  console.log(ok ? 'ALL PASS' : 'SOME FAIL'); process.exit(ok ? 0 : 1);
});
