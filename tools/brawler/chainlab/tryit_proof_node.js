// "Try in game" proof in Node (tryit.js's loads on the browser's core): the Lab build (SITE/rom/lab-<f>.neo + its
// manifest), P1 = the fighter vs a dummy (the training), then (1) a queue of one animation plays it (lab.cur = its $NN,
// the fighter's frames = the animation's), (2) a queue of three plays them in order, back to back, (3) a slot override
// (forward + C = a pool special) plays it on forward + C, (4) the core's speed. Prints a JSON report.
//   node tryit_proof_node.js SITE_DIR FIGHTER [ANIM] [QUEUE a,b,c] [SLOT_SPECIAL_INPUT]
const fs = require('fs'), path = require('path');
const [site, f, one = 'A9', three = '51,5B,D4', spInput = '623D'] = process.argv.slice(2);
const CL = require(path.join(__dirname, 'lab.js'));
const GeoCore = require(path.resolve(site, 'core.js'));
const man = JSON.parse(fs.readFileSync(path.join(site, 'rom', `lab-${f}.json`)));
(async () => {
  const lab = await CL.Lab.create(GeoCore, { bios: fs.readFileSync(path.join(site, 'neogeo.zip')), rom: fs.readFileSync(path.join(site, man.rom)),
                                             moduleArgs: { locateFile: p => path.resolve(site, p) } }, man.layout);
  const dummy = man.fighters.indexOf('ryo');
  lab.boot(man.id, dummy, null);
  const rep = {};
  const P = (k) => lab.fget(0, k);
  const trace = (n, keys) => {
    const out = [];
    for (let i = 0; i < n; i++) {
      lab.setPad(0, typeof keys === 'function' ? keys(i) : keys || ''); lab.run(1);
      out.push({ cur: lab.tryCur(), pos: lab.tryPos(), state: lab.stateName(0), ix: P('spec_ix'), frame: P('frame_ovr'), pstep: P('pstep') });
    }
    return out;
  };
  // (1) one animation
  const send = cfg => lab.installTry(CL.encodeTry(Object.assign({ fighter: man.id }, cfg)));   // the TRY blob (load 6)
  send({ queue: [parseInt(one, 16)], now: true });
  let t = trace(150);
  rep.one = { load: lab.tryStatus(), played: t.filter(r => r.cur === parseInt(one, 16)).length, spec_ix: [...new Set(t.filter(r => r.cur !== 0xFFFF).map(r => r.ix))],
              frames: [...new Set(t.filter(r => r.cur === parseInt(one, 16)).map(r => r.frame))], states: [...new Set(t.map(r => r.state))] };
  // (2) three back to back
  const q = three.split(',').map(x => parseInt(x, 16));
  trace(30);
  send({ queue: q, now: true });
  t = trace(240);
  const order = []; let gaps = 0;
  t.forEach((r, i) => { if (r.cur !== 0xFFFF && order[order.length - 1] !== r.cur) order.push(r.cur); if (i && t[i - 1].cur !== 0xFFFF && r.cur === 0xFFFF && order.length < q.length) gaps++; });
  rep.queue = { load: lab.tryStatus(), order: order.map(v => '$' + v.toString(16).toUpperCase()), want: q.map(v => '$' + v.toString(16).toUpperCase()), inOrder: JSON.stringify(order) === JSON.stringify(q), gaps,
                frames_each: q.map(v => t.filter(r => r.cur === v).length) };
  // (3) forward + C = the pool special spInput (an S- piece)

  const k = man.pool.indexOf(spInput);
  send({ slots: { sp_fc: [CL.LE_SPEC | k] } }); trace(2);
  rep.slot_load = lab.tryStatus();
  lab.request(2); trace(20);
  t = trace(90, i => i < 3 ? 'Rc' : '');          // P1 faces right: R + C = forward + C
  rep.slot = { input: spInput, pool_index: k, played: t.filter(r => r.cur === (CL.LE_SPEC | k)).length, spec_ix: [...new Set(t.filter(r => r.state === 'SPECIAL').map(r => r.ix))] };
  // (3b) without the override forward + C plays the ROM's slot
  send({}); trace(60);
  lab.request(2); trace(20);
  t = trace(60, i => i < 3 ? 'Rc' : '');
  rep.slot_rom = { spec_ix: [...new Set(t.filter(r => r.state === 'SPECIAL').map(r => r.ix))], cur: [...new Set(t.map(r => r.cur))] };
  // (5) WHEN: a blob sent mid-move stays pending until P1 is back in neutral; "apply now" (tnow) applies it next tick
  trace(240); lab.installTry(CL.encodeTry({ fighter: man.id, queue: [0xD4], now: true }), true); trace(4);   // (P1 back in neutral first)
  const midState = lab.stateName(0);
  lab.installTry(CL.encodeTry({ fighter: man.id, queue: [0x51] })); trace(2);
  const pend = lab.tryStatus();
  t = trace(80);
  const afterNeutral = lab.tryStatus();
  const firstIdle = t.findIndex(r => r.state === 'IDLE' || r.state === 'WALK');
  trace(240); lab.installTry(CL.encodeTry({ fighter: man.id, queue: [0xD4], now: true }), true); trace(4);
  lab.installTry(CL.encodeTry({ fighter: man.id, queue: [0x51] }), true); trace(2);
  rep.when = { states: [...new Set(t.map(r => r.state))], sent_during: midState, after_send: pend, after_neutral: afterNeutral, first_neutral_frame: firstIdle,
               apply_now: lab.tryStatus(), state_when_applied_now: lab.stateName(0) };
  // (6) a refused blob: not version 1
  const bad = CL.encodeTry({ fighter: man.id, queue: [0x51] }); bad[2] = 9; lab.installTry(bad, true); trace(2);
  rep.refused = lab.tryStatus();
  // (4) speed: frames per second of the core alone
  const t0 = Date.now(); for (let i = 0; i < 600; i++) lab.run(1); rep.core_fps = Math.round(600 / ((Date.now() - t0) / 1000));
  console.log(JSON.stringify(rep, null, 1));
})();
