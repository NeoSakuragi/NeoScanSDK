#!/usr/bin/env python3
"""TODO #184: the round-win animation of each non-KOF source game, read in our emulator (emu/neogeo_sdl --capture).
From each game's capture state, P2 is put one hit from the end of the round (its life low; SS2: P1's hit puts him
ahead and the round clock is set to its last second: a time-over win), P1 lands a light attack, and the run goes on
with no input: the animations P1 plays after the round is decided are its win. Per frame: P1's animation id, the sound
commands; screenshots every SNAP_EVERY frames for the source-vs-brawler sheets (win184_proof.py). KOF96 / 98 / 99: tools/kof98/capture/
wins98.py (GAME=kof96 / kof98 / kof99), the same idea with KOF's state numbers.

    python3 wins184.py OUTDIR [ss2:haohmaru ...]   -> OUTDIR/<game>_<fighter>/ (snaps) + OUTDIR/wins184.json
                                                     (2026-10-07: /data/tmp/win184/src; the json kept in
                                                     /data/neogeo_dict/captures/wins184)

Fields (each game's README / capture tools):
  SS2   the players are tasks named "0-PLAYER" / "1-PLAYER" (cap_ss2.players), animation word +$66, world x +$4E; the
        round clock = the BCD byte $100AC6 (one less every 40 frames [meas]); the word $106836 drops with P2's life
        ($3F80 -> $2FC0 at a light slash [meas]) but poking it does not end the round, so the clock does
  WHP   P1's animation = record $1060DA - base $100064 (cap_whp.obj), P2's life = $10610C (record +$0C), P2's x $100102
  KZ    P1 $108200 +$40 (char << 12 | n), P2's life $108513 (+$113), P2's x $108424 (cap_kz / capture_kz)
  DD    P1 $10042A +$1C (dd.fighter_fields), P2's damage taken $100550 (+$26, KO at $6800, capture_dd)"""
import json, os, sys, subprocess, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
SNAP_EVERY = 6
N = 720                                                  # frames per run

def u16(b, o): return b[o] << 8 | b[o + 1]

def ss2_p1(r):
    sys.path.insert(0, os.path.join(HERE, '..', 'samsho2')); import cap_ss2 as C
    a1, a2 = C.players(r)
    return a1, a2

def anim_ss2(r):
    a1, _ = ss2_p1(r)
    return u16(r, a1 - 0x100000 + 0x66) if a1 else None
def anim_whp(r): return u16(r, 0x60DA) - u16(r, 0x0064)
def anim_kz(r): return u16(r, 0x8240) & 0xFFF
def anim_dd(r): return u16(r, 0x042A + 0x1C)

def ss2_setup(state):
    """P2 50 px in front of P1 (its world x +$4E), P1's A at frame 10 (its hit: frame 26), the clock at 1 (frame 40)"""
    run(state, '3:-', [], '/data/tmp/win184/work/probe', dump=(1,), snaps=(), neo=GAMES['ss2'][0])
    r = open('/data/tmp/win184/work/probe/ram1.bin', 'rb').read()
    a1, a2 = ss2_p1(r); x = (r[a1 - 0x100000 + 0x4E] << 8 | r[a1 - 0x100000 + 0x4F]) + 50
    pk = [f'{f}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for f in range(1, 4)] + ['40:100AC6=01']
    return '10:-,3:a', pk

GAMES = {
    # game: (neo, fighter -> state, setup(state) -> (seq, pokes), anim reader)
    'ss2': ('/data/roms/samsho2.neo', {'haohmaru': '/data/neogeo_dict/samsho2/cap/p1_00.state',
                                       'genjuro': '/data/neogeo_dict/samsho2/cap/p1_12.state',
                                       'kuroko': '/data/neogeo_dict/samsho2/cap/p1_17.state',
                                       'hanzo': '/data/neogeo_dict/samsho2/cap/p1_02.state'}, ss2_setup, anim_ss2),
    'whp': ('/data/roms/whp.neo', {'hanzo': '/data/neogeo_dict/whp/cap/vs.state'},
            lambda st: ('10:-,3:a', [f'{f}:100102={240 * 128 >> 8 & 255:02X},100103={240 * 128 & 255:02X}' for f in range(1, 14)] +
                        ['2:10610C=01']), anim_whp),
    'kz': ('/data/roms/kizuna.neo', {'kim': '/data/neogeo_dict/kizuna/cap/vs.state'},
           lambda st: ('10:-,3:a', [f'{f}:108424=01,108425=18' for f in range(1, 14)] + ['2:108513=01']), anim_kz),
    'dd': ('/data/roms/doubledr.neo', {'billy_lee': '/data/neogeo_dict/doubledr/cap/vs.state',
                                       'billy_super': '/data/neogeo_dict/doubledr/cap/p1_01.state'},
           lambda st: ('30:R,3:a', ['2:100550=67,100551=F0']), anim_dd),
}

def run(state, seq, pokes, d, dump=None, snaps=None, neo=None):
    shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
    n = sum(int(x.split(':')[0]) for x in seq.split(','))
    dump = range(1, N) if dump is None else dump
    snaps = range(SNAP_EVERY, N, SNAP_EVERY) if snaps is None else snaps
    env = dict(os.environ, SEQ=seq + (f',{N - n}:-' if N > n else ''), SEQ2=f'{N}:-', OUT=f'{d}/cap.txt', LOAD=state,
               DUMP=';'.join(f'{f}:{d}/ram{f}.bin' for f in dump), SNDLOG=f'{d}/snd.txt', POKE=';'.join(pokes))
    if snaps: env.update(SNAPS=','.join(map(str, snaps)), SNAPDIR=d)
    subprocess.run([NGSDL, neo or GAMES['ss2'][0], '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=3600)

def capture(game, name, out):
    neo, states, setup, reader = GAMES[game]
    d = os.path.join(out, f'{game}_{name}')
    seq, pk = setup(states[name])
    run(states[name], seq, pk, d, neo=neo)
    seqa, snd = [], {}
    for l in open(f'{d}/snd.txt') if os.path.exists(f'{d}/snd.txt') else []:
        w = l.split()
        if len(w) >= 2 and w[0].isdigit(): snd.setdefault(int(w[0]) + 1, []).append(w[1])
    for f in range(1, N):
        p = f'{d}/ram{f}.bin'
        if not os.path.exists(p): continue
        a = reader(open(p, 'rb').read())
        if not seqa or seqa[-1][0] != a: seqa.append([a, f])
        os.remove(p)
    return {'anims': seqa, 'snd': {str(k): v for k, v in sorted(snd.items())}}

if __name__ == '__main__':
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    want = sys.argv[2:] or [f'{g}:{n}' for g, v in GAMES.items() for n in v[1]]
    path = os.path.join(out, 'wins184.json')
    res = json.load(open(path)) if os.path.exists(path) else {}
    for w in want:
        g, n = w.split(':')
        res[w] = capture(g, n, out)
        print(w, [a for a, _ in res[w]['anims']], flush=True)
        json.dump(res, open(path, 'w'), indent=1)
