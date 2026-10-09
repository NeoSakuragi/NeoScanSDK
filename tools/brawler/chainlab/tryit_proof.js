// "Try in game" proof in headless Chrome (puppeteer-core; NODE_PATH=/home/bruno/CLProjects/NeoGeo/node_modules): the
// pages as Bruno uses them, served from a Lab site (make_site.py / tryit_site.py output, its rom/ with the Lab build).
//   node tryit_proof.js BASE_URL GAME_DIR OUT_DIR      (BASE_URL: http://127.0.0.1:8765/; GAME_DIR: examples/brawler)
// 1. workshop.html?f=robert: the "Try in game" button of animation $A9 (Haoh Shoukou Ken's) -> the fighter plays the LAB
//    special's $A9 (lab.cur = $A9) and its frames are $A9's ROM frames (build_lab_robert/bm_frames.json vs the
//    dictionary), screenshot; 2. anims.html?f=robert: $51, $5B, $D4 added to the queue from their larger views, "Try the
//    queue in game" -> played in that order; 3. arbitrage.html?f=robert with his answer forward + C = S-004 (the decisions
//    store answered by the proof) -> "Try this sheet in game", forward + C plays S-004 (623D); 4. the player's speed
//    (frames per second delivered by the page's loop, and the core's cost per frame); 5. the Chain Lab page (index.html,
//    gameplay.js shared with it) still plays. Writes OUT_DIR/report.json + screenshots.
const fs = require('fs'), path = require('path');
const puppeteer = require('puppeteer-core');
const [base, game, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const sleep = ms => new Promise(r => setTimeout(r, ms));
const bmf = JSON.parse(fs.readFileSync(path.join(game, 'build_lab_robert', 'bm_frames.json')))['robert'];
const rep = {};
(async () => {
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--autoplay-policy=no-user-gesture-required', '--window-size=1500,1000'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1500, height: 1000 });
  const errors = [];
  page.on('pageerror', e => errors.push(String(e).slice(0, 300)));
  page.on('console', m => { if (m.type() === 'error' && !/feedback-api|404|Failed to load resource/.test(m.text())) errors.push('console: ' + m.text().slice(0, 200)); });
  await page.setRequestInterception(true);
  let arb = null;                                      // the decisions store as the proof answers it
  page.on('request', r => {
    const u = r.url();
    if (u.includes('feedback-api/decisions/robert-arb') && arb) return r.respond({ status: 200, contentType: 'application/json', body: JSON.stringify(arb) });
    if (u.includes('feedback-api/')) return r.respond({ status: 200, contentType: 'application/json', body: '{}' });
    r.continue();
  });
  const waitFor = async (expr, ms = 120000) => { await page.waitForFunction(expr, { timeout: ms, polling: 100 }); };
  // sample P1 while the page's own loop runs: cur, frame shown, spec_ix
  // (again: press the panel's "Play again" first: the queue from its start)
  const sample = (ms, again) => page.evaluate((ms, again) => new Promise(ok => {
    if (again) [...document.querySelectorAll('#tryit button')].find(b => b.textContent === 'Play again').click();
    const L = window.tryit.lab, out = [], t0 = performance.now();
    const tick = () => { out.push([L.tryCur(), L.fget(0, 'frame_ovr'), L.fget(0, 'spec_ix'), L.stateName(0)]); if (performance.now() - t0 < ms) requestAnimationFrame(tick); else ok(out); };
    requestAnimationFrame(tick);
  }), ms, again);
  const ready = () => waitFor('window.tryit && window.tryit.ready && window.tryit.lab.tryStatus() === "taken"', 180000);

  // ---- 1. the Workshop: Try $A9 ----
  await page.goto(base + 'workshop.html?f=robert', { waitUntil: 'load' });
  await waitFor('window.workshopReady');
  await waitFor('document.querySelector("#anim-A9 .tryit-btn") && !document.querySelector("#anim-A9 .tryit-btn").hidden', 20000);
  const tLoad = Date.now();
  await page.evaluate(() => { const c = document.getElementById('anim-A9'); c.hidden = false; c.querySelector('.tryit-btn').click(); });
  await ready();
  rep.load_ms = Date.now() - tLoad;
  let s = await sample(2500, true);
  await page.evaluate(() => [...document.querySelectorAll('#tryit button')].find(b => b.textContent === 'Play again').click());
  await sleep(700);
  await page.screenshot({ path: path.join(out, 'try_A9.png') });
  const el = await page.$('#tryit canvas'); if (el) await el.screenshot({ path: path.join(out, 'try_A9_game.png') });
  const a9 = s.filter(r => r[0] === 0xA9);
  const DA = await page.evaluate(async b => (await (await fetch(b + 'review/robert_anims.json')).json()).anims.find(a => a.id === 'A9').steps.map(x => x.fr), base);
  const dict = [...new Set(DA)];                       // (the dictionary's $A9: its steps' ROM frames)
  const shown = [...new Set(a9.map(r => r[1]).filter(v => v !== 0xFFFF))].map(v => +bmf[v].split(':')[1]);
  rep.try_A9 = { anim_in_ram: a9.length ? '$A9' : 'never', samples: a9.length, rom_frames_shown: shown, dictionary_frames: dict,
                 frames_match: shown.length > 0 && shown.every(v => dict.includes(v)) && dict.every(v => shown.includes(v)),
                 status: await page.$eval('#tryit .tstat', e => e.textContent) };

  // ---- 2. the dictionary: a queue $51 > $5B > $D4 from the larger views ----
  await page.goto(base + 'anims.html?f=robert', { waitUntil: 'load' });
  await waitFor('window.dictReady');
  await page.evaluate(() => localStorage.removeItem('tryit-queue-robert'));
  for (const id of ['51', '5B', 'D4']) {
    await page.evaluate(id => { const c = [...document.querySelectorAll('.card')].find(b => b.getAttribute('aria-label') === 'Animation $' + id + ': open the larger view'); c.hidden = false; c.click(); }, id);
    await waitFor(`window.dictOpen === '${id}'`);
    await page.evaluate(() => { const b = [...document.querySelectorAll('.modal button')].find(b => b.textContent.startsWith('+ Add to the queue')); b.click(); });
    await page.evaluate(() => { [...document.querySelectorAll('.modal .mhead button')].find(b => b.textContent === 'Close').click(); });
  }
  rep.queue_ui = await page.evaluate(() => window.dictQueue);
  await waitFor('[...document.querySelectorAll(".tryit-btn")].some(b => b.textContent === "Try the queue in game" && !b.hidden)', 20000);
  await page.evaluate(() => [...document.querySelectorAll('.tryit-btn')].find(b => b.textContent === 'Try the queue in game').click());
  await ready();
  s = await sample(3000, true);
  const order = []; s.forEach(r => { if (r[0] !== 0xFFFF && order[order.length - 1] !== r[0]) order.push(r[0]); });
  rep.queue = { order: order.map(v => '$' + v.toString(16).toUpperCase()), in_order: JSON.stringify(order.slice(0, 3)) === JSON.stringify([0x51, 0x5B, 0xD4]),
                now: await page.$eval('#tryit .tnow[aria-live]', e => e.textContent) };
  await page.screenshot({ path: path.join(out, 'try_queue.png') });

  // ---- 3. the arbitration sheet: forward + C = S-004 ----
  arb = { sp_fc: { choice: 1, pieces: ['S-004'], note: '', label: 'picked' } };
  await page.goto(base + 'arbitrage.html?f=robert', { waitUntil: 'load' });
  await waitFor('window.arbReady');
  rep.sheet_answers = await page.evaluate(() => window.arbSheet());
  await waitFor('[...document.querySelectorAll(".tryit-btn")].some(b => !b.hidden)', 20000);
  await page.evaluate(() => [...document.querySelectorAll('.tryit-btn')].find(b => b.textContent === 'Try this sheet in game').click());
  await ready();
  const sp = await page.evaluate(async () => {
    const T = window.tryit, L = T.lab, gp = T.gp, out = [];
    if (!gp.paused) gp.togglePause();
    L.request(2); gp.stepFrames(20);                    // both on their marks: P1 faces right
    const k = T.state.man.pool.indexOf('623D');
    gp.override = 'Rc'; gp.stepFrames(3); gp.override = '';
    for (let i = 0; i < 80; i++) { gp.stepFrames(1); out.push([L.tryCur(), L.fget(0, 'spec_ix'), L.stateName(0)]); }
    gp.override = null; gp.togglePause();
    return { k, out, now: document.querySelector('#tryit .tnow[aria-live]').textContent };
  });
  rep.sheet = { pool_index_623D: sp.k, played_S004: sp.out.filter(r => r[0] === (0x1000 | sp.k)).length, spec_ix_in_special: [...new Set(sp.out.filter(r => r[2] === 'SPECIAL').map(r => r[1]))], now: sp.now };
  await page.screenshot({ path: path.join(out, 'try_sheet.png') });

  // ---- 4. speed: the page's loop for 5 s ----
  const sp0 = await page.evaluate(() => window.tryit.gp.stats());
  await sleep(5000);
  const sp1 = await page.evaluate(() => window.tryit.gp.stats());
  const fr = sp1.frames - sp0.frames, ms = sp1.ms - sp0.ms;
  rep.speed = { delivered_fps: +(fr / 5).toFixed(1), core_ms_per_frame: +(ms / fr).toFixed(2), core_max_fps: Math.round(1000 / (ms / fr)) };

  // ---- 5. the Chain Lab still plays (gameplay.js shared) ----
  await page.goto(base + 'index.html', { waitUntil: 'load' });
  await waitFor('window.chainlab && window.chainlab.lab', 120000);
  rep.chainlab = await page.evaluate(() => { const c = window.chainlab; const f0 = c.lab.labFrame(); c.play('20:a,20:-'); return { frames: c.lab.labFrame() - f0, status: document.getElementById('status').textContent }; });
  rep.errors = errors;
  fs.writeFileSync(path.join(out, 'report.json'), JSON.stringify(rep, null, 1));
  console.log(JSON.stringify(rep, null, 1));
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
