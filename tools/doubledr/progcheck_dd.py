#!/usr/bin/env python3
"""The exported specials' programs (export_dd.py: bprim_t ops + the variant table) run by a Python copy of the brawler's
prog_update / pan_advance (examples/brawler/fighter.c), every row of every special, against the DD frame model
(model_dd.play: = the game, compare_dd.py): per frame the definition shown, x (px forward) and height.

    python3 progcheck_dd.py [EXPORT_DIR]      -> /data/neogeo_dict/doubledr/progcheck.json"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import dd, model_dd as M, export_dd as E

P = {v: k for k, v in E.P.items()}
def fmul16(v, k):
    a = abs(v); a = (a >> 16) * k + (((a & 0xFFFF) * k + 0x8000) >> 16)
    return -a if v < 0 else a

def run(sp, var, limit=400):
    r = sp['rom']; vt = r['vtable']; prims = r['prims']
    anims = [r['anims'][k] for k in r['states']]
    st = dict(x=0, y=0, vx=0, vy=0, g=0, fric=0, cnt=0, pres=0, an=None, step=0, left=0, end=False, land=False)
    out = []
    def pan_play(a):
        st['an'] = a; st['step'] = 0; st['left'] = a['steps'][0]['ticks'] + 1; st['end'] = False
    def pan_advance():
        a = st['an']; st['left'] -= 1
        if st['left']: return
        if st['step'] + 1 < len(a['steps']): st['step'] += 1
        else:
            st['end'] = True
            if a['mode'] == 'hold': st['left'] = 1; return
            st['step'] = 0
        st['left'] = a['steps'][st['step']]['ticks'] + 1
    for f in range(limit):
        pc = st['pres']; over = False
        for _ in range(96):
            op, a, b, v = prims[pc]; pc += 1
            if op & 0x80: op &= 0x7F; v = vt['rows'][var][b]
            name = P.get(op)
            if name == 'anim': pan_play(anims[a + (var * vt['vanim'] if vt['nvar'] else 0)])
            elif name == 'set':
                key = {0: 'vx', 1: 'vy', 2: 'g', 3: 'fric', 4: 'cnt'}[a]; st[key] = v
            elif name == 'mul': key = 'vx' if a == 0 else 'vy'; st[key] = fmul16(st[key], v)
            elif name == 'add': key = {0: 'vx', 1: 'vy', 4: 'cnt'}[a]; st[key] += v
            elif name == 'move': st['x'] += st['vx']
            elif name == 'fall':
                v0 = st['vy']; st['vy'] -= st['g']; st['y'] += v0; st['land'] = False
                if st['y'] <= 0: st['y'] = 0; st['land'] = True
            elif name == 'dec': st['cnt'] -= 1
            elif name == 'br':
                c = a & 0x7F; val = {0: st['end'], 2: st['land'], 4: st['cnt'] < 0, 7: True}[c]
                if val == bool(a >> 7):
                    if b < 0: break
                    pc = b
            elif name == 'resume': st['pres'] = pc
            elif name == 'jmp': pc = b
            elif name == 'resume_at': st['pres'] = b
            elif name in ('spawn',): pass
            elif name in ('end', 'form'): over = True; break
            else: raise ValueError(name)
        if over: break
        pan_advance()
        s = st['an']['steps'][st['step']]
        out.append((s['frame'], st['x'] / 65536, st['y'] / 65536))
    return out

def main(exdir):
    ex = json.load(open(os.path.join(exdir, 'kof95_export.json')))
    res = {}
    for name, ch in ex['characters'].items():
        cid = ch['id']; B = E.Builder(cid)
        frames = {f['record']: i for i, f in enumerate(ch['frames'])}
        for sp in ch['specials']:
            vt = sp['rom']['vtable']
            for v, a0 in enumerate(vt['anims']):
                got = run(sp, v)
                ref = M.play(cid, a0)
                # the model's record shows the step loaded in that frame; the brawler's after its frame's advance:
                # the definition compared with the model's next frame
                bad = []; dx = dy = 0.0
                for i, (fr, x, y) in enumerate(got):
                    if i + 1 >= len(ref): break
                    m = ref[i]; nm = ref[i + 1]
                    want = str(dd.steps(cid, nm['anim'])[1][nm['step']]['def_'])
                    have = ch['frames'][fr]['record']
                    dx = max(dx, abs(x - m['x'])); dy = max(dy, abs(y - m['y']))
                    if have != want and len(bad) < 5: bad.append([i, have, want])
                key = f'{name} {sp["input"]} {"ABCD"[v] if vt["nvar"] else "-"}'
                res[key] = dict(frames_prog=len(got), frames_model=len(ref) - 1, max_dx=round(dx, 2), max_dy=round(dy, 2), def_mismatch=bad)
                print(key, res[key], flush=True)
    json.dump(res, open('/data/neogeo_dict/doubledr/progcheck.json', 'w'), indent=1)

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/billy/ex')
