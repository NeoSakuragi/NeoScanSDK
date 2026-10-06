#!/usr/bin/env python3
"""Per fighter: (1) the ROM decoder vs our emulator's VRAM on a capture of idle + up to 4 specials (every display-list
entry of frame f-1 rendered from the ROM against the VRAM of frame f, match_ss2.match), (2) a contact sheet of idle +
those specials (+ the rage-only move) rendered from the ROM -> /data/tmp/samsho2/out/CC_name.png, check.json
    python3 proof_ss2.py [CHAR ...]"""
import sys, os, json, glob, re
import ss2, cap_ss2 as C, commands_ss2 as K, capture_cmds as X, match_ss2 as M, sheet_ss2 as S
OUT = '/data/tmp/samsho2/out'

def picks(c, n=4):
    seen = set(); fam = set(); out = []
    for e in K.command_list(c):                       # one per motion (the A / B / A+B variants share it)
        if e['kind'] not in ('ground', 'air', 'ground_stand'): continue
        d = K.descriptor(c, 0, 1, e['result']); an = K.anims_of(d)
        nt = e['notation'].split('(')[0].split(); btn = nt[-1] if nt else ''
        motion = ' '.join(nt[:-1]) + ('K' if 'C' in btn or 'D' in btn else 'S')
        if not an or an[0] in seen or motion in fam: continue
        seen.add(an[0]); fam.add(motion); out.append((e, an))
    stand = [p for p in out if p[0]['kind'] == 'ground_stand']
    ground = [p for p in out if p[0]['kind'] == 'ground'][:n]
    return ground, stand

def run(c):
    ground, stand = picks(c)
    seq = '20:-'
    for e, an in ground:
        if e['kind'] == 'ground': seq += ',' + X.seq_for(e) + ',110:-'
    cap = f'/data/tmp/samsho2/proof{c:02d}'
    for f in glob.glob(f'{cap}/*'): os.remove(f)
    C.run(cap, seq, load=f'{X.STA}/p1_{c:02d}.state', pal_every=0)
    fs = sorted(int(re.findall(r'vram(\d+)', p)[0]) for p in glob.glob(f'{cap}/vram*.bin'))
    tot = eq = exact = used = peq = 0; defs = set()
    for f in fs:
        if C.ram(cap, f - 1) is None: continue
        if not any(M.N.words(f'{cap}/vram{f}.bin')[0x8251:0x8251 + 240]): continue
        n, q, bad, ents = M.match(cap, f); used += 1
        if n != q and '-v' in sys.argv: print('  frame', f, n - q, 'px differ', dict(bad))
        tot += n; eq += q; exact += n == q; peq += M.match.pen_eq; defs.update(e['d'] & 0x7FFF for e in ents)
    for f in glob.glob(f'{cap}/ram*.bin'): os.remove(f)
    anims = [4 if c == 10 else 0] + [an[0] for _, an in ground] + [an[0] for _, an in stand][:1]
    labels = {anims[0]: 'idle'}
    for e, an in ground + stand[:1]: labels[an[0]] = e['notation'] + (' (rage)' if e['kind'] == 'ground_stand' else '')
    name = ss2.NAMES[c].replace(' ', '_').lower()
    S.sheet(c, anims, f'{OUT}/{c:02d}_{name}.png', labels)
    return dict(char=c, name=ss2.NAMES[c], frames=used, exact=exact, pixels=eq, of=tot, pen_equal=peq, defs=len(defs),
                sheet=f'{OUT}/{c:02d}_{name}.png', anims=anims)

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    chars = [int(x) for x in sys.argv[1:] if x != '-v'] or [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15]
    res = []
    p = '/data/neogeo_dict/samsho2/check.json'
    old = {r['char']: r for r in json.load(open(p))} if os.path.exists(p) else {}
    for c in chars:
        r = run(c); old[c] = r; print(r)
    json.dump(sorted(old.values(), key=lambda r: r['char']), open(p, 'w'), indent=1)
