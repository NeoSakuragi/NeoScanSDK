#!/usr/bin/env python3
"""Pinned effects hold with their owner's hit-stop (bproj_t follow FL_HSTOP, note 20261011-112545-5d29: "the circling
effect is now desynchronized from Haohmaru"), in our emulator (the repo's Geolith core, harness.py), the Chain Lab's
training (scenario.setup: the game's own path), Ryo the dummy.

Per frame: the owner's state / animation / step / freeze / hs_now and each of his effects whose bproj_t carries
FL_HSTOP (read from the build's bm_spec.c: the follow byte of every bproj_t element, the entity's pdef -> its element
through build/rom.elf's symbols): its row and timer. Checks, per run:
  held     on every frame the owner holds in hit-stop (hs_now; a build without the field: his freeze), his step and
           every FL_HSTOP effect's row and timer stay as they were the frame before
  in_step  each effect's row - the owner's live frames since its spawn (frames not held) stays constant over its life:
           it advances exactly when he does, to its end
  hits     the run's hits (Tenha: 12)
Runs: Haohmaru's MAX Tenha Fuujinzan (down + D, the wind 337), his C = 623AB Kogetsuzan (the crescent), Genjuro's
fury (D: the card wind on the caught victim, then the cards). --sheet DIR: Tenha's frames around hits 1 and 6 (hit - 2
.. hit + 3) as one PNG with the frame table under each picture.

    python3 hstop_proof.py ROM GAME_DIR OUT.json [--sheet DIR]   (GAME_DIR: the build's examples/brawler, its build/)"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); BR = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, HERE); sys.path.insert(0, BR)
import harness, scenario as S
FL_HSTOP = 128
NPJ = 8

def bproj_table(game):
    """pdef address -> (array name, element, follow) for every bproj_t of the build"""
    src = open(os.path.join(game, 'build', 'bm_spec.c')).read()
    follow = {}
    for m in re.finditer(r'static const bproj_t (\w+)\[\] = \{(.*)\};', src):
        els = m.group(2)[1:-1].split('}, {')
        follow[m.group(1)] = [int(e.split(',')[7]) for e in els]
    nm = subprocess.run(['m68k-linux-gnu-nm', '-S', os.path.join(game, 'build', 'rom.elf')], capture_output=True, text=True).stdout
    out = {}
    for line in nm.splitlines():
        p = line.split()
        if len(p) == 4 and p[3] in follow:
            addr, size, fl = int(p[0], 16), int(p[1], 16), follow[p[3]]
            for k, f in enumerate(fl): out[addr + k * (size // len(fl))] = (p[3], k, f)
    return out

def run(b, rec, pj, shots=(), sheet=None):
    S.setup(b, rec); t0 = b.frame; h0 = len(b.hits); rows = []
    owner = b.base; has_hs = 'hs_now' in b.layout
    keys = []
    for part in [p for p in rec['do_keys'].split(',') if p]:
        n, k = part.split(':'); keys += [k.replace('-', '')] * int(n)
    keys += [''] * rec.get('proof', 60)
    for t, k in enumerate(keys):
        if t + 1 in shots: b.pad[0] = set(k); b.screenshot(os.path.join(sheet, f'f{t + 1:03d}.png'))
        else: b.run(1, p1=k)
        r = {'t': t + 1, 'p1': b.states[b.fget(0, 'state')], 'pan': b.fget(0, 'pan'), 'pstep': b.fget(0, 'pstep'),
             'fz1': b.fget(0, 'freeze'), 'hs': b.fget(0, 'hs_now') if has_hs else None, 'fz2': b.fget(2, 'freeze'),
             'd': b.states[b.fget(2, 'state')], 'fx': []}
        for i in range(NPJ):
            if b.states[b.pget(i, 'state')] != 'PROJ' or b.pget(i, 'owner') != owner: continue
            d = pj.get(b.pget(i, 'pdef'))
            if d and d[2] & 1:                                  # pinned to him (bit 1), with or without FL_HSTOP
                r['fx'].append({'i': i, 'def': f'{d[0]}[{d[1]}]', 'follow': d[2], 'prow': b.pget(i, 'prow'),
                                'st': b.pget(i, 'state_t'), 'pend': b.pget(i, 'pend')})
        rows.append(r)
    hits = [f - t0 for f, i, d, st in b.hits[h0:] if i == 2]
    return rows, hits

def check(rows, hits, has_hs):
    held = lambda r: r['hs'] if has_hs else None
    bad_held, life = [], {}
    for a, r in zip(rows, rows[1:]):
        h = r['hs'] if has_hs else (a['fz1'] > 0)             # (no hs_now: held when the frame started with a freeze)
        for e in r['fx']:
            k = (e['i'], e['def']); life.setdefault(k, []).append((r['t'], e['prow'], e['st'], h))
            if not h: continue
            p = next((x for x in a['fx'] if x['i'] == e['i'] and x['def'] == e['def']), None)
            if p and (p['prow'], p['st']) != (e['prow'], e['st']): bad_held.append((r['t'], e['def'], p['prow'], e['prow']))
        if h and (a['pan'], a['pstep']) != (r['pan'], r['pstep']): bad_held.append((r['t'], 'owner', a['pstep'], r['pstep']))
    in_step = {}
    for k, seq in life.items():
        live, offs = 0, set()
        j0 = next((j for j, s in enumerate(seq) if s[2]), len(seq))   # from its first live frame (its spawn frame and
        for j, (t, prow, st, h) in enumerate(seq[j0:]):                 # its row-0 frame both show timer 0)
            if j and not h: live += 1
            offs.add(st - live)                               # its timer (state_t: its live frames) vs his live frames
        in_step[f'{k[1]}@{k[0]}'] = {'frames': len(seq), 'held_frames': sum(1 for s in seq[1:] if s[3]),
                                      'offsets': sorted(offs), 'rows': [s[1] for s in seq]}
    held_n = sum(1 for r in rows[1:] if (r['hs'] if has_hs else False))
    return {'hits': hits, 'held_frames': held_n, 'held_violations': bad_held[:20], 'n_held_violations': len(bad_held),
            'effects': in_step,
            'ok': not bad_held and bool(life) and all(len(v['offsets']) == 1 for v in in_step.values())}

def main(rom, game, out, sheet=None):
    b = harness.Brawler(rom=rom, game=game, tick_sync=True); b.game = game
    pj = bproj_table(game); has_hs = 'hs_now' in b.layout
    lab = lambda **k: {'setup': dict({'mode': 'lab', 'fighter': 'haohmaru', 'dummy': 'ryo'}, **k.pop('setup', {})), **k}
    runs = {'tenha': lab(setup={'gap': 60, 'hp': 15, 'fury': 'full'}, do_keys='2:Dd,300:-', proof=60),
            'kogetsuzan': lab(do_keys='2:c,100:-', proof=40),
            'genjuro_fury': lab(setup={'fighter': 'genjuro', 'gap': 60, 'fury': 'full', 'drive': 'full'}, do_keys='2:d,300:-', proof=40)}
    R, ok = {'has_hs_now': has_hs}, True
    for name, rec in runs.items():
        rows, hits = run(b, rec, pj)
        R[name] = check(rows, hits, has_hs); R[name]['table'] = rows
        if name == 'tenha': R[name]['ok'] &= len(hits) == 12
        ok &= R[name]['ok']
        print(name, 'OK' if R[name]['ok'] else 'FAIL', 'hits', len(hits), 'held', R[name]['held_frames'],
              'violations', R[name]['n_held_violations'], {k: (v['frames'], v['held_frames'], v['offsets']) for k, v in R[name]['effects'].items()})
    if sheet:
        os.makedirs(sheet, exist_ok=True)
        h = R['tenha']['hits']; pick = [t for c in (h[0], h[5]) for t in range(c - 2, c + 4)]
        rows, _ = run(b, runs['tenha'], pj, shots=set(pick), sheet=sheet)
        from PIL import Image, ImageDraw
        ims = [Image.open(os.path.join(sheet, f'f{t:03d}.png')) for t in pick]
        w, hh = ims[0].size; W = 6
        out_im = Image.new('RGB', (W * w, 2 * (hh + 40)), 'white'); dr = ImageDraw.Draw(out_im)
        for j, (t, im) in enumerate(zip(pick, ims)):
            x, y = (j % W) * w, (j // W) * (hh + 40)
            out_im.paste(im, (x, y)); r = rows[t - 1]; e = r['fx'][0] if r['fx'] else None
            dr.text((x + 4, y + hh + 2), f"t{t} {'HIT' if t in h else ''} step {r['pstep']} fz {r['fz1']} hs {r['hs']}", fill='black')
            dr.text((x + 4, y + hh + 20), f"wind row {e['prow'] if e else '-'} timer {e['st'] if e else '-'}", fill='black')
        out_im.save(os.path.join(sheet, 'tenha_sheet.png')); R['sheet'] = os.path.join(sheet, 'tenha_sheet.png')
    json.dump(R, open(out, 'w'), indent=1, default=str)
    print('ALL OK' if ok else 'FAIL'); return ok

if __name__ == '__main__':
    a = sys.argv[1:]; sh = a[a.index('--sheet') + 1] if '--sheet' in a else None
    sys.exit(0 if main(a[0], a[1], a[2], sh) else 1)
