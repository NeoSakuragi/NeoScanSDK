# KOF98 v1.7 Sound Driver Track Map

## Music Tracks (commands 0x20-0x56)

| Cmd  | Track Name       | Notes |
|------|------------------|-------|
| 0x25 | New Challenger   | "Here comes a new challenger" → character select |
| 0x30 | Terry's Theme    | Confirmed working with ADPCM-B |
| 0x31 | (Terry broken?)  | Sounded like Terry without ADPCM-B |
| 0x33 | Ikari            | Confirmed perfect |
| 0x32 | Takuma's Theme   | Confirmed perfect |
| 0x33 | Ikari            | Confirmed perfect |
| 0x34 | Athena           | Confirmed perfect |
| 0x35 | Chizuru          | Confirmed perfect |
| 0x36 | Kim              | Confirmed perfect |
| 0x3A | Dies Irae        | |
| 0x3F | Fairy            | |

## System Commands

| Cmd  | Function         |
|------|------------------|
| 0x02 | Eyecatcher jingle (NEO GEO logo) |
| 0x03 | Stop / soft reset |
| 0x07 | Unlock music (MUST send before any track command) |

## SFX Commands (0xC0-0xFF)

64 ADPCM-A sound effects.

## Protocol

1. Send `0x07` to unlock music
2. Send track command (e.g. `0x30` for Terry)
3. Send `0x03` to stop
