#!/usr/bin/env python3
"""Hanzo's Mozu Otoshi (6 2 3 + C / D / C+D) CONNECTING in Samurai Shodown II, measured in our emulator (notes
20261015-212217-e03d / 212313: "too slow, in the real game the character goes out of the screen or very high, and his
voice"). P1 Hanzo (cap/p1_02.state), P2 poked GAP px in front of him, the command played; per frame both players'
class / action (+$E6 / +$E7), animation, world x / height, the camera, and every sound word the 68000 sends.
RUN (note 20261016-100735-e03d reopen): the run version, P2 150 px away, Hanzo runs (6 6 held), 2 brakes him
(class 0 action 41, anim 72), 3 + C+D catches out of the brake.
Sounds: 'snd' = the bytes the 68000 writes to the Z80's latch ($5F82, one byte a frame), 'queued' = the words as the
game queues them (the ring $10F000, its write index $10F104: [frame, word, sound id]): SS2 sends its queue one byte a
frame, so a word queued behind others reaches the Z80 later (the brake's seven prefix-$15 words, which the driver plays
nothing for, hold its $1C $4E back 14 frames).

    python3 mozu_ss2.py [C|D|CD|RUN ...] [--out DIR]   (default all four; /data/tmp/mozu_ss2)
    python3 mozu_ss2.py whistle [--out DIR]            the words only the run version sends vs CD (from the captures)
-> DIR/mozu_<b>.json (rows, sounds) + DIR/<b>/snap*.png every 4th frame"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import cap_ss2 as C

STATE = '/data/neogeo_dict/samsho2/cap/p1_02.state'
GAP = {'RUN': 150}                                   # (default 50)
SEQ = {'C': '10:-,3:R,3:D,3:DR,3:DRc,200:-', 'D': '10:-,3:R,3:D,3:DR,3:DRd,200:-', 'CD': '10:-,3:R,3:D,3:DR,3:DRcd,200:-',
       'RUN': '10:-,2:R,2:-,20:R,2:D,2:DR,3:DRcd,200:-'}
QUEUE, QW = 0x10F000, 0x10F104                         # the sound ring ($5FB0: a5 + $7000, write index a5 + $7104)

def queued(rams):
    """[(frame, word, ids)] the words queued in each frame (ring diff of consecutive RAM dumps)"""
    import neo2 as N
    rev = {}
    for i in range(1024): rev.setdefault(N.u16(0x5FD2 + 2 * i), []).append(i)
    out = []; prev = None
    for f, r in rams:
        w = r[QW - 0x100000]
        k = prev
        while prev is not None and k != w:
            o = QUEUE - 0x100000 + k; word = r[o] << 8 | r[o + 1]
            out.append([f, f'{word:04X}', [f'{i:03X}' for i in rev.get(word, [])]]); k = (k + 2) & 0xFF
        prev = w
    return out

def side(r, a):
    o = C.obj(r, a); b = a - 0x100000
    return dict(cls=r[b + 0xE6], act=r[b + 0xE7], anim=o['anim'], wx=o['wx'], wy=o['wy'], x=o['x'], y=o['y'], face=o['facing'])

def capture(btn, out):
    d = os.path.join(out, btn)
    C.run(d + '/probe', '3:-', load=STATE, vram=False, sndlog=False)
    r = C.ram(d + '/probe', 1); a1, a2 = C.players(r)
    x = C.obj(r, a1)['wx'] + GAP.get(btn, 50)
    n = C.nframes(SEQ[btn])
    pk = ';'.join(f'{k}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}' for k in range(1, 12))
    C.run(d, SEQ[btn], load=STATE, vram=False, pokes=pk, snaps=range(4, n - 1, 4))
    rows = []; rams = []
    for f in range(1, n - 1):
        rr = C.ram(d, f)
        if rr is None: continue
        rows.append({'f': f, 'p1': side(rr, a1), 'p2': side(rr, a2)}); rams.append((f, rr))
    snd = open(os.path.join(d, 'snd.txt')).read().split('\n') if os.path.exists(os.path.join(d, 'snd.txt')) else []
    json.dump({'button': btn, 'gap': GAP.get(btn, 50), 'seq': SEQ[btn], 'rows': rows, 'snd': [l for l in snd if l.strip()],
               'queued': queued(rams)},
              open(os.path.join(out, f'mozu_{btn}.json'), 'w'), indent=0)
    return rows, snd

def latch(m):
    """[(frame, word)] the words the Z80 received: (prefix, code) byte pairs of the latch log, at the code's frame"""
    b = [(int(l.split()[0]), int(l.split()[1], 16)) for l in m['snd']]
    out = []; i = 0
    while i < len(b):
        if b[i][1] in (0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C) and i + 1 < len(b):
            out.append((b[i + 1][0], f'{b[i][1]:02X}{b[i + 1][1]:02X}')); i += 2
        else: out.append((b[i][0], f'{b[i][1]:02X}')); i += 1
    return out

def whistle(out):
    """the run version's own sounds: the words it queues that CD (from a stand) does not, each with the frame it was
    queued and the frame the Z80 got it, relative to the catch (P1 class 1 action 45 first seen)"""
    m = {b: json.load(open(os.path.join(out, f'mozu_{b}.json'))) for b in ('CD', 'RUN')}
    res = {}
    for b, x in m.items():
        catch = next(r['f'] for r in x['rows'] if (r['p1']['cls'], r['p1']['act']) == (1, 45))
        res[b] = {'catch': catch, 'queued': [[f - catch, w, i] for f, w, i in x['queued']],
                  'latch': [[f - catch, w] for f, w in latch(x)]}
    reg = {w for _, w, _ in res['CD']['queued']}
    res['run_only'] = [q for q in res['RUN']['queued'] if q[1] not in reg]
    json.dump(res, open(os.path.join(out, 'whistle.json'), 'w'), indent=1)
    return res

if __name__ == '__main__':
    a = sys.argv[1:]; out = '/data/tmp/mozu_ss2'
    if '--out' in a: i = a.index('--out'); out = a[i + 1]; del a[i:i + 2]
    if a[:1] == ['whistle']:
        r = whistle(out)
        for b in ('CD', 'RUN'): print(b, 'catch', r[b]['catch'], 'queued', r[b]['queued'], 'latch', r[b]['latch'])
        print('run only', r['run_only']); sys.exit()
    for b in a or ['C', 'D', 'CD', 'RUN']:
        rows, snd = capture(b, out)
        print(b, len(rows), 'frames;', len(snd), 'sound lines')
