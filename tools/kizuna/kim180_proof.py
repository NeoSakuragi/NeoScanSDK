#!/usr/bin/env python3
"""TODO #180 proof: Kim's Phoenix (fury, D = Kizuna's 6246A) connecting in a real fight, every sprite on the screen
attributed to the entity that drew it (main.c order / block_spr / block_placed, budget_proof.Probe), next to Kizuna's
own fury (our emulator, followups_kz '6246A_h').

The second Kim of note 20261007-002048-5d29 was a script object of the Phoenix's export (frame of Kim drawn 195 px
behind him, rows 108-186): Kizuna's sound task 'SOUND' in slot 12 holding a dead task's Kim animation $50A0, taken as
one of Kim's objects (cap_kz.new_objects now skips tasks that never loaded a step).

    python3 kim180_proof.py [OUTDIR]          (default /data/tmp/kim180/out)

Per frame of the fury: every entity drawing (label, state, frame) and its sprites' screen x range; FAIL when a sprite
drawn by Kim or one of his effects lies more than 160 px behind his body (the ghost was at -195), or when the export's
6246A still carries a script object of Kim's body frames that far behind. -> OUT/kim180.json, OUT/phoenix_brawler.png
(every 4 frames), OUT/phoenix_kizuna.png, OUT/objects.txt (every entity drawing during his specials)."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/kim180/out'
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
from harness import Brawler
import budget_proof as BP
from PIL import Image, ImageDraw
VICTIM = 2
FAR = 160

def chains(V):
    """sprite -> screen x (sticky chains: +16 each)"""
    out, x, size = {}, 0, 0
    for s in range(1, 382):
        y3 = V[0x8200 + s]
        if y3 & 0x40: x += 16
        else: x = V[0x8400 + s] >> 7; size = y3 & 0x3F
        if size and any(V[s * 64 + 2 * r] or V[s * 64 + 2 * r + 1] & 0xF0 for r in range(min(size, 32))):
            out[s] = x - 512 if x >= 400 else x
    return out

def play(b, pr, keys, setup, shots_every=4, tag='fury'):
    setup()
    rows, cells, started, end = [], [], None, None
    for f in range(700):
        st = b.states[b.fget(0, 'state')]
        if started is None and st == 'SPECIAL': started = f
        if started is not None and end is None and st != 'SPECIAL': end = f
        b.run(1, p1=keys if f < 3 else '')
        pr.frame()                                       # RAM view of this frame (VRAM shows it next frame)
        if started is None:
            if f > 60: break
            continue
        if end is not None: break
        sx = chains(pr.vram); owners = pr.prev['owners']
        cam = b.r(b.syms['cam_x'], 2); cam = cam - 65536 if cam > 32767 else cam
        kx = int(b.fget(0, 'x')) - cam
        per = {}
        for s, x in sx.items():
            o = owners.get(s)
            if o is None: continue
            per.setdefault(o, []).append(x)
        kim = [o for o in per if o.startswith('P0:') or o.startswith('pj') and o.endswith(':kim')]
        far = {o: min(per[o]) for o in kim if min(per[o]) < kx - FAR}
        rows.append(dict(f=f - started, kim_x=kx, ents={o: [min(v), max(v) + 16] for o, v in per.items()}, far=far))
        if (f - started) % shots_every == 0:
            p = os.path.join(OUT, '_shot.png'); b.screenshot(p)
            cells.append((Image.open(p).convert('RGB'), f - started, far))
    return rows, cells, started, end

def grid(cells, out, title, cols=6):
    w, h = 320, 224
    sh = Image.new('RGB', (cols * w, 18 + ((len(cells) + cols - 1) // cols) * (h + 14)), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 3), title, fill='black')
    for k, (im, f, far) in enumerate(cells):
        x, y = k % cols * w, 18 + k // cols * (h + 14)
        d.text((x + 3, y + 1), f'fury frame {f}' + (f'  FAR {far}' if far else ''), fill='red' if far else 'black')
        sh.paste(im.resize((w, h)), (x, y + 14))
    sh.save(out)

def main():
    os.makedirs(OUT, exist_ok=True)
    roster = [c['name'] for c in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
    k = roster.index('kim')
    ex = json.load(open(os.path.join(GAME, 'build', 'tmp_kizuna_kim', 'kof95_export.json')))['characters']['kim']
    sp = next(s for s in ex['specials'] if s['input'] == '6246A')
    behind = [(i, o) for i, r in enumerate(sp['script']) for o in r[3] if o[1] < -FAR]
    b = Brawler(); pr = BP.Probe(b, GAME)
    b.pick(k, unlock=True); start = b.save()
    def setup():
        b.load(start); st = b.states.index
        for i in (0, VICTIM):
            b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
        b.place(0, x=100, z=20); b.fset(0, 'facing', 1); b.fset(0, 'meter', 120)
        b.place(VICTIM, x=160, z=20); b.fset(VICTIM, 'facing', -1)
        for i in range(3, 8): b.place(i, x=900, z=20)
        pr.prev = None
    rows, cells, started, end = play(b, pr, 'd', setup)
    hit = any(r['ents'] for r in rows) and b.fget(VICTIM, 'hp') < 60
    grid(cells, os.path.join(OUT, 'phoenix_brawler.png'), f'Kim Phoenix (D) connecting, brawler, every 4 frames; victim hp 60 -> {b.fget(VICTIM, "hp")}')
    far = [r for r in rows if r['far']]
    seen = {}
    for r in rows:
        for o, (a, z) in r['ents'].items(): seen.setdefault(o, [r['f'], r['f'], a - r['kim_x'], z - r['kim_x']]); seen[o][1] = r['f']; \
            seen[o][2] = min(seen[o][2], a - r['kim_x']); seen[o][3] = max(seen[o][3], z - r['kim_x'])
    with open(os.path.join(OUT, 'objects.txt'), 'w') as fo:
        fo.write('entities drawing during the Phoenix (first / last fury frame, x range relative to Kim body x)\n')
        for o, v in sorted(seen.items()): fo.write(f'  {o:20s} frames {v[0]}-{v[1]}  dx {v[2]}..{v[3]}\n')
        fo.write(f'\nexport 6246A script objects more than {FAR} px behind Kim: {len(behind)}\n')
    ok = started is not None and end is not None and hit and not far and not behind
    json.dump(dict(ok=ok, started=started, end=end, frames=len(rows), victim_hit=hit, far=far[:10],
                   export_behind=behind[:5], entities=seen), open(os.path.join(OUT, 'kim180.json'), 'w'), indent=1)
    print(open(os.path.join(OUT, 'objects.txt')).read())
    print('fury frames', len(rows), 'victim hit', hit, 'far frames', len(far), 'export behind', len(behind), 'ok' if ok else 'FAIL')

if __name__ == '__main__':
    main()
