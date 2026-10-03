#!/usr/bin/env python3
"""Animation gallery: one self-contained HTML page that plays every exported animation with KOF95's own timing.
Uses only the exporter's output (kof95_export.json + kof95_c1/c2.bin), so it shows exactly what the ROM build gets.
    python3 gallery.py EXPORTDIR OUT.html"""
import base64, io, json, os, sys
import numpy as np
from PIL import Image
import rom  # noqa: F401  (puts the shared neosdk library on the path)
from neogeo.sprite_decode import decode_tile, decode_color
from preview import load

GROUPS = [
    ('Movement', ['idle', 'walk_fwd', 'walk_back', 'turn', 'prejump', 'jump_up_rise', 'jump_up_fall', 'land',
                  'jump_fwd_rise', 'jump_fwd_fall', 'jump_back_rise', 'jump_back_fall', 'crouch_down', 'crouch', 'crouch_up',
                  'hop_up_rise', 'hop_up_fall', 'hop_fwd_rise', 'hop_fwd_fall',
                  'run_start', 'run', 'run_stop', 'backstep_start', 'backstep', 'backstep_land', 'roll_start', 'roll', 'roll_end']),
    ('Guard', ['guard_stand_in', 'guard_stand', 'guard_stand_out', 'guard_crouch_in', 'guard_crouch']),
    ('Attacks', [f'atk_{b}_{k}' for b in 'abcd' for k in ('close', 'far', 'jump', 'jump_diag', 'crouch')]),
    ('Body toss (C+D)', ['body_toss', 'body_toss_air']),
    ('Special moves', []),
    ('Throw', ['throw', 'throw_c', 'throw_d', 'air_throw']),
    ('Win poses', ['win_a', 'win_a_hold', 'win_b', 'win_b_hold', 'win_c', 'win_c_hold', 'win_d', 'win_d_hold']),
    ('Other animation slots', []),        # every slot of the character's table not shown above (KOF96/98 exports)
    ('Hit and knockdown', ['hit_stand_light', 'hit_stand_mid', 'hit_stand_heavy', 'hit_crouch_light', 'hit_crouch_heavy',
                           'hit_air', 'air_land', 'blowback', 'knockdown_flight', 'knockdown_bounce', 'trip', 'knockdown_fall', 'down', 'getup', 'dizzy']),
]

def render_frame(region, frame):
    """-> (index image 'L', origin x, origin y) cropped to the frame's parts; pixel = palette index, 0 = transparent"""
    placed = []
    for p in frame['parts']:
        cols = p['tiles']; w, h = len(cols) * 16, len(cols[0]) * 16
        img = np.zeros((h, w), dtype=np.uint8)
        for c, col in enumerate(cols):
            for r, t in enumerate(col):
                if t: img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = decode_tile(region, t)
        x0 = -p['dx'] - w if p['hflip'] else p['dx']
        y0 = -p['dy'] - h if p['vflip'] else p['dy']
        if p['hflip']: img = img[:, ::-1]
        if p['vflip']: img = img[::-1, :]
        placed.append((x0, y0, img))
    minx = min(x for x, _, _ in placed); miny = min(y for _, y, _ in placed)
    maxx = max(x + i.shape[1] for x, _, i in placed); maxy = max(y + i.shape[0] for _, y, i in placed)
    out = np.zeros((maxy - miny, maxx - minx), dtype=np.uint8)
    for (x, y, img), p in zip(placed, frame['parts']):
        m = img > 0                                          # pixel = palette of the block * 16 + colour (KOF96 parts
        out[y - miny:y - miny + img.shape[0], x - minx:x - minx + img.shape[1]][m] = img[m] + 16 * p.get('pal', 0)   # carry their own)
    ys, xs = np.nonzero(out)                                # crop to the drawn pixels
    if len(xs) == 0: return Image.new('L', (1, 1)), 0, 0
    y1, y2, x1, x2 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    return Image.fromarray(out[y1:y2, x1:x2], 'L'), int(-minx - x1), int(-miny - y1)

def atlas(images):
    """shelf-pack -> (PNG data URI, [(x, y)])"""
    W, x, y, row, pos = 1024, 0, 0, 0, []
    for im in images:
        if x + im.width > W: x, y, row = 0, y + row + 1, 0
        pos.append((x, y)); x += im.width + 1; row = max(row, im.height)
    sheet = Image.new('P', (W, y + row + 1), 0)
    sheet.putpalette([v for i in range(256) for v in (i, 0, 0)])
    for im, p in zip(images, pos): sheet.paste(im, p)
    deep = any(im.getextrema()[1] > 15 for im in images)         # several palettes per frame: 8-bit indices
    buf = io.BytesIO()
    sheet.save(buf, 'PNG', optimize=True, bits=8 if deep else 4, transparency=0)   # drawn pixels never have colour 0
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode(), pos

def signed(v): return v - 256 if v > 127 else v

def build(d):
    ex, region = load(d); mv = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'moves.json')))
    data = {'groups': GROUPS, 'chars': {}, 'set_names': {'kof98': ['A button', 'B button', 'C button', 'D button'], 'kof99': ['Set 1', 'Set 2 (B)']}.get(ex.get('game'), ['Regular', 'Mirror']), 'reactions': mv.get('reactions', {}) if ex.get('game', 'kof95') == 'kof95' else {},
            'game': ex.get('game', 'kof95'),
            'poses': json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                 {'kof95': 'victim_poses.json', 'kof96': '../kof96/victim_poses96.json',
                                                  'kof98': '../kof96/victim_poses98.json', 'kof99': '../kof96/victim_poses99.json'}[ex.get('game', 'kof95')])))['poses']}
    for name, ch in ex['characters'].items():
        rendered = [render_frame(region, f) for f in ch['frames']]
        uri, pos = atlas([r[0] for r in rendered])
        def pkey(f):
            kind, idx = f.get('palette', ['body', None])
            return 'b' if kind == 'body' else f'c{idx}' if kind == 'char' else f'g{idx}'
        frames = [[x, y, im.width, im.height, ox, oy, pkey(f)] for (im, ox, oy), (x, y), f in zip(rendered, pos, ch['frames'])]
        anims = {}
        for m, a in ch['anims'].items():
            anims[m] = {'slot': a['slot'], 'hold': a['mode'] == 'hold', **({'states': a['states']} if 'states' in a else {}),
                        'steps': [[s['frame'], s['ticks'],
                                   [[int(k[0], 16), signed(b[0]), signed(b[1]), b[2], b[3]] for k, b in s['boxes'].items()]]
                                  for s in a['steps']]}
        pal = lambda p: [[f'#{r:02x}{g:02x}{b:02x}', f'{w:04X}'] for w, (r, g, b) in ((w, decode_color(w)) for w in p)]
        hexpal = lambda p: [f'#{r:02x}{g:02x}{b:02x}' for r, g, b in (decode_color(w) for w in p)]
        used = {f[6] for f in frames}
        blocks = {k[1:] for k in used if k[0] == 'c'} | {str(p.get('pal', 0)) for f in ch['frames'] for p in f['parts']}
        sets = len(ch['block_palettes'])
        block = [{b: hexpal(ch['block_palettes'][s][int(b)]) for b in blocks} for s in range(sets)]
        gpal = {k[1:]: hexpal(ch['effect_palettes'][k[1:]] if k[1:] in ch['effect_palettes'] else ch['effect_palettes'][int(k[1:])])
                for k in used if k[0] == 'g'}
        data['chars'][name] = {'id': ch['id'], 'atlas': uri, 'block': block, 'gpal': gpal, 'specials': ch.get('specials', []), 'commands': ch.get('commands', []), 'frames': frames, 'anims': anims, 'physics': ch['physics'],
                               'palettes': [pal(p) for p in ch['palette_sets']] if 'palette_sets' in ch else [pal(ch['palette']), pal(ch['palette_mirror'])],
                               'throws': ch.get('throws', {})}
    return data

if __name__ == '__main__':
    # --split: atlases as separate PNGs next to the page (atlas/<name>.png) instead of data URIs, for a page over 16 MB
    split = '--split' in sys.argv; args = [a for a in sys.argv[1:] if a != '--split']
    d, out = args[0], args[1]
    data = build(d)
    if split:
        import base64
        os.makedirs(os.path.join(os.path.dirname(os.path.abspath(out)), 'atlas'), exist_ok=True)
        for name, ch in data['chars'].items():
            png = base64.b64decode(ch['atlas'].split(',', 1)[1])
            open(os.path.join(os.path.dirname(os.path.abspath(out)), 'atlas', f'{name}.png'), 'wb').write(png)
            ch['atlas'] = f'atlas/{name}.png'
    tpl = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gallery_template.html')).read()
    tpl = tpl.replace('KOF95 sprites face left', f"{data['game'].upper()} sprites face left")
    if data['game'] == 'kof99':
        for a, b in (('KOF95 Animation Bank', 'KOF99 Animation Bank'), ("The King of Fighters '95", "The King of Fighters '99"),
                     ('as stored in the program ROM: 16 colours per set, $1D9000 + id × $400 for the regular set and +$200 for the mirror set',
                      'as stored in the program ROM: palette n at $2D77F0 + n × 32; body n = $100 + id × $20 + $10 × colour set (two sets; B at character select gives set 2), effects n = $520 + id × $10 (checked against palette RAM in our emulator)'),
                     ("Walk, jump launch and gravity come from each character's record at $7AF16 + id × 128 in the program ROM; walking back is ¾ of the walk speed and the jump drift equals it, as measured in MAME. Knockdown values were measured on Terry; their gravity is shared by every reaction.",
                      'Walk speed from the table at $B51C4 + id × 4, jump launch and gravity from $B524C + id × 8 (program ROM); walking back and the jump drift assumed equal to the walk speed, as in KOF96/98.'),
                     ("Slots 82–101 in every character\\'s state table: five per button, in this column order.",
                      'Game states 80–115 named with KOF98’s numbers (KOF99 runs the same engine; not yet checked in a running game).')):
            tpl = tpl.replace(a, b)
    if data['game'] == 'kof98':
        for a, b in (('KOF95 Animation Bank', 'KOF98 Animation Bank'), ("The King of Fighters '95", "The King of Fighters '98"),
                     ('as stored in the program ROM: 16 colours per set, $1D9000 + id × $400 for the regular set and +$200 for the mirror set',
                      'as stored in the program ROM (bank 2): palette n at $2D77F0 + n × 32; body n = $100 + id × $40 + $10 × colour set (A–D, A and B shown), effects n = $B80 + id × $10'),
                     ("Walk, jump launch and gravity come from each character's record at $7AF16 + id × 128 in the program ROM; walking back is ¾ of the walk speed and the jump drift equals it, as measured in MAME. Knockdown values were measured on Terry; their gravity is shared by every reaction.",
                      'Walk speed from the table at $ABFC8 + id × 4, jump launch and gravity from $AC060 + id × 8 (program ROM); walking back and the jump drift equal the walk speed, as measured in MAME on Kyo.'),
                     ("Slots 82–101 in every character\\'s state table: five per button, in this column order.",
                      'Game states 80–115 (close, far, jump, jump diagonal, crouch per button), slots from each fighter’s own state map ($B9536).')):
            tpl = tpl.replace(a, b)
    if data['game'] == 'kof96':
        for a, b in (('KOF95 Animation Bank', 'KOF96 Animation Bank'), ("The King of Fighters '95", "The King of Fighters '96"),
                     ('as stored in the program ROM: 16 colours per set, $1D9000 + id × $400 for the regular set and +$200 for the mirror set',
                      'as stored in the second program ROM (bank 1): palette n at $200002 + n × 32, the body is n = $100 + id × $20, the mirror set 16 palettes later'),
                     ("Walk, jump launch and gravity come from each character's record at $7AF16 + id × 128 in the program ROM; walking back is ¾ of the walk speed and the jump drift equals it, as measured in MAME. Knockdown values were measured on Terry; their gravity is shared by every reaction.",
                      'Walk speed from the table at $6E8EE + id × 4, jump launch and gravity from $6E96E + id × 8 (program ROM); walking back and the jump drift equal the walk speed, as measured in MAME on Kyo.'),
                     ("Slots 82–101 in every character\\'s state table: five per button, in this column order.",
                      'Game states 80–115 (close, far, jump, jump diagonal, crouch per button), slots from the state map every KOF96 fighter shares.'),
                     ("Inputs decoded from the game\\'s command recogniser (motion patterns at $7A6B0, 8 commands per fighter); each move was then performed in MAME with that input and replayed here frame by frame, projectiles included, in their own palettes. P = A or C, K = B or D; [2] 35f, 8 = hold down 35 frames, then up.",
                      "Inputs decoded from the game\\'s command recogniser ($11C76; lists at $71B9E, one per facing side); every command was performed in MAME with each button and every distinct move is replayed here frame by frame, projectiles included. Numpad notation facing right (6 = forward); [4] = charge back. Supers were done on red life."),
                     ("The victim here is the same fighter in the mirror colours.",
                      "The victim\\'s pose and offset come from the ROM throw list for the chosen victim (validated frame for frame against MAME on Yuri); the default victim is the same fighter in the mirror colours.")):
            tpl = tpl.replace(a, b)
    open(out, 'w').write(tpl.replace('/*DATA*/null', json.dumps(data, separators=(',', ':'))))
    print(out, os.path.getsize(out) // 1024, 'KB')
