/* LIVE CLIPS, the Web Worker (liveclips.js starts it): its own core instance (core.js / core.wasm, built with the worker
 * environment: build_wasm.sh) running the Character Lab shell + the fighter's pack headless (liveclips_core.js), so the
 * page stays responsive while clips are simulated. Messages:
 *   in  {type: 'init', key, shellUrl, shellSha, pack (ArrayBuffer), slot, dummy}   -> {type: 'ready', key, bootMs, spawnGap} | {type: 'error', key, error}
 *   in  {type: 'clip', id, req}                                                   -> {type: 'clip', id, result} (data transferred)
 * One request at a time (the page's queue decides the order: visible clips first). */
importScripts('core.js', 'lab.js', 'liveclips_core.js');
let sim = null, simKey = null, shellSha = null, shellBytes = null, bios = null, doc = null;
const get = async u => { const r = await fetch(u, { cache: 'no-cache', credentials: 'same-origin' }); if (!r.ok) throw new Error(u + ': HTTP ' + r.status); return new Uint8Array(await r.arrayBuffer()); };
const sha256 = async u8 => [...new Uint8Array(await crypto.subtle.digest('SHA-256', u8))].map(x => x.toString(16).padStart(2, '0')).join('');
onmessage = async ev => {
  const m = ev.data;
  if (m.type === 'init') {
    try {
      if (!bios) bios = await get('neogeo.zip');
      if (shellSha !== m.shellSha) {
        shellBytes = await get(m.shellUrl);
        if (await sha256(shellBytes) !== m.shellSha) throw new Error('the shell: sha256 mismatch after the download');
        doc = self.ChainLab.readAnchor(shellBytes).doc; shellSha = m.shellSha; sim = null;
      }
      const pack = new Uint8Array(m.pack);
      if (!sim) { sim = await self.LiveSim.LiveSim.create(self.GeoCore, { bios, rom: shellBytes, pack, doc, slot: m.slot, dummy: m.dummy }); shellBytes = null; }
      else { sim.swap(pack); sim.boot(m.slot, m.dummy); }
      simKey = m.key;
      postMessage({ type: 'ready', key: m.key, bootMs: sim.bootMs, spawnGap: sim.spawnGap });
    } catch (e) { postMessage({ type: 'error', key: m.key, error: e.message }); }
    return;
  }
  if (m.type === 'clip') {
    let result;
    try {
      if (!sim) throw new Error('the simulation is not loaded');
      const q = Object.assign({}, m.req, { blob: m.req.blob ? new Uint8Array(m.req.blob) : null });
      result = sim.clip(q);
    } catch (e) { result = { error: e.message, fatal: true }; }
    postMessage({ type: 'clip', id: m.id, result }, result.data ? [result.data.buffer, result.pal.buffer] : []);
  }
};
