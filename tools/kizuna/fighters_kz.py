#!/usr/bin/env python3
"""Kizuna Encounter's fighters for the tools in this folder (one code path for every character): ids, the data files
of each, the vs states its captures start from, and Kim's animation numbers moved to another fighter's.

Character ids (the select / debug name table $4AF4A, the animation tables $80000[char]): HAYATE 0, EAGLE 1, GOZU 2,
MEZU 3, ROSA 4, KIM 5, JOKER 6, CHUN 7, GORDON 8, SHISHIOH 9, R SHISHI 10, A CHUN 11, ZYAZU 12; R Shishi (10) plays
Shishioh's animations and A Chun (11) Chung's (their command lists differ: SHARES).

Animations: every fighter's state map (long[$69118 + 4 char], 480 words: state -> animation) uses the same states, the
animation numbers differ (Kim's idle is $A0, the others' 0; his jump fall $81, theirs $80): kim_anim(ch, n) = the
animation fighter ch plays in the first state where Kim plays n (identity for Kim)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import kz

CAST = {'hayate': 0, 'eagle': 1, 'gozu': 2, 'mezu': 3, 'rosa': 4, 'kim': 5, 'joker': 6, 'chung': 7, 'gordon': 8,
        'shishioh': 9, 'jyazu': 12}
SHARES = {'shishioh': (10, 'R Shishi'), 'chung': (11, 'A Chun')}
NAMES = {0: 'Hayate', 1: 'Eagle', 2: 'Gozu', 3: 'Mezu', 4: 'Rosa', 5: 'Kim Young Mok', 6: 'Joker', 7: 'Chung',
         8: 'Gordon', 9: 'Shishioh', 12: 'Jyazu (ZYAZU)'}
ROOT = '/data/neogeo_dict/kizuna'
KIM_FILES = {'capture': 'kim_capture.json', 'moves': 'kim_moves.json', 'followups': 'kim_followups.json',
             'brute': 'kim_brute.json', 'substates': 'kim_substates.json', 'voices': 'kim_voices.json',
             'cancels': 'cancels_kz.json', 'check': 'kim_substates_check.txt'}

def name_of(ch): return next(k for k, v in CAST.items() if v == ch)
def ddir(name):
    d = ROOT if name == 'kim' else os.path.join(ROOT, name)
    os.makedirs(d, exist_ok=True); return d
def path(name, kind, ext='json'):
    """the fighter's data file of that kind (Kim's keep their first names, in ROOT)"""
    if name == 'kim' and kind in KIM_FILES: return os.path.join(ROOT, KIM_FILES[kind])
    return os.path.join(ddir(name), f'{kind}.{ext}')

def teams(name):
    """the team records of its two vs states: (P1 first, P1 second, P2 first, P2 second); 'vs' = it is P1 against
    Hayate + Eagle, 'vs2' = P1 Hayate against it (its victim captures)"""
    ch = CAST[name]
    mate = 4 if ch != 4 else 5
    return {'vs': (ch, mate, 0, 1), 'vs2': (0, mate, ch, 1 if ch != 1 else 2)}
def state(name, which='vs'):
    if name == 'kim': return os.path.join(ROOT, 'cap', f'{which}.state')
    return os.path.join(ROOT, 'cap', f'{which}_{name}.state')

def smap(ch):
    b = kz.u32(0x69118 + 4 * ch); return [kz.u16(b + 2 * s) & 0xFFF for s in range(0x1E0)]
_K = {}
def kim_anim(ch, n):
    """Kim's animation n -> fighter ch's (the first state Kim plays it in)"""
    if ch == 5: return n
    if not _K: _K.update({a: s for s, a in reversed(list(enumerate(smap(5))))})
    return smap(ch)[_K[n]]

def make_states(name):
    """boot Kizuna into its two fights and save them (mkvs.py's inputs: the select times out, the team record poked)"""
    import boot
    for which, t in teams(name).items():
        N = 3005
        poke = ';'.join(f'{f}:1088EC={t[0]:02X},1088ED={t[2]:02X},1088EE={t[1]:02X},1088EF={t[3]:02X}' for f in range(2000, 2150))
        p1, p2 = ['-'] * N, ['-'] * N
        for f in range(600, 606): p1[f] = 'o'
        for f in range(650, 656): p2[f] = 'o'
        for f in range(720, 726): p1[f] = 's'
        for f in range(760, 766): p2[f] = 's'
        for f in range(801, 2300):
            if f % 20 < 3: p1[f] = p2[f] = 'a'
        boot.boot(N, save=3000, extra={'POKE': poke}, name=os.path.basename(state(name, which))[:-6], p1=p1, p2=p2)

if __name__ == '__main__':
    for n in sys.argv[1:]: make_states(n); print(n, state(n), state(n, 'vs2'))
