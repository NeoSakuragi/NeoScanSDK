#!/usr/bin/env python3
"""
Disassemble key sections of the KOF96 Neo Geo sound driver (M1 ROM).
Uses z80disasm.py to produce annotated output for reverse-engineering
the music bytecode format.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from z80disasm import format_disassembly

ROM_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "examples", "hello_neo", "res", "kof96_m1.bin")

SECTIONS = [
    (0x1C30, 0x1C60, "SECTION 1: Command Dispatch / LUT Setup (0x1C30-0x1C60)",
     """\
; This section handles incoming commands from the 68K.
; It reads the command byte, determines whether it's a music/SFX command,
; and sets up the lookup table pointer for dispatching.
"""),

    (0x1C55, 0x1D10, "SECTION 2: Command Handler Jump Table Entries (0x1C55-0x1D10)",
     """\
; Jump table for command opcodes.  Each 2-byte entry is a little-endian
; address of the handler routine for a specific command range (0xC0-0xFF).
; The dispatcher indexes into this table after subtracting the base command.
"""),

    (0x1D11, 0x1D80, "SECTION 3: Command Handlers C2, C6, CE (0x1D11-0x1D80)",
     """\
; Handlers for individual command opcodes:
;   C2 -- likely tempo / timing related
;   C6 -- likely volume or fade
;   CE -- possibly channel mask or enable/disable
"""),

    (0x1D6D, 0x1E00, "SECTION 4: Command Handlers C0, EA (0x1D6D-0x1E00)",
     """\
; Handlers for:
;   C0 -- stop all sound / silence
;   EA -- possibly fade-out or special effect
"""),

    (0x1E3C, 0x1F06, "SECTION 5: Command Handlers C1, E6, EB, EC, ED, EE (0x1E3C-0x1F06)",
     """\
; Handlers for multiple command opcodes:
;   C1 -- possibly pause/resume
;   E6 -- unknown (debug? test?)
;   EB -- possibly ADPCM-A related
;   EC -- possibly ADPCM-B related
;   ED -- possibly SSG related
;   EE -- possibly FM related
"""),

    (0x1F06, 0x1FC0, "SECTION 6: Event Dispatcher (0x1F06-0x1FC0)",
     """\
; The event dispatcher is called after command lookup.
; It reads the event/sequence data pointer for the active channel,
; decodes the next event byte, and branches to the appropriate
; sub-handler (note-on, rest, instrument change, etc.).
"""),

    (0x1F81, 0x2100, "SECTION 7: Command Handlers Continued (0x1F81-0x2100)",
     """\
; Continuation of command handler routines.
; Includes handlers for the 0xD0-0xDF and 0xE0-0xEF ranges,
; which control playback parameters like volume, panning,
; instrument selection, and loop points.
"""),

    (0x2100, 0x2400, "SECTION 8: More Handlers D0-E0 Range (0x2100-0x2400)",
     """\
; Extended command handlers for the D0-E0 opcode range.
; These typically handle:
;   - FM register writes
;   - SSG envelope settings
;   - ADPCM sample triggers
;   - Loop/repeat constructs in sequence data
"""),

    (0x02BB, 0x0360, "SECTION 9: Channel Tick Handler (0x02BB-0x0360)",
     """\
; Called once per tick (timer interrupt) for each active channel.
; Decrements the duration counter; when it reaches zero, fetches
; the next event from the sequence data stream.
; This is the inner loop of the sequencer.
"""),

    (0x0340, 0x03F0, "SECTION 10: Event Reader + Note Processor (0x0340-0x03F0)",
     """\
; Reads the next byte from the channel's sequence data pointer.
; If the byte is < 0xC0, it's a note/rest with duration.
; If >= 0xC0, it's an inline command (instrument, volume, etc.).
; Notes are converted to FM frequency registers or ADPCM triggers.
"""),

    (0x01E7, 0x027D, "SECTION 11: Key-On Handler (0x01E7-0x027D)",
     """\
; Performs the actual key-on for a note.
; Writes the appropriate YM2610 registers:
;   - FM: frequency (fnum + block), key-on via $28
;   - SSG: tone period, mixer enable
;   - ADPCM-A: start/end address, volume, key-on
; The channel type determines which path is taken.
"""),

    (0x1944, 0x19A0, "SECTION 12: IRQ Handler / Sequencer Tick (0x1944-0x19A0)",
     """\
; Entry point for the Z80 NMI/IRQ (RST $38 jumps here).
; This is the master timer tick:
;   1. Save registers
;   2. Read YM2610 status (timer flags)
;   3. If Timer A fired: advance all active channels by one tick
;   4. If Timer B fired: handle tempo/fade tasks
;   5. Restore registers and RETI
; The Neo Geo sound driver typically uses Timer A for sequencer tempo
; and Timer B for fade/communication timing.
"""),
]


def main():
    with open(ROM_PATH, "rb") as f:
        data = f.read()

    print(f"KOF96 Z80 Sound Driver Disassembly")
    print(f"ROM: kof96_m1.bin ({len(data)} bytes)")
    print(f"Driver ID: \"{data[0x3E:0x66].decode('ascii', errors='replace').strip()}\"")
    print(f"=" * 72)
    print()

    for start, end, title, header in SECTIONS:
        print(f"{'=' * 72}")
        print(f"; {title}")
        print(f"{'=' * 72}")
        print(header)
        print(format_disassembly(data, start, end))
        print()
        print()

    # Also dump the vector table for reference
    print(f"{'=' * 72}")
    print(f"; APPENDIX: Z80 Vector Table (0x0000-0x003F)")
    print(f"{'=' * 72}")
    print("""\
; RST 00h = Reset vector (DI; JP init)
; RST 08h = unused (RET)
; RST 10h = JP $1208 (utility)
; RST 18h = JP $2625 (utility)
; RST 20h = JP $2640 (utility)
; RST 28h = JP $0C08 (utility)
; RST 38h = DI; JP $1944 (NMI/IRQ handler)
""")
    print(format_disassembly(data, 0x0000, 0x0040))
    print()

    # Dump the init routine at $00B0 for context
    print(f"{'=' * 72}")
    print(f"; APPENDIX: Init Routine (0x00B0-0x0140)")
    print(f"{'=' * 72}")
    print("""\
; Called from RST 00h. Sets up stack, clears RAM, initializes YM2610,
; loads default bank, enters main loop.
""")
    print(format_disassembly(data, 0x00B0, 0x0140))
    print()


if __name__ == "__main__":
    main()
