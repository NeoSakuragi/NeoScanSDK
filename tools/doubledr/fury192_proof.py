#!/usr/bin/env python3
"""TODO #192 proof: Billy Lee's fury (DD's SUPER 236, anim 82) connecting in a real fight, Double Dragon vs the brawler,
per hit: the hit count, the victim's reaction, its height at the hit and its rise until the next, and the final launch
(peak, travel, landing).

    python3 fury192_proof.py [OUT_DIR]      (default /data/tmp/billy192/out)

DD: /data/neogeo_dict/doubledr/fury192.json + /data/tmp/dd95/fury192/snap_<frame>.png (fury_dd.py: Billy vs Jimmy,
placed mid-stage, the powered flag poked). Brawler: the harness (tick_sync) in the Chain Lab, Billy Lee at the screen's
left (x 20) with Ryo 60 px ahead, the meter full, D pressed: case `lab` = the camera locked (the lab: the screen is the
arena, the scenario of note 20261007-014003-5d29), case `open` = lock_x poked so the camera follows (a campaign
stretch: the launch away from the screen edge). Out: fury192.json (both sides' per-hit table), sheet_<case>.png (per hit
DD | brawler 3 frames after the hit, then the launch), table.txt. One core per process; run after `make`."""
import json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
from PIL import Image, ImageDraw
DD_JSON = '/data/neogeo_dict/doubledr/fury192.json'
DD_SNAPS = '/data/tmp/dd95/fury192'
RECIPE = {'setup': {'mode': 'lab', 'fighter': 'billy_lee', 'dummy': 'ryo', 'gap': 60, 'x': 20, 'meter': 'full'}}
DD_REACT = {55: 'reel', 56: 'reel', 57: 'reel', 67: 'blowback (launch)', 69: 'knockdown hop', 71: 'bounce', 73: 'down', 75: 'getup'}

def dd_side():
    s = json.load(open(DD_JSON))['super']; R = s['rows']; st = s['summary']['start']
    hits = [i for i in range(st, len(R)) if R[i]['dmg'] > R[i - 1]['dmg']]
    return per_hit([dict(t=i - st, f=R[i]['f'], y=R[i]['y2'], x=R[i]['x2'], ax=R[i]['x1'], react=R[i]['a2']) for i in range(st, len(R))],
                   [i - st for i in hits], lambda q: q['react'] in (71, 73, 75), lambda r: f"{r} {DD_REACT.get(r, '')}")

def per_hit(rows, hits, landed, name):
    """rows: per frame t, y (victim height), x, ax (attacker x), react; hits: their t -> the table"""
    out = []
    for k, t in enumerate(hits):
        nxt = hits[k + 1] if k + 1 < len(hits) else None
        span = [q for q in rows if t <= q['t'] < (nxt if nxt is not None else 10 ** 9)]
        if nxt is None:                                  # the launch: until it lands (bounce / down)
            end = next((i for i, q in enumerate(span) if i and landed(q)), len(span) - 1); span = span[:end + 1]
        r = rows[t + 3]['react'] if t + 3 < len(rows) else span[0]['react']   # (DD writes it at the hit; the brawler's
        out.append(dict(hit=k + 1, t=t, reaction=name(r), y_at_hit=round(span[0]['y'], 1),   # state the frame after)
                        y_max=round(max(q['y'] for q in span), 1), travel=round(abs(span[-1]['x'] - span[0]['x']), 1),
                        frames=len(span)))
    return out

def brawler_side(case, out):
    import harness as H, scenario
    hdr = open(os.path.join(scenario.GAME, 'build', 'bm_chars.h')).read()
    ba = re.search(r'enum \{ (BA_IDLE[^}]*)\}', hdr).group(1).replace(' ', '').split(',')
    b = H.Brawler(tick_sync=True); b.game = scenario.GAME
    scenario.setup(b, RECIPE)
    if case == 'open': b.w(b.syms['lock_x'], 2, 4000); b.run(1)
    rows, pics = [], []
    def grab(b):
        data, w, h, pitch = b._video
        pics.append(Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB'))
        rows.append(dict(t=len(rows), y=b.fget(2, 'y'), x=b.fget(2, 'x'), ax=b.fget(0, 'x'), state=b.states[b.fget(2, 'state')],
                         react=f"{b.states[b.fget(2, 'state')]} {ba[b.fget(2, 'anim')][3:]}", hp=b.fget(2, 'hp'), p1=b.states[b.fget(0, 'state')]))
    t0 = b.frame; b._want_video = True
    b.run(4, p1='d', each=grab); b.run(190, each=grab); b._want_video = False
    hits = [h[0] - t0 - 1 for h in b.hits if h[0] > t0 and h[1] == 2]
    tab = per_hit(rows, hits, lambda q: q['state'] in ('DOWN', 'GETUP') or 'BOUNCE' in q['react'], lambda r: r)
    return tab, rows, pics, hits

def sheet(path, dd_tab, br_tab, br_pics, br_hits, title):
    s = json.load(open(DD_JSON))['super']; f0 = s['rows'][s['summary']['start']]['f']
    W, Hh = 320, 224
    moments = [(f'hit {r["hit"]} +3', d['t'] + 3, r['t'] + 3) for d, r in zip(dd_tab, br_tab)]
    ld, lb = dd_tab[-1], br_tab[-1]
    moments += [('launch +8', ld['t'] + 8 + 9, lb['t'] + 8 + 7), ('launch landing', ld['t'] + ld['frames'] - 1, lb['t'] + lb['frames'] - 1)]
    im = Image.new('RGB', (2 * W + 8, (Hh + 16) * len(moments) + 20), 'white'); d = ImageDraw.Draw(im)
    d.text((4, 4), title, fill='black')
    for k, (lab, td, tb) in enumerate(moments):
        y = 20 + k * (Hh + 16)
        p = os.path.join(DD_SNAPS, f'snap_{f0 + td}.png')
        if os.path.exists(p): im.paste(Image.open(p).convert('RGB').resize((W, Hh)), (0, y + 14))
        if 0 <= tb < len(br_pics): im.paste(br_pics[tb], (W + 8, y + 14))
        d.text((4, y + 2), f'DOUBLE DRAGON  {lab} (t {td})', fill='black'); d.text((W + 12, y + 2), f'BRAWLER  {lab} (t {tb})', fill='black')
    im.save(path)

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/billy192/out'
    os.makedirs(out, exist_ok=True)
    dd_tab = dd_side(); res = {'dd': dd_tab}; lines = []
    case = os.environ.get('CASE')                        # one core per process: each case in its own child
    if case:
        tab, rows, pics, hits = brawler_side(case, out)
        json.dump({'tab': tab, 'rows': rows}, open(os.path.join(out, f'brawler_{case}.json'), 'w'))
        sheet(os.path.join(out, f'sheet_{case}.png'), dd_tab, tab, pics, hits,
              f'TODO #192 Billy Lee fury: Double Dragon (Billy vs Jimmy) | brawler ({case}: Billy vs Ryo)')
        sys.exit(0)
    import subprocess
    for c in ('lab', 'open'):
        subprocess.run([sys.executable, __file__, out], env=dict(os.environ, CASE=c), check=True)
        res[c] = json.load(open(os.path.join(out, f'brawler_{c}.json')))['tab']
    for name, tab in (('DD', dd_tab), ('brawler lab', res['lab']), ('brawler open', res['open'])):
        lines.append(f'{name}: {len(tab)} hits')
        for r in tab:
            lines.append(f"  hit {r['hit']} t{r['t']:4}  {r['reaction']:<28} height at hit {r['y_at_hit']:5}  max until next {r['y_max']:5}  "
                         f"victim travel {r['travel']:6} in {r['frames']} f")
    res['hits_equal'] = len(dd_tab) == len(res['lab']) == len(res['open']) == 5
    lines.append(f"hit count DD {len(dd_tab)} = brawler {len(res['lab'])} / {len(res['open'])}: {res['hits_equal']}")
    json.dump(res, open(os.path.join(out, 'fury192.json'), 'w'), indent=1)
    open(os.path.join(out, 'table.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))
