#!/usr/bin/env python3
"""TODO #222 proof: Yashiro's fury (D, KOF98 21426C) and MAX (down+D) always play the maxed-out mash (Bruno: "don't
implement the button detection, just apply the maxed-out version as standard"; tools/kof96/handlers98.FOLLOW_MAXED).

KOF98 side (our emulator, romspecials98.trace, P2 48 px ahead): the move with C pressed every 4 frames (the mash, the
study /data/study/mash) and without (the old brawler's version). Brawler side: a real campaign fight (AI on), Yashiro
picked on the select screen, the nearest enemy put 48 px in front, a full meter, D (or down+D) pressed once and no
other button. Per case: hits, damage, duration (the special's first frame to its last, hit-stops included) and the
special states in order; a frame sheet of the brawler every 4 frames (OUT/brawler_<DM|MAX>.png). Pass: the brawler's
hit count = KOF98's mashed (13 DM, 23 MAX), with no button pressed after the trigger.

    python3 yashiro222_proof.py [OUT_DIR]       (default /data/tmp/y222/out; examples/brawler built, AI on)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
import romspecials98 as K
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/y222/out'
CID, INP = 21, '21426C'
EVERY = 4

def kof(sdm, mash):
    rows = K.trace(CID, INP, 'close', False, 420, dm=True, sdm=sdm, mash=mash)[0]
    k0 = next(i for i, r in enumerate(rows) if K.special(r['state']))
    end = next((i for i in range(k0 + 2, len(rows)) if not K.special(rows[i]['state'])), len(rows))
    hits = sum(1 for i in range(k0 + 1, min(end + 30, len(rows))) if rows[i]['p2life'] < rows[i - 1]['p2life'])
    seq = []
    for r in rows[k0:end]:
        if not seq or seq[-1][0] != r['state']: seq.append([r['state'], 0])
        seq[-1][1] += 1
    return dict(hits=hits, damage=rows[k0]['p2life'] - min(r['p2life'] for r in rows[k0:]), duration=end - k0, states=seq)

def brawler(b, k, sdm):
    b.pick(k)
    st = b.states
    x0 = b.fget(0, 'x'); z0 = b.fget(0, 'z')
    foes = [i for i in range(1, 8) if b.fget(i, 'hp') > 0 and st[b.fget(i, 'state')] not in ('DEAD', 'NONE', 'OFF')]
    v = min(foes, key=lambda i: abs(b.fget(i, 'x') - x0) + abs(b.fget(i, 'z') - z0))
    b.fset(0, 'facing', 1); b.fset(0, 'meter', 300)
    b.place(v, x=x0 + 48, z=z0); b.fset(v, 'facing', -1); b.fset(v, 'hp', 300)
    h0 = len(b.hits); keys = 'Dd' if sdm else 'd'
    rows, cells, started, end = [], [], None, None
    for f in range(700):
        s = st[b.fget(0, 'state')]
        if started is None and s == 'SPECIAL': started = f
        if started is not None and end is None and s != 'SPECIAL': end = f
        if end is not None or (started is None and f > 60): break
        k_ = keys if f < 3 else ''
        if started is not None and (f - started) % EVERY == 0:
            p = os.path.join(OUT, '_shot.png'); b.pad = [set(k_), set()]; b.screenshot(p)
            cells.append((f - started, Image.open(p).convert('RGB')))
        else: b.run(1, p1=k_)
        rows.append(dict(f=f, st=s, part=b.fget(0, 'spart') if 'spart' in b.layout else None, vhp=b.fget(v, 'hp')))
    vh = [h for h in b.hits[h0:] if h[1] == v and h[2] > 0]
    return dict(victim=v, hits=len(vh), damage=sum(h[2] for h in vh), duration=(end - started) if end and started is not None else None,
                parts=[r['part'] for r in rows if started is not None and r['f'] >= started and
                       (r['f'] == started or r['part'] != rows[rows.index(r) - 1]['part'])]), cells

def sheet(cells, path, title, cols=10):
    if not cells: return
    w, h = cells[0][1].size
    im = Image.new('RGB', (cols * w, 16 + ((len(cells) + cols - 1) // cols) * (h + 12)), 'white'); d = ImageDraw.Draw(im)
    d.text((4, 2), title, fill='black')
    for n, (f, c) in enumerate(cells):
        x, y = (n % cols) * w, 16 + (n // cols) * (h + 12)
        im.paste(c, (x, y + 12)); d.text((x + 2, y), f'f{f}', fill='black')
    im.save(path)

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    K.OUT = os.path.join(OUT, 'traces')
    res = {}
    for sdm in (False, True):
        tag = 'MAX' if sdm else 'DM'
        res[tag] = {'kof98_mashed': kof(sdm, True), 'kof98_nomash': kof(sdm, False)}
    from harness import Brawler
    b = Brawler()
    k = [r['name'] for r in json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))['roster']].index('yashiro')
    for sdm in (False, True):
        tag = 'MAX' if sdm else 'DM'
        res[tag]['brawler'], cells = brawler(b, k, sdm)
        sheet(cells, os.path.join(OUT, f'brawler_{tag}.png'), f'Yashiro {tag} 21426C, brawler {res[tag]["brawler"]["hits"]} hits, '
              f'no button after the trigger (every {EVERY} frames)')
        res[tag]['ok'] = res[tag]['brawler']['hits'] == res[tag]['kof98_mashed']['hits']
    if os.path.exists(os.path.join(OUT, '_shot.png')): os.remove(os.path.join(OUT, '_shot.png'))
    json.dump(res, open(os.path.join(OUT, 'yashiro222.json'), 'w'), indent=1)
    for tag, r in res.items():
        print(tag, 'ok' if r['ok'] else 'FAIL', {s: {q: r[s][q] for q in ('hits', 'damage', 'duration')} for s in ('kof98_mashed', 'kof98_nomash', 'brawler')})
    print('ALL OK' if all(r['ok'] for r in res.values()) else 'FAIL')
