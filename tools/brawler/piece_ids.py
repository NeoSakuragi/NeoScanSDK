#!/usr/bin/env python3
"""PIECE IDS (Bruno 2026-10-10, binding): the stable names of a fighter's pieces in the Brawler Lab.

  $NN     an animation: its index in the fighter's animation table (the dictionary's id, as the sheets always wrote it)
  S-001   a decoded SPECIAL VERSION (light / heavy / EX / MAX, ground and air: each version is its own piece)
  T-001   a decoded THROW / grab / command grab

S- and T- ids are per fighter, numbered in decode order, never renumbered and never reused (a piece the library loses
keeps its id, marked "gone"). The input is data on the piece, never in the id: a ground and an air special can share a
command. The REGISTRY tools/brawler/arb_pieces/<fighter>_ids.json is the source of truth; arb_compile.py reads it (a
sheet answer "S-004" links that special) and assigns ids to newly decoded pieces whenever it refreshes the piece library
(`arb_compile.py pieces <f>`, every real run); tools/brawler/workshop.py `unlock` assigns one by hand.

Registry: {fighter, about, next: {S, T}, pieces: {id: {kind: special | throw, input, name, air, move (throws: the
export's throw_c / throw_d), source, assigned, gone?}}}. `input` is the piece library's key (arb_pieces/<f>.json
"specials": "623C", "EX 624D", "MAX 23624C", "air 214D"; Kizuna "[2]8C", "j.2B") for a special, the throw's command for a
throw ("forward + C")."""
import datetime, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, 'arb_pieces')
ID_RE = re.compile(r'^([ST])-(\d{3,})$')
THROW_ORDER = ['throw_c', 'throw_d', 'throw_big', 'throw_x']   # export_bm.THROWS (+ the third grab where a fighter has
                                                            # one, + the throw of a big victim: SS2, export_bm BIG_THROW)
THROW_INPUT = {'throw_c': 'forward + C', 'throw_d': 'forward + D', 'throw_x': 'forward + A+B',
               'throw_big': 'forward / back + A on a big victim'}
ABOUT = ('Piece ids (tools/brawler/piece_ids.py): S-NNN = a decoded special version, T-NNN = a decoded throw / grab; '
         'per fighter, in decode order, never renumbered or reused. The source of truth for arb_compile.py and the '
         'Workshop page (brawler-lab/workshop.html?f=<fighter>). Animations keep their $NN.')


def path(f, d=DIR): return os.path.join(d, f'{f}_ids.json')


def load(f, d=DIR):
    p = path(f, d)
    if os.path.exists(p): return json.load(open(p))
    return {'fighter': f, 'about': ABOUT, 'next': {'S': 1, 'T': 1}, 'pieces': {}}


def save(reg, d=DIR):
    os.makedirs(d, exist_ok=True)
    with open(path(reg['fighter'], d), 'w') as fh: json.dump(reg, fh, ensure_ascii=False, indent=1)


def by_input(reg, kind):
    """{input: id} for one kind (special / throw), live pieces only"""
    return {p['input']: i for i, p in reg['pieces'].items() if p['kind'] == kind and not p.get('gone')}


def resolve(reg, token):
    """'S-004' / 'T-001' -> the registry entry (+ 'id'), else None"""
    p = reg['pieces'].get(token)
    return dict(p, id=token) if p else None


# ---- names from the dictionary (review/<f>_anims.json: KOF's "<input> <Name>" move strings) ----
def special_name(inp, D):
    """'MAX 23624C' -> 'Ryuuko Ranbu MAX, C version'; no name in the dictionary (Kizuna) -> the input"""
    nm = None
    for a in (D or {}).get('anims', []):
        for s in a.get('moves', []):
            if s.startswith(inp + ' ') and '(its projectile)' not in s and not s[len(inp) + 1:].startswith('('):
                nm = s[len(inp) + 1:].strip(); break          # (Kizuna's "214B (air)": a variant note, not a name)
        if nm: break
    if not nm: return inp
    if inp.startswith('EX ') and 'EX' not in nm.split(): nm += ' EX'
    if inp.startswith('air ') and 'air' not in nm.lower(): nm += ' (air)'
    btn = re.search(r'(?<![A-D])([A-D]{1,2})$', inp)       # (SS2's versions: A / B / A+B, C / D / C+D; a B+C+D one: none)
    return f'{nm}, {"+".join(btn.group(1))} version' if btn else nm


def throw_name(move, aid, D):
    """the throw's name from its animation's move string ('throw (forward + C, Ryuuchou Kyaku)' -> 'Ryuuchou Kyaku',
    Kizuna '6C (throw)' -> 'Throw (6C / 4C)')"""
    a = next((x for x in (D or {}).get('anims', []) if x['id'] == aid), None)
    for s in (a or {}).get('moves', []):
        m = re.match(r'^throw \(([^,)]+)(?:, ([^)]+))?\)$', s)
        if m: return m.group(2) or f'Throw, {m.group(1)}'
    ks = [s.split(' (')[0] for s in (a or {}).get('moves', []) if s.endswith('(throw)')]
    if ks: return 'Throw (' + ' / '.join(ks) + ')'
    return {'throw_c': 'Throw C', 'throw_d': 'Throw D', 'throw_x': 'Grab'}.get(move, move)


def throw_input(lib, mv):
    """a throw's input as the registry keys it: the game's own words (lib throw_inputs: SS2's), else THROW_INPUT"""
    return (lib.get('throw_inputs') or {}).get(mv) or THROW_INPUT.get(mv, mv)


def decoded_throws(lib):
    """the library's decoded throws in THROW_ORDER: [(move, first animation id)] (an animation the export plays as
    throw_c / throw_d: its paired script is decoded)"""
    got = {}
    for x, e in lib['anims'].items():
        for t in e.get('throws', []):
            got.setdefault(t, x)
    return [(t, got[t]) for t in THROW_ORDER if t in got] + sorted((t, x) for t, x in got.items() if t not in THROW_ORDER)


def assign(reg, kind, inp, name, **extra):
    """the next id of kind ('S' / 'T') for this input (its existing id if it has one: never two ids for one piece)"""
    k = 'special' if kind == 'S' else 'throw'
    old = by_input(reg, k).get(inp)
    if old: return old, False
    gone = next((i for i, p in reg['pieces'].items() if p['kind'] == k and p['input'] == inp and p.get('gone')), None)
    if gone:                                                # decoded again: the same id comes back (never reused for another)
        reg['pieces'][gone].pop('gone', None); return gone, True
    n = reg['next'][kind]; reg['next'][kind] = n + 1
    i = f'{kind}-{n:03d}'
    reg['pieces'][i] = dict(kind=k, input=inp, name=name, **extra, assigned=datetime.date.today().isoformat())
    return i, True


def sync(f, lib, D=None, d=DIR, write=True):
    """ids for every decoded special version and throw of the piece library that has none (library order: the
    specials sorted by input, the throws in THROW_ORDER); pieces the library no longer has are marked gone, never
    dropped. -> (registry, [new ids])"""
    reg = load(f, d); new = []
    for inp, s in lib['specials'].items():
        if not s['decoded']: continue
        i, made = assign(reg, 'S', inp, special_name(inp, D), air=bool(s['air']), source=s.get('source'))
        if made: new.append(i)
    tin = dict(THROW_INPUT, **(lib.get('throw_inputs') or {}))   # (a game's own words for its throws: SS2's)
    for mv, aid in decoded_throws(lib):
        i, made = assign(reg, 'T', tin.get(mv, mv), throw_name(mv, aid, D), move=mv, source='export throws')
        if made: new.append(i)
    live_s = {i for i, s in lib['specials'].items() if s['decoded']}
    live_t = {tin.get(m, m) for m, _ in decoded_throws(lib)}
    lost = 0
    for i, p in reg['pieces'].items():
        if (p['input'] not in (live_s if p['kind'] == 'special' else live_t)) and not p.get('gone'): p['gone'] = True; lost += 1
    if write and (new or lost or not os.path.exists(path(f, d))): save(reg, d)
    return reg, new
