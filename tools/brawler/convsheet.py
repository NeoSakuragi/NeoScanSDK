#!/usr/bin/env python3
"""Brawler move vocabulary (TODO #142 step 1): one code path that reads every fighter's exported moves, whatever the
source (KOF96 / 98 / 99 ROM programs, Kizuna / SS4 / WHP / KOF captures), and writes

    vocab.json      the standard features (families, parameters, semantics, the mechanism implementing each today) with
                    the moves using each, counted per source game
    ruleset.json    the game-wide rules per source as the brawler implements them, the disagreements, options
    missing.json    every still-recorded move -> the enhancement / new component / analysis it needs; the debt plan
                    (which component retires the most recorded moves first)
    sheets/<fighter>_<input>.json + .md   conversion sheets: ROM code (68000, annotated) or "capture" -> what was
                    understood -> step mapping into standard features -> features used / missing -> ingestion class
                    (a covered / b enhancement + regression set / c new component) -> fidelity (existing proof outputs)

    python3 tools/brawler/convsheet.py [--out /data/tmp/vocab] [fighter:input ...]
        (default sheets: terry:623A ryo:23624C kim:236C haohmaru:421C)

Reads examples/brawler/build/{bm_spec.c, bm_chars.c, chainlab.json} and game.json (run `make` first), the KOF ROMs
through tools/kof96/handlers98.py for the ROM code excerpts, and the proof outputs under /data/tmp for fidelity.
Analysis only: it changes nothing in the game. docs/brawler_move_vocabulary.md explains the output."""
import glob, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
BUILD = os.path.join(ROOT, 'examples', 'brawler', 'build')
GAME_JSON = os.path.join(ROOT, 'examples', 'brawler', 'game.json')

# ---- the exported C data, parsed back (bm_chars.h struct layouts) ----------------------------------------------------
TOK = re.compile(r'\{|\}|-?0x[0-9A-Fa-f]+|-?\d+\.\d+|-?\d+|&?[A-Za-z_]\w*')
def c_value(s):
    """a C initializer -> nested lists (numbers as int, identifiers as str)"""
    stack = [[]]
    for t in TOK.findall(s):
        if t == '{': stack.append([])
        elif t == '}': v = stack.pop(); stack[-1].append(v)
        elif t[0].isdigit() or t[0] == '-': stack[-1].append(float(t) if '.' in t else int(t, 16) if 'x' in t else int(t))
        else: stack[-1].append(t.lstrip('&'))
    return stack[0][0]

DEF = re.compile(r'^(?:static )?const (\w+) (\w+)(?:\[\w*\])? = (.*);$')
def c_tables(path, types=None):
    out = {}
    for line in open(path):
        if not line.startswith(('static const', 'const')): continue
        m = DEF.match(line.rstrip('\n'))
        if m and (types is None or m.group(1) in types): out[m.group(2)] = (m.group(1), c_value(m.group(3)))
    return out

def pad(v, n): return list(v) + [0] * (n - len(v))
def row_d(r):    # bspec_row_t
    r = pad(r, 10)
    return {'frame': r[0], 'x': r[1], 'y': r[2], 'atk': r[3], 'hit': r[4], 'dmg': r[5],
            'obj': [dict(zip(('frame', 'x', 'y', 'same', 'react', 'box'), o)) for o in r[6]], 'vx': r[7], 'vy': r[8], 'fx': r[9]}
def step_d(s):   # bstep_t
    return dict(zip(('frame', 'ticks', 'flags', 'hurt', 'atk', 'dx', 'hy'), s))
PJ_F = ('nrows', 'loop', 'nend', 'kind', 'spawn_row', 'react', 'fx', 'follow', 'spawn_x', 'spawn_y', 'wrap_x', 'rows', 'end',
        'child', 'child_b0', 'child_b1', 'child_period', 'sig', 'child_dx', 'child_dy')
SP_F = ('nrows', 'inv_rows', 'nparts', 'nproj', 'rows', 'proj', 'prog', 'anims', 'robj', 'parts', 'links', 'nlinks',
        'bd_first', 'bd_end', 'bd_col')

P = dict(ANIM=1, SET=2, MUL=3, MOVE=4, FRICMOVE=5, FALL=6, NUDGE=7, DEC=8, BR=9, RESUME=10, RESUMEAT=11, JMP=12, SPAWN=13,
         FXOFF=14, END=15, ADV=16, CHECK=17, PART=18, EVCLR=19, ONHIT=20, PUT=21, HITCLR=22, HOLD=23, UNHOLD=24, SIGCLR=25,
         HITOFF=26)                                     # bm_chars.h P_*
PN = {v: k for k, v in P.items()}
PC = ['end', 'event', 'land', 'falling', 'cnt', 'hit', 'off', 'always', 'stepev', 'window', 'link', 'hitany', 'sig7',
      'sig7c', 'sig6', 'far', 'low']                   # bm_chars.h PC_*
REG = ['vx', 'vy', 'g', 'fric', 'cnt', 'h']
R = ['light', 'heavy', 'knockdown', 'launch', 'trip', 'blowback', 'slam', 'lift']   # fighter.h R_*
SLOTS = ['D', 'fD', 'dD', 'uD', 'dfD', 'ufD']           # game.json roster specials (BS_* order)

def load_moves():
    """every special of every fighter's pool as a move record (pool order = bm_spec.c order), with its slot"""
    cl = json.load(open(os.path.join(BUILD, 'chainlab.json')))
    roster = {r['name']: r for r in json.load(open(GAME_JSON))['roster']}
    T = c_tables(os.path.join(BUILD, 'bm_spec.c'))
    get = lambda name: T[name][1] if isinstance(name, str) and name in T else []
    moves = []
    for f in cl['fighters']:
        n, game = f['name'], f['game']
        specs = T[f'{n}_specials'][1]
        rs = roster.get(n, {})
        vmore = {}
        for key, vid, at in f['voices'].get('more', []): vmore.setdefault(key - 62, []).append(vid)   # VK_SPEC = 62
        for k, (pool, sp) in enumerate(zip(f['pool'], specs)):
            s = dict(zip(SP_F, pad(sp, len(SP_F))))
            inp = pool['input']
            slot = '+'.join([k_ for k_, v_ in (rs.get('specials') or {}).items() if v_ == inp] + (['fury'] if inp == rs.get('fury') else [])) or None
            anims = [[step_d(st) for st in get(a[2])] if len(a) > 2 else [] for a in get(s['anims'])] if s['prog'] else []
            anim_hold = [a[1] for a in get(s['anims'])] if s['prog'] else []
            def pj(name):
                return [dict(zip(PJ_F, pad(p, len(PJ_F)))) for p in get(name)]
            moves.append({'fighter': n, 'game': game, 'input': inp, 'slot': slot, 'index': k,
                          'kind': 'rom' if s['prog'] else 'recorded', 'nrows': s['nrows'], 'inv_rows': s['inv_rows'],
                          'rows': [row_d(r) for r in get(s['rows'])], 'proj': pj(s['proj']), 'robj': pj(s['robj']),
                          'prog': [tuple(pad(o, 4)) for o in get(s['prog'])], 'anims': anims, 'anim_hold': anim_hold,
                          'parts': [dict(zip(('first', 'end', 'next'), p)) for p in get(s['parts'])],
                          'links': [dict(zip(('from', 'to', 'trig', 'in', 'dir', 'at', 'lo', 'hi'), l)) for l in get(s['links'])],
                          'bd': (s['bd_first'], s['bd_end']) if s['bd_end'] else None, 'vmore': len(vmore.get(k, [])),
                          'hit_sfx': (rs.get('hit_sfx') or {}).get(inp)})
    return cl, roster, moves

def throws_of():
    """fighter -> number of throws with rows (bm_chars.c bthrow_t)"""
    out = {}
    for line in open(os.path.join(BUILD, 'bm_chars.c')):
        m = re.match(r'^static const bthrow_t (\w+)_throws\[\w*\] = (.*);$', line.rstrip('\n'))
        if m: out[m.group(1)] = sum(1 for t in c_value(m.group(2)) if t and t[0])
    return out

# ---- per move facts (what the exported data actually does) -----------------------------------------------------------
def hit_steps(mv):
    """ROM move: [(anim index, step index, step)] of steps whose attack box is live"""
    return [(a, i, s) for a, st in enumerate(mv['anims']) for i, s in enumerate(st) if s['flags'] & 1]

def facts(mv):
    ops = mv['prog']; codes = [o[0] for o in ops]
    br = [PC[o[1] & 0x7F] for o in ops if o[0] == P['BR'] and (o[1] & 0x7F) < len(PC)]
    sets = {REG[o[1]] for o in ops if o[0] == P['SET'] and o[1] < len(REG)}
    rows = mv['rows']
    f = {'codes': set(codes), 'br': set(br), 'sets': sets}
    if mv['kind'] == 'rom':
        hs = hit_steps(mv)
        f['hits'] = sum(1 for a, i, s in hs if not (i and mv['anims'][a][i - 1]['flags'] & 1 and mv['anims'][a][i - 1]['flags'] & 16))
        f['catch'] = any(s['flags'] & 64 for a, i, s in hs)
        f['nostop'] = any(s['flags'] & 128 for a, i, s in hs)
        f['noslide'] = any(s['flags'] & 4 for a, i, s in hs)
        f['samehit'] = any(s['flags'] & 16 for a, i, s in hs)
        f['packed'] = any(s['hy'] > 15 for a, i, s in hs)
        f['stepdx'] = any(s['dx'] for st in mv['anims'] for s in st)
        f['event'] = any(s['flags'] & 8 for st in mv['anims'] for s in st)
        f['window'] = any(s['flags'] & 32 for st in mv['anims'] for s in st)
        f['nohurt'] = any(not s['flags'] & 2 for st in mv['anims'] for s in st)
        f['hold_last'] = any(mv['anim_hold'])
        f['reacts'] = sorted({R[(o[2] >> 8) & 7] for o in ops if o[0] == P['ANIM'] and f['hits']} |
                             {R[s['hy'] & 7] for a, i, s in hs if s['hy']} | {R[(s['hy'] >> 4) & 7] for a, i, s in hs if s['hy'] > 15})
        f['fx'] = sorted({o[3] & 0x3F for o in ops if o[0] == P['ANIM']}); f['burn'] = any(o[3] >> 6 for o in ops if o[0] == P['ANIM'])
        objs = mv['robj']
    else:
        f['hits'] = sum(1 for r in rows if r['hit'] & 2)
        f['carry'] = any(r['hit'] & 4 and r['vy'] for r in rows) or any(r['hit'] & 4 for r in rows if not r['hit'] & 2)
        f['contact'] = any(r['hit'] & 8 for r in rows)
        f['cont'] = any(r['hit'] & 16 for r in rows)
        f['slide'] = any(r['hit'] & 2 and not r['hit'] & 4 and r['vx'] for r in rows)
        f['path_air'] = any(r['y'] > 0 for r in rows)
        f['path_x'] = any(r['x'] for r in rows)
        f['reacts'] = sorted({R[(r['hit'] >> 5) & 7] for r in rows if r['hit'] & 2})
        f['fx'] = sorted({r['fx'] & 0x3F for r in rows if r['hit'] & 2}); f['burn'] = any(r['fx'] >> 6 for r in rows if r['hit'] & 2)
        f['script_obj'] = any(o['frame'] != 0xFFFF for r in rows for o in r['obj'])
        f['script_obj_box'] = any(o['frame'] != 0xFFFF and o['box'][2] for r in rows for o in r['obj'])
        objs = mv['proj']
    f['travel'] = any(o['kind'] == 1 for o in objs)
    f['erupt'] = any(o['kind'] == 3 and not (o['follow'] & 1) for o in objs)
    f['pinned'] = any(o['follow'] & 1 for o in objs)
    f['trail'] = any(o['child'] for o in objs)
    f['sig'] = any(o['sig'] for o in objs)
    f['loop'] = any(o['loop'] != 255 for o in objs)
    f['nobj'] = len(objs)
    f['variants'] = variant_tests(mv) if mv['slot'] else []
    return f

def slots(mv): return (mv['slot'] or '').split('+')
def variant_tests(mv):
    """a ROM move: the input fields its handler branches on (button +$1A4 / EX flag +$1D6): it has variants"""
    if mv['kind'] != 'rom': return []
    try:
        H, export96, m = kof_env(mv['game'])
        cid = {'kof96': export96.CAST, 'kof98': export96.CAST98, 'kof99': export96.CAST99}[mv['game']].index(mv['fighter'])
        h, b = H.handler_of(cid, mv['input'], game=mv['game'])
        dec = H.Decoder(m); dec.trace = []
        H.decode(m, h, b, mv['input'].startswith('EX '), dec=dec, cid=cid)
        return sorted({x['test'].split(' (')[0] for x in branches(dec.trace, h) if x['variant']})
    except Exception: return []
def mid(mv): return f"{mv['fighter']}:{mv['input']}"
def label(mv): return f"{mv['fighter']} {mv['input']}" + (f" [{mv['slot']}]" if mv['slot'] else '')

# ---- the standard features --------------------------------------------------------------------------------------------
# (family, name, parameters [(name, type, range)], semantics, implemented by today, detector over facts / move)
FEATURES = [
 ('animation', 'anim.play', [('anim', 'animation id', 'the fighter\'s banks'), ('speed', '8.8 fixed', '0x40-0x400')],
  'Plays an animation: frames with per-step durations (ticks + 1 frames), hurt box per step.',
  'P_ANIM + banim_t/bstep_t (ROM moves); bspec_row_t.frame per row (recorded moves); rnode_t.speed (normals)',
  lambda mv, f: True),
 ('animation', 'anim.hold_last', [('anim', 'animation id', '')], 'The animation stays on its last step until the move code moves on.',
  'banim_t.hold', lambda mv, f: mv['kind'] == 'rom' and f['hold_last']),
 ('animation', 'anim.event_marker', [('step', 'int', 'step index')],
  'A step flagged as the move\'s event: timing point for spawns / part switches (KOF $0080).',
  'bstep_t flags 8, PC_EVENT / PC_STEPEV, P_EVCLR', lambda mv, f: mv['kind'] == 'rom' and f['event']),
 ('animation', 'anim.no_hurt_step', [('steps', 'step range', '')],
  'Steps without a hurt box: intrinsic invulnerability of the animation (nothing to hit).',
  'bstep_t flags bit 1 clear (combat() skips the victim)', lambda mv, f: mv['kind'] == 'rom' and f['nohurt']),
 ('movement', 'move.velocity', [('vx', 'px/frame 16.16', '-16..16'), ('vy', 'px/frame 16.16', '-16..20')],
  'Sets the body\'s velocity; applied each frame by move / fall.', 'P_SET vx/vy + P_MOVE', lambda mv, f: 'vx' in f['sets'] or 'vy' in f['sets']),
 ('movement', 'move.friction', [('fric', '0.16 multiplier', '0..1')], 'vx scaled each frame (decelerating rush).',
  'P_SET fric + P_FRICMOVE, P_MUL', lambda mv, f: bool({P['FRICMOVE'], P['MUL']} & f['codes'])),
 ('movement', 'move.gravity', [('g', 'px/frame^2 16.16', '0..3')], 'Height += vy, vy -= g each frame; lands at 0.',
  'P_SET g + P_FALL, PC_LAND / PC_FALL', lambda mv, f: P['FALL'] in f['codes']),
 ('movement', 'move.nudge', [('dx', 'px', '-64..64'), ('dy', 'px', '-64..64')], 'An instant displacement.',
  'P_NUDGE; P_SET h', lambda mv, f: P['NUDGE'] in f['codes'] or 'h' in f['sets']),
 ('movement', 'move.step_offset', [('dx', 'px per step', '-64..64')], 'A step moves the body forward as it starts (KOF $FB).',
  'bstep_t.dx', lambda mv, f: mv['kind'] == 'rom' and f['stepdx']),
 ('movement', 'move.keyframed_path', [('rows', '[(frame, x, y)]', 'per frame')],
  'Position per frame from a recorded script (no physics). Captures only: to be replaced by the three above.',
  'bspec_row_t.x / .y (special_update)', lambda mv, f: mv['kind'] == 'recorded' and (f['path_x'] or f['path_air'])),
 ('attack', 'hit.box', [('box', 'x,y,w,h px', ''), ('damage', 'int', '0..60'), ('reaction', 'enum R_*', '8 values'),
                        ('fx', 'hit kind 0..32', 'sound'), ('burn', '0..2', '')],
  'A live attack box; a new hit opens with damage, reaction, hit sound / burn.',
  'bstep_t.atk + flags 1 (ROM, P_ANIM b = damage | reaction << 8, v = fx); bspec_row_t.atk / hit / dmg / fx (recorded)',
  lambda mv, f: f['hits'] > 0),
 ('attack', 'hit.multi', [('hits', 'int', '2..20')], 'Several hits in one move; same-hit steps chain one hit over several steps.',
  'a new hit per active step (unless the step before has $4000, bstep_t flags 16); bspec_row_t.hit bit 1', lambda mv, f: f['hits'] > 1),
 ('attack', 'hit.reaction_by_height', [('standing', 'R_*', ''), ('airborne', 'R_*', '')],
  'The victim\'s reaction depends on whether it is standing or juggled (KOF\'s reaction table by attack box).',
  'bstep_t.hy packed standing | juggled << 4 (fighter_hit)', lambda mv, f: mv['kind'] == 'rom' and f['packed']),
 ('attack', 'hit.no_stop', [], 'A hit with no hit-stop for either side; the victim reels in place (barrages, KOF class 4).',
  'bstep_t flags 128', lambda mv, f: mv['kind'] == 'rom' and f['nostop']),
 ('attack', 'hit.slide', [('px', 'int', '0..127 or none')], 'How far a reel slides the victim (0 = in place).',
  'bstep_t flags 4 (no slide); bspec_row_t.vx (recorded reel slide)', lambda mv, f: f.get('noslide') or f.get('slide')),
 ('attack', 'hit.burn', [('colour', '1 purple / 2 orange', '')], 'The victim shows a burn palette until it lands.',
  'fx bits 6-7 -> set_burn', lambda mv, f: f['burn']),
 ('defence', 'inv.fury', [], 'Untouchable from the trigger to the end (hits, grabs, pushes).', 'INV_FURY (start_special, every fury)',
  lambda mv, f: 'fury' in slots(mv)),
 ('defence', 'inv.reversal', [('frames', 'int', '0..nrows')], 'Invincible for the first N frames (up to the last hit or apex).',
  'bspec_t.inv_rows, applied on the down+C slot only (fighter.c)', lambda mv, f: 'dD' in slots(mv)),
 ('spawn', 'spawn.projectile', [('def', 'library id', ''), ('row', 'frame', ''), ('offset', 'px', ''), ('react', 'R_*', '')],
  'A travelling object with its own attack box; its hit ends it (end rows play); one at a time; clashes.',
  'bproj_t kind 1 (proj / robj), P_SPAWN, proj_spawn', lambda mv, f: f['travel']),
 ('spawn', 'spawn.eruption', [('def', 'library id', ''), ('offset', 'px', '')],
  'An object that stays where it spawned and plays on after its hit (pillars, Power Geyser, Round Wave).',
  'bproj_t kind 3 not pinned', lambda mv, f: f['erupt']),
 ('spawn', 'spawn.pinned_effect', [('def', 'library id', ''), ('until', 'fxoff | last row', '')],
  'An effect attached to the fighter (Burn Knuckle\'s flame), ended by the move.', 'bproj_t.follow, P_FXOFF',
  lambda mv, f: f['pinned']),
 ('spawn', 'spawn.trail', [('child', 'library id', ''), ('period', 'frames', '')], 'An object that leaves child objects (no box).',
  'bproj_t.child / child_b0 / child_period', lambda mv, f: f['trail']),
 ('spawn', 'spawn.loop', [('from', 'row', ''), ('wrap', '1/8 px', '')], 'The object\'s flight repeats from a row, moving on each repeat.',
  'bproj_t.loop / wrap_x', lambda mv, f: f['loop']),
 ('spawn', 'spawn.signal', [('bits', 'end / hit', '')], 'The object signals its owner (end / hit) and the move branches on it.',
  'bproj_t.sig, PC_SIG7 / SIG7C / SIG6, P_SIGCLR', lambda mv, f: f['sig'] or bool({'sig7', 'sig7c', 'sig6'} & f['br'])),
 ('spawn', 'spawn.script_effect', [('rows', 'per frame', '')], 'Up to 2 effect objects placed per row from a recording.',
  'bspec_row_t.obj[2] (recorded)', lambda mv, f: mv['kind'] == 'recorded' and f['script_obj']),
 ('branch', 'branch.on_anim_end', [], 'Next phase when the animation ends.', 'P_BR PC_END', lambda mv, f: 'end' in f['br']),
 ('branch', 'branch.on_event', [], 'Next phase at the animation\'s event step.', 'P_BR PC_EVENT / PC_STEPEV',
  lambda mv, f: bool({'event', 'stepev'} & f['br'])),
 ('branch', 'branch.on_land', [], 'Next phase on landing / when falling starts.', 'P_BR PC_LAND / PC_FALL',
  lambda mv, f: bool({'land', 'falling'} & f['br'])),
 ('branch', 'branch.on_timer', [('frames', 'int', '0..255')], 'Next phase after N frames (a counter).', 'P_SET cnt, P_DEC, PC_CNT',
  lambda mv, f: 'cnt' in f['br']),
 ('branch', 'branch.on_hit', [('scope', 'this attack | any since clear', '')], 'Branch when the move connected.',
  'PC_HIT / PC_HITANY, P_HITCLR, P_HITOFF; bslink_t trig LK_HIT (parts)', lambda mv, f: bool({'hit', 'hitany'} & f['br']) or any(l['trig'] == 1 for l in mv['links'])),
 ('branch', 'branch.on_input', [('input', 'stick + button | again', ''), ('window', 'frames', ''), ('at', 'now | part end', ''), ('needs_hit', 'bool', '')],
  'A follow-up: a press inside a window switches to another part.',
  'P_CHECK / PC_LINK / PC_WINDOW / P_PART + bslink_t LK_IN (ROM), bspart_t / bslink_t (recorded)',
  lambda mv, f: bool({'link', 'window'} & f['br']) or P['CHECK'] in f['codes'] or any(l['trig'] & 2 for l in mv['links'])),
 ('branch', 'branch.on_distance', [('px', 'int', '0..400')], 'Branch on the opponent\'s distance.', 'PC_FAR (fighter_t.popp)',
  lambda mv, f: 'far' in f['br']),
 ('branch', 'branch.on_height', [('px', 'int', '0..255')], 'Branch on the body\'s height.', 'PC_LOW', lambda mv, f: 'low' in f['br']),
 ('branch', 'branch.on_offscreen', [], 'Branch when off screen.', 'PC_OFF', lambda mv, f: 'off' in f['br']),
 ('branch', 'branch.parts', [('parts', '[rows]', ''), ('next', 'part | end', '')], 'A move made of parts that chain.',
  'bspart_t (recorded), the program\'s own flow (ROM)', lambda mv, f: bool(mv['parts'])),
 ('hold', 'hold.catch', [('box', 'attack box', ''), ('dead', 'frames', '1..12'), ('routine', 'phase', '')],
  'A catch box: no damage, the victim is held, the move goes to its catch phase after dead frames.',
  'bstep_t flags 64, P_ONHIT, fighter_t.pcatch / pdead', lambda mv, f: mv['kind'] == 'rom' and (f['catch'] or P['ONHIT'] in f['codes'])),
 ('hold', 'hold.place', [('px', 'int', '0..127')], 'The caught victim put N px in front, facing the attacker.', 'P_PUT',
  lambda mv, f: P['PUT'] in f['codes']),
 ('hold', 'hold.held_reel', [], 'The held victim reels in place under every hit until let go.', 'P_HOLD / P_UNHOLD, PF_HOLD, HOLD_BOX',
  lambda mv, f: P['HOLD'] in f['codes']),
 ('hold', 'hold.contact_grab', [], 'A reach that catches without damage; the continuation hits.', 'bspec_row_t.hit bit 3 (recorded)',
  lambda mv, f: mv['kind'] == 'recorded' and f['contact']),
 ('hold', 'hold.carry', [('rows', '(x, y) per row', '')], 'The victim is placed per row relative to the attacker (recorded cinematic).',
  'bspec_row_t.hit bit 2 + vx / vy (recorded)', lambda mv, f: mv['kind'] == 'recorded' and f['carry']),
 ('variant', 'variant.parameter_set', [('variants', '[input -> parameter set]', 'light / heavy / EX light / EX heavy'),
                                       ('selector', 'button | EX flag', '')],
  'One behaviour (the program) with parameter sets chosen by the input that started it: KOF\'s handler tests the button '
  '(+$1A4), the EX flag (+$1D6) and a DM\'s MAX bit (+$E4 bit 0) and writes other speeds, timers, state / spawn tables, '
  'counts and damage ids (Double Dragon 1995: 4 per special).',
  'decoded, not played: handlers98.decode_variants forks at each selector test, export_rom stores every version '
  '(rom.variants); the game plays the slot\'s own button; the sheets list the versions side by side',
  lambda mv, f: bool(f.get('variants'))),
 ('presentation', 'fx.backdrop', [('rows', 'range', ''), ('colours', '2 x 16-bit', '')], 'The stage hidden, the backdrop alternating 2 colours.',
  'bspec_t.bd_* (main.c screen_fx)', lambda mv, f: bool(mv['bd'])),
 ('presentation', 'fx.voice_extra', [('voices', '[(id, at)]', '')], 'More than one voice line in a move.', 'bchar_t.vmore',
  lambda mv, f: mv['vmore'] > 0),
 ('presentation', 'fx.hit_sound_override', [('sfx', 'songs.json name', '')], 'The move\'s hits play a chosen sound instead of KOF\'s kind.',
  'game.json roster[].hit_sfx', lambda mv, f: bool(mv['hit_sfx'])),
]
# fighter-wide mechanisms (not per special): counted per fighter
FIGHTER_FEATURES = [
 ('attack', 'normal.route_node', [('move', 'BA_*', ''), ('weight', 'light | strong', ''), ('effect', 'none|knockdown|launch|trip|blowback', ''),
                                  ('damage', 'int', '0..255'), ('push', 'px', '-128..127'), ('speed', '8.8', '0x40-0x400'), ('links', 'RI_* -> node', '')],
  'A normal attack as a chain-route node (data: tools/brawler/routes/<fighter>.json).', 'rnode_t / rt_head_t, route_tab'),
 ('hold', 'hold.throw_script', [('rows', '(thrower frame, offset, victim pose, offset, flags) per frame', ''), ('speed', '8.8', '')],
  'A paired attacker / victim script with impacts (the walk-in throws C / D).', 'bthrow_t / bthrow_row_t, throw_update'),
 ('hold', 'hold.grab_hold', [('hits', 'int', '3'), ('time', 'frames', '90')], 'Walk into a standing enemy: hold, knee hits, throw, escape.',
  'S_GRAB / S_GRABBED, GRAB_* (hold_update)'),
 ('presentation', 'fx.meter_flash', [('frames', 'int', '4')], 'A breaker (a special out of a hit) costs 200 (else 12 life) and the sprite blinks white to its end; the red state (life <= 25 %) blinks red.', 'gmeter.blink'),
]

# ---- the ruleset (as implemented in the brawler, per source) ------------------------------------------------------------
RULESET = [
 {'rule': 'hit-stop', 'brawler_constant': 'HITSTOP 7 frames, both sides, every hit (fighter_hit); projectiles fly on',
  'sources': {'KOF98 ROM': 'class table by step flags bits 4-6 ($1DCCC, 7-11 frames in KOF); brawler: 7 for all, class 4 = 0 (bstep_t 128); a catch waits 1 + the class hit-stop (P_ONHIT a)',
              'KOF96 ROM': 'same engine, table $16E20 (class 4 and 6 = 0); brawler as KOF98',
              'KOF99 ROM': 'table $19832; brawler as KOF98',
              'KOF captured': 'game freezes removed from the recording, brawler 7 at its own hits',
              'Kizuna': 'freezes removed (export_kz frozen()), brawler 7', 'SS4': 'freezes removed, brawler 7', 'WHP': 'freezes removed, brawler 7'},
  'disagreement': 'KOF varies hit-stop by class (7-11, 0 for barrages); the brawler flattens to 7 + an exception flag; catch dead frames still follow KOF\'s class table',
  'options': ['A. one value (7) + no-stop flag, catch dead frames fixed (today minus the class table)',
              'B. three standard classes: none 0 / normal 7 / heavy 11 (finishers, furies, launchers), every source mapped onto them',
              'C. keep each source\'s table'],
  'recommend': 'B: designers get one knob with three values; KOF classes map directly, other sources take normal / heavy by reaction'},
 {'rule': 'hitstun / reel', 'brawler_constant': 'STUN_LIGHT 36, STUN_HEAVY 54 frames (react); special body hits add KOF98\'s reel 258 physics (5 frames still, slide 13.5 px x 0.828)',
  'sources': {'KOF ROM': 'kof_react R_HEAVY slide or none (bstep_t 4)', 'KOF captured': 'slide measured per hit (bspec_row_t.vx)',
              'Kizuna': 'reel, no slide data (react_of: launch / knockdown / heavy only)', 'SS4': 'brawler react() only', 'WHP': 'brawler react() only (no trip in WHP)',
              'normals': 'react(): push / 4 per node'},
  'disagreement': 'two reel models coexist: react() for normals and non-KOF specials, react() + kof_react slide for specials',
  'options': ['A. one reel: stun by weight (36 / 54) + slide px parameter per hit (default by weight)', 'B. KOF\'s reel physics for every hit', 'C. keep both'],
  'recommend': 'A: slide becomes a hit parameter (hit.slide), stun stays the beat \'em up length'},
 {'rule': 'reaction set', 'brawler_constant': 'R_LIGHT, HEAVY, KNOCKDOWN, LAUNCH, TRIP, BLOWBACK, SLAM, LIFT',
  'sources': {'KOF ROM': 'reaction table by attack box, standing | juggled (handlers98.box_react) + per move ROM_REACT; default last hit knockdown, others heavy',
              'KOF captured': 'measured on the victim (victim_reaction: heavy / knockdown / launch / trip)',
              'Kizuna': 'react_of: launch / knockdown / heavy', 'SS4': 'projectile knockdown; body hits: default knockdown', 'WHP': 'projectile heavy; no trip',
              'normals': 'rnode weight + effect (none / knockdown / launch / trip / blowback)'},
  'disagreement': 'how the reaction is chosen (table by box vs measured vs authored) and two physics: brawler react() vs KOF98 kof_react (specials only)',
  'options': ['A. authored per hit from the 8 R_* values, standing / airborne pair, one physics (KOF98\'s, measured)', 'B. authored per hit, brawler physics', 'C. per source'],
  'recommend': 'A: every importer writes the pair (hit.reaction_by_height); one physics table for all hits including normals'},
 {'rule': 'juggle', 'brawler_constant': 'falling knockdowns hittable with JUGGLE_BOX, no limit; KOF reaction physics: only launch 286 / 293 keep a hurt box (KM_HURT)',
  'sources': {'KOF ROM / captured': 'hittable only in launch states (KOF rule) after a special hit', 'Kizuna / SS4 / WHP': 'brawler rule: always hittable while falling, no limit',
              'normals': 'brawler rule'},
  'disagreement': 'unlimited juggles vs KOF\'s by-reaction rule; depends on which hit sent the victim up',
  'options': ['A. by reaction: launch / lift juggleable, knockdown / blowback / slam not', 'B. unlimited + juggle counter (e.g. 3 extra hits, then fall untouchable)', 'C. unlimited (today for most)'],
  'recommend': 'A + a counter cap of B: readable and stops infinite loops in a 4-player brawl'},
 {'rule': 'knockdown / getup', 'brawler_constant': 'GRAVITY_KD 0.31, DOWN_FRAMES 40, INV_GETUP 30, revive invincible 90',
  'sources': {'all': 'same for every source; KOF-reaction falls use KOF98 gravities (kof_fall) until the floor'},
  'disagreement': 'fall arc differs by who hit (normals: brawler gravity; specials: KOF98 per reaction)',
  'options': ['A. KOF98 reaction arcs for all hits', 'B. brawler arcs for all', 'C. keep'], 'recommend': 'A (follows the reaction rule)'},
 {'rule': 'damage scale', 'brawler_constant': 'life 60; normals per route node; special SPECIAL_DAMAGE 8 split over its hits; throw 12; hold hits 3; splash 6; +power per stage',
  'sources': {'KOF ROM / captured': '8 split (KOF damage tables dropped)', 'Kizuna': '8 split, except 6246A: Kizuna\'s life drop scaled 192 -> 60 (game_damage)',
              'SS4 / WHP': '8 split', 'furies': '8 split (same as a special)'},
  'disagreement': 'a fury deals what a special deals; Kizuna\'s desperation move uses source damage',
  'options': ['A. damage tiers: special 8, fury 16, throw 12, split over hits', 'B. source damage scaled to life 60', 'C. flat 8 (today)'],
  'recommend': 'A: designers pick a tier; sources only rank moves within a tier'},
 {'rule': 'guard / chip', 'brawler_constant': 'none: no block state, no chip damage',
  'sources': {'all originals': 'have guard and chip', 'brawler': 'none for any source'},
  'disagreement': 'none inside the brawler; every source differs from it',
  'options': ['A. no guard (beat \'em up)', 'B. enemies guard (AI), players do not', 'C. full guard + chip for specials'],
  'recommend': 'B (later): needs a guard reaction in the vocabulary; A until then'},
 {'rule': 'meter', 'brawler_constant': 'revamp 2: 3 stocks = 300, +1 per 4 frames; special 100 (else 6 life), breaker 200 (else 12 life, blinking), fury 300, MAX 300 in the red state (life <= 25 %) (players only)',
  'sources': {'KOF': 'power stocks / MAX dropped', 'Kizuna': 'desperation at life <= 96 dropped (421A, 6246A playable anytime)', 'SS4': 'rage / BUST conditions dropped', 'WHP': 'none'},
  'disagreement': 'source conditions (life-gated, stock) all replaced by one meter',
  'options': ['A. one meter (today)', 'B. one meter + optional life gate per fury', 'C. per source'], 'recommend': 'A'},
 {'rule': 'invincibility', 'brawler_constant': 'fury: whole move (INV_FURY); down+C slot: inv_rows (last hit or apex); getup 30; steps without hurt box (ROM anims)',
  'sources': {'KOF ROM': 'move\'s own hurt-box gaps kept + slot rule', 'captured (all)': 'hurt box from the frame\'s boxes + slot rule'},
  'disagreement': 'reversal invincibility belongs to the slot, not the move: the same move is vulnerable on another slot',
  'options': ['A. a move property inv.reversal (frames), any slot', 'B. slot rule (today)', 'C. only the source\'s hurt-box gaps'],
  'recommend': 'A: the move carries its invincibility; the slot only picks the move'},
 {'rule': 'push / bodies', 'brawler_constant': 'specials below 64 px push opponents to 32 px ahead (PUSH_DX); held victims share the push; normals push per node',
  'sources': {'KOF': 'push boxes and push-back not modelled (x off by up to 28 px in close proofs)', 'SS4': 'low leap held 30 px before the body (AIR_BLOCK_Y rule)', 'others': 'same PUSH_DX'},
  'disagreement': 'one approximate push vs per-game push boxes', 'options': ['A. PUSH_DX for all (today)', 'B. a push box per fighter', 'C. none'],
  'recommend': 'A (keep; it is already source-independent)'},
 {'rule': 'follow-up input timing', 'brawler_constant': 'press inside the window [lo, hi) rows or on P_CHECK frames; presses in hit-stop latched (phl)',
  'sources': {'KOF98': 'read 4 frames after the press (6 for forward+P)', 'KOF99': '5 frames', 'Kizuna': 'windows in script rows, again = same button', 'SS4 / WHP': 'no follow-ups exported'},
  'disagreement': 'input lag differs per source; KOF drops some presses right after hit-stop',
  'options': ['A. one buffer: a press counts for 8 frames before the window opens, through hit-stop', 'B. source lag', 'C. exact window only'],
  'recommend': 'A: one rule, lenient, players never lose a press to hit-stop'},
 {'rule': 'projectiles', 'brawler_constant': 'one at a time per thrower, both spent on a clash, gone off screen (-64 / 384 px), hit ends a travelling one',
  'sources': {'all': 'KOF96/98/99 rules applied to every source'}, 'disagreement': 'none', 'options': ['keep'], 'recommend': 'keep'},
]

# ---- what the recorded moves lack (TODO #77-#140, handlers98.md) ---------------------------------------------------------
# components: kind enh (an existing feature extended: its users are the regression set), new (a library component),
# analysis (decoding work first; no engine change)
COMPONENTS = {
 'hold.paired_script': ('enh', ['hold.throw_script', 'hold.catch'],
    'A catch (hold.catch) or a grab starts a paired attacker / victim script: victim pose + offset per frame, impacts '
    '(the throw script, bthrow_t, made startable from a move). Covers KOF\'s held victim states placed from a table, '
    'the engine\'s cinematic finisher (both fighters\' states from a table) and grabs that drive the victim\'s own states.'),
 'input.sustain': ('new', [], 'A part repeats / extends while a button is mashed (N presses in M frames) or held; '
    'parameters: button, presses per repeat, max repeats, hold release.'),
 'stage.wall': ('new', [], 'Stage edges as walls: a condition branch.on_wall (body within N px of the edge) and a wall '
    'bounce reaction. The brawler\'s camera clamp is not a wall today.'),
 'branch.on_velocity': ('enh', ['branch.on_distance', 'branch.on_height'], 'Branch on the body\'s vx sign / size.'),
 'spawn.multihit_object': ('enh', ['spawn.projectile', 'spawn.eruption'], 'An object with its own hit list: N hits on a '
    'period, each with damage / reaction, a hit counter, a state list.'),
 'anim.step_spawn': ('enh', ['anim.event_marker', 'spawn.eruption'], 'Steps spawn objects from a table (optionally a '
    'random pick among N), instead of the move code.'),
 'spawn.boomerang': ('enh', ['spawn.projectile'], 'A projectile whose path returns to the thrower (built, TODO #176: bproj_t kind 4, SS2 Kuroko\'s flag; its hit rule '
    'is data: the rows\' boxes).'),
 'decode.ss4': ('analysis', [], 'Samurai Shodown IV handler decoder (tools/samsho4 has captures only).'),
 'decode.whp': ('analysis', [], 'World Heroes Perfect handler decoder (tools/whp has captures only).'),
 'decode.kizuna': ('analysis', [], 'Kizuna handler decoder (tools/kizuna/substates_kz.py: sub-state tables, not programs yet).'),
 'decode.kof_trace': ('analysis', [], 'A KOF trace that enters the special (no capture try reaches its handler, or the decoder '
    'stops on an unplaced test).'),
}
# recorded move -> (TODO item, components, note). Moves not listed: classified from their facts (untracked).
MISSING = {
 'ralf:AAAA': (81, ['input.sustain', 'decode.kof_trace'], 'Vulcan Punch: state list re-armed by A presses; no KOF trace of the repeat'),
 'robert:426B': (83, ['decode.kof_trace'], 'no capture enters the handler (KOF gives a normal, state 90)'),
 'yamazaki:214A': (86, ['decode.kof_trace'], 'decoder stops on a test off a4 (f-1)'),
 'billy:CCCC': (88, ['input.sustain', 'decode.kof_trace'], 'mash move; no KOF trace with the repeated C'),
 'iori:624D': (94, ['hold.paired_script'], 'catch sends the victim into held states 432-435 placed from $25376 / $25396'),
 'iori:624B': (96, ['hold.paired_script'], 'same handler as 624D'),
 'rugal:624A': (115, ['stage.wall', 'branch.on_velocity'], 'calls the wall test $18092, branches on vx'),
 'rugal:6426A': (116, ['spawn.multihit_object'], 'Kaiser Wave steps a state list through +$C2, counts hits in +$138'),
 'rugal:6426C': (117, ['spawn.multihit_object'], 'as 6426A'),
 'goenitz:214C': (119, ['anim.step_spawn'], 'wind objects 179-181 from the animate routine\'s step-effect table $249E8, random pick'),
 'yamazaki:236236C': (87, ['hold.paired_script'], 'hits come from the victim\'s scripted states 433-442 (attacker sets victim +$D1 bit 7)'),
 'iori:23624C': (98, ['hold.paired_script'], 'finisher = engine cinematic hit ($1EB20 box, $3F8A test, $1E7E8 table by +$F8)'),
 'rugal:23624C': (118, ['stage.wall'], 'the catch grinds the victim to the stage wall ($18092)'),
 'goenitz:2141236C': (120, ['hold.paired_script'], 'finisher = KOF96 cinematic hit ($17796 box, $3676 test)'),
 'haohmaru:236C': (121, ['decode.ss4'], ''), 'haohmaru:421C': (122, ['decode.ss4'], ''), 'haohmaru:623B': (123, ['decode.ss4'], ''),
 'haohmaru:BUST 236D': ((124, 126), ['decode.ss4'], 'up+C slot and fury'), 'haohmaru:BUST 623D': (125, ['decode.ss4'], ''),
 'hanzo:236A': (127, ['decode.whp'], ''), 'hanzo:236D': (128, ['decode.whp'], ''), 'hanzo:623B': (129, ['decode.whp'], ''),
 'hanzo:214C': (130, ['decode.whp'], ''), 'hanzo:623A': (131, ['decode.whp'], ''), 'hanzo:214D': (132, ['decode.whp'], ''),
 'yamazaki:214B': (None, ['decode.kof_trace'], 'captured since #73 (its own state path 128 -> 132); no open TODO item; likely the snake-arm handler of 214A (#86)'),
 'yamazaki:214C': (None, ['decode.kof_trace'], 'captured since #73 (state path 128 -> 133); no open TODO item; as 214B'),
 'kim:421A': (136, ['decode.kizuna', 'hold.paired_script'], 'hit sequence with the victim placed per row (carry); Kim\'s side decodable (export_kz KzProg), the victim\'s flight is Kizuna\'s reaction code'),
 'kim:6246A': (138, ['decode.kizuna', 'hold.paired_script'], 'cinematic with carry + backdrop (fx.backdrop exists); as 421A'),
}
# fighters extracted but not in the build (#77) and follow-up leftovers (#140): their gaps, counted apart
OFF_BUILD = [
 ('kizuna:gozu/mezu/joker/gordon fury', 77, ['hold.paired_script'], 'a grab by code (no box: no hit)'),
 ('kizuna:hayate [2]8C', 77, ['spawn.boomerang'], 'boomerangs hit by code (not exported)'),
 ('kizuna:chung fury, r_shishi 4264A / 214B', 77, ['decode.kizuna'], 'not captured'),
 ('kizuna:projectiles', 77, ['decode.kizuna'], 'drawn, no end rows'),
 ('kof99:k_dash 214D / 236B / 236D / 623A / 23624C follow-ups', 140, ['decode.kof_trace'], 'decoded only, wait for Bruno\'s recorded paths'),
 ('kof98:kyo 236C 6A after hit-stop', 140, [], 'ruleset: follow-up input timing (KOF misses presses right after hit-stop)'),
 ('all furies: super flash', 139, [], 'presentation: KOF\'s super flash dropped as bookkeeping (fx.super_flash not in the vocabulary)'),
]

def inventory(cl, moves):
    played = [mv for mv in moves if mv['slot']]
    fx = {mid(mv): facts(mv) for mv in moves}
    out = {}
    for fam, name, params, sem, impl, det in FEATURES:
        users = [mv for mv in played if det(mv, fx[mid(mv)])]
        by = {}
        for mv in users: by[mv['game']] = by.get(mv['game'], 0) + 1
        out.setdefault(fam, []).append({'name': name, 'params': [dict(zip(('name', 'type', 'range'), p)) for p in params],
                                        'semantics': sem, 'implemented_by': impl, 'count': len(users), 'by_source': by,
                                        'moves': [label(mv) for mv in users]})
    thr = throws_of()
    for fam, name, params, sem, impl in FIGHTER_FEATURES:
        if name == 'hold.throw_script': fs = [f"{f['name']} throws ({thr[f['name']]})" for f in cl['fighters'] if thr.get(f['name'])]
        elif name == 'hold.grab_hold': fs = [f"{f['name']} hold" for f in cl['fighters'] if thr.get(f['name'])]
        else: fs = [f['name'] for f in cl['fighters']]
        out.setdefault(fam, []).append({'name': name, 'params': [dict(zip(('name', 'type', 'range'), p)) for p in params],
                                        'semantics': sem, 'implemented_by': impl, 'count': len(fs), 'unit': 'fighters', 'moves': fs})
    return out, fx

def users_of(vocab, names):
    feats = {f['name']: f for fam in vocab.values() for f in fam}
    return sorted({m for n in names for m in feats.get(n, {}).get('moves', [])})

def classify(mv, f, vocab):
    """ingestion class of a move: a covered by existing features, b needs an enhancement (+ regression set),
    c needs a new component; analysis = decoding first"""
    used = [ft['name'] for fam in vocab.values() for ft in fam if label(mv) in ft['moves']]
    if mv['kind'] == 'rom': return {'class': 'a', 'features': used, 'needs': [], 'regression_set': []}
    need = MISSING.get(mid(mv), (None, [], ''))[1]
    kinds = [COMPONENTS[c][0] for c in need]
    cls = 'c' if 'new' in kinds else 'b' if 'enh' in kinds else 'analysis' if kinds else 'untracked'
    reg = users_of(vocab, [b for c in need if COMPONENTS[c][0] == 'enh' for b in COMPONENTS[c][1]])
    if cls == 'analysis':                              # decoded later; the capture shows which features it would use
        cls = 'a (after analysis)'
    return {'class': cls, 'features': used, 'needs': [{'component': c, 'kind': COMPONENTS[c][0], 'extends': COMPONENTS[c][1],
                                                        'spec': COMPONENTS[c][2]} for c in need], 'regression_set': reg}

def missing(moves, vocab, fx):
    rec = [mv for mv in moves if mv['slot'] and mv['kind'] == 'recorded']
    items = []
    for mv in rec:
        todo, need, note = MISSING.get(mid(mv), (None, [], 'not in the TODO list'))
        items.append({'move': label(mv), 'game': mv['game'], 'todo': todo, 'needs': need, 'note': note,
                      'class': classify(mv, fx[mid(mv)], vocab)['class']})
    for what, todo, need, note in OFF_BUILD:
        items.append({'move': what, 'game': what.split(':')[0], 'todo': todo, 'needs': need, 'note': note, 'class': 'off build'})
    plan = {}
    for it in items:
        for c in it['needs']: plan.setdefault(c, []).append(it['move'])
    debt = sorted(({'component': c, 'kind': COMPONENTS[c][0], 'extends': COMPONENTS[c][1], 'spec': COMPONENTS[c][2],
                    'retires_in_build': sum(1 for m in ms if '[' in m), 'moves': ms,
                    'blocked_alone': sum(1 for it in items if it['needs'] == [c] and '[' in it['move']),
                    'regression_set_size': len(users_of(vocab, COMPONENTS[c][1]))} for c, ms in plan.items()),
                  key=lambda d: (-d['blocked_alone'], -d['retires_in_build']))
    return {'recorded_in_build': len(rec), 'items': items, 'debt_plan': debt}

# ---- conversion sheets --------------------------------------------------------------------------------------------------
KOF = os.path.join(ROOT, 'tools', 'kof96')
FLAGS_JSON = os.path.join(ROOT, 'docs', 'kof_engine_flags.json')   # the shared KOF-engine field / flag table
_MEM = {}
def kof_env(game):
    """(handlers98, export96, rom Mem) of a KOF game, loaded once"""
    sys.path.insert(0, KOF); sys.path.insert(0, os.path.join(KOF, 'capture'))
    import handlers98 as H, rom96, export96
    if game not in _MEM: _MEM[game] = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    return H, export96, _MEM[game]

def flag_table():
    if not hasattr(flag_table, 't'): flag_table.t = json.load(open(FLAGS_JSON))
    return flag_table.t

def fname(f):
    """a fighter-object field's name from the flag table ('+$50 vx (16.16 px/frame)')"""
    n = flag_table()['fields'].get(f'+${f:X}')
    return f'+${f:X}' + (f' {n.split(" (")[0]}' if n else '')

def fval(f, size, v):
    """a stored value as the engine reads it (handlers98.store_value: 16.16 speeds as px, ROM pointers as addresses)"""
    return kof_env('kof98')[0].store_value(f, size, v)

def ctx_label(ctxs, ctx, top):
    ra, depth, _ = ctxs[ctx]
    return 'handler' if depth == 0 and ra == top else f'object routine ${ra:X}' + (' (hit)' if depth > 1 else '')

BUTTON_FIELD, EX_FIELD, FACING_FIELD, MAX_FIELD = 0x1A4, 0x1D6, 0x31, 0xE4
def branches(trace, top):
    """the branches the decode decided from a known field (the button, the EX flag, the MAX bit, the facing): one per
    address"""
    H = kof_env('kof98')[0]; trace_ctx = H.trace_ctx
    ctxs = trace_ctx(trace); out, seen = [], set()
    for ctx, (ra, depth, ev) in ctxs.items():
        for e in ev:
            if e[0] != 'decide' or (ctx, e[2]) in seen: continue
            seen.add((ctx, e[2]))
            _, _, a, src, v, cond, taken, t, nx = e
            kind, ta, f, x = src
            if f == BUTTON_FIELD and kind == 'btst':
                what = f'button bit {x} of +$1A4 ({"ABCD"[x - 4] if 4 <= x < 8 else "?"})'; state = 'set' if v else 'clear'
            elif f == EX_FIELD: what = 'EX flag +$1D6'; state = 'EX' if v else 'not EX'
            elif f == MAX_FIELD and kind == 'btst' and x == 0: what = 'MAX / SDM bit +$E4 bit 0'; state = 'MAX' if v else 'not MAX'
            elif f == FACING_FIELD and kind == 'btst' and x == 0: what = 'facing +$31 bit 0'; state = 'right (decoder assumption; left mirrors)'
            else: what = fname(f) + (f' bit {x}' if kind == 'btst' else ''); state = str(v)
            out.append({'addr': f'${a:06X}', 'test_at': f'${ta:06X}', 'in': ctx_label(ctxs, ctx, top), 'test': what,
                        'value': state, 'variant': f in (BUTTON_FIELD, EX_FIELD) or f == MAX_FIELD and kind == 'btst' and x == 0,
                        'taken': f'${t:06X}' if taken else f'${nx:06X} (falls through)',
                        'other_way': f'${nx:06X} (falls through)' if taken else f'${t:06X}'})
    return out

def bits_of(op):
    """a handlers98 ('flag', base, field, value) op -> [(bit, 'set' | 'cleared')]"""
    _, base, fd, v = op[:4]
    return [(b, 'set') for b in range(8) if v >> b & 1] if base.startswith('or') else [(b, 'cleared') for b in range(8) if not v >> b & 1]

NAMED_BIT_OPS = {'part', 'fxoff', 'sigclr', 'hitclr', 'hitoff', 'hold', 'unhold', 'evclr'}   # handlers98 ops that model a bit write
def kof_source(mv):
    """(excerpt, model, extra) of a KOF ROM move: the handler's instructions that produced each decoded op (68000,
    annotated with the op, one line per instruction), the whiff model's state runs (and the catch branch), and extra:
    dead stores, branches decided by the button / EX flag / facing, the bit writes the export drops (unexplained ones
    flagged), the move's variants, the exported program's op -> instruction address"""
    game = mv['game']; H, export96, m = kof_env(game)
    cast = {'kof96': export96.CAST, 'kof98': export96.CAST98, 'kof99': export96.CAST99}[game]
    cid = cast.index(mv['fighter'])
    h, b = H.handler_of(cid, mv['input'], game=game)
    ex = mv['input'].startswith('EX ')
    dec = H.Decoder(m); dec.trace = []
    d = H.decode(m, h, b, ex, dec=dec, cid=cid)
    trace = dec.trace; dec.trace = None
    ctxs = H.trace_ctx(trace); dead = H.dead_stores(trace, dec)
    dead_at = {}                                       # (routine, address) -> its dead store record
    for (ctx, a), (e, kl) in dead.items():
        ra = ctxs[ctx][0]
        dead_at[(ra, a)] = {'addr': f'${a:06X}', 'in': ctx_label(ctxs, ctx, h), 'field': fname(e[3]), 'value': fval(e[3], e[4], e[5]),
                            'overwritten_at': f'${kl[2]:06X}', 'by': fval(kl[3], kl[4], kl[5])}
    tab = flag_table(); lines = []; bitw = []
    rows, objs = H.run_model(m, cid, d, frames=400)
    reached = {id(o.prog) for o in objs}             # the objects the whiff model spawns
    def walk(dd, ind=''):
        ops = dd['ops']; named = {a for a, op in ops if op[0] in NAMED_BIT_OPS}
        for i, (a, op) in enumerate(ops):
            if op[0] == 'flag' and op[1] != 'pruned' and a in named: continue     # the named op says it (one line)
            try: mn, ops_, _ = dec.at(a); ins = f'{mn} {",".join(ops_)}'
            except Exception: ins = '?'
            txt = ' '.join(str(x) if not isinstance(x, (int, float)) or abs(x) < 256 else f'${int(x):X}' for x in op if not isinstance(x, tuple))
            note = None
            if op[0] == 'flag' and op[1] == 'pruned': txt = f'branch on {op[2]} pruned (both ways meet before anything but bookkeeping)'
            elif op[0] == 'flag':
                parts = []
                for bt, how in bits_of(op):
                    ent = tab['bits'].get(f'+${op[2]:X}.{bt}')
                    w = f'+${op[2]:X} bit {bt} {how}'
                    rec = {'addr': f'${a:06X}', 'in': ind or 'handler', 'write': w, 'name': ent['name'] if ent else None,
                           'effect': ent['effect'] if ent else 'unknown', 'brawler': ent['brawler'] if ent else None,
                           'status': 'explained' if ent and ent['effect'] != 'unknown' else 'UNEXPLAINED'}
                    bitw.append(rec)
                    parts.append(w + (f': {ent["name"]} ({ent["effect"]})' if ent and ent['effect'] != 'unknown' else ': UNEXPLAINED'))
                txt = 'dropped bit write: ' + '; '.join(parts)
            elif op[0] in ('ownerflag', 'flags', 'inflight', 'release'):
                t_ = int(ops_[0], 16) if ins != '?' and ops_ and ops_[0].startswith('0x') else None
                ent = tab['routines'].get(f'{game}:${t_:X}') if t_ is not None else None
                w = f'jsr ${t_:X}' if t_ is not None else op[0]
                if op[0] in ('ownerflag', 'flags'):
                    bitw.append({'addr': f'${a:06X}', 'in': ind or 'handler', 'write': w + (' (' + ', '.join(ent.get('sets', []) + ent.get('clears', []) + ent.get('reads', [])) + ')' if ent else ''),
                                 'name': ent['name'] if ent else None, 'effect': ent['effect'] if ent else 'unknown',
                                 'brawler': ent['brawler'] if ent else None, 'status': 'explained' if ent else 'UNEXPLAINED'})
                if ent: txt += f' = {ent["name"]}: ' + ', '.join([f'sets {x}' for x in ent.get('sets', [])] + [f'clears {x}' for x in ent.get('clears', [])] + [f'reads {x}' for x in ent.get('reads', [])])
                elif op[0] in ('ownerflag', 'flags'): txt += ' UNEXPLAINED'
            if op[0] == 'br' and isinstance(op[1], str) and op[1].startswith('owner_') and '.' in op[1]:
                ent = tab['bits'].get('+$' + op[1][6:])
                txt += f' (owner +${op[1][6:]}: ' + (ent['name'] if ent else 'UNEXPLAINED') + ')'
            if op[0] == 'spawn' and dd is d and op[1] < len(d['objects']) and id(d['objects'][op[1]]) not in reached:
                note = 'never reached in the whiff model: a decode-time place past the state\'s last event step (KOF spawns no such object)'
            dr = dead_at.get((dd['addr'], a))
            if dr and op[0] == 'set': note = f'DEAD: overwritten at {dr["overwritten_at"]} ({dr["by"]}) before any frame plays'
            if lines and lines[-1]['addr'] == f'${a:06X}' and lines[-1]['in'] == (ind or 'handler') and lines[-1]['asm'] == ins:
                lines[-1]['op'] += '; ' + txt; continue          # one instruction, one line (its ops joined)
            lines.append({'addr': f'${a:06X}', 'asm': ins, 'op': txt, 'in': ind or 'handler', **({'note': note} if note else {})})
        for k, ob in enumerate(dd.get('objects', [])): walk(ob, f'object {k} (${ob["addr"]:X}, state {ob.get("state")}, kind {ob["kind"]})')
        if ind and dd.get('hit'): walk(dd['hit'], ind + ' hit')
    walk(d)
    runs = lambda rs: [[s, a, b_] for s, a, b_ in _runs([r[1] for r in rs])]
    states = []                                        # export_rom's anim order: first appearance in the decoded ops
    for a_, op in d['ops']:
        if op[0] == 'anim' and op[1] not in states: states.append(op[1])
    model = {'handler': f'${h:X}', 'button': b, 'states': states, 'whiff': runs(rows), 'whiff_frames': len(rows)}
    if any(op[0] == 'onhit' for a, op in d['ops']) and len(states) == len(mv['anims']):   # the catch branch: caught on
        for i, st in enumerate(states):                 # the first catch step's first frame (point blank)
            k = next((j for j, s_ in enumerate(mv['anims'][i]) if s_['flags'] & 64), None)
            start = next((a_ for s_, a_, b_ in model['whiff'] if s_ == st), None)
            if k is None or start is None: continue
            ca = start + sum(s_['ticks'] + 1 for s_ in mv['anims'][i][:k])
            r2, _ = H.run_model(m, cid, d, frames=400, catch_at=ca, hits=range(ca, 400))
            model['catch_at'] = ca; model['caught'] = runs(r2); model['caught_frames'] = len(r2); break
    per, last, peak, n = H.openings(m, cid, d)
    model['openings'] = {str(k): v for k, v in per.items()}
    # the exported program (bspec_t.prog) = the handler's ops minus DROP_OPS (voice sends kept) and hitkind (export_rom): op -> address
    kept = [a for a, op in d['ops'] if H.kept_op(m, op) and op[0] != 'hitkind']   # (+ its voice sends, TODO #163)
    br = branches(trace, h)
    extra = {'dead_stores': sorted(dead_at.values(), key=lambda r: (r['in'] != 'handler', r['addr'])), 'branches': br,
             'bit_writes': bitw, 'prog_addr': kept if len(kept) == len(mv['prog']) else None,
             'variants': variants(mv, H, m, cid, h, b, ex, br)}
    return lines, model, extra

def variants(mv, H, m, cid, h, b, ex, br):
    """every version of the move's handler (handlers98.decode_variants: forked at each button / EX / MAX test, the
    same code path as the export's 'variants'): its live field writes, states, objects, whiff length, hit openings.
    [] when the handler has one version."""
    vs = H.decode_variants(m, h, b, ex, cid)
    if len(vs) < 2: return []
    out = []
    for v in vs:
        r = H.variant_summary(m, cid, mv['input'], v)
        try: same = H.handler_of(cid, r['input'], v['ex'], m.game)[0] == h
        except Exception: same = None                 # no capture of that input
        out.append({'input': r['input'], 'strength': ('MAX ' if v['sdm'] else '') + ('EX ' if v['ex'] else '') + ('light' if v['button'] in 'AB' else 'heavy'),
                    'this_sheet': r['input'] == mv['input'], 'button': v['button'], 'ex': v['ex'], 'max': v['sdm'],
                    'captured_same_handler': same, 'states': r['states'], 'objects_spawned': r['objects_spawned'],
                    'hit_kind': r['hit_kind'], 'whiff_frames': r['whiff_frames'], 'hits': r['hit_openings'],
                    'params': {fname(int(k[2:], 16)): x for k, x in r['fields'].items()},
                    'path': [t for a_, t in r['path']], 'path_at': [a_ for a_, t in r['path']]})
    return out

def _runs(seq):
    out, start = [], 0
    for i in range(1, len(seq) + 1):
        if i == len(seq) or seq[i] != seq[start]: out.append((seq[start], start, i - 1)); start = i
    return out

def prog_mapping(mv, model=None, extra=None):
    """the exported program as phases: one per P_ANIM, with the ops that run in it mapped to standard features. A set
    overwritten before any frame plays (extra dead_stores: the other variant's value the handler writes first) is left
    out; a set names the instruction it came from ('at')"""
    states = model['states'] if model and len(model['states']) == len(mv['anims']) else []
    addrs = (extra or {}).get('prog_addr')
    dead = {r['addr'] for r in (extra or {}).get('dead_stores', []) if r['in'] == 'handler'}
    phases, cur, pre = [], None, []
    for i, (op, a, b, v) in enumerate(mv['prog']):
        at = f'${addrs[i]:06X}' if addrs else None
        if op == P['SET'] and at in dead: continue
        name = PN.get(op, str(op))
        if op == P['ANIM']:
            steps = mv['anims'][a]
            hits = [k for k, s in enumerate(steps) if s['flags'] & 1 and not (k and steps[k - 1]['flags'] & 1 and steps[k - 1]['flags'] & 16)]
            st = states[a] if a < len(states) else None
            fr = None
            if model and st is not None:
                for path in ('caught', 'whiff'):        # the catch branch first, else the whiff's
                    rr = [(x, y) for s, x, y in model.get(path, []) if s == st]
                    if rr: fr = [rr[0][0], rr[-1][1]] + ([] if path == 'caught' or 'caught' not in model else ['whiff']); break
            cur = {'anim': a, 'kof_state': st, 'frames': fr, 'steps': len(steps), 'length': sum(s['ticks'] + 1 for s in steps),
                   'features': [{'feature': 'anim.play', 'params': {'anim': st if st is not None else a, 'steps': len(steps)}}]}
            if hits:
                cur['features'].append({'feature': 'hit.box', 'params': {'hits': len(hits), 'damage_each': b & 0xFF, 'reaction': R[(b >> 8) & 7],
                                        'fx': v & 0x3F, 'burn': v >> 6,
                                        'by_height': sorted({f"{R[s['hy'] & 7]}/{R[(s['hy'] >> 4) & 7]}" for s in steps if s['flags'] & 1 and s['hy'] > 15})}})
                if any(s['flags'] & 64 for s in steps): cur['features'].append({'feature': 'hold.catch', 'params': {}})
                if any(s['flags'] & 128 for s in steps if s['flags'] & 1): cur['features'].append({'feature': 'hit.no_stop', 'params': {}})
                if any(s['flags'] & 4 for s in steps if s['flags'] & 1): cur['features'].append({'feature': 'hit.slide', 'params': {'px': 0}})
            if any(s['dx'] for s in steps): cur['features'].append({'feature': 'move.step_offset', 'params': {'dx': [s['dx'] for s in steps if s['dx']]}})
            if not all(s['flags'] & 2 for s in steps): cur['features'].append({'feature': 'anim.no_hurt_step', 'params': {'steps': [k for k, s in enumerate(steps) if not s['flags'] & 2]}})
            if pre: cur['features'][1:1] = pre; pre = []
            phases.append(cur); continue
        feat = None
        if op == P['SET']:
            reg = REG[a]; val = v / 65536 if a in (0, 1, 2, 5) else v / 65536 if a == 3 else v
            feat = {'feature': {'vx': 'move.velocity', 'vy': 'move.velocity', 'g': 'move.gravity', 'fric': 'move.friction',
                                'cnt': 'branch.on_timer', 'h': 'move.nudge'}[reg], 'params': {reg: round(val, 4), **({'at': at} if at else {})}}
        elif op == P['MUL']: feat = {'feature': 'move.friction', 'params': {'mul': round(v / 65536, 4)}}
        elif op in (P['MOVE'], P['FRICMOVE'], P['FALL']):
            feat = {'feature': {P['MOVE']: 'move.velocity', P['FRICMOVE']: 'move.friction', P['FALL']: 'move.gravity'}[op], 'params': {'apply': name.lower()}}
        elif op == P['NUDGE']: feat = {'feature': 'move.nudge', 'params': {'dx': b, 'dy': v}}
        elif op == P['BR']:
            c = PC[a & 0x7F]
            if c == 'always': continue
            fmap = {'end': 'branch.on_anim_end', 'event': 'branch.on_event', 'stepev': 'branch.on_event', 'land': 'branch.on_land',
                    'falling': 'branch.on_land', 'cnt': 'branch.on_timer', 'hit': 'branch.on_hit', 'hitany': 'branch.on_hit',
                    'off': 'branch.on_offscreen', 'link': 'branch.on_input', 'window': 'branch.on_input', 'far': 'branch.on_distance',
                    'low': 'branch.on_height', 'sig7': 'spawn.signal', 'sig7c': 'spawn.signal', 'sig6': 'spawn.signal'}
            feat = {'feature': fmap[c], 'params': {'when': c + (' true' if a & 0x80 else ' false'), 'goto': 'next frame' if b == -1 else f'op {b}', **({'v': v} if v else {})}}
        elif op == P['SPAWN']:
            o = mv['robj'][a] if a < len(mv['robj']) else {}
            k = 'spawn.pinned_effect' if o.get('follow', 0) & 1 else 'spawn.projectile' if o.get('kind') == 1 else \
                'spawn.boomerang' if o.get('kind') == 4 else 'spawn.eruption'
            feat = {'feature': k, 'params': {'object': a, 'frames': o.get('nrows'), 'react': R[o['react'] & 7] if o else None}}
        elif op == P['FXOFF']: feat = {'feature': 'spawn.pinned_effect', 'params': {'end': True}}
        elif op == P['ONHIT']: feat = {'feature': 'hold.catch', 'params': {'routine_op': b, 'dead_frames': a + 1}}
        elif op == P['PUT']: feat = {'feature': 'hold.place', 'params': {'px': v}}
        elif op in (P['HOLD'], P['UNHOLD']): feat = {'feature': 'hold.held_reel', 'params': {'hold': op == P['HOLD']}}
        elif op in (P['HITCLR'], P['HITOFF']): feat = {'feature': 'branch.on_hit', 'params': {'clear': name.lower()}}
        elif op in (P['CHECK'], P['PART']): feat = {'feature': 'branch.on_input', 'params': {name.lower(): a}}
        elif op == P['END']: feat = {'feature': 'end', 'params': {}}
        if feat is None: continue
        (cur['features'] if cur else pre).append(feat)
        if op == P['END']: cur = None                   # code past an end belongs to the phase it leads into
    return phases

def capture_mapping(mv):
    """a recorded move: phases (parts, else ground / air runs) with their motion fitted to physics, hits and links"""
    rows = mv['rows']; n = len(rows)
    spans = [(p['first'], p['end'], k) for k, p in enumerate(mv['parts'])] or None
    if not spans:
        spans, s = [], 0
        for i in range(1, n + 1):
            if i == n or (rows[i]['y'] > 0) != (rows[s]['y'] > 0): spans.append((s, i, None)); s = i
    phases = []
    for a, b, k in spans:
        rs = rows[a:b]
        if not rs: continue
        feats = [{'feature': 'anim.play', 'params': {'frames': sorted({r['frame'] for r in rs})[:12], 'rows': len(rs)}}]
        xs = [r['x'] for r in rs]; ys = [r['y'] for r in rs]
        if len(rs) > 2 and max(ys) > 0:                 # fitted ballistic: y = y0 + vy t - g t^2 / 2, x = x0 + vx t
            fit = _fit(xs, ys)
            feats.append({'feature': 'move.velocity', 'params': {'vx': fit['vx'], 'vy': fit['vy']}})
            feats.append({'feature': 'move.gravity', 'params': {'g': fit['g'], 'max_error_px': fit['err']}})
        elif xs[-1] != xs[0]:
            feats.append({'feature': 'move.velocity', 'params': {'vx_mean': round((xs[-1] - xs[0]) / max(1, len(xs) - 1), 3), 'distance': xs[-1] - xs[0]}})
        hits = [i for i in range(a, b) if rows[i]['hit'] & 2]
        if hits:
            feats.append({'feature': 'hit.box', 'params': {'hits': len(hits), 'rows': hits, 'damage': [rows[i]['dmg'] for i in hits],
                                                         'reaction': sorted({R[(rows[i]['hit'] >> 5) & 7] for i in hits}),
                                                         'fx': sorted({rows[i]['fx'] & 0x3F for i in hits})}})
        if any(r['hit'] & 4 for r in rs): feats.append({'feature': 'hold.carry', 'params': {'rows': sum(1 for r in rs if r['hit'] & 4)}})
        if any(o['frame'] != 0xFFFF for r in rs for o in r['obj']): feats.append({'feature': 'spawn.script_effect', 'params': {}})
        for p in mv['proj']:
            if a <= p['spawn_row'] < b:
                feats.append({'feature': 'spawn.projectile' if p['kind'] == 1 else 'spawn.eruption',
                              'params': {'row': p['spawn_row'], 'offset': [p['spawn_x'], p['spawn_y']], 'react': R[p['react'] & 7], 'frames': p['nrows']}})
        for l in mv['links']:
            if k is not None and l['from'] == k:
                what = ('hit' if l['trig'] & 1 else '') + ('+' if l['trig'] == 3 else '') + ('input' if l['trig'] & 2 else '')
                inp = 'again' if l['dir'] == 0xFE else (SLOTS[l['dir']] if l['dir'] < 6 else 'any') + ('+' + {1: 'A', 2: 'B', 4: 'C', 8: 'D'}.get(l['in'], '')) if l['trig'] & 2 else None
                feats.append({'feature': 'branch.on_input' if l['trig'] & 2 else 'branch.on_hit',
                              'params': {'on': what, 'input': inp, 'window_rows': [l['lo'], l['hi']], 'to_part': l['to'], 'at': 'now' if l['at'] else 'part end'}})
        if k is not None: feats.append({'feature': 'branch.parts', 'params': {'next': 'end' if mv['parts'][k]['next'] == 255 else mv['parts'][k]['next']}})
        if mv['bd'] and a <= mv['bd'][0] < b: feats.append({'feature': 'fx.backdrop', 'params': {'rows': list(mv['bd'])}})
        phases.append({'part': k, 'rows': [a, b - 1], 'features': feats})
    return phases

def _fit(xs, ys):
    t = list(range(len(ys))); nn = len(t)
    def solve(cols, y):                                # least squares, normal equations (3x3 at most)
        k = len(cols); A = [[sum(cols[i][j] * cols[l][j] for j in range(nn)) for l in range(k)] for i in range(k)]
        bb = [sum(cols[i][j] * y[j] for j in range(nn)) for i in range(k)]
        for i in range(k):
            p = max(range(i, k), key=lambda r: abs(A[r][i])); A[i], A[p] = A[p], A[i]; bb[i], bb[p] = bb[p], bb[i]
            for r in range(k):
                if r != i and A[i][i]:
                    q = A[r][i] / A[i][i]; A[r] = [A[r][c] - q * A[i][c] for c in range(k)]; bb[r] -= q * bb[i]
        return [bb[i] / A[i][i] if A[i][i] else 0 for i in range(k)]
    one = [1] * nn
    y0, vy, c = solve([one, t, [x * x for x in t]], ys)
    x0, vx = solve([one, t], xs)
    err = max(abs(y0 + vy * x + c * x * x - y) for x, y in zip(t, ys))
    return {'vx': round(vx, 3), 'vy': round(vy + c, 3), 'g': round(-2 * c, 4), 'err': round(err, 2)}   # discrete: vy0 = b + c

def understood(mv, phases):
    out = []
    for i, ph in enumerate(phases):
        bits = []
        for ft in ph['features']:
            n, p = ft['feature'], ft['params']
            if n == 'anim.play': bits.append(f"plays {'state ' + str(ph.get('kof_state')) if ph.get('kof_state') is not None else 'its frames'}"
                                             + (f" (frames {ph['frames'][0]}-{ph['frames'][1]})" if ph.get('frames') else f" (rows {ph['rows'][0]}-{ph['rows'][1]})" if ph.get('rows') else ''))
            elif n == 'hit.box': bits.append(f"{p['hits']} hit(s), {p.get('reaction')}")
            elif n.startswith('move.') and p: bits.append(n.split('.')[1] + ' ' + ', '.join(f'{k} {v}' for k, v in p.items()))
            elif n.startswith('branch.'): bits.append(f"{n.split('.', 1)[1]} " + (p['when'] if 'when' in p else f"{p['on']} {p.get('input') or ''} rows {p['window_rows']} -> part {p['to_part']} ({p['at']})" if 'on' in p else json.dumps(p)))
            elif n.startswith(('spawn.', 'hold.', 'fx.')): bits.append(n + (' ' + json.dumps(p) if p else ''))
        out.append(f"phase {i}: " + '; '.join(bits))
    return out

def fidelity(mv):
    """the existing proof outputs for this move (romspecials_check / fury summaries, kim sequence proof, Haohmaru proof)"""
    out = []
    case = lambda e: e.get('case', '').split(':')[0] == mv['fighter'] and e.get('input') == mv['input']
    seen = set()                                       # the newest proof per branch (older runs are superseded)
    for f in sorted(glob.glob('/data/tmp/*/out*/summary.json') + glob.glob('/data/tmp/*/summary.json'), key=os.path.getmtime, reverse=True):
        try: d = json.load(open(f))
        except Exception: continue
        for e in d if isinstance(d, list) else []:
            if isinstance(e, dict) and case(e) and e.get('branch') not in seen:
                seen.add(e.get('branch'))
                kh, bh = e.get('kof_hits') or [], e.get('brawler_hits') or []
                out.append({'hit_frame_offsets': sorted({b_ - a_ for a_, b_ in zip(kh, bh)}),'proof': f, 'branch': e.get('branch'), 'frames': [e.get('kof_frames'), e.get('brawler_frames')],
                            'frame_mismatch': e.get('frame_mismatch'), 'hits': [len(e.get('kof_hits') or []), len(e.get('brawler_hits') or [])],
                            'hit_frames_equal': e.get('kof_hits') == e.get('brawler_hits'), 'max_dx_px': e.get('max_dx'), 'max_dh_px': e.get('max_dh'),
                            'victim_max_dx_px': e.get('victim_max_dx'), 'victim_max_dh_px': e.get('victim_max_dh')})
    if not out and mv['kind'] == 'rom' and mv['input'][-1] in 'ABCD':   # its button twin (same handler, the other strength)
        twin = mv['input'][:-1] + {'A': 'C', 'C': 'A', 'B': 'D', 'D': 'B'}[mv['input'][-1]]
        out = [dict(e, twin=twin, note=f'no proof of {mv["input"]} (not on a slot); its twin {twin}, same handler') for e in fidelity(dict(mv, input=twin, kind='twin'))]
    kp = '/data/tmp/kim76/seq/proof.json'
    if mv['fighter'] == 'kim' and os.path.exists(kp):
        for k, v in json.load(open(kp))['scenarios'].items():
            if k.split()[0] == mv['input']:
                out.append({'proof': kp, 'scenario': k, 'parts': [v['parts'], v['kizuna_parts']], 'ok': v['ok'], 'hits': [v['kizuna_hits'], len(v['hits'])]})
    hp = '/data/tmp/haohmaru/out/proof.json'
    if mv['fighter'] == 'haohmaru' and os.path.exists(hp):
        d = json.load(open(hp)); slot = {'D': 'D', 'fD': 'fwd+D', 'dD': 'down+D', 'uD': 'up+D'}.get(slots(mv)[0])
        out.append({'proof': hp, 'render_frames_same': d['frames_same'], 'render_frames_differ': d['frames_differ'],
                    'brawler_hits': d['specials'].get(slot, {}).get('hits'), 'note': 'render check + brawler hits only: no SS4 frame-timing proof (no handler decoder)'})
    return out

def sheet(mv, vocab, fx):
    rec = {'move': label(mv), 'fighter': mv['fighter'], 'game': mv['game'], 'input': mv['input'], 'slot': mv['slot'], 'played_as': mv['kind']}
    extra = {'dead_stores': [], 'branches': [], 'bit_writes': [], 'variants': []}
    if mv['kind'] == 'rom':
        try: code, model, extra = kof_source(mv)
        except Exception as e: code, model = [{'error': repr(e)}], None
        rec['source'] = {'kind': 'rom', 'code': code, 'model': model, 'dead_stores': extra['dead_stores']}
        phases = prog_mapping(mv, model, extra)
    else:
        rec['source'] = {'kind': 'capture', 'code': 'capture', 'rows': mv['nrows'],
                         'note': MISSING.get(mid(mv), (None, [], ''))[2]}
        phases = capture_mapping(mv)
    rec['understood'] = understood(mv, phases)
    rec['mapping'] = phases
    used = sorted({ft['feature'] for ph in phases for ft in ph['features'] if ft['feature'] != 'end'})
    rec['features_used'] = used
    rec['ingestion'] = classify(mv, fx[mid(mv)], vocab)
    rec['features_missing'] = [n['component'] for n in rec['ingestion']['needs']]
    rec['fidelity'] = fidelity(mv)
    rec['branches'] = extra['branches']               # decided by the button / EX flag / facing (+ other known fields)
    rec['variants'] = extra['variants']               # one handler, several inputs: parameter sets side by side
    rec['bit_writes'] = extra['bit_writes']           # every bit write the export drops, with its meaning
    rec['bit_writes'] = list({(w['addr'], w['in'], w['write']): w for w in rec['bit_writes']}.values())   # (a loop walked twice: once)
    rec['unexplained'] = [w for w in rec['bit_writes'] if w['status'] == 'UNEXPLAINED']
    return rec

def sheet_md(s):
    L = [f"# {s['move']} ({s['game']}, played as {s['played_as']})", '', '## (a) Source']
    src = s['source']
    if src['kind'] == 'rom' and src['model']:
        L += [f"Handler {src['model']['handler']}, button {src['model']['button']}. Instruction behind each decoded op:", '', '```']
        L += [f"{c['addr']}  {c['asm']:<40} ; {c['op']}" + ('' if c['in'] == 'handler' else f"   [{c['in']}]") + (f"   << {c['note']}" if c.get('note') else '') for c in src['code']]
        L += ['```', '', f"Model (whiff): state runs [state, first, last frame] {src['model']['whiff']}"]
        if 'caught' in src['model']: L.append(f"Model (catch at frame {src['model']['catch_at']}): {src['model']['caught']}")
        L += ['', '### Branches decided by the input (button / EX flag) and the facing']
        for x in s['branches']:
            own = next((dict(zip(v['path_at'], v['path'])) for v in s['variants'] if v.get('this_sheet')), {})
            vs = lambda same: [v['input'] for v in s['variants'] if x['addr'] in v.get('path_at', []) and x['addr'] in own
                               and (dict(zip(v['path_at'], v['path']))[x['addr']] == own[x['addr']]) == same]
            L.append(f"- {x['addr']} ({x['in']}) {x['test']} = **{x['value']}** -> {x['taken']}" + (f" ({', '.join(vs(True))})" if vs(True) else '')
                     + f"; otherwise {x['other_way']}" + (f" ({', '.join(vs(False))})" if vs(False) else ''))
        if not s['branches']: L.append('- none: the handler does not test them')
        L += ['', '### Dead stores (overwritten before any frame plays: not in the mapping)']
        for r in src.get('dead_stores', []):
            L.append(f"- {r['addr']} ({r['in']}) {r['field']} = {r['value']}, overwritten at {r['overwritten_at']} by {r['by']}" + (' (same value)' if r['value'] == r['by'] else ''))
        if not src.get('dead_stores'): L.append('- none')
        L += ['', '### Bit writes the export drops']
        for w in s['bit_writes']:
            L.append(f"- {w['addr']} ({w['in']}) {w['write']}: " + (f"**UNEXPLAINED**" if w['status'] == 'UNEXPLAINED' else f"{w['name']}; effect {w['effect']}; brawler: {w['brawler']}"))
        if not s['bit_writes']: L.append('- none')
        L.append(f"Unexplained: {len(s['unexplained'])} (table: docs/kof_engine_flags.json)")
        L += ['', '### Variants (one handler, parameter sets chosen by the button / EX flag)']
        V = [v for v in s['variants'] if 'error' not in v]
        if V:
            keys = []
            for v in V: keys += [k for k in v['params'] if k not in keys]
            cell = lambda x: '/'.join(map(str, x)) if isinstance(x, list) else '-' if x is None else str(x)
            L += ['| parameter | ' + ' | '.join(f"{v['input']} ({v['strength']})" + (' *' if v['this_sheet'] else '') for v in V) + ' |', '|---' * (len(V) + 1) + '|']
            L.append('| path | ' + ' | '.join('; '.join(v['path']) for v in V) + ' |')
            L.append('| states (whiff model) | ' + ' | '.join(cell(v['states']) for v in V) + ' |')
            L.append('| objects spawned (whiff model) | ' + ' | '.join(cell(v['objects_spawned']) for v in V) + ' |')
            L.append('| hit kind | ' + ' | '.join(cell(v['hit_kind']) for v in V) + ' |')
            L.append('| whiff frames / hit openings | ' + ' | '.join(f"{v['whiff_frames']} / {v['hits']}" for v in V) + ' |')
            same = []
            for k in keys:
                vals = [v['params'].get(k) for v in V]
                if all(x == vals[0] for x in vals): same.append(f'{k} {cell(vals[0])}'); continue
                L.append(f'| {k} | ' + ' | '.join(cell(x) for x in vals) + ' |')
            L.append(f"Same in every variant: {', '.join(same) or 'nothing'}. Captured with this handler: " +
                     ', '.join(f"{v['input']} {'yes' if v['captured_same_handler'] else 'no capture' if v['captured_same_handler'] is None else 'NO (other handler)'}" for v in V) + '. (* = this sheet)')
        for v in s['variants']:
            if 'error' in v: L.append(f"- {v['input']}: decode error {v['error']}")
        if not s['variants']: L.append('- one parameter set: the handler tests neither the button nor the EX flag')
    else: L += ['capture (no handler decoder for this source): ' + str(src.get('rows')) + ' recorded rows. ' + (src.get('note') or '')]
    L += ['', '## (b) Understood'] + [f'- {u}' for u in s['understood']]
    L += ['', '## (c) Step mapping', '| phase | frames / rows | feature | parameters |', '|---|---|---|---|']
    for i, ph in enumerate(s['mapping']):
        span = ph.get('frames') or ph.get('rows') or ''
        for ft in ph['features']: L.append(f"| {i} | {span} | {ft['feature']} | {json.dumps(ft['params'])} |")
    ing = s['ingestion']
    L += ['', '## (d) Features used / missing', 'Used: ' + ', '.join(s['features_used']), 'Missing: ' + (', '.join(s['features_missing']) or 'none'),
          '', f"Ingestion class: **{ing['class']}**"]
    for n in ing['needs']: L.append(f"- {n['component']} ({n['kind']}{', extends ' + ', '.join(n['extends']) if n['extends'] else ''}): {n['spec']}")
    if ing['regression_set']: L.append(f"- regression set ({len(ing['regression_set'])} moves): " + ', '.join(ing['regression_set']))
    L += ['', '## (e) Fidelity']
    for f in s['fidelity']: L.append('- ' + json.dumps(f))
    if not s['fidelity']: L.append('- no proof output for this move')
    return '\n'.join(L) + '\n'

def main():
    args = sys.argv[1:]; out = '/data/tmp/vocab'
    if '--out' in args: i = args.index('--out'); out = args[i + 1]; del args[i:i + 2]
    want = args or ['terry:623A', 'ryo:23624C', 'kim:236C', 'haohmaru:421C']
    os.makedirs(os.path.join(out, 'sheets'), exist_ok=True)
    cl, roster, moves = load_moves()
    vocab, fx = inventory(cl, moves)
    played = [mv for mv in moves if mv['slot']]
    summary = {'moves_in_game': len(played), 'rom': sum(1 for mv in played if mv['kind'] == 'rom'),
               'recorded': sum(1 for mv in played if mv['kind'] == 'recorded'),
               'by_source': {g: sum(1 for mv in played if mv['game'] == g) for g in sorted({mv['game'] for mv in played})}}
    json.dump({'summary': summary, 'families': vocab}, open(os.path.join(out, 'vocab.json'), 'w'), indent=1)
    json.dump(RULESET, open(os.path.join(out, 'ruleset.json'), 'w'), indent=1)
    miss = missing(moves, vocab, fx)
    json.dump(miss, open(os.path.join(out, 'missing.json'), 'w'), indent=1)
    by = {mid(mv): mv for mv in moves}
    for w in want:
        mv = by[w]
        s = sheet(mv, vocab, fx)
        base = os.path.join(out, 'sheets', w.replace(':', '_').replace(' ', '_'))
        json.dump(s, open(base + '.json', 'w'), indent=1); open(base + '.md', 'w').write(sheet_md(s))
        print(f"{s['move']}: class {s['ingestion']['class']}, {len(s['mapping'])} phases, features {len(s['features_used'])}, fidelity {len(s['fidelity'])} proof(s)")
    print(json.dumps(summary))
    for fam, fs in vocab.items(): print(fam, ', '.join(f"{f['name']} {f['count']}" for f in fs))
    for d in miss['debt_plan']: print(f"debt {d['component']} ({d['kind']}): alone {d['blocked_alone']}, in build {d['retires_in_build']}, regression {d['regression_set_size']}")

if __name__ == '__main__':
    main()
