#!/usr/bin/env python3
"""The Ki training tree's sounds (note 20261014-171700-5d29: "the crackling tree and the falling tree; the falling tree
sound is missing"): AOF2 vs the brawler, frame by frame from the punch mark (main.c bn_fall_t; make_bonus.py FALL_MARK).

AOF2 side: our emulator (emu/neogeo_sdl --capture, SNDLOG = every byte the 68000 writes to REG_SOUND) from the bonus
select state (/data/tmp/t7/aof2_sel.state), Spirit Training at the top grade (A at 541, bonus_rip.py spirit_top); its
tree sounds = the slot 1 effects $1A $B7 (crack) and $1A $B8 (fall). Brawler side: harness.py from the note's scenario
(scenarios.json: Terry, the gauge pressed at the top), the bytes sound.c queued per tick; the ports = songs.json sfx
codes whose "from" is aof2 $1AB7 / $1AB8. Pass: the same events at the same frame from the mark (+-1).

A failed grade too (note 20261014-133606-5d29, Bruno: "the real sound from the original game when it's FAILED"): AOF2
pressed below the top (A at 521, tools/aof/ki_fail.py: its punch lands 38 frames after its first punch send, as on the
pass) -> its leaves ($1A $C6 / $C7) and fail jingle ($2E) from the punch mark vs the brawler's from note 133606's
scenario (the gauge pressed early): the ports ($1A + songs.json "from" aof2 $1AC6 / $1AC7) and the BONUS_OVER song.

    python3 tree_snd_proof.py [OUTDIR]          (default /data/tmp/tree_snd) -> OUT/timeline.json"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/tree_snd'
NOTE, MARK = '20261014-171700-5d29', 700
FAIL_NOTE, FAIL_P, PUNCH_TO_MARK = '20261014-133606-5d29', 521, 38   # (AOF2: first punch send -> the punch mark, the pass's 662 -> 700)
LEAF = {'1AC6': 'leaf', '1AC7': 'leaf'}
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


_B = []
def _brawler():                                  # (one core per process: both runs share it)
    import harness as H, scenario
    if not _B: _B.append(H.Brawler()); _B[0].game = scenario.GAME
    return _B[0]


def brawler():
    import harness as H, scenario
    songs = json.load(open(os.path.join(REPO, 'examples', 'brawler', 'songs.json')))['sfx']['from']
    port = {int(c, 16): TREE[f['cmd']] for c, f in songs.items() if f['game'] == 'aof2' and f['cmd'] in TREE}
    b = _brawler()
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


def aof2_fail():
    log = os.path.join(OUT, 'aof2_fail_snd.log')
    env = dict(os.environ, LOAD='/data/tmp/t7/aof2_sel.state', SEQ=f'4:a,{FAIL_P - 4}:-,4:a,600:-', SNDLOG=log)
    subprocess.run(['timeout', '600', os.path.join(REPO, 'emu', 'neogeo_sdl'), '/data/roms/aof2.neo', '--capture'], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rows = [(int(l.split()[0]), int(l.split()[1], 16)) for l in open(log) if l.strip()]
    mark = next(f for f, c in rows if f > FAIL_P and c == 0x15) + PUNCH_TO_MARK
    ev = [(f - mark, LEAF[f'{a:02X}{c:02X}']) for (f, a), (_, c) in zip(rows, rows[1:]) if f'{a:02X}{c:02X}' in LEAF]
    ev += [(f - mark, 'jingle') for f, c in rows if c == 0x2E and f > mark]
    return sorted(ev)


def brawler_fail():
    import harness as H, scenario
    songs = json.load(open(os.path.join(REPO, 'examples', 'brawler', 'songs.json')))
    port = {int(c, 16): LEAF[f['cmd']] for c, f in songs['sfx']['from'].items() if f['game'] == 'aof2' and f['cmd'] in LEAF}
    mus = {n: int(v, 16) for n, v in re.findall(r'#define MUS_(\w+) +0x([0-9A-F]+)', open(os.path.join(REPO, 'examples', 'brawler', 'build', 'snd', 'songs.h')).read())}
    b = _brawler()
    sc = json.load(open(os.path.join(HERE, 'scenarios.json')))[FAIL_NOTE]
    scenario.setup(b, sc)
    q, qa = b.syms['q'], b.syms['qt']; last = b.r(qa, 1)
    keys = []
    for part in sc['do_keys'].split(','):
        n, k = part.split(':'); keys += [k if k != '-' else ''] * int(n)
    ev, mark, song = [], None, b.r(b.syms['snd_song'], 1)
    for t in range(900):
        b.run(1, p1=keys[t] if t < len(keys) else '')
        qt = b.r(qa, 1); got = []
        while last != qt: got.append(b.r(q + last, 1)); last = (last + 1) & 31
        if mark is None and b.r(b.syms['bn_hit_t'], 2) == 12: mark = t
        for a, c in zip(got, got[1:]):
            if a == 0x1A and c in port: ev.append((t, port[c]))
        sg = b.r(b.syms['snd_song'], 1)
        if sg != song and sg == mus['BONUS_OVER']: ev.append((t, 'jingle'))
        song = sg
        if b.r(b.syms['bonus_on'], 1) == 3 and ev and ev[-1][1] == 'jingle': break
    return sorted((t - mark, k) for t, k in ev)


def main():
    os.makedirs(OUT, exist_ok=True)
    fa, fb = aof2_fail(), brawler_fail()
    fok = len(fa) == len(fb) and all(x[1] == y[1] and abs(x[0] - y[0]) <= 1 for x, y in zip(fa, fb))
    print('AOF2 failed grade (frame from the punch mark)', fa)
    print('brawler failed grade (tick from the blow)    ', fb)
    print(('OK  ' if fok else 'FAIL') + ' a failed grade: the leaves and the fail jingle at AOF2\'s frames')
    a, rows = aof2(); bw, port = brawler()
    ok = fok and len(a) == len(bw) and all(x[1] == y[1] and abs(x[0] - y[0]) <= 1 for x, y in zip(a, bw))
    print('AOF2    (frame from the punch mark: sound)', a)
    print('brawler (tick from the blow: sound)       ', bw, ' codes', {f'{k:02X}': v for k, v in port.items()})
    json.dump(dict(ok=ok, aof2=a, brawler=bw, aof2_fail=fa, brawler_fail=fb, aof2_bytes=rows), open(os.path.join(OUT, 'timeline.json'), 'w'), indent=1)
    print(('OK  ' if ok else 'FAIL') + ' the tree\'s crack and fall at AOF2\'s frames')
    sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
