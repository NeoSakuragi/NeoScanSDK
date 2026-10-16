// The Factory's PLAYERS tab (players.js, the player admin console 2026-10-16), headless (puppeteer-core + Chrome, 390 px
// wide: the 6" split phone view) against REAL local services: an Oros server (the brawler-signup branch, its own DB) on
// OROS and the feedback service (tools/feedback/server.py, its own DATA) on FB. This proxy plays nginx: /brawler-factory/
// = this folder, /brawler-lab/ = chainlab/, /brawler-lab/feedback-api/ -> FB/api/, /oros/ -> OROS/, each with the admin's
// oros_token cookie. Through the page's own controls: the lists, Nightly on/off, Block (+ its IP) / Unblock, Make admin /
// Remove admin, Reset password (the temporary password shown once), Sign out everywhere, Delete (confirm + the typed
// login), Reset cloud save, Grant access, an invite code added + switched off, an IP block added + lifted, the audit log.
//   NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules node players_proof.js ADMIN_TOKEN|@FILE OUT [OROS] [FB]
// The accounts it acts on (created beforehand): Ken_44 (a tester with a session), Bot_a / Bot_b / Bot_c (brawler
// accounts), wael (an Oros tester), paulina (an Oros account without access), Ryu_44 (a tester with a cloud save).
const http = require('http'), fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [tokArg, out, OROS = 'http://127.0.0.1:8900', FB = 'http://127.0.0.1:8921'] = process.argv.slice(2);
const tok = tokArg.startsWith('@') ? fs.readFileSync(tokArg.slice(1), 'utf8').trim() : tokArg;   // @FILE: the token from a file
fs.mkdirSync(out, { recursive: true });
const FAC = __dirname, LABDIR = path.join(__dirname, '..', 'chainlab');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.css': 'text/css' };
function proxy(q, r, target) {
  const u = new URL(target);
  const h = Object.assign({}, q.headers, { cookie: 'oros_token=' + tok, host: u.host, 'x-real-ip': '203.0.113.9' });
  const p = http.request({ host: u.hostname, port: u.port, path: u.pathname + u.search, method: q.method, headers: h }, pr => { r.writeHead(pr.statusCode, pr.headers); pr.pipe(r); });
  p.on('error', e => { r.writeHead(502); r.end(String(e)); }); q.pipe(p);
}
const srv = http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'); const p = decodeURIComponent(u.pathname);
  if (p.startsWith('/brawler-lab/feedback-api/')) return proxy(q, r, FB + '/api/' + p.slice('/brawler-lab/feedback-api/'.length) + u.search);
  if (p.startsWith('/oros/')) return proxy(q, r, OROS + '/' + p.slice('/oros/'.length) + u.search);
  if (p === '/brawler-lab/cast.json') { r.writeHead(200, { 'Content-Type': 'application/json' }); return r.end('{"fighters":[]}'); }
  let f = null;
  if (p.startsWith('/brawler-factory/')) f = path.join(FAC, p.slice('/brawler-factory/'.length) || 'index.html');
  else if (p.startsWith('/brawler-lab/')) f = path.join(LABDIR, p.slice('/brawler-lab/'.length));
  if (!f) { r.writeHead(404); r.end(); return; }
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
});
let ok = true;
const check = (name, cond, detail) => { ok = ok && !!cond; console.log((cond ? 'PASS ' : 'FAIL ') + name + (detail !== undefined ? '  ' + JSON.stringify(detail).slice(0, 300) : '')); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
srv.listen(0, async () => {
  const base = `http://127.0.0.1:${srv.address().port}`;
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const pg = await browser.newPage();
    await pg.setViewport({ width: 390, height: 1600, deviceScaleFactor: 1 });
    const errs = []; pg.on('pageerror', e => errs.push(e.message));
    let promptAnswer = null; const dialogs = [];
    pg.on('dialog', async d => { dialogs.push(d.message()); if (d.type() === 'prompt') await d.accept(promptAnswer); else await d.accept(); });
    await pg.goto(base + '/brawler-factory/?tab=players', { waitUntil: 'networkidle0' });
    await pg.waitForSelector('#pPlayers details.acc[data-u]', { timeout: 20000 });
    const shot = async n => { await pg.screenshot({ path: path.join(out, n + '.png'), fullPage: true }); };
    const row = u => pg.$eval(`#pPlayers details.acc[data-u="${u}"] > summary`, e => e.textContent).catch(() => null);
    const open = async u => { await pg.$eval(`#pPlayers details.acc[data-u="${u}"]`, d => { d.open = true; }); await sleep(900); };
    const det = u => pg.$eval(`#pPlayers details.acc[data-u="${u}"] .det`, e => e.textContent).catch(() => '');
    const act = async (u, label) => { await pg.$$eval(`#pPlayers details.acc[data-u="${u}"] .acts button`, (bs, l) => { const b = bs.find(x => x.textContent === l); if (!b) throw new Error('no button ' + l); b.click(); }, label); await sleep(1200); };
    const msg = () => pg.$eval('#pPlayers > p.msg', e => e.textContent);
    const users = await pg.$$eval('#pPlayers details.acc[data-u]', ds => ds.map(d => d.dataset.u));
    check('one row per brawler account (the Oros ones too)', ['Ryu_44', 'Ken_44', 'Bot_a', 'wael', 'bruno'].every(u => users.includes(u)) && !users.includes('paulina'), users);
    const live = await pg.$eval('#plLive', e => e.textContent);
    check('Online now', /Online now/.test(live), live);
    const spect = await pg.$$eval('#plLive a.spect', as => as.map(a => a.getAttribute('href')));
    check('Spectate links to the Lab live view', spect.every(h => /^\/brawler-lab\/game\.html#sess=[0-9a-f]{8}-\d{8}-\d{6}$/.test(h)), spect);
    check('a row: tags, last seen, play, sessions, code', /tester/.test(await row('Ken_44')) && /seen/.test(await row('Ken_44')) && /sessions/.test(await row('Ken_44')) && /via BRAWLER27/.test(await row('Ken_44')), await row('Ken_44'));
    check('shared IPs flagged (the Bot_ accounts: one address)', /⚑ shared IP/.test(await row('Bot_d')), await row('Bot_d'));
    await open('Ryu_44');
    const d1 = await det('Ryu_44');
    check('details: joined, language, devices, IPs, cloud save, sessions list', /code BRAWLER27/.test(d1) && /English|Français/.test(d1) && /Devices/.test(d1) && /IPs/.test(d1) && /Cloud save/.test(d1) && /(Watch|Spectate)/.test(d1), d1);
    await shot('players_0_list');
    // nightly
    await act('Ryu_44', 'Nightly off'); check('Nightly off', !/nightly/.test(await row('Ryu_44')), await row('Ryu_44'));
    await act('Ryu_44', 'Nightly on'); check('Nightly on (row tag)', /nightly/.test(await row('Ryu_44')), await row('Ryu_44'));
    // block + IP, unblock
    await open('Ken_44');
    await pg.$eval('#pPlayers details.acc[data-u="Ken_44"] input[type=checkbox]', c => { c.checked = true; });
    await act('Ken_44', 'Block');
    check('Block: the row says blocked', /blocked/.test(await row('Ken_44')), await row('Ken_44'));
    const blocks1 = await pg.$eval('#pPlayers', e => e.textContent);
    check('Block + its IP: in the blocked addresses', /block:Ken_44/.test(blocks1));
    await shot('players_1_blocked');
    await open('Ken_44'); await act('Ken_44', 'Unblock');
    check('Unblock: tester again, its IP lifted', /tester/.test(await row('Ken_44')) && !/block:Ken_44/.test(await pg.$eval('#pPlayers', e => e.textContent)), await row('Ken_44'));
    // admin on / off (confirmed)
    await open('wael'); await act('wael', 'Make admin');
    check('Make admin (confirmed)', /admin/.test(await row('wael')) && dialogs.some(m => /Make wael a brawler admin/.test(m)), await row('wael'));
    await open('wael'); await act('wael', 'Remove admin');
    check('Remove admin', /tester/.test(await row('wael')), await row('wael'));
    // reset password: shown once
    await open('Bot_a'); await act('Bot_a', 'Reset password');
    const temp = await pg.$eval('#pPlayers details.acc[data-u="Bot_a"] .temp code', e => e.textContent).catch(() => null);
    check('Reset password: the temporary one shown, the row says temp password', /^[a-z2-9]{10}$/.test(temp || '') && /temp password/.test(await row('Bot_a')), temp);
    await shot('players_2_temp_password');
    await pg.$$eval('#pPlayers details.acc[data-u="Bot_a"] .temp button', bs => bs.find(b => b.textContent === 'Hide').click()); await sleep(300);
    check('Hide: gone for good', !(await pg.$('#pPlayers details.acc[data-u="Bot_a"] .temp')));
    // sign out everywhere
    await open('Bot_b'); await act('Bot_b', 'Sign out everywhere');
    check('Sign out everywhere', /signed out everywhere/.test(await msg()), await msg());
    // delete: confirm + typed login (a wrong one refuses)
    await open('Bot_c'); promptAnswer = 'nope'; await act('Bot_c', 'Delete account');
    check('Delete refused when the typed login differs', !!(await row('Bot_c')) && /Not deleted/.test(await msg()), await msg());
    promptAnswer = 'Bot_c'; await open('Bot_c'); await act('Bot_c', 'Delete account');
    check('Delete account (confirmed twice)', !(await row('Bot_c')), await msg());
    // reset cloud save
    await open('Ryu_44'); await act('Ryu_44', 'Reset cloud save');
    check('Reset cloud save', /cloud save reset/.test(await msg()) && /Cloud savenone/.test(await det('Ryu_44')), await msg());
    // grant an Oros account
    await pg.select('#pPlayers .card select[aria-label="Oros account"]', 'paulina');
    await pg.$$eval('#pPlayers .card button', bs => bs.find(b => b.textContent === 'Grant').click()); await sleep(1200);
    check('Grant access: paulina is a tester', /tester/.test(await row('paulina') || ''), await row('paulina'));
    // invite codes
    await pg.type('#pPlayers input[aria-label="New code"]', 'party2');
    await pg.type('#pPlayers input[aria-label="Label"]', 'second chat');
    await pg.$$eval('#pPlayers button', bs => bs.find(b => b.textContent === 'Add code').click()); await sleep(1200);
    const codes = () => pg.$$eval('#pPlayers .card', cs => cs.find(c => /Invite codes/.test(c.textContent)).textContent);
    check('Add code PARTY2 (50, on)', /PARTY2 on0 \/ 50 used/.test(await codes()), await codes());
    await pg.$$eval('#pPlayers .card details.acc', ds => { const d = ds.find(x => /PARTY2/.test(x.textContent)); d.open = true; [...d.querySelectorAll('button')].find(b => b.textContent === 'Switch off').click(); }); await sleep(1200);
    check('Switch off PARTY2', /PARTY2 off/.test(await codes()), await codes());
    check('who joined with BRAWLER27', /Joined with it/.test(await codes()) && /Ryu_44/.test(await codes()));
    // IP blocks
    await pg.type('#pPlayers input[aria-label="Address to block"]', '198.51.100.7');
    await pg.type('#pPlayers input[aria-label="Reason"]', 'spam');
    await pg.$$eval('#pPlayers button', bs => bs.find(b => b.textContent === 'Block address').click()); await sleep(1200);
    const blk = () => pg.$$eval('#pPlayers .card', cs => cs.find(c => /Blocked addresses/.test(c.textContent)).textContent);
    check('IP block added', /198\.51\.100\.7/.test(await blk()), await blk());
    await pg.$$eval('#pPlayers .card', cs => [...cs.find(c => /Blocked addresses/.test(c.textContent)).querySelectorAll('.prow')].find(p => /198\.51\.100\.7/.test(p.textContent)).querySelector('button').click()); await sleep(1200);
    check('IP block lifted', !/198\.51\.100\.7/.test(await blk()), await blk());
    // the audit log: every action above
    const audit = await pg.$$eval('#pPlayers .card.audit', cs => cs[0].textContent);
    for (const a of ['nightly off', 'block Ken_44', 'unblock', 'make admin', 'remove admin', 'reset password', 'sign out', 'delete', 'reset save', 'grant', 'code add', 'code change', 'ip block', 'ip unblock'])
      check('audit: ' + a, audit.includes(a), a);
    check('no horizontal scroll at 390 px', await pg.evaluate(() => document.documentElement.scrollWidth <= 390), await pg.evaluate(() => document.documentElement.scrollWidth));
    check('no page errors', !errs.length, errs);
    await shot('players_3_after');
  } catch (e) { check('ran', false, String(e && e.stack || e)); }
  finally { await browser.close(); srv.close(); console.log(ok ? 'ALL OK' : 'FAILED'); process.exit(ok ? 0 : 1); }
});
