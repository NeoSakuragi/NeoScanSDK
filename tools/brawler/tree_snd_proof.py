#!/usr/bin/env python3
"""The Ki training tree's sounds (note 20261014-171700-5d29: "the crackling tree and the falling tree; the falling tree
sound is missing"): AOF2 vs the brawler, frame by frame from the punch mark (main.c bn_fall_t; make_bonus.py FALL_MARK).

AOF2 side: our emulator (emu/neogeo_sdl --capture, SNDLOG = every byte the 68000 writes to REG_SOUND) from the bonus
select state (/data/tmp/t7/aof2_sel.state), Spirit Training at the top grade (A at 541, bonus_rip.py spirit_top); its
tree sounds = the slot 1 effects $1A $B7 (crack) and $1A $B8 (fall). Brawler side: harness.py from the note's scenario
(scenarios.json: Terry, the gauge pressed at the top), the bytes sound.c queued per tick; the ports = songs.json sfx
codes whose "from" is aof2 $1AB7 / $1AB8. Pass: the same events at the same frame from the mark (+-1).

    python3 tree_snd_proof.py [OUTDIR]          (default /data/tmp/tree_snd) -> OUT/timeline.json"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/tree_snd'
NOTE, MARK = '20261014-171700-5d29', 700
TREE = {'1AB7': 'crack', '1AB8': 'fall'}


def aof2():
    log = os.path.join(OUT, 'aof2_snd.log')
    env = dict(os.environ, LOAD='/data/tmp/t7/aof2_sel.state', SEQ='4:a,537:-,4:a,600:-', SNDLOG=log)
    subprocess.run(['timeout', '600', os.path.join(REPO, 'emu', 'neogeo_sdl'), '/data/roms/aof2.neo', '--capture'], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = [(int(l.split()[0]), int(l.split()[1], 16)) for l in open(log) if l.strip()]
    ev = []
    for (f, a), (_, c) in zip(rows, rows[1:]):
        k = f'{a:02X}{c:02X}'
        if k in TREE: ev.append((f - MARK, TREE[k]))
    return ev, rows


def brawler():
    import harness as H, scenario
    songs = json.load(open(os.path.join(REPO, 'examples', 'brawler', 'songs.json')))['sfx']['from']
    port = {int(c, 16): TREE[f['cmd']] for c, f in songs.items() if f['game'] == 'aof2' and f['cmd'] in TREE}
    b = H.Brawler(); b.game = scenario.GAME
    scenario.setup(b, json.load(open(os.path.join(HERE, 'scenarios.json')))[NOTE])
    q, qa = b.syms['q'], b.syms['qt']; last = b.r(qa, 1)
    keys = []
    for part in json.load(open(os.path.join(HERE, 'scenarios.json')))[NOTE]['do_keys'].split(','):
        n, k = part.split(':'); keys += [k if k != '-' else ''] * int(n)
    ev, prev = [], None
    for t in range(700):
        b.run(1, p1=keys[t] if t < len(keys) else '')
        qt = b.r(qa, 1); got = []
        while last != qt: got.append(b.r(q + last, 1)); last = (last + 1) & 31
        ft = b.r(b.syms['bn_fall_t'], 2)
        for a, c in zip(got, got[1:]):
            if a == 0x1A and c in port: ev.append((ft - 2, port[c]))   # (bn_fall_t was raised after the send: tick ft - 2
    return ev, port                                                     #  from the blow = main.c fall_t)


def main():
    os.makedirs(OUT, exist_ok=True)
    a, rows = aof2(); bw, port = brawler()
    ok = len(a) == len(bw) and all(x[1] == y[1] and abs(x[0] - y[0]) <= 1 for x, y in zip(a, bw))
    print('AOF2    (frame from the punch mark: sound)', a)
    print('brawler (tick from the blow: sound)       ', bw, ' codes', {f'{k:02X}': v for k, v in port.items()})
    json.dump(dict(ok=ok, aof2=a, brawler=bw, aof2_bytes=rows), open(os.path.join(OUT, 'timeline.json'), 'w'), indent=1)
    print(('OK  ' if ok else 'FAIL') + ' the tree\'s crack and fall at AOF2\'s frames')
    sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
