#!/usr/bin/env python3
"""The Brawler Lab WORKSHOP (Bruno 2026-10-10: part 1 of the Lab, the token-bound side: conversation, unlock requests,
decoding; part 2 ASSEMBLY = the arbitration sheet + arb_compile.py, zero tokens). Page: the Fighter Lab's Workshop tab, brawler-lab/lab.html?f=<f>&tab=workshop
(chainlab/workshop.html + workshop.js), the fighter's catalogue:

  Specials    every special version in the fighter's piece library (arb_pieces/<f>.json "specials": the dictionary's
              move list + the decoded programs). UNLOCKED = it has an S- id (piece_ids.py registry): id, name, input,
              its animations as clips, what it does. LOCKED = not decoded: greyed, clips still play, "Unlock this".
  Throws      T- ids the same way (the export's decoded throws; a dictionary throw the export lacks is locked)
  Animations  every $NN with the hit class of each attack frame: KOF98 / 99 the attack box's id -> KOF's reaction
              (handlers98 REACT tables, situation 0 / 2 standing, 6 juggled) -> "light normal", "heavy normal",
              "sweep", "launcher", "high launcher", "launch straight up", "blowback", "slam"; others "class not decoded"
  Threads     per piece, Bruno's requests and my replies: decisions store, set "<f>-workshop", one entry per message,
              id "<piece key>--<time>", fields choice = the piece key, label = request | reply | unlocked, note = text.
              Piece keys: S-001 / T-001, a locked special "sp-<input>" (spaces and brackets -> _), a locked throw
              "th-<anim>", an animation "anim-<hex>"; an unlocked piece also shows its locked-key thread.

    python3 tools/brawler/workshop.py list [FIGHTER]                  threads; OPEN = the last message is his request
    python3 tools/brawler/workshop.py reply FIGHTER PIECE "text"       PIECE: S-004, T-001, $A9, or a locked input "623B"
    python3 tools/brawler/workshop.py unlock FIGHTER PIECE ["text"]   a decoded special / throw gets its id (registry), a
                                                                      reply is posted and the page data republished
    python3 tools/brawler/workshop.py sync FIGHTER                    ids for everything decoded (= arb_compile pieces)
    python3 tools/brawler/workshop.py build OUT [GAME_DIR] [FIGHTER ...]   -> OUT/review/<f>_workshop.json (make_site.py)
    python3 tools/brawler/workshop.py publish FIGHTER                 build that file alone and copy it to the VPS site

unlock needs the special decoded in the piece library first (handlers98.ROM_SPECIALS / export_kz, then
`arb_compile.py pieces <f>`): an id names a piece the compiler can link, never a wish."""
import argparse, json, os, re, shlex, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
REPO = os.path.dirname(TOOLS)
for p in (HERE, os.path.join(TOOLS, 'kof96'), os.path.join(TOOLS, 'neosdk')):
    if p not in sys.path: sys.path.insert(0, p)
import piece_ids

VPS = 'root@195.201.91.211'
BASE = 'http://127.0.0.1:8920/api/'                        # the feedback service on the box (ssh = authenticated)
LAB = '/data/brawler-lab'
FIGHTERS = tuple(__import__('animdict').DICTS)        # the fighters with an animation dictionary (animdict.DICTS: one list)


def SET(f): return f + '-workshop'
def slug(s): return re.sub(r'[^A-Za-z0-9-]+', '_', s).strip('_')


# ============================================================================================ hit classes
def hit_classes(game):
    """KOF98 / 99: attack box id (hex '$25') -> {label, standing, juggled}: KOF's reaction for a hit by that box,
    read from its REACT tables (handlers98: situation 2 standing, 6 juggled; the light / heavy strength of a reel from
    situation 0, where the tables tell the boxes apart: index % 4 < 2 light). None: no tables for this game."""
    import rom96, handlers98 as H98
    if game not in H98.REACT_TABLES: return None
    m = rom96.Mem(rom96.load(rom96.GAMES[game]['neo'])[0], game)
    t0, t1, _ = H98.REACT_TABLES[game]
    def rx(box, situ): return m.u8(t1 + (box - 0x18) * 36 + situ) if box >= 0x18 else m.u8(t0 + (box - 0x0C) * 72 + situ)
    def fam(r, r0=None):
        if r in H98.HIGH_LAUNCH: return 'high launcher'
        c = H98.react_class(r)
        if c == H98.R_HEAVY:
            if r == 80: return 'own reaction (not in the table)'
            s = r0 if r0 is not None and r0 <= 15 else r
            return ('light normal' if s % 4 < 2 else 'heavy normal') if s <= 15 else 'reel'
        return {H98.R_TRIP: 'sweep', H98.R_LAUNCH: 'launcher', H98.R_LIFT: 'launch straight up', H98.R_SLAM: 'slam'}.get(c, 'blowback')
    out = {}
    for box in range(0x0C, 0x40):
        st, ju = fam(rx(box, 2), rx(box, 0)), fam(rx(box, 6))
        out['$%02X' % box] = {'label': st, 'standing': st, 'juggled': ju}
    return out


def box_id(key, game):
    """a dictionary attack box's key -> KOF's attack id (animdict.box_px: 0x10 | t, or 0x100 | t from t = 16); None
    for other games"""
    if game not in ('kof96', 'kof97', 'kof98', 'kof99'): return None
    return key - 0x100 if key >= 0x100 else key & 0x0F


# ============================================================================================ the page data
def pieces_of(f):
    p = os.path.join(HERE, 'arb_pieces', f'{f}.json')
    return json.load(open(p)) if os.path.exists(p) else None


def what_it_does(ids, Dby, classes, game, proj):
    """a short line from the data: animations, the hit classes of their attack frames, projectile, travel"""
    labs = []
    for x in ids:
        for s in (Dby.get(x) or {}).get('steps', []):
            for b in s['b']:
                if b[0] != 'a': continue
                k = box_id(b[1], game)
                lab = (classes or {}).get('$%02X' % k, {}).get('label') if k is not None and classes else None
                lab = lab or 'class not decoded'
                if lab not in labs: labs.append(lab)
    tr = max((abs((Dby.get(x) or {}).get('travel') or 0) for x in ids), default=0)
    bits = [f'{len(ids)} animation' + ('s' if len(ids) != 1 else '')]
    bits.append('hits: ' + ', '.join(labs) if labs else 'no attack box')
    if proj: bits.append('projectile ' + ' '.join('$' + p for p in proj))
    if tr: bits.append(f'travels up to {tr} px')
    return '; '.join(bits)


def page_data(f, D, lib, reg, classes):
    """the Workshop page's data for one fighter (review/<f>_workshop.json; arbitrage.js reads it for its picker too)"""
    Dby = {a['id']: a for a in D['anims']}
    game = D.get('game') or lib.get('game')
    sid = piece_ids.by_input(reg, 'special'); tid = piece_ids.by_input(reg, 'throw')
    projs = {}                                            # input -> its projectile animations (dictionary "(its projectile)")
    for a in D['anims']:
        for s in a.get('moves', []):
            if s.endswith('(its projectile)'):
                inp = s.split(' ')[0] if not s.startswith(('EX ', 'MAX ', 'air ')) else ' '.join(s.split(' ')[:2])
                projs.setdefault(inp, []).append(a['id'])
        for s in a.get('exported', []):                   # Kizuna: "<input> effect"
            if s.endswith(' effect'): projs.setdefault(s[:-7], []).append(a['id'])
    specials = []
    for inp, s in lib['specials'].items():
        i = sid.get(inp)
        anims = [x for x in s['anims'] if x in Dby]
        pr = [x for x in dict.fromkeys(projs.get(inp, [])) if x in Dby]
        keys = ([i] if i else []) + ['sp-' + slug(inp)]
        specials.append({'id': i, 'input': inp, 'name': reg['pieces'][i]['name'] if i else piece_ids.special_name(inp, D),
                         'air': bool(s['air']), 'decoded': bool(s['decoded']), 'anims': anims, 'projectile': pr,
                         'source': s.get('source'), 'what': what_it_does(anims, Dby, classes, game, pr), 'keys': keys,
                         'pending': bool(s['decoded'] and not i),
                         'knobs': (lib.get('knobs') or {}).get(i, []) if i else []})   # its key parameters (knobs.py)
    specials.sort(key=lambda x: (x['id'] is None, x['id'] or '', x['input']))
    throws, seen = [], set()
    for mv, aid in piece_ids.decoded_throws(lib):
        inp = piece_ids.throw_input(lib, mv); i = tid.get(inp)
        anims = [x for x, e in lib['anims'].items() if mv in e.get('throws', []) and x in Dby]
        seen.update(anims)
        throws.append({'id': i, 'input': inp, 'name': reg['pieces'][i]['name'] if i else piece_ids.throw_name(mv, aid, D),
                       'move': mv, 'decoded': True, 'anims': anims, 'what': what_it_does(anims, Dby, classes, game, []),
                       'keys': ([i] if i else []) + ['th-' + slug(inp)], 'pending': not i})
    for a in D['anims']:                                  # dictionary throws the export does not play: locked
        ts = [s for s in a.get('moves', []) if s.startswith('throw (') or s.endswith('(throw)')]
        if not ts or a['id'] in seen: continue
        throws.append({'id': None, 'input': ts[0], 'name': ts[0], 'move': None, 'decoded': False, 'anims': [a['id']],
                       'what': what_it_does([a['id']], Dby, classes, game, []), 'keys': ['th-' + a['id']], 'pending': False})
    gone = [dict(p, id=i) for i, p in reg['pieces'].items() if p.get('gone')]
    return {'fighter': f, 'display': D.get('display') or f.upper(), 'game': game, 'source': D.get('source'),
            'classes': classes, 'class_note': None if classes else f'{game}: hit class not decoded',
            'specials': specials, 'throws': throws, 'gone': gone,
            'counts': {'unlocked': sum(1 for s in specials if s['id']), 'locked': sum(1 for s in specials if not s['id']),
                       'throws_unlocked': sum(1 for t in throws if t['id']), 'throws_locked': sum(1 for t in throws if not t['id'])}}


def build(out, game=None, names=None):
    """OUT/review/<f>_workshop.json for every fighter with a dictionary (OUT/review/<f>_anims.json) and a piece library"""
    res, cls_cache = {}, {}
    for f in names or FIGHTERS:
        p = os.path.join(out, 'review', f'{f}_anims.json')
        lib = pieces_of(f)
        if not os.path.exists(p) or not lib: continue
        D = json.load(open(p))
        g = D.get('game') or lib['game']
        if g not in cls_cache: cls_cache[g] = hit_classes(g) if g in ('kof98', 'kof99') else None
        doc = page_data(f, D, lib, piece_ids.load(f), cls_cache[g])
        json.dump(doc, open(os.path.join(out, 'review', f'{f}_workshop.json'), 'w'), ensure_ascii=False)
        res[f] = doc
    return res


# ============================================================================================ the threads (decisions store)
def api(path_, body=None):
    cmd = f'curl -s -S --max-time 30 {shlex.quote(BASE + path_)}'
    if body is not None: cmd += " -X POST -H 'Content-Type: application/json' --data-binary @-"
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', VPS, cmd], input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    if r.returncode: raise SystemExit('ssh/curl: ' + r.stderr.strip())
    out = json.loads(r.stdout or '{}')
    if isinstance(out, dict) and 'error' in out: raise SystemExit('feedback service: ' + str(out['error']))
    return out


def threads(f):
    """{piece key: [messages oldest first]} of the fighter's workshop set"""
    try: cur = api(f'decisions/{SET(f)}')
    except SystemExit: cur = {}
    th = {}
    for mid, a in (cur or {}).items():
        if not isinstance(a, dict) or not a.get('choice'): continue
        th.setdefault(a['choice'], []).append(dict(a, mid=mid))
    for v in th.values(): v.sort(key=lambda a: a.get('at') or '')
    return th


def piece_key(f, token):
    """S-004 / T-001 / $A9 / anim-A9 / a special's input ('623B', 'MAX 23624A') / a key itself -> (key, label)"""
    reg = piece_ids.load(f)
    t = token.strip()
    if piece_ids.ID_RE.match(t):
        if t not in reg['pieces']: raise SystemExit(f'{f}: no piece {t} in the registry')
        return t, f"{t} {reg['pieces'][t]['name']}"
    if re.match(r'^\$?[0-9A-Fa-f]{1,3}$', t) or t.startswith('anim-'):
        x = t.replace('anim-', '').lstrip('$').upper(); return 'anim-' + x, '$' + x
    if t.startswith(('sp-', 'th-')): return t, t
    lib = pieces_of(f) or {'specials': {}}
    if t in lib['specials']:
        i = piece_ids.by_input(reg, 'special').get(t)
        return (i, f"{i} {reg['pieces'][i]['name']}") if i else ('sp-' + slug(t), t + ' (locked)')
    raise SystemExit(f'{f}: "{token}" is not a piece (S-/T- id, $NN or a special input of arb_pieces/{f}.json)')


def post(f, key, label, text, question):
    mid = f'{key}--{int(time.time() * 1000):x}'
    return api('decision', {'set': SET(f), 'id': mid[:40], 'choice': key, 'label': label, 'note': text, 'question': question})


def cmd_list(f):
    fs = [f] if f else [x for x in FIGHTERS if pieces_of(x)]
    for x in fs:
        th = threads(x)
        if not th: print(f'{x}: no workshop messages'); continue
        print(f'{x}: {len(th)} thread(s)')
        for k, msgs in sorted(th.items(), key=lambda kv: kv[1][-1].get('at') or ''):
            st = 'OPEN' if msgs[-1].get('label') == 'request' else 'answered'
            print(f'  {k}  [{st}]  {msgs[0].get("question") or ""}')
            for m in msgs: print(f"    {(m.get('at') or '')[:16].replace('T', ' ')}  {m.get('label'):<9} {m.get('note') or ''}")


def cmd_unlock(f, token, text):
    lib = pieces_of(f)
    if not lib: raise SystemExit(f'{f}: no piece library (arb_compile.py pieces {f})')
    reg = piece_ids.load(f)
    t = token.strip()
    if t.startswith('sp-'): t = next((i for i in lib['specials'] if 'sp-' + slug(i) == t), t)
    D = fetch_dict(f)
    if t in lib['specials']:
        if not lib['specials'][t]['decoded']:
            raise SystemExit(f'{f}: {t} is not decoded in the piece library: decode it (handlers98.ROM_SPECIALS / export_kz), '
                             f'then `arb_compile.py pieces {f}`, then unlock')
        i, made = piece_ids.assign(reg, 'S', t, piece_ids.special_name(t, D), air=bool(lib['specials'][t]['air']), source=lib['specials'][t].get('source'))
        old_key = 'sp-' + slug(t)
    else:
        mv = next((m for m, _ in piece_ids.decoded_throws(lib) if m == t or piece_ids.throw_input(lib, m) == t), None)
        if not mv: raise SystemExit(f'{f}: "{token}" is neither a special input nor a decoded throw (throw_c / throw_d / "forward + C")')
        aid = dict(piece_ids.decoded_throws(lib))[mv]
        i, made = piece_ids.assign(reg, 'T', piece_ids.throw_input(lib, mv), piece_ids.throw_name(mv, aid, D), move=mv, source='export throws')
        old_key = 'th-' + slug(piece_ids.throw_input(lib, mv))
    if made: piece_ids.save(reg)
    nm = reg['pieces'][i]['name']
    print(f'{f}: {t} = {i} {nm}' + ('' if made else ' (had its id already)'))
    post(f, i, 'unlocked', text or f'Unlocked as {i}: {nm}. It is in the arbitration sheet\'s picker now.', f'{i} {nm}')
    if old_key != i and old_key in threads(f):
        post(f, old_key, 'unlocked', f'Unlocked as {i} ({nm}): this thread continues there.', t)
    publish(f)


def fetch_dict(f):
    import arb_compile
    return arb_compile.fetch_dict(f)


def publish(f):
    """the fighter's page data rebuilt and copied to the hosted Lab (no full deploy needed after an unlock)"""
    d = tempfile.mkdtemp(prefix='workshop_', dir='/data/tmp' if os.path.isdir('/data/tmp') else None)
    os.makedirs(os.path.join(d, 'review'))
    json.dump(fetch_dict(f), open(os.path.join(d, 'review', f'{f}_anims.json'), 'w'))
    doc = build(d, None, [f])[f]
    subprocess.run(['scp', '-q', os.path.join(d, 'review', f'{f}_workshop.json'), f'{VPS}:{LAB}/review/'], check=True)
    print(f'published review/{f}_workshop.json: {doc["counts"]}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sp = ap.add_subparsers(dest='cmd', required=True)
    x = sp.add_parser('list'); x.add_argument('fighter', nargs='?')
    x = sp.add_parser('reply'); x.add_argument('fighter'); x.add_argument('piece'); x.add_argument('text')
    x = sp.add_parser('unlock'); x.add_argument('fighter'); x.add_argument('piece'); x.add_argument('text', nargs='?')
    x = sp.add_parser('sync'); x.add_argument('fighter')
    x = sp.add_parser('publish'); x.add_argument('fighter')
    x = sp.add_parser('build'); x.add_argument('out'); x.add_argument('game', nargs='?'); x.add_argument('fighters', nargs='*')
    a = ap.parse_args()
    if a.cmd == 'list': cmd_list(a.fighter)
    elif a.cmd == 'reply':
        k, lab = piece_key(a.fighter, a.piece); post(a.fighter, k, 'reply', a.text, lab); print(f'{a.fighter} {k}: replied')
    elif a.cmd == 'unlock': cmd_unlock(a.fighter, a.piece, a.text)
    elif a.cmd == 'sync':
        lib = pieces_of(a.fighter)
        if not lib: raise SystemExit(f'{a.fighter}: no piece library')
        reg, new = piece_ids.sync(a.fighter, lib, fetch_dict(a.fighter))
        for i, p in reg['pieces'].items(): print(f"  {i}{' (new)' if i in new else ''}{' GONE' if p.get('gone') else ''}  {p['input']:<12} {p['name']}")
    elif a.cmd == 'publish': publish(a.fighter)
    else:
        for f, d in build(a.out, a.game, a.fighters or None).items(): print(f, d['counts'])


if __name__ == '__main__':
    main()
