#!/usr/bin/env python3
"""Double Dragon proofs (our emulator only):
 1. check: every frame of each fighter playing its first special (button D) from its vs state: the ROM render
    (dd.draw_def of the PREVIOUS frame's +$04 at THIS frame's +$D8 / 496 - +$DA - 2 (no -2 when airborne, +$01
    bit 7: $8538), facing from +$01 bit 5, palette +$03) vs the
    fighter's VRAM slots rendered as the LSPC shows them; full-size frames only (camera zoom 0)
 2. screen: Billy's frame vs the emulator's own screenshot (fighter-opaque pixels)
 3. sheets: contact sheet per fighter, idle + that special (every step, ROM render, the fighter's palette)
    -> /data/tmp/dd95/out/<name>.png, /data/tmp/dd95/out/check.json"""
import json, os, numpy as np
from PIL import Image, ImageDraw
import cap_dd as c, dd, commands_dd as cm, specials_dd as sp
from fighters_dd import CHARS, STATE
OUT = '/data/tmp/dd95/out'; os.makedirs(OUT, exist_ok=True)
P1 = 0x10042A

def first_special(ch):
    for e in cm.entries(ch):
        if e['flags'] & 0xD or e['anims'][3] < 0 or e['flags'] & 2: continue
        return e
def check(ch):
    e = first_special(ch)
    seq = sp.inputs(e, 'd')
    rows = c.run('30:R,12:-,' + seq + ',80:-', load=STATE.format(ch), vram=True)
    n = ok = 0; bad = []
    for prev, r in zip(rows, rows[1:]):
        F = dd.fighter_fields(r['ram'], P1)
        if F['zx'] or F['zy'] or F['sx'] == -32768: continue
        v = dd.vram_words(r['vram']); pw = dd.vram_words(r['pal'])[:4096]
        a = dd.render_vram(v, pw, dd.slots_with_palette(v, F['pal']))
        diffs = []
        Q = dd.fighter_fields(prev['ram'], P1)
        for D in (Q['def_'], F['def_']):                 # the vblank draw sees fields of either frame
          for G in (F, Q):
            b = dd.draw_def(D, pw, palette=F['pal'], hflip=not (G['dir'] & 0x20), size=(320, 224), groups={0},
                            origin=(G['sx'], (496 - G['sy'] - (0 if G['dir'] & 0x80 else 2)) & 511))
            diffs.append(int(np.any(a != b, axis=-1).sum()))
        n += 1
        if min(diffs) == 0: ok += 1
        else: bad.append((r['f'], F['anim'], hex(F['def_']), min(diffs)))
    return dict(name=CHARS[ch], special=cm.notation(e), anim=e['anims'][3], frames=n, identical=ok, bad=bad[:10]), rows

def screen_check(frames=(5, 9, 13, 17, 21)):
    """the ROM render (step of the RAM before the frame, position of the frame) vs the emulator's own screenshot
    (snap N = the screen of VRAM row f = N - 2): every fighter-opaque pixel; colours compared through the one-to-one
    map between our RGB conversion and the frontend's (each Neo Geo colour -> one screenshot colour)"""
    rows = c.run('3:-,30:R', vram=True, snaps=','.join(map(str, frames)))
    res = []
    for fr in frames:
        shot = np.array(Image.open(f'/data/tmp/dd95/snap_{fr}.ppm').convert('RGB'))
        k = fr - 3; r = rows[k]; F = dd.fighter_fields(r['ram'], P1)          # snap N = VRAM row f N - 2 [meas]
        pw = dd.vram_words(r['pal'])[:4096]; best = None
        for D in (dd.fighter_fields(rows[k - 1]['ram'], P1)['def_'], F['def_']):
            b = dd.draw_def(D, pw, palette=F['pal'], hflip=not (F['dir'] & 0x20), size=(320, 224), groups={0},
                            origin=(F['sx'], (496 - F['sy'] - (0 if F['dir'] & 0x80 else 2)) & 511))[:, 8:312]
            m = b[..., 3] > 0; src = b[..., :3][m]; dst = shot[m]
            pairs = {}
            for x, y in zip(map(tuple, src), map(tuple, dst)): pairs.setdefault(x, set()).add(y)
            bad = sum(1 for x, y in zip(map(tuple, src), map(tuple, dst)) if len(pairs[x]) > 1)
            if best is None or bad < best[1]: best = (int(m.sum()), bad, hex(D))
        res.append(dict(snap=fr, pixels=best[0], conflicting=best[1], def_=best[2]))
    return res, (224, 304)

def sheet(ch, rows):
    e = first_special(ch)
    pw = dd.vram_words(rows[0]['pal'])[:4096]
    pal = dd.fighter_fields(rows[0]['ram'], P1)['pal']
    frames = [('idle', s['def_']) for s in dd.steps(ch, 0)[1]]
    for p in sp.chain(ch, e['anims'][3]):
        frames += [(f"{p['anim']}", s['def_']) for s in dd.steps(ch, p['anim'])[1]]
    W, H = 150, 190; cols = 10
    img = Image.new('RGB', (W * cols, H * ((len(frames) + cols - 1) // cols) + 20), (255, 255, 255))
    dr = ImageDraw.Draw(img)
    dr.text((4, 4), f"{CHARS[ch]} (ch {ch}): idle + {cm.notation(e)} D (anims {[p['anim'] for p in sp.chain(ch, e['anims'][3])]})", fill=0)
    for i, (lab, w) in enumerate(frames):
        a = dd.draw_def(w, pw, palette=pal, hflip=True, size=(W, H - 14), origin=(W // 2, H - 24))
        x0, y0 = (i % cols) * W, 20 + (i // cols) * H
        img.paste(Image.fromarray(a[..., :3]), (x0, y0), Image.fromarray(a[..., 3]))
        dr.rectangle([x0, y0, x0 + W - 1, y0 + H - 1], outline=0)
        dr.text((x0 + 3, y0 + H - 13), f"{lab} {w:03X}", fill=0)
    img.save(f'{OUT}/{CHARS[ch].split()[0].lower()}.png')

if __name__ == '__main__':
    res = {}
    for ch in [0, 2, 4, 5, 6, 7, 8, 9, 10, 11]:
        r, rows = check(ch); res[CHARS[ch]] = r; print(r, flush=True)
        sheet(ch, rows)
    sc, shape = screen_check(); res['screen'] = dict(shape=shape, frames=sc); print('screen', shape, sc)
    json.dump(res, open(f'{OUT}/check.json', 'w'), indent=1)
