#!/usr/bin/env python3
"""LB2 Moriya's follow-ups in the brawler (2026-10-12): his pack build (make LAB_PACK=moriya: the game with him in the
Lab slot, his roster entry's slots) in our emulator (tools/brawler/harness.py, the Geolith core; never MAME), a training
dummy. A pressed sequence (roster[].seq_press) starts its base from its slot and presses the slot's button again every
6 frames: the pieces must play in the sequence's order; each piece's hit is measured on its own run, the dummy kept
out of his depth until that piece starts, then put standing in front of him (so every piece meets a fresh, standing dummy).
The on-hit continuation (roster[].hit_next: Midare Setsugekka on the MAX) is fired on the fury key through the Lab's TRY
blob (chainlab/lab.js encodeTry, the full Lab meter), the dummy in front: the run's hit starts the continuation; far
away (a whiff) the move ends as it is.

    python3 tools/lastbld2/followups_lb2_proof.py [GAME_DIR]   -> /data/tmp/lb2lab/moriya_followups.json
"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
import harness
from labdrive import Lab

LAB_JS = os.path.join(BR, 'chainlab', 'lab.js')
LE_SPEC = 0x1000
# (name, the start: [(frames, keys)], the follow-up press, dummy gap px)
SEQS = [('Tsukikage A (forward + C)', [(2, 'Rc')], 'c', 60),
        ('Tsukikage B (up-forward + C)', [(2, 'URc')], 'c', 80),
        ('Byakuya 22A route 1 (down,up + A)', [(2, 'D'), (2, 'Ua')], 'a', 80),
        ('Shingetsu > Sougetsu (C, then C once it hit)', [(2, 'c')], 'c', 40)]
# (T6, 2026-10-14) roster[].seq_hit: the next piece also needs the piece's hit (LB2: Sougetsu only after Shingetsu hit,
# tools/lastbld2/sougetsu_lb2_proof.py): whiffed (the dummy far), C pressed all along, the move ends with the first piece
WHIFF = [('Shingetsu whiffed: no Sougetsu', [(2, 'c')], 'c', 250, 1)]
SEQ_HIT = {'specials.D'}


def encode(cfg):
    js = ("const CL=require(%r);const c=JSON.parse(process.argv[1]);"
          "process.stdout.write(Buffer.from(CL.encodeTry(c)).toString('hex'))") % LAB_JS
    return bytes.fromhex(subprocess.run(['node', '-e', js, json.dumps(cfg)], capture_output=True, text=True, check=True).stdout)


def main():
    game = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'examples', 'brawler'))
    harness.GAME = game
    L = Lab(rom=os.path.join(game, 'pack-moriya.neo'), game=game, build='build_pack_moriya'); b = L.b; ST = b.states
    G = json.load(open(os.path.join(game, 'game.json')))
    names = [r['name'] for r in G['roster']]; fid = len(names)
    CLJ = json.load(open(os.path.join(game, 'build_pack_moriya', 'chainlab.json')))
    pool = next(x for x in CLJ['fighters'] if x['name'] == 'slot')['pool']
    label = lambda i: pool[i]['input'] + (f" ({pool[i]['seq']} #{pool[i]['seq_i']})" if pool[i].get('seq') else '')
    L.start(fid, names.index('ryo')); b.run(30); base = b.save()
    lf = b.syms['lab_fields']
    out, ok = [], True

    def setup(gap, z=30):
        b.load(base)
        cam = b.r(b.syms["cam_x"], 2); x0 = cam + 40               # (room ahead: the screen clamps the dummy)
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + gap, z=z); b.fset(2, 'facing', 0xFF if gap > 0 else 1); b.fset(2, 'hp', b.fget(2, 'hp_max')); b.run(2)

    def run(start, again, gap, at_piece=None, frames=600):
        """-> [{piece, from, frames, hits}]; at_piece k: the dummy out of his depth (z + 60) until piece k starts, then in
        front of him"""
        setup(gap, 30 if at_piece is None else 90)
        keys = [k for n, k in start for _ in range(n)]
        hp = b.fget(2, 'hp'); pieces, cur = [], None
        for i in range(frames):
            k = keys[i] if i < len(keys) else (again if again and i >= 8 and i % 6 == 0 else '')
            b.run(1, p1=k)
            s = ST[b.fget(0, 'state')]; ix = b.fget(0, 'spec_ix')
            if s == 'SPECIAL' and ix != cur:
                cur = ix; pieces.append({'piece': label(ix), 'from': i, 'frames': 0, 'hits': 0})
                if at_piece is not None:
                    if len(pieces) - 1 == at_piece:             # (him back to a place with room ahead: Byakuya's run
                        fw = 1 if b.fget(0, 'facing') == 1 else -1  # takes him to the screen's edge, which clamps the dummy)
                        cam = b.r(b.syms['cam_x'], 2); px = cam + (60 if fw > 0 else 260)
                        b.place(0, x=px, z=30); b.place(2, x=px + gap * fw, z=30); b.fset(2, 'facing', 0xFF if fw > 0 else 1)
            if s == 'SPECIAL': pieces[-1]['frames'] += 1
            elif pieces and i > len(keys) + 2: break
            h = b.fget(2, 'hp')
            if h < hp and pieces: pieces[-1]['hits'] += 1
            hp = h
            if h < 40: b.fset(2, 'hp', b.fget(2, 'hp_max')); hp = b.fget(2, 'hp')
        return pieces

    for name, start, again, gap in SEQS:
        chain = run(start, again, gap)
        seq0 = chain[0]['piece'].split(' (')[1].split(' #')[0] if chain and ' (' in chain[0]['piece'] else None
        if seq0 in SEQ_HIT:                                  # (seq_hit: each next piece needs the hit, so the pieces are
            n = sum(1 for p in pool if p.get('seq') == seq0)  # measured on the chain run itself, one dummy; the C
            chain = chain[:n]; [p.update(gap=gap) for p in chain]   # presses after it start a new one: cut)
        for k in range(len(chain) if seq0 not in SEQ_HIT else 0):
            for g in (gap, 40, 20, 60, 100, 120, 140, 160):         # (the first gap its hit lands at: each piece its own reach)
                got = run(start, again, g, at_piece=k)
                chain[k]['hits'] = got[k]['hits'] if k < len(got) and got[k]['piece'] == chain[k]['piece'] else 0
                chain[k]['gap'] = g
                if chain[k]['hits']: break
        seq = chain[0]['piece'].split(' (')[1].split(' #')[0] if chain and ' (' in chain[0]['piece'] else None
        order = all(p['piece'].endswith(f'({seq} #{j})') for j, p in enumerate(chain))
        good = seq is not None and order and len(chain) == sum(1 for p in pool if p.get('seq') == seq) and all(p['hits'] >= 1 for p in chain)
        ok &= good; out.append({'case': name, 'pieces': chain, 'result': 'PASS' if good else 'FAIL'})
        print(f'{name}: {"PASS" if good else "FAIL"}', flush=True)
        for p in chain: print(f"   {p['piece']:34} from {p['from']:3} frames {p['frames']:3} hits {p['hits']} (gap {p.get('gap')})", flush=True)
    for name, start, again, gap, want in WHIFF:
        chain = run(start, again, gap)
        good = len(chain) == want and all(p['hits'] == 0 for p in chain)
        ok &= good; out.append({'case': name, 'pieces': chain, 'result': 'PASS' if good else 'FAIL'})
        print(f'{name}: {"PASS" if good else "FAIL"}', flush=True)
        for p in chain: print(f"   {p['piece']:34} from {p['from']:3} frames {p['frames']:3} hits {p['hits']}", flush=True)
    # the on-hit continuation: Midare Setsugekka on the fury key (TRY blob), the dummy in front
    mx = next(i for i, p in enumerate(pool) if p['input'] == '641236B' and not p.get('seq'))
    for gap, want in ((120, True), (-120, False)):         # (hit: the continuation; whiff, the dummy behind: the move ends as it is)
        setup(gap)
        blob = encode({'slots': {'fury': [LE_SPEC | mx]}, 'fighter': fid})
        L.poke(lf['tblob'], blob); L.poke(lf['lstat'], [0]); L.poke(lf['tnow'], [1]); L.poke(0, b'LAB1'); L.poke(5, [fid]); L.poke(7, [6])
        b.run(3)
        cam = b.r(b.syms['cam_x'], 2)
        b.place(0, x=cam + 160, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=cam + 160 + gap, z=30); b.fset(2, 'facing', 0xFF if gap > 0 else 1); b.fset(2, 'hp', b.fget(2, 'hp_max')); b.run(1)
        hp = b.fget(2, 'hp'); pieces, cur = [], None
        for i in range(500):
            b.run(1, p1='d' if i < 2 else '')
            s = ST[b.fget(0, 'state')]; ix = b.fget(0, 'spec_ix')
            if s == 'SPECIAL' and ix != cur: cur = ix; pieces.append({'piece': label(ix), 'from': i, 'frames': 0, 'hits': 0})
            if s == 'SPECIAL': pieces[-1]['frames'] += 1
            elif pieces and i > 4: break
            h = b.fget(2, 'hp')
            if h < hp and pieces: pieces[-1]['hits'] += 1
            hp = h
            if h < 40: b.fset(2, 'hp', b.fget(2, 'hp_max')); hp = b.fget(2, 'hp')
        ins = [p['piece'] for p in pieces]
        good = (ins == ['641236B', '641236B>B1'] and pieces[1]['hits'] >= 1) if want else ins == ['641236B']
        ok &= good
        nm = f"Midare Setsugekka {'hit' if want else 'whiff'} (gap {gap})"
        out.append({'case': nm, 'pieces': pieces, 'result': 'PASS' if good else 'FAIL'})
        print(f'{nm}: {"PASS" if good else "FAIL"}', flush=True)
        for p in pieces: print(f"   {p['piece']:34} from {p['from']:3} frames {p['frames']:3} hits {p['hits']}", flush=True)
    os.makedirs('/data/tmp/lb2lab', exist_ok=True)
    json.dump(out, open('/data/tmp/lb2lab/moriya_followups.json', 'w'), indent=1)
    print('ALL PASS' if ok else 'FAIL')
    sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
