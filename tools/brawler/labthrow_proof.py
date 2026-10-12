#!/usr/bin/env python3
"""A pack's throws in the Character Lab's shell (the slot's victim side, vthrow.h bvslot_t; docs/character_lab.md "The
pack format"), in our emulator (harness, the repo's Geolith core; never MAME):

    BRAWLER_CORE=<core> python3 labthrow_proof.py [FIGHTER] [VICTIM] [OUT] [--old]   (default terry, ryo,
                                    /data/tmp/labthrow; make LAB_SHELL=1 + make LAB_PACK=FIGHTER first; --old: the pack's
                                    header word +12 zeroed, as in a pack from before: the script's rows both ways)

The shell with FIGHTER's pack applied (lab_pack.apply: what a swap gives), the practice through the lab mailbox:
  row     P1 = the slot (FIGHTER from the pack) throws VICTIM forward and back: the victim plays the slot's own rows
          (fighter_t.vrw in .labslot, slot_vthr.row), frame for frame where the roster's own FIGHTER puts VICTIM
  column  P1 = VICTIM throws the slot: the slot plays its column's rows (slot_vthr.col), frame for frame as the
          roster's FIGHTER is thrown
-> OUT/sheet_lab_<case>.png (the slot's throw, every 4th frame) + OUT/labthrow.json"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness, lab_pack
from harness import Brawler

F = sys.argv[1] if len(sys.argv) > 1 else 'terry'
VIC = sys.argv[2] if len(sys.argv) > 2 else 'ryo'
OUT = sys.argv[3] if len(sys.argv) > 3 else '/data/tmp/labthrow'
GAME = harness.GAME
os.makedirs(OUT, exist_ok=True)
rom, why = lab_pack.apply(lab_pack.neo(os.path.join(GAME, 'lab-shell.neo')), open(os.path.join(GAME, 'packs', F + '.pack'), 'rb').read())
assert rom, why
OLD = '--old' in sys.argv                                  # a pack from before the victim side: its header word +12 = 0
if OLD:                                                    # (the 4 zeros it always had): the script's rows, both ways
    sys.argv.remove('--old'); OUT = os.path.join(OUT, 'old'); os.makedirs(OUT, exist_ok=True)
    d, sizes, lay = lab_pack.neo(os.path.join(GAME, 'lab-shell.neo')); m = bytearray(rom)
    for i in range(12, 16): m[lay['P'][0] + ((lab_pack.LABHDR_AT + i) ^ 1)] = 0   # (.neo P: each word low byte first)
    rom = bytes(m)
ROM = os.path.join(OUT, 'shell+' + F + '.neo'); open(ROM, 'wb').write(rom)
b = Brawler(rom=ROM, game=GAME, build='build_shell')
S = b.syms
names = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
SLOT = len(names)                                          # the shell's slot: the last index (build_tables add_slot)
PE = lab_pack.syms(os.path.join(GAME, 'build_pack_' + F, 'rom.elf'))   # the pack's .labslot symbols (a fixed region)
LS = (lab_pack.LABSLOT_AT, 0x100000)
LAB_REQ, LAB_FIGHTER, LAB_ACTIVE = 4, 5, 8                 # fighter.h lab_t (scenario.py)
D = 2                                                      # the practice's dummy (LAB_DUMMY)
fails = []
def check(ok, what):
    print(('ok   ' if ok else 'FAIL ') + what, flush=True)
    if not ok: fails.append(what)

def setup(p1, dummy):
    b.core.retro_reset(); b.frame = 0
    for _ in range(400): b.core.retro_run()
    lab = S['lab']
    for i, v in enumerate(b'LAB1'): b.w(lab + i, 1, v)
    b.w(lab + LAB_FIGHTER, 1, p1); b.w(lab + LAB_FIGHTER + 1, 1, dummy); b.w(lab + LAB_REQ, 1, 1)
    for _ in range(3000):
        b.run(1)
        if b.r(lab + LAB_ACTIVE, 1) == 1 and b.char_of(0) == p1 and b.char_of(D) == dummy: break
    else: raise RuntimeError('the practice never started: ' + b.brief())
    b.run(30)
    for i in range(1, 8):
        if i != D and b.fget(i, 'ch'): b.fset(i, 'state', b.states.index('OFF'))
    cam = (lambda v: v - 65536 if v >= 32768 else v)(b.r(S['cam_x'], 2))
    return cam

def throw(p1, dummy, act, shots=None, hide=False):
    """P1 grabs the dummy (walks into it) and throws (fwd: forward + A, back: back + A): per frame P1 / the dummy"""
    cam = setup(p1, dummy)
    back = act == 'back'
    x1 = cam + (250 if back else 60)
    b.place(0, x=x1, z=30); b.fset(0, 'facing', 1); b.place(D, x=x1 + 34, z=30); b.fset(D, 'facing', 0xFF)
    b.fset(D, 'hp', 120); b.run(2)
    for _ in range(80):
        b.run(1, p1='R')
        if b.states[b.fget(0, 'state')] == 'GRAB': break
    else: raise RuntimeError('no grab: ' + b.brief())
    rows, vrw = [], set()
    if shots: os.makedirs(shots, exist_ok=True)
    for f in range(200):
        k = ('La' if back else 'Ra') if f == 0 else ''
        if shots: b.pad = [set(k), set()]; b.screenshot(os.path.join(shots, f'{f:03d}.png'))
        else: b.run(1, p1=k)
        st = b.states[b.fget(D, 'state')]
        if st == 'THROWN': vrw.add((b.fget(D, 'vrw'), b.fget(D, 'vrn')))
        rows.append((st, round(b.fget(D, 'x') - b.fget(0, 'x'), 2), round(b.fget(D, 'y'), 2), b.fget(D, 'facing'),
                     b.fget(D, 'shown_frame') if not hide else None, b.states[b.fget(0, 'state')]))   # (the slot's
                                                           # own frames are numbered by its export: not compared)
        if f > 20 and st in ('DOWN', 'GETUP', 'IDLE') and rows[-1][5] in ('IDLE', 'WALK'): break
    return rows, vrw

def sheet(d, name, n, step=4):
    from PIL import Image, ImageDraw
    fs = sorted(x for x in os.listdir(d) if x.endswith('.png'))[:n:step]
    tiles = []
    for fn in fs:
        im = Image.open(os.path.join(d, fn)).convert('RGB'); g = ImageDraw.Draw(im)
        g.rectangle((0, 0, im.width, 11), fill=(255, 255, 255)); g.text((2, 0), f'{name} f{fn[:3]}', fill=(0, 0, 0)); tiles.append(im)
    W, H = tiles[0].size; cols = 4
    out = Image.new('RGB', (W * cols, H * ((len(tiles) + cols - 1) // cols)), (255, 255, 255))
    for i, t in enumerate(tiles): out.paste(t, ((i % cols) * W, (i // cols) * H))
    p = os.path.join(OUT, f'sheet_lab_{name}.png'); out.save(p); return p

fi, vi = names.index(F), names.index(VIC)
res = {}
if OLD:
    for p1, dm, act in ((SLOT, vi, 'fwd'), (SLOT, vi, 'back'), (vi, SLOT, 'fwd')):
        rows, vrw = throw(p1, dm, act)
        check(b.r(S['lab_vslot'], 4) == 0 and vrw == {(0, 0)} and rows[-1][0] in ('DOWN', 'GETUP', 'IDLE'),
              f'header word 0 ({"slot" if p1 == SLOT else VIC} {act}): lab_vslot 0, the script\'s rows {vrw}, the throw ends ({rows[-1][0]}, {len(rows)} frames)')
    print('ALL OK' if not fails else f'{len(fails)} FAILED'); sys.exit(1 if fails else 0)
for act in ('fwd', 'back'):                                # the row: the slot throws
    case = f'{F}_slot_{act}_{VIC}'
    d = os.path.join(OUT, case)
    slot_rows, vrw = throw(SLOT, vi, act, shots=d)
    vs = b.r(S['lab_vslot'], 4)
    check(vs == PE['slot_vthr'][0], f'{case}: lab_vslot = slot_vthr ${vs:X} (the pack\'s header word)')
    own = [v for v in vrw if v[0]]
    check(len(own) == 1 and LS[0] <= own[0][0] < LS[1], f'{case}: the victim plays rows in .labslot: {[(hex(a), n) for a, n in vrw]}')
    ref_rows, rvrw = throw(fi, vi, act)
    check(slot_rows == ref_rows, f'{case}: frame for frame as the roster\'s {F} throws {VIC} ({len(slot_rows)} frames; roster rows {[(hex(a), n) for a, n in rvrw]})')
    res[case] = {'frames': len(slot_rows), 'vrw': [hex(a) for a, n in vrw], 'same_as_roster': slot_rows == ref_rows, 'sheet': sheet(d, case, len(slot_rows))}
case = f'{VIC}_fwd_{F}_slot'                               # the column: the slot thrown
d = os.path.join(OUT, case)
slot_rows, vrw = throw(vi, SLOT, 'fwd', shots=d, hide=True)
own = [v for v in vrw if v[0]]
check(len(own) == 1 and LS[0] <= own[0][0] < LS[1], f'{case}: the slot plays its column\'s rows in .labslot: {[(hex(a), n) for a, n in vrw]}')
ref_rows, rvrw = throw(vi, fi, 'fwd', hide=True)
check(slot_rows == ref_rows, f'{case}: frame for frame as {VIC} throws the roster\'s {F} ({len(slot_rows)} frames)')
res[case] = {'frames': len(slot_rows), 'vrw': [hex(a) for a, n in vrw], 'same_as_roster': slot_rows == ref_rows, 'sheet': sheet(d, case, len(slot_rows))}
json.dump({'fighter': F, 'victim': VIC, 'cases': res, 'fails': fails}, open(os.path.join(OUT, 'labthrow.json'), 'w'), indent=1)
print('ALL OK' if not fails else f'{len(fails)} FAILED')
sys.exit(1 if fails else 0)
