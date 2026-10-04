#!/usr/bin/env python3
"""Mechanical check of the brawler's specials: per fighter, its ground specials as export_bm plays them.

    python3 check_specials.py [--all] [game:name ...]      (default: CHARS of examples/brawler/Makefile)

Per special: rows, rows with a body attack box (atk), hit windows (hits: rows that open a new hit, export_bm
special_rows; with a continuation: hits of the whiff + of the continuation), the hits the game landed in its
close-range capture (game: drops of P2's life, '-' = no close capture; a projectile's counts too), the first row of the
hit-confirmed continuation (cont), rows with objects (obj), its projectile (proj: object kind @ spawn row, free-flight
travel; the script's objects are effects without a box since 2026-10-04), states visited,
rows whose animation step was not found in the ROM (nostep: their boxes come from the frame lookup). Picked specials (D / fwd+D / down+D /
up+D, pick_specials) always; --all adds every other normal ground special. FLAG = nothing in it can hit.
Scripts as played (export_bm.special_play): the game's contact freezes found / rows removed / impact rows with the
opponent's reaction measured after them, then every hit the brawler opens: row, reaction (H heavy = stays on the
ground, K knockdown, U launch), damage."""
import os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import export_bm, export96

def chars_from_makefile():
    mk = open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'Makefile')).read()
    return re.search(r'^CHARS\s*=\s*(.+)$', mk, re.M).group(1).split()

def main(args):
    full = '--all' in args; specs = [a for a in args if not a.startswith('--')] or chars_from_makefile()
    games = {}
    for s in specs: g, n = s.split(':'); games.setdefault(g, []).append(n)
    tmp = os.path.join('/tmp', 'check_specials'); flagged = 0
    print(f'{"fighter":10} {"role":6} {"input":14} {"rows":>4} {"atk":>4} {"hits":>6} {"game":>4} {"cont":>4} {"obj":>4} {"proj":>12} {"states":>6} {"nostep":>6}')
    for g, names in games.items():
        ex = export96.export(names, tmp, g, only={'idle', 'specials'})
        for n in names:
            ch = ex['characters'][n]
            picked = export_bm.pick_specials(ch, n)
            rows = [(role, sp) for role, sp in zip(('D', 'fwd+D', 'down+D', 'up+D'), picked) if sp]
            if full:
                rows += [('-', sp) for sp in ch['specials'] if sp['condition'] == 'normal' and not sp['input'].startswith('air')
                         and sp not in picked]
            for role, sp in rows:
                sp = export_bm.special_play(sp); sr = export_bm.special_rows(sp)
                atk = sum(1 for r in sr if r[1]); cont = sp.get('cont', 0)
                hits = sum(1 for r in sr if r[2] & 2 and not r[2] & 8)
                if cont: hits = f'{sum(1 for i, r in enumerate(sr) if r[2] & 2 and not r[2] & 8 and i < cont)}+{sum(1 for i, r in enumerate(sr) if r[2] & 2 and i >= cont)}'
                game = sp.get('game_hits', -1)
                obj = sum(1 for r in sp['script'] if r[3])
                pjs = sp['projectiles'] if export_bm.real_projectile(sp) else []   # bspec_t.proj: kind @ spawn row
                pj = pjs[0] if pjs else None
                proj = ('+'.join(f'k{q["kind"]}@{q["spawn_row"]}' for q in pjs) + f' {pj["travel"]:.0f}px') if pj else '-'
                nostep = sum(1 for r in sp.get('row_steps', []) if r[2] < 0)
                flag = not atk and not pj
                flagged += flag and role != '-'
                print(f'{n:10} {role:6} {sp["input"]:14} {len(sp["script"]):4} {atk:4} {hits:>6} {game if game >= 0 else "-":>4} {cont:4} {obj:4} {proj:>12} '
                      f'{len(sp["states"]):6} {nostep:6}' + ('  FLAG: nothing hits' if flag else ''))
                st = sp['stats']; R = '-LHKU'                # reactions: L light, H heavy (grounded), K knockdown, U launch
                if st['freezes'] or sp['objreact'] is not None:
                    print(f'{"":17} freezes {st["freezes"]}, rows removed {st["removed"]}, impacts at rows {st["impacts"]} '
                          f'(opponent {st["contact"]} px ahead at the first) '
                          f'reacting {"".join(R[r + 1] if r is not None else "?" for r in st["reactions"])}'
                          + (f', objects {R[sp["objreact"] + 1]}' if sp['objreact'] is not None else ''))
                print(f'{"":17} hits: ' + ' '.join(f'{i}{R[(r[2] >> 5) + 1]}{r[3]}' for i, r in enumerate(sr) if r[2] & 2))
    print(f'{flagged} picked specials without a hitting row')
    return flagged

if __name__ == '__main__':
    sys.exit(1 if main(sys.argv[1:]) else 0)
