// The Decisions tab, headless (puppeteer-core + Chrome, 420 px): answered questions are hidden behind one "Show the N answered"
// button (Bruno 2026-10-12), open ones shown, the button reveals the answered ones.   node decide_proof.js SITE_DIR ANSWERS.json SET OUT
const fs = require('fs'), path = require('path'), http = require('http');
const puppeteer = require('puppeteer-core');
const [site, ansf, set, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const answers = JSON.parse(fs.readFileSync(ansf, 'utf8'));
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.css': 'text/css', '.jpg': 'image/jpeg', '.mp4': 'video/mp4', '.mp3': 'audio/mpeg' };
const srv = http.createServer((q, r) => {
  const u = new URL(q.url, 'http://x'); let p = decodeURIComponent(u.pathname);
  const js = (c, o) => { r.writeHead(c, { 'Content-Type': 'application/json' }); r.end(JSON.stringify(o)); };
  if (p.startsWith('/feedback-api/')) { p = p.slice(14); if (p === 'decisions/' + set) return js(200, answers); if (p === 'lab/me') return js(200, { user: 'bruno', role: 'admin' }); return js(200, {}); }
  const f = path.join(site, p === '/' ? 'index.html' : p);
  fs.readFile(f, (e, d) => { if (e) { r.writeHead(404); r.end(); return; } r.writeHead(200, { 'Content-Type': MIME[path.extname(f)] || 'application/octet-stream' }); r.end(d); });
});
srv.listen(0, async () => {
  const base = `http://127.0.0.1:${srv.address().port}/`; let ok = true;
  const browser = await puppeteer.launch({ executablePath: '/usr/bin/google-chrome', headless: true, args: ['--no-sandbox'] });
  try {
    const pg = await browser.newPage(); await pg.setViewport({ width: 420, height: 900 });
    const errs = []; pg.on('pageerror', e => errs.push(e.message));
    await pg.goto(base + 'game.html?set=' + set + '#decide', { waitUntil: 'networkidle0' });
    await pg.screenshot({ path: path.join(out, 'decide_first.png') }); await pg.waitForSelector('.dq', { timeout: 15000 });
    const vis = await pg.$$eval('.dq', els => els.filter(e => e.offsetParent !== null).map(e => e.querySelector('h3').textContent));
    const btn = await pg.$eval('.dshowold', b => b.textContent).catch(() => null);
    const answered = Object.values(answers).filter(a => a && a.choice != null).length;
    console.log('visible:', JSON.stringify(vis)); console.log('button:', btn, '| answered in store:', answered);
    const billy = vis.some(t => /billy/i.test(t));
    ok = !billy && btn && errs.length === 0;
    await pg.screenshot({ path: path.join(out, 'decide_open.png'), fullPage: true });
    await pg.click('.dshowold'); const vis2 = await pg.$$eval('.dq', els => els.filter(e => e.offsetParent !== null).length);
    console.log('after show:', vis2, 'cards visible'); ok = ok && vis2 > vis.length;
    console.log('errors:', errs); console.log(ok ? 'ALL OK' : 'FAIL');
  } catch (e) { ok = false; console.log("ERROR", e.message); } finally { await browser.close(); srv.close(); process.exit(ok ? 0 : 1); }
});
