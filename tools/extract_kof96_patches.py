#!/usr/bin/env python3
"""Extract FM instrument patches from KOF96 sound driver via Z80 tracing.

Runs the Z80 tracer against each of the 29 KOF96 songs, captures YM2610
FM operator register writes, and identifies unique FM patches.
"""

import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from z80_trace import Z80Tracer

MROM_PATH = os.path.join(os.path.dirname(__file__), '..', 'examples', 'hello_neo', 'res', 'kof96_m1.bin')

# KOF96 song commands: 0x20-0x2E (15 songs) and 0x40-0x4D (14 songs) = 29 total
SONG_CMDS = list(range(0x20, 0x2F)) + list(range(0x40, 0x4E))

# YM2610 FM register ranges per operator
# Op ordering in YM2610: op1=0, op3=8, op2=4, op4=12
# But the task says: op1=0, op2=8, op3=4, op4=12
# Actually in YM2610:
#   Slot 1 (op1): offset 0
#   Slot 2 (op2): offset 8
#   Slot 3 (op3): offset 4
#   Slot 4 (op4): offset 12
# The task definition says op1=0, op2=8, op3=4, op4=12 which matches standard numbering

OP_OFFSETS = [0, 8, 4, 12]  # op1, op2, op3, op4

# Register base addresses
REG_DT_MUL = 0x30
REG_TL     = 0x40
REG_KS_AR  = 0x50
REG_AM_DR  = 0x60
REG_SR     = 0x70
REG_SL_RR  = 0x80
REG_FB_ALG = 0xB0
REG_LR_AMS_PMS = 0xB4

REG_BASES = [REG_DT_MUL, REG_TL, REG_KS_AR, REG_AM_DR, REG_SR, REG_SL_RR]
REG_NAMES = ['DT_MUL', 'TL', 'KS_AR', 'AM_DR', 'SR', 'SL_RR']

def extract_patches_from_song(cmd, ticks=80):
    """Run one song and extract FM patches from register writes."""
    z = Z80Tracer(MROM_PATH)
    z.trace_ym = False
    z.verbose = False

    # Boot
    z.run_until_main_loop()
    z.iff1 = 1
    z.ym_writes.clear()

    # Send unlock (0x07) then song command
    commands = [0x07, cmd]
    cmd_idx = 0
    nmi_cooldown = 0
    irq_interval = 2000
    irq_counter = 0
    tick_num = 0
    total_steps = 0
    max_steps = ticks * irq_interval * 2

    while total_steps < max_steps and tick_num < ticks:
        if cmd_idx < len(commands) and nmi_cooldown <= 0:
            z.sound_code = commands[cmd_idx]
            z.fire_nmi()
            cmd_idx += 1
            nmi_cooldown = 500

        irq_counter += 1
        if irq_counter >= irq_interval and z.iff1:
            irq_counter = 0
            z.fire_irq()
            for _ in range(5000):
                z.step()
                total_steps += 1
                if z.is_main_loop(z.pc):
                    break
            tick_num += 1
            continue

        z.step()
        total_steps += 1
        nmi_cooldown -= 1

    return z.ym_writes

def parse_ym_writes(ym_writes):
    """Parse raw YM writes into register state per channel.

    Returns list of unique FM patches found.
    """
    # Track current address register for each port pair
    addr_a = 0  # Port A address (port 0x04)
    addr_b = 0  # Port B address (port 0x06)

    # Track register state for channels
    # Port A: ch offsets 0,1,2 (but only 1,2 are active FM channels)
    # Port B: ch offsets 0,1,2 (but only 1,2 are active FM channels)
    # We collect ALL channel writes to get maximum patch data
    ch_regs = {}  # (port, ch_offset) -> {reg_base: {op_offset: value}}
    ch_fb_alg = {}  # (port, ch_offset) -> value
    ch_lr = {}  # (port, ch_offset) -> value

    patches_seen = []

    for cyc, port, val in ym_writes:
        if port == 0x04:
            addr_a = val
        elif port == 0x06:
            addr_b = val
        elif port == 0x05:
            # Data write on Port A
            reg = addr_a
            _process_reg_write(reg, val, 'A', ch_regs, ch_fb_alg, ch_lr, patches_seen)
        elif port == 0x07:
            # Data write on Port B
            reg = addr_b
            _process_reg_write(reg, val, 'B', ch_regs, ch_fb_alg, ch_lr, patches_seen)

    return patches_seen

def _process_reg_write(reg, val, port_name, ch_regs, ch_fb_alg, ch_lr, patches_seen):
    """Process a single register write and detect complete patches."""
    if 0x30 <= reg <= 0x8F:
        # Operator register
        base = (reg & 0xF0)
        offset_raw = reg & 0x0F
        ch_offset = offset_raw & 0x03  # channel within port (0,1,2)
        op_offset = offset_raw & 0x0C  # operator offset (0,4,8,12)

        key = (port_name, ch_offset)
        if key not in ch_regs:
            ch_regs[key] = {}
        if base not in ch_regs[key]:
            ch_regs[key][base] = {}
        ch_regs[key][base][op_offset] = val

    elif 0xB0 <= reg <= 0xB2:
        ch_offset = reg - 0xB0
        key = (port_name, ch_offset)
        ch_fb_alg[key] = val

        # Check if we have a complete patch
        _try_extract_patch(key, ch_regs, ch_fb_alg, ch_lr, patches_seen)

    elif 0xB4 <= reg <= 0xB6:
        ch_offset = reg - 0xB4
        key = (port_name, ch_offset)
        ch_lr[key] = val

        # Check if we have a complete patch
        _try_extract_patch(key, ch_regs, ch_fb_alg, ch_lr, patches_seen)

def _try_extract_patch(key, ch_regs, ch_fb_alg, ch_lr, patches_seen):
    """Try to extract a complete patch from accumulated register writes."""
    if key not in ch_regs or key not in ch_fb_alg:
        return

    regs = ch_regs[key]

    # Check we have all 6 register bases and all 4 operators for each
    required_bases = [0x30, 0x40, 0x50, 0x60, 0x70, 0x80]
    for base in required_bases:
        if base not in regs:
            return
        for op_off in [0, 4, 8, 12]:
            if op_off not in regs[base]:
                return

    # Extract patch in our canonical op order: op1(0), op2(8), op3(4), op4(12)
    patch = {}
    for base, name in zip(required_bases, REG_NAMES):
        patch[name] = [
            regs[base][0],   # op1
            regs[base][8],   # op2
            regs[base][4],   # op3
            regs[base][12],  # op4
        ]

    patch['FB_ALG'] = ch_fb_alg[key]
    patch['LR_AMS_PMS'] = ch_lr.get(key, 0xC0)

    # Check if this patch is unique (compare all values)
    patch_tuple = _patch_to_tuple(patch)
    for existing in patches_seen:
        if _patch_to_tuple(existing) == patch_tuple:
            return  # already seen

    patches_seen.append(patch)

    # Reset this channel's accumulated regs so we can detect the next patch load
    ch_regs[key] = {}

def _patch_to_tuple(patch):
    """Convert patch dict to a hashable tuple for dedup."""
    return (
        tuple(patch['DT_MUL']),
        tuple(patch['TL']),
        tuple(patch['KS_AR']),
        tuple(patch['AM_DR']),
        tuple(patch['SR']),
        tuple(patch['SL_RR']),
        patch['FB_ALG'],
    )

def classify_patch(patch):
    """Try to classify what a patch sounds like based on its parameters."""
    alg = patch['FB_ALG'] & 0x07
    fb = (patch['FB_ALG'] >> 3) & 0x07

    # Carrier detection based on algorithm
    # Algorithms 0-3: 1 carrier (op4 in most), 4: 2 carriers, 5-6: 3 carriers, 7: all 4 carriers
    carrier_counts = {0:1, 1:1, 2:1, 3:1, 4:2, 5:3, 6:3, 7:4}
    n_carriers = carrier_counts.get(alg, 1)

    # Average TL of modulators (higher = less modulation = cleaner)
    # In alg 0, ops 1,2,3 are modulators, op4 is carrier
    # We'll use a simpler heuristic based on alg + TL + AR/DR
    tl_vals = patch['TL']
    ar_vals = [v & 0x1F for v in patch['KS_AR']]
    dr_vals = [v & 0x1F for v in patch['AM_DR']]
    sr_vals = patch['SR']
    sl_rr = patch['SL_RR']
    dt_mul = patch['DT_MUL']

    # Compute average modulator TL (exclude carriers)
    avg_mod_tl = sum(tl_vals) / 4
    max_ar = max(ar_vals)
    max_dr = max(dr_vals)
    avg_sr = sum(sr_vals) / 4

    # Multiplier analysis
    muls = [v & 0x0F for v in dt_mul]
    max_mul = max(muls)

    tags = []

    # Algorithm classification
    if alg == 7:
        tags.append('ADD')  # additive
    elif alg >= 5:
        tags.append('RICH')
    elif alg == 4:
        tags.append('DUAL')
    elif alg == 0:
        tags.append('SERIAL')
    else:
        tags.append(f'ALG{alg}')

    # Timbre classification
    if alg == 7 and max_mul > 1:
        return 'ORGAN_ADD'
    if alg == 7:
        return 'SINE_ADD'

    # Attack/decay behavior
    fast_attack = all(ar >= 0x1C for ar in ar_vals)
    slow_attack = any(ar < 0x0C for ar in ar_vals)
    fast_decay = any(dr >= 0x10 for dr in dr_vals)
    slow_decay = all(dr < 0x08 for dr in dr_vals)

    # High modulator TL = clean
    clean = avg_mod_tl > 0x40
    harsh = avg_mod_tl < 0x20 and fb >= 4

    if harsh and alg <= 1:
        if fast_attack and fast_decay:
            return 'DIST_PLUCK'
        return 'DIST_HEAVY'

    if alg == 0:
        if slow_attack:
            return 'BRASS_SOFT'
        if fast_attack and fast_decay:
            return 'BASS_HEAVY'
        if fast_attack and slow_decay:
            return 'BRASS_HARD'
        return 'WIND'

    if alg == 1:
        if fast_attack and fast_decay:
            return 'PLUCK'
        if slow_attack:
            return 'PAD_WARM'
        return 'STRINGS'

    if alg == 2:
        if fast_attack:
            return 'BELL'
        return 'KEYS'

    if alg == 3:
        if fast_attack and fast_decay:
            return 'CLAV'
        return 'LEAD'

    if alg == 4:
        if slow_attack:
            return 'PAD_SOFT'
        if fast_decay:
            return 'GUITAR'
        return 'STRINGS_DUAL'

    if alg >= 5:
        if fast_attack and fast_decay:
            return 'PERC_FM'
        if slow_attack:
            return 'PAD_RICH'
        return 'LEAD_BRIGHT'

    return 'UNKNOWN'

def main():
    all_patches = []

    print(f"Extracting FM patches from KOF96 ({len(SONG_CMDS)} songs)...")
    print(f"M-ROM: {MROM_PATH}")
    print()

    for cmd in SONG_CMDS:
        print(f"Song cmd 0x{cmd:02X}...", end=' ', flush=True)
        writes = extract_patches_from_song(cmd, ticks=60)
        patches = parse_ym_writes(writes)
        new_count = 0
        for p in patches:
            pt = _patch_to_tuple(p)
            if not any(_patch_to_tuple(e) == pt for e in all_patches):
                all_patches.append(p)
                new_count += 1
        print(f"{len(writes)} writes, {len(patches)} patches ({new_count} new) -> total {len(all_patches)}")

    print(f"\n=== {len(all_patches)} unique FM patches found ===\n")

    for i, patch in enumerate(all_patches):
        name = classify_patch(patch)
        alg = patch['FB_ALG'] & 0x07
        fb = (patch['FB_ALG'] >> 3) & 0x07
        print(f"Patch {i}: {name} (ALG={alg}, FB={fb})")
        for key in REG_NAMES:
            vals = ', '.join(f'0x{v:02X}' for v in patch[key])
            print(f"  {key:8s}: [{vals}]")
        print(f"  FB_ALG  : 0x{patch['FB_ALG']:02X}")
        print(f"  LR_AMS  : 0x{patch['LR_AMS_PMS']:02X}")
        print()

    # Output Python dict format for neosynth_build.py
    print("\n=== Python patch definitions ===\n")
    used_names = {}
    for i, patch in enumerate(all_patches):
        base_name = classify_patch(patch)
        if base_name in used_names:
            used_names[base_name] += 1
            name = f"{base_name}_{used_names[base_name]}"
        else:
            used_names[base_name] = 1
            name = base_name

        print(f"FM_PATCH_{name.upper()} = {{")
        for key in REG_NAMES:
            vals = ', '.join(f'0x{v:02X}' for v in patch[key])
            print(f"    '{key}': [{vals}],")
        print(f"    'FB_ALG': 0x{patch['FB_ALG']:02X},")
        print(f"    'LR_AMS_PMS': 0x{patch['LR_AMS_PMS']:02X},")
        print(f"}}")
        print()

if __name__ == '__main__':
    main()
