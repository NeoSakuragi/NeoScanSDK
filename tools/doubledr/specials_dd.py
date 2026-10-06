#!/usr/bin/env python3
"""Every command entry of every fighter played with each button A / B / C / D in our emulator, next to the ROM's
parameters of the animation that button selects (Double Dragon: the four buttons = four animations n .. n+3).
    python3 specials_dd.py [CHAR ...]  -> /data/neogeo_dict/doubledr/specials.json
Inputs come from the decoded pattern (commands_dd.py): exact steps 2 frames each, a charge step held window + 3 frames,
the button pressed with the newest direction. Supers (entry flag bit 2) need the powered state: object +$00 bit 0,
poked; they are played with A+B. P1 walks in 30 frames first (58 px from P2), P2 = Jimmy, idle."""
import json, os, sys
import cap_dd as c, dd, commands_dd as cm
from fighters_dd import CHARS, STATE
OUT = '/data/neogeo_dict/doubledr/specials.json'
KEY = {0: '-', 1: 'U', 2: 'D', 4: 'L', 8: 'R', 10: 'DR', 6: 'DL', 9: 'UR', 5: 'UL'}
P1, P2 = 0x10042A, 0x10052A

def inputs(e, button):
    seq = []
    for w, cont, v in reversed(e['pattern'][1:]):
        seq.append(f"{w + 3 if cont else 2}:{KEY.get(v, '-')}")
    last = KEY.get(e['pattern'][0][2], '-') if e['pattern'] else '-'
    last = '' if last == '-' else last
    btn = 'ab' if e['flags'] & 4 else button
    seq.append(f"3:{last}{btn}")
    if e['flags'] & 1: seq = ['2:UR', '6:-'] + seq                # air entries: jump first
    return ','.join(seq)

def mash(e, button):
    k = 'abcd'.index(button); n = e['pattern'][0][0] if False else dd.P[dd.off(e['addr'] + 2 + k)]
    return ','.join(['2:' + button, '2:-'] * (n + 1))

def chain(ch, n, limit=6):
    out = []
    while n and len(out) < limit and n not in [x['anim'] for x in out]:
        p = dd.anim_params(ch, n); out.append(p)
        b7 = int(p['hdr'][14:16], 16)
        n = b7 if b7 and b7 not in (0, 1) and b7 < dd.anim_count(ch) else 0
    return out

def play(ch, e, button, anim):
    seq = mash(e, button) if e['flags'] & 2 else inputs(e, button)
    pokes = ';'.join(f'{f}:10042A=81' for f in range(1, 60)) if e['flags'] & 4 else None
    pre = '50:R,4:-,' if anim < 0 else '30:R,12:-,'
    rows = c.run(pre + seq + ',170:-', load=STATE.format(ch), pokes=pokes)
    recs = []
    for r in rows:
        F = dd.fighter_fields(r['ram'], P1); G = dd.fighter_fields(r['ram'], P2)
        recs.append(dict(f=r['f'], anim=F['anim'], x=F['x'], y=F['y'], p2=G['anim'], p2x=G['x'], dmg=c.u16(r['ram'], P2 + 0x26),
                         snd=r['snd']))
    if anim < 0:                                         # the throw: the first animation change after the input
        t = c.nframes(pre + seq) - 3
        s = next((i for i in range(t, len(recs)) if recs[i]['anim'] != recs[t - 1]['anim'] and recs[i]['anim'] not in (0, 1, 2, 3, 13, 14)), None)
    else: s = next((i for i, q in enumerate(recs) if q['anim'] == anim), None)
    if s is None:
        got = sorted({q['anim'] for q in recs[c.nframes(pre):]})
        return dict(input=seq, triggered=False, anims_seen=got)
    end = next((i for i in range(s, len(recs)) if recs[i]['anim'] in (0, 1, 2, 3)), len(recs))
    seqa = []
    for q in recs[s:end]:
        if not seqa or seqa[-1] != q['anim']: seqa.append(q['anim'])
    hits = [[recs[i]['f'] - recs[s]['f'], recs[i]['dmg'] - recs[i - 1]['dmg']] for i in range(s, min(end + 30, len(recs)))
            if recs[i]['dmg'] > recs[i - 1]['dmg']]
    p2a = []
    for q in recs[s:]:
        if not p2a or p2a[-1] != q['p2']: p2a.append(q['p2'])
    ys = [q['y'] for q in recs[s:end]]
    return dict(input=seq, triggered=True, anims=seqa, frames=end - s, startup=hits[0][0] + 1 if hits else None,
                hits=hits, damage=sum(h[1] for h in hits), dx=recs[end - 1]['x'] - recs[s]['x'],
                rise=recs[s]['y'] - min(ys) if ys else 0, p2_anims=p2a,
                p2_push=recs[min(end + 20, len(recs) - 1)]['p2x'] - recs[s]['p2x'],
                snd=[f'{x:02X}' for x in sorted({x for q in recs[s:end] for x in q['snd']})])

def run(ch):
    res = []
    for e in cm.entries(ch):
        if e['flags'] & 8: continue                      # (8)/(2)+button: the 124 entries (opponent-state moves)
        row = dict(addr=f"{e['addr']:06X}", notation=cm.notation(e), flags=e['flags'], anims=e['anims'], variants={})
        for k, b in enumerate('abcd'):
            a = e['anims'][k]
            if a < 0:                                    # $C000 | n: command throw ($23ECA), played at contact range
                v = dict(note=f'command throw ${a & 0xFFFF:04X} ($2380E -> $23ECA)'); v.update(play(ch, e, b, a))
                row['variants'][b.upper()] = v; continue
            if k and a == e['anims'][0] and e['flags'] & 4: continue
            v = dict(rom=chain(ch, a)); v.update(play(ch, e, b, a)); row['variants'][b.upper()] = v
        res.append(row)
        print(ch, CHARS[ch], row['notation'], {b: (v.get('frames'), v.get('damage'), v.get('hits') and len(v['hits'])) for b, v in row['variants'].items()}, flush=True)
    return res

if __name__ == '__main__':
    chars = [int(x) for x in sys.argv[1:]] or [0, 2, 4, 5, 6, 7, 8, 9, 10, 11]
    data = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for ch in chars:
        data[str(ch)] = dict(name=CHARS[ch], entries=run(ch))
        json.dump(data, open(OUT, 'w'), indent=1)
