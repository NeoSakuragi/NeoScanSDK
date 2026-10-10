// LIVE CLIPS proof (liveclips.js): headless Chrome on the Assembly, against a local site + stub service or LIVE on canneji
// (LOGIN=user:password or LOGIN_FILE: an admin through the real Oros login). Writes are blocked: a decision POST is answered
// by the proof (the page's memory changes, the server's answers do not), every other write (the auto-send's PUT, the
// ship) is aborted. Checks (docs/character_lab.md "Live clips"):
//   1. Robert: S-012 (6426C Haoh Shoukou Ken) picked on forward + C, its speed knob 7 -> 12: the clip is simulated again,
//      the projectile's measured speed and the strip's numbers follow;
//   2. Hanzo (SS2): press 3 ($15C) at the far gap and the near gap: hits / whiff, boxes drawn;
//   3. a chain timing knob (press 1's hit-stop) changes the whole-chain clip's total frames;
//   4. 1280 and 400 px screens; the simulation's time per clip (desktop, and a phone emulation: 400 px, mobile, CPU / 4).
//   node liveclips_proof.js SITE_DIR|URL OUT [--stub-dl DIR] [--catalogue FILE] [--decisions DIR] [--core DIR] [--serve PORT: the stub only]
const fs = require('fs'), path = require('path'), http = require('http');
const puppeteer = require('/home/bruno/CLProjects/NeoGeo/node_modules/puppeteer-core');
const args = process.argv.slice(2), target = args[0], out = args[1];
const opt = k => { const i = args.indexOf(k); return i >= 0 ? args[i + 1] : null; };
fs.mkdirSync(out, { recursive: true });
const live = /^https?:/.test(target);
const rep = { target, blocked: [], answered: [], checks: [], timings: {} };
let bad = 0;
const check = (name, ok, detail) => { if (!ok) bad++; console.log((ok ? 'PASS ' : 'FAIL ') + name + (detail !== undefined ? '  ' + JSON.stringify(detail).slice(0, 900) : '')); rep.checks.push({ name, ok: !!ok, detail }); };
const settle = ms => new Promise(r => setTimeout(r, ms));
const HERE = __dirname;

function stub(site) {
  const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.wasm': 'application/wasm', '.zip': 'application/zip' };
  const cat = fs.readFileSync(opt('--catalogue')), dl = opt('--stub-dl'), dec = opt('--decisions'), core = opt('--core');
  const OVER = ['lab.html', 'fighterlab.js', 'arbitrage.js', 'tryit.js', 'lab.js', 'knobui.js', 'anims_core.js', 'gameplay.js', 'liveclips.js', 'liveclips_worker.js', 'liveclips_core.js'];
  return http.createServer((q, r) => {
    const u = new URL(q.url, 'http://x'); let p = decodeURIComponent(u.pathname);
    const js = (code, o) => { r.writeHead(code, { 'Content-Type': 'application/json' }); r.end(JSON.stringify(o)); };
    if (p.startsWith('/feedback-api/')) {
      p = p.slice('/feedback-api/'.length);
      if (q.method !== 'GET') { q.resume(); return js(403, { error: 'stub: no writes' }); }
      if (p.startsWith('decisions/')) { const f = path.join(dec, p.slice(10) + '.json'); return js(200, fs.existsSync(f) ? JSON.parse(fs.readFileSync(f)) : {}); }
      if (p === 'lab/me') return js(200, { user: 'proof', role: 'admin' });
      if (p === 'lab/catalogue') { r.writeHead(200, { 'Content-Type': 'application/json' }); return r.end(cat); }
      if (p === 'lab/config') return js(200, { configs: [] });
      if (p.startsWith('lab/ship')) return js(200, { requests: [] });
      return js(404, {});
    }
    let f;
    if (p.startsWith('/brawler/lab/dl/')) f = path.join(dl, p);
    else {
      const b = p === '/' ? 'lab.html' : p.slice(1);
      f = OVER.includes(b) ? path.join(HERE, b) : (b === 'core.js' || b === 'core.wasm') && core ? path.join(core, b) : path.join(site, b);
    }
    fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
  });
}

if (args.includes('--serve')) {                            // the stub alone (a device's browser: adb reverse tcp:PORT tcp:PORT)
  const port = +opt('--serve'); stub(target).listen(port, () => console.log('stub on http://127.0.0.1:' + port + '/lab.html?f=robert&tab=assembly'));
} else (async () => {
  let srv = null, base = target;
  if (!live) { srv = stub(target); await new Promise(ok => srv.listen(0, ok)); base = `http://127.0.0.1:${srv.address().port}/`; }
  if (!base.endsWith('/')) base += '/';
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 1000 });
  const errs = []; page.on('pageerror', e => errs.push(e.message));
  page.on('console', m => { if (m.type() === 'error' && !/Failed to load resource/.test(m.text())) errs.push('console: ' + m.text()); });
  if (live) {
    const [u, pw] = (process.env.LOGIN || fs.readFileSync(process.env.LOGIN_FILE, 'utf8').trim()).split(/:(.*)/s);
    await page.goto(base + 'lab.html', { waitUntil: 'load' });
    if (/login\.html/.test(page.url())) {
      await page.type('#u', u); await page.type('#p', pw);
      await Promise.all([page.waitForNavigation({ timeout: 30000 }).catch(() => null), page.click('#go')]);
      await settle(1500);
    }
  }
  // writes: a decision is answered here (the page's memory only), everything else non-GET to the service is aborted
  const mem = {};
  await page.setRequestInterception(true);
  page.on('request', r => {
    const u = r.url();
    if (r.method() !== 'GET' && /feedback-api\/decision$/.test(u)) {
      const j = JSON.parse(r.postData() || '{}'), a = mem[j.set + '/' + j.id] = Object.assign(mem[j.set + '/' + j.id] || {}, j, { at: new Date().toISOString() });
      rep.answered.push(j.set + '/' + j.id);
      return r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, answer: a }) });
    }
    if (r.method() !== 'GET' && /feedback-api\//.test(u)) { rep.blocked.push(r.method() + ' ' + u.replace(/^.*feedback-api\//, '')); return r.abort(); }
    r.continue();
  });
  const cdp = await page.target().createCDPSession();
  const open = async (F, width, mobile) => {
    await page.setViewport({ width, height: 1000, isMobile: !!mobile, hasTouch: !!mobile });
    await page.goto(base + `lab.html?f=${F}&tab=assembly`, { waitUntil: 'load' });
    await page.waitForFunction(() => window.arbReady && 'arbLive' in window, { timeout: 120000, polling: 300 });
    return page.evaluate(() => window.arbLive);
  };
  // the clip `key`'s result once its request is simulated (scrolled into view first); pred: wait for a newer one
  const clipOf = (key, prevMs) => page.evaluate(async (key, prevMs) => {
    const C = window.liveclips.clips, st0 = C.get(key);
    if (!st0) return { error: 'no clip ' + key };
    st0.el.scrollIntoView({ block: 'center' });
    for (let i = 0; i < 600; i++) {
      const st = C.get(key);
      if (st.res && st.el.dataset.busy !== '1' && !st.dirty && (prevMs === null || st.res !== window.__prev)) {
        window.__prev = st.res;
        const r = st.res;
        return { n: r.n, w: r.w, h: r.h, ms: r.ms, wall: r.wall, fd: r.fd, gapMode: st.gapMode, req: st.req && st.req.text, state: st.stateEl.textContent,
                 boxes: r.frames.reduce((a, f) => a + f.atk.length + f.hurt.length, 0), err: r.error };
      }
      if (st.stateEl.className.includes('bad')) return { error: st.stateEl.textContent };
      await new Promise(r => setTimeout(r, 100));
    }
    return { error: 'timeout', state: C.get(key).stateEl.textContent };
  }, key, prevMs === undefined ? null : prevMs);
  const shot = async (sel, name) => { const e = await page.$(sel); if (e) await e.screenshot({ path: path.join(out, name) }).catch(() => {}); };

  // ---- 1. Robert: S-012 on forward + C, speed 7 -> 12 ----
  const lr = await open('robert', 1280);
  check('Robert: the Assembly has live clips', lr === true);
  await page.evaluate(() => { const b = [...document.querySelectorAll('.lclip-boxes')][0]; if (b && b.getAttribute('aria-pressed') !== 'true') b.click(); });
  await page.screenshot({ path: path.join(out, 'robert_top_1280.png') });
  const picked = await page.evaluate(async () => {
    const box = document.querySelector('#slot-sp_fc');
    [...box.querySelectorAll('button')].find(b => b.textContent === 'Pick animation').click();
    await new Promise(r => setTimeout(r, 400));
    const use = [...document.querySelectorAll('.pmodal button.use')].find(b => b.textContent === 'Use S-012');
    if (!use) return 'no "Use S-012"';
    use.click();
    for (let i = 0; i < 50 && !document.querySelector('#slot-sp_fc .knobs'); i++) await new Promise(r => setTimeout(r, 100));
    return document.querySelector('#slot-sp_fc .knobs') ? 'ok' : 'no knob panel';
  });
  check('Robert: S-012 picked on forward + C (the decision answered by the proof)', picked === 'ok', picked);
  const a7 = await clipOf('sp_fc');
  rep.robert7 = a7;
  console.log('speed 7:', JSON.stringify(a7).slice(0, 700));
  await shot('#slot-sp_fc', 'robert_s012_speed7.png');
  await page.evaluate(() => { const i = document.querySelector('#slot-sp_fc .krow[data-knob="speed"] input[type=number]'); i.value = '12'; i.dispatchEvent(new Event('change')); });
  const a12 = await clipOf('sp_fc', a7.ms);
  rep.robert12 = a12;
  console.log('speed 12:', JSON.stringify(a12).slice(0, 700));
  await shot('#slot-sp_fc', 'robert_s012_speed12.png');
  check('Robert S-012 speed 7: the projectile flies 7 px a frame', a7.fd && a7.fd.proj && a7.fd.proj.speed === 7, a7.fd && a7.fd.proj);
  check('Robert S-012 speed 12: the projectile flies 12 px a frame', a12.fd && a12.fd.proj && a12.fd.proj.speed === 12, a12.fd && a12.fd.proj);
  check('Robert S-012: the strip changed with the knob (active / hit frame / total)', a7.fd && a12.fd && (a7.fd.active !== a12.fd.active || String(a7.fd.hitFrames) !== String(a12.fd.hitFrames)),
    { k7: a7.fd && [a7.fd.startup, a7.fd.active, a7.fd.hitFrames, a7.fd.total], k12: a12.fd && [a12.fd.startup, a12.fd.active, a12.fd.hitFrames, a12.fd.total] });
  const strip = await page.$eval('#slot-sp_fc .lfd', e => e.textContent).catch(() => '');
  check('Robert S-012: the strip text shows 12 px a frame', /Projectile: 12 px a frame/.test(strip), strip);
  // chain timing: press 1's hit-stop -> the whole chain's total frames
  const c0 = await clipOf('chain');
  rep.chain0 = c0;
  const hs = await page.evaluate(() => {
    const d = document.querySelector('#arb .timing details.tpress[data-press="a1"]'); d.open = true;
    const i = d.querySelector('.krow[data-knob="hitstop"] input[type=number]'), v0 = +i.value;
    i.value = String(v0 + 20); i.dispatchEvent(new Event('change'));
    return { from: v0, to: v0 + 20 };
  });
  const c1 = await clipOf('chain', c0.ms);
  rep.chain1 = c1; rep.hitstop = hs;
  console.log('chain', JSON.stringify(hs), c0.fd && [c0.fd.total, c0.n, c0.fd.hits], '->', c1.fd && [c1.fd.total, c1.n, c1.fd.hits]);
  check('Robert: press 1\'s hit-stop +20 changes the whole-chain clip\'s total frames', c0.fd && c1.fd && c1.fd.total !== c0.fd.total, { before: c0.fd && c0.fd.total, after: c1.fd && c1.fd.total, hits: [c0.fd && c0.fd.hits, c1.fd && c1.fd.hits] });
  await shot('#slot-chain', 'robert_whole_chain.png');
  rep.timings.desktop_robert = await page.evaluate(() => ({ boot: window.liveclips.stats.boot, list: window.liveclips.stats.list }));

  // ---- 2. Hanzo: press 3 ($15C) far / near ----
  const lh = await open('hanzo_ss2', 1280);
  check('Hanzo: the Assembly has live clips', lh === true);
  await page.evaluate(() => { const b = document.querySelector('.lclip-boxes'); if (b && b.getAttribute('aria-pressed') !== 'true') b.click(); });
  // press 3 = $15C (his sheet's pick when he made the note; picked here if the sheet has moved on: answered by the proof)
  rep.hanzo_a3 = await page.evaluate(async () => {
    const box = document.querySelector('#slot-a3');
    if (/\$15C/.test(box.querySelector('.chip') ? box.querySelector('.chip').textContent : '')) return 'already $15C';
    [...box.querySelectorAll('button')].find(b => b.textContent === 'Pick animation').click();
    await new Promise(r => setTimeout(r, 400));
    document.querySelector('.pmodal input[type=search]').value = '15C'; document.querySelector('.pmodal input[type=search]').dispatchEvent(new Event('input'));
    const use = [...document.querySelectorAll('.pmodal button.use')].find(b => b.textContent === 'Use $15C');
    if (!use) return 'no "Use $15C"';
    use.click();
    for (let i = 0; i < 50 && !/\$15C/.test((document.querySelector('#slot-a3 .chip') || {}).textContent || ''); i++) await new Promise(r => setTimeout(r, 100));
    return 'picked $15C';
  });
  console.log('hanzo a3:', rep.hanzo_a3);
  const gapTo = mode => page.evaluate(async mode => {
    const st = window.liveclips.clips.get('a3'), b = st.el.querySelector('.lchead button');
    for (let i = 0; i < 3 && st.gapMode !== mode; i++) b.click();
    return st.gapMode;
  }, mode);
  await gapTo('near'); const hn = await clipOf('a3', -1);
  await shot('#slot-a3', 'hanzo_15C_near.png');
  await gapTo('far'); const hf = await clipOf('a3', -1);
  await shot('#slot-a3', 'hanzo_15C_far.png');
  rep.hanzo = { near: hn, far: hf };
  console.log('hanzo near', JSON.stringify(hn && hn.fd), '\nfar', JSON.stringify(hf && hf.fd));
  check('Hanzo $15C at the far gap (150 px): it whiffs', hf.fd && hf.fd.hits === 0, hf.fd && { hits: hf.fd.hits, gap: hf.fd.gap, reach: hf.fd.reach });
  check('Hanzo $15C at the near gap (44 px): it hits', hn.fd && hn.fd.hits > 0, hn.fd && { hits: hn.fd.hits, gap: hn.fd.gap, reach: hn.fd.reach });
  check('Hanzo $15C: boxes recorded on the clip', hn.boxes > 0 && hf.boxes > 0, [hn.boxes, hf.boxes]);
  const hc = await clipOf('chain'); rep.hanzo_chain = hc;
  await shot('#slot-chain', 'hanzo_whole_chain.png');
  await page.screenshot({ path: path.join(out, 'hanzo_1280.png') });
  rep.timings.desktop_hanzo = await page.evaluate(() => window.liveclips.stats.list);

  // ---- 3. 400 px, phone emulation (mobile, CPU / 4) ----
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 4 });
  const lp = await open('robert', 400, true);
  check('400 px (mobile, CPU / 4): live clips', lp === true);
  const p1 = await clipOf('a1'), p2 = await clipOf('sp_c');
  await page.evaluate(() => document.querySelector('#slot-a1').scrollIntoView());
  await page.screenshot({ path: path.join(out, 'robert_400.png') });
  await shot('#slot-sp_c', 'robert_sp_c_400.png');
  rep.timings.phone = await page.evaluate(() => ({ boot: window.liveclips.stats.boot, list: window.liveclips.stats.list, phone: window.liveclips.LC.phone }));
  console.log('phone', JSON.stringify(rep.timings.phone));
  check('400 px: clips simulated', !p1.error && !p2.error, [p1.error, p2.error]);
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 });
  const embed = await (async () => {
    await page.goto(base + 'lab.html?f=robert&tab=assembly&embed=1', { waitUntil: 'load' });
    await page.waitForFunction(() => window.arbReady && 'arbLive' in window, { timeout: 120000, polling: 300 });
    const r = await clipOf('a2');
    await page.screenshot({ path: path.join(out, 'robert_embed_400.png') });
    return r;
  })();
  check('the embed (the Player\'s WebView page): a live clip', !embed.error && embed.n > 0, embed.error);
  check('no write reached the server', live ? rep.blocked.every(b => !/^GET/.test(b)) : true, rep.blocked);
  check('no page error', !errs.length, errs.slice(0, 5));
  rep.bad = bad;
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rep, null, 1));
  await browser.close(); if (srv) srv.close();
  process.exit(bad ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
