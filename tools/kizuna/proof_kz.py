#!/usr/bin/env python3
"""A Kizuna fighter's proof sheet (TODO #77): its export (export_kz.py, the brawler's bank layout) as a contact sheet of
its moves and a line of /data/tmp/kz77/out/index.json with the counts.

    python3 proof_kz.py NAME EXPORT_DIR      -> /data/tmp/kz77/out/NAME.png, index.json updated

Sheet: one row per exported move (the brawler's moves without their aliases, then each special: every distinct frame
of its script, objects included), each cell Kizuna's own drawing of the step at the export's zoom (kz.render_step_zoom,
colour A from the ROM), the move name and its step count at the left.
Index entry: moves found (the catalogue's captured moves: attacks with a live box, specials), animations in its table,
moves / specials exported, frames, tiles, the frame checks (check_frames.py --char: ROM render vs Kizuna's VRAM, export
vs ROM render; the harness check of the throwaway build when present), follow-ups (plan_kz: parts / links per
multipart special; substates_kz --check agreements / disagreements)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import numpy as np, kz, fighters_kz as FK
from PIL import Image, ImageDraw
OUT = '/data/tmp/kz77/out'
CW, CH_, PER = 96, 128, 18

def cell(recs, pal):
    img = np.zeros((CH_ * 2, CW * 2), np.uint16)
    for a in recs.split('+'): kz.render_step_zoom(img, int(a, 16), CW, CH_ * 2 - 24, 0xCC)
    rgb = kz.colorize(img, pal); rgb[img == 0] = 255
    im = Image.fromarray(rgb)
    ys, xs = np.nonzero(img)
    if len(ys):                                          # centred on the feet, cut to the cell
        im = im.crop((CW - CW // 2, max(0, min(CH_ * 2 - CH_, ys.min() - 4)), CW + CW // 2, max(0, min(CH_ * 2 - CH_, ys.min() - 4)) + CH_))
    else: im = im.crop((CW // 2, CH_, CW + CW // 2, 2 * CH_))
    return im

def main(name, exp):
    ex = json.load(open(os.path.join(exp, 'kof95_export.json')))['characters'][name]
    ch = FK.CAST[name]
    pal = [0] * 4096
    a_set = kz.u16(0x1438 + 2 * ch)
    for k in range(24):
        pal[(16 + k) * 16:(17 + k) * 16] = [kz.u16(0x70000 + 32 * (a_set + k) + 2 * i) for i in range(16)]
    rows, seen = [], set()
    for mv, a in ex['anims'].items():
        key = tuple(s['frame'] for s in a['steps'])
        if key in seen: continue
        seen.add(key); rows.append((mv, [ex['frames'][s['frame']]['record'] for s in a['steps']]))
    for sp in ex['specials']:
        fs = []
        for r in sp['script']:
            for f in [r[0]] + [o[0] for o in r[3]]:
                if f not in fs: fs.append(f)
        rows.append((f"sp {sp['input']}" + (f" ({len(sp['parts'])} parts)" if sp.get('parts') else ''), [ex['frames'][f]['record'] for f in fs]))
    lines = []
    for mv, recs in rows:
        for k in range(0, len(recs), PER): lines.append((mv if not k else '', recs[k:k + PER], len(recs)))
    sheet = Image.new('RGB', (110 + CW * PER, CH_ * len(lines)), 'white'); d = ImageDraw.Draw(sheet)
    for i, (mv, recs, n) in enumerate(lines):
        if mv: d.text((4, i * CH_ + 4), mv, fill='black'); d.text((4, i * CH_ + 18), f'{n} frames', fill='black')
        for j, r in enumerate(recs): sheet.paste(cell(r, pal), (110 + j * CW, i * CH_))
        d.line([0, (i + 1) * CH_ - 1, sheet.width, (i + 1) * CH_ - 1], fill='black')
    os.makedirs(OUT, exist_ok=True)
    sheet.save(os.path.join(OUT, f'{name}.png'))
    # the index line
    cat = json.load(open(FK.path(name, 'moves')))
    attacks = {k: m for k, m in cat['moves'].items() if m.get('active') or m.get('hits')}
    cmds = {c['notation'] for c in cat['commands']}
    chk = os.path.join(OUT, f'check_{name}.json')
    plan = json.load(open(FK.path(name, 'follow'))) if os.path.exists(FK.path(name, 'follow')) else {}
    sub = open(FK.path(name, 'check', 'txt')).read().splitlines() if os.path.exists(FK.path(name, 'check', 'txt')) else []
    hp = os.path.join(OUT, f'harness_{name}.json')
    ent = {'name': name, 'character': FK.NAMES[ch], 'id': ch, 'animations': cat['anim_count'] + 1,
           'moves_found': len(cat['moves']), 'attacks_found': len(attacks), 'commands': len(cat['commands']),
           'moves_exported': len({tuple(s['frame'] for s in a['steps']) for a in ex['anims'].values()}),
           'specials_exported': [sp['input'] for sp in ex['specials']], 'frames': len(ex['frames']),
           'frame_check': json.load(open(chk)) if os.path.exists(chk) else None,
           'harness': json.load(open(hp)) if os.path.exists(hp) else None,
           'followups': {k: {'parts': len(F['parts']), 'links': [f"{F['parts'][l[0]][1][-1]:X}->{F['parts'][l[1]][1][0]:X} {l[2]} {l[3] or ''} {l[5]}" for l in F['links']]}
                         for k, F in plan.get('follow', {}).items()},
           'substates_check': {'agree': sum(1 for l in sub if l.startswith('agree')), 'disagree': [l[9:] for l in sub if l.startswith('DISAGREE')]},
           'sheet': os.path.join(OUT, f'{name}.png')}
    for k in ('vram_bad', 'export_bad'):
        if ent['frame_check'] and k in ent['frame_check']: ent['frame_check'][k] = ent['frame_check'][k][:10]
    ip = os.path.join(OUT, 'index.json')
    idx = json.load(open(ip)) if os.path.exists(ip) else {}
    idx[name] = ent
    json.dump(idx, open(ip, 'w'), indent=1)
    print(name, 'sheet', len(lines), 'rows ->', ent['sheet'], '| found', ent['moves_found'], 'moves,', ent['attacks_found'], 'attacks; exported',
          ent['moves_exported'], 'moves +', len(ent['specials_exported']), 'specials')

if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
