# v1.7 Bytecode — Complete Opcode Reference

Reverse-engineered from soccerfury.m1 (KOF98 v1.7 sound driver).

## Encoding

- `0xC0-0xFE`: Set duration (bottom 6 bits = 0-62 ticks)
- `0x00-0x34`: Opcode (see below)
- `0xFF`: End of channel

## Opcodes

### Notes & Rests
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x00 | 2 | note_on | Play note. P1=note number, P2=velocity |
| 0x01 | 0 | rest | Silent for current duration |
| 0x02 | 0 | rest | Alias for 0x01 |
| 0x2A | 2 | note_on | Alias for 0x00 |

### Instrument & Volume
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x03 | 1 | set_instrument | P1=instrument/patch ID |
| 0x05 | 2 | set_volume | P1,P2=volume + modifier (14-bit value) |
| 0x0F | 1 | set_pan | P1=panning value (stored at IX+0x09) |
| 0x2C | 1 | volume_slide | P1=slide target (recalculates volume) |

### Pitch Control
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x23 | 2 | set_detune | P1,P2=global detune (16-bit, stored at 0xFDA0) |
| 0x24 | 1 | set_vol_offset | P1=volume offset (stored at IX+0x10) |
| 0x25 | 1 | set_fine_tune | P1=pitch fine tune (base differs per channel type) |
| 0x27 | 1 | set_pitch_adj | P1=pitch adjust (FM: -0x18 base, ADPCM-B: direct) |
| 0x2E | 1 | transpose | P1=semitone offset (stored at IX+0x0F) |

### Effects
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x07 | 4 | effect_setup_1 | Set up effect slot 1 (at IX+0x12): enable, speed, target, step |
| 0x08 | 3 | effect_tick_1 | Effect slot 1 envelope/counter control |
| 0x09 | 4 | effect_setup_2 | Set up effect slot 2 (at IX+0x1E): similar to 0x07 |
| 0x0A | 2 | effect_tick_2 | Effect slot 2 counter control |
| 0x11 | 1 | set_lfo | P1=LFO rate (writes to YM2610 register 0x22) |
| 0x12 | 0 | vibrato_on | Enable vibrato (effect slot in IY area) |
| 0x13 | 0 | vibrato_on | Alias for 0x12 |
| 0x14 | 0 | portamento_on | Enable portamento |
| 0x15 | 0 | portamento_on | Alias for 0x14 |
| 0x21 | 0 | vibrato_on | Alias for 0x12 |
| 0x22 | 0 | portamento_on | Alias for 0x14 |
| 0x28 | 0 | set_pan_ams | Set FM panning + AMS/PMS (YM2610 reg 0xB4) |

### Articulation
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x0E | 0 | clear_flags | Clear channel effect flags |
| 0x26 | 0 | key_off | Clear sustain flag (RES 0 of IX+0x08) |
| 0x31 | 0 | tie_on | Tie notes (no key-off between notes) |
| 0x32 | 0 | legato_on | Legato mode on |
| 0x33 | 0 | legato_off | Legato mode off |

### Flow Control
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x06 | 0 | end_channel | Stop this channel |
| 0x0B | 1 | goto | P1,P2=16-bit address (redirect stream, 2 bytes read as addr) |
| 0x0C | 1 | call_sub | P1=index into subroutine table, saves return on stack at 0xFDCB |
| 0x16 | 0 | get_loop_addr | Load loop address from IX+0x0C/0x0D |
| 0x1A | 1 | loop_start | P1=loop count (combined with flags at 0xFD09) |
| 0x1B | 3 | loop_end | P1=counter reg, P2,P3=loop-back address |
| 0x34 | 0 | play_subsong | Trigger nested song (calls song start routine 0x132A) |

### Channel-Specific
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x0D | 2 | ssg_mode | P1=SSG/noise mode, P2=envelope. Uses table at 0x2E0E |
| 0x29 | 2 | adpcmb_rate | P1,P2=ADPCM-B delta-N rate (pitch). ADPCM-B channel only |
| 0x2D | 1 | bank_switch | P1=bank config. Switches Z80 ROM banks for sequence data |
| 0x2F | 6 | arpeggio_setup | P1=slot, P2=low note, P3=high note + range/mask calc |
| 0x30 | 3 | arpeggio_play | P1=slot, triggers note from arpeggio range |

### Tempo
| Op | Params | Name | Description |
|----|--------|------|-------------|
| 0x10 | 1 | set_tempo | P1=Timer B rate value (calls tempo routine 0x2656) |

### NOPs (do nothing)
| Op | Handler |
|----|---------|
| 0x04, 0x19, 0x1C, 0x1F, 0x20, 0x2B | 0x1D67 (RET) |

### Unresolved
| Op | Params | Handler | Notes |
|----|--------|---------|-------|
| 0x17 | 0 | 0x23C4 | Clears 0xFA1D — resets some global state |
| 0x18 | 0 | 0x23C9 | Clears 6 entries at 0xF9EF (ADPCM-A channel state) |
| 0x1D | 1 | 0x2412 | Flag manipulation based on param bits |
| 0x1E | 1 | 0x2420 | Context-saving macro call |

## Channel State Block (IX+offset)

| Offset | Size | Name | Description |
|--------|------|------|-------------|
| 0x00 | 1 | status | 0=off, 1-5=various play states |
| 0x01 | 1 | duration | Current note length in ticks |
| 0x02 | 1 | note | Current note number |
| 0x03 | 1 | velocity | Note velocity/volume |
| 0x04-05 | 2 | tick_count | Tick countdown (16-bit) |
| 0x06-07 | 2 | sub_tick | Sub-tick countdown |
| 0x08 | 1 | flags | Bit 0=sustain, 4=tie, 5=legato |
| 0x09 | 1 | pan | Panning value |
| 0x0A-0B | 2 | stream_ptr | Current position in sequence data |
| 0x0C-0D | 2 | loop_addr | Loop return address |
| 0x0F | 1 | transpose | Semitone offset |
| 0x10 | 1 | vol_offset | Volume offset/slide target |
| 0x11 | 1 | fine_tune | Pitch fine-tune |
| 0x12-1D | 12 | effect_1 | Effect slot 1 state (counters, pointers) |
| 0x1E-26 | 9 | effect_2 | Effect slot 2 state |
