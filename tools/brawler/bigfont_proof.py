#!/usr/bin/env python3
"""The big font's proof (Bruno 2026-10-14: "a BIG bitmap font ... I like the one from SAVAGE REIGN"; make_bigfont.py,
main.c "big text", game.json big_text), all in OUR emulator:

1. rip     Savage Reign (/data/roms/savagere.neo) played with emu/neogeo_sdl --capture (coin, START, Hayate, the first
           fight): ROUND 1 (frame 2420), FIGHT! (2500), ROUND 3 / ROUND 4 + -FINAL- (the round counter $1084AA poked to
           2 / 3 before the call, frame 2392): VRAM + palette RAM dumps; checks: the round call's sprites show exactly
           make_bigfont.SR_GLYPHS' tiles in palette $BD, FIGHT! = SR_FIGHT's 8 x 4 tiles in $BC, $BD (bank 1) =
           make_bigfont.SR_PAL; render() (the construction) re-draws R O U N D from their masks (pixel agreement)
2. brawler the brawler's messages as the game draws them (harness.py, scenario.py recipes bigfont-*): STAGE 1 START,
           STAGE CLEAR, GAME OVER, TIME OVER, FURY UNLOCKED! / PRESS D: the first tick the message stands still; checks:
           its sprites (BT_SPR..) show the font's tiles, nothing past 96 sprites on a line, the fix row it replaced empty
3. sheet   OUT/sheet.png: Savage Reign's screens (the letters' rows cut at 1:1) next to the brawler's, 1:1; OUT/glyphs.png
           (make_bigfont sheet: the originals + the full set, x3)

    python3 bigfont_proof.py [OUT]       (default /data/tmp/bigfont/proof; examples/brawler built)   exit 1 on a FAIL"""
import ctypes as C, json, os, struct, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import make_bigfont as MB
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/bigfont/proof'
EMU = os.path.join(HERE, '..', '..', 'emu', 'neogeo_sdl')
GAMESEQ = '1500:-,6:o,60:-,6:s,300:-,6:a,200:-,6:a,200:-,6:a,200:-,6:a,3000:-'   # one credit, Hayate, the first fight
fails = 0


def check(ok, msg):
    global fails
    print('OK  ' if ok else 'FAIL', msg); fails += 0 if ok else 1


def sr_run(name, frames, poke=None):
    d = os.path.join(OUT, 'sr', name); os.makedirs(d, exist_ok=True)
    env = dict(os.environ, SEQ=GAMESEQ, SNAPS=','.join(map(str, frames)), SNAPDIR=d,
               VRAMDUMP=';'.join(f'{f}:{d}/{f}.vram' for f in frames), PALDUMP=';'.join(f'{f}:{d}/{f}.pal' for f in frames))
    if poke: env['POKE'] = ';'.join(f'{f}:{poke}' for f in range(2200, max(frames) + 1))
    subprocess.run(['timeout', '900', EMU, MB.ROM, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return d


def sprites(v):
    w = lambda a: v[a * 2] << 8 | v[a * 2 + 1]
    out = []; x = y = h = 0
    for i in range(1, 381):
        s3 = w(0x8200 + i); s4 = w(0x8400 + i)
        if s3 & 0x40: x = (x + 16) & 0x1FF
        else: h = s3 & 0x3F; y = 496 - (s3 >> 7); x = s4 >> 7
        if not h: continue
        tiles = [(w(i * 64 + r * 2) | ((w(i * 64 + r * 2 + 1) >> 4) & 0xF) << 16, w(i * 64 + r * 2 + 1) >> 8) for r in range(min(h, 32))]
        out.append(dict(i=i, x=x, y=y if y < 256 else y - 512, h=h, tiles=tiles))
    return out


def rip():
    """Savage Reign's round call and FIGHT! in our emulator -> the screens (304 x 224) to show, checks"""
    shots = {}
    d = sr_run('round1', [2420, 2500])
    for f, want, pal in ((2420, 'ROUN' 'D1', 0xBD), (2500, None, 0xBC)):
        v = open(f'{d}/{f}.vram', 'rb').read(); p = open(f'{d}/{f}.pal', 'rb').read()
        sp = [s for s in sprites(v) if s['tiles'] and s['tiles'][0][1] == pal]
        got = [[t - MB.T0 for t, _ in s['tiles']] for s in sp]
        if want: exp = [c for k in want for c in MB.SR_GLYPHS[k][0]]; label = 'ROUND 1'
        else: exp = MB.SR_FIGHT; label = 'FIGHT!'
        check(got == exp, f'Savage Reign {label} (frame {f}): {len(sp)} sprites in palette ${pal:02X} show make_bigfont\'s tiles {"" if got == exp else got}')
        if want:
            pw = [struct.unpack('>H', p[8192 + (pal * 16 + k) * 2:8192 + (pal * 16 + k) * 2 + 2])[0] for k in range(16)]
            check(pw == MB.SR_PAL, f'Savage Reign palette ${pal:02X} (bank 1) = make_bigfont.SR_PAL')
        shots[label] = f'{d}/snap_{f}.ppm'
    for val, label, glyphs in (('02', 'ROUND 3', 'ROUND3'), ('03', 'ROUND 4 + FINAL', 'ROUND4')):
        d = sr_run('round' + label[6], [2392], poke=f'1084AA={val}')
        v = open(f'{d}/2392.vram', 'rb').read()
        sp = [s for s in sprites(v) if s['tiles'] and s['tiles'][0][1] == 0xBD]
        got = [[t - MB.T0 for t, _ in s['tiles']] for s in sp]
        exp = [c + ([MB.SR_FINAL[k]] if glyphs == 'ROUND4' else []) for k, c in enumerate(c for g in glyphs for c in MB.SR_GLYPHS[g][0])]
        check(got == exp, f'Savage Reign {label} (round counter $1084AA = {val}): its sprites show make_bigfont\'s tiles {"" if got == exp else got}')
        shots[label] = f'{d}/snap_2392.ppm'
    for k in 'ROUND':                                   # the construction vs Savage Reign's own letters
        a = MB.glyph(k)[0]; r = MB.render(a >= 4)
        shape = ((a > 0) == (r > 0)).mean(); pens = ((a == r) | ~((a >= 4) & (r >= 4))).mean()
        check(shape > 0.97 and pens > 0.95, f'render() re-draws Savage Reign\'s {k}: shape {shape:.1%}, colours {pens:.1%} of its pixels')
    return shots


MESSAGES = [  # (label, scenario recipe, the fix row the big text replaced (None: moved / kept), the text expected)
    ('STAGE 1 START', 'bigfont-stage-intro', 13),
    ('STAGE CLEAR', 'bigfont-stage-clear', 13),
    ('GAME OVER', 'bigfont-game-over', 10),
    ('TIME OVER', 'bigfont-time-over', 13),
    ('FURY UNLOCKED! / PRESS D', 'bigfont-posts-won', 13),
]


def brawler():
    """each message in a process of its own (one harness core a process)"""
    global fails
    shots = {}
    for label, rid, row in MESSAGES:
        r = subprocess.run([sys.executable, os.path.abspath(__file__), OUT, '--one', rid], capture_output=True, text=True)
        out = [l for l in r.stdout.splitlines() if l.startswith(('OK', 'FAIL'))]
        print('\n'.join(out) or r.stderr[-2000:])
        fails += sum(l.startswith('FAIL') for l in out) + (0 if out else 1)
        p = os.path.join(OUT, f'brawler_{rid}.png')
        if os.path.exists(p): shots[label] = p
    return shots


def one(want):
    import harness as H, scenario
    G = os.path.join(HERE, '..', '..', 'examples', 'brawler')
    R = json.load(open(os.path.join(HERE, 'scenarios.json')))
    shots = {}
    for label, rid, row in MESSAGES:
        if rid != want: continue
        p = os.path.join(OUT, f'brawler_{rid}.png')
        if os.path.exists(p): os.remove(p)
        if rid == 'bigfont-posts-won':                     # (the posts broken by bonus_proof's player: walk up, A)
            import bonus_proof
            P = bonus_proof.Proof(G, os.path.join(OUT, 'bonus')); P.play_posts('terry', 'a'); b = P.b; R[rid]['do_keys'] = '1:-'
        else:
            b = H.Brawler(game=G); b.game = G
            scenario.setup(b, R[rid])
        S = b.syms; n = b.core.retro_get_memory_size(3)
        vram = (C.c_uint16 * (n // 2)).from_address(b.core.retro_get_memory_data(3))
        btn = lambda: b.r(S['bt_n'], 1)
        keys = [(int(m), k) for m, k in (p.split(':') for p in R[rid]['do_keys'].split(','))] + [(4000, '-')]
        done = False; t = 0
        for m, k in keys:
            for _ in range(m):
                b.run(1, p1=k); t += 1
                if btn() and b.r(S['bt_t'], 1) >= 40: done = True; break   # (standing still: past any slide, 16 ticks here)
            if done: break
        check(done, f'{label}: the big text shows ({rid}, {t} frames)')
        if not done: continue
        n_spr = btn()
        p = os.path.join(OUT, f'brawler_{rid}.png'); b.screenshot(p); shots[label] = p
                                                            # the font's columns as bigfont.h has them
        hdr = open(os.path.join(G, 'build', 'bigfont.h')).read()
        words = [int(x, 16) for x in hdr.split('bigf_map[BIGF_COLS * BIGF_ROWS * 2] = {')[1].split('}')[0].split(',')]
        cols = {tuple(words[i:i + 6:2]) for i in range(0, len(words), 6)}
        bt = 324
        got = [tuple(vram[(bt + i) * 64 + r * 2] for r in range(3)) for i in range(n_spr)]
        check(all(g in cols for g in got) and all((vram[(bt + i) * 64 + 1] >> 8) == 250 for i in range(n_spr)),
              f'{label}: {n_spr} sprites (324-{323 + n_spr}) show the font\'s columns in palette 250')
        cnt = [0] * 224; x = y = h = 0                     # the LSPC's per-line count (sprites 1-381, sticky chains)
        for i in range(1, 381):
            s3 = vram[0x8200 + i]
            if not (s3 & 0x40): y = 496 - (s3 >> 7); h = s3 & 0x3F
            if not h: continue
            yy = y if y < 256 else y - 512
            for L in range(max(0, yy), min(224, yy + 16 * h)): cnt[L] += 1
        check(max(cnt) <= 96, f'{label}: at most {max(cnt)} sprites on a line (96)')
        txt = ''.join(chr(v) if 0x20 < v < 0x7F else ' ' for v in (vram[0x7000 + c * 32 + row + 2] & 0xFFF for c in range(1, 39))).strip()   # (FIX_print's row r = VRAM row r + 2)
        check(not any(w in txt for w in ('START', 'CLEAR', 'GAME OVER', 'TIME OVER', 'FURY')), f'{label}: the fix row {row} it replaced holds {txt!r}')
    return shots


def crop_rows(p, y0, y1):
    return Image.open(p).convert('RGB').crop((0, y0, 304, y1))


def sheet(sr, br):
    """1:1: Savage Reign's calls (their rows) | the brawler's screens (whole)"""
    W = 304 * 2 + 12
    rows_sr = [(k, crop_rows(v, 50, 130)) for k, v in sr.items()]
    br_imgs = [(k, Image.open(v).convert('RGB')) for k, v in br.items()]
    H = 16 + sum(im.height + 14 for _, im in rows_sr) + 16 + ((len(br_imgs) + 1) // 2) * (224 + 14) + 8
    s = Image.new('RGB', (W, H), (255, 255, 255)); d = ImageDraw.Draw(s)
    d.text((4, 2), "Savage Reign (our emulator, 1:1): the round call's letters and FIGHT!", fill=(0, 0, 0))
    y = 16
    for k, im in rows_sr:
        d.text((4, y), k, fill=(0, 0, 0)); s.paste(im, (4, y + 12)); y += im.height + 14
    d.text((4, y), 'The brawler (our emulator, 1:1): its headlines in the big font (game.json big_text)', fill=(0, 0, 0)); y += 14
    for i, (k, im) in enumerate(br_imgs):
        x = 4 + (i % 2) * (304 + 6); yy = y + (i // 2) * (224 + 14)
        d.text((x, yy), k, fill=(0, 0, 0)); s.paste(im, (x, yy + 12))
    s.save(os.path.join(OUT, 'sheet.png'))


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    if '--one' in sys.argv:
        one(sys.argv[sys.argv.index('--one') + 1]); sys.exit(1 if fails else 0)
    sr = rip()
    br = brawler()
    sheet(sr, br)
    MB.sheet(os.path.join(OUT, 'glyphs.png'))
    print(os.path.join(OUT, 'sheet.png'), os.path.join(OUT, 'glyphs.png'))
    print('ALL OK' if not fails else f'{fails} FAIL')
    sys.exit(1 if fails else 0)
