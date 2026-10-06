#!/usr/bin/env python3
"""Double Dragon (Technos 1995): Billy / Jimmy's transformation (A+B+C+D while powered), captured in our emulator.

    python3 transform_dd.py            # all: capture, checks, state, sheets, specials of the transformed form
    -> /data/neogeo_dict/doubledr/transform.json, cap/p1_01.state (transformed Billy vs Jimmy),
       /data/tmp/dd95/out/transform/{sequence,side_by_side,dragon}.png

Code [read in /data/tmp/dd95/p1.dis]:
  entry  $2428C (top of the command recogniser, before the command table): object +$00 bit 0 (powered) AND character
         0 or 2 AND the four buttons HELD (+$18 & $F0 = $F0) AND on the ground (+$01 bit 7 clear) -> animation 81 ($51),
         step 0, +$02 &= $3F, +$F3 bit 3 set (= transforming)
  powered $3F14-$3FA0: per player (damage taken high byte, capped 104) + (gauge +$E6 high byte, capped 104), both as the
         HUD shows them (they move toward the value a step per frame) >= 104 with a gauge > 0 -> +$00 bit 0. The power
         gauge fills the life bar from the other end: powered = the two bars meet.
  anim 81 header b0 = 11 -> step handler $21944 (table $20C2C): at a step's first frame, step attr bit 4 -> palette
         slot +$03 -= 2 (18 -> 16, the transformed colours preloaded there; anim 99 adds 4 back), attr bit 5 ->
         character +$1B += 1 and +$F3 bit 3 cleared (the form change itself, step 19).
  cancel $20BD4: a new animation without header flag bit 4 while +$F3 bit 3 is set (anim 81 has it) -> +$F3 bit 3,
         powered and the gauge cleared; $25FB2: hit while +$F3 bit 3 -> the same. Anim 81 has no body box (box types
         0 / $200 / $8x), so nothing can hit it [inf from the boxes, meas: P2's 236D at 3 timings never connects].
  revert $1173C (round init): character 1 / 3 -> 0 / 2 (and $10DCB0 += 1); the form lasts until the round ends.
  powered after the change: kept (+$00 bit 0 stays); $25C5A: hits of a powered attacker +25 % damage; $25D90: no
         gauge gain while powered; the KO ($22066) clears powered + gauge of both fighters."""
import json, os, sys
import numpy as np
from PIL import Image, ImageDraw
import cap_dd as c, dd

OUT = '/data/tmp/dd95/out/transform'
JSON = '/data/neogeo_dict/doubledr/transform.json'
STATE1 = '/data/neogeo_dict/doubledr/cap/p1_01.state'
P1, P2 = 0x10042A, 0x10052A
POWER = '2:100450=20,100510=48'      # damage taken $2000 (life kept visible), gauge $48xx: $20 + $48 >= 104 -> powered
PRESS = 80                           # A+B+C+D on rows 81-84 (powered from row 74)
SEQ = f'{PRESS}:-,4:abcd,130:-'

def b(R, a): return R[a - 0x100000]
def obj(R, base):
    F = dd.fighter_fields(R, base)
    F.update(dmg=c.u16(R, base + 0x26), gauge=c.u16(R, base + 0xE6), f3=b(R, base + 0xF3), step_attr=b(R, base + 2))
    return F

def capture():
    snaps = list(range(PRESS - 1, PRESS + 112, 3))
    rows = c.run(SEQ, pokes=POWER, vram=True, snaps=','.join(str(s + 2) for s in snaps),
                 save=f'{PRESS + 120}:{STATE1}')
    tl = []
    for r in rows:
        F = obj(r['ram'], P1); G = obj(r['ram'], P2)
        tl.append(dict(f=r['f'], ch=F['ch'], anim=F['anim'], step=F['step'], def_=F['def_'], x=F['x'], y=F['y'],
                       pal=F['pal'], powered=F['flags'] & 1, f3=F['f3'], dmg=F['dmg'], gauge=F['gauge'],
                       p2anim=G['anim'], p2dmg=G['dmg'], snd=r['snd']))
    return rows, tl, snaps

def events(tl):
    t0 = next(q['f'] for q in tl if q['anim'] == 81)
    ev = []; prev = None
    for q in tl:
        k = (q['ch'], q['anim'], q['step'], q['pal'], q['powered'], q['f3'])
        if k != prev and q['f'] >= t0 - 1:
            ev.append(dict(t=q['f'] - t0, f=q['f'], ch=q['ch'], anim=q['anim'], step=q['step'], def_=q['def_'],
                           y_up=488 - q['y'], pal=q['pal'], powered=q['powered'], transforming=bool(q['f3'] & 8),
                           dmg=q['dmg'], gauge=q['gauge'], snd=[f'{s:02X}' for s in q['snd']]))
        prev = k
    return t0, ev

def checks():
    """the rules measured: hit during the rise (P2 dashes in), the dragon's hit (P1 close), round end + next round"""
    out = {}
    for t in (74, 84, 100):                              # P2 236D (Jimmy dash) timed into the transformation
        rows = c.run(SEQ, f'{t}:-,3:D,3:DL,3:L,3:Ld,100:-', pokes=POWER)
        tl = [(r['f'], obj(r['ram'], P1), obj(r['ram'], P2)) for r in rows if 'ram' in r]
        out[f'p2_dash_at_{t}'] = dict(p1_damage_change=tl[-1][1]['dmg'] - tl[5][1]['dmg'],
                                      p1_ch_end=tl[-1][1]['ch'], p1_powered_end=tl[-1][1]['flags'] & 1,
                                      p2_damage=tl[-1][2]['dmg'], p2_anims=sorted({x[2]['anim'] for x in tl[t:]}))
    rows = c.run('50:-,24:R,6:-,4:abcd,120:-', pokes=POWER)          # close: the dragon's boxes reach P2
    tl = [(obj(r['ram'], P1), obj(r['ram'], P2)) for r in rows]
    hits = [(i + 1, tl[i][1]['dmg'] - tl[i - 1][1]['dmg']) for i in range(1, len(tl)) if tl[i][1]['dmg'] != tl[i - 1][1]['dmg']]
    out['close'] = dict(gap=tl[79][1]['x'] - tl[79][0]['x'], p1_anims=sorted({q[0]['anim'] for q in tl[79:]}), p2_hits=hits,
                        p2_anims=sorted({q[1]['anim'] for q in tl[79:]}),
                        p1_ch_end=tl[-1][0]['ch'])
    rows = c.run(SEQ.replace(',130:-', ',120:-,30:R,4:d,1100:-'), pokes=POWER + ';210:100550=67')
    seen = []; prev = None
    for r in rows:
        F = obj(r['ram'], P1); G = obj(r['ram'], P2)
        k = (F['ch'], F['anim'] == 99, F['pal'], F['flags'] & 1, F['gauge'] > 0, G['dmg'] >= 0x6800)
        if k != prev: seen.append(dict(f=r['f'], ch=F['ch'], anim=F['anim'], pal=F['pal'], powered=F['flags'] & 1,
                                       gauge=F['gauge'], p2_ko=G['dmg'] >= 0x6800, dmg=F['dmg']))
        prev = k
    out['round_end'] = seen
    rows = c.run('300:-', '130:-,4:abcd,150:-', pokes='2:100610=68')     # Jimmy (P2): 2 -> 3
    seen = []; prev = None
    for r in rows:
        G = obj(r['ram'], P2); k = (G['ch'], G['anim'], G['pal'])
        if k != prev: seen.append(dict(f=r['f'], ch=G['ch'], anim=G['anim'], pal=G['pal'], y_up=488 - G['y']))
        prev = k
    out['jimmy_p2'] = seen
    return out

def label_font(dr, xy, s): dr.text(xy, s, fill=(0, 0, 0))

def sequence_sheet(tl, t0, snaps):
    """the game screen (emulator screenshots: snap N shows RAM row N - 2 [meas, proof_dd]) every 3 frames"""
    cols, W, H = 6, 320, 224
    img = Image.new('RGB', (cols * W, ((len(snaps) + cols - 1) // cols) * (H + 16) + 22), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    label_font(dr, (4, 4), f'Double Dragon: Billy (P1, powered) A+B+C+D, game screen every 3 frames; t = frame - {t0} '
                           f'(first frame of anim 81); a = anim, s = step, ch = character, pal = palette slot')
    by = {q['f']: q for q in tl}
    for i, f in enumerate(snaps):
        p = f'/data/tmp/dd95/snap_{f + 2}.ppm'
        if not os.path.exists(p): continue
        x0, y0 = (i % cols) * W, 22 + (i // cols) * (H + 16)
        img.paste(Image.open(p).convert('RGB').resize((W, H)), (x0, y0 + 14))
        q = by.get(f, {})
        dr.rectangle([x0, y0, x0 + W - 1, y0 + H + 13], outline=(0, 0, 0))
        label_font(dr, (x0 + 3, y0 + 2), f"t{f - t0:+d} f{f} ch{q.get('ch')} a{q.get('anim')} s{q.get('step')} pal{q.get('pal')} up{488 - q.get('y', 488)}")
    img.save(f'{OUT}/sequence.png'); return f'{OUT}/sequence.png'

def uniq_steps(ch, n):
    """the animation and the ones its header's 'next' chains to (specials_dd.chain), consecutive equal defs merged"""
    import specials_dd as sp
    out = []
    for p in (sp.chain(ch, n) if n else [dict(anim=0)]):
        for i, s in enumerate(dd.steps(ch, p['anim'])[1]):
            if out and out[-1]['def_'] == s['def_']: out[-1]['frames'] += s['ticks'] + 1; continue
            out.append(dict(i=f"{p['anim']}.{i}", def_=s['def_'], frames=s['ticks'] + 1))
    return out

PAIRS = [('idle', 0, 0), ('walk forward', 1, 1), ('623 D (normal 90 / transformed 94)', 90, 94),
         ('236 D (86 / 86)', 86, 86), ('214 D (94 / 98)', 94, 98), ('j.214 D (98) / 41236 D (90)', 98, 90),
         ('super 236+AB (82; the form has no super) / its anim 99 = the round-win pose (palette back to 18 at step 2)', 82, 99)]

def side_by_side(pw):
    """ROM renders (dd.draw_def), palettes from the capture's palette RAM: slot 18 = Billy, slot 16 = transformed"""
    W, H, cols = 170, 200, 11
    blocks = []
    for lab, a0, a1 in PAIRS:
        blocks.append((f'{lab}: Billy ch 0 anim {a0}', 0, a0, 18))
        blocks.append((f'{lab}: transformed ch 1 anim {a1}', 1, a1, 16))
    lines = sum(1 + (len(uniq_steps(ch, n)) + cols - 1) // cols for _, ch, n, _ in blocks)
    img = Image.new('RGB', (cols * W, 24 + lines * H), (255, 255, 255)); dr = ImageDraw.Draw(img)
    label_font(dr, (4, 4), 'Billy (ch 0, palette 18) vs transformed Billy (ch 1, palette 16): every distinct sprite '
                           'definition of the animation, ROM render; label = step, definition, frames shown')
    y = 24
    for lab, ch, n, pal in blocks:
        label_font(dr, (4, y + 4), lab); y += 18
        st = uniq_steps(ch, n)
        for k, s in enumerate(st):
            if k and k % cols == 0: y += H
            a = dd.draw_def(s['def_'], pw, palette=pal, hflip=True, size=(W, H - 30), origin=(W // 2, H - 40))
            x0 = (k % cols) * W
            img.paste(Image.fromarray(a[..., :3]), (x0, y), Image.fromarray(a[..., 3]))
            dr.rectangle([x0, y, x0 + W - 1, y + H - 30], outline=(0, 0, 0))
            dr.line([x0 + W // 2 - 4, y + H - 40, x0 + W // 2 + 4, y + H - 40], fill=(0, 0, 0))
            label_font(dr, (x0 + 3, y + H - 28), f"s{s['i']} d{s['def_']} {s['frames']}f")
        y += H - 18
    img = img.crop((0, 0, img.width, y + 4)); img.save(f'{OUT}/side_by_side.png'); return f'{OUT}/side_by_side.png'

def dragon(pw):
    """the dragon effect = group 1 of anim 81's sprite definitions (own palette 128), drawn with the body (no object)"""
    h, st = dd.steps(0, 81)
    W, Hh, cols = 260, 300, 7
    img = Image.new('RGB', (cols * W, 40 + ((len(st) + cols - 1) // cols) * Hh), (255, 255, 255)); dr = ImageDraw.Draw(img)
    label_font(dr, (4, 4), 'Transformation (anim 81): the dragon effect = group 1 of each step definition, palette 128 '
                           '(fixed in the def); grey = the body (group 0); + = the anchor (feet), facing right as on P1 side')
    label_font(dr, (4, 18), 'label: step, frames, def, effect columns, effect box from the anchor (x0..x1, y0..y1 px, y up)')
    rec = []; t = 0
    for i, s in enumerate(st):
        d = dd.sdef(s['def_']); g1 = [col for col in d['cols'] if col['group'] >= 1]
        body = dd.draw_def(s['def_'], pw, palette=18, hflip=True, size=(W, Hh - 30), origin=(W // 2, Hh - 50), groups={0})
        fx = dd.draw_def(s['def_'], pw, palette=18, hflip=True, size=(W, Hh - 30), origin=(W // 2, Hh - 50),
                         groups={g for g in range(1, 8)})
        x0, y0 = (i % cols) * W, 40 + (i // cols) * Hh
        canvas = np.full((Hh - 30, W, 3), 255, np.uint8)
        m = body[..., 3] > 0; canvas[m] = 200
        m = fx[..., 3] > 0; canvas[m] = fx[..., :3][m]
        img.paste(Image.fromarray(canvas), (x0, y0))
        ax, ay = x0 + W // 2, y0 + Hh - 50
        dr.line([ax - 6, ay, ax + 6, ay], fill=(0, 0, 0)); dr.line([ax, ay - 6, ax, ay + 6], fill=(0, 0, 0))
        dr.rectangle([x0, y0, x0 + W - 1, y0 + Hh - 31], outline=(0, 0, 0))
        ys, xs = np.nonzero(fx[..., 3])
        box = [int(xs.min() - W // 2), int(xs.max() - W // 2), int((Hh - 50) - ys.max()), int((Hh - 50) - ys.min())] if len(xs) else None
        label_font(dr, (x0 + 3, y0 + Hh - 28), f"s{i} {s['ticks'] + 1}f d{s['def_']} fx cols {len(g1)}")
        label_font(dr, (x0 + 3, y0 + Hh - 15), f"t{t}-{t + s['ticks']} box {box}")
        rec.append(dict(step=i, t=t, frames=s['ticks'] + 1, def_=s['def_'], attr=s['attr'], sound=s['b5'],
                        effect_cols=len(g1), effect_palettes=sorted({at >> 8 for col in g1 for _, at in col['tiles']}),
                        effect_box_px=box, boxes=[(hex(x['type']), x['x'], x['y'], x['hw'], x['hh']) for x in dd.boxes(s['w6'])]))
        t += s['ticks'] + 1
    img.save(f'{OUT}/dragon.png'); return f'{OUT}/dragon.png', rec

def stats():
    """ROM tables, Billy (0) vs transformed (1), and Jimmy (2) vs (3)"""
    def hv(ch, n):
        h = dd.steps(ch, n)[0]
        return [int.from_bytes(h[2:4], 'big', signed=True) / 256, int.from_bytes(h[4:6], 'big', signed=True) / 256]
    out = {}
    for ch in (0, 1, 2, 3):
        out[ch] = dict(defence=dd.u8(dd.DEFENCE + ch), palette_base=f'{dd.u8(0x20C1E + ch):02X}',
                       damage={cat: [dd.u16(dd.DAMAGE + 64 * ch + 8 * cat + 2 * l) for l in range(4)] for cat in range(4)},
                       walk_fwd=hv(ch, 1), walk_back=hv(ch, 3), jump_fwd=hv(ch, 7), jump_back=hv(ch, 9),
                       idle_frames=sum(s['ticks'] + 1 for s in dd.steps(ch, 0)[1]))
    return out

def main():
    os.makedirs(OUT, exist_ok=True)
    rows, tl, snaps = capture()
    t0, ev = events(tl)
    pw = dd.vram_words(rows[PRESS + 100]['pal'])[:4096]
    res = dict(press_rows=[PRESS + 1, PRESS + 4], anim81_first_row=t0, events=ev)
    res['sequence_png'] = sequence_sheet(tl, t0, snaps)
    res['side_by_side_png'] = side_by_side(pw)
    res['dragon_png'], res['dragon_steps'] = dragon(pw)
    res['palette_cycle_slot16_pen9'] = sorted({f'{dd.vram_words(r["pal"])[16 * 16 + 9]:04X}' for r in rows[t0 + 70:t0 + 90]})
    res['stats'] = stats()
    res['checks'] = checks()
    json.dump(res, open(JSON, 'w'), indent=1)
    for e in ev: print(e)
    print(json.dumps(res['checks'], indent=0)[:3000])

if __name__ == '__main__':
    main()
