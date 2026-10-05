#!/usr/bin/env python3
"""Kim's moves played by Kizuna Encounter in our emulator (emu/neogeo_sdl --capture), one capture per recipe from
the 'vs' state (cap/vs.state: P1 Kim at x 240 facing right, P2 Hayate; P2's x pinned per recipe unless None).
Per frame: P1 [anim n (id & $FFF), step, x, y, flip, step pointer, life, zoom], P2 the same, the pool objects that are
not there at the start [slot, anim id, step, x, y, flip, step pointer, name] (x / y in px: world x = +$24,
y = +$28 (up negative; 0 on the floor); flip = +$0F bit 1; life = +$113; zoom = $10966A, the camera's shrink).

    python3 capture_kz.py [OUT.json] [names...]      (default /data/neogeo_dict/kizuna/kim_capture.json)

Reactions are Kim's own (P1) under P2 Hayate's attacks."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import cap_kz as cap

OUT = '/data/neogeo_dict/kizuna/kim_capture.json'
FAR, NEAR = 400, 300
DIRS = {'1': 'DL', '2': 'D', '3': 'DR', '4': 'L', '5': '-', '6': 'R', '7': 'UL', '8': 'U', '9': 'UR'}
def m(motion, b, hold=3):
    """a motion in numpad notation (P1 facing right), 3 frames per direction, the button with the last, held 3"""
    d = [DIRS[c] for c in motion]
    last = d[-1] if d[-1] != '-' else ''
    return '2:-,' + ','.join(f'{hold}:{x}' for x in d[:-1]) + f',3:{last}{b},3:{b},'
def charge(back, fwd, b, n=50):
    return f'2:-,{n}:{DIRS[back]},3:{DIRS[fwd]}{b},3:{b},'
def inp(v):
    """an input byte (bits 0-3 up / down / left / right, 4-7 A-D) -> the recorder's letters"""
    s = ''.join(k for b, k in ((1, 'U'), (2, 'D'), (4, 'L'), (8, 'R'), (16, 'a'), (32, 'b'), (64, 'c'), (128, 'd')) if v & b)
    return s or '-'
def from_pattern(steps, hold=3):
    """a ROM command pattern (commands_kz.pattern: newest first) -> input sequence oldest first"""
    seq = ['2:-']
    for typ, win, val in reversed(steps):
        if typ & 0x0F == 0x0B: seq.append(f'{max(win, 1) + 10}:{inp(val)}')      # charge: held longer than the window
        else: seq.append(f'{hold}:{inp(val)}')
    seq.append(f'3:{inp(steps[0][2])}')
    return ','.join(seq) + ','
AWAY = '2:-,40:R'
def away(seq): return '2:-,40:-,' + seq[4:]
RECIPES = {
    'idle': (FAR, '2:-,150:-', ''),
    'walk_fwd': (None, '2:-,60:R,10:-', ''), 'walk_back': (FAR, '2:-,60:L,10:-', ''),
    'run': (None, away('2:-,3:R,3:-,30:R,30:-'), AWAY), 'backdash': (FAR, '2:-,3:L,3:-,3:L,60:-', ''),
    'crouch': (FAR, '2:-,40:D,30:-', ''),
    'jump_up': (FAR, '2:-,3:U,80:-', ''), 'jump_fwd': (None, away('2:-,3:UR,80:-'), AWAY), 'jump_back': (FAR, '2:-,3:UL,80:-', ''),
    'hop_up': (FAR, '2:-,1:U,80:-', ''), 'hop_fwd': (None, away('2:-,1:UR,80:-'), AWAY),
    **{f'far_{b}': (FAR, f'2:-,3:{b},80:-', '') for b in 'abcd'},
    **{f'close_{b}': (NEAR, f'2:-,3:{b},80:-', '') for b in 'abcd'},
    **{f'crouch_{b}': (FAR, f'2:-,8:D,3:D{b},50:D,30:-', '') for b in 'abcd'},
    **{f'jump_{b}': (FAR, f'2:-,3:U,12:-,3:{b},80:-', '') for b in 'abcd'},
    **{f'jump_fwd_{b}': (None, away(f'2:-,3:UR,12:-,3:{b},80:-'), AWAY) for b in 'abcd'},
    **{f'fwd_{b}': (FAR, f'2:-,6:R,3:R{b},70:-', '') for b in 'abcd'},
    **{f'back_{b}': (FAR, f'2:-,6:L,3:L{b},70:-', '') for b in 'abcd'},
    **{f'df_{b}': (FAR, f'2:-,6:DR,3:DR{b},70:-', '') for b in 'abcd'},
    'ab': (FAR, '2:-,3:ab,90:-', ''), 'cd': (FAR, '2:-,3:cd,90:-', ''), 'bc': (FAR, '2:-,3:bc,90:-', ''),
    'ac': (FAR, '2:-,3:ac,90:-', ''), 'bd': (FAR, '2:-,3:bd,90:-', ''),
    # throws: P2 next to Kim, forward / back + C / D
    **{f'throw_{d}{b}': (270, f'2:-,6:{"R" if d == "f" else "L"},3:{"R" if d == "f" else "L"}{b},150:-', '') for d in 'fb' for b in 'cd'},
    # Kim hit by P2 (Hayate, facing left: forward = L)
    'react_a': (NEAR, '2:-,80:-', '2:-,3:a,75:-'), 'react_b': (NEAR, '2:-,80:-', '2:-,3:b,75:-'),
    'react_c': (NEAR, '2:-,90:-', '2:-,3:c,85:-'), 'react_d': (NEAR, '2:-,90:-', '2:-,3:d,85:-'),
    'react_crouch_c': (NEAR, '2:-,90:D', '2:-,3:Dc,85:-'),
    'react_sweep': (NEAR, '2:-,200:-', '2:-,8:D,3:DLc,60:D,129:-'),
    'react_air': (NEAR, '2:-,3:U,150:-', '2:-,8:-,3:c,139:-'),
    'react_throw': (270, '2:-,200:-', '2:-,6:L,3:Lc,189:-'),
    'react_knockdown': (NEAR, '2:-,220:-', '2:-,3:L,3:D,3:DL,3:b,3:b,203:-'),     # Hayate's 623B (cmd $28)
    'react_knockdown2': (NEAR, '2:-,220:-', '2:-,3:R,3:DR,3:D,3:DL,3:L,3:c,3:c,197:-'),   # Hayate's 63214C
    # the weak-to-strong chain (close A -> B -> C, each pressed while the previous one plays)
    'chain_abc': (NEAR, '2:-,3:a,6:-,3:b,6:-,3:c,80:-', ''), 'chain_ac': (NEAR, '2:-,3:a,6:-,3:c,80:-', ''),
    'chain_bc': (NEAR, '2:-,3:b,10:-,3:c,80:-', ''),
    # the KO: P1 at life 1 hit by P2's close C
    'react_ko': (NEAR, '2:-,200:-', '2:-,3:c,195:-'),
}
import commands_kz
CMDS = commands_kz.commands(5)
for c in CMDS:                                     # Kim's command list read from the ROM: each played on the ground
    if c['command'] in (6, 7, 0x22, 0x23) and c['notation'] in ('5656', '5454', '6C', '4C'): continue
    s = from_pattern(c['steps'])
    RECIPES[f"cmd_{c['notation']}"] = (FAR, s + '150:-', '')                                  # whiff, P2 far
    RECIPES[f"cmd_{c['notation']}_near"] = (NEAR, s + '150:-', '')                            # P2 in reach
    RECIPES[f"cmd_{c['notation']}_air"] = (FAR, '2:-,3:U,10:-,' + s[4:] + '120:-', '')       # in a jump

LOW_LIFE = '108313=14,108315=14,108391=14'          # P1 life 20 of 192 (red: desperation moves)
EXTRA = {}                                          # recipe -> more pokes every frame
for c in CMDS:
    if c['cond'] & 0x4440:
        n = f"cmd_{c['notation']}_low"
        RECIPES[n] = (FAR, from_pattern(c['steps']) + '150:-', ''); EXTRA[n] = LOW_LIFE
        RECIPES[n + '_near'] = (NEAR, from_pattern(c['steps']) + '150:-', ''); EXTRA[n + '_near'] = LOW_LIFE
# 236A (cond bit 6): only while +$107 bit 5 is set (set by the tag-in code, $350DE / $3668C, when +$109 bit 7 and +$108
# bit 4) and the counter +$1BA <= 20: the tag-in attack. Played here with those two forced every frame.
TAGIN = '108307=20,1083BA=00,1083BB=00'
for k in ('cmd_236A', 'cmd_236A_near'): EXTRA[k] = TAGIN
EXTRA['react_ko'] = '108313=01,108315=01,108391=01'
# whiffs for the export: P2 walks away first (AWAY: 40 frames back, nothing pinned)
for c in CMDS:
    k = f"cmd_{c['notation']}"
    if k not in RECIPES: continue
    s = from_pattern(c['steps'])
    RECIPES['sw_' + c['notation']] = (None, away(s + '150:-'), AWAY)
    if f'{k}_low' in RECIPES:
        RECIPES[f"sw_{c['notation']}_low"] = (None, away(s + '150:-'), AWAY); EXTRA[f"sw_{c['notation']}_low"] = LOW_LIFE
EXTRA['sw_236A'] = TAGIN

# Kim as the victim of Hayate's specials (state vs2: P1 Hayate + Rosa, P2 Kim + Eagle; Hayate faces right, the ROM
# patterns as listed): the rows keep Kim first
SWAP = {'react_knockdown': (NEAR, '2:-,3:R,3:D,3:DR,3:b,3:b,200:-', '2:-,220:-'),         # Hayate's 623B
        'react_knockdown2': (NEAR, '2:-,3:L,3:DL,3:D,3:DR,3:R,3:c,3:c,200:-', '2:-,220:-'),  # Hayate's 63214C
        'react_launch': (NEAR, '2:-,40:D,3:Uc,3:Uc,200:-', '2:-,250:-'),                     # Hayate's [2]8C
        'react_throw2': (270, '2:-,6:R,3:Rc,180:-', '2:-,200:-')}                            # Hayate's 6C throw
RECIPES.update(SWAP)

def fighter(r, a):
    o = cap.obj(r, a)
    return [o['anim'] & 0xFFF, o['step'], o['x'], o['y'], o['flags'] >> 1 & 1, o['ptr'], o['raw'][0x113],
            r['cam'][0x2A], o['anim'] >> 12, cap.s16(r['cam'], 0x1A)]

def capture(name, pokes_extra=None):
    p2x, seq, seq2 = RECIPES[name]
    n = max(cap.nframes(seq), cap.nframes(seq2) if seq2 else 0)
    pk = [f'{f}:108424={p2x >> 8:02X},108425={p2x & 255:02X}' for f in range(n)] if p2x else []
    pokes_extra = pokes_extra or EXTRA.get(name)
    if pokes_extra: pk = [f'{f}:{pokes_extra}' for f in range(n)] if not pk else [p + ',' + pokes_extra for p in pk]
    sw = name in SWAP
    rows = cap.run(seq, seq2, pokes=';'.join(pk) or None, load=cap.VS2 if sw else cap.VS)
    base = {k for k in range(0x40) if rows[0]['pool'][k * 0x100 + 0x40:k * 0x100 + 0x42] != b'\0\0'}
    out = []
    for r in rows:
        objs = []
        for k in range(0x40):
            o = r['pool'][k * 0x100:(k + 1) * 0x100]
            if k in base or not cap.u32(o, 0x94): continue
            ob = cap.obj(r, 0x100000 + k * 0x100)
            objs.append([k, ob['anim'], ob['step'], ob['x'], ob['y'], ob['flags'] >> 1 & 1, ob['ptr'], ob['name'].strip()])
        a, b = (0x108400, 0x108200) if sw else (0x108200, 0x108400)
        out.append([fighter(r, a), fighter(r, b), objs, r['snd']])
    return out

def anims_of(fr, i=0):
    seen = []
    for f in fr:
        if f[i][0] not in seen: seen.append(f[i][0])
    return seen

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else OUT
    names = sys.argv[2:] or list(RECIPES)
    data = json.load(open(path)) if os.path.exists(path) and sys.argv[2:] else {}
    for k in names:
        fr = capture(k)
        data[k] = {'recipe': RECIPES[k], 'frames': fr}
        print(k, [hex(a) for a in anims_of(fr)], 'P2', [hex(a) for a in anims_of(fr, 1)], 'objs', sorted({(o[1], o[7]) for f in fr for o in f[2]})[:6])
    json.dump(data, open(path, 'w'))
