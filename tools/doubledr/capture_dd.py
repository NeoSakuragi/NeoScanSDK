#!/usr/bin/env python3
"""Play a move in our emulator from a vs state and measure it (Double Dragon).
    measure(seq, load=VS, close=False) -> dict(anims, frames, startup, hits, damage, p2_anims, dx, rise, snd, rows)
P1 = $10042A, P2 = $10052A. Damage = P2 +$26 (damage taken, KO at $6800); the hit's damage = +$FE.
Startup = frames from the first frame of the move's animation to the frame the damage lands."""
import json, sys
import cap_dd as c, dd
P1, P2 = 0x10042A, 0x10052A

def walk_in(frames):
    return f'{frames}:R,' if frames else ''

def measure(seq, load=c.VS, tail=90, walk=0, idle_anims=(0, 1, 2, 3, 124)):
    pre = walk_in(walk)
    rows = c.run(pre + seq + f',{tail}:-', load=load)
    t0 = c.nframes(pre)
    recs = []
    for r in rows:
        R = r['ram']; F = dd.fighter_fields(R, P1); G = dd.fighter_fields(R, P2)
        recs.append(dict(f=r['f'], anim=F['anim'], step=F['step'], def_=F['def_'], x=F['x'], y=F['y'],
                         p2anim=G['anim'], p2x=G['x'], dmg=c.u16(R, P2 + 0x26), snd=r['snd']))
    # the move = first frame after t0 whose anim is not idle/walk, until back to idle
    start = next((i for i, q in enumerate(recs) if q['f'] > t0 and q['anim'] not in idle_anims), None)
    if start is None: return dict(anims=[], frames=0, rows=recs)
    end = next((i for i in range(start, len(recs)) if recs[i]['anim'] in idle_anims), len(recs))
    seqa = []
    for q in recs[start:end]:
        if not seqa or seqa[-1] != q['anim']: seqa.append(q['anim'])
    hits = [(recs[i]['f'] - recs[start]['f'], recs[i]['dmg'] - recs[i - 1]['dmg']) for i in range(start, len(recs)) if recs[i]['dmg'] != recs[i - 1]['dmg']]
    ys = [q['y'] for q in recs[start:end]]
    p2a = []
    for q in recs[start:]:
        if not p2a or p2a[-1] != q['p2anim']: p2a.append(q['p2anim'])
    snd = sorted({s for q in recs[start:end] for s in q['snd']})
    return dict(anims=seqa, frames=end - start, startup=hits[0][0] if hits else None, hits=hits,
                damage=recs[-1]['dmg'] - recs[start - 1]['dmg'], p2_anims=p2a, dx=recs[end - 1]['x'] - recs[start]['x'],
                rise=(recs[start]['y'] - min(ys)) if ys else 0, snd=[f'{s:02X}' for s in snd], rows=recs, start=start)

if __name__ == '__main__':
    m = measure(sys.argv[1], walk=int(sys.argv[2]) if len(sys.argv) > 2 else 0)
    m.pop('rows'); print(json.dumps(m))
