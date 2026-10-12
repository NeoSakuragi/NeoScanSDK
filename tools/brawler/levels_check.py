#!/usr/bin/env python3
"""The Factory's Levels in the built game, in our emulator (harness.py, BRAWLER_CORE): each stage started the scenario
way (scenario.setup mode stage, a fighter with no theme so stage 1 plays its own song), the music command the 68000
sends after the $07 unlock vs game.json's stage music (build/snd/songs.h MUS_*), a screenshot per stage (the HUD's
stage name, bottom left).

    python3 levels_check.py GAME_DIR OUT [--stages 1,2] [--fighter rosa]  -> OUT/stage<n>.png, prints OK / FAIL lines"""
import ctypes as C, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)


def child(game, out, si, fighter):
    import harness as H, scenario
    b = H.Brawler(game=game); b.game = game
    ev = []
    def wt(addr, v, s):
        if addr in (0x320000, 0x320001): ev.append(v & 0xFF if s == 1 else v >> 8)
    WT = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)(wt)
    b.core.retro_neoscan_m68k_write_tap(WT)
    scenario.setup(b, {'setup': {'mode': 'stage', 'fighter': fighter, 'stage': si, 'wave': 0}})
    b.run(90)
    b.core.retro_neoscan_m68k_write_tap(C.cast(None, type(WT)))
    songs = [ev[i + 1] for i in range(len(ev) - 1) if ev[i] == 0x07 and 0x20 <= ev[i + 1] < 0x60]
    b.screenshot(os.path.join(out, f'stage{si + 1}.png'))
    print(json.dumps({'song': songs[-1] if songs else None}))


def main():
    a = sys.argv[1:]
    if a and a[0] == '--child': return child(a[1], a[2], int(a[3]), a[4])
    game, out = a[0], a[1]; os.makedirs(out, exist_ok=True)
    g = json.load(open(os.path.join(game, 'game.json')))
    st = [int(x) for x in a[a.index('--stages') + 1].split(',')] if '--stages' in a else range(1, len(g['stages']) + 1)
    fighter = a[a.index('--fighter') + 1] if '--fighter' in a else 'rosa'
    mus = {k: int(v, 16) for k, v in re.findall(r'#define MUS_(\w+)\s+(0x[0-9A-Fa-f]+)', open(os.path.join(game, 'build', 'snd', 'songs.h')).read())}
    ok = True
    for n in st:
        s = g['stages'][n - 1]
        r = subprocess.run([sys.executable, __file__, '--child', game, out, str(n - 1), fighter], capture_output=True, text=True)
        try: d = json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError): print(f'stage {n}: FAIL (no result) {r.stderr[-400:]}'); ok = False; continue
        good = d['song'] == mus[s['music']]
        ok &= good
        print(f"stage {n} {s['name']!r}: song ${d['song'] or 0:02X} expected {s['music']} ${mus[s['music']]:02X}: {'OK' if good else 'FAIL'}"
              + f"  -> {out}/stage{n}.png (the HUD's stage name, bottom left: look)")
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
