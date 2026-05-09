#!/usr/bin/env python3
"""Analyze danmaku per-frame trace CSV."""
import csv, sys, collections

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/danmaku_trace.csv"

with open(path) as f:
    rows = list(csv.DictReader(f))

if not rows:
    print("Empty trace."); sys.exit(1)

total = len(rows)
misses = sum(1 for r in rows if int(r['vblank_miss']))
exceptions = sum(1 for r in rows if int(r['exception']))
resets = sum(1 for r in rows if int(r['vec_switch']) == 2 and int(r['alive']))
watchdogs = sum(1 for r in rows if int(r['watchdog']))

# Active bullet stats
actives = [int(r['active']) for r in rows if int(r['alive'])]
curves = [int(r['curves']) for r in rows if int(r['alive'])]
spawns = [int(r['spawns']) for r in rows if int(r['alive'])]
cmds = [int(r['cmds']) for r in rows if int(r['alive'])]
cycles = [int(r['m68k_cyc']) for r in rows if int(r['alive'])]
vram_wr = [int(r['vram_wr']) for r in rows if int(r['alive'])]

# Miss distribution by scheduler slot
miss_by_slot = collections.Counter()
for r in rows:
    if int(r['vblank_miss']):
        miss_by_slot[int(r['slot'])] += 1

# Miss distribution over time (10-second windows)
window = 600
miss_windows = collections.Counter()
for r in rows:
    if int(r['vblank_miss']):
        w = int(r['frame']) // window
        miss_windows[w] += 1

# Burst detection
miss_frames = [int(r['frame']) for r in rows if int(r['vblank_miss'])]
max_burst = 0
cur_burst = 0
burst_start = 0
worst_burst = (0, 0)
prev_f = -2
for f in miss_frames:
    if f == prev_f + 1:
        cur_burst += 1
    else:
        if cur_burst > max_burst:
            max_burst = cur_burst
            worst_burst = (burst_start, burst_start + cur_burst)
        cur_burst = 1
        burst_start = f
    prev_f = f

print(f"=== DANMAKU TRACE ANALYSIS ===")
print(f"Total frames: {total}")
print(f"Game frames (alive): {len(actives)}")
print()
print(f"=== STABILITY ===")
print(f"VBlank misses: {misses} ({misses*100/max(total,1):.1f}%)")
print(f"Exceptions: {exceptions}")
print(f"Resets (vec→BIOS while alive): {resets}")
print(f"Watchdog fires: {watchdogs}")
print()
if misses > 0:
    print(f"=== MISS ANALYSIS ===")
    print(f"Peak burst: {max_burst} consecutive (frames {worst_burst[0]}-{worst_burst[1]})")
    print(f"By scheduler slot:")
    for slot in sorted(miss_by_slot):
        print(f"  slot {slot:2d}: {miss_by_slot[slot]} misses")
    print(f"By 10-second window:")
    for w in sorted(miss_windows):
        t0 = w * window // 60
        t1 = (w + 1) * window // 60
        print(f"  {t0:3d}-{t1:3d}s: {miss_windows[w]} misses")
    print()

if actives:
    print(f"=== BULLETS ===")
    print(f"Active: avg={sum(actives)//len(actives)} peak={max(actives)}")
    print(f"Curves: avg={sum(curves)//len(curves)} peak={max(curves)}")
    print(f"Spawns/frame: avg={sum(spawns)/len(spawns):.1f} peak={max(spawns)}")
    print()

if cycles:
    budget = 202752
    work = [int(r['work_cyc']) for r in rows if int(r['alive']) and 'work_cyc' in r and int(r['work_cyc']) > 0]
    idle = [int(r['idle_cyc']) for r in rows if int(r['alive']) and 'idle_cyc' in r]
    waits = [int(r['wait_spins']) for r in rows if int(r['alive']) and 'wait_spins' in r]
    print(f"=== CPU ===")
    print(f"Budget: {budget} cycles/frame")
    if work:
        avg_work = sum(work) // len(work)
        peak_work = max(work)
        avg_idle = sum(idle) // len(idle) if idle else 0
        print(f"Work cycles: avg={avg_work} ({avg_work*100//budget}%) peak={peak_work} ({peak_work*100//budget}%)")
        print(f"Idle cycles: avg={avg_idle} ({avg_idle*100//budget}%) = headroom")
        print(f"Wait spins:  avg={sum(waits)//len(waits)} peak={max(waits)} min={min(waits)}")
    else:
        avg_cyc = sum(cycles) // len(cycles)
        print(f"68K cycles/frame: avg={avg_cyc} (wait counter not available)")
    print()

if vram_wr:
    print(f"=== VRAM ===")
    print(f"Writes/frame: avg={sum(vram_wr)//len(vram_wr)} peak={max(vram_wr)}")
    if cmds:
        print(f"Cmd buf usage: avg={sum(cmds)//len(cmds)} peak={max(cmds)}/512")
