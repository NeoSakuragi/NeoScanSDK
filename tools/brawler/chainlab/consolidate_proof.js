// The consolidated Brawler Lab (2026-10-10) in headless Chrome (puppeteer-core; NODE_PATH=/home/bruno/CLProjects/NeoGeo/
// node_modules), at 1280 and 400 px: the cast (lab.html and index.html), Robert's five tabs (Info, Dictionary, Workshop,
// Assembly with the chain timing knobs, Review), the embed (the Player's Assembly), the Game tools' ten tabs, every old URL
// redirecting, then the CHAIN TIMING measured in the game: Robert's chain played on the dummy by "Try this sheet in game"
// (A every other frame, the game's own event log: each link's start and first hit), at the game's timing, with press 1's
// startup and hit-stop knobs raised through the page, and back to default.
//   node consolidate_proof.js SITE_DIR OUT     a built site + a stub of the feedback service (decisions, lab/me admin,
//                                              lab/config, the catalogue = CATALOGUE file or none: Try = the Lab build)
//   node consolidate_proof.js BASE_URL OUT     the live site (LOGIN=user:password through the real Oros login): it never
//                                              writes: a decision POST is answered here, every other write aborted
const http = require('http'), fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [target, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const live = /^https?:/.test(target);
const rep = { target, pages: [], redirects: [], blocked: [], answered: [], puts: [] };
let bad = 0;
const check = (name, ok, detail) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail !== undefined ? '  ' + JSON.stringify(detail).slice(0, 600) : '')); (rep.checks = rep.checks || []).push({ name, ok: !!ok, detail }); };

function stub(site) {                                      // the feedback service, enough for the pages
  const store = {};
  const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.wasm': 'application/wasm', '.wav': 'audio/wav' };
  const cat = process.env.CATALOGUE ? fs.readFileSync(process.env.CATALOGUE) : JSON.stringify({ shell: null, packs: [] });
  return http.createServer((q, r) => {
    const u = new URL(q.url, 'http://x'); let p = decodeURIComponent(u.pathname);
    const js = (code, o) => { r.writeHead(code, { 'Content-Type': 'application/json' }); r.end(JSON.stringify(o)); };
    if (p.startsWith('/feedback-api/')) {
      p = p.slice('/feedback-api/'.length);
      if (q.method !== 'GET') {
        let b = ''; q.on('data', c => b += c); q.on('end', () => {
          const j = b ? JSON.parse(b) : {};
          if (p === 'decision') {
            const s = store[j.set] = store[j.set] || {}, a = s[j.id] = s[j.id] || {};
            for (const k of ['choice', 'label', 'note', 'question', 'pieces', 'knobs']) if (k in j) { if (j[k] === null) delete a[k]; else a[k] = j[k]; }
            a.at = new Date().toISOString();
            return js(200, { ok: true, answer: a });
          }
          if (/^lab\/config\//.test(p)) { rep.puts.push({ path: p, note: j.note, json: j.json }); return js(200, { version: rep.puts.length, changed: true }); }
          js(404, {});
        });
        return;
      }
      if (p.startsWith('decisions/')) return js(200, store[p.slice(10)] || {});
      if (p === 'lab/me') return js(200, { user: 'proof', role: 'admin' });
      if (p === 'lab/catalogue') { r.writeHead(200, { 'Content-Type': 'application/json' }); return r.end(cat); }
      if (p === 'lab/config') return js(200, { configs: [] });
      return js(404, {});
    }
    const f = path.join(site, p === '/' ? 'index.html' : p);
    fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
  });
}

(async () => {
  let srv = null, base = target;
  if (!live) { srv = stub(target); await new Promise(ok => srv.listen(0, ok)); base = `http://127.0.0.1:${srv.address().port}/`; }
  if (!base.endsWith('/')) base += '/';
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox', '--autoplay-policy=no-user-gesture-required'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 900 });
  if (live && process.env.LOGIN) {                     // through the real Oros login page
    const [u, pw] = process.env.LOGIN.split(/:(.*)/s);
    await page.goto(base + 'lab.html', { waitUntil: 'load' });
    if (/login\.html/.test(page.url())) {
      await page.type('#u', u); await page.type('#p', pw);
      await Promise.all([page.waitForNavigation({ timeout: 30000 }).catch(() => null), page.click('#go')]);
      await new Promise(r => setTimeout(r, 1500));
    }
    rep.login = page.url(); console.log('after login:', page.url());
  }
  if (live) {                                          // never a write to the live service
    await page.setRequestInterception(true);
    page.on('request', r => {
      if (r.method() === 'GET' || !/feedback-api\//.test(r.url())) return r.continue();
      if (/feedback-api\/decision$/.test(r.url())) {     // answered here, as the service would (the page's state moves on)
        rep.answered.push(r.method() + ' ' + r.url() + ' ' + (r.postData() || '').slice(0, 200));
        return r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }) });
      }
      rep.blocked.push(r.method() + ' ' + r.url()); r.abort();
    });
  }
  let errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 300)));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errors.push('console: ' + m.text().slice(0, 200)); });
  const STUB_ONLY = live ? null : /feedback-api\/(list|reviews)/;            // (the stub has no feedback notes)
  page.on('response', r => { if (r.status() >= 400 && !(STUB_ONLY && STUB_ONLY.test(r.url())) && !/favicon\.ico|review\/\w+_(anims|workshop|arb)\.json|lab\/config\/|shell-[^/]*\.json|pack-[^/]*\.json|decisions\//.test(r.url())) errors.push('HTTP ' + r.status() + ' ' + r.url()); });
  const settle = ms => new Promise(r => setTimeout(r, ms));
  const visit = async (w, q, ready, shot, extra) => {
    errors = [];
    await page.setViewport({ width: w, height: w > 600 ? 900 : 800 });
    await page.goto(base + q, { waitUntil: 'load', timeout: 120000 });
    let ok = true;
    try { await page.waitForFunction(ready, { timeout: 90000, polling: 200 }); } catch (e) { ok = false; }
    await settle(1200);
    const info = await page.evaluate(() => ({ title: document.title, url: location.href.replace(location.origin, ''), scrollW: document.documentElement.scrollWidth, vw: innerWidth }));
    if (extra) info.extra = await page.evaluate(extra);
    const f = path.join(out, shot + '.png');
    await page.screenshot({ path: f, fullPage: false });
    const r = Object.assign({ w, q, ready: ok, errors: errors.slice(), shot: f }, info);
    rep.pages.push(r);
    check(`${w} ${q}: ready, no error, no sideways scroll`, ok && !errors.length && info.scrollW <= info.vw, { title: info.title, errors, scroll: info.scrollW + '/' + info.vw, extra: info.extra });
    return r;
  };
  const TIMING_READY = `window.arbReady && window.arbTiming && document.querySelectorAll('#arb .timing .knobs').length === window.arbTiming.N`;
  for (const w of [1280, 400]) {
    await visit(w, 'lab.html', 'window.fighterLabReady && window.fighterLabReady.cast > 0', `cast_${w}`, () => document.querySelectorAll('.ccard').length);
    await visit(w, 'index.html', 'window.fighterLabReady && window.fighterLabReady.cast > 0', `index_${w}`, () => ({ cards: document.querySelectorAll('.ccard').length, game: !!document.querySelector('.top a[href="game.html"]'), howto: !!document.querySelector('.top a[href="howto.html"]') }));
    await visit(w, 'lab.html?f=robert&tab=info', 'window.fighterLabReady', `robert_info_${w}`, () => [...document.querySelectorAll('.tabs a')].map(a => a.textContent));
    await visit(w, 'lab.html?f=robert&tab=dictionary', `document.querySelectorAll('#dict .card').length > 20`, `robert_dictionary_${w}`, () => document.querySelectorAll('#dict .card').length);
    await visit(w, 'lab.html?f=robert&tab=workshop', 'window.workshopReady', `robert_workshop_${w}`);
    await visit(w, 'lab.html?f=robert&tab=assembly', TIMING_READY, `robert_assembly_${w}`, () => ({ timing: window.arbTiming, rows: [...document.querySelectorAll('#arb .timing .knobs')].map(k => [...k.querySelectorAll('.krow')].map(r => r.dataset.knob + '=' + r.querySelector('input[type=number]').value).join(' ')) }));
    const tbox = await page.$('#arb .timing');
    if (tbox) { await tbox.scrollIntoView(); await settle(300); await page.screenshot({ path: path.join(out, `robert_timing_${w}.png`) }); }
    await visit(w, 'lab.html?f=robert&tab=review', `document.querySelectorAll('#rev .card').length > 3`, `robert_review_${w}`, () => ({ cards: document.querySelectorAll('#rev .card').length, nav: !!document.querySelector('#rev nav.who') && getComputedStyle(document.querySelector('#rev nav.who')).display }));
    await visit(w, 'lab.html?f=haohmaru&tab=dictionary', `document.querySelector('#dict .note')`, `haohmaru_dictionary_${w}`, () => document.querySelector('#dict .note').textContent);
    await visit(w, 'lab.html?f=robert&tab=assembly&embed=1', TIMING_READY, `robert_embed_${w}`, () => ({ chrome: getComputedStyle(document.querySelector('.top')).display, tabs: getComputedStyle(document.querySelector('.tabs')).display }));
    await visit(w, 'game.html', 'window.gameToolsReady', `game_${w}`, () => location.hash);
    for (const t of ['stages', 'enemies', 'chars', 'select', 'feedback', 'quirks', 'expose', 'decide', 'impacts', 'sounds']) {
      const col = { stages: 'stagecol', enemies: 'enemycol', chars: 'charcol', select: 'selcol', feedback: 'fbcol', quirks: 'quirkcol', expose: 'exposecol', decide: 'decidecol', impacts: 'impactcol', sounds: 'soundcol' }[t];
      errors = [];
      await page.evaluate(t => window.labTab(t), t);
      let filled = true;
      try { await page.waitForFunction(c => { const e = document.getElementById(c); return e && !e.hidden && e.textContent.trim().length > 40; }, { timeout: 30000, polling: 200 }, col); } catch (e) { filled = false; }
      await settle(800);
      const info = await page.evaluate(c => ({ hash: location.hash, on: (document.querySelector('nav.tabs button.on') || {}).textContent, text: document.getElementById(c).textContent.trim().slice(0, 80), scrollW: document.documentElement.scrollWidth, vw: innerWidth,
        game: getComputedStyle(document.getElementById('gamecol')).display !== 'none' && !document.getElementById('gamecol').hidden }), col);
      await page.screenshot({ path: path.join(out, `game_${t}_${w}.png`) });
      check(`${w} game.html tab ${t}: shown, filled, hash #${t}`, filled && info.hash === '#' + t && !errors.length && info.scrollW <= info.vw + (t === 'select' || t === 'stages' || t === 'enemies' || t === 'chars' ? 400 : 0), Object.assign(info, { errors }));
    }
  }
  // ---- every old URL ----
  const REDIR = [['anims.html?f=robert', /lab\.html\?f=robert&tab=dictionary$/], ['review.html?f=robert', /lab\.html\?f=robert&tab=review$/],
    ['review.html?f=kim&q=kim-followups', /lab\.html\?f=kim&q=kim-followups&tab=review$/], ['review.html#f=krauser', /lab\.html\?f=krauser&tab=review$/],
    ['review.html', /lab\.html\?tab=review&f=\w+$/], ['arbitrage.html?f=robert', /lab\.html\?f=robert&tab=assembly$/],
    ['workshop.html?f=robert#S-001', /lab\.html\?f=robert&tab=workshop#S-001$/], ['decide.html', /game\.html#decide$/],
    ['impacts.html', /game\.html#impacts$/], ['sounds.html?f=kim', /game\.html\?f=kim#sounds$/], ['index.html#decide', /game\.html#decide$/],
    ['index.html#fb=20261010-000000-abcd', /game\.html#fb=20261010-000000-abcd$/], ['index.html#expose', /game\.html#expose$/], ['', /\/$|index\.html$/]];
  for (const [from, want] of REDIR) {
    await page.goto(base + from, { waitUntil: 'load' });
    await settle(1500);
    const at = page.url().replace(base, '/');
    rep.redirects.push({ from, at });
    check(`redirect ${from || '(the site root)'} -> ${at}`, want.test(page.url()), at);
  }
  // ---- the chain timing in the game: Robert, "Try this sheet in game" ----
  errors = [];
  await page.setViewport({ width: 1280, height: 900 });
  await page.goto(base + 'lab.html?f=robert&tab=assembly', { waitUntil: 'load' });
  await page.waitForFunction(TIMING_READY, { timeout: 90000, polling: 200 });
  const play = async label => {
    const r = await page.evaluate(async () => {
      await window.TryIt.sheet('robert', window.arbSheet());
      const T = window.tryit, L = T.lab, gp = T.gp;
      if (!L) return { error: document.querySelector('#tryit .tnow').textContent };
      if (!gp.paused) gp.togglePause();
      L.request(2); gp.stepFrames(4);                  // positions reset, the dummy close
      const from = L.nev();
      for (let i = 0; i < 240; i++) { gp.override = i % 2 ? '' : 'a'; gp.stepFrames(1); }
      gp.override = null; gp.stepFrames(60);
      const ev = L.eventsSince(from).events, links = [];
      for (const e of ev) {
        if (e.kind === 'START') links.push({ node: e.node, start: e.frame, hits: [] });
        else if (e.kind === 'HIT' && links.length) links[links.length - 1].hits.push(e.frame);
      }
      return { mode: T.state.man.mode, now: document.querySelector('#tryit .tnow[aria-live]').textContent, err: document.querySelector('#tryit .terr').textContent,
        links: links.slice(0, 6).map(l => ({ start: l.start, contact: l.hits.length ? l.hits[0] - l.start : null, hits: l.hits.length })) };
    });
    r.label = label;
    if (r.links) {
      const t0 = r.links.length ? r.links[0].start : 0;
      r.rel = r.links.map(l => [l.start - t0, l.contact, l.hits]);       // (frames from the chain's first press)
      r.gap12 = r.links.length > 1 ? r.links[1].start - r.links[0].start : null;
      r.span = r.links.length ? r.links[r.links.length - 1].start - r.links[0].start : null;
    }
    console.log('PLAY', JSON.stringify(r));
    return r;
  };
  const setKnob = (panel, knob, v) => page.evaluate((panel, knob, v) => {
    const row = document.querySelectorAll('#arb .timing .knobs')[panel].querySelector(`.krow[data-knob="${knob}"]`), num = row.querySelector('input[type=number]');
    num.value = String(v); num.dispatchEvent(new Event('change'));
    return { over: row.classList.contains('over'), chg: row.querySelector('.kchg').textContent, back: !row.querySelector('.kback').hidden };
  }, panel, knob, v);
  const base0 = await play('the game\'s timing');
  const T0 = await page.evaluate(() => window.arbTiming);
  const s0 = T0.defaults.retime[T0.moves[0]][0], hs0 = T0.defaults.hitstop[0];
  const m1 = await setKnob(0, 's0', s0 * 2), m2 = await setKnob(0, 'hitstop', hs0 + 12);
  check('the knobs mark the override (bold row, "changed from", Back to default)', m1.over && m2.over && m1.back && m2.back && /changed from/.test(m1.chg), { m1, m2 });
  await settle(2500);                                  // (the 0.5 s save, the 1.5 s auto-send)
  const sheet1 = await page.evaluate(() => window.arbSheet());
  check('the sheet carries the timing', sheet1.timing && sheet1.timing.hitstop && sheet1.timing.hitstop.a1 === hs0 + 12 && sheet1.timing.retime[T0.moves[0]][0] === s0 * 2, sheet1.timing);
  const slow = await play(`press 1: startup ${s0} -> ${s0 * 2}, hit-stop ${hs0} -> ${hs0 + 12}`);
  // back to default (the rows' own buttons)
  await page.evaluate(() => { for (const b of document.querySelectorAll('#arb .timing .knobs')[0].querySelectorAll('.kback')) if (!b.hidden) b.click(); });
  await settle(2500);
  const back = await play('back to default');
  const sheet2 = await page.evaluate(() => window.arbSheet());
  rep.timing = { moves: T0.moves, defaults: T0.defaults, base: base0, slow, back, sheet1: sheet1.timing, sheet2: sheet2.timing };
  const c0 = base0.links && base0.links[0], c1 = slow.links && slow.links[0];
  check('the game plays the slower startup: press 1 connects later by the added frames', c0 && c1 && c0.contact !== null && c1.contact === c0.contact + s0, { before: c0, after: c1 });
  check('the chain is slower with the timing (press 1 -> press 2 later by the startup + the hit-stop added)', base0.gap12 !== null && slow.gap12 === base0.gap12 + s0 + 12, { before: base0.gap12, after: slow.gap12 });
  check('back to default = the game\'s timing again (same frames from the first press)', JSON.stringify(back.rel) === JSON.stringify(base0.rel) && !sheet2.timing, { back: back.rel, base: base0.rel });
  check('the chain played whole each time (every press hit)', [base0, slow, back].every(r => r.links && r.links.length >= T0.N && r.links.slice(0, T0.N).every(l => l.hits)), [base0, slow, back].map(r => r.rel));
  if (!live) check('the auto-send put the timing in the live config (stub)', rep.puts.some(p => p.json && p.json.lab_try && p.json.lab_try.chain && p.json.lab_try.chain.timing), rep.puts.map(p => p.note));
  else check('the live service was never written (decisions answered here, other writes aborted)', rep.blocked.every(b => !/^GET/.test(b)), { blocked: rep.blocked.length, answered: rep.answered.length });
  rep.errors = errors;
  await (await page.$('#tryit')).screenshot({ path: path.join(out, 'try_robert_timing.png') }).catch(() => {});
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rep, null, 1));
  await browser.close();
  if (srv) srv.close();
  console.log(bad ? `${bad} problem(s)` : 'all good');
})();
