#!/usr/bin/env python3
"""A fighter's move catalogue (Kim's first): every animation of his table (ROM) and every move (an input, what it plays, measured in our
emulator) with its metadata.

    python3 catalogue_kz.py [--char NAME] [OUT.json]      (default Kim: /data/neogeo_dict/kizuna/kim_moves.json;
                                                           fighters_kz.path(NAME, 'moves'))

Per animation (ROM, kz.parse_anim): steps [ticks, sprite defs, part offsets, boxes in force (a step's trailer bit 4
keeps the previous step's), sound word, command: stop / move / velocity / acceleration / spawn], frames (sum of ticks),
first / last attack step.
Per move (kim_capture.json recipes): the input, where it comes from (the ROM command list $604D0[5], the buttons, a
chain), the animations it plays, frames until idle, startup / active / recovery from the attack boxes in force,
the hits (P2's life drops: damage, P2's reaction animation), Kim's travel (dx, highest point), the objects it spawns
(projectiles and effects: name, animation), the sound commands it sends (prefix + code, frame), cancel windows
(cancels_kz.json)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import kz, commands_kz, fighters_kz as FK
CH = 5
CAP = '/data/neogeo_dict/kizuna/kim_capture.json'
OUT = '/data/neogeo_dict/kizuna/kim_moves.json'
IDLE = {0xA0, 0x0}
NONMOVE = (7, 0xA3, 1, 2, 9, 0xA, 0xB, 0x81, 0x82)     # Kim's numbers: crouch, walks, jumps, landing (not a move start)
def setup(name):
    """another fighter: its id, files, idle / non-move animations (Kim's moved through the state map)"""
    global CH, CAP, OUT, IDLE, NONMOVE
    CH = FK.CAST[name]; CAP = FK.path(name, 'capture'); OUT = FK.path(name, 'moves')
    IDLE = {FK.kim_anim(CH, 0xA0), 0x0}; NONMOVE = tuple(FK.kim_anim(CH, a) for a in NONMOVE)

def anim_info(n):
    st = kz.parse_anim(CH << 12 | n)
    steps, boxes, frames, atk = [], [], 0, []
    for i, s in enumerate(st):
        if s['boxes'] is not None: boxes = s['boxes']
        elif not s['trailer'] & 0x10 and not s['nboxes']: boxes = []
        live = [b for b in boxes if b[0] >= 0x10 and b[0] not in (0x27, 0x33)]
        if live: atk.append(i)
        cmd = None
        if s['cmd']:
            a = s['args']; nm = kz.CMD_NAMES.get(s['cmd'], f"cmd{s['cmd']}")
            if s['cmd'] in (5, 6): cmd = [nm, kz.sw(a[0] << 8 | a[1]), kz.sw(a[2] << 8 | a[3])]
            elif s['cmd'] in (9,): cmd = [nm, kz.sw(a[0] << 8 | a[1]) / 256, kz.sw(a[2] << 8 | a[3]) / 256]
            elif s['cmd'] in (3, 4, 17, 18): cmd = [nm, kz.sb(a[0]) * 2, kz.sb(a[1]) * 2, a[2] << 8 | a[3]]
            elif s['cmd'] in (7, 8): cmd = [nm, kz.sb(a[0]) * 2, kz.sb(a[1]) * 2, kz.sb(a[2]) * 2, kz.sb(a[3]) * 2, a[4] << 8 | a[5]]
            else: cmd = [nm] + [kz.sw(a[k] << 8 | a[k + 1]) for k in range(0, len(a), 2)]
        steps.append({'addr': s['addr'], 'ticks': s['ticks'], 'defs': s['defs'], 'offs': s['offs'],
                      'boxes': [list(b) for b in boxes], 'sound': s['sound'], 'cmd': cmd, 'trailer': s['trailer']})
        frames += s['ticks']
    return {'n': n, 'steps': steps, 'end': st[-1]['end'], 'frames': frames, 'attack_steps': atk}

def runs(rows, i=0, key=0):
    out = []
    for f in rows:
        v = f[i][key]
        if out and out[-1][0] == v: out[-1][1] += 1
        else: out.append([v, 1])
    return out

def move_info(rec, frames, A, step_boxes):
    p1 = [f[0] for f in frames]
    start = next((i for i, p in enumerate(p1) if p[0] not in IDLE and p[0] not in NONMOVE), None)
    if start is None: return None
    end = next((i for i in range(start, len(p1)) if p1[i][0] in IDLE), len(p1))
    anims = []
    for p in p1[start:end]:
        if p[0] not in anims: anims.append(p[0])
    live = [i - start for i in range(start, end) if any(b[0] >= 0x10 and b[0] not in (0x27, 0x33) for b in step_boxes.get(p1[i][5], []))]
    hits, prev = [], frames[start][1][6]
    for i in range(start, len(frames)):
        l = frames[i][1][6]
        if l < prev: hits.append({'frame': i - start, 'damage': prev - l, 'p2_anim': frames[min(i + 1, len(frames) - 1)][1][0]})
        prev = l
    x0, y0 = p1[start][2], p1[start][3]
    objs = {}
    for i in range(start, end):
        for o in frames[i][2]:
            objs.setdefault((o[1], o[7].strip('\0 ')), i - start)
    snd = []
    for i in range(start, end):
        for v in frames[i][3] if len(frames[i]) > 3 else []: snd.append([i - start, v])
    pairs, k = [], 0
    while k < len(snd):                                  # prefix + code pairs as the game sends them
        if snd[k][1] in (0x18, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E) and k + 1 < len(snd):
            pairs.append({'frame': snd[k][0], 'word': f'{snd[k][1]:02X}{snd[k + 1][1]:02X}'}); k += 2
        else: pairs.append({'frame': snd[k][0], 'word': f'{snd[k][1]:02X}'}); k += 1
    return {'anims': [f'{a:X}' for a in anims], 'frames': end - start,
            'startup': live[0] + 1 if live else None, 'active': len(live), 'recovery': (end - start - 1 - live[-1]) if live else None,
            'hits': hits, 'damage': sum(h['damage'] for h in hits),
            'dx': p1[end - 1][2] - x0, 'height': max(p[3] for p in p1[start:end]) - y0,
            'path': [[p[2] - x0, p[3] - y0] for p in p1[start:end]],
            'objects': [{'anim': f'{a:04X}', 'name': nm, 'frame': f} for (a, nm), f in sorted(objs.items(), key=lambda kv: kv[1])],
            'sounds': pairs}

MOVE_SOURCES = {
    'idle': 'stand', 'walk_fwd': 'hold 6', 'walk_back': 'hold 4', 'run': '66', 'backdash': '44', 'crouch': 'hold 2',
    'jump_up': '8', 'jump_fwd': '9', 'jump_back': '7',
    'far_a': 'A (far)', 'far_b': 'B (far)', 'far_c': 'C (far)', 'close_a': 'A (close)', 'close_b': 'B (close)', 'close_c': 'C (close)',
    'crouch_a': '2A', 'crouch_b': '2B', 'crouch_c': '2C', 'jump_a': 'j.A (up)', 'jump_b': 'j.B (up)', 'jump_c': 'j.C (up)',
    'jump_fwd_a': 'j.A (fwd)', 'jump_fwd_b': 'j.B (fwd)', 'jump_fwd_c': 'j.C (fwd)',
    'fwd_a': '6A', 'fwd_b': '6B', 'fwd_c': '6C (far)', 'df_a': '3A', 'df_b': '3B', 'df_c': '3C',
    'ab': 'AB', 'cd': 'CD', 'bc': 'BC', 'throw_fc': '6C (throw)', 'throw_bc': '4C (throw)',
    'chain_abc': 'close A > B > C (chain)', 'chain_ac': 'close A > C (chain)', 'chain_bc': 'close B > C (chain)',
}

def build():
    cap = json.load(open(CAP))
    A = {}
    for n in range(0, kz.anim_count(CH)):
        try: A[n] = anim_info(n)
        except Exception as e: A[n] = {'n': n, 'error': str(e)}
    step_boxes = {s['addr']: s['boxes'] for a in A.values() for s in a.get('steps', [])}
    cmds = {f"cmd_{c['notation']}": c for c in commands_kz.commands(CH)}
    moves = {}
    for rec, d in cap.items():
        if rec.startswith('react_'): continue
        mi = move_info(rec, d['frames'], A, step_boxes)
        if mi is None: continue
        base = rec.replace('_near', '').replace('_air', '').replace('_low', '')
        c = cmds.get(base)
        mi.update({'recipe': rec, 'p1_input': d['recipe'][1], 'p2_x': d['recipe'][0],
                   'input': (c['notation'] + (' (air)' if rec.endswith('_air') else '') + (' (life <= 96)' if '_low' in rec else '')) if c else MOVE_SOURCES.get(rec, rec),
                   'rom_command': {'entry': f"{c['entry']:06X}", 'pattern': f"{c['pattern']:06X}", 'cond': f"{c['cond']:04X}",
                                   'command': f"{c['command']:02X}"} if c else None})
        moves[rec] = mi
    react = {}
    for rec, d in cap.items():
        if not rec.startswith('react_'): continue
        rs = runs(d['frames'])
        react[rec] = {'anims': [f'{a:X}' for a, _ in rs if a not in IDLE], 'runs': [[f'{a:X}', n] for a, n in rs]}
    used = {}
    for rec, m in moves.items():
        for a in m['anims']: used.setdefault(a, []).append(rec)
    for rec, m in react.items():
        for a in m['anims']: used.setdefault(a, []).append(rec)
    smap = kz.u32(0x69118 + 4 * CH)
    states = {}
    for s in range(0x1E0):
        a = kz.u16(smap + 2 * s) & 0xFFF
        if a: states.setdefault(f'{a:X}', []).append(f'{s:X}')
    return {'character': f'{FK.NAMES[CH]} (character {CH})', 'anim_table': f'{kz.anim_table(CH):06X}',
            'anim_count': kz.anim_count(CH) - 1, 'state_map': f'{smap:06X}',
            'commands': [{'notation': c['notation'], 'cond': f"{c['cond']:04X}", 'command': f"{c['command']:02X}",
                          'steps': c['steps']} for c in commands_kz.commands(CH)],
            'animations': {f'{n:X}': {**a, 'used_by': used.get(f'{n:X}', []), 'states': states.get(f'{n:X}', [])} for n, a in A.items()},
            'moves': moves, 'reactions': react}

if __name__ == '__main__':
    av = sys.argv[1:]; name = 'kim'
    if '--char' in av: i = av.index('--char'); name = av[i + 1]; setup(name); del av[i:i + 2]
    out = av[0] if av else OUT
    cat = build()
    canc = FK.path(name, 'cancels')
    if os.path.exists(canc): cat['cancels'] = json.load(open(canc))
    json.dump(cat, open(out, 'w'), indent=0)
    A = cat['animations']
    print('animations', len(A), 'with steps', sum(1 for a in A.values() if a.get('steps')), 'used by a capture',
          sum(1 for a in A.values() if a.get('used_by')), 'in the state map', sum(1 for a in A.values() if a.get('states')))
    for k, m in cat['moves'].items():
        print(f"{k:22s} {m['input']:26s} {','.join(m['anims']):18s} f{m['frames']:3d} su{m['startup']} act{m['active']} "
              f"hits{len(m['hits'])} dmg{m['damage']} dx{m['dx']} h{m['height']} objs{len(m['objects'])} snd{[s['word'] for s in m['sounds']]}")
