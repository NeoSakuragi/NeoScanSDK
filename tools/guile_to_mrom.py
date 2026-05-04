#!/usr/bin/env python3
"""Convert Guile's Theme VGM data into KOF96 v0.1 bytecode and patch the M-ROM."""

import gzip, struct, sys, os, json

# KOF96 v0.1 note encoding: lookup table at 0x2B5E maps note bytes to
# (semitone<<4 | octave). Semitone 0-11, octave 0-7.
# Byte = 0x18 + octave*12 + semitone  (for octave 0-7, semitone 0-11)
# Range: 0x18 (C0) to 0x77 (B7). 0x00 = rest.

SEMI_NAMES = {'C':0,'C#':1,'D':2,'D#':3,'E':4,'F':5,'F#':6,'G':7,'G#':8,'A':9,'A#':10,'B':11}

def note_to_byte(semi, octave):
    if octave < 0: octave = 0
    if octave > 7: octave = 7
    return 0x18 + octave * 12 + semi

def seconds_to_ticks(dur_sec, tick_rate):
    ticks = int(dur_sec * tick_rate + 0.5)
    return max(1, min(255, ticks))

# --- Extract notes from VGM ---
def extract_vgm_notes(vgm_path):
    with gzip.open(vgm_path, 'rb') as f:
        vgm = f.read()

    version = struct.unpack_from('<I', vgm, 0x08)[0]
    data_offset = struct.unpack_from('<I', vgm, 0x34)[0] + 0x34 if version >= 0x150 else 0x40

    pos = data_offset
    wait_total = 0
    events = []

    while pos < len(vgm):
        cmd = vgm[pos]
        if cmd == 0x54:
            events.append((wait_total, vgm[pos+1], vgm[pos+2])); pos += 3
        elif cmd == 0x61:
            wait_total += struct.unpack_from('<H', vgm, pos+1)[0]; pos += 3
        elif cmd == 0x62: wait_total += 735; pos += 1
        elif cmd == 0x63: wait_total += 882; pos += 1
        elif cmd == 0x66: break
        elif cmd == 0x67: pos += 7 + struct.unpack_from('<I', vgm, pos+3)[0]
        elif 0x70 <= cmd <= 0x7F: wait_total += (cmd & 0x0F) + 1; pos += 1
        else: pos += 1

    ym_to_semi = {0:1, 1:2, 2:3, 4:4, 5:5, 6:6, 8:7, 9:8, 10:9, 12:10, 13:11, 14:0}
    ch_state = {i: {'kc': 0} for i in range(8)}
    ch_notes = {i: [] for i in range(8)}
    ch_last_on = {i: None for i in range(8)}

    for time, reg, val in events:
        if 0x28 <= reg <= 0x2F:
            ch_state[reg - 0x28]['kc'] = val
        elif reg == 0x08:
            ch = val & 0x07
            ops = (val >> 3) & 0x0F
            kc = ch_state[ch]['kc']
            octave = (kc >> 4) & 0x07
            nc = kc & 0x0F
            semi = ym_to_semi.get(nc, -1)
            if semi == 0: octave += 1

            if ops > 0:
                if ch_last_on[ch] is not None:
                    prev_t, prev_s, prev_o = ch_last_on[ch]
                    dur = (time - prev_t) / 44100
                    ch_notes[ch].append((prev_t/44100, prev_s, prev_o, dur))
                if semi >= 0:
                    ch_last_on[ch] = (time, semi, octave)
            else:
                if ch_last_on[ch] is not None:
                    prev_t, prev_s, prev_o = ch_last_on[ch]
                    dur = (time - prev_t) / 44100
                    ch_notes[ch].append((prev_t/44100, prev_s, prev_o, dur))
                    ch_last_on[ch] = None

    return ch_notes

# --- Compile note list to v0.1 bytecode ---
def compile_channel(notes, instrument, pan, tick_rate, transpose=0):
    stream = bytearray()

    # Init commands
    stream.append(0xEC)  # INSTRUMENT
    stream.append(instrument & 0xFF)
    stream.append(0xEB)  # PAN
    stream.append(pan & 0xFF)

    if not notes:
        stream.append(0xFF)  # END
        return stream

    # Convert notes to bytecode
    start_time = notes[0][0]

    for i, (time, semi, octave, dur) in enumerate(notes):
        # Insert rest if there's a gap
        if i == 0:
            gap = 0
        else:
            prev_end = notes[i-1][0] + notes[i-1][3]
            gap = time - prev_end

        if gap > 0.02:
            rest_ticks = seconds_to_ticks(gap, tick_rate)
            stream.append(0x00)  # REST note
            stream.append(rest_ticks)

        # Note
        adj_oct = octave + transpose
        nb = note_to_byte(semi, adj_oct)
        dur_ticks = seconds_to_ticks(dur, tick_rate)
        stream.append(nb)
        stream.append(dur_ticks)

    # Loop back to start of notes (after init commands)
    loop_addr_placeholder = len(stream)
    stream.append(0xC9)  # JUMP
    stream.append(0x00)  # placeholder low
    stream.append(0x00)  # placeholder high

    return stream, 4  # return stream and offset where notes start (after init)

# --- Build song ---
def build_song(channels, tempo=0x55, speed=0x05):
    """Build a complete song from channel streams.
    channels: list of (channel_index, stream_bytes, loop_offset) tuples
    """
    header = bytearray(14)

    # Enable flags for active channels
    for ch_idx, _, _ in channels:
        if ch_idx < 11:
            header[ch_idx] = 0x01

    header[11] = tempo
    header[12] = speed
    header[13] = 0x20  # config

    # Calculate pointer table
    num_active = len(channels)
    ptr_table_size = num_active * 2
    data_start = 14 + ptr_table_size  # relative to song start

    # Build pointer table and channel data
    ptr_table = bytearray()
    all_data = bytearray()

    for ch_idx, stream, loop_off in channels:
        # Pointer is absolute Z80 address — will be fixed up by patcher
        ptr_table.append(0x00)  # placeholder
        ptr_table.append(0x00)
        all_data.extend(stream)

    return header, ptr_table, all_data, channels

# --- Main ---
def main():
    vgm_path = '/home/bruno/NeoVGM/sf2_vgm/10 U.S.A. (Guile) I.vgz'
    mrom_path = '/home/bruno/CLProjects/NeoScanSDK/examples/hello_neo/res/kof96_m1.bin'
    output_path = '/home/bruno/CLProjects/NeoScanSDK/examples/hello_neo/res/kof96_m1_guile.bin'

    print("Extracting notes from VGM...")
    ch_notes = extract_vgm_notes(vgm_path)

    # Filter out setup notes (C#0 at time ~0)
    for ch in ch_notes:
        ch_notes[ch] = [(t, s, o, d) for t, s, o, d in ch_notes[ch] if not (o == 0 and s == 1)]

    # Tick rate: ~60 ticks/sec (one per vblank at 59.19 Hz)
    TICK_RATE = 60

    # YM2151 ch -> YM2610 mapping + KOF96 instrument patches
    # Ch0 = lead melody -> FM1, Ch5 = bass -> FM2,
    # Ch2-4 = chords -> FM3, Ch1 = arpeggio -> FM4

    channels = []

    # FM1: Lead melody (ch0) — use KOF96 instrument ~0x15 (a lead-ish patch)
    melody = ch_notes.get(0, [])
    if melody:
        # Skip the intro silence, start from first real note
        melody = [(t - melody[0][0], s, o, d) for t, s, o, d in melody]
        stream, loop_off = compile_channel(melody, instrument=0x15, pan=0x03, tick_rate=TICK_RATE)
        channels.append((0, stream, loop_off))
        print(f"  FM1 (melody): {len(melody)} notes, {len(stream)} bytes")

    # FM2: Bass (ch5)
    bass = ch_notes.get(5, [])
    if bass:
        # Sync to melody start
        melody_start = ch_notes[0][0][0] if ch_notes.get(0) else 0
        bass = [(t - melody_start, s, o, d) for t, s, o, d in bass if t >= melody_start - 2]
        if bass and bass[0][0] < 0:
            bass = [(0, s, o, d) for t, s, o, d in bass]
        stream, loop_off = compile_channel(bass, instrument=0x20, pan=0x03, tick_rate=TICK_RATE)
        channels.append((1, stream, loop_off))
        print(f"  FM2 (bass): {len(bass)} notes, {len(stream)} bytes")

    # FM3: Chord stabs (ch2 — top note of chord)
    chords = ch_notes.get(2, [])
    if chords:
        melody_start = ch_notes[0][0][0] if ch_notes.get(0) else 0
        chords = [(t - melody_start, s, o, d) for t, s, o, d in chords if t >= melody_start - 2]
        if chords and chords[0][0] < 0:
            chords = [(0, s, o, d) if t < 0 else (t, s, o, d) for t, s, o, d in chords]
        stream, loop_off = compile_channel(chords, instrument=0x30, pan=0x03, tick_rate=TICK_RATE)
        channels.append((2, stream, loop_off))
        print(f"  FM3 (chords): {len(chords)} notes, {len(stream)} bytes")

    # FM4: Arpeggios (ch1)
    arps = ch_notes.get(1, [])
    if arps:
        melody_start = ch_notes[0][0][0] if ch_notes.get(0) else 0
        arps = [(t - melody_start, s, o, d) for t, s, o, d in arps if t >= melody_start - 2]
        if arps and arps[0][0] < 0:
            arps = [(max(0, t), s, o, d) for t, s, o, d in arps]
        stream, loop_off = compile_channel(arps, instrument=0x10, pan=0x03, tick_rate=TICK_RATE)
        channels.append((3, stream, loop_off))
        print(f"  FM4 (arps): {len(arps)} notes, {len(stream)} bytes")

    # Build the song
    tempo = 0x55  # same as KOF96 song 1
    header, ptr_table, all_data, ch_list = build_song(channels, tempo=tempo)

    total_song = header + ptr_table + all_data
    print(f"\nTotal song size: {len(total_song)} bytes")

    # --- Patch into M-ROM ---
    with open(mrom_path, 'rb') as f:
        mrom = bytearray(f.read())

    # Place song data at 0x7000 (in fixed bank, ~4KB before end of 32KB)
    SONG_ADDR = 0x7000  # Z80 address in fixed bank
    ROM_OFFSET = SONG_ADDR  # fixed bank = direct mapping

    if ROM_OFFSET + len(total_song) > 0x8000:
        print(f"ERROR: Song too large! {len(total_song)} bytes, max {0x8000 - ROM_OFFSET}")
        sys.exit(1)

    # Fix up channel pointers
    data_base = SONG_ADDR + 14 + len(ptr_table)
    offset = 0
    for i, (ch_idx, stream, loop_off) in enumerate(ch_list):
        ch_addr = data_base + offset
        # Write pointer in the pointer table
        ptr_table[i*2] = ch_addr & 0xFF
        ptr_table[i*2 + 1] = (ch_addr >> 8) & 0xFF

        # Fix up the JUMP command at end of stream (C9 addr_lo addr_hi)
        jump_target = ch_addr + loop_off  # loop back to after init commands
        jump_pos = len(stream) - 2  # last 2 bytes are the address
        stream[jump_pos] = jump_target & 0xFF
        stream[jump_pos + 1] = (jump_target >> 8) & 0xFF

        offset += len(stream)

    # Rebuild total song with fixed pointers
    total_song = header + ptr_table + bytearray().join(s for _, s, _ in ch_list)

    # Write into M-ROM
    mrom[ROM_OFFSET:ROM_OFFSET + len(total_song)] = total_song

    # Update song pointer table at 0x30D0 — use slot 15 (cmd 0x2F)
    SLOT = 15
    struct.pack_into('<H', mrom, 0x30D0 + SLOT * 2, SONG_ADDR)

    # Update bank mapping at 0x3210 — bank 0 (fixed bank)
    mrom[0x3210 + SLOT] = 0x00

    # Write output
    with open(output_path, 'wb') as f:
        f.write(mrom)

    print(f"\nPatched M-ROM: {output_path}")
    print(f"Song at Z80 addr 0x{SONG_ADDR:04X}, slot {SLOT} (cmd 0x{0x20+SLOT:02X})")
    print(f"Select track 0x{0x20+SLOT:02X} in hello_neo to play")

if __name__ == '__main__':
    main()
