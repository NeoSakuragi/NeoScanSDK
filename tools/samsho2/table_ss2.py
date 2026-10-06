#!/usr/bin/env python3
"""Move catalogue from the captures (capture_cmds.py -> moves/CC.json, CC_rage.json): per entry / extra input the actions
P1 went through, the animations, frames until P1 is back in class 0 sub 0 (idle), P1 travel / rise, whether P2 reacted
(P2 class 3 = hit reaction, 4 = thrown) and the sound commands. -> /data/neogeo_dict/samsho2/moves.md + moves.json
    python3 table_ss2.py"""
import json, os, glob
import ss2
D = '/data/neogeo_dict/samsho2/moves'

def summarize(m):
    rows = m['rows']; lead = 12
    act = [r for r in rows if r['f'] > lead]
    start = next((r['f'] for r in act if (r['p1']['cls'], r['p1']['sub']) not in ((0, 0),) and r['p1']['cls'] == 1 or r['p1']['cls'] in (4,)), None)
    if start is None:
        start = next((r['f'] for r in act if r['p1']['cls'] == 0 and r['p1']['sub'] >= 37), None)
    anims = []; acts = []
    for r in rows:
        if start and r['f'] >= start:
            a = r['p1']['a']
            if not anims or anims[-1] != a: anims.append(a)
            k = (r['p1']['cls'], r['p1']['sub'])
            if not acts or acts[-1] != k: acts.append(k)
    end = None
    if start:
        end = next((r['f'] for r in rows if r['f'] > start and r['p1']['cls'] == 0 and r['p1']['sub'] == 0), None)
    x0 = rows[0]['p1']['x']; y0 = rows[0]['p1']['y']
    seg = [r for r in rows if start and r['f'] >= start and (end is None or r['f'] < end)]
    hit = next((r['f'] for r in seg if r['p2']['cls'] in (3, 4)), None)
    p2_unarmed = any(r['p2']['mode'] for r in rows)
    snd = [v for r in seg for v in r['snd']]
    return dict(start=start, frames=(end - start) if start and end else None, anims=anims[:8], actions=acts[:4],
                dx=(max((r['p1']['x'] - x0 for r in seg), key=abs) if seg else 0),
                rise=(max((y0 - r['p1']['y'] for r in seg), default=0)), hit=(hit - start) if hit else None,
                p2_disarmed=p2_unarmed, sounds=snd[:12])

def main():
    out = {}; md = ['# Samurai Shodown II: captured moves (P1, from p1_CC.state; P2 Haohmaru 160 px away, throws 56 px)', '',
                    'frames = from the action start to P1 back in class 0 sub 0; hit = frames from the start to P2\'s reaction;',
                    'dx / rise in px (world x / y); rage = captured with P1 +$F0 = 32. Captures: tools/samsho2/capture_cmds.py.', '']
    for p in sorted(glob.glob(f'{D}/*.json')):
        key = os.path.basename(p)[:-5]; c = int(key[:2]); rage = key.endswith('rage')
        res = json.load(open(p)); rows = []
        md.append(f'## {c} {ss2.NAMES[c]}{" (rage)" if rage else ""}'); md.append('')
        md.append('| name | input | kind | result | actions | anims | frames | hit | dx | rise | P2 disarmed |')
        md.append('|---|---|---|---|---|---|---|---|---|---|---|')
        for m in res:
            s = summarize(m); e = m['entry']
            row = dict(name=m['name'], input=e['notation'] if e else m['seq'], kind=e['kind'] if e else 'extra',
                       result=e['result'] if e else None, **s)
            rows.append(row)
            if rage and not (e and e['kind'] in ('ground_stand',)): continue
            md.append(f"| {row['name']} | {row['input']} | {row['kind']} | {row['result'] if row['result'] is not None else ''} | "
                      f"{' '.join(f'{a}/{b}' for a, b in s['actions'])} | {' '.join(map(str, s['anims']))} | {s['frames'] or ''} | "
                      f"{s['hit'] if s['hit'] is not None else ''} | {s['dx']} | {s['rise']} | {'yes' if s['p2_disarmed'] else ''} |")
        md.append('')
        out[key] = rows
    json.dump(out, open('/data/neogeo_dict/samsho2/moves.json', 'w'), indent=0)
    open('/data/neogeo_dict/samsho2/moves.md', 'w').write('\n'.join(md))

if __name__ == '__main__': main()
