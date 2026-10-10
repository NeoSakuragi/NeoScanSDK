// The Fighter Lab (lab.html) in headless Chrome (puppeteer-core; NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules), at
// a desktop width and a phone WebView width: the cast grid shows every roster fighter; each named fighter's Info /
// Workshop / Assembly tabs render without a page error; the embed (the Player's Assembly) renders; "Try in game" plays
// the Character Lab shell + the fighter's pack (P1 = the slot fighter, one of his decoded specials played).
//   node fighterlab_proof.js BASE_URL OUT_DIR [fighters=robert,iori,kim,haohmaru] [try=robert,iori] [widths=1280,400]
//   (BASE_URL: the Lab's directory, e.g. https://canneji.duckdns.org/brawler-lab/; COOKIE=oros_token=... for the live site)
const fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [base, out, fl, tl, wl] = process.argv.slice(2);
const FIGHTERS = (fl || 'robert,iori,kim,haohmaru').split(','), TRY = (tl || 'robert,iori').split(',').filter(Boolean);
const WIDTHS = (wl || '1280,400').split(',').map(Number);
fs.mkdirSync(out, { recursive: true });
const rep = { base, pages: [], tries: [] };
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage();
  if (process.env.COOKIE) {
    const [name, value] = process.env.COOKIE.split(/=(.*)/s);
    await page.setCookie({ name, value, url: base });
  }
  if (process.env.LOGIN) {                             // the live site: through the real Oros login page (LOGIN=user:password)
    const [u, pw] = process.env.LOGIN.split(/:(.*)/s);
    await page.goto(base + 'lab.html', { waitUntil: 'load' });
    if (/login\.html/.test(page.url())) {
      await page.type('#u', u); await page.type('#p', pw);
      await Promise.all([page.waitForNavigation({ timeout: 30000 }).catch(() => null), page.click('#go')]);
      await new Promise(r => setTimeout(r, 1500));
    }
    rep.login = page.url();
    console.log('after login:', page.url());
  }
  // the proof only reads: every write to the server (the sheet's on-open push to the live config, saves) is blocked
  await page.setRequestInterception(true);
  rep.blocked = [];
  page.on('request', r => { if (r.method() !== 'GET' && /feedback-api\//.test(r.url())) { rep.blocked.push(r.method() + ' ' + r.url()); r.abort(); } else r.continue(); });
  let errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 300)));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text().slice(0, 200)); });
  page.on('response', r => { if (r.status() >= 400 && !/review\/\w+_(anims|workshop|arb)\.json|lab\/config\/|shell-[^/]*\.json|pack-[^/]*\.json/.test(r.url())) errors.push('HTTP ' + r.status() + ' ' + r.url()); });
  const visit = async (w, q, ready, shot) => {
    errors = [];
    await page.setViewport({ width: w, height: w > 600 ? 900 : 800 });
    await page.goto(base + q, { waitUntil: 'load', timeout: 120000 });
    let ok = true;
    try { await page.waitForFunction(ready, { timeout: 60000, polling: 200 }); } catch (e) { ok = false; }
    await new Promise(r => setTimeout(r, 1200));
    const info = await page.evaluate(() => ({ title: document.title, cards: document.querySelectorAll('.ccard').length, notes: [...document.querySelectorAll('.note')].map(n => n.textContent.slice(0, 160)),
      scrollW: document.documentElement.scrollWidth, vw: innerWidth, h1: (document.querySelector('#lab h1, #ws h1, #arb h1') || {}).textContent }));
    const f = path.join(out, shot + '.png');
    await page.screenshot({ path: f, fullPage: false });
    const r = Object.assign({ w, q, ready: ok, errors: errors.slice(), shot: f }, info);
    rep.pages.push(r);
    console.log(`${ok && !errors.length ? 'OK ' : 'BAD'} ${w} ${q} ${info.title} cards ${info.cards} overflow ${info.scrollW > info.vw ? info.scrollW + '>' + info.vw : 'none'} ${errors.join(' | ')}`);
    return r;
  };
  for (const w of WIDTHS) {
    await visit(w, 'lab.html', 'window.fighterLabReady && window.fighterLabReady.cast > 0', `cast_${w}`);
    for (const f of FIGHTERS) {
      await visit(w, `lab.html?f=${f}&tab=info`, 'window.fighterLabReady', `${f}_info_${w}`);
      await visit(w, `lab.html?f=${f}&tab=workshop`, `window.workshopReady || document.querySelector('#ws .note') || /No workshop/.test((document.querySelector('#ws') || {}).textContent)`, `${f}_workshop_${w}`);
      await visit(w, `lab.html?f=${f}&tab=assembly`, `window.arbReady || document.querySelector('#arb .note') || /No arbitration/.test((document.querySelector('#arb') || {}).textContent)`, `${f}_assembly_${w}`);
    }
    await visit(w, 'lab.html?f=robert&tab=assembly&embed=1', 'window.arbReady', `robert_embed_${w}`);
    await visit(w, 'workshop.html?f=robert', 'window.workshopReady', `redirect_workshop_${w}`);
  }
  // "Try in game": the shell + his pack, one of his decoded specials
  for (const f of TRY) {
    errors = [];
    await page.setViewport({ width: 1280, height: 900 });
    await page.goto(base + `lab.html?f=${f}&tab=info`, { waitUntil: 'load' });
    await page.waitForFunction('window.fighterLabReady && window.TryIt', { timeout: 60000 });
    const t0 = Date.now();
    const res = await page.evaluate(async f => {
      const W = await fetch('review/' + f + '_workshop.json', { credentials: 'same-origin' }).then(r => r.ok ? r.json() : null);
      const sp = W && W.specials.find(p => p.id);
      await window.TryIt.sheet(f, { slots: {} });
      const T = window.tryit, S = T.state, L = T.lab;
      if (!L) return { error: document.querySelector('#tryit .tnow') && document.querySelector('#tryit .tnow').textContent };
      const y = S.man.layout;
      const r = { note: S.man.note, mode: S.man.mode, title: document.querySelector('#tryit b').textContent, p1: (L.fget(0, 'ch') - y.syms.bm_chars) / y.sizeof_bchar, slot: S.man.id,
                  shell: S.man.shell && S.man.shell.version, pack: S.man.pack && S.man.pack.version, err: document.querySelector('#tryit .terr').textContent };
      if (sp) {
        await window.TryIt.queue(f, [sp.id], { loop: false });
        const seen = new Set();
        for (let i = 0; i < 90; i++) { T.gp.stepFrames(1); seen.add(L.stateName(0)); }
        Object.assign(r, { special: sp.id + ' ' + sp.name + ' (' + sp.input + ')', states: [...seen], now: document.querySelector('#tryit .tnow[aria-live]').textContent, err2: document.querySelector('#tryit .terr').textContent });
      }
      return r;
    }, f);
    res.ms = Date.now() - t0; res.fighter = f; res.errors = errors.slice();
    const shot = path.join(out, `try_${f}.png`);
    await (await page.$('#tryit')).screenshot({ path: shot });
    res.shot = shot;
    rep.tries.push(res);
    console.log('TRY', JSON.stringify(res));
  }
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rep, null, 1));
  await browser.close();
  const bad = rep.pages.filter(p => !p.ready || p.errors.length).length + rep.tries.filter(t => t.mode !== 'pack' || (!t.note && t.p1 !== t.slot) || t.err || t.err2 || (t.states && !t.states.includes('SPECIAL'))).length;
  console.log(bad ? `${bad} problem(s)` : 'all good');
})();
