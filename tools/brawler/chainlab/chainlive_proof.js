// A FIGHTER'S ASSEMBLY CHAIN, LIVE (note 20261010-210158-5d29: Bruno's Hanzo chain of dictionary animations went live as
// an empty blob): headless Chrome through the real Oros login (LOGIN=user:password, an admin), the fighter's Assembly as
// he left it (his answers are only read: a decision POST is aborted), then
//   1. no slot says "Can't go live" for a pick that can (window.arbIssues; every "Can't go live" line is reported),
//   2. "Send to Player" -> the live config's TRY blob carries his chain (lab.js tryChain: the entries per press) and the
//      revision queues a ship (POST lab/ship/<f>),
//   3. "Try this sheet in game": A every other frame on the dummy; per frame P1's piece (an attack: its animation $NN; a
//      lab entry: lab.cur) and the game's event log (each press's start, its hits) -> which press played what, when.
//   node chainlive_proof.js BASE_URL FIGHTER OUT     (screens + report.json in OUT)
const fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [base0, F, out] = process.argv.slice(2);
const base = base0.endsWith('/') ? base0 : base0 + '/';
fs.mkdirSync(out, { recursive: true });
const rep = { base, fighter: F, blocked: [], writes: [], checks: [] };
let bad = 0;
const check = (name, ok, detail) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail !== undefined ? '  ' + JSON.stringify(detail).slice(0, 700) : '')); rep.checks.push({ name, ok: !!ok, detail }); };
const settle = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 1000 });
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  const [u, pw] = (process.env.LOGIN || '').split(/:(.*)/s);
  await page.goto(base + 'lab.html', { waitUntil: 'load' });
  if (/login\.html/.test(page.url())) {
    await page.type('#u', u); await page.type('#p', pw);
    await Promise.all([page.waitForNavigation({ timeout: 30000 }).catch(() => null), page.click('#go')]);
    await settle(1500);
  }
  await page.setRequestInterception(true);
  page.on('request', r => {
    if (r.method() !== 'GET' && /feedback-api\/decision$/.test(r.url())) { rep.blocked.push(r.method() + ' ' + r.url()); return r.abort(); }
    if (r.method() !== 'GET' && /feedback-api\//.test(r.url())) rep.writes.push(r.method() + ' ' + r.url().replace(/^.*feedback-api\//, '') + ' ' + (r.postData() || '').slice(0, 160));
    r.continue();
  });
  await page.goto(base + `lab.html?f=${F}&tab=assembly`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.arbReady && window.arbIssues && window.arbTiming, { timeout: 120000, polling: 300 });
  await settle(2500);
  const iss = await page.evaluate(() => ({ issues: window.arbIssues, lines: [...document.querySelectorAll('#arb .golive')].map(e => e.closest('[id]') ? e.closest('[id]').id + ': ' + e.textContent : e.textContent),
    timing: window.arbTiming, sheet: window.arbSheet(), ingame: (document.querySelector('#arb .ingame') || {}).textContent }));
  rep.assembly = iss;
  check('the Assembly: no chain press says "Can\'t go live"', !Object.keys(iss.issues).some(k => /^a\d$/.test(k)), iss.issues);
  check('the Assembly: every "Can\'t go live" line shown is in the issues', iss.lines.length === Object.keys(iss.issues).length, iss.lines);
  await page.screenshot({ path: path.join(out, 'assembly_top.png') });
  await page.$eval('#arb .timing', e => e.scrollIntoView()).catch(() => {});
  await page.screenshot({ path: path.join(out, 'assembly_chain.png') });
  // 2. Send to Player (the sheet's: the first "Send to Player" of the page's top row)
  const sendSaid = await page.evaluate(async f => {
    const btn = [...document.querySelectorAll('#arb .tryrow .tryit-send')][0];
    if (!btn) return 'no Send button';
    btn.click();
    const said = btn.parentElement.querySelector('.tryit-said');
    for (let i = 0; i < 100 && !/^(Sent|Unchanged|Not sent)/.test(said.textContent); i++) await new Promise(r => setTimeout(r, 200));
    return said.textContent;
  }, F);
  rep.send = sendSaid;
  check('Send to Player: sent', /^(Sent|Unchanged)/.test(sendSaid), sendSaid);
  await settle(1500);
  const live = await page.evaluate(async f => {
    const r = await fetch('feedback-api/lab/config/' + f, { cache: 'no-store', credentials: 'same-origin' }), j = await r.json();
    const b = Uint8Array.from(atob(j.blob), c => c.charCodeAt(0)), CL = window.ChainLab, parts = CL.liveParts(b), ch = CL.tryChain(parts.tryBlob);
    const s = await (await fetch('feedback-api/lab/ship?fighter=' + f, { cache: 'no-store', credentials: 'same-origin' })).json();
    return { version: j.version, size: j.size, version_byte: b[2], chain: ch.chain && { entries: ch.chain.entries.map(e => e === null ? null : '0x' + e.toString(16)), hitstop: ch.chain.hitstop },
             retime: ch.retime, lc: !!parts.chain, json: j.json, ships: (s.requests || []).slice(-3) };
  }, F);
  rep.live = live;
  check('the live config carries the chain (TRY blob v3)', live.version_byte === 3 && live.chain && live.chain.entries.some(e => e !== null), live);
  check('the live send queued a ship of that revision', live.ships.some(x => x.rev === live.version), live.ships);
  // 3. Try this sheet in game
  const tr = await page.evaluate(async f => {
    await window.TryIt.sheet(f, window.arbSheet());
    const T = window.tryit, L = T.lab, gp = T.gp, S = T.state;
    if (!L) return { error: document.querySelector('#tryit .tnow').textContent };
    if (!gp.paused) gp.togglePause();
    L.request(2); gp.stepFrames(4);
    const ba = S.man.chain.ba, hexOf = {};
    for (const [m, x] of Object.entries(S.man.moves || {})) hexOf[ba.indexOf(m)] = String(x).replace(/^\$/, '').toUpperCase();
    const from = L.nev(), f0 = L.labFrame(), seq = []; let prev = '';
    for (let i = 0; i < 260; i++) {
      gp.override = i % 2 ? '' : 'a'; gp.stepFrames(1);
      const st = L.stateName(0), cur = L.tryCur(), an = L.fget(0, 'anim');
      const piece = st === 'SPECIAL' && cur !== 0xFFFF ? '$' + cur.toString(16).toUpperCase() : st === 'ATTACK' ? '$' + (hexOf[an] || '?') + ' ' + ba[an] : st;
      if (piece !== prev) seq.push([L.labFrame() - f0, piece]);
      prev = piece;
    }
    gp.override = null; gp.stepFrames(30);
    const ev = L.eventsSince(from).events.filter(e => ['START', 'HIT', 'CHAINWIN', 'END'].includes(e.kind)).map(e => [e.frame - f0, e.kind, e.node]);
    return { now: document.querySelector('#tryit .tnow[aria-live]').textContent, err: document.querySelector('#tryit .terr').textContent, status: L.tryStatus(), seq, ev, combo: L.combo() };
  }, F);
  rep.try = tr;
  console.log('Try in game:', JSON.stringify(tr).slice(0, 1500));
  await (await page.$('#tryit')).screenshot({ path: path.join(out, 'try_in_game.png') }).catch(() => {});
  check('Try in game: the sheet applied, nothing refused', tr.status === 'taken' && !tr.err, { status: tr.status, err: tr.err });
  check('no page error', !errs.length, errs);
  rep.bad = bad;
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rep, null, 1));
  await browser.close();
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
