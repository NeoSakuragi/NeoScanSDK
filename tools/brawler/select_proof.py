#!/usr/bin/env python3
"""Select screen proof (the Lab's Select screen tab, Bruno 2026-10-07): the editor's picture (chainlab/selectrender.js,
run in Node on the site's select.json, select_images.py) against the game's select screen in our emulator (harness.py),
pixel for pixel over the 304 px a TV shows (the screenshot = LSPC x 8-311), with the cursor on every fighter in turn
(the stick, left to right through the layout's order), bosses locked (a fresh game) and beaten; and the editor's
sprites per line against the LSPC's own count (the #170 probe core, retro memory 106: per line the sprites on it).

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
  const r = R.render(D, D.layout, { cursor: j.cursor, unlocked: j.unlocked });
  fs.writeFileSync(j.raw, Buffer.from(r.rgba.buffer));
  out.push({ counts: Array.from(r.counts), worst: r.worst, cursor: r.cursor, arrow: r.arrow });
}
fs.writeFileSync(process.argv[5], JSON.stringify(out));
"""


def main(game, out, sel_json=None):
    os.makedirs(out, exist_ok=True)
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    if not sel_json:
        import select_images
        sel_json = os.path.join(out, 'select.json'); json.dump(select_images.select_data(game, b=b), open(sel_json, 'w'))
    D = json.load(open(sel_json))
    L = build_tables.select_layout(json.load(open(os.path.join(game, 'game.json'))))
    assert D['layout'] == L, 'select.json is not this build\'s layout'
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
            shots.append((tag, p, lspc)); jobs.append({'cursor': c, 'unlocked': bool(unl), 'raw': os.path.join(out, f'editor_{tag}.raw')})
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
                     f'   arrow col {r["arrow"]["col"]} row {r["arrow"]["row"]}{" over " + ",".join(r["arrow"]["hits"]) if r["arrow"]["hits"] else ""}')
    lines.append(f'{len(shots)} screens, {bad} mismatch(es)')
    open(os.path.join(out, 'select_proof.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
    return bad


if __name__ == '__main__':
    if len(sys.argv) < 3: sys.exit(__doc__)
    sys.exit(1 if main(*sys.argv[1:4]) else 0)
