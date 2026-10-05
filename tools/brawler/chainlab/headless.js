// headless Chrome driver for the lab page proofs: node headless.js URL STEPS.json (steps: {eval, save?}, {wait}, {shot, full?}, {width, height, mobile?})
const { spawn } = require('child_process'), fs = require('fs');
const [url, stepsFile] = process.argv.slice(2), steps = JSON.parse(fs.readFileSync(stepsFile));
const port = 9333 + Math.floor(Math.random() * 500);
const chrome = spawn('google-chrome', ['--headless=new', `--remote-debugging-port=${port}`, '--user-data-dir=/data/tmp/chainlab/chrome', '--no-first-run', '--autoplay-policy=no-user-gesture-required', '--window-size=1600,1000', 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  let ws;
  for (let i = 0; i < 50; i++) { try { const l = await (await fetch(`http://127.0.0.1:${port}/json`)).json(); const p = l.find(t => t.type === 'page'); if (p) { ws = new WebSocket(p.webSocketDebuggerUrl); break; } } catch (e) {} await sleep(200); }
  await new Promise(r => ws.onopen = r);
  let id = 0; const pend = new Map();
  ws.onmessage = m => { const d = JSON.parse(m.data); if (d.id && pend.has(d.id)) { pend.get(d.id)(d); pend.delete(d.id); } else if (d.method === 'Runtime.consoleAPICalled') console.log('console:', d.params.args.map(a => a.value).join(' ')); else if (d.method === 'Runtime.exceptionThrown') console.log('EXC', JSON.stringify(d.params.exceptionDetails).slice(0, 600)); };
  const call = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
  await call('Runtime.enable'); await call('Page.enable');
  await call('Emulation.setDeviceMetricsOverride', { width: 1500, height: 1000, deviceScaleFactor: 1, mobile: false });
  await call('Page.navigate', { url });
  for (const s of steps) {
    if (s.width) await call('Emulation.setDeviceMetricsOverride', { width: s.width, height: s.height, deviceScaleFactor: 1, mobile: !!s.mobile });
    if (s.wait) await sleep(s.wait);
    if (s.eval) { const r = await call('Runtime.evaluate', { expression: s.eval, awaitPromise: true, returnByValue: true }); const v = r.result && (r.result.exceptionDetails ? 'EXC ' + JSON.stringify(r.result.exceptionDetails).slice(0, 500) : JSON.stringify(r.result.result.value)); console.log('eval:', (v || '').slice(0, 300)); if (s.save) fs.writeFileSync(s.save, JSON.stringify(r.result.result.value)); }
    if (s.shot) { const r = await call('Page.captureScreenshot', { format: 'png', captureBeyondViewport: !!s.full }); fs.writeFileSync(s.shot, Buffer.from(r.result.data, 'base64')); console.log('shot', s.shot); }
  }
  ws.close(); chrome.kill();
})();
