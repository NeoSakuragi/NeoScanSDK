#!/usr/bin/env python3
"""TODO #205 proof (found by #202): a special read from the ROM was hit-tested against the hurt box of the animation the
fighter played BEFORE the move (fighter_step: f->anim), never the move's own steps, so KOF's steps without a hurt box
did not protect. Fixed: fighter.c fighter_hurt_step (the program's step, pan / pstep, once its first frame played) in
every hurt test (combat, the hold crowd, thrown bodies, main.c's debug boxes), and export_bm rom_c gives a KOF step a
hurt box only with KOF's $0200 flag (the boxes stay loaded across steps; $0200 says the step has one: handlers98.react_hurt's rule).

harness.py on `make AI_OFF=1` builds (the test drives the enemies), our emulator only.

    BRAWLER_CORE=<core> python3 hurt205_proof.py GAME_DIR OUT TAG [FIGHTER ...]     (default kyo terry iori)

Per fighter, every ROM special in its six C slots + its fury (D) and MAX (down+D):
  kof98     KOF98's own per-frame hurt box, captured in KOF98 in our emulator (the export's row_steps: the step flags the
            game held each frame, $0200) -> the invincible start (frames before the first one with a hurt box); a capture
            that connected carries the hit-stops (Iori's 623C, Kyo's 236C): its later frames are offset (capture_same)
  engine    the brawler alone (nobody near): per frame of the program (srow >= 1) the step fighter_hurt_step reads (pan /
            pstep from RAM, the bstep_t from the P ROM) and whether it has a hurt box: vs KOF98's ROM ($0200 of the steps
            drawing that KOF frame in the move's states: rom_step_mismatch) and vs the capture frame by frame
  hit       two minions jabbing every frame (A, re-stood when knocked) on each side from the move's first frame: the first
            frame P1 is hit (life lost or a reel); own_inv: the move's own invincibility (INV_FURY: furies + roster
            `invincible`; down+D's rising-reversal rule `inv_rows`)
  ok        no ROM mismatch, and (moves without their own invincibility) the first hit lands on the engine's first frame
            with a hurt box
-> OUT/TAG.json"""
import json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))

SLOT_DIR = {'D': '', 'fD': 'R', 'dD': 'D', 'uD': 'U', 'dfD': 'DR', 'ufD': 'UR'}
MINIONS = (3, 4, 5, 6)
INV_FURY = 0xFF
BSTEP = 14                                                         # sizeof(bstep_t): frame, ticks, flags, hurt, atk, dx, hy


def kof_ref(game_dir, name, inp):
    """KOF98's own frames of the move, captured in KOF98 in our emulator (the export's row_steps: per frame the state, the
    step and the step's flags as the game held them, +$7C): hurt = $0200"""
    ex = json.load(open(os.path.join(game_dir, 'build', f'tmp_kof98_{name}', 'kof95_export.json')))['characters'][name]
    sp = next((s for s in ex['specials'] if s['input'] == inp), None)
    if sp is None or not sp.get('row_steps'): return None
    return [dict(state=r[0], step=r[1], hurt=bool(r[2] & 0x200)) for r in sp['row_steps']]


def rom_hurt(game_dir, name, inp):
    """KOF98's ROM: per KOF frame number drawn by the move's states (the captured states), the $0200 of the steps showing
    it (a set: one frame may sit on steps with and without it)"""
    import rom96
    ex = json.load(open(os.path.join(game_dir, 'build', f'tmp_kof98_{name}', 'kof95_export.json')))['characters'][name]
    sp = next((s for s in ex['specials'] if s['input'] == inp), None)
    m = rom96.Mem(rom96.load(rom96.GAMES['kof98']['neo'])[0], 'kof98'); out = {}
    sts = {x[0] for x in sp['states']} - {0}
    if inp.startswith('MAX '):                                     # (a MAX's program may play its version's other states:
        sts |= {x[0] for s in ex['specials'] if s['input'].startswith('MAX ') for x in s['states']} - {0}   # Terry's)
    for st in sts:
        steps, _ = rom96.parse_anim(m, rom96.anim_addr(m, ex['id'], rom96.state_slot(m, ex['id'], st)))
        for t in steps: out.setdefault(t[1], set()).add(bool(t[2] & 0x200))
    return out


class Prom:
    """the P ROM's first MB from the .neo (word-swapped there: bank_proof.py)"""
    def __init__(self, neo):
        raw = open(neo, 'rb').read(); p = struct.unpack_from('<I', raw, 4)[0]
        self.p = raw[4096:4096 + min(p, 0x100000)]
    def u8(self, a): return self.p[a ^ 1]
    def u32(self, a): return (self.u8(a) << 24) | (self.u8(a + 1) << 16) | (self.u8(a + 2) << 8) | self.u8(a + 3)


def engine_hurt(b, pr):
    """fighter_hurt_step's answer for P1 (a ROM special's own step: pan / pstep), or None outside a program frame"""
    off, _ = b.layout['pstep']
    pan = b.r(b.base + off - 4, 4); pstep = b.fget(0, 'pstep')
    if b.states[b.fget(0, 'state')] != 'SPECIAL' or not b.fget(0, 'srow') or not pan: return None
    st = pr.u32(pan + 2) + pstep * BSTEP
    return dict(frame=(pr.u8(st) << 8) | pr.u8(st + 1), hurt=bool(pr.u8(st + 3) & 2))


def setup(b, start, minions):
    st = b.states; b.load(start)
    for i in range(1, 8): b.fset(i, 'state', st.index('OFF'))
    for i in (0,) + MINIONS: b.fset(i, 'state', st.index('IDLE')); b.fset(i, 'hp', 60); b.fset(i, 'freeze', 0); b.fset(i, 'inv', 0); b.fset(i, 'y', 0)
    b.place(0, x=160, z=30); b.fset(0, 'facing', 1); b.fset(0, 'meter', 120)
    for i in MINIONS: b.place(i, x=1000, z=30); b.intent(i)


def jab(b):
    st = b.states; x, z = b.fget(0, 'x'), b.fget(0, 'z')
    for j, i in enumerate(MINIONS):
        fc = 1 if j < 2 else -1
        if st[b.fget(i, 'state')] not in ('IDLE', 'WALK', 'ATTACK'):
            b.fset(i, 'state', st.index('IDLE')); b.fset(i, 'freeze', 0); b.fset(i, 'y', 0); b.fset(i, 'inv', 0)
        b.fset(i, 'hp', 60)
        b.place(i, x=x - fc * (30 + 16 * (j % 2)), z=z); b.fset(i, 'facing', fc & 0xFF); b.intent(i, press=1, face=fc & 0xFF)


def play(b, start, keys, pr, minions):
    """the move from neutral; rows per frame from its first program frame"""
    setup(b, start, minions); st = b.states
    b.run(1, p1=keys); rows = []; t = 0
    while t < 400:
        if minions: jab(b)
        hp = b.fget(0, 'hp'); s0 = st[b.fget(0, 'state')]
        b.run(1); t += 1
        s1 = st[b.fget(0, 'state')]
        e = engine_hurt(b, pr)
        if rows or e is not None:
            rows.append(dict(st=s1, eng=e, inv=b.fget(0, 'inv'), hit=b.fget(0, 'hp') < hp or (s0 == 'SPECIAL' and s1 in ('HITSTUN', 'KNOCKDOWN')),
                             spec=b.fget(0, 'spec_ix')))
            if s1 != 'SPECIAL': break
        elif t > 6: break
    return rows


def main(game, out, tag, names):
    from harness import Brawler
    G = json.load(open(os.path.join(game, 'game.json'))); roster = [r['name'] for r in G['roster']]
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game); pr = Prom(os.path.join(game, 'brawler.neo'))
    res = {}
    for name in names:
        r = G['roster'][roster.index(name)]
        moves = [(k, SLOT_DIR[k] + 'c', v) for k, v in r['specials'].items() if v]
        if r.get('fury'): moves += [('fury', 'd', r['fury']), ('MAX', 'Dd', 'MAX ' + r['fury'])]
        frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))[name]
        b.pick(roster.index(name), unlock=True); b.run(10); start = b.save()
        res[name] = {}
        for role, keys, inp in moves:
            ref = kof_ref(game, name, inp)
            alone = play(b, start, keys, pr, False)
            if not alone or ref is None:
                res[name][role] = dict(input=inp, ok=None, why='no ROM program' if not alone else 'not in the KOF98 export'); continue
            eng = [x['eng'] for x in alone if x['eng'] is not None]
            rh = rom_hurt(game, name, inp)                         # (bm_frames: 'KOF character id:KOF frame')
            kofno = [int(frames[e['frame']].split(':')[1]) if str(frames[e['frame']]).count(':') == 1 else None for e in eng]
            rom_mism = [k for k, e in enumerate(eng) if kofno[k] in rh and e['hurt'] not in rh[kofno[k]]]
            rom_unknown = sum(1 for k in kofno if k not in rh)
            n = min(len(eng), len(ref))
            mism = [k for k in range(n) if eng[k]['hurt'] != ref[k]['hurt']]
            kof_inv = next((k for k, x in enumerate(ref) if x['hurt']), len(ref))
            eng_inv = next((k for k, x in enumerate(eng) if x['hurt']), len(eng))
            hits = play(b, start, keys, pr, True)
            first_hit = next((k for k, x in enumerate(hits) if x['hit']), None)
            own_inv = [k for k, x in enumerate(hits) if x['inv']][:3]
            res[name][role] = dict(input=inp, rom_step_mismatch=rom_mism[:12], rom_frames_unmatched=rom_unknown, kof_frames=len(ref), engine_frames=len(eng), compared=n, hurt_mismatch=mism[:12],
                                   kof_no_hurt=[k for k, x in enumerate(ref) if not x['hurt']][:40],
                                   kof_invincible_start=kof_inv, engine_invincible_start=eng_inv, first_hit_frame=first_hit,
                                   own_inv=bool(own_inv), capture_same=not mism and kof_inv == eng_inv,
                                   ok=not rom_mism and (bool(own_inv) or first_hit is None or first_hit >= eng_inv) and
                                      (bool(own_inv) or eng_inv == 0 or first_hit == eng_inv),
                                   kof_seq=' '.join(f"{x['state']}.{x['step']}{'H' if x['hurt'] else '-'}" for x in ref),
                                   engine_seq=' '.join(f"{x['frame']}{'H' if x['hurt'] else '-'}" for x in eng))
            print(tag, name, role, inp, json.dumps({k: v for k, v in res[name][role].items() if k not in ('kof_no_hurt', 'kof_seq', 'engine_seq')}), flush=True)
    json.dump(res, open(os.path.join(out, f'{tag}.json'), 'w'), indent=1)
    bad = [f'{n}:{k}' for n, v in res.items() for k, x in v.items() if x['ok'] is False]
    diff = [f'{n}:{k}' for n, v in res.items() for k, x in v.items() if x.get('capture_same') is False]
    print(tag, 'ALL OK' if not bad else 'MISMATCH ' + ' '.join(bad), '| differ from the KOF98 capture frame by frame:', ' '.join(diff) or 'none')


if __name__ == '__main__':
    os.makedirs(sys.argv[2], exist_ok=True)
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:] or ['kyo', 'terry', 'iori'])
