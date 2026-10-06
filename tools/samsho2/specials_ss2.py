#!/usr/bin/env python3
"""Compact specials table (README): every command-list entry grouped by motion, its button variants with the measured
animations / frames / first hit (moves.json from table_ss2.py; rage-only entries from the rage captures).
    python3 specials_ss2.py > /data/neogeo_dict/samsho2/specials_table.md"""
import json
import ss2, commands_ss2 as K
M = json.load(open('/data/neogeo_dict/samsho2/moves.json'))

def main():
    print('| fighter | motion | kind | variants: button -> result, anims, frames, hit |')
    print('|---|---|---|---|')
    for c in [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 13, 14, 15]:
        norm = {r['name']: r for r in M.get(f'{c:02d}', [])}
        rage = {r['name']: r for r in M.get(f'{c:02d}_rage', [])}
        groups = {}
        for e in K.command_list(c):
            nt = e['notation'].split('('); main_ = nt[0].split()
            btn = main_[-1] if main_ and not main_[-1].isdigit() else ''
            motion = ' '.join(main_[:-1] if btn else main_)
            key = (motion, e['kind'], 'K' if btn and set(btn) <= set('CD') else 'S')
            src = rage if e['kind'] in ('ground_stand', 'behind_stand', 'opp_state_stand') else norm
            r = src.get(f"cmd{e['i']}", {})
            an = r.get('anims') or K.anims_of(K.descriptor(c, 0 if e['mode'] in (0, 255) else 1,
                                                           0 if e['kind'] in ('system', 'throw') else 1, e['result']))
            v = f"{btn or '-'}{' (charge)' if e['charge'] else ''}{' (1 proj.)' if e['one_projectile'] else ''}" \
                f"{' (unarmed)' if e['mode'] == 1 else ''} -> {e['result']}: a{'/'.join(map(str, an[:4]))}" \
                f"{(', ' + str(r['frames']) + ' f') if r.get('frames') else ''}{(', hit ' + str(r['hit'])) if r.get('hit') else ''}" \
                f"{', disarms' if r.get('p2_disarmed') else ''}{'' if r.get('start') else ' (not triggered)'}"
            groups.setdefault(key, []).append(v)
        for (motion, kind, sk), vs in groups.items():
            print(f"| {ss2.NAMES[c]} | {motion or '5'} | {kind}{' (rage)' if kind.endswith('stand') else ''} | {'; '.join(vs)} |")

if __name__ == '__main__': main()
