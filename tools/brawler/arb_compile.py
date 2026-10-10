#!/usr/bin/env python3
"""The ARBITRATION SHEET COMPILER (Bruno 2026-10-10: "once a game is analysed and its specials decoded and converted,
every piece — animation, special, code — should just be linked in the new version without tokens").

Bruno's sheet (Brawler Lab arbitrage.html?f=<fighter>, decisions set "<fighter>-arb", slot ids: chainlab/arbitrage.js)
names animations of the fighter's dictionary (animdict.py) per input slot. Each answered slot is classified against the
fighter's PIECE LIBRARY (tools/brawler/arb_pieces/<fighter>.json, generated here) and either LINKED (written into
game.json's roster entry, no agent needed) or UNRESOLVED (listed, never guessed):

  a  normal    a plain animation played as a normal / command normal / hop: its brawler move name (the fighter's own,
               else a spare name with roster[].moves "<name>": "$XX", export96 `slots` / export_kz moves)
  b  special   an animation of a special already decoded for the fighter (handlers98.ROM_SPECIALS programs; Kizuna's
               export_kz programs): that special's input in the slot (one special only: two candidates = a variant
               choice, unresolved)
  c  anim      an animation-only special (roster[].anim_specials "$NN": how, the Krauser mechanism) when the library
               knows its reaction (an entry's "anim_special"); else unresolved
  Piece ids (piece_ids.py, registry arb_pieces/<f>_ids.json, Bruno 2026-10-10): an answer's pieces are animations
  ("anim-A9", "$A9") or decoded pieces by id: "S-004" = that special version (class b, its input in the slot, no
  variant question: the id names one version), "T-001" = a throw (the throws are paired scripts: unresolved)
  d  -         unresolved: a pick that starts an undecoded special, a pick the library cannot place, a slot the engine
               has no field for, a changed chain length, the throws / fury script, and EVERY slot with a typed note

Slot -> roster field (the three agent-built rounds: Krauser 4261de6, Robert 591c7d0 / 74e5a04; Kim's paper gold):
  a1..aN       chain.links (presses 1..N-1) + finishers.neutral (the last press); "presses" = the chain length
  fin_fwd / fin_up / fin_down    finishers.forward / up / down_move (down: several animations = a list, back to back)
  bz_ff / dd / uu / du           blitz.<k> (a special input, "$NN", or a normal's move name); empty = no key
  sp_c / sp_fc / sp_dc           specials.D (+ uD / dfD / ufD where they followed D) / fD / dD
  air_bz_dd    air_specials.ddA;   air_sp_c / fc / dc   air_specials.C / fC / dC
  air_a        air.forward + air.straight;   air_da   air.down
  grab_hit / grab_fin            throws.hold.hit / fin
  fury / max   fury / max (a decoded special)
  no field (unresolved when changed): fin_df, air_bz_ff / uu / du, fin_back, grab_fwd, grab_back, fury_note

    python3 tools/brawler/arb_compile.py pieces FIGHTER [--game DIR] [--dict FILE]     -> arb_pieces/FIGHTER.json
    python3 tools/brawler/arb_compile.py FIGHTER [--dry-run] [--answers FILE] [--game DIR] [--dict FILE]
                                         [--compare GAME_JSON] [--no-build] [--no-check] [--out DIR]

Without --dry-run: game.json (roster entry) + docs/brawler_gold.md (a dated "sheet round" section) are written, the
game is built (make -C sdk; rm build/*.o; make -j2; bank_proof.py) and every changed slot is played in our emulator
(harness.py + the Chain Lab's training mode, 2-frame presses, one emulator process): its input, the move / special it
starts, the chosen animation's ROM frames on screen (build/bm_frames.json), a hit on the dummy for attacks. --compare
prints the compiled roster entry against another game.json's (e.g. an agent's round) field by field.
Answers: the VPS decisions store (ssh root@195.201.91.211), else --answers FILE. Dictionary: review/<f>_anims.json of
the hosted Lab (/data/brawler-lab/review on the VPS), cached in /data/tmp/arb_compile, else --dict FILE."""
import argparse, copy, datetime, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for p in (HERE, os.path.join(TOOLS, 'kof96'), os.path.join(TOOLS, 'kizuna'), os.path.join(TOOLS, 'neosdk')):
    if p not in sys.path: sys.path.insert(0, p)

VPS = 'root@195.201.91.211'
DECISIONS = '/data/brawler/feedback/decisions'
LAB_REVIEW = '/data/brawler-lab/review'
CACHE = '/data/tmp/arb_compile'
OLD_IDS = {'air_dda': 'air_bz_dd'}                         # arbitrage.js OLD_IDS: an old answer read under its new id
import piece_ids
ID_RE = piece_ids.ID_RE                                    # S-001 / T-001: a decoded piece by its id

# ---- the sheet's slots -> roster fields ----
FIN = {'fin_fwd': 'forward', 'fin_up': 'up', 'fin_down': 'down_move'}
BLITZ = {'bz_ff': 'ff', 'bz_dd': 'dd', 'bz_uu': 'uu', 'bz_du': 'du'}
SPEC = {'sp_c': 'D', 'sp_fc': 'fD', 'sp_dc': 'dD'}
FOLLOW_D = ('uD', 'dfD', 'ufD')                            # "C in any other direction = the neutral's" (the rounds)
AIRSP = {'air_bz_dd': 'ddA', 'air_sp_c': 'C', 'air_sp_fc': 'fC', 'air_sp_dc': 'dC'}
AIR = {'air_a': ('forward', 'straight'), 'air_da': ('down',)}
HOLD = {'grab_hit': 'hit', 'grab_fin': 'fin'}
NOFIELD = {'fin_df': 'the engine has no down-forward finisher (routes.py finishers: neutral / forward / up / down)',
           'air_bz_ff': 'the engine has no forward,forward air Blitz (export_bm.AIR_KEY: dd + A only)',
           'air_bz_uu': 'the engine has no up,up air Blitz (export_bm.AIR_KEY: dd + A only)',
           'air_bz_du': 'the engine has no down,up air Blitz (export_bm.AIR_KEY: dd + A only)',
           'fin_back': 'the back finisher is the throw: a paired script, not an animation',
           'grab_fwd': 'the throws are paired scripts (victim side): an agent', 'grab_back': 'the throws are paired scripts (victim side): an agent'}
ORDER = ['a%d' % i for i in range(1, 9)] + list(FIN) + ['fin_df', 'fin_back'] + list(BLITZ) + \
    ['air_bz_ff', 'air_bz_dd', 'air_bz_uu', 'air_bz_du'] + list(SPEC) + ['air_sp_c', 'air_sp_fc', 'air_sp_dc'] + \
    list(AIR) + list(HOLD) + ['grab_fwd', 'grab_back', 'fury_note', 'fury', 'max']
LABEL = {'fin_fwd': 'last hit + forward', 'fin_up': 'last hit + up', 'fin_down': 'last hit + down', 'fin_df': 'last hit + down-forward',
         'fin_back': 'last hit + back', 'bz_ff': 'forward,forward + A', 'bz_dd': 'down,down + A', 'bz_uu': 'up,up + A',
         'bz_du': 'down,up + A', 'air_bz_ff': 'air forward,forward + A', 'air_bz_dd': 'air down,down + A',
         'air_bz_uu': 'air up,up + A', 'air_bz_du': 'air down,up + A', 'sp_c': 'C', 'sp_fc': 'forward + C', 'sp_dc': 'down + C',
         'air_sp_c': 'air C', 'air_sp_fc': 'air forward + C', 'air_sp_dc': 'air down + C', 'air_a': 'jump + A',
         'air_da': 'jump + down + A', 'grab_hit': 'hold hit', 'grab_fin': 'hold finisher', 'grab_fwd': 'throw forward',
         'grab_back': 'throw back', 'fury_note': 'fury note', 'fury': 'fury (D)', 'max': 'MAX (down + D)',
         'presses': 'chain length', **{'a%d' % i: 'A press %d' % i for i in range(1, 9)}}
# spare move names for an animation the fighter has no move name for (class a): the brawler's six-button names a KOF /
# Kizuna fighter does not have natively, in the order the golds took them (Kim: atk_ab_close / atk_ab_far / atk_cd_close /
# cmd_fwd_c; Robert: atk_cd_close for $D4, atk_ab_far for $67)
SPARE = ['atk_cd_close', 'atk_ab_far', 'atk_ab_close', 'atk_cd_crouch', 'atk_ab_crouch', 'cmd_fwd_c', 'cmd_fwd_cd']
GROUND_ATK = re.compile(r'^(atk_[a-d]{1,2}_(close|far|crouch)|body_toss|cmd_\w+)$')
AIR_ATK = re.compile(r'^atk_[a-d]{1,2}_(jump|hop)(_diag)?$')
SPECIAL_INPUT = re.compile(r'^((?:MAX |EX |air )*(?:\[\d\])?\d+[A-D]+)(?=\s|$)')
GAME_KEYS = ['name', 'display', 'bank', 'watch', 'routes', 'archetype', 'scale', 'about', 'moves', 'anim_specials', 'retime',
             'chain', 'finishers', 'specials', 'blitz', 'air', 'air_specials', 'throws', 'fury', 'max']


def repo_of(game): return os.path.normpath(os.path.join(game, '..', '..'))
def fmt(p): return p if ID_RE.match(p) else '$' + p           # a pick as the sheet shows it: S-004, T-001, $A9
def token(p):
    """a sheet answer's piece -> 'S-004' / 'T-001' or an animation's hex ('anim-a9', '$A9', 'A9' -> 'A9')"""
    p = p.strip()
    return p.upper() if ID_RE.match(p.upper()) else re.sub(r'^(anim-|\$)', '', p, flags=re.I).upper()
def H(x): return '%X' % x


# ============================================================================================ inputs
def fetch_answers(f, path=None):
    """the sheet's answers {slot: {choice, pieces, note}} (the decisions store; {} = no sheet)"""
    if path: return json.load(open(path))
    r = subprocess.run(['ssh', VPS, f'cat {DECISIONS}/{f}-arb.json'], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else {}


def fetch_dict(f, path=None):
    """the fighter's animation dictionary (review/<f>_anims.json: ids, slots, states, kind, the moves that play each)"""
    if path: return json.load(open(path))
    os.makedirs(os.path.join(CACHE, 'review'), exist_ok=True)
    p = os.path.join(CACHE, 'review', f'{f}_anims.json')
    if subprocess.run(['scp', '-q', f'{VPS}:{LAB_REVIEW}/{f}_anims.json', p]).returncode != 0 and not os.path.exists(p):
        import animdict                                   # (offline: build it locally)
        animdict.build(CACHE, None, [f])
    return json.load(open(p))


def roster_of(G, f): return next(r for r in G['roster'] if r['name'] == f)


# ============================================================================================ the piece library
def native_kof(game, f, D):
    """KOF96 / 98 / 99: {anim id: [brawler move names]} from the export's own tables (export96 MOVES* state -> slot,
    CMD_NORMALS: a hop's later states -> 'hop_of'), the decoded specials {input: [anim ids]} (handlers98.ROM_SPECIALS),
    the state that selects each animation (anim_specials address a state)"""
    import rom96, export96, handlers98
    prom, _ = rom96.load(rom96.GAMES[game]['neo']); m = rom96.Mem(prom, game)
    cast, moves = {'kof97': (export96.CAST97, export96.MOVES97), 'kof98': (export96.CAST98, export96.MOVES98),
                   'kof99': (export96.CAST99, export96.MOVES99)}.get(game, (export96.CAST, export96.MOVES))
    cid = cast.index(f)
    k98 = game in ('kof97', 'kof98', 'kof99')
    mp = None if k98 else rom96.shared_map(m)
    slot_of = (lambda st: rom96.state_slot(m, cid, st)) if k98 else (lambda st: mp[st])
    by_slot = {s: a['id'] for a in D['anims'] for s in a['slots']}
    by_state = {s: a['id'] for a in D['anims'] for s in a.get('states', [])}
    def aid(st, state=True):
        if state and st in by_state: return by_state[st]
        try: return by_slot.get(slot_of(st) if state else st)
        except Exception: return None
    names, hop = {}, {}
    for mv, st in moves.items():
        a = aid(st)
        if a: names.setdefault(a, []).append(mv)
    for mv, v in export96.CMD_NORMALS.get(game, {}).get(f, {}).items():
        sts = [v[0]] + ([r[0] for r in v[2]] if len(v) > 2 else [])
        ids = list(dict.fromkeys(x for x in (aid(s) for s in sts) if x))
        if ids: names.setdefault(ids[0], []).append(mv)
        for x in ids[1:]: hop[x] = mv
    specs = {}
    if handlers98.ROM_GAME.get(f, 'kof98') == game:
        fury = None
        for inp in sorted(handlers98.ROM_SPECIALS.get(f, ())):
            for i in [inp, 'MAX ' + inp]:
                try: rom = handlers98.export_rom(m, cid, i, lambda *a: 0)
                except Exception: continue
                if 'error' in rom: continue
                ids = list(dict.fromkeys(x for x in (aid(s) for s in rom['states']) if x))
                if i.startswith('MAX ') and ids == specs.get(inp, {}).get('anims'): continue   # (no MAX path of its own)
                if i.startswith('MAX ') and any(k.startswith('MAX ') and v['anims'] == ids for k, v in specs.items()):
                    continue                           # (the same MAX path as another button's: Robert's MAX 6426A /
                                                       # 6426C, the handler's MAX branch ignores the button)
                specs[i] = {'decoded': True, 'anims': ids, 'air': i.startswith('air '), 'source': 'handlers98.ROM_SPECIALS'}
    return names, hop, specs


def native_kizuna(f, D):
    """Kizuna (export_kz): MOVES ('anim', n, 0, None) = a whole animation under a move name; the specials played as
    programs from Kizuna's handlers (PROG_MOVES, AIR) with their animations (SPECIALS, AIR, the dictionary's)"""
    import export_kz
    names, specs = {}, {}
    for mv, v in export_kz.MOVES.items():
        if v[0] == 'anim' and v[2] == 0 and v[3] is None: names.setdefault(H(v[1]), []).append(mv)
    for inp in export_kz.PROG_MOVES:
        ids = [H(n) for n in export_kz.SPECIALS.get(inp, (None, None, []))[2]]
        ids += [a['id'] for a in D['anims'] if inp in a.get('exported', []) and a['id'] not in ids and a['kind'] != 'effect-only']
        specs[inp] = {'decoded': True, 'anims': ids, 'air': False, 'source': 'export_kz.PROG_MOVES'}
    for inp, d in export_kz.AIR.items():
        specs[inp] = {'decoded': True, 'anims': [H(d[k]) for k in ('dive', 'land', 'again') if k in d], 'air': True, 'source': 'export_kz.AIR'}
    return names, {}, specs


def build_pieces(f, G, D, old=None):
    """the fighter's piece library: animation id -> class facts; specials; spare names (see the module doc). `old`: the
    previous library, whose hand-added fields (an entry's anim_special / note) are kept"""
    r = roster_of(G, f)
    game = r['bank'].split(':')[0]
    if game in ('kof96', 'kof97', 'kof98', 'kof99'): names, hop, specs = native_kof(game, f, D)
    elif game == 'kizuna': names, hop, specs = native_kizuna(f, D)
    else: raise SystemExit(f'{f}: bank {r["bank"]}: no piece library for {game} yet (the arbitration sheets need an animation dictionary: animdict.DICTS)')
    for a in D['anims']:                                   # the dictionary's captured specials (decoded or not)
        if a['kind'] == 'effect-only': continue
        ins = [mm.group(1) for mm in (SPECIAL_INPUT.match(x) for x in a.get('moves', []) if '(its projectile)' not in x) if mm] \
            if game != 'kizuna' else [x for x in a.get('exported', []) if (SPECIAL_INPUT.match(x) or x.startswith('j.')) and ' ' not in x]
        for i in ins:
            s = specs.setdefault(i, {'decoded': False, 'anims': [], 'air': i.startswith('air ') or i.startswith('j.'), 'source': 'dictionary capture'})
            if a['id'] not in s['anims']: s['anims'].append(a['id'])
    oldA = (old or {}).get('anims', {})
    anims = {}
    for a in D['anims']:
        x = a['id']
        e = {'kind': a['kind'], 'state': (a.get('states') or [None])[0], 'names': names.get(x, []),
             'specials': [i for i, s in specs.items() if x in s['anims']]}
        if x in hop: e['hop_of'] = hop[x]
        th = [n for n in a.get('exported', []) if n.startswith('throw')]   # (the throws: paired scripts, the sheet's "now")
        if th: e['throws'] = th
        o = oldA.get(x, {})
        for k in ('anim_special', 'note'):
            if o.get(k): e[k] = o[k]
        anims[x] = e
    for k, how in (r.get('anim_specials') or {}).items():     # reactions the roster already gives (an agent's decision)
        x = k[1:].upper()
        st = next((a['id'] for a in D['anims'] if int(x, 16) in a.get('states', [])), x) if game != 'kizuna' else x
        if st in anims: anims[st]['anim_special'] = how
    native = {n for v in names.values() for n in v}
    return {'fighter': f, 'bank': r['bank'], 'game': game, 'dictionary': D.get('source'),
            'about': 'arb_compile.py piece library: per animation id (the dictionary\'s, = the sheet\'s pieces) its brawler '
                     'move names (names), the specials whose program plays it (specials; decoded ones in "specials" below), '
                     'hop_of (a later state of a hop: not playable alone), state (what anim_specials "$NN" address), '
                     'anim_special (the reaction when played as an animation special: known = linkable, class c) and '
                     'note. handled: {slot: {pieces, note, by}} sheet answers with a typed note that an agent has '
                     'implemented (the same pieces + note are not listed again; a changed answer is). Regenerated from '
                     'the ROM tables + the dictionary + game.json; anim_special / note / handled entries added by hand '
                     'are kept.',
            'spare_names': [n for n in SPARE if n not in native],
            'handled': (old or {}).get('handled') or {},
            'specials': dict(sorted(specs.items())), 'anims': anims}


def pieces_path(game, f): return os.path.join(repo_of(game), 'tools', 'brawler', 'arb_pieces', f'{f}.json')


def load_pieces(game, f, G, D, write=True):
    p = pieces_path(game, f)
    old = json.load(open(p)) if os.path.exists(p) else None
    lib = build_pieces(f, G, D, old)
    if write:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, 'w') as fh: json.dump(lib, fh, ensure_ascii=False, indent=1)
        _, new = piece_ids.sync(f, lib, D, os.path.dirname(p))         # ids for the newly decoded pieces (decode order)
        if new: print(f'{f}: new piece ids {" ".join(new)} ({piece_ids.path(f, os.path.dirname(p))})')
    return lib


# ============================================================================================ the compiler
class Res:
    def __init__(s, slot, pick, note=''):
        s.slot, s.pick, s.note = slot, pick, note
        s.cls = s.status = s.value = s.field = s.why = ''
        s.check = None
    def row(s): return dict(slot=s.slot, pick=s.pick, note=s.note, cls=s.cls, status=s.status, field=s.field, value=s.value, why=s.why)


def compile_sheet(f, ans, G, lib, reg=None):
    """-> (new roster entry, [Res]): every answered slot linked / unchanged / unresolved (reg: the piece-id registry,
    piece_ids.load: S- / T- ids in the answers)"""
    reg = reg or {'pieces': {}}
    r = roster_of(G, f)
    new = copy.deepcopy(r)
    A = lib['anims']; S = lib['specials']
    mv = dict(r.get('moves') or {})
    used_names = set()                                     # names the compiled entry plays (spare names taken)
    def name_anim(n):                                      # a move name -> its animation id for this fighter
        if n in mv: return mv[n][1:].upper()
        return next((x for x, e in A.items() if n in e['names']), None)
    def pieces_of(v):                                      # a roster value -> the animations it plays (the sheet's "now")
        if not v: return []
        if isinstance(v, list): return [p for x in v for p in pieces_of(x)]
        if v.startswith('$'): return [v[1:].upper()]
        if v in S: return list(S[v]['anims'])
        if v.startswith('throw'): return [x for x, e in A.items() if v in e.get('throws', [])]
        a = name_anim(v); return [a] if a else []
    ans = dict(ans)
    for o, n in OLD_IDS.items():
        if o in ans and n not in ans: ans[n] = ans[o]
    mine = {k: v for k, v in ans.items() if isinstance(v, dict) and v.get('choice') == 1}
    out = []

    # ---- the slot's current value (the sheet's "now") ----
    links = list((r.get('chain') or {}).get('links') or [])
    fin = r.get('finishers') or {}
    n_now = len(links) + (1 if fin.get('neutral') else 0)
    chain_len = G['chain']['lengths'][r.get('archetype', 'balanced')]
    def now_val(slot):
        if slot[0] == 'a' and slot[1:].isdigit():
            k = int(slot[1:]) - 1
            seq = links + ([fin['neutral']] if fin.get('neutral') else [])
            return seq[k] if k < len(seq) else None
        if slot in FIN: return fin.get(FIN[slot])
        if slot in BLITZ: return (r.get('blitz') or {}).get(BLITZ[slot])
        if slot in SPEC: return (r.get('specials') or {}).get(SPEC[slot])
        if slot in AIRSP: return (r.get('air_specials') or {}).get(AIRSP[slot])
        if slot in AIR:
            import build_tables
            return dict(build_tables.AIR_DEFAULT, **(r.get('air') or {}))[AIR[slot][0]]
        if slot in HOLD: return ((r.get('throws') or {}).get('hold') or {}).get(HOLD[slot])
        if slot in ('fury', 'max'): return r.get(slot)
        if slot in ('fin_back', 'grab_fwd', 'grab_back'): return 'throw_c'
        return None

    # ---- class a: a normal's move name ----
    def normal(x, air=False, cur=None, spare_ok=True):
        e = A.get(x)
        if not e: return None, f'${x} is not in the dictionary'
        if e.get('hop_of'): return None, f'${x} is a later state of the hop {e["hop_of"]}: pick its first animation'
        ok = AIR_ATK if air else GROUND_ATK
        mine_ = [n for n, v in mv.items() if v[1:].upper() == x and ok.match(n)]          # the roster's own name for it
        nat = [n for n in e['names'] if ok.match(n) and n not in mv]                         # the fighter's native name
        if cur in mine_ + nat: return cur, 'its current name'
        if mine_: return mine_[0], 'roster moves'
        if nat: return nat[0], 'its own move'
        if air: return None, f'${x} has no air move name for {f} (an air normal from another animation: an agent)'
        if e['names']: return None, f'${x} is {e["names"][0]} ({e["kind"]}): not a ground attack'
        if e['kind'] != 'attack': return None, f'${x} is a {e["kind"]} animation (no attack box)'
        if not spare_ok: return None, f'${x} has no move name and no known reaction (an animation special needs one: library anim_special)'
        spare = next((n for n in lib['spare_names'] if n not in mv and n not in used_names), None)
        if not spare: return None, 'no spare move name left'
        mv[spare] = '$' + x
        return spare, f'spare name: moves "{spare}": "${x}"' + (f' (an animation of {", ".join(e["specials"])})' if e['specials'] else '')

    # ---- class b / c: a special ----
    def special(ps, air=False, slot=None):
        cands = [i for i, s in S.items() if all(p in s["anims"] for p in ps) and s["air"] == air and i.startswith("MAX ") == (slot == "max")]
        dec = [i for i in cands if S[i]['decoded']]
        if len(cands) > 1:
            return None, None, f'variant choice: {" / ".join(cands)} all play ' + ' '.join('$' + p for p in ps) + \
                (f' (decoded: {", ".join(dec)})' if dec else ' (none decoded)')
        if dec: return 'b', dec[0], f'{dec[0]} ({S[dec[0]]["source"]}' + (', its first animation' if S[dec[0]]['anims'][0] == ps[0] else
                                                                          f', plays from ${S[dec[0]]["anims"][0]}') + ')'
        if len(ps) == 1 and A.get(ps[0], {}).get('anim_special'):
            e = A[ps[0]]
            return 'c', '$' + (H(e['state']) if isinstance(e['state'], int) else ps[0]), f'animation special, reaction "{e["anim_special"]}" (library)'
        if cands: return None, None, f'{cands[0]} is not decoded (a captured special: its program is not read from the ROM yet)'
        if len(ps) == 1 and ps[0] in A and A[ps[0]]['kind'] == 'attack':
            return None, None, f'${ps[0]} plays no special: an animation special needs its reaction (library anim_special)'
        return None, None, 'the library cannot place ' + ' '.join('$' + p for p in ps)

    # ---- the chain length ----
    if 'presses' in mine:
        try: n = int(mine['presses'].get('note') or 0)
        except ValueError: n = 0
        if n and n != max(n_now, chain_len):
            x = Res('presses', str(n)); x.status = 'unresolved'; x.why = f'chain length {n} (now {max(n_now, chain_len)}, archetype {r.get("archetype")}): an agent'
            out.append(x)
    seq_new = links + ([fin['neutral']] if fin.get('neutral') else [])
    chain_changed = False
    for slot in sorted(ORDER, key=ORDER.index):
        if slot not in mine: continue
        a = mine[slot]
        ps = [token(p) for p in a.get('pieces') or []]
        x = Res(slot, ps, (a.get('note') or '').strip())
        nowv = now_val(slot); nowp = pieces_of(nowv)
        ids = [p for p in ps if ID_RE.match(p)]
        if ids:                                            # a decoded piece by its id (the Workshop's S- / T- ids)
            e = piece_ids.resolve(reg, ids[0])
            if e and e['kind'] == 'special' and e['input'] in S: x.anim0 = (S[e['input']]['anims'] or [None])[0]
            if x.note and not ((lib.get('handled') or {}).get(slot) or {}).get('note') == x.note:
                x.status, x.cls, x.why = 'unresolved', 'd', 'typed note: ' + x.note
            elif len(ps) > 1: x.status, x.cls, x.why = 'unresolved', 'd', f'{" ".join(fmt(p) for p in ps)}: a piece id plays alone in its slot'
            elif not e: x.status, x.cls, x.why = 'unresolved', 'd', f'{ids[0]} is not in {f}\'s registry (arb_pieces/{f}_ids.json)'
            elif e.get('gone'): x.status, x.cls, x.why = 'unresolved', 'd', f'{ids[0]} ({e["name"]}) is gone from the piece library'
            elif e['kind'] == 'throw': x.status, x.cls, x.why = 'unresolved', 'd', f'{ids[0]} {e["name"]}: the throws are paired scripts (victim side): an agent'
            elif nowv == e['input']: x.status, x.value, x.why = 'unchanged', nowv, f'pick = now ({ids[0]} {e["name"]})'
            elif slot in NOFIELD or slot == 'fury_note': x.status, x.cls, x.why = 'unresolved', 'd', NOFIELD.get(slot, 'the fury is a script')
            elif not (slot in BLITZ or slot in SPEC or slot in AIRSP or slot in ('fury', 'max')):
                x.status, x.cls, x.why = 'unresolved', 'd', f'{ids[0]} {e["name"]} is a special: this slot plays a normal (an animation)'
            elif (slot in AIRSP) != bool(e['air']) and not (slot == 'air_bz_dd' and e['air']):
                x.status, x.cls, x.why = 'unresolved', 'd', f'{ids[0]} {e["name"]} is a {"n air" if e["air"] else " ground"} special: not for this slot'
            elif (slot == 'max') != e['input'].startswith('MAX '):
                x.status, x.cls, x.why = 'unresolved', 'd', f'{ids[0]} {e["name"]}: ' + ('not a MAX version' if slot == 'max' else 'a MAX version plays in the MAX slot')
            else:
                v = e['input']; x.status, x.cls, x.value, x.why = 'linked', 'b', v, f'{ids[0]} {e["name"]} (registry)'
                if slot in BLITZ: new.setdefault('blitz', {})[BLITZ[slot]] = v; x.field = f'blitz.{BLITZ[slot]}'
                elif slot in SPEC:
                    sp = new.setdefault('specials', {}); old = sp.get('D')
                    sp[SPEC[slot]] = v; x.field = f'specials.{SPEC[slot]}'
                    if slot == 'sp_c':
                        fol = [k for k in FOLLOW_D if sp.get(k) == old]
                        for k in fol: sp[k] = v
                        if fol: x.field += ' (+ ' + ' '.join(fol) + ': the neutral\'s)'
                elif slot in AIRSP: new.setdefault('air_specials', {})[AIRSP[slot]] = v; x.field = f'air_specials.{AIRSP[slot]}'
                else: new[slot] = v; x.field = slot
            if x.status == 'unresolved' and not x.field: x.field = slot
            out.append(x); continue
        same = ps == nowp or (ps and nowp and len(ps) == 1 and ps[0] in nowp and isinstance(nowv, str) and (nowv in S or nowv.startswith('$')))
        x.field = slot
        hd = (lib.get('handled') or {}).get(slot)
        if x.note and hd and hd.get('note') == x.note and hd.get('pieces') == ps:
            x.status, x.value, x.why = 'unchanged', nowv, f'this answer was handled by an agent already ({hd.get("by", "library handled")})'
            out.append(x); continue
        if x.note:
            x.status, x.cls = 'unresolved', 'd'
            x.why = 'typed note: ' + x.note + (' (pick = now)' if same else '')
            out.append(x); continue
        if same:
            x.status, x.value, x.why = 'unchanged', nowv, 'pick = now'
            if isinstance(nowv, str): used_names.add(nowv)
            out.append(x); continue
        if slot in NOFIELD or slot == 'fury_note':
            x.status, x.cls, x.why = 'unresolved', 'd', NOFIELD.get(slot, 'the fury is a script')
            out.append(x); continue
        if not ps:
            if slot in BLITZ or slot in AIRSP:
                x.status, x.cls, x.value = 'linked', '-', None; x.why = 'cleared: no move here'
            else:
                x.status, x.cls, x.why = 'unresolved', 'd', 'cleared, but the engine needs a move in this slot'
            out.append(x); continue
        # chain presses + finishers + holds: normals
        if slot[0] == 'a' and slot[1:].isdigit() or slot in FIN or slot in HOLD:
            if len(ps) > 1 and slot != 'fin_down':
                x.status, x.cls, x.why = 'unresolved', 'd', 'several animations back to back: only "last hit + down" plays a list'
                out.append(x); continue
            nm = []
            for p in ps:
                n_, why = normal(p, cur=nowv if isinstance(nowv, str) else None)
                if not n_: break
                nm.append(n_); used_names.add(n_)
            if len(nm) != len(ps):
                x.status, x.cls, x.why = 'unresolved', 'd', why; out.append(x); continue
            x.status, x.cls, x.value, x.why = 'linked', 'a', (nm if len(nm) > 1 else nm[0]), why
            if slot[0] == 'a' and slot[1:].isdigit():
                k = int(slot[1:]) - 1
                while len(seq_new) <= k: seq_new.append(None)
                seq_new[k] = x.value; chain_changed = True
                x.field = f'chain.links[{k}]' if k < len(seq_new) - 1 else 'finishers.neutral'
            elif slot in FIN:
                new.setdefault('finishers', {})[FIN[slot]] = x.value; x.field = f'finishers.{FIN[slot]}'
            else:
                new.setdefault('throws', {}).setdefault('hold', {})[HOLD[slot]] = x.value; x.field = f'throws.hold.{HOLD[slot]}'
            out.append(x); continue
        if slot in AIR:
            if len(ps) > 1:
                x.status, x.cls, x.why = 'unresolved', 'd', 'one air normal per slot'; out.append(x); continue
            n_, why = normal(ps[0], air=True, cur=nowv)
            if not n_: x.status, x.cls, x.why = 'unresolved', 'd', why; out.append(x); continue
            for k in AIR[slot]: new.setdefault('air', {})[k] = n_
            x.status, x.cls, x.value, x.why, x.field = 'linked', 'a', n_, why, ' + '.join('air.' + k for k in AIR[slot])
            out.append(x); continue
        # Blitz, specials, air specials, fury: a special (or, for a Blitz, a normal's move)
        air = slot in AIRSP
        cls, v, why = special(ps, air=air, slot=slot)
        if not cls and slot in BLITZ and len(ps) == 1 and not A.get(ps[0], {}).get('specials'):
            n_, w2 = normal(ps[0], spare_ok=False)
            if n_: cls, v, why = 'a', n_, w2 + ' (a normal as the Blitz)'
            else: why = w2
        if not cls:
            x.status, x.cls, x.why = 'unresolved', 'd', why; out.append(x); continue
        if slot in ('fury', 'max') and cls != 'b':
            x.status, x.cls, x.why = 'unresolved', 'd', 'the fury / MAX must be a decoded special: ' + why; out.append(x); continue
        if slot == 'max' and not v.startswith('MAX '):
            x.status, x.cls, x.why = 'unresolved', 'd', f'{v} is not a MAX version'; out.append(x); continue
        x.status, x.cls, x.value, x.why = 'linked', cls, v, why
        if cls == 'c':
            new.setdefault('anim_specials', {})[v] = A[ps[0]]['anim_special']
        if slot in BLITZ: new.setdefault('blitz', {})[BLITZ[slot]] = v; x.field = f'blitz.{BLITZ[slot]}'
        elif slot in SPEC:
            sp = new.setdefault('specials', {}); old = sp.get('D')
            sp[SPEC[slot]] = v; x.field = f'specials.{SPEC[slot]}'
            if slot == 'sp_c':
                fol = [k for k in FOLLOW_D if sp.get(k) == old]
                for k in fol: sp[k] = v
                if fol: x.field += ' (+ ' + ' '.join(fol) + ': the neutral\'s)'
        elif slot in AIRSP: new.setdefault('air_specials', {})[AIRSP[slot]] = v; x.field = f'air_specials.{AIRSP[slot]}'
        else: new[slot] = v; x.field = slot
        out.append(x)
    for x in out:                                          # compiled to what the slot holds already: nothing to link
        if x.status == 'linked' and x.value is not None and x.value == now_val(x.slot) and not \
                (x.cls == 'a' and x.why.startswith('spare')):
            x.status, x.why = 'unchanged', f'= now ({x.why})'
    # cleared Blitz / air special slots: drop their keys
    for x in out:
        if x.status == 'linked' and x.value is None:
            if x.slot in BLITZ: (new.get('blitz') or {}).pop(BLITZ[x.slot], None); x.field = f'blitz.{BLITZ[x.slot]}'
            if x.slot in AIRSP: (new.get('air_specials') or {}).pop(AIRSP[x.slot], None); x.field = f'air_specials.{AIRSP[x.slot]}'
    if chain_changed:
        if any(v is None for v in seq_new):
            for x in out:
                if x.slot[0] == 'a' and x.slot[1:].isdigit() and x.status == 'linked':
                    x.status, x.cls, x.why = 'unresolved', 'd', 'the chain has presses no answer or roster names (the generator\'s chain): an agent'
        else:
            new.setdefault('chain', {})['links'] = seq_new[:-1]
            new.setdefault('finishers', {})['neutral'] = seq_new[-1]
    if mv != (r.get('moves') or {}): new['moves'] = mv
    for k in ('blitz', 'air_specials'):
        if k in new and not new[k]: del new[k]
    return order_keys(new, r), out


def order_keys(new, old):
    """the entry's keys in their old order, new keys after their GAME_KEYS predecessor"""
    keys = [k for k in old if k in new]
    for k in new:
        if k in keys: continue
        prev = [p for p in GAME_KEYS[:GAME_KEYS.index(k)] if p in keys] if k in GAME_KEYS else []
        keys.insert(keys.index(prev[-1]) + 1 if prev else len(keys), k)
    return {k: new[k] for k in keys}


# ============================================================================================ writing
def write_game(path, f, new):
    """rewrite only the fighter's roster entry in game.json, key by key: an unchanged key keeps its text"""
    text = open(path).read(); lines = text.split('\n')
    G = json.loads(text); old = roster_of(G, f)
    i = next(k for k, l in enumerate(lines) if re.match(r'^\s*"name": "%s",?$' % re.escape(f), l))
    ind = re.match(r'^(\s*)', lines[i]).group(1)
    s = i
    while lines[s].strip() != '{': s -= 1
    e = i
    while not re.match(r'^%s},?$' % re.escape(ind[:-1]), lines[e]): e += 1
    spans, cur = {}, None
    for k in range(s + 1, e):
        mm = re.match(r'^%s"(\w+)": ' % re.escape(ind), lines[k])
        if mm: cur = mm.group(1); spans[cur] = [lines[k]]
        else: spans[cur].append(lines[k])
    body = []
    for k, v in new.items():
        if k in old and old[k] == v and k in spans:
            t = '\n'.join(spans[k]).rstrip()
            body.append(t[:-1] if t.endswith(',') else t)
        else: body.append(f'{ind}"{k}": ' + json.dumps(v, ensure_ascii=False))
    lines[s + 1:e] = ',\n'.join(body).split('\n')
    out = '\n'.join(lines)
    assert roster_of(json.loads(out), f) == new, 'game.json rewrite mismatch'
    open(path, 'w').write(out)


def gold_section(f, display, res, date, version):
    lk = [x for x in res if x.status == 'linked']; un = [x for x in res if x.status == 'unresolved']
    def pk(x): return ' then '.join(fmt(p) for p in x.pick) if x.pick else 'empty'
    L = [f'', f'### {display}: sheet round {date} (tools/brawler/arb_compile.py, decisions set `{f}-arb`, build {version})',
         f'Compiled from the sheet without an agent: {len(lk)} slot(s) linked, {len(un)} unresolved'
         f'{" (listed for an agent, nothing guessed)" if un else ""}; slots whose pick = now not listed.']
    for x in lk: L.append(f'- {x.slot} ({LABEL.get(x.slot, x.slot)}): {pk(x)} -> {x.field} = {json.dumps(x.value, ensure_ascii=False)} — linked, class {x.cls}: {x.why}')
    for x in un: L.append(f'- {x.slot} ({LABEL.get(x.slot, x.slot)}): {pk(x)} — UNRESOLVED: {x.why}')
    return '\n'.join(L) + '\n'


# ============================================================================================ build + check
def build(game):
    repo = repo_of(game)
    for cmd in (['make', '-C', os.path.join(repo, 'sdk')],):
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    for o in os.listdir(os.path.join(game, 'build')) if os.path.isdir(os.path.join(game, 'build')) else []:
        if o.endswith('.o'): os.remove(os.path.join(game, 'build', o))
    r = subprocess.run(['make', '-j2'], cwd=game, capture_output=True, text=True)
    if r.returncode: print(r.stdout[-3000:], r.stderr[-3000:]); raise SystemExit('build failed')
    r = subprocess.run([sys.executable, os.path.join(repo, 'tools', 'brawler', 'bank_proof.py'), game], capture_output=True, text=True)
    print(r.stdout.strip().split('\n')[-1])
    if r.returncode or 'FAIL' in r.stdout: print(r.stdout[-2000:]); raise SystemExit('bank_proof failed')


def check(game, f, res, lib):
    """every linked slot played in our emulator (harness.py + the Chain Lab's training mode: P1 = the fighter vs a dummy
    that never attacks; one emulator process, 2-frame presses): its input, what starts (move name / special input),
    the chosen animation's ROM frames on screen (KOF: build/bm_frames.json vs the ROM's animation), a hit on the dummy
    for an attack animation -> [(Res, PASS | FAIL | SKIP, detail)]"""
    sys.path.insert(0, os.path.join(HERE, 'chainlab'))
    import harness
    harness.GAME = game
    from labdrive import Lab
    import export_bm
    G = json.load(open(os.path.join(game, 'game.json')))
    names = [r['name'] for r in G['roster']]
    CL = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    pool = [p['input'] for p in next(x for x in CL['fighters'] if x['name'] == f)['pool']]
    frames = json.load(open(os.path.join(game, 'build', 'bm_frames.json')))[f]
    rr = roster_of(G, f)
    want_frames = anim_frames(lib['game'], f)
    MOVES = export_bm.MOVES; M = G['meter']
    L = Lab(rom=os.path.join(game, 'brawler.neo'), game=game); b = L.b; ST = b.states
    dummy = next(n for n in ('ryo', 'terry', 'kyo') if n != f and n in names)
    L.start(names.index(f), names.index(dummy)); b.run(30); base = b.save()
    st = lambda i=0: ST[b.fget(i, 'state')]
    def what():
        s = st()
        if s == 'SPECIAL':
            six = b.fget(0, 'spec_ix'); return f'SPECIAL {pool[six] if six < len(pool) else six}'
        if s in ('ATTACK', 'AIR_ATTACK'): return f'{s} {MOVES[b.fget(0, "anim")]}'
        return s
    seq = list((rr.get('chain') or {}).get('links') or []) + [rr['finishers']['neutral']]
    def phases(x):
        """the slot's input: [(keys, wait until, max frames)] (until None = the slot's move started and, for an attack
        animation, hit); None = not scripted"""
        hits = lambda n: (lambda lg: len(lg['hits']) >= n)
        chain = lambda k: [('2:a', hits(i + 1), 40) for i in range(k)]
        if x.slot[0] == 'a' and x.slot[1:].isdigit(): return chain(int(x.slot[1:]) - 1) + [('2:a', None, 150)]
        if x.slot in FIN: return chain(len(seq) - 1) + [('2:' + {'fin_fwd': 'R', 'fin_up': 'U', 'fin_down': 'D'}[x.slot] + 'a', None, 150)]
        if x.slot in BLITZ: return [({'ff': '1:R,1:-,1:R,2:Ra', 'dd': '1:D,1:-,1:D,2:Da', 'du': '1:D,1:-,1:U,2:Ua',
                                      'uu': '1:U,1:-,1:U,2:Ua'}[BLITZ[x.slot]], None, 150)]
        if x.slot in SPEC: return [('2:' + {'D': '', 'fD': 'R', 'dD': 'D'}[SPEC[x.slot]] + 'c', None, 200)]
        if x.slot in AIRSP: return [('2:b', None, 12), ({'ddA': '1:D,1:-,1:D,2:Da', 'C': '2:c', 'fC': '2:Rc', 'dC': '2:Dc'}[AIRSP[x.slot]], None, 150)]
        if x.slot == 'air_a': return [('2:Rb', None, 14), ('2:a', None, 80)]
        if x.slot == 'air_da': return [('2:Rb', None, 14), ('2:Da', None, 80)]
        return None
    def attempt(x, v, dist, ph):
        b.load(base)
        cam = b.r(b.syms['cam_x'], 2); x0 = cam + 160
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + dist, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', 60)
        b.fset(0, 'drive', M['chunk'] * M['chunks']); b.run(2)
        lg = dict(starts=[], frames=set(), hits=[]); state = dict(hp=b.fget(2, 'hp'), prev=None)
        def step(k=''):
            b.run(1, p1=k); w = what()
            if w != state['prev'] and w.split(' ')[0] in ('ATTACK', 'AIR_ATTACK', 'SPECIAL', 'THROW'): lg['starts'].append(w)
            state['prev'] = w
            if w.endswith(' ' + v): lg['frames'].add(b.fget(0, 'shown_frame'))
            h = b.fget(2, 'hp')
            if h < state['hp']: lg['hits'].append((w, state['hp'] - h, st(2)))
            state['hp'] = h
        target = lambda lg: any(w.endswith(' ' + v) for w in lg['starts']) and \
            (A_kind(lib, anim0(x)) != 'attack' or any(h[0].endswith(' ' + v) for h in lg['hits']))
        for keys, until, n in ph:
            for part in keys.split(','):
                c, k = part.split(':')
                for _ in range(int(c)): step(k.replace('-', ''))
            for _ in range(n):
                if (until or target)(lg): break
                step()
        for _ in range(240):                             # to the move's end (its frames, its later hits)
            if st() in ('IDLE', 'WALK') and not b.fget(0, 'freeze'): break
            step()
        shown = {frames[i] for i in lg['frames'] if i < len(frames)}
        wf = want_frames.get(anim0(x))
        return dict(dist=dist, started=any(w.endswith(' ' + v) for w in lg['starts']), starts=lg['starts'][-4:],
                    anim_on_screen=bool(shown & wf) if wf else None,
                    hits=[h for h in lg['hits'] if h[0].endswith(' ' + v)][:4])
    rows = []
    for x in res:
        if x.status != 'linked' or x.value is None: continue
        v = x.value[0] if isinstance(x.value, list) else x.value
        if x.slot in HOLD: rows.append((x, 'SKIP', 'the hold is not scripted here')); continue
        ph = phases(x)
        if not ph: rows.append((x, 'SKIP', 'no input script')); continue
        atk = A_kind(lib, anim0(x)) == 'attack'
        for dist in (44, 30, 60, 80, 110):
            got = attempt(x, v, dist, ph)
            ok = got['started'] and got['anim_on_screen'] is not False and (bool(got['hits']) or not atk)
            if ok: break
        rows.append((x, 'PASS' if ok else 'FAIL', json.dumps(got)))
        print(x.slot, rows[-1][1], rows[-1][2], flush=True)
    return rows


def A_kind(lib, aid): return lib['anims'].get(aid, {}).get('kind')
def anim0(x): return getattr(x, 'anim0', None) or x.pick[0]      # the slot's first animation (an S- pick: its special's)


def anim_frames(game, f):
    """KOF: animation id -> its ROM frames as bm_frames.json writes them ('cid:frame'); {} for other banks"""
    if game not in ('kof96', 'kof97', 'kof98', 'kof99'): return {}
    import rom96, export96
    prom, _ = rom96.load(rom96.GAMES[game]['neo']); m = rom96.Mem(prom, game)
    cast = {'kof97': export96.CAST97, 'kof98': export96.CAST98, 'kof99': export96.CAST99}.get(game, export96.CAST)
    cid = cast.index(f); out = {}
    for slot in range(512):
        try: steps, _ = rom96.parse_anim(m, rom96.anim_addr(m, cid, slot))
        except Exception: continue
        out[H(slot)] = {f'{cid}:{s[1]}' for s in steps}
    return out


# ============================================================================================ main
def compare(new, other_game, f):
    o = roster_of(json.load(open(other_game)), f)
    rows = []
    for k in sorted(set(new) | set(o), key=lambda k: GAME_KEYS.index(k) if k in GAME_KEYS else 99):
        if k == 'about': continue
        a, b_ = new.get(k), o.get(k)
        if isinstance(a, dict) or isinstance(b_, dict):
            for kk in sorted(set(a or {}) | set(b_ or {})):
                x, y = (a or {}).get(kk), (b_ or {}).get(kk)
                rows.append((f'{k}.{kk}', x == y, x, y))
        else: rows.append((k, a == b_, a, b_))
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('fighter'); ap.add_argument('more', nargs='?')
    ap.add_argument('--dry-run', action='store_true'); ap.add_argument('--answers'); ap.add_argument('--dict')
    ap.add_argument('--game', default=os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler')))
    ap.add_argument('--compare'); ap.add_argument('--no-build', action='store_true'); ap.add_argument('--no-check', action='store_true')
    ap.add_argument('--no-gold', action='store_true'); ap.add_argument('--out', default=os.path.join(CACHE, 'out'))
    a = ap.parse_args()
    game = os.path.abspath(a.game)
    if a.fighter == 'pieces':
        f = a.more; G = json.load(open(os.path.join(game, 'game.json')))
        lib = load_pieces(game, f, G, fetch_dict(f, a.dict))
        print(f'{pieces_path(game, f)}: {len(lib["anims"])} animations, {len(lib["specials"])} specials '
              f'({sum(s["decoded"] for s in lib["specials"].values())} decoded), spare names {lib["spare_names"]}')
        return
    f = a.fighter
    gpath = os.path.join(game, 'game.json'); G = json.load(open(gpath))
    D = fetch_dict(f, a.dict)
    lib = load_pieces(game, f, G, D, write=not a.dry_run)
    ans = fetch_answers(f, a.answers)
    new, res = compile_sheet(f, ans, G, lib, piece_ids.load(f, os.path.dirname(pieces_path(game, f))))
    old = roster_of(G, f)
    print(f'{f}: {len([k for k in ans if k != "done"])} answered slot(s) in {f}-arb' + ('' if ans else ' (no sheet: everything = now)'))
    print(f'{"slot":<10} {"pick":<16} {"class":<5} {"status":<10} field / value / why')
    for x in sorted(res, key=lambda x: ORDER.index(x.slot) if x.slot in ORDER else -1):
        pk = ' '.join(fmt(p) for p in x.pick) if isinstance(x.pick, list) else str(x.pick)
        print(f'{x.slot:<10} {pk or "empty":<16} {x.cls or "":<5} {x.status:<10} '
              + (f'{x.field} = {json.dumps(x.value, ensure_ascii=False)}  ({x.why})' if x.status == 'linked' else x.why))
    changed = {k for k in set(new) | set(old) if new.get(k) != old.get(k)}
    print('game.json roster changes:', ', '.join(f'{k}: {json.dumps(old.get(k), ensure_ascii=False)} -> {json.dumps(new.get(k), ensure_ascii=False)}'
                                                for k in sorted(changed)) or 'none')
    if a.compare:
        rows = compare(new, a.compare, f)
        un_fields = {x.field.split(' ')[0] for x in res if x.status == 'unresolved'}
        print(f'compare with {a.compare} (roster {f}, "about" left out):')
        for k, eq, x, y in rows:
            if not eq: print(f'  DIFF {k}: compiled {json.dumps(x, ensure_ascii=False)} vs {json.dumps(y, ensure_ascii=False)}')
        print(f'  {sum(eq for _, eq, _, _ in rows)} / {len(rows)} fields equal')
    lk = [x for x in res if x.status == 'linked']; un = [x for x in res if x.status == 'unresolved']
    if not a.dry_run:
        if changed: write_game(gpath, f, new)
        if not a.no_gold and (lk or un):
            gp = os.path.join(repo_of(game), 'docs', 'brawler_gold.md')
            with open(gp, 'a') as fh: fh.write(gold_section(f, (roster_of(G, f).get('display') or f).upper(), res,
                                                           datetime.date.today().isoformat(), open(os.path.join(game, 'VERSION')).read().strip()))
        if lk and not a.no_build: build(game)
        if lk and not a.no_check:
            rows = check(game, f, res, lib)
            print(f'{"slot":<10} {"pick":<10} {"class":<5} result')
            for x, r, why in rows: print(f'{x.slot:<10} {" ".join(fmt(p) for p in x.pick):<10} {x.cls:<5} {r}  {why}')
            os.makedirs(a.out, exist_ok=True)
            json.dump([dict(x.row(), check=r, detail=why) for x, r, why in rows], open(os.path.join(a.out, f'{f}_check.json'), 'w'), indent=1, default=list)
    print(f'REPORT {f}: linked free {len(lk)}; unchanged {sum(x.status == "unchanged" for x in res)}; unresolved {len(un)}'
          + ''.join(f'\n  - {x.slot}: {x.why}' for x in un))


if __name__ == '__main__':
    main()
