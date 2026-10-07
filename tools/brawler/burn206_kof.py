#!/usr/bin/env python3
"""TODO #206: which of KOF98's ROM-read specials (tools/kof96/handlers98.ROM_SPECIALS) burn their victim, measured in our
emulator (tools/kof96/capture/romspecials98.trace: P2 standing 48 px ahead, close; and 112 px, mid), against the export's
rule (handlers98.fire_element: the element of the hitting animation step, its byte 1 bits 4-6 = the attacker's +$7E;
KOF98's hit $1AF44 copies it to the victim's +$132 and $17764 picks the victim's colours by it: $20 orange ($F8),
$30 purple ($F9), $50 orange in the launch group, $10 / $40 other effects, no burn).

The victim's burn = its object +$3A (palette byte) = $F8 / $F9 on a frame after a hit. Furies (DM) in their normal and
MAX version, 420 frames (Ralf's MAX Galactica Phantom burns on its last punch, frame ~300).

    python3 burn206_kof.py OUT.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'kof96')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96', 'capture'))
import romspecials98 as R, handlers98 as H, export96, rom96

COLOUR = {1: 'purple', 2: 'orange'}
FURY = {'21426C', '21416C', '23624C', '236236C', '21426D'}

def victim_palette(path):
    """per frame from the try's start: P2's +$3A (palette byte) and life"""
    out = []
    for line in open(path):
        p = line.split(); f = int(p[0]) - R.START
        if f < 0: continue
        q = bytes.fromhex(p[4]); out.append((f, q[0x3A], q[0x138] << 8 | q[0x139]))
    return out

def main(dst):
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98')
    res = {}
    for n, inps in H.ROM_SPECIALS.items():
        if H.ROM_GAME.get(n, 'kof98') != 'kof98': continue
        cid = export96.CAST98.index(n)
        for inp in sorted(inps):
            for sdm in ((False, True) if inp in FURY else (False,)):
                ex = inp.startswith('EX '); k = ('MAX ' if sdm else '') + inp
                rom = H.export_rom(m, cid, k, lambda fi, tab=None: fi)
                pred = sorted({e for e in [rom.get('elements', {}).get(st) for st in rom.get('states', [])] +
                               [e for e in H.object_elements(rom.get('objects', []))] if e})
                row = {'predicted_burn': sorted({COLOUR[H.BURN_OF[e]] for e in pred if e in H.BURN_OF})}
                for dist in ('close', 'mid'):
                    try: rows, _, path = R.trace(cid, inp, dist, ex=ex, frames=420 if inp in FURY else 220, dm=inp in FURY, sdm=sdm)
                    except Exception as e: row[dist] = {'error': str(e)}; continue
                    vp = victim_palette(path)
                    hits = sum(1 for a, b in zip(vp, vp[1:]) if b[2] < a[2])
                    pal = sorted({p for f, p, l in vp if p in (0xF8, 0xF9)})
                    row[dist] = {'hits': hits, 'burn': ['orange' if p == 0xF8 else 'purple' for p in pal],
                                 'first_burn': next((f for f, p, l in vp if p in (0xF8, 0xF9)), None)}
                hit_any = [d for d in ('close', 'mid') if row.get(d, {}).get('hits')]
                kof = sorted({c for d in hit_any for c in row[d]['burn']})
                row['kof98_burn'] = kof
                row['agree'] = (not hit_any) or kof == row['predicted_burn']
                res.setdefault(n, {})[k] = row
                print(n, k, row, flush=True)
    json.dump(res, open(dst, 'w'), indent=1)
    bad = [(n, k) for n, d in res.items() for k, r in d.items() if not r['agree']]
    print('disagree:', bad)
    return not bad

if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1]) else 1)
