#!/usr/bin/env python3
"""model_dd.py vs Double Dragon itself (our emulator): each special of a fighter, buttons A-D, played from its vs state
(P2 far: no contact), per frame from the special's first animation: animation, step, x (px forward), y (px up).
    python3 compare_dd.py CHAR [STATE]   -> /data/neogeo_dict/doubledr/model_check_<char>.json"""
import json, sys
import cap_dd as c, dd, commands_dd as cm, specials_dd as sp, model_dd as M
from fighters_dd import STATE
P1 = 0x10042A

FAR_P2 = False
FAR = ';'.join(f'{f}:100530=03,100531=00' for f in range(1, 400))   # P2 kept at x 768 (+$06: no contact)

def capture(ch, seq, state, pre='45:L,15:-,'):
    rows = c.run(pre + seq + ',150:-', load=state, pokes=FAR if FAR_P2 else None)
    out = []
    for r in rows:
        F = dd.fighter_fields(r['ram'], P1)
        out.append((F['anim'], F['step'], F['x'], 488 - F['y'], F['dir'], r['snd']))
    return out

def compare(ch, anim, cap, right):
    s = next((i for i, q in enumerate(cap) if q[0] == anim), None)
    if s is None: return dict(triggered=False)
    model = M.play(ch, anim, right=right)
    x0 = cap[s][2] - (model[0]['x'] if right else -model[0]['x'])
    n = len(model); bad = []
    for i, m in enumerate(model):
        if s + i >= len(cap): break
        q = cap[s + i]; mx = x0 + (m['x'] if right else -m['x'])
        nm = model[i + 1] if i + 1 < len(model) else dict(anim=m.get('next'), step=0)   # a RAM dump = the state after the
        if (q[0], q[1]) != (nm['anim'], nm['step']) or abs(q[2] - int(mx)) > 1 or abs(q[3] - int(m['y'])) > 1:
            bad.append([i, [q[0], q[1], q[2], q[3]], [m['anim'], m['step'], round(mx, 2), round(m['y'], 2)]])
    end = next((i for i in range(s, len(cap)) if cap[i][0] in (0, 1, 2, 3)), len(cap))
    seq = []
    for q in cap[s:]:
        if not seq or seq[-1] != q[0]: seq.append(q[0])
    return dict(triggered=True, frames_model=n, frames_game=end - s, mismatches=len(bad), first=bad[:4], game_anims=seq[:8])

if __name__ == '__main__':
    FAR_P2 = '--far' in sys.argv; sys.argv = [a for a in sys.argv if a != '--far']   # (TODO #212: P2 poked far away:
    ch = int(sys.argv[1]); state = sys.argv[2] if len(sys.argv) > 2 else STATE.format(ch)   # the long moves never meet it)
    res = {}
    for e in cm.entries(ch):
        if e['flags'] & 0xA: continue
        for k, b in enumerate('abcd'):
            a = e['anims'][k]
            if a < 0 or (k and e['flags'] & 4): continue
            seq = sp.inputs(e, b)
            pokes = None
            cap = capture(ch, seq, state) if not e['flags'] & 4 else None
            if cap is None:
                cap = [(r) for r in []]
                rows = c.run('45:L,15:-,' + seq + ',150:-', load=state, pokes=';'.join(f'{f}:10042A=81' for f in range(1, 80)) + (';' + FAR if FAR_P2 else ''))
                cap = [(dd.fighter_fields(r['ram'], P1)['anim'], dd.fighter_fields(r['ram'], P1)['step'], dd.fighter_fields(r['ram'], P1)['x'],
                        488 - dd.fighter_fields(r['ram'], P1)['y'], dd.fighter_fields(r['ram'], P1)['dir'], r['snd']) for r in rows]
            right = not any(q[4] & 0x20 for q in cap[60:61])
            r = compare(ch, a, cap, right)
            res[f'{"SUPER " if e["flags"] & 4 else ""}{cm.notation(e)} {b.upper()}'] = r
            print(ch, cm.notation(e), b.upper(), r, flush=True)
    json.dump(res, open(f'/data/neogeo_dict/doubledr/model_check_{ch}{"_far" if FAR_P2 else ""}.json', 'w'), indent=1)
