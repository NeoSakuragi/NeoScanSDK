#!/usr/bin/env python3
"""TODO #164: every projectile's impact height (its end rows, bpend_t) against its flight's height (bprow_t), read
from an export (build/bm_spec.c), before and after the rule "an end plays where its hit was" (bpend_t y = height from
the impact's; fighter.c proj_row / proj_hit p->py0).

    python3 impact164.py OLD_BM_SPEC NEW_BM_SPEC [OUT.json]

Per projectile with an end (fighter, table name): the flight's heights (min..max), the end's first height as drawn
(old: absolute; new: the hit's height + the row's), and whether the old one drew its impact elsewhere than the hit
(the mismatches #164 fixed: an end at 0 under a flight at 88 / 96 = Krauser's Blitz Ball and Kaiser Wave read from the
ROM, Rugal's Reppuken...)."""
import json, re, sys

def tables(path):
    t = open(path).read()
    rows = {m.group(1): [tuple(int(v) for v in r) for r in re.findall(r'\{(\d+), (-?\d+), (-?\d+), \{', m.group(2))]
            for m in re.finditer(r'static const bprow_t (\w+)\[\] = \{(.*?)\};\n', t)}
    ends = {m.group(1): [tuple(int(v) for v in r) for r in re.findall(r'\{(\d+), (-?\d+), (-?\d+)\}', m.group(2))]
            for m in re.finditer(r'static const bpend_t (\w+)\[\] = \{(.*?)\};\n', t)}
    projs = []
    for m in re.finditer(r'static const bproj_t (\w+)(?:\[\])? = \{?(.*?)\}?;\n', t):
        for e in re.finditer(r'\{(\d+), (\d+), (\d+), (\d+), \d+, \d+, \d+, (\d+), -?\d+, -?\d+, -?\d+, (\w+), (\w+),', m.group(2)):
            nrows, loop, nend, kind, follow, r, en = e.groups()
            if int(nend) and r in rows and en in ends:
                projs.append({'name': m.group(1), 'rows': r, 'end': en, 'kind': int(kind), 'follow': int(follow),
                              'flight_y': sorted({y for f, x, y in rows[r]}), 'end_y': [y for f, x, y in ends[en][:int(nend)]]})
    return projs

def main(old, new, out=None):
    o, n = {p['name'] + ':' + p['rows']: p for p in tables(old)}, {p['name'] + ':' + p['rows']: p for p in tables(new)}
    res = []
    for k, p in n.items():
        q = o.get(k)
        fy = p['flight_y']
        new_first = [fy[0] + p['end_y'][0], fy[-1] + p['end_y'][0]]          # the hit's height + the end's first row
        old_first = q['end_y'][0] if q else None                              # (old: absolute)
        res.append({'projectile': k, 'flight_height': [fy[0], fy[-1]], 'end_first_old': old_first,
                    'end_first_new': new_first if fy[0] != fy[-1] else new_first[0],
                    'old_mismatch': q is not None and not (fy[0] <= old_first <= fy[-1]) and abs(old_first - fy[0]) > 2})
    res.sort(key=lambda r: (not r['old_mismatch'], r['projectile']))
    for r in res: print(json.dumps(r))
    print(f"{len(res)} projectiles with an end; {sum(r['old_mismatch'] for r in res)} drew their impact away from the hit's height before")
    if out: json.dump(res, open(out, 'w'), indent=1)

if __name__ == '__main__':
    main(*sys.argv[1:])
