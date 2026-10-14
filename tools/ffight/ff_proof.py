#!/usr/bin/env python3
"""Final Fight's Guy / Cody / Haggar in the brawler (our emulator: tools/brawler/harness.py, the Geolith core; never MAME),
the Lab shell with the fighter's pack (make LAB_PACK=<f> -> examples/brawler/pack-<f>.neo), the same scenarios FF was
measured in (rec_ff.py), every frame logged (+ a picture for the side-by-side sheets, sbs_ff.py):

  walk (forward held 60 frames), jumpn / jumpf (B; forward + B), special (A+B), chain (A pressed every other frame
  against the dummy), chain_back (the same, back + A on the last link), grab_knees (walk into the dummy, A x3),
  grab_fwd / grab_back (forward / back + A in the hold), grab_up (up + A: Haggar's piledriver)

    python3 ff_proof.py NAME [SCENARIO ...] [--png]   -> /data/tmp/ffight/brawler/NAME_SCENARIO.json (+ png/...)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, os.path.join(BR, 'chainlab')); sys.path.insert(0, BR)
import harness
from labdrive import Lab
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))
OUT = '/data/tmp/ffight/brawler'
DUMMY = 'terry'
LINKS = {'guy': 5, 'cody': 4, 'haggar': 3}

def scen_keys(name, scen):
    """-> (dummy gap px or None (far away), a function k -> keys for frame k given the log so far, frames)"""
    n = LINKS[name]
    if scen == 'walk': return None, lambda k, log: 'R', 60
    if scen == 'jumpn': return None, lambda k, log: 'b' if k == 0 else '', 70
    if scen == 'jumpf': return None, lambda k, log: 'Rb' if k == 0 else 'R', 70
    if scen == 'special': return None, lambda k, log: 'ab' if k == 0 else '', 90
    if scen == 'whiff': return None, lambda k, log: 'a' if k == 0 else '', 40
    if scen == 'jatk_n': return None, lambda k, log: 'b' if k == 0 else 'a' if k == 14 else '', 70
    if scen == 'jatk_f': return None, lambda k, log: 'Rb' if k == 0 else 'Ra' if k == 14 else 'R', 70
    if scen == 'jatk_d': return None, lambda k, log: 'b' if k == 0 else 'Da' if k == 22 else 'D' if k > 22 else '', 70
    def hits(log): return sum(1 for r in log if r.get('dmg'))
    if scen == 'chain': return 34, lambda k, log: ('a' if k % 2 == 0 else '') if hits(log) < n else '', 160
    if scen == 'chain_back':
        return 34, lambda k, log: (('La' if hits(log) >= n - 1 else 'a') if k % 2 == 0 else '') if hits(log) < n else '', 160
    if scen.startswith('grab_'):
        act = scen[5:]
        def keys(k, log):
            g = next((i for i, r in enumerate(log) if r['state'] == 'GRAB'), None)
            if g is None: return 'R'
            j = k - g
            if act == 'knees': return 'a' if j in (6, 26, 46) else ''
            if act == 'fwd': return 'Ra' if j == 6 else ''
            if act == 'back': return 'La' if 4 <= j <= 6 and j == 6 else ('L' if 2 <= j < 6 else '')
            if act == 'up': return 'Ua' if j == 6 else ''
            if act == 'b': return 'b' if j == 6 else ''           # hold + B (Haggar: the piledriver, throws.b)
            if act in ('bf', 'bb'): return ('R' if act == 'bf' else 'L') + 'b' if j == 6 else ''   # forward / back + B
            return ''
        return 60, keys, 260
    raise KeyError(scen)

SCENS = ['walk', 'jumpn', 'jumpf', 'special', 'chain', 'chain_back', 'grab_knees', 'grab_fwd', 'grab_back', 'grab_up',
         'whiff', 'jatk_n', 'jatk_f', 'jatk_d', 'grab_b', 'grab_bf', 'grab_bb']

# the sounds: every byte the game queues (sound.c q[], through the core's write tap: the frame the game asks for it, as
# rec_ff.py's 'snd' logs FF's ring), decoded as sound.c sends them ($1A + an effect code, a voice prefix + a code: fighter.c
# voice_id, the effect-voice bit takes the other team's prefix) and named back: a voice = 'v' + FF's command (voices.json
# cmd), an effect = its songs.json name
def snd_names(game, build, f):
    import re
    vh = open(os.path.join(game, build, 'snd', 'voices.h')).read()
    pre = {int(v, 16): k for k, v in re.findall(r'#define VOICE_(PREFIX2?_\w+) 0x([0-9A-F]+)', vh)}
    codes = [int(x) for x in re.search(r'vcode_\d+\[\] = \{([^}]*)\};\s*/\* slot \*/', vh).group(1).split(',')]
    vj = json.load(open(os.path.join(HERE, '..', 'brawler', 'voices.json')))['fighters'][f]['voices']
    voice = {codes[v['id']]: 'v' + v['cmd'][2:] for v in vj if v['id'] < len(codes) and codes[v['id']]}
    sh = open(os.path.join(game, build, 'snd', 'songs.h')).read()
    line = next(l for l in sh.split('\n') if l.startswith('#define SFX_LIST'))
    sfx = {int(c, 16): n for c, n in re.findall(r'\{ 0x([0-9A-F]+), "([^"]+)" \}', line)}
    return pre, voice, sfx

def snd_decode(stream, names):
    """[(frame, byte)] -> [(frame, 'vXX' | 'vXX(fx slot)' (an FF voice) | 's:NAME' (an effect) | 'ssgXX')]"""
    pre, voice, sfx = names; out = []; i = 0
    while i < len(stream):
        f, b = stream[i]
        nb = stream[i + 1][1] if i + 1 < len(stream) else None
        if b == 0x1A and nb is not None: out.append((f, 's:' + sfx.get(nb, '%02X' % nb))); i += 2; continue
        if b in pre and nb is not None:
            c = nb | (0x100 if '2' in pre[b] else 0)
            out.append((f, voice.get(c, 'code%03X' % c) + ('' if 'PLAYER' in pre[b] else '(fx slot)'))); i += 2; continue
        if b == 0x07 and nb is not None: i += 2; continue                # a song
        out.append((f, 'ssg%02X' % b)); i += 1
    return out

def main():
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument('name'); ap.add_argument('scen', nargs='*'); ap.add_argument('--png', action='store_true')
    a = ap.parse_args(); f = a.name
    harness.GAME = GAME
    L = Lab(rom=os.path.join(GAME, f'pack-{f}.neo'), game=GAME, build='build_shell'); b = L.b; ST = b.states
    G = json.load(open(os.path.join(GAME, 'game.json')))
    names = [r['name'] for r in G['roster']]; fid = len(names)
    ba = json.load(open(os.path.join(GAME, f'build_pack_{f}', 'lab.json')))['ba'] if os.path.exists(os.path.join(GAME, f'build_pack_{f}', 'lab.json')) else None
    L.start(fid, names.index(DUMMY)); b.run(30); base = b.save()
    os.makedirs(OUT, exist_ok=True)
    import re, subprocess
    nm = subprocess.run(['m68k-linux-gnu-nm', os.path.join(GAME, 'build_shell', 'rom.elf')], capture_output=True, text=True).stdout
    qh = int(re.search(r'^([0-9a-f]+) b qh$', nm, re.M).group(1), 16)
    qa = min((int(x, 16) for x in re.findall(r'^([0-9a-f]+) b q$', nm, re.M)), key=lambda x: abs(x - qh))   # sound.c's q
    stream = []
    def tap(addr, val, size):
        if size == 1 and qa <= addr < qa + 32: stream.append((b.frame, val))
    b._sndtap = harness.TAP_CB(tap); b.core.retro_neoscan_m68k_write_tap(b._sndtap)
    names = snd_names(GAME, 'build_shell', f)
    for s in a.scen or SCENS:
        if s in ('grab_up', 'grab_b', 'grab_bf', 'grab_bb') and f != 'haggar': continue
        b.load(base)
        gap, keys, frames = scen_keys(f, s)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 100
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + (gap if gap else 400), z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', b.fget(2, 'hp_max'))
        b.run(2)
        pdir = os.path.join(OUT, 'png', f'{f}_{s}')
        if a.png: os.makedirs(pdir, exist_ok=True)
        log = []; hp = b.fget(2, 'hp'); X0 = b.fget(0, 'x'); stream.clear(); F0 = b.frame
        for k in range(frames):
            kk = keys(k, log)
            if a.png:
                b.pad = [set(kk), set()]; b.screenshot(os.path.join(pdir, '%03d.png' % k))
            else: b.run(1, p1=kk)
            h = b.fget(2, 'hp')
            r = {'f': k, 'keys': kk, 'state': ST[b.fget(0, 'state')], 'anim': b.fget(0, 'anim'), 'step': b.fget(0, 'step'),
                 'x': round(b.fget(0, 'x') - X0, 3), 'y': round(b.fget(0, 'y'), 3), 'facing': b.fget(0, 'facing'),
                 'freeze': b.fget(0, 'freeze'), 'srow': b.fget(0, 'srow'), 'frame': b.fget(0, 'shown_frame'),
                 'd_state': ST[b.fget(2, 'state')], 'd_x': round(b.fget(2, 'x') - X0, 1), 'd_y': round(b.fget(2, 'y'), 1),
                 'd_hp': h, 'dmg': hp - h if h < hp else 0, 'd_freeze': b.fget(2, 'freeze'), 'cam': b.r(b.syms['cam_x'], 2) - cam,
                 'sx': round(b.fget(0, 'x') - b.r(b.syms['cam_x'], 2))}
            if ba and r['anim'] < len(ba): r['move'] = ba[r['anim']]
            log.append(r); hp = h
        snd = [(fr - F0, n) for fr, n in snd_decode(list(stream), names)]   # frame k = log[k] (sent while it ran)
        json.dump({'fighter': f, 'scenario': s, 'rows': log, 'snd': snd}, open(os.path.join(OUT, f'{f}_{s}.json'), 'w'))
        seq = []
        for r in log:
            k_ = (r['state'], r.get('move', r['anim']))
            if not seq or seq[-1][0] != k_: seq.append([k_, 1])
            else: seq[-1][1] += 1
        print(s, ' '.join(f'{st}/{mv}x{n}' for (st, mv), n in seq[:16]), '| dmg', [r['dmg'] for r in log if r['dmg']])
        print('   snd', ' '.join(f'{fr}:{n}@{log[fr].get("move", log[fr]["anim"]) if 0 <= fr < len(log) else "-"}' for fr, n in snd))

if __name__ == '__main__': main()
