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
        pulled set (default: pulled now). Prints each throw's mapping and the game.json diff; --dry writes nothing.

ROUND 2 (review.html?q=throws2, Bruno 2026-10-16 after 0.10.142: "define WHEN THE IMPACT occurs (the visual + the
sound), and separately WHEN THE ACTUAL LAUNCH occurs [...] Separate these concerns"): set "throws2", one answer per
throw: choice 0 = these events / 1 = "None of these" (the note says), flags impact-N, launch-N, dir-up | dir-away |
dir-none, size-small | size-medium | size-big (optional), held-N (optional), N = the throw's frame as the page shows it
(1 = its first frame: the engine's throw frame clock, no row mapping). -> game.json roster[].throws.events.<forward |
back | hold_b> = {impact, launch: {frame, dir, size?}, held?, from} (build_tables throw_events: the data model); the
throw's throws.timing entry (and for SS2 Hanzo's hold + B, special_grab_timing "623K") removed: one path.
    python3 tools/brawler/throw_answers.py pull2 [OUT.json]             set "throws2" from the VPS
    python3 tools/brawler/throw_answers.py propose [OUT.json]           round 1 -> round 2's proposal (as the page
        pre-fills it: damage -> impact; an IMPACT's eject (else damage) / a SLAM's glue (else damage) -> launch; IMPACT
        -> away, SLAM -> up), in set "throws2"'s format (throw_regress.py --events reads it)
    python3 tools/brawler/throw_answers.py apply2 GAME_DIR [ANSWERS2.json] [--dry]
        every answer of set "throws2" (pulled now, or ANSWERS2.json) into GAME_DIR/game.json: incremental and idempotent
        (an answer already applied changes nothing; run it again after each new answer), then rebuild. Flags read:
        impact-N (one per impact: 1-3), share-N-P (the impact on frame N takes P % of the damage; default all on the
        last), launch-N, dir-*, size-*, held-N. A note that is only the mic's prompt text is dropped."""
import datetime, difflib, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_tables as BT

VPS = 'root@195.201.91.211'
BASE = 'http://127.0.0.1:8920/api/'                  # the feedback service on the box (ssh = authenticated)
SET = 'throws'
KIND = {0: 'impact', 1: 'slam'}
KEY = {'fwd': 'forward', 'back': 'back', 'holdb': 'hold_b'}   # the page's row id -> throws.timing key (gamedata.h TM_*)


def pull(st=SET):
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', VPS, f'curl -s -S --max-time 30 {BASE}decisions/{st}'], capture_output=True, text=True)
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


def set_field(out, f, field, val):
    """only fighter f's roster field rewritten (build_tables' layout at its depth; None: removed): the rest of game.json
    stays byte for byte"""
    at = out.index(f'"name": "{f}"')
    a = out.rindex('\n  {', 0, at) + 3; b = out.index('\n  }', at) + 4
    obj = out[a:b]
    m = re.search(r'\n   "%s": ' % re.escape(field), obj)
    if m:
        _, end = json.JSONDecoder().raw_decode(obj, m.end())
        if val is None:
            end += 1 if obj[end:end + 1] == ',' else 0
            obj = obj[:m.start()] + obj[end:]
        else: obj = obj[:m.end()] + BT.fmt(val, 3) + obj[end:]
    elif val is not None:
        nl = obj.index('\n', obj.index(f'"name": "{f}"'))
        obj = obj[:nl] + f'\n   "{field}": ' + BT.fmt(val, 3) + ',' + obj[nl:]
    return out[:a] + obj + out[b:]


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
        out = set_field(out, f, 'throws', t)
    assert json.loads(out) == g, 'the patched file does not read back as the edited game'
    diff = ''.join(difflib.unified_diff(text.splitlines(True), out.splitlines(True), path, path + ' (throw review)'))
    if not dry and out != text: open(path, 'w').write(out)
    return diff


# ---- round 2: the events ----
SET2 = 'throws2'
MIC_PROMPT = 'Neo Geo brawler game feedback, in English or French.'   # the mic's transcription prompt (micnote.js), not his
                                                                     # words: a note that is only that is no note


def parse2(a):
    """an answer's flags -> {impacts: [frames], shares: {frame: %}, launch, held?, dir, size?} (impact-N once per impact,
    share-N-P: the impact on frame N takes P % of the throw's damage)"""
    o = {'impacts': [], 'shares': {}}
    for f in a.get('flags') or []:
        m = re.match(r'^impact-(\d+)$', f)
        if m: o['impacts'].append(int(m.group(1))); continue
        m = re.match(r'^share-(\d+)-(\d+)$', f)
        if m: o['shares'][int(m.group(1))] = int(m.group(2)); continue
        m = re.match(r'^(launch|held)-(\d+)$', f)
        if m: o[m.group(1)] = int(m.group(2)); continue
        m = re.match(r'^(dir|size)-(\w+)$', f)
        if m: o[m.group(1)] = m.group(2)
    o['impacts'] = sorted(set(o['impacts']))
    if o['impacts']: o['impact'] = o['impacts'][0]
    return o


def note_of(a):
    n = (a.get('note') or '').strip()
    return '' if n.startswith(MIC_PROMPT) else n


def propose(old):
    """round 1's answers -> round 2's proposal (review.js throwReview2 propose(): the same rule)"""
    out = {}
    for rid, a in old.items():
        p = flags(a)
        if 'dmg' not in p: continue
        imp = a.get('choice') == 0
        e = {'impact': p['dmg'], 'launch': (p.get('eject') or p['dmg']) if imp else (p.get('glue') or p['dmg']), 'dir': 'away' if imp else 'up'}
        out[rid] = {'choice': 0, 'proposed': True, 'flags': [f"impact-{e['impact']}", f"launch-{e['launch']}", f"dir-{e['dir']}"],
                    'label': f"proposed from round 1 ({a.get('label') or ', '.join(a.get('flags') or [])})"}
    return out


def events_of_answer(a):
    """one answer -> the throws.events entry (build_tables throw_events' data model), or (None, why not)"""
    if a.get('choice') != 0: return None, f"{a.get('label') or 'no answer'}: not written" + (f" (note: {note_of(a)})" if note_of(a) else '')
    p = parse2(a)
    miss = [k for k, ok in (('impact', p['impacts']), ('launch', 'launch' in p), ('dir', 'dir' in p)) if not ok]
    if miss: return None, f"no {' / '.join(miss)} yet"
    imps = []
    for k, fr in enumerate(p['impacts']):
        x = {'frame': fr}
        if fr in p['shares'] and k + 1 < len(p['impacts']): x['damage'] = p['shares'][fr]
        imps.append(x)
    e = {'impacts': imps}
    if p.get('held'): e['held'] = p['held']
    e['launch'] = dict({'frame': p['launch'], 'dir': p['dir']}, **({'size': p['size']} if p.get('size') else {}))
    e['from'] = (f"throw review round 2 {a.get('at', '')[:10] or datetime.date.today()} (review.html?q=throws2): "
                 + a.get('label', '') + (f"; note: {note_of(a)}" if note_of(a) else ''))
    return e, None


def row_of(g, rid):
    """a page row id <fighter>-<fwd | back | holdb> -> (fighter, throws.events key, kind 'paired' | 'special'), or None"""
    f, _, k = rid.rpartition('-')
    r = next((x for x in g['roster'] if x['name'] == f), None)
    if not r or k not in KEY: return None
    key = KEY[k]
    return f, key, 'special' if BT.event_special(r, key) else 'paired'


def entries2(answers, g):
    out, skipped = [], []
    for rid, a in sorted(answers.items()):
        row = row_of(g, rid)
        if not row: skipped.append((rid, 'not a throw of this game')); continue
        e, why = events_of_answer(a)
        if e is None: skipped.append((rid, why)); continue
        out.append(row + (e, rid))
    return out, skipped


def apply2(game, answers, dry=False):
    """every answer present -> game.json (only the fighters' throws / special_grab_timing fields rewritten): incremental
    and idempotent, an answer already applied changes nothing, a changed one replaces its entry; run it again on each
    new answer. -> the diff (empty: nothing new)"""
    path = os.path.join(game, 'game.json')
    text = open(path).read(); g = json.loads(text)
    es, skipped = entries2(answers, g)
    for rid, why in skipped: print(f'{rid}: skipped: {why}')
    out = text
    for f in sorted({f for f, *_ in es}):
        r = next(x for x in g['roster'] if x['name'] == f)
        t = r.setdefault('throws', {})
        ev = t.setdefault('events', {})
        sgt = False
        for f2, k, kind, e, rid in es:
            if f2 != f: continue
            print(f"{rid}: {f} throws.events.{k} = {json.dumps({x: y for x, y in e.items() if x != 'from'})}" + ('' if ev.get(k) != e else '  (already applied)'))
            ev[k] = e
            (t.get('timing') or {}).pop(k, None)             # one path: the events replace the timing
            sp = BT.event_special(r, k)
            if sp and sp in (r.get('special_grab_timing') or {}):
                del r['special_grab_timing'][sp]; sgt = True
        if sgt:
            if not r['special_grab_timing']: del r['special_grab_timing']
            out = set_field(out, f, 'special_grab_timing', r.get('special_grab_timing'))
        t['events'] = {k: ev[k] for k in BT.EVENT_KEYS if k in ev}
        if 'timing' in t and not t['timing']: del t['timing']
        BT.throw_events(r, g)                                 # the data model's own checks
        out = set_field(out, f, 'throws', t)
    assert json.loads(out) == g, 'the patched file does not read back as the edited game'
    diff = ''.join(difflib.unified_diff(text.splitlines(True), out.splitlines(True), path, path + ' (throw review round 2)'))
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
    elif a[0] in ('pull2', 'propose'):
        d = pull(SET2) if a[0] == 'pull2' else propose(pull())
        s = json.dumps(d, indent=1, ensure_ascii=False)
        if len(a) > 1: open(a[1], 'w').write(s)
        else: print(s)
    elif a[0] == 'apply2':
        rest = [x for x in a[2:] if not os.path.isdir(x)]   # (a SITE_DIR, as before: no longer needed)
        ans = json.load(open(rest[0])) if rest else pull(SET2)
        print(apply2(a[1], ans, dry) or '(no change: every answer already applied)')
    elif a[0] == 'apply':
        ans = json.load(open(a[3])) if len(a) > 3 else pull()
        print(apply(a[1], ans, a[2], dry) or '(no change)')
    else: sys.exit(__doc__)
