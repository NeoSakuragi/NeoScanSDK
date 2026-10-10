#!/usr/bin/env python3
"""PIECE KNOBS (Bruno 2026-10-10: "each special move comes with its key params and default values, adjustable in the
Assembly; clearly surface where values are overridden and offer going back to default"). The token side (decode) finds
each decoded special's key parameters here, from our own export of it; the Assembly pages tune them live (token free);
arb_compile ships them (game.json roster[].knobs); the game plays them (fighter.h gknob_t, fighter.c "knobs").

    python3 tools/brawler/knobs.py derive FIGHTER            print the knobs of every S- piece (what pieces() stores)
    python3 tools/brawler/knobs.py rows FIGHTER S-012 speed=12 hits=3    the engine rows those values give

A KNOB (arb_pieces/<f>.json "knobs": {"S-012": [knob, ...]}):
  {id, name, unit, default, min, max, step, rows: [{kind, a, match, base}], from, judgment}
  default = the ROM's value as our export plays it; min / max / step = the Assembly's range (speeds and distances up to 3x
  the default, integers by 1 when the default is one; Bruno 2026-10-10: "a decoded speed of 6, then the same piece on 3
  slots at 9, 12 and 15"); rows = the engine rows a value gives, ONE formula here and in lab.js knobRows:
      val = round(base * value / default)
  kind (fighter.h KN_*): 1 KN_SET  P_SET of register a (0 vx, 1 vy: export_bm P_REGS) whose 16.16 value is match plays val
                                   (base = match: the value scales it; a dive's two components scale together)
                         2 KN_PSPEED the special's travelling objects fly val / 256 as fast (base 256)
                         3 KN_PHITS  they hit val times (base = default: val = the value)
                         4 KN_DMG    its hits deal val / 256 of their damage (base 256, the value in %)
  from = where the default comes from in the export; judgment = true where the choice was mine (which P_SET is "the"
  rush, the damage range), not a number the export states.

Engine limits (what would break, the only hard bounds): KN_PHITS <= 255 (fighter_t.khit is a byte); KN_DMG: a hit's
damage is a byte (capped at 255 by the game); speeds have none (32-bit arithmetic; a projectile dies off screen, a rush
stops at the stage's edge, a rise past the screen top comes back down)."""
import json, math, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
for p in (HERE, os.path.join(TOOLS, 'kof96'), os.path.join(TOOLS, 'kof95')):
    if p not in sys.path: sys.path.insert(0, p)
import piece_ids

KIND = {'set': 1, 'pspeed': 2, 'phits': 3, 'dmg': 4}
REG = {'vx': 0, 'vy': 1}
HITS_MAX = 10                         # the Assembly's range (the engine's own bound: 255)
FX = 65536


def rng(default):
    """a speed / distance knob's range: 1 .. 3x its default (at least default + 3), integer steps when it is one"""
    whole = abs(default - round(default)) < 1e-9
    step = 1 if whole else 0.25
    hi = math.ceil(max(3 * default, default + 3) / step) * step
    return {'min': 1 if default >= 1 else step, 'max': hi, 'step': step}


def num(v): return int(round(v)) if abs(v - round(v)) < 1e-9 else round(v, 4)


def knob_rows(k, value):
    """the engine rows (fighter.h gknob_t minus slot / spec) a knob's value gives: [{kind, a, match, val}]"""
    return [{'kind': r['kind'], 'a': r['a'], 'match': r['match'], 'val': int(round(r['base'] * value / k['default']))} for r in k['rows']]


def derive_rom(rom):
    """a decoded KOF special (handlers98.export_rom) -> its knobs"""
    out = []
    ops = rom['ops']
    own = (rom.get('variants') or [{}])[0].get('fields', {})
    def own_vals(key):
        v = own.get(key, [])
        return [x for x in (v if isinstance(v, list) else [v]) if isinstance(x, (int, float)) and abs(x) < 1000]
    moves = any(o[0] in ('move', 'fricmove') for o in ops)
    falls = any(o[0] == 'fall' for o in ops)
    sets = [(i, o[1], o[2]) for i, o in enumerate(ops) if o[0] == 'set' and o[1] in REG]
    # a dive: vx > 0 then vy < 0 set back to back, the same magnitude (a polar speed: KOF's angle table)
    dive = next(((a, b) for (i, ra, a), (j, rb, b) in zip(sets, sets[1:]) if j == i + 1 and ra == 'vx' and rb == 'vy'
                 and a > 0 and b < 0 and abs(a + b) < 0.01), None)
    if dive and moves:
        sp = math.hypot(*dive); d = num(round(sp, 2))
        out.append(dict(id='dive', name='Dive speed', unit='px/frame', default=d, **rng(d),
                        rows=[{'kind': KIND['set'], 'a': REG['vx'], 'match': round(dive[0] * FX), 'base': round(dive[0] * FX)},
                              {'kind': KIND['set'], 'a': REG['vy'], 'match': round(dive[1] * FX), 'base': round(dive[1] * FX)}],
                        sfrom=f'P_SET vx {dive[0]:.4f} / vy {dive[1]:.4f} (its polar speed, {sp:.2f} px a frame at 45 degrees)', judgment=False))
    if moves and not dive:
        vxs = [v for _, r, v in sets if r == 'vx' and v > 0 and any(abs(v - x) < 1e-4 for x in own_vals('+$50'))]
        if vxs:
            v = max(vxs); d = num(v)
            out.append(dict(id='travel', name='Travel speed', unit='px/frame', default=d, **rng(d),
                            rows=[{'kind': KIND['set'], 'a': REG['vx'], 'match': round(v * FX), 'base': round(v * FX)}],
                            sfrom=f'P_SET vx {v} (its forward speed, KOF +$50)', judgment=len(set(vxs)) > 1))
    if falls:
        vys = [v for _, r, v in sets if r == 'vy' and v > 0 and any(abs(v - x) < 1e-4 for x in own_vals('+$58'))]
        if vys:
            v = max(vys); d = num(v)
            out.append(dict(id='rise', name='Rise speed', unit='px/frame up', default=d, **rng(d),
                            rows=[{'kind': KIND['set'], 'a': REG['vy'], 'match': round(v * FX), 'base': round(v * FX)}],
                            sfrom=f'P_SET vy {v} (its take-off speed, KOF +$58; the height grows with its square)', judgment=len(set(vys)) > 1))
    obj = next((o for o in rom.get('objects', []) if o['kind'] == 1 and not o['follow'] and len(o['rows']) > 1), None)
    if obj:
        xs = [r[1] for r in obj['rows']]
        dl = sorted({round(b - a, 3) for a, b in zip(xs, xs[1:])})
        d = num(dl[0] if len(dl) == 1 else (xs[-1] - xs[0]) / (len(xs) - 1))
        out.append(dict(id='speed', name='Projectile speed', unit='px/frame', default=d, **rng(d),
                        rows=[{'kind': KIND['pspeed'], 'a': 0, 'match': 0, 'base': 256}],
                        sfrom=f'its object\'s rows: x +{d} px a frame (handlers98 object_rows)', judgment=len(dl) != 1))
        if not obj.get('next') and not obj.get('hits_list'):
            h = obj.get('phase_hits') or obj.get('hits') or 1
            out.append(dict(id='hits', name='Projectile hits', unit='hits', default=h, min=1, max=HITS_MAX, step=1,
                            rows=[{'kind': KIND['phits'], 'a': 0, 'match': 0, 'base': h}],
                            sfrom='its object: one hit ends it (KOF +$138 not counted)' if h == 1 else f'its object: {h} hits (KOF +$138)',
                            judgment=False))
    out.append(dict(id='damage', name='Damage', unit='%', default=100, min=10, max=300, step=10,
                    rows=[{'kind': KIND['dmg'], 'a': 0, 'match': 0, 'base': 256}],
                    sfrom='every hit it deals (the export\'s per-hit damage x the tier)', judgment=True))
    for k in out: k['from'] = k.pop('sfrom')
    return out


def derive(f, reg=None):
    """{S- id: [knob]} for every decoded special piece of fighter f (a KOF fighter: handlers98.export_rom; another game:
    none yet)"""
    reg = reg or piece_ids.load(f)
    import export96, handlers98, rom96
    game = handlers98.ROM_GAME.get(f, 'kof98')
    cast = {'kof97': export96.CAST97, 'kof98': export96.CAST98, 'kof99': export96.CAST99}.get(game, export96.CAST)
    if f not in cast: return {}
    prom, _ = rom96.load(rom96.GAMES[game]['neo']); m = rom96.Mem(prom, game)
    cid = cast.index(f); out = {}
    for pid, p in sorted(reg['pieces'].items()):
        if p['kind'] != 'special' or p.get('gone') or p.get('source') != 'handlers98.ROM_SPECIALS': continue
        try: rom = handlers98.export_rom(m, cid, p['input'], lambda *a, **k: 0, game=game)
        except Exception as e: print(f'knobs: {f} {pid} {p["input"]}: {e}'); continue
        if 'error' in rom: continue
        out[pid] = derive_rom(rom)
    return out


# the arbitration sheet's slots in fighter.h LS_* order (= chainlab/lab.js LAB_SLOTS); 'queue' = LS_QUEUE (the Try queue)
LAB_SLOTS = ['fin_fwd', 'fin_up', 'fin_down', 'fin_df', 'fin_back', 'bz_ff', 'bz_dd', 'bz_uu', 'bz_du',
             'air_bz_ff', 'air_bz_dd', 'air_bz_uu', 'air_bz_du', 'sp_c', 'sp_fc', 'sp_dc', 'air_sp_c', 'air_sp_fc', 'air_sp_dc',
             'air_a', 'air_da', 'grab_hit', 'grab_fin', 'grab_fwd', 'grab_back', 'fury', 'max']
LS_QUEUE = 0xFE
# the slots a shipped knob may sit on: those the normal game starts with their slot known (fighter.c knob_slot /
# pend_kslot: the C specials, the Blitz, the air specials) AND arb_compile's knob_check plays (KNOB_KEYS); the fury / MAX,
# the finishers and the grab slots take knobs in the Lab (the TRY blob) but do not ship yet
SHIP_SLOTS = ['sp_c', 'sp_fc', 'sp_dc', 'bz_ff', 'bz_dd', 'bz_uu', 'bz_du', 'air_sp_c', 'air_sp_fc', 'air_sp_dc', 'air_bz_dd']


def library(f):
    """(the knob catalogue {S- id: [knob]}, the id registry) of fighter f (arb_pieces: the data every tool reads)"""
    p = os.path.join(HERE, 'arb_pieces', f + '.json')
    lib = json.load(open(p)) if os.path.exists(p) else {}
    return lib.get('knobs') or {}, piece_ids.load(f)


def bounds(k):
    """a knob's rows with their engine value bounds: [(row, vmin, vmax)] (its min and max values expanded)"""
    lo, hi = knob_rows(k, k['min']), knob_rows(k, k['max'])
    return [(r, min(a['val'], b['val']), max(a['val'], b['val'])) for r, a, b in zip(k['rows'], lo, hi)]


def check_roster(name, lib_name, knobs, pool):
    """game.json roster[].knobs {slot: {S- id: {knob id: value}}} -> the engine rows [(slot, spec, kind, a, match, val)];
    raises ValueError with a plain reason on anything the catalogue does not allow"""
    cat, reg = library(lib_name)
    out = []
    for slot, per in (knobs or {}).items():
        if slot not in SHIP_SLOTS: raise ValueError(f'{name}: knobs.{slot}: knobs ship only on {", ".join(SHIP_SLOTS)}')
        for pid, vals in per.items():
            p = reg['pieces'].get(pid)
            if pid not in cat or not p: raise ValueError(f'{name}: knobs.{slot}.{pid}: no knobs for that piece (arb_pieces/{lib_name}.json)')
            if p['input'] not in pool: raise ValueError(f'{name}: knobs.{slot}.{pid} ({p["input"]}): not in its pool ({" ".join(pool)})')
            ks = {k['id']: k for k in cat[pid]}
            for kid, v in vals.items():
                k = ks.get(kid)
                if not k: raise ValueError(f'{name}: knobs.{slot}.{pid}.{kid}: {pid} has no such knob ({", ".join(ks)})')
                if not isinstance(v, (int, float)) or not k['min'] <= v <= k['max']:
                    raise ValueError(f'{name}: knobs.{slot}.{pid}.{kid} = {v}: outside {k["min"]}..{k["max"]} {k["unit"]}')
                for r in knob_rows(k, v): out.append((LAB_SLOTS.index(slot), pool.index(p['input']), r['kind'], r['a'], r['match'], r['val']))
    return sorted(out, key=lambda x: (x[0], x[1]))


def c_tables(g, build, slot_sec):
    """game_tables.c / .h: gknob_rom[BC_COUNT] (the shipped rows, roster[].knobs) and gkcat_rom[BC_COUNT] (the catalogue
    the game checks a TRY blob's rows against), per roster fighter; the shell's slot: its own arrays in .labslot"""
    pools = {f['name']: [p['input'] for p in f['pool']] for f in json.load(open(os.path.join(build, 'chainlab.json')))['fighters']}
    c, kn, kc = [], [], []
    c.append('static const gknob_t gknob_none[1] = { { 0, 0, KN_END, 0, 0, 0 } };')
    c.append('static const gkcat_t gkcat_none[1] = { { 0, KN_END, 0, 0, 0, 0, 0 } };')
    for i, r in enumerate(g['roster']):
        n, lib_name = r['name'], r.get('slot_of') or r['name']
        sec = slot_sec if r.get('slot_of') else ''
        pool = pools.get(n, [])
        try: rows = check_roster(n, lib_name, r.get('knobs'), pool)
        except ValueError as e: raise SystemExit('knobs: ' + str(e))
        cat, reg = library(lib_name)
        crow = []
        for pid, ks in sorted(cat.items()):
            p = reg['pieces'].get(pid)
            if not p or p['input'] not in pool: continue
            for k in ks:
                for rw, lo, hi in bounds(k): crow.append((pool.index(p['input']), rw['kind'], rw['a'], rw['match'], lo, hi))
        if rows or sec:
            c.append(f'static const gknob_t gknob_{i}[{len(rows) + 1}]{sec} = {{ ' + ''.join(
                f'{{ {s}, {sp}, {k}, {a}, {m}, {v} }}, ' for s, sp, k, a, m, v in rows) + '{ 0, 0, KN_END, 0, 0, 0 } };   /* ' + n + ' */')
            kn.append(f'gknob_{i}')
        else: kn.append('gknob_none')
        if crow or sec:
            c.append(f'static const gkcat_t gkcat_{i}[{len(crow) + 1}]{sec} = {{ ' + ''.join(
                f'{{ {sp}, {k}, {a}, 0, {m}, {lo}, {hi} }}, ' for sp, k, a, m, lo, hi in crow) + '{ 0, KN_END, 0, 0, 0, 0, 0 } };   /* ' + n + ' */')
            kc.append(f'gkcat_{i}')
        else: kc.append('gkcat_none')
    c.append('const gknob_t *const gknob_rom[BC_COUNT] = { ' + ', '.join(kn) + ' };   /* (fighter.c "knobs") roster[].knobs */')
    c.append('const gkcat_t *const gkcat_rom[BC_COUNT] = { ' + ', '.join(kc) + ' };   /* the knob catalogue (arb_pieces "knobs") */')
    return c


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == 'derive':
        for pid, ks in derive(a[1]).items():
            print(pid, piece_ids.load(a[1])['pieces'][pid]['name'])
            for k in ks: print(f"   {k['id']:8} {k['name']:17} {k['default']} {k['unit']} [{k['min']}..{k['max']} by {k['step']}]"
                               f"{' (judgment)' if k['judgment'] else ''}  {k['from']}")
    elif len(a) >= 3 and a[0] == 'rows':
        lib = json.load(open(os.path.join(HERE, 'arb_pieces', a[1] + '.json')))
        ks = {k['id']: k for k in lib.get('knobs', {}).get(a[2], [])}
        for kv in a[3:]:
            n, v = kv.split('='); print(n, knob_rows(ks[n], float(v)))
    else: print(__doc__)


if __name__ == '__main__': main()
