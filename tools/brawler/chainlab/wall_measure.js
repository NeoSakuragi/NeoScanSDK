#!/usr/bin/env node
/* Live wall proof (wall.js): the Lab page in headless Chrome on a LOCAL Lab (wall_feed.py feeding fake live sessions to
 * a local feedback service), the wall opened; after a warm-up, for SECONDS: the CPU time of every Chrome process
 * (/proc/<pid>/stat utime + stime, the browser's whole tree) and the renderer's memory (RSS / PSS from smaps_rollup),
 * every tile's own report (its worker's busy fraction of a core, frames per second, wasm heap, lag, the drift check).
 * Prints one JSON line; screenshots wall_<n>.png (+ the phone width) into OUT.
 *   node wall_measure.js URL N OUT_DIR [--warm 25] [--seconds 30] [--phone] [--base]   (--base: the page without the wall) */
const fs = require('fs'), path = require('path');
const puppeteer = require('/home/bruno/CLProjects/NeoGeo/node_modules/puppeteer-core');
const a = process.argv.slice(2), opt = (k, d) => { const i = a.indexOf(k); if (i < 0) return d; const v = a[i + 1]; a.splice(i, 2); return v; };
const flag = k => { const i = a.indexOf(k); if (i < 0) return false; a.splice(i, 1); return true; };
const WARM = +opt('--warm', 25), SECS = +opt('--seconds', 30), PHONE = flag('--phone'), BASE = flag('--base');
const [url, N, out] = a;
const sleep = ms => new Promise(r => setTimeout(r, ms));
const HZ = 100;
function tree(root) {                                    // the browser process and all its descendants
  const kids = {}; for (const p of fs.readdirSync('/proc').filter(x => /^\d+$/.test(x))) {
    try { const s = fs.readFileSync(`/proc/${p}/stat`, 'utf8'), pp = +s.slice(s.lastIndexOf(')') + 2).split(' ')[1]; (kids[pp] = kids[pp] || []).push(+p); } catch (e) { /* gone */ }
  }
  const all = [], q = [root]; while (q.length) { const p = q.shift(); all.push(p); q.push(...(kids[p] || [])); } return all;
}
function cpu(pids) { let t = 0; for (const p of pids) { try { const f = fs.readFileSync(`/proc/${p}/stat`, 'utf8').slice(0).split(') ')[1].split(' '); t += +f[11] + +f[12]; } catch (e) { /* gone */ } } return t / HZ; }
function mem(pids) {
  let rss = 0, pss = 0; const per = [];
  for (const p of pids) {
    try {
      const s = fs.readFileSync(`/proc/${p}/smaps_rollup`, 'utf8'), g = k => +((new RegExp('^' + k + ':\\s+(\\d+)', 'm').exec(s) || [0, 0])[1]) / 1024;
      const cmd = fs.readFileSync(`/proc/${p}/cmdline`, 'utf8'), type = (/--type=([a-z-]+)/.exec(cmd) || [0, 'browser'])[1];
      rss += g('Rss'); pss += g('Pss'); per.push({ type, pss: Math.round(g('Pss')) });
    } catch (e) { /* gone */ }
  }
  return { rss: Math.round(rss), pss: Math.round(pss), per };
}
(async () => {
  const b = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: 'new', args: ['--autoplay-policy=no-user-gesture-required'] });
  const p = await b.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message)); p.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
  await p.setViewport(PHONE ? { width: 390, height: 844, deviceScaleFactor: 1 } : { width: 1400, height: 1000 });
  await p.goto(url + (BASE ? '#sessions' : '#wall'), { waitUntil: 'load' });
  await sleep(WARM * 1000);
  const pids = tree(b.process().pid);
  const c0 = cpu(pids), t0 = Date.now();
  await sleep(SECS * 1000);
  const c1 = cpu(tree(b.process().pid)), dt = (Date.now() - t0) / 1000, m = mem(tree(b.process().pid));
  const tiles = BASE ? [] : await p.evaluate(() => window.labWall ? window.labWall.tiles() : []);
  const texts = BASE ? [] : await p.evaluate(() => [...document.querySelectorAll('#sesscol .wall .tile')].map(t => t.innerText.replace(/\n/g, ' | ')));
  fs.mkdirSync(out, { recursive: true });
  await p.screenshot({ path: path.join(out, `wall_${N}${PHONE ? '_phone' : ''}${BASE ? '_base' : ''}.png`), fullPage: PHONE });
  console.log(JSON.stringify({ n: +N, phone: PHONE, base: BASE, seconds: +dt.toFixed(1), cpu_cores: +((c1 - c0) / dt).toFixed(3), mem_rss_mb: m.rss, mem_pss_mb: m.pss,
    procs: m.per.filter(x => x.pss > 20),
    tiles: tiles.map(t => ({ id: t.id, err: t.err, cpu: t.cpu && +t.cpu.toFixed(3), fps: t.fps && +t.fps.toFixed(1), heap_mb: t.heap && Math.round(t.heap / 1e6), lag: t.lag && +t.lag.toFixed(1),
      checked: t.checked, mismatches: t.mismatches, gaps: t.gaps, live: t.live, catching: t.catching })), texts, errors: errs.slice(0, 10) }));
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
