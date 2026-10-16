#!/usr/bin/env python3
"""RELEASE GATE (2026-10-16): the whole game as a real MVS / AES runs it, on BOTH BIOS, in ~1 min. Replaces
odd_access_proof.py (which runs this now). Our stock emulator core forgives what the real hardware does not; two
FPGA / MVS crashes in a day came from that:
  - 0.10.152: a crash ~24 s after power-on, in the attract demo (route trees as byte arrays at odd addresses read as
    words: export_bm.py aligns them);
  - 0.10.153: a RESET the moment the posts bonus was won, as SS2's referee was to walk in (rf_draw: GCC 15 compiled
    `(int16_t)(rf.y >> 8)` into a word read at rf.y + 1, an odd address: the 68000's address error, SNK's BIOS then
    garbage, a green screen and the title; main.c fx8_int). odd_access_proof.py's short campaign never won a bonus.

    python3 hw_strict_proof.py [--rom examples/brawler/brawler.neo] [--build build] [--out /data/tmp/hw_strict]
           [--attract 8100] [--max 60000] [--wave-limit 600] [--boss-limit 900]

1. odd_static_lint.py on build/rom.elf: no word / long access at an odd address anywhere in the code (also run by
   every link: examples/brawler/Makefile).
2. fpga_playthrough.py on the address-error core (aerr_core.sh, rebuilt when stale) for mvs-mvs (SNK MVS BIOS) and
   uni-aes (UniBIOS as an AES) at once: power on, 3 attract loops, coin, START, the select, EVERY stage (a wave the bot
   has not finished in --wave-limit frames cleared by poke, the boss KO'd after --boss-limit), the posts bonus WON
   (walk, A, A, A), SS2's referee's whole speech, the D quirk in his held message (the fury on his body, his
   HORRIBLE ATMOSPHERE), the Ki training after stage 3 passed, the ending's screens, back to the title.
ALL OK = on both: zero odd-address word / long accesses (a 68000's ADDRESS ERROR); zero CPU exceptions (bus /
address error, illegal instruction, zero divide, CHK, TRAPV, privilege, line A / F, TRAP); zero WATCHDOG resets and
the longest stretch without a $300001 kick under half the watchdog's 8 frames (Geolith = MAME = the boards); no reset
(the game's tick counter never goes back); the stack's high-water mark at least 1 KB above .bss; no fault past the
BIOS's boot (PC outside ROM / RAM / BIOS, a long stay in the BIOS, ticks stalled); and the run went through all of
the above (posts won, the referee's phases incl. HOLD and the quirk's WAIT, the referee hit, the Ki game, the
ending, the title after it). Each failure is listed (an odd access with the symbol its address and PPC fall in,
build/rom.elf); the runs' logs and screenshots stay in OUT/<sys>/ (run.json, shots/)."""
import argparse, bisect, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))

ap = argparse.ArgumentParser()
ap.add_argument('--rom', default=os.path.join(GAME, 'brawler.neo')); ap.add_argument('--game', default=GAME)
ap.add_argument('--build', default='build'); ap.add_argument('--out', default='/data/tmp/hw_strict')
ap.add_argument('--attract', type=int, default=8100); ap.add_argument('--max', type=int, default=60000)
ap.add_argument('--wave-limit', type=int, default=600); ap.add_argument('--boss-limit', type=int, default=900)
a = ap.parse_args()
WD_MAX = 4.0                                             # frames: half the watchdog's 8
STACK_MIN = 1024                                         # bytes above .bss's end

import harness
harness.aerr_core()
elf = os.path.join(a.game, a.build, 'rom.elf')
env = dict(os.environ, BRAWLER_AERR='1'); env.pop('BRAWLER_CORE', None)
procs = {}
for sys_ in ('mvs-mvs', 'uni-aes'):
    out = os.path.join(a.out, sys_); os.makedirs(out, exist_ok=True)
    procs[sys_] = subprocess.Popen([sys.executable, os.path.join(HERE, 'fpga_playthrough.py'), '--rom', a.rom, '--game', a.game,
                                    '--build', a.build, '--sys', sys_, '--out', out, '--attract', str(a.attract),
                                    '--max', str(a.max), '--wave-limit', str(a.wave_limit), '--boss-limit', str(a.boss_limit),
                                    '--aerr', '1'],
                                   env=env, stdout=open(os.path.join(out, 'log.txt'), 'w'), stderr=subprocess.STDOUT)

bad = False
lint = subprocess.run([sys.executable, os.path.join(HERE, 'odd_static_lint.py'), elf], capture_output=True, text=True)
print('static: ' + ('OK' if lint.returncode == 0 else 'FAIL') + ': ' + lint.stdout.strip().replace('\n', '\n    '))
bad |= lint.returncode != 0

syms = []                                                # (addr, name) of the ELF's symbols, for the report
try:
    for ln in subprocess.run(['m68k-linux-gnu-nm', '-n', elf], capture_output=True, text=True).stdout.splitlines():
        f = ln.split()
        if len(f) == 3 and f[1] in 'tTdDbBrR': syms.append((int(f[0], 16), f[2]))
except FileNotFoundError: pass
addrs = [s[0] for s in syms]
def sym(x):
    i = bisect.bisect_right(addrs, x) - 1
    return f'{syms[i][1]}+{x - syms[i][0]:#x}' if i >= 0 else '?'

for sys_, p in procs.items():
    rc = p.wait(); out = os.path.join(a.out, sys_)
    if rc: print(f'{sys_}: fpga_playthrough failed (rc {rc}): {out}/log.txt'); bad = True; continue
    r = json.load(open(os.path.join(out, 'run.json'))); rc_ = r.get('reached', {})
    n = r.get('odd_access_count')
    play = any(k[0] == 1 for k, f in r['screens'])
    faults = [f for f in r['faults'] if f[0] >= 600 and 'odd-address' not in f[1]]   # (the BIOS's boot: ticks stall)
    st = r.get('stack') or {}
    refs = rc_.get('referee', [])
    checks = [
        (n == 0, f'odd-address word / long accesses: {n}'),
        (r.get('exceptions') == 0, f'CPU exceptions: {r.get("exceptions")}'),
        (r.get('watchdog_resets') == 0 and (r.get('watchdog_worst_frames') or 99) < WD_MAX,
         f'watchdog: {r.get("watchdog_resets")} resets, longest without a kick {r.get("watchdog_worst_frames")} frames '
         f'(limit {r.get("watchdog_limit_frames")}, gate < {WD_MAX})'),
        ((st.get('headroom') or 0) >= STACK_MIN, f'stack: lowest {st.get("lowest")}, {st.get("headroom")} bytes above .bss ({st.get("bss_end")})'),
        (not faults, f'faults past the boot (resets, hangs, PC off the map, BIOS screens): {faults[:5]}'),
        (play and rc_.get('posts_won') and {'WALK', 'HOLD', 'WAIT'} <= set(refs) and rc_.get('quirk_hit')
         and rc_.get('ki_played') and rc_.get('ending') and rc_.get('title_after_ending'),
         f'went through: stages {rc_.get("stages")}, bonus games {rc_.get("bonus_games")}, posts won {rc_.get("posts_won")}, '
         f'the referee {"/".join(refs)}, hit {rc_.get("quirk_hit")}, the Ki game {rc_.get("ki_played")}, '
         f'the ending {rc_.get("ending")}, the title after it {rc_.get("title_after_ending")}'),
    ]
    ok = all(c for c, _ in checks); bad |= not ok
    print(f'{sys_}: {"OK" if ok else "FAIL"}: {r["frames"]} frames')
    for c, what in checks: print(f'    {"ok  " if c else "FAIL"} {what}')
    for x in r.get('odd_access', [])[:40]:
        print(f'    {"read " if x[1] else "write"} {x[0]:#08x} ({sym(x[0])}) by PPC {x[3]:#08x} ({sym(x[3])})')
print('ALL OK' if not bad else 'FAIL')
sys.exit(1 if bad else 0)
