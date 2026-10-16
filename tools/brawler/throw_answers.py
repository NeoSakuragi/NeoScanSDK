#!/usr/bin/env python3
"""Bruno's throw review answers -> game data (note 20261016-045300-e03d round 2: "Throws should be case by case").

The page (review.html?q=throws, review.js "the throw review", data tools/brawler/throw_review.py) saves one answer per
throw in the feedback service's decisions store, set "throws", id "<fighter>-<fwd | back | holdb>":
  choice 0 IMPACT / 1 SLAM / 2 "None of these" (label: the same in words), note (typed or spoken),
  flags "dmg-N" (the damage frame), "eject-N" (an IMPACT's eject frame; none: its damage frame), "glue-N" (optional:
  the victim glued until frame N), N = the frame number as the page shows it (1-based, the throw's first frame = 1).
This turns each answered IMPACT / SLAM into game.json roster[].throws.timing.<forward | back | hold_b> =
  {kind, damage_row, eject_row?, glue_row?, from}: the frames mapped to the throw's script rows through the capture the
page showed (OUT/review/throws/<id>.json: the victim's row on each frame; past the victim's script, the row its script
would have reached at its speed). build_tables.py (throw_timing) -> gthrow_tm -> fighter.c throw_start: the damage lands on
damage_row, the victim is the engine's body from its hand-off row (IMPACT: eject_row, else damage_row, not before glue_row;
SLAM: glue_row, else the throw_handoff rule). A throw with no answer keeps the 0.10.129 rule (fighter.c slam_row).
"None of these" and a grab special (Hanzo's Mozu Otoshi: no paired script) are listed, not written.

    python3 tools/brawler/throw_answers.py pull [OUT.json]                 the set from the VPS (default: stdout)
    python3 tools/brawler/throw_answers.py apply GAME_DIR SITE_DIR [ANSWERS.json] [--dry]
        SITE_DIR: where throw_review.py wrote review/throws/ (the capture the answers were given on); ANSWERS.json: a
        pulled set (default: pulled now). Prints each throw's mapping and the game.json diff; --dry writes nothing."""
import datetime, difflib, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_tables as BT

VPS = 'root@195.201.91.211'
BASE = 'http://127.0.0.1:8920/api/'                  # the feedback service on the box (ssh = authenticated)
SET = 'throws'
KIND = {0: 'impact', 1: 'slam'}
KEY = {'fwd': 'forward', 'back': 'back', 'holdb': 'hold_b'}   # the page's row id -> throws.timing key (gamedata.h TM_*)


def pull():
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', VPS, f'curl -s -S --max-time 30 {BASE}decisions/{SET}'], capture_output=True, text=True)
    if r.returncode: raise SystemExit('ssh/curl: ' + r.stderr.strip())
    return json.loads(r.stdout or '{}')


def flags(a):
    out = {}
    for f in a.get('flags') or []:
        m = re.match(r'^(dmg|eject|glue)-(\d+)$', f)
        if m: out[m.group(1)] = int(m.group(2))
    return out


def row_at(cap, row, n):
    """frame n (1-based, as the page shows it) -> (the script row on it, how it was read)"""
    i = n - 1
    assert 0 <= i < len(cap['rows']), f'frame {n} outside the capture (1-{len(cap["rows"])})'
    th = [j for j, s in enumerate(cap['states']) if s[1] == 'THROWN']
    if cap['states'][i][1] == 'THROWN': return cap['rows'][i][0], 'the victim\'s row'
    if not th: raise SystemExit(f"{cap['id']}: no paired script in the capture")
    if i < th[0]: return 0, 'before the script: its first row'
    j = th[-1]                                       # past the victim's script (the hand-off): where its rows would be
    return cap['rows'][j][0] + ((i - j) * (row['speed'] or 256) + 255) // 256, f'past the hand-off (frame {j + 1}): extrapolated at the speed'


def entries(answers, site):
    IX = json.load(open(os.path.join(site, 'review', 'throws', 'index.json')))
    rows = {r['id']: r for r in IX['rows']}
    out, skipped = [], []
    for rid, a in sorted(answers.items()):
        r = rows.get(rid)
        if not r: skipped.append((rid, 'not a row of this capture')); continue
        if a.get('choice') not in KIND: skipped.append((rid, f"{a.get('label') or 'no kind'}: not written" + (f" (note: {a['note']})" if a.get('note') else ''))); continue
        if r['kind'] != 'paired': skipped.append((rid, f"{a.get('label')}: a grab special, no paired script (engine fields not read for it)")); continue
        fl = flags(a)
        if 'dmg' not in fl: skipped.append((rid, f"{a.get('label')}: no damage frame yet")); continue
        cap = json.load(open(os.path.join(site, r['data'])))
        e = {'kind': KIND[a['choice']]}
        how = {}
        e['damage_row'], how['damage'] = row_at(cap, r, fl['dmg'])
        if a['choice'] == 0 and fl.get('eject'): e['eject_row'], how['eject'] = row_at(cap, r, fl['eject'])
        if fl.get('glue'): e['glue_row'], how['glue'] = row_at(cap, r, fl['glue'])
        e['from'] = (f"throw review {a.get('at', '')[:10] or datetime.date.today()} (review.html?q=throws, build {IX['game_version']}): "
                     + a.get('label', '') + (f"; note: {a['note']}" if a.get('note') else ''))
        out.append((r['fighter'], KEY[r['throw']], e, how, rid))
    return out, skipped


def apply(game, answers, site, dry=False):
    path = os.path.join(game, 'game.json')
    text = open(path).read(); g = json.loads(text)
    es, skipped = entries(answers, site)
    for rid, why in skipped: print(f'{rid}: skipped: {why}')
    for f, k, e, how, rid in es:
        print(f"{rid}: {f} throws.timing.{k} = {json.dumps({x: y for x, y in e.items() if x != 'from'})}  ({'; '.join(f'{x}: {y}' for x, y in how.items())})")
    out = text
    for f in sorted({f for f, *_ in es}):
        r = next(x for x in g['roster'] if x['name'] == f)
        had = 'throws' in r
        t = r.get('throws') or {}
        r['throws'] = t
        tm = t.setdefault('timing', {})
        for f2, k, e, how, rid in es:
            if f2 == f: tm[k] = e
        BT.throw_timing(r)                           # the build's own checks
        for f2, k, e, how, rid in es:
            hand = max(e.get('eject_row', e['damage_row']), e.get('glue_row', 0)) if e['kind'] == 'impact' else e.get('glue_row')
            if f2 == f and hand is None and how['damage'].startswith('past'):
                print(f'{rid}: WARNING: its damage frame is after the victim is let go now (no glue): it lands at the hand-off')
        # only that fighter's "throws" value rewritten (build_tables' layout at its depth): the rest stays byte for byte
        at = out.index(f'"name": "{f}"')
        a = out.rindex('\n  {', 0, at) + 3; b = out.index('\n  }', at) + 4
        obj = out[a:b]
        val = BT.fmt(t, 3)
        m = re.search(r'\n   "throws": ', obj)
        if m:
            _, end = json.JSONDecoder().raw_decode(obj, m.end())
            obj = obj[:m.end()] + val + obj[end:]
        else:
            assert not had
            nl = obj.index('\n', obj.index(f'"name": "{f}"'))
            obj = obj[:nl] + '\n   "throws": ' + val + ',' + obj[nl:]
        out = out[:a] + obj + out[b:]
    assert json.loads(out) == g, 'the patched file does not read back as the edited game'
    diff = ''.join(difflib.unified_diff(text.splitlines(True), out.splitlines(True), path, path + ' (throw review)'))
    if not dry and out != text: open(path, 'w').write(out)
    return diff


if __name__ == '__main__':
    a = sys.argv[1:]
    dry = '--dry' in a; a = [x for x in a if x != '--dry']
    if not a: sys.exit(__doc__)
    if a[0] == 'pull':
        s = json.dumps(pull(), indent=1, ensure_ascii=False)
        if len(a) > 1: open(a[1], 'w').write(s)
        else: print(s)
    elif a[0] == 'apply':
        ans = json.load(open(a[3])) if len(a) > 3 else pull()
        print(apply(a[1], ans, a[2], dry) or '(no change)')
    else: sys.exit(__doc__)
