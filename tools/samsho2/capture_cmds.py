#!/usr/bin/env python3
"""Every command-list entry of one fighter played in our emulator (one run, the vs state reloaded for each entry):
per frame the P1 / P2 objects and the display list, the sound commands. -> /data/neogeo_dict/samsho2/moves/CC.json
    python3 capture_cmds.py CHAR [--close] [--extra 'name:SEQ' ...]
P1 = CHAR (state cap/p1_CC.state, P2 Haohmaru 160 px away, both idle); throws ('throw' entries) with P2 poked to 56 px."""
import os, sys, json, glob, re
import cap_ss2 as C, commands_ss2 as K, ss2

SEG = 240; LEAD = 12
RAGE = False
STA = '/data/neogeo_dict/samsho2/cap'
OUT = '/data/neogeo_dict/samsho2/moves'

def seq_for(e, hold=3):
    """input lane for an entry: directions `hold` frames each, the button step pressed with the last direction;
    a charge first step (b4 bit 0) held its window + 4 frames"""
    steps = e['steps']; lane = []
    for k, (m, v, fr) in enumerate(steps):
        d = v & 15 if m & 15 else 0
        s = ('U' if d & 1 else '') + ('D' if d & 2 else '') + ('L' if d & 4 else '') + ('R' if d & 8 else '')
        b = ''.join(n for k2, n in ((0x10, 'a'), (0x20, 'b'), (0x40, 'c'), (0x80, 'd')) if v & k2 and m & 0xF0)
        if b and not s and lane and k == len(steps) - 1 and lane[-1][1] not in ('-',) and not (m & 15):
            s = lane[-1][1]                                   # a button-only last step: keep the last direction
        n = hold
        if k == 0 and e['charge'] and fr: n = fr + 4
        lane.append([n, (s + b) or '-'])
    return ','.join(f'{n}:{x}' for n, x in lane)

def run_char(char, extra=(), state=None):
    state = state or f'{STA}/p1_{char:02d}.state'
    ents = K.command_list(char)
    jobs = [(f"cmd{e['i']}", seq_for(e), e) for e in ents] + [(n, s, None) for n, s in extra]
    # locate the players in this state (1-frame run)
    d0 = '/data/tmp/samsho2/cc_probe'; C.run(d0, '3:-', load=state, vram=False, sndlog=False)
    r = C.ram(d0, 1); a1, a2 = C.players(r)
    res = []
    for c0 in range(0, len(jobs), 6):                      # RAMDUMP lists stay under the 128 KB env-string limit
        res += _run_chunk(jobs[c0:c0 + 6], state, r, a1, a2, char)
    return res

def _run_chunk(jobs, state, r, a1, a2, char):
    import subprocess
    lanes = []; pokes = []; reload = []
    for j, (name, sq, e) in enumerate(jobs):
        base = j * SEG; reload.append(base)
        body = f'{LEAD}:-,{sq}'
        n = C.nframes(body); lanes.append(body + f',{SEG - n}:-')
        if (e and e['kind'] == 'throw') or (not e and name.startswith('close_')):   # P2 next to P1: P2 world x = P1 x + 56
            x = C.s16(r, a1 - 0x100000 + 0x4E) + 56
            pokes.append(f'{base + 1}:{a2 + 0x4E:X}={x >> 8 & 255:02X},{a2 + 0x4F:X}={x & 255:02X}')
        if not e and 'unarmed' in name:                     # +$F4 = 1: the weapon-less mode (its own action tables)
            pokes.append(';'.join(f'{base + k}:{a1 + 0xF4:X}=01' for k in range(1, 4)))
        if RAGE or (not e and 'rage' in name):              # +$F0 = 32: the rage state the type-13 entries test
            pokes.append(';'.join(f'{base + k}:{a1 + 0xF0:X}=20' for k in range(1, 4)))
    seq = ','.join(lanes); total = C.nframes(seq)
    out = f'/data/tmp/samsho2/cc{char:02d}'; os.makedirs(out, exist_ok=True)
    for f in glob.glob(f'{out}/cap.txt*'): os.remove(f)
    rd = ';'.join(f'{f}:{a1:X}:120;{f}:{a2:X}:120;{f}:101000:1000' for f in range(total))
    env = dict(os.environ, SEQ=seq, SEQ2=f'{total}:-', OUT=f'{out}/cap.txt', LOAD=state, RAMDUMP=rd, SNDLOG=f'{out}/snd.txt')
    if len(reload) > 1: env.update(RELOAD=','.join(map(str, reload[1:])), RELOAD_STATE=state)
    if pokes: env['POKE'] = ';'.join(pokes)
    subprocess.run([C.NGSDL, C.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=7200)
    snd = {}
    for line in open(f'{out}/snd.txt'):
        f, v = int(line[:5]), int(line[6:8], 16); snd.setdefault(f, []).append(v)
    res = []
    for j, (name, sq, e) in enumerate(jobs):
        base = j * SEG; rows = []
        for f in range(base + 1, base + SEG):
            o1 = parse_hex(f'{out}/cap.txt.ram{f}_{a1:06X}'); o2 = parse_hex(f'{out}/cap.txt.ram{f}_{a2:06X}')
            dl = parse_hex(f'{out}/cap.txt.ram{f}_101000')
            if o1 is None: continue
            rows.append(dict(f=f - base, p1=obj_row(o1), p2=obj_row(o2), dl=dl_defs(dl, a1, a2), snd=snd.get(f, [])))
        res.append(dict(name=name, seq=f'{LEAD}:-,{sq}', entry=e, rows=rows))
    for f in glob.glob(f'{out}/cap.txt.ram*'): os.remove(f)
    return res

def parse_hex(p):
    if not os.path.exists(p): return None
    return bytes.fromhex(open(p).read().strip())

def obj_row(o):
    g = lambda k: o[k]
    return dict(t=C.u16(o, 0x64), a=C.u16(o, 0x66), st=C.u32(o, 0x6C), x=C.s16(o, 0x4E), y=C.s16(o, 0x50),
                cls=g(230), sub=g(231), mode=g(244), face=g(0x7F), flags=C.u16(o, 0x74), s249=g(249))

def dl_defs(dl, a1, a2):
    """display entries as (def, x, y, flip, pal) relative to the list ($32D0 walk), the fighters' and the others'"""
    out = []; a = 0; seen = set()
    while True:
        a = C.u16(dl, a + 2) - 0x1000
        if a in seen or not 0 <= a < 0x1000: break
        seen.add(a)
        if C.u16(dl, a + 4) == 0xFFFF: break
        out.append((C.u16(dl, a + 0x18), C.s16(dl, a + 0x10), C.s16(dl, a + 0x12), dl[a + 0x1C], dl[a + 0x1D], C.u16(dl, a + 4)))
    return out

if __name__ == '__main__':
    char = int(sys.argv[1])
    RAGE = '--rage' in sys.argv
    extra = []
    if '--extra' in sys.argv:
        for x in sys.argv[sys.argv.index('--extra') + 1:]:
            n, s = x.split('=', 1); extra.append((n, s))
    if '--normals' in sys.argv:
        for b in ('a', 'b', 'ab', 'c', 'd', 'cd'):
            extra += [(f'far_{b}', f'3:{b}'), (f'close_{b}', f'3:{b}'), (f'crouch_{b}', f'6:D,3:D{b}'),
                      (f'jump_{b}', f'3:UR,14:-,3:{b}')]
        extra += [('close_throw_6ab', '6:R,3:Rab'), ('close_throw_6d', '6:R,3:Rd'), ('close_throw_6cd', '6:R,3:Rcd'),
                  ('walk_f', '40:R'), ('walk_b', '40:L'), ('dash_f', '2:R,2:-,30:R'), ('back_step', '2:L,2:-,3:L'),
                  ('jump_u', '3:U'), ('jump_f', '3:UR'), ('unarmed_idle', '30:-'), ('unarmed_a', '3:a'), ('unarmed_c', '3:c')]
    res = run_char(char, extra)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(f'{OUT}/{char:02d}{"_rage" if RAGE else ""}.json', 'w'))
    for m in res:
        seqa = []
        for r in m['rows']:
            k = (r['p1']['cls'], r['p1']['sub'], r['p1']['a'])
            if not seqa or seqa[-1][0] != k: seqa.append([k, r['f']])
        print(m['name'], m['entry']['notation'] if m['entry'] else m['seq'], ' '.join(f"{c}/{s}:a{a}@{f}" for (c, s, a), f in seqa[:12]))
