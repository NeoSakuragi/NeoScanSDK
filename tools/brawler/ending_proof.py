#!/usr/bin/env python3
"""The ending (game.json "ending", main.c "the ending"; Bruno 2026-10-11, decisions open-2026-10-11 card ending-music),
played in our emulator (harness.py, BRAWLER_CORE, the arcade system mvs-mvs, a fresh save): stage 5, FIGHTER kills its
boss (screenmusic_proof's 'ending' recipe), then no input to the BIOS: the KO, the win poses, ENDING (the story), STAFF
ROLL, THANK YOU, BOSS UNLOCKED, back to the BIOS. Out per fighter: a screenshot at each screen's start + 30 frames and
every 120 frames (OUT/FIGHTER/fNNNNN_<screen>.png), a contact sheet (OUT/FIGHTER.png), the sound commands the 68000
sent per screen (OUT/FIGHTER.json). --skip: START every 70 frames from the KO on (each screen passes at its minimum).

    python3 ending_proof.py [--skip] [ROM] [OUT] [FIGHTER...]   (default examples/brawler/brawler.neo, /data/tmp/ending,
                                                                 terry haohmaru billy_lee)"""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
FRAMES = 5200


def child(rom, out, name, skip):
    import harness as H, scenario
    b = H.Brawler(rom=rom, options=scenario.SYSTEMS['mvs-mvs']); b.game = H.GAME; Y = b.syms
    import ctypes as C
    hdr = open(os.path.join(H.GAME, 'build', 'snd', 'songs.h')).read()
    mus = {int(v, 16): n for n, v in re.findall(r'#define MUS_(\w+) +0x([0-9A-F]+)', hdr)}
    ev = []
    def wt(addr, v, s):
        if addr in (0x320000, 0x320001): ev.append((b.frame, v & 0xFF if s == 1 else v >> 8))
    WT = C.CFUNCTYPE(None, C.c_uint32, C.c_uint32, C.c_int)(wt)
    scenario.setup(b, {'setup': {'mode': 'stage', 'fighter': name, 'stage': 4, 'wave': 5, 'wait': 150, 'alone': True,
                                 'foe_hp': 1, 'gap': 50}})
    b.core.retro_neoscan_m68k_write_tap(WT)
    d = os.path.join(out, name); os.makedirs(d, exist_ok=True)
    for f in os.listdir(d): os.remove(os.path.join(d, f))
    def scr():
        m = b.r(Y['mode'], 1)
        if m == 1: return 'play phase %d' % b.r(Y['phase'], 1) + (' drama' if b.r(Y['dr_on'], 1) else '')
        if m == 4: return ['ENDING', 'STAFF ROLL', 'THANK YOU'][b.r(Y['en_st'], 1)]
        return {0: 'select', 2: 'title/attract', 3: 'BOSS UNLOCKED', 5: 'GAME OVER'}.get(m, 'mode %d' % m)
    t0 = b.frame; screens = []; shots = []; since = 0
    b.seq('60:-,3:a')
    while b.frame - t0 < FRAMES:
        k = set()
        if skip and screens and screens[-1][1] not in ('play phase 2',) and (b.frame - t0) % 70 == 0: k = {'s'}
        b.pad = [k, set()]; b.core.retro_run(); b.frame += 1; b.pad = [set(), set()]
        c = scr()
        if not screens or screens[-1][1] != c: screens.append((b.frame - t0, c)); since = 0
        since += 1
        if since == 30 or (since > 30 and since % 120 == 30) or (c == 'ENDING' and since in (8, 300, 700)):
            p = os.path.join(d, 'f%05d_%s.png' % (b.frame - t0, c.replace(' ', '_').replace('/', '-')))
            b.screenshot(p); shots.append(p)
    def screen_at(f):
        c = screens[0][1]
        for g, n in screens:
            if g <= f: c = n
        return c
    snd = {}
    for i, (f, v) in enumerate(ev):
        tag = '%02X' % v
        if i and ev[i - 1][1] == 0x07 and v in mus: tag += ' (MUS_%s)' % mus[v]
        snd.setdefault(screen_at(f - t0), []).append((f - t0, tag))
    json.dump({'screens': screens, 'sound': snd, 'shots': shots}, open(os.path.join(out, name + '.json'), 'w'), indent=1)
    from PIL import Image                                   # contact sheet: the shots, 4 a row, half size
    ims = [Image.open(p) for p in shots]
    if ims:
        w, h = ims[0].size; cols = 4; sw, sh = w // 2 * 2 // 2, h // 2 * 2 // 2
        sheet = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * h))
        for i, im in enumerate(ims): sheet.paste(im, ((i % cols) * w, (i // cols) * h))
        sheet.save(os.path.join(out, name + '.png'))


def main():
    a = sys.argv[1:]; skip = '--skip' in a; a = [x for x in a if x != '--skip']
    rom = a[0] if a else os.path.join(HERE, '..', '..', 'examples', 'brawler', 'brawler.neo')
    out = a[1] if len(a) > 1 else '/data/tmp/ending'
    names = a[2:] or ['terry', 'haohmaru', 'billy_lee']
    if os.environ.get('ENDING_CHILD'): return child(rom, out, names[0], skip)
    os.makedirs(out, exist_ok=True)
    for n in names:                                         # one emulator at a time
        subprocess.run([sys.executable, __file__] + (['--skip'] if skip else []) + [rom, out, n], check=True, env=dict(os.environ, ENDING_CHILD='1'))
        r = json.load(open(os.path.join(out, n + '.json')))
        print(n, 'screens', r['screens'])
        for s, cmds in r['sound'].items(): print('   %-16s' % s, ' '.join(t for _, t in cmds)[:300])


if __name__ == '__main__': main()
