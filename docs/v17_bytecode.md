# v1.7 Sound Driver Bytecode Specification

## Sequence Format

Each channel has an independent byte stream. The bytecode processor at Z80 address 0x1BB5 reads opcodes from the stream and dispatches via a jump table at 0x1C8A.

### Byte Encoding

- `0x00-0x3F`: Opcode (see table below). May consume additional parameter bytes.
- `0xC0-0xFE`: Set duration — bottom 6 bits (0-62) = note length in ticks
- `0xFF`: End of channel sequence

### Duration

Before each note/rest, a duration byte (0xC0-0xFE) sets how long the note plays. If no duration byte precedes an opcode, the previous duration is reused. Duration is stored in channel state at IX+0x01.

### Channel State Block (39 bytes at IX)

Each channel has a state block in Z80 RAM:
- IX+0x00: Channel status (0=inactive, 1-5=various states)
- IX+0x01: Current duration (ticks)
- IX+0x02: Base note/param
- IX+0x04-0x05: Tick countdown (16-bit LE)
- IX+0x06-0x07: Sub-tick countdown (16-bit LE)
- IX+0x08: Flags (bit 4=tie, bit 5=legato)
- IX+0x0A-0x0B: Stream pointer (16-bit LE)

### Channel RAM Addresses

| Channel   | RAM Base | Type     | ID |
|-----------|----------|----------|----|
| FM 1      | 0xFA24   | FM       | 1  |
| FM 2      | 0xFA4B   | FM       | 2  |
| FM 3      | 0xFA72   | FM       | 3  |
| FM 4      | 0xFA99   | FM       | 4  |
| SSG A     | 0xFAC0   | SSG      | 8  |
| SSG B     | 0xFAE7   | SSG      | 9  |
| SSG C     | 0xFB0E   | SSG      | 10 |
| ADPCM-A 1 | 0xFB35   | ADPCM-A  | 11 |
| ADPCM-A 2 | 0xFB5C   | ADPCM-A  | 12 |
| ADPCM-A 3 | 0xFB83   | ADPCM-A  | 13 |
| ADPCM-B   | 0xFBAA   | ADPCM-B  | 14 |

Channel state blocks are 0x27 (39) bytes apart.

## Opcode Table

Jump table at 0x1C8A, 4 bytes per entry (EX DE,HL + JP addr).

| Op   | Handler | Name              | Params | Notes |
|------|---------|-------------------|--------|-------|
| 0x00 | 0x1DCB  | note_on           | 1: note| Play note |
| 0x01 | 0x1D67  | rest              | 0      | Rest (silent tick) |
| 0x02 | 0x1D67  | rest              | 0      | Same as 0x01 |
| 0x03 | 0x2050  | set_instrument    | ?      | Load FM patch / sample |
| 0x04 | 0x1D67  | nop               | 0      | |
| 0x05 | 0x2090  | set_volume        | ?      | |
| 0x06 | 0x1D68  | end_channel       | 0      | Stop this channel |
| 0x07 | 0x20E8  | ?                 | ?      | |
| 0x08 | 0x2100  | ?                 | ?      | |
| 0x09 | 0x211E  | ?                 | ?      | |
| 0x0A | 0x2135  | ?                 | ?      | |
| 0x0B | 0x216B  | ?                 | ?      | |
| 0x0C | 0x2170  | ?                 | ?      | |
| 0x0D | 0x2191  | ?                 | ?      | |
| 0x0E | 0x1D5E  | clear_flags       | 0      | Clear channel flags |
| 0x0F | 0x21D1  | ?                 | ?      | |
| 0x10 | 0x21D7  | ?                 | ?      | |
| 0x11 | 0x21DF  | ?                 | ?      | |
| 0x12 | 0x21E6  | vibrato?          | ?      | Shared handler |
| 0x13 | 0x21E6  | vibrato?          | ?      | Shared handler |
| 0x14 | 0x2244  | portamento?       | ?      | Shared handler |
| 0x15 | 0x2244  | portamento?       | ?      | Shared handler |
| 0x16 | 0x23BD  | ?                 | ?      | |
| 0x17 | 0x23C4  | ?                 | ?      | |
| 0x18 | 0x23C9  | ?                 | ?      | |
| 0x19 | 0x1D67  | nop               | 0      | |
| 0x1A | 0x23D9  | loop_start?       | ?      | |
| 0x1B | 0x23FC  | loop_end?         | ?      | |
| 0x1C | 0x1D67  | nop               | 0      | |
| 0x1D | 0x2412  | ?                 | ?      | |
| 0x1E | 0x2420  | ?                 | ?      | |
| 0x1F | 0x1D67  | nop               | 0      | |
| 0x20 | 0x1D67  | nop               | 0      | |
| 0x21 | 0x21E6  | vibrato?          | ?      | Same as 0x12 |
| 0x22 | 0x2244  | portamento?       | ?      | Same as 0x14 |
| 0x23 | 0x230F  | ?                 | ?      | |
| 0x24 | 0x2318  | ?                 | ?      | |
| 0x25 | 0x231E  | ?                 | ?      | |
| 0x26 | 0x2341  | ?                 | ?      | |
| 0x27 | 0x2346  | ?                 | ?      | |
| 0x28 | 0x2373  | ?                 | ?      | |
| 0x29 | 0x23A6  | ?                 | ?      | |
| 0x2A | 0x1DCB  | note_on           | 1: note| Same as 0x00 |
| 0x2B | 0x1D67  | nop               | 0      | |
| 0x2C | 0x1F57  | ?                 | ?      | |
| 0x2D | 0x1EFE  | ?                 | ?      | |
| 0x2E | 0x1EA4  | ?                 | ?      | |
| 0x2F | 0x1EAC  | ?                 | ?      | |
| 0x30 | 0x1EDD  | ?                 | ?      | |
| 0x31 | 0x1F12  | ?                 | ?      | |
| 0x32 | 0x1F17  | ?                 | ?      | |
| 0x33 | 0x1F1C  | ?                 | ?      | |
| 0x34 | 0x2430  | ?                 | ?      | |

## Timer B ISR Flow (0x194C)

1. Save registers
2. Read YM2610 status (ports 0x04, 0x06)
3. Handle ADPCM-A channel end flags (call 0x0306 per channel)
4. Check Timer B flag → if not fired, skip music
5. Re-arm Timer B (call 0x12EF)
6. For each active channel: call bytecode processor (0x1BB5)
7. After bytecode: call channel output handler (FM=0x164C, SSG=0x1662, ADPCM=0x1688)
8. Process SFX overlay channels
9. Restore registers, RETI

## ROM Layout References

- Engine code: 0x0000-0x2C48
- Bank config table: 0x2708 (32 entries × 4 bytes)
- Song pointer table: 0x329E
- Song-to-bank mapping: 0x33DE
- Command type table: 0x3038 (224 bytes)
- FM patch table: 0x33DE area
- Sequence data: 0x341E+
