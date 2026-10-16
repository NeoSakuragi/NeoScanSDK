#!/usr/bin/env node
/* Live wall proof (wall.js) in headless Chrome against a LOCAL Lab fed by wall_feed.py with 3 sessions, the 2nd and
 * the 3rd ending after 50 s (wall_feed.py --n 3 --end-after 1:50 --end-after 2:50 A120 B300 C300):
 * tiles join, drift check identical, the tapped tile alone sends sound, double-tap = the single view (its info line
 * from the core) and back, a pinned ended session stays and an unpinned one leaves, the phone width (<= 2 tiles in one
 * column), the list's LIVE NOW / past sections with the character columns. Screenshots into OUT.
 *   node wall_proof.js URL OUT_DIR */
const fs = require('fs'), path = require('path');
const puppeteer = require('/home/bruno/CLProjects/NeoGeo/node_modules/puppeteer-core');
const [url, out] = process.argv.slice(2);
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ok = (c, what) => { console.log((c ? 'PASS ' : 'FAIL ') + what); if (!c) process.exitCode = 1; };
(async () => {
  fs.mkdirSync(out, { recursive: true });
  const b = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: 'new', args: ['--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  p.on('pageerror', e => console.log('pageerror:', e.message));
  await p.setViewport({ width: 1400, height: 1100 });
  await p.goto(url + '#wall', { waitUntil: 'load' });
  const tiles = () => p.evaluate(() => (window.labWall ? window.labWall.tiles() : []));
  const until = async (f, s, what) => { for (let i = 0; i < s * 2; i++) { const v = await f(); if (v) return v; await sleep(500); } ok(false, what + ' (timed out)'); return null; };
  await until(async () => (await tiles()).filter(t => t.checked > 0).length === 3, 60, 'three tiles running');
  let T = await tiles();
  ok(T.length === 3 && T.every(t => !t.mismatches.length && !t.gaps.length), `3 tiles, drift check identical: ${T.map(t => t.id.slice(0, 8) + ' ' + t.checked).join(', ')}`);
  const texts = await p.evaluate(() => [...document.querySelectorAll('#sesscol .wall .tile')].map(t => t.innerText.replace(/\n/g, ' | ')));
  console.log(texts.join('\n'));
  ok(texts.some(t => /STAGE|demo|title|select|fight/.test(t)), 'tile info lines read from RAM / the HUD');
  await p.screenshot({ path: path.join(out, 'proof_wall3.png') });
  // sound: tap the first tile -> it alone sends audio
  await p.evaluate(() => { window._aud = {}; const els = [...document.querySelectorAll('#sesscol .wall .tile')]; els[0].click(); });
  const heardN = await p.evaluate(() => document.querySelectorAll('#sesscol .wall .tile.heard').length);
  ok(heardN === 1, 'one tile heard after a tap');
  await sleep(3000);
  const au = (await tiles()).map(t => t.audio);
  ok(au[0] > 30 && au.slice(1).every(x => x === 0), `only the tapped tile sends sound (audio frames received per tile: ${au.join(', ')})`);
  // pin the 2nd tile (it ends at 50 s); the 3rd one is left unpinned
  const ids = await p.evaluate(() => { const els = [...document.querySelectorAll('#sesscol .wall .tile')]; els[1].querySelector('.th button').click(); return els.map(e => e.querySelector('.th').innerText); });
  console.log('pinned the 2nd:', ids[1].replace(/\n/g, ' '));
  // double-tap the first tile: the single view
  await p.evaluate(() => { const e = document.querySelector('#sesscol .wall .tile'); e.click(); e.click(); });
  await sleep(6000);
  const single = await p.evaluate(() => ({ grid: document.querySelector('#sesscol .wall .grid').hidden, box: !!document.querySelector('#sesscol .box canvas'),
    lines: [...document.querySelectorAll('#sesscol .box .mono')].map(e => e.textContent) }));
  console.log(single.lines.join('\n'));
  ok(single.grid && single.box, 'double-tap: the single view, the grid hidden');
  ok(single.lines.some(l => /STAGE|demo|title|select|fight|LEVEL/.test(l)), 'single view: the info line from the core');
  await p.screenshot({ path: path.join(out, 'proof_single.png') });
  T = await tiles(); ok(T.every(t => t.paused), 'tiles paused behind the single view');
  await p.evaluate(() => [...document.querySelectorAll('#sesscol .wall .wbar button')].find(x => /Back/.test(x.textContent)).click());
  await sleep(4000);
  T = await tiles(); ok(!(await p.evaluate(() => document.querySelector('#sesscol .wall .grid').hidden)) && T.every(t => !t.paused), 'back to the wall, tiles running');
  // the 2 sessions end at 50 s: the unpinned one leaves ~15 s (live) + 5 s later, the pinned one stays
  const end = await until(async () => (await tiles()).length === 2, 120, 'the unpinned ended session leaves');
  T = await tiles();
  ok(end && T.some(t => t.live === false), `the pinned ended session stays (ENDED): ${T.map(t => t.id.slice(0, 8) + (t.live ? ' live' : ' ended')).join(', ')}`);
  await p.screenshot({ path: path.join(out, 'proof_pinned.png') });
  await p.evaluate(() => { const e = [...document.querySelectorAll('#sesscol .wall .tile')].find(t => /ENDED/.test(t.innerText)); e.querySelector('.th button').click(); });
  await until(async () => (await tiles()).length === 1, 20, 'unpinned: it leaves');
  ok((await tiles()).length === 1, 'unpinned ended session left');
  // phone width
  await p.setViewport({ width: 390, height: 844 });
  await sleep(3000);
  const ph = await p.evaluate(() => ({ n: document.querySelectorAll('#sesscol .wall .tile').length, cols: getComputedStyle(document.querySelector('#sesscol .wall .grid')).gridTemplateColumns.split(' ').length,
    over: document.documentElement.scrollWidth - innerWidth }));
  ok(ph.n <= 2 && ph.cols === 1, `phone: ${ph.n} tile(s), ${ph.cols} column, horizontal overflow ${ph.over}px`);
  await p.screenshot({ path: path.join(out, 'proof_phone_wall.png'), fullPage: false });
  // the list: LIVE NOW, then the past sessions, with the character columns
  await p.setViewport({ width: 1400, height: 1100 });
  await p.evaluate(() => window.labWall.close());
  await sleep(8000);
  const list = await p.evaluate(() => [...document.querySelectorAll('#sesscol h3.sect, #sesscol table tr')].map(e => e.innerText.replace(/\t/g, ' | ')));
  console.log(list.slice(0, 12).join('\n'));
  ok(list[0].startsWith('LIVE NOW') && list.some(l => l === 'Past sessions'), 'list: LIVE NOW then Past sessions');
  ok(list.some(l => /TERRY|ROBERT|HAOHMARU|KIM|HANZO|HAGGAR/.test(l)), 'list: a character read');
  await p.screenshot({ path: path.join(out, 'proof_list.png') });
  await p.setViewport({ width: 390, height: 844 });
  await sleep(1500);
  await p.screenshot({ path: path.join(out, 'proof_phone_list.png') });
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
