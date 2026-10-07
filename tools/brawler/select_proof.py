#!/usr/bin/env python3
"""Select screen proof (the Lab's Select screen tab, Bruno 2026-10-07): the editor's picture (chainlab/selectrender.js,
run in Node on the site's select.json, select_images.py) against the game's select screen in our emulator (harness.py),
pixel for pixel over the 304 px a TV shows (the screenshot = LSPC x 8-311), with the cursor on every fighter in turn
(the stick, left to right through the layout's order), bosses locked (a fresh game) and beaten; and the editor's
sprites per line against the LSPC's own count (the #170 probe core, retro memory 106: per line the sprites on it).
The stick (TODO #187): the editor's cursor graph (selectrender.js stick) = the build's (build_tables.py select_stick)
on the game's layout and on 300 shuffled ones (both modes); then the cursor walk in our emulator: from every
selectable fighter, each of right / left / up / down, bosses locked and beaten, where the game's cursor lands against
the graph (main.c sel_move: locked ones skipped) -> OUT_DIR/select_walk.txt, a table of moves.

    python3 select_proof.py GAME_DIR OUT_DIR [SELECT_JSON]     -> OUT_DIR/select_proof.txt (+ editor_*.png, game_*.png, diff_*.png)
(SELECT_JSON: a site's select.json, e.g. what the Lab serves; default: select_images.py for this build)"""
import json, os, subprocess, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
PROBE = '/data/tmp/budget170/geolith/libretro/geolith_libretro.so'
if os.path.exists(PROBE): os.environ.setdefault('BRAWLER_CORE', PROBE)
import build_tables
from harness import Brawler

NODE = r"""
const fs = require('fs'), R = require(process.argv[2]);
const D = JSON.parse(fs.readFileSync(process.argv[3])), jobs = JSON.parse(fs.readFileSync(process.argv[4]));
const out = [];
for (const j of jobs) {
  const r = R.render(D, j.layout, { cursor: j.cursor, unlocked: j.unlocked });
  let h = 2166136261 >>> 0; for (const v of r.rgba) { h ^= v; h = Math.imul(h, 16777619) >>> 0; }   // = selectTab.hash()
  fs.writeFileSync(j.raw, Buffer.from(r.rgba.buffer));
  out.push({ counts: Array.from(r.counts), worst: r.worst, cursor: r.cursor, arrow: r.arrow, hash: h.toString(16) });
}
fs.writeFileSync(process.argv[5], JSON.stringify(out));
"""
NODE_STICK = r"""
const fs = require('fs'), R = require(process.argv[2]);
const D = JSON.parse(fs.readFileSync(process.argv[3])), jobs = JSON.parse(fs.readFileSync(process.argv[4]));
R.prepare(D);
fs.writeFileSync(process.argv[5], JSON.stringify(jobs.map(j => R.stick(D, j.layout, j.mode).graph)));
"""


def heads_of(D, L):
    """each fighter's head point for its pose in L (select.json: the ROM's frame or a candidate)"""
    return {n: next(p for p in D['fighters'][n]['poses'] if L[n]['pose'] in p['alias'])['head'] for n in L}


def stick_move(G, n, d, locked):
    """main.c sel_move on the graph: right / left on past locked fighters, up / down the first selectable of ups / downs;
    none selectable that way: stay"""
    if d in ('up', 'down'): return next((t for t in G[n][d + 's'] if t not in locked), n)
    t = n
    for _ in range(len(G)):
        t = G[t][d]
        if t == n: break
        if t not in locked: return t
    return n


def stick_check(D, sel_json, out, L):
    """the editor's graph (Node) = the build's, on the game's layout and 300 shuffled ones -> (lines, mismatches)"""
    import random
    rnd = random.Random(187)
    jobs = [{'layout': L, 'mode': m} for m in ('positions', 'order')]
    for k in range(300):
        L2 = json.loads(json.dumps(L)); names = list(L2); slots = list(range(len(names))); rnd.shuffle(slots)
        for n, sl in zip(names, slots):
            L2[n]['x'] = rnd.randint(-20, 340); L2[n]['y'] = rnd.choice([rnd.randint(90, 230), 110, 160, 206]); L2[n]['slot'] = sl
            L2[n]['facing'] = rnd.choice(['left', 'right'])
        jobs.append({'layout': L2, 'mode': 'order' if k % 5 == 4 else 'positions'})
    js, jf, rf = os.path.join(out, 'stick.js'), os.path.join(out, 'stick_jobs.json'), os.path.join(out, 'stick_res.json')
    open(js, 'w').write(NODE_STICK); json.dump(jobs, open(jf, 'w'))
    subprocess.run(['node', js, os.path.join(HERE, 'chainlab', 'selectrender.js'), sel_json, jf, rf], check=True)
    res = json.load(open(rf)); bad = 0
    for j, g in zip(jobs, res):
        bad += g != build_tables.select_stick(j['layout'], heads_of(D, j['layout']), j['mode'])
    build = D.get('graph')
    lines = [f'stick: editor graph = build graph on {len(jobs)} layouts (the game\'s, both modes, + {len(jobs) - 2} shuffled): {len(jobs) - bad} agree, {bad} differ',
             f'stick: select.json graph (the build\'s) = the editor\'s on the game\'s layout: {build == res[0] if build else "no graph in select.json"}']
    return lines, bad + (build is not None and build != res[0])


def main(game, out, sel_json=None):
    os.makedirs(out, exist_ok=True)
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    if not sel_json:
        import select_images
        sel_json = os.path.join(out, 'select.json'); json.dump(select_images.select_data(game, b=b), open(sel_json, 'w'))
    D = json.load(open(sel_json))
    L = build_tables.select_layout(json.load(open(os.path.join(game, 'game.json'))))
    for n, v in L.items():                        # (a site's select.json from an older build: the game's poses must be among its frames)
        assert any(v['pose'] in p['alias'] for p in D['fighters'][n]['poses']), f'{n}: pose {v["pose"]} not in {sel_json}'
    order = sorted(L, key=lambda n: L[n]['slot'])
    stat = b.core.retro_get_memory_data(106)
    import ctypes as C
    T = (C.c_uint16 * (264 * 34)).from_address(stat) if stat else None
    shots, jobs = [], []
    for unl in (0, 1):
        b.core.retro_reset(); b.seq('600:-,4:o,100:-')
        if unl: b.unlock_all()
        b.seq('4:s,120:-')
        seen = []
        while True:
            c = order[b.r(b.syms['cursor'], 1)]
            if c in seen: break
            seen.append(c)
            tag = f'{"beaten" if unl else "fresh"}_{len(seen):02d}_{c}'
            b.run(30); p = os.path.join(out, f'game_{tag}.png'); b.screenshot(p)
            lspc = [T[l * 34] for l in range(16, 240)] if T else None
            shots.append((tag, p, lspc)); jobs.append({'cursor': c, 'unlocked': bool(unl), 'raw': os.path.join(out, f'editor_{tag}.raw'), 'layout': L})
            b.run(4, 'R'); b.run(12)
    njs = os.path.join(out, 'render.js'); open(njs, 'w').write(NODE)
    jf, rf = os.path.join(out, 'jobs.json'), os.path.join(out, 'res.json')
    json.dump(jobs, open(jf, 'w'))
    subprocess.run(['node', njs, os.path.join(HERE, 'chainlab', 'selectrender.js'), sel_json, jf, rf], check=True)
    res = json.load(open(rf))
    lines, bad = [], 0
    for (tag, p, lspc), j, r in zip(shots, jobs, res):
        ed = np.frombuffer(open(j['raw'], 'rb').read(), np.uint8).reshape(224, 320, 4)[:, 8:312, :3]
        Image.fromarray(ed).save(os.path.join(out, f'editor_{tag}.png')); os.remove(j['raw'])
        gm = np.asarray(Image.open(p).convert('RGB'))
        d = np.any(ed != gm, axis=2); nd = int(d.sum())
        if nd:
            Image.fromarray(np.where(d, 0, 255).astype(np.uint8)).save(os.path.join(out, f'diff_{tag}.png'))
        cm = None if lspc is None else sum(1 for a, c in zip(lspc, r['counts']) if a != c)
        bad += bool(nd) + bool(cm)
        lines.append(f'{tag:28s} pixels differing {nd:6d}   lines whose sprite count differs {cm}   worst line y {r["worst"]}: '
                     f'{r["counts"][r["worst"]]} (LSPC {lspc[r["worst"]] if lspc else "?"}, LSPC max {max(lspc) if lspc else "?"})'
                     f'   editor hash {r["hash"]}   arrow col {r["arrow"]["col"]} row {r["arrow"]["row"]}{" over " + ",".join(r["arrow"]["hits"]) if r["arrow"]["hits"] else ""}')
    lines.append(f'{len(shots)} screens, {bad} mismatch(es)')
    sl, sb = stick_check(D, sel_json, out, L); lines += sl; bad += sb
    wl, wb = walk(b, D, L, out); lines += wl; bad += wb
    open(os.path.join(out, 'select_proof.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return bad


def walk(b, D, L, out):
    """the cursor walk in our emulator (TODO #187): from every selectable fighter, each direction, bosses locked / beaten:
    the game's cursor after one press against the graph -> OUT/select_walk.txt (a table of moves) -> (summary, mismatches)"""
    order = sorted(L, key=lambda n: L[n]['slot']); slot = {n: k for k, n in enumerate(order)}
    G = D.get('graph') or build_tables.select_stick(L, heads_of(D, L), D.get('stick'))
    KEY = {'right': 'R', 'left': 'L', 'up': 'U', 'down': 'D'}; ARW = {'right': '->', 'left': '<-', 'up': '^', 'down': 'v'}
    cur = b.syms['cursor']; tab, bad, moves = [], 0, 0
    for unl in (0, 1):
        locked = set() if unl else {n for n in L if D['fighters'][n]['locked']}
        b.core.retro_reset(); b.seq('600:-,4:o,100:-')
        if unl: b.unlock_all()
        b.seq('4:s,120:-')
        tab.append(f'\nbosses {"beaten" if unl else "locked (a fresh game)"}: the game\'s cursor after one press (expected = the graph, locked skipped; * = differs)')
        tab.append(f'{"from":10s} ' + ' '.join(f'{ARW[d] + " " + d:>20s}' for d in KEY))
        for n in order:
            if n in locked: continue
            row = []
            for d in KEY:
                b.w(cur, 1, slot[n]); b.run(6); b.run(4, KEY[d]); b.run(12)
                got = order[b.r(cur, 1)]; exp = stick_move(G, n, d, locked); moves += 1
                bad += got != exp
                row.append(f'{got + ("" if got == exp else " *(" + exp + ")"):>20s}')
            tab.append(f'{n:10s} ' + ' '.join(row))
    txt = '\n'.join(tab).lstrip('\n') + '\n'
    open(os.path.join(out, 'select_walk.txt'), 'w').write(txt); print(txt)
    return [f'walk: {moves} presses in our emulator, {moves - bad} land on the graph\'s fighter, {bad} differ (select_walk.txt)'], bad


if __name__ == '__main__':
    if len(sys.argv) < 3: sys.exit(__doc__)
    sys.exit(1 if main(*sys.argv[1:4]) else 0)
