#!/usr/bin/env python3
"""Build a NeoSynth Z80 M-ROM with full YM2610 sound driver.

Features:
  - ADPCM-A sample trigger on channels 0-5  (cmd $C0-$FF)
  - FM note playback on channels 1-4        (cmd $10-$1F)
  - SSG note playback on channels 1-3       (cmd $20-$2F)
  - Panning control                         (cmd $30-$3F)
  - Tick-based music sequencer              (cmd $50-$5F)
  - Stop/silence all                        (cmd $03)

Command protocol (68K -> Z80 via NMI):
  $01         - Init/reset
  $03         - Stop all (including sequencer)
  $08         - Set param (next NMI byte = param value, via SND_play2)
  $10+ch      - FM key-on ch (0-3), note from param byte (MIDI note)
  $14+ch      - FM key-off ch (0-3)
  $18+ch      - FM set patch ch (0-3), patch from param byte
  $20+ch      - SSG key-on ch (0-2), note from param byte
  $24+ch      - SSG key-off ch (0-2)
  $28+ch      - SSG set patch ch (0-2), preset from param byte (0-4)
  $30+ch      - FM panning ch (0-3), param: 0=L, 1=C, 2=R
  $34+ch      - ADPCM-A panning ch (0-5), param: 0=L, 1=C, 2=R
  $50+N       - Play song N (tick-based sequencer, Timer A driven)
  $C0+smp     - ADPCM-A trigger sample (on current ADPCM-A channel)

Music engine:
  Timer A IRQ at ~55Hz, software counter divides to sequencer tick rate.
  Song data: 8 bytes/row (FM0-3, SSG0-2, ADPCM-A) in M-ROM.
  Row bytes: $00=sustain, $01=key-off, $02-$7F=note-on, $80-$BF=set-patch.
  $FF = end-of-song (loops to start).
  2 built-in songs: C major scale (song 0), chord progression (song 1).
"""
import os, struct, sys, argparse

ADPCM_SAMPLES = [
    (0x0000, 0x0007),  # 0: 1KB
    (0x0000, 0x0073),  # 1: 28KB
    (0x0008, 0x000D),  # 2: 1KB
    (0x0008, 0x000E),  # 3: 1KB
    (0x000F, 0x005A),  # 4: 18KB
    (0x005B, 0x00AA),  # 5: 19KB
    (0x0074, 0x00C9),  # 6: 21KB
    (0x00AB, 0x00F2),  # 7: 17KB
    (0x00F3, 0x0143),  # 8: 20KB
    (0x0144, 0x019E),  # 9: 22KB
    (0x019F, 0x01FF),  # 10: 24KB
    (0x0200, 0x0237),  # 11: 13KB
    (0x0200, 0x02C0),  # 12: 48KB
    (0x0207, 0x02C0),  # 13: 46KB
    (0x0238, 0x026D),  # 14: 13KB
    (0x026E, 0x02A6),  # 15: 14KB
    (0x02A7, 0x02E5),  # 16: 15KB
    (0x02C6, 0x02CE),  # 17: 2KB
    (0x02E6, 0x02F0),  # 18: 2KB
    (0x02F1, 0x02F8),  # 19: 1KB
    (0x02F9, 0x032D),  # 20: 13KB
    (0x0336, 0x0375),  # 21: 15KB
    (0x0376, 0x03B9),  # 22: 16KB
    (0x03BA, 0x03FF),  # 23: 17KB
    (0x0400, 0x0423),  # 24: 8KB
    (0x0424, 0x0451),  # 25: 11KB
    (0x0452, 0x0484),  # 26: 12KB
    (0x0485, 0x04A6),  # 27: 8KB
    (0x04A7, 0x04D5),  # 28: 11KB
    (0x04D6, 0x04F7),  # 29: 8KB
    (0x04F8, 0x0521),  # 30: 10KB
    (0x0522, 0x052D),  # 31: 2KB
    (0x052E, 0x0559),  # 32: 10KB
    (0x055A, 0x057C),  # 33: 8KB
    (0x057D, 0x05A5),  # 34: 10KB
    (0x05A6, 0x05CC),  # 35: 9KB
    (0x05CD, 0x05FF),  # 36: 12KB
    (0x0600, 0x061B),  # 37: 6KB
    (0x061C, 0x063C),  # 38: 8KB
    (0x063D, 0x0659),  # 39: 7KB
    (0x065A, 0x0679),  # 40: 7KB
    (0x067A, 0x0692),  # 41: 6KB
    (0x0693, 0x06A7),  # 42: 5KB
    (0x06A8, 0x06C2),  # 43: 6KB
    (0x06C3, 0x06E3),  # 44: 8KB
    (0x06E4, 0x06FE),  # 45: 6KB
    (0x06FF, 0x0719),  # 46: 6KB
    (0x071A, 0x0734),  # 47: 6KB
    (0x0735, 0x0751),  # 48: 7KB
    (0x0752, 0x076D),  # 49: 6KB
    (0x076E, 0x0789),  # 50: 6KB
    (0x078A, 0x07A9),  # 51: 7KB
    (0x07AA, 0x07C8),  # 52: 7KB
    (0x07C9, 0x07E3),  # 53: 6KB
    (0x07E4, 0x07FF),  # 54: 6KB
    (0x0800, 0x0808),  # 55: 2KB
    (0x0809, 0x081F),  # 56: 5KB
    (0x0820, 0x082C),  # 57: 3KB
    (0x082D, 0x0836),  # 58: 2KB
    (0x0837, 0x084A),  # 59: 4KB
    (0x0845, 0x0859),  # 60: 5KB
    (0x084B, 0x085F),  # 61: 5KB
    (0x0860, 0x086F),  # 62: 3KB
    (0x0870, 0x0883),  # 63: 4KB
    (0x0884, 0x0895),  # 64: 4KB
    (0x0896, 0x08A2),  # 65: 3KB
    (0x08A3, 0x08B7),  # 66: 5KB
    (0x08B8, 0x08C8),  # 67: 4KB
    (0x08C9, 0x08DE),  # 68: 5KB
    (0x08DF, 0x08EE),  # 69: 3KB
    (0x08EF, 0x0902),  # 70: 4KB
    (0x0903, 0x091A),  # 71: 5KB
    (0x091B, 0x0933),  # 72: 6KB
    (0x0934, 0x093C),  # 73: 2KB
    (0x0937, 0x094B),  # 74: 5KB
    (0x093D, 0x0954),  # 75: 5KB
    (0x0955, 0x0965),  # 76: 4KB
    (0x0966, 0x096E),  # 77: 2KB
    (0x09A7, 0x09B6),  # 78: 3KB
    (0x09B7, 0x09F1),  # 79: 14KB
    (0x09F2, 0x09FF),  # 80: 3KB
    (0x0A00, 0x0A29),  # 81: 10KB
    (0x0A2A, 0x0A33),  # 82: 2KB
    (0x0A58, 0x0A6F),  # 83: 5KB
    (0x0A70, 0x0A8B),  # 84: 6KB
    (0x0A8C, 0x0A95),  # 85: 2KB
    (0x0A96, 0x0AB8),  # 86: 8KB
    (0x0AB9, 0x0AC3),  # 87: 2KB
    (0x0AC4, 0x0AEB),  # 88: 9KB
    (0x0AEC, 0x0B0B),  # 89: 7KB
    (0x0B0C, 0x0B20),  # 90: 5KB
    (0x0B21, 0x0B49),  # 91: 10KB
    (0x0B4A, 0x0B5F),  # 92: 5KB
    (0x0B60, 0x0B6C),  # 93: 3KB
    (0x0B6D, 0x0B7C),  # 94: 3KB
    (0x0BA6, 0x0BB3),  # 95: 3KB
    (0x0BB4, 0x0BCF),  # 96: 6KB
    (0x0BD0, 0x0BDB),  # 97: 2KB
    (0x0BDC, 0x0BED),  # 98: 4KB
    (0x0BEE, 0x0BFF),  # 99: 4KB
    (0x0C00, 0x0C5A),  # 100: 22KB
    (0x0C64, 0x0C86),  # 101: 8KB
    (0x0C7E, 0x0CD8),  # 102: 22KB
    (0x0CD9, 0x0CEC),  # 103: 4KB
    (0x0CED, 0x0D03),  # 104: 5KB
    (0x0D7D, 0x0DD9),  # 105: 23KB
    (0x0D98, 0x0DD9),  # 106: 16KB
    (0x0DDA, 0x0DFF),  # 107: 9KB
    (0x0E00, 0x0E08),  # 108: 2KB
    (0x0E09, 0x0E2B),  # 109: 8KB
    (0x0E2C, 0x0E47),  # 110: 6KB
    (0x0E48, 0x0E5C),  # 111: 5KB
    (0x0E5D, 0x0E78),  # 112: 6KB
    (0x0E79, 0x0EAB),  # 113: 12KB
    (0x0EAC, 0x0ECE),  # 114: 8KB
    (0x0ECF, 0x0F10),  # 115: 16KB
    (0x0F11, 0x0F38),  # 116: 9KB
    (0x0FC4, 0x0FFD),  # 117: 14KB
    (0x1000, 0x1025),  # 118: 9KB
    (0x1026, 0x108F),  # 119: 26KB
    (0x1090, 0x10B2),  # 120: 8KB
    (0x10B3, 0x10D7),  # 121: 9KB
    (0x10D8, 0x10FF),  # 122: 9KB
    (0x1100, 0x1114),  # 123: 5KB
    (0x1115, 0x115C),  # 124: 17KB
    (0x115D, 0x1179),  # 125: 7KB
    (0x117A, 0x1196),  # 126: 7KB
    (0x1197, 0x11B3),  # 127: 7KB
    (0x11B4, 0x11D0),  # 128: 7KB
    (0x11D1, 0x11ED),  # 129: 7KB
    (0x1400, 0x1434),  # 130: 13KB
    (0x143A, 0x1474),  # 131: 14KB
    (0x1475, 0x14B8),  # 132: 16KB
    (0x14B9, 0x14F3),  # 133: 14KB
    (0x14F4, 0x1543),  # 134: 19KB
    (0x1544, 0x157D),  # 135: 14KB
    (0x157E, 0x15BE),  # 136: 16KB
    (0x15BF, 0x15FF),  # 137: 16KB
    (0x1600, 0x1637),  # 138: 13KB
    (0x1638, 0x163E),  # 139: 1KB
    (0x163F, 0x166E),  # 140: 11KB
    (0x166F, 0x1699),  # 141: 10KB
    (0x169A, 0x16D2),  # 142: 14KB
    (0x16D3, 0x1702),  # 143: 11KB
    (0x1703, 0x1733),  # 144: 12KB
    (0x1734, 0x176B),  # 145: 13KB
    (0x176C, 0x179B),  # 146: 11KB
    (0x179C, 0x17D0),  # 147: 13KB
    (0x17D1, 0x17FF),  # 148: 11KB
    (0x1800, 0x1824),  # 149: 9KB
    (0x1825, 0x1849),  # 150: 9KB
    (0x184A, 0x186B),  # 151: 8KB
    (0x186C, 0x188F),  # 152: 8KB
    (0x1890, 0x18B8),  # 153: 10KB
    (0x18B9, 0x18E4),  # 154: 10KB
    (0x18E5, 0x1910),  # 155: 10KB
    (0x1911, 0x1939),  # 156: 10KB
    (0x193A, 0x1960),  # 157: 9KB
    (0x1961, 0x1984),  # 158: 8KB
    (0x1985, 0x19AB),  # 159: 9KB
    (0x19AC, 0x19B2),  # 160: 1KB
    (0x19B3, 0x19DB),  # 161: 10KB
    (0x19DC, 0x19FF),  # 162: 8KB
    (0x1A00, 0x1A0B),  # 163: 2KB
    (0x1A0C, 0x1A2B),  # 164: 7KB
    (0x1A2C, 0x1A4A),  # 165: 7KB
    (0x1A4B, 0x1A68),  # 166: 7KB
    (0x1A69, 0x1A87),  # 167: 7KB
    (0x1A88, 0x1AA5),  # 168: 7KB
    (0x1AA6, 0x1AC6),  # 169: 8KB
    (0x1AC7, 0x1AE3),  # 170: 7KB
    (0x1AE4, 0x1B01),  # 171: 7KB
    (0x1B02, 0x1B1F),  # 172: 7KB
    (0x1B20, 0x1B3E),  # 173: 7KB
    (0x1B3F, 0x1B5C),  # 174: 7KB
    (0x1B5D, 0x1B7D),  # 175: 8KB
    (0x1B7E, 0x1B9C),  # 176: 7KB
    (0x1B9D, 0x1BBD),  # 177: 8KB
    (0x1BBE, 0x1BDC),  # 178: 7KB
    (0x1BDD, 0x1BFF),  # 179: 8KB
    (0x1C00, 0x1C1B),  # 180: 6KB
    (0x1C03, 0x1CC0),  # 181: 47KB
    (0x1C1C, 0x1C37),  # 182: 6KB
    (0x1C38, 0x1C52),  # 183: 6KB
    (0x1C53, 0x1C6C),  # 184: 6KB
    (0x1C6D, 0x1C78),  # 185: 2KB
    (0x1C79, 0x1C94),  # 186: 6KB
    (0x1C95, 0x1CAC),  # 187: 5KB
    (0x1CAD, 0x1CC9),  # 188: 7KB
    (0x1CCA, 0x1CE1),  # 189: 5KB
    (0x1CE2, 0x1CF9),  # 190: 5KB
    (0x1CFA, 0x1D12),  # 191: 6KB
    (0x1D13, 0x1D2C),  # 192: 6KB
    (0x1D2D, 0x1D46),  # 193: 6KB
    (0x1D47, 0x1D5E),  # 194: 5KB
    (0x1D5F, 0x1D7B),  # 195: 7KB
    (0x1D7C, 0x1D95),  # 196: 6KB
    (0x1D96, 0x1DB1),  # 197: 6KB
    (0x1DB2, 0x1DCA),  # 198: 6KB
    (0x1DCB, 0x1DE2),  # 199: 5KB
    (0x1DE3, 0x1DFF),  # 200: 7KB
    (0x1E00, 0x1E16),  # 201: 5KB
    (0x1E17, 0x1E2A),  # 202: 4KB
    (0x1E2B, 0x1E3F),  # 203: 5KB
    (0x1E40, 0x1E53),  # 204: 4KB
    (0x1E54, 0x1E67),  # 205: 4KB
    (0x1E68, 0x1E7C),  # 206: 5KB
    (0x1E7D, 0x1E8D),  # 207: 4KB
    (0x1E8E, 0x1EA1),  # 208: 4KB
    (0x1EA2, 0x1EB5),  # 209: 4KB
    (0x1EB6, 0x1ECB),  # 210: 5KB
    (0x1ECC, 0x1EE2),  # 211: 5KB
    (0x1EE3, 0x1EF9),  # 212: 5KB
    (0x1EFA, 0x1F0E),  # 213: 5KB
    (0x1F0F, 0x1F23),  # 214: 5KB
    (0x1F24, 0x1F38),  # 215: 5KB
    (0x1F39, 0x1F4E),  # 216: 5KB
    (0x1F4F, 0x1F63),  # 217: 5KB
    (0x1F64, 0x1F7A),  # 218: 5KB
    (0x1F7B, 0x1F91),  # 219: 5KB
    (0x1F92, 0x1FA6),  # 220: 5KB
    (0x1FA7, 0x1FBD),  # 221: 5KB
    (0x1FBE, 0x1FD4),  # 222: 5KB
    (0x1FD5, 0x1FEA),  # 223: 5KB
    (0x1FEB, 0x1FFF),  # 224: 5KB
    (0x2000, 0x200F),  # 225: 3KB
    (0x2010, 0x201F),  # 226: 3KB
    (0x2020, 0x202E),  # 227: 3KB
    (0x202F, 0x203C),  # 228: 3KB
    (0x203D, 0x204C),  # 229: 3KB
    (0x204D, 0x205B),  # 230: 3KB
    (0x205C, 0x206D),  # 231: 4KB
    (0x206E, 0x207B),  # 232: 3KB
    (0x207C, 0x208A),  # 233: 3KB
    (0x208B, 0x2099),  # 234: 3KB
    (0x209A, 0x20A8),  # 235: 3KB
    (0x20A9, 0x20BB),  # 236: 4KB
    (0x20BC, 0x20CB),  # 237: 3KB
    (0x20CC, 0x20DB),  # 238: 3KB
    (0x20DC, 0x20EE),  # 239: 4KB
    (0x20EF, 0x20FA),  # 240: 2KB
    (0x20FB, 0x210C),  # 241: 4KB
    (0x210D, 0x211B),  # 242: 3KB
    (0x211C, 0x212E),  # 243: 4KB
    (0x212F, 0x213D),  # 244: 3KB
    (0x213E, 0x214D),  # 245: 3KB
    (0x214E, 0x215C),  # 246: 3KB
    (0x215D, 0x216D),  # 247: 4KB
    (0x216E, 0x217C),  # 248: 3KB
    (0x217D, 0x218B),  # 249: 3KB
    (0x218C, 0x219B),  # 250: 3KB
    (0x219C, 0x21A3),  # 251: 1KB
    (0x219E, 0x21BC),  # 252: 7KB
    (0x21A4, 0x21B5),  # 253: 4KB
    (0x21B6, 0x21C9),  # 254: 4KB
    (0x21BD, 0x21DA),  # 255: 7KB
    (0x21CA, 0x21D9),  # 256: 3KB
    (0x21DA, 0x21ED),  # 257: 4KB
    (0x21DB, 0x21FF),  # 258: 9KB
    (0x21EE, 0x21FF),  # 259: 4KB
    (0x2200, 0x2208),  # 260: 2KB
    (0x2209, 0x2213),  # 261: 2KB
    (0x220E, 0x2221),  # 262: 4KB
    (0x2214, 0x221C),  # 263: 2KB
    (0x221D, 0x222A),  # 264: 3KB
    (0x222B, 0x2234),  # 265: 2KB
    (0x2235, 0x2241),  # 266: 3KB
    (0x223C, 0x224A),  # 267: 3KB
    (0x2242, 0x224E),  # 268: 3KB
    (0x224F, 0x2257),  # 269: 2KB
    (0x2258, 0x2263),  # 270: 2KB
    (0x2264, 0x226D),  # 271: 2KB
    (0x226E, 0x2279),  # 272: 2KB
    (0x226F, 0x227C),  # 273: 3KB
    (0x227A, 0x2282),  # 274: 2KB
    (0x227D, 0x228F),  # 275: 4KB
    (0x2283, 0x228E),  # 276: 2KB
    (0x228F, 0x2297),  # 277: 2KB
    (0x2298, 0x22A4),  # 278: 3KB
    (0x22A5, 0x22B2),  # 279: 3KB
    (0x22B3, 0x22BD),  # 280: 2KB
    (0x22BE, 0x22C6),  # 281: 2KB
    (0x22C7, 0x22D3),  # 282: 3KB
    (0x22D4, 0x22DC),  # 283: 2KB
    (0x22DD, 0x22E7),  # 284: 2KB
    (0x22E8, 0x22F3),  # 285: 2KB
    (0x22F4, 0x22FE),  # 286: 2KB
    (0x22FF, 0x230A),  # 287: 2KB
    (0x230B, 0x2317),  # 288: 3KB
    (0x2317, 0x2334),  # 289: 7KB
    (0x2318, 0x2322),  # 290: 2KB
    (0x2323, 0x232F),  # 291: 3KB
    (0x2330, 0x233A),  # 292: 2KB
    (0x233B, 0x2345),  # 293: 2KB
    (0x2346, 0x234F),  # 294: 2KB
    (0x2350, 0x2359),  # 295: 2KB
    (0x235A, 0x2364),  # 296: 2KB
    (0x2365, 0x236D),  # 297: 2KB
    (0x236E, 0x2379),  # 298: 2KB
    (0x237A, 0x2383),  # 299: 2KB
    (0x2384, 0x238F),  # 300: 2KB
    (0x2390, 0x2398),  # 301: 2KB
    (0x2399, 0x23FF),  # 302: 25KB
    (0x2400, 0x2443),  # 303: 16KB
    (0x2444, 0x2488),  # 304: 17KB
    (0x2489, 0x24A9),  # 305: 8KB
    (0x24AA, 0x24C2),  # 306: 6KB
    (0x24C3, 0x24E1),  # 307: 7KB
    (0x24E2, 0x24FD),  # 308: 6KB
    (0x24FE, 0x2520),  # 309: 8KB
    (0x2521, 0x2540),  # 310: 7KB
    (0x2541, 0x256D),  # 311: 11KB
    (0x256E, 0x2598),  # 312: 10KB
    (0x2599, 0x25C9),  # 313: 12KB
    (0x25CA, 0x25F2),  # 314: 10KB
    (0x25F3, 0x25FF),  # 315: 3KB
    (0x2600, 0x2608),  # 316: 2KB
    (0x2609, 0x2612),  # 317: 2KB
    (0x2613, 0x261B),  # 318: 2KB
    (0x261C, 0x2624),  # 319: 2KB
    (0x2625, 0x2632),  # 320: 3KB
    (0x2633, 0x2647),  # 321: 5KB
    (0x2648, 0x265F),  # 322: 5KB
    (0x2660, 0x2676),  # 323: 5KB
    (0x2677, 0x268E),  # 324: 5KB
    (0x268F, 0x26A9),  # 325: 6KB
    (0x26AA, 0x26C2),  # 326: 6KB
    (0x26C3, 0x26D7),  # 327: 5KB
    (0x26D8, 0x26EB),  # 328: 4KB
    (0x26EC, 0x2705),  # 329: 6KB
    (0x2706, 0x2715),  # 330: 3KB
    (0x2716, 0x2728),  # 331: 4KB
    (0x2729, 0x2758),  # 332: 11KB
    (0x2759, 0x2787),  # 333: 11KB
    (0x2788, 0x27B0),  # 334: 10KB
    (0x27B1, 0x27DF),  # 335: 11KB
    (0x27E0, 0x27FF),  # 336: 7KB
    (0x2800, 0x280E),  # 337: 3KB
    (0x280F, 0x281C),  # 338: 3KB
    (0x281D, 0x2826),  # 339: 2KB
    (0x2827, 0x2834),  # 340: 3KB
    (0x2835, 0x2840),  # 341: 2KB
    (0x2841, 0x284F),  # 342: 3KB
    (0x2850, 0x2869),  # 343: 6KB
    (0x286A, 0x287A),  # 344: 4KB
    (0x287B, 0x28A7),  # 345: 11KB
    (0x28A8, 0x28CF),  # 346: 9KB
    (0x28D0, 0x28ED),  # 347: 7KB
    (0x28EE, 0x2905),  # 348: 5KB
    (0x2906, 0x2929),  # 349: 8KB
    (0x292A, 0x2940),  # 350: 5KB
    (0x2941, 0x2957),  # 351: 5KB
    (0x2958, 0x299E),  # 352: 17KB
    (0x299F, 0x29AF),  # 353: 4KB
    (0x29B0, 0x29D3),  # 354: 8KB
    (0x29D4, 0x29FF),  # 355: 10KB
    (0x2A00, 0x2A0C),  # 356: 3KB
    (0x2A0D, 0x2A1C),  # 357: 3KB
    (0x2A1D, 0x2A2C),  # 358: 3KB
    (0x2A2D, 0x2A3F),  # 359: 4KB
    (0x2A40, 0x2A52),  # 360: 4KB
    (0x2A53, 0x2A6C),  # 361: 6KB
    (0x2A6D, 0x2A8B),  # 362: 7KB
    (0x2A8C, 0x2A9F),  # 363: 4KB
    (0x2AA0, 0x2AB0),  # 364: 4KB
    (0x2AB1, 0x2ACE),  # 365: 7KB
    (0x2ACF, 0x2ADE),  # 366: 3KB
    (0x2ADF, 0x2AEE),  # 367: 3KB
    (0x2AEF, 0x2B01),  # 368: 4KB
    (0x2B02, 0x2B12),  # 369: 4KB
    (0x2B13, 0x2B52),  # 370: 15KB
    (0x2B53, 0x2B77),  # 371: 9KB
    (0x2B78, 0x2BC9),  # 372: 20KB
    (0x2BCA, 0x2BFF),  # 373: 13KB
    (0x2C00, 0x2C0B),  # 374: 2KB
    (0x2C0C, 0x2C17),  # 375: 2KB
    (0x2C18, 0x2C21),  # 376: 2KB
    (0x2C22, 0x2C35),  # 377: 4KB
    (0x2C36, 0x2C56),  # 378: 8KB
    (0x2C57, 0x2C60),  # 379: 2KB
    (0x2C61, 0x2C79),  # 380: 6KB
    (0x2C7A, 0x2C9E),  # 381: 9KB
    (0x2C9F, 0x2CCE),  # 382: 11KB
    (0x2CCF, 0x2CE5),  # 383: 5KB
    (0x2CE6, 0x2CF8),  # 384: 4KB
    (0x2CF9, 0x2D14),  # 385: 6KB
    (0x2D15, 0x2D46),  # 386: 12KB
    (0x2D47, 0x2D60),  # 387: 6KB
    (0x2D61, 0x2D69),  # 388: 2KB
    (0x2D6A, 0x2D9E),  # 389: 13KB
    (0x2D9F, 0x2DAC),  # 390: 3KB
    (0x2DAD, 0x2DEC),  # 391: 15KB
    (0x2DED, 0x2DFF),  # 392: 4KB
    (0x2E00, 0x2E0F),  # 393: 3KB
    (0x2E10, 0x2E55),  # 394: 17KB
    (0x2E56, 0x2E84),  # 395: 11KB
    (0x2E85, 0x2EAA),  # 396: 9KB
    (0x2EAB, 0x2EDF),  # 397: 13KB
    (0x2EE0, 0x2F16),  # 398: 13KB
    (0x2F17, 0x2F53),  # 399: 15KB
    (0x2F54, 0x2F8C),  # 400: 14KB
    (0x2F8D, 0x2FC6),  # 401: 14KB
    (0x2FC7, 0x2FFF),  # 402: 14KB
    (0x3000, 0x300B),  # 403: 2KB
    (0x300C, 0x3018),  # 404: 3KB
    (0x3019, 0x3024),  # 405: 2KB
    (0x3025, 0x3041),  # 406: 7KB
    (0x3042, 0x3069),  # 407: 9KB
    (0x306A, 0x3097),  # 408: 11KB
    (0x3098, 0x30A4),  # 409: 3KB
    (0x30A5, 0x30D2),  # 410: 11KB
    (0x30D3, 0x3101),  # 411: 11KB
    (0x3102, 0x3126),  # 412: 9KB
    (0x3127, 0x3152),  # 413: 10KB
    (0x3153, 0x3174),  # 414: 8KB
    (0x3175, 0x31A8),  # 415: 12KB
    (0x31A9, 0x31FF),  # 416: 21KB
    (0x3200, 0x320F),  # 417: 3KB
    (0x3210, 0x3222),  # 418: 4KB
    (0x3223, 0x3234),  # 419: 4KB
    (0x3235, 0x3248),  # 420: 4KB
    (0x3249, 0x325A),  # 421: 4KB
    (0x325B, 0x3281),  # 422: 9KB
    (0x3282, 0x3293),  # 423: 4KB
    (0x3294, 0x32AD),  # 424: 6KB
    (0x32AE, 0x32D3),  # 425: 9KB
    (0x32D4, 0x32ED),  # 426: 6KB
    (0x32EE, 0x3323),  # 427: 13KB
    (0x3324, 0x3345),  # 428: 8KB
    (0x3346, 0x335B),  # 429: 5KB
    (0x335D, 0x3380),  # 430: 8KB
    (0x3381, 0x33A7),  # 431: 9KB
    (0x33A8, 0x33CF),  # 432: 9KB
    (0x33D0, 0x33FF),  # 433: 11KB
    (0x3400, 0x340E),  # 434: 3KB
    (0x340F, 0x341A),  # 435: 2KB
    (0x341B, 0x3445),  # 436: 10KB
    (0x3446, 0x3499),  # 437: 20KB
    (0x349A, 0x34BB),  # 438: 8KB
    (0x34BC, 0x34D9),  # 439: 7KB
    (0x34DA, 0x3508),  # 440: 11KB
    (0x3509, 0x3537),  # 441: 11KB
    (0x3538, 0x3555),  # 442: 7KB
    (0x3556, 0x3595),  # 443: 15KB
    (0x3596, 0x35BA),  # 444: 9KB
    (0x35BB, 0x35DA),  # 445: 7KB
    (0x35DB, 0x35FF),  # 446: 9KB
    (0x3600, 0x360A),  # 447: 2KB
    (0x360B, 0x3612),  # 448: 1KB
    (0x3613, 0x361D),  # 449: 2KB
    (0x361E, 0x3639),  # 450: 6KB
    (0x363A, 0x3647),  # 451: 3KB
    (0x3648, 0x3664),  # 452: 7KB
    (0x3665, 0x367A),  # 453: 5KB
    (0x367B, 0x3691),  # 454: 5KB
    (0x3692, 0x36AD),  # 455: 6KB
    (0x36AE, 0x36DB),  # 456: 11KB
    (0x36DC, 0x3702),  # 457: 9KB
    (0x3703, 0x372C),  # 458: 10KB
    (0x372D, 0x374B),  # 459: 7KB
    (0x374C, 0x3778),  # 460: 11KB
    (0x3779, 0x37C1),  # 461: 18KB
    (0x37C2, 0x37D6),  # 462: 5KB
    (0x37D7, 0x37FF),  # 463: 10KB
    (0x3800, 0x3809),  # 464: 2KB
    (0x380A, 0x381B),  # 465: 4KB
    (0x381C, 0x3824),  # 466: 2KB
    (0x3825, 0x3832),  # 467: 3KB
    (0x3833, 0x3840),  # 468: 3KB
    (0x3841, 0x384A),  # 469: 2KB
    (0x384B, 0x3860),  # 470: 5KB
    (0x3861, 0x387A),  # 471: 6KB
    (0x387B, 0x389E),  # 472: 8KB
    (0x389F, 0x38A7),  # 473: 2KB
    (0x38A8, 0x38C0),  # 474: 6KB
    (0x38C1, 0x38DF),  # 475: 7KB
    (0x38E0, 0x38F9),  # 476: 6KB
    (0x38FA, 0x3900),  # 477: 1KB
    (0x3901, 0x390A),  # 478: 2KB
    (0x390B, 0x3947),  # 479: 15KB
    (0x3948, 0x3984),  # 480: 15KB
    (0x3985, 0x39AF),  # 481: 10KB
    (0x39B0, 0x39FF),  # 482: 19KB
    (0x3A00, 0x3A08),  # 483: 2KB
    (0x3A09, 0x3A15),  # 484: 3KB
    (0x3A16, 0x3A25),  # 485: 3KB
    (0x3A26, 0x3A4C),  # 486: 9KB
    (0x3A4D, 0x3A5A),  # 487: 3KB
    (0x3A5B, 0x3A76),  # 488: 6KB
    (0x3A77, 0x3A93),  # 489: 7KB
    (0x3A94, 0x3AAE),  # 490: 6KB
    (0x3AAF, 0x3ACF),  # 491: 8KB
    (0x3AD0, 0x3AF3),  # 492: 8KB
    (0x3AF4, 0x3B1D),  # 493: 10KB
    (0x3B1E, 0x3B58),  # 494: 14KB
    (0x3B59, 0x3B68),  # 495: 3KB
    (0x3B69, 0x3B97),  # 496: 11KB
    (0x3B98, 0x3BC2),  # 497: 10KB
    (0x3BC3, 0x3BFF),  # 498: 15KB
    (0x3C00, 0x3C0B),  # 499: 2KB
    (0x3C0C, 0x3C18),  # 500: 3KB
    (0x3C19, 0x3C26),  # 501: 3KB
    (0x3C27, 0x3C33),  # 502: 3KB
    (0x3C34, 0x3C5C),  # 503: 10KB
    (0x3C5D, 0x3C7E),  # 504: 8KB
    (0x3C7F, 0x3C90),  # 505: 4KB
    (0x3C91, 0x3CB3),  # 506: 8KB
    (0x3CB4, 0x3CCE),  # 507: 6KB
    (0x3CCF, 0x3CE9),  # 508: 6KB
    (0x3CEA, 0x3D0F),  # 509: 9KB
    (0x3D10, 0x3D28),  # 510: 6KB
    (0x3D29, 0x3D46),  # 511: 7KB
    (0x3D47, 0x3D64),  # 512: 7KB
    (0x3D65, 0x3D7A),  # 513: 5KB
    (0x3D7B, 0x3DA2),  # 514: 9KB
    (0x3DA3, 0x3DCC),  # 515: 10KB
    (0x3DCD, 0x3DD7),  # 516: 2KB
    (0x3DD8, 0x3DFF),  # 517: 9KB
    (0x3E00, 0x3E0F),  # 518: 3KB
    (0x3E10, 0x3E1F),  # 519: 3KB
    (0x3E20, 0x3E44),  # 520: 9KB
    (0x3E45, 0x3E5F),  # 521: 6KB
    (0x3E60, 0x3E6A),  # 522: 2KB
    (0x3E6B, 0x3E7D),  # 523: 4KB
    (0x3E7E, 0x3EA0),  # 524: 8KB
    (0x3EA1, 0x3EB0),  # 525: 3KB
    (0x3EB1, 0x3EE1),  # 526: 12KB
    (0x3EE2, 0x3F05),  # 527: 8KB
    (0x3F06, 0x3F3B),  # 528: 13KB
    (0x3F3C, 0x3F55),  # 529: 6KB
    (0x3F56, 0x3F66),  # 530: 4KB
    (0x3F67, 0x3F7B),  # 531: 5KB
    (0x3F7C, 0x3F9A),  # 532: 7KB
    (0x3F9B, 0x3FCB),  # 533: 12KB
    (0x3FCC, 0x3FFF),  # 534: 12KB
    (0x4000, 0x4008),  # 535: 2KB
    (0x4009, 0x4010),  # 536: 1KB
    (0x4011, 0x401F),  # 537: 3KB
    (0x4020, 0x402E),  # 538: 3KB
    (0x402F, 0x4038),  # 539: 2KB
    (0x4039, 0x4080),  # 540: 17KB
    (0x4081, 0x40B6),  # 541: 13KB
    (0x40B7, 0x40E0),  # 542: 10KB
    (0x40E1, 0x4112),  # 543: 12KB
    (0x4113, 0x411B),  # 544: 2KB
    (0x411C, 0x414A),  # 545: 11KB
    (0x414B, 0x4179),  # 546: 11KB
    (0x417A, 0x41CD),  # 547: 20KB
    (0x41CE, 0x41FF),  # 548: 12KB
    (0x4200, 0x4211),  # 549: 4KB
    (0x4212, 0x421B),  # 550: 2KB
    (0x421C, 0x4226),  # 551: 2KB
    (0x4227, 0x4232),  # 552: 2KB
    (0x4233, 0x4244),  # 553: 4KB
    (0x4245, 0x4255),  # 554: 4KB
    (0x4256, 0x4277),  # 555: 8KB
    (0x4278, 0x4291),  # 556: 6KB
    (0x4292, 0x42B0),  # 557: 7KB
    (0x42B1, 0x42D7),  # 558: 9KB
    (0x42D8, 0x42E5),  # 559: 3KB
    (0x42EA, 0x4307),  # 560: 7KB
    (0x4308, 0x4320),  # 561: 6KB
    (0x4321, 0x433B),  # 562: 6KB
    (0x433C, 0x4354),  # 563: 6KB
    (0x4355, 0x436B),  # 564: 5KB
    (0x436C, 0x4392),  # 565: 9KB
    (0x4393, 0x439B),  # 566: 2KB
    (0x439C, 0x43E8),  # 567: 19KB
    (0x43E9, 0x43FF),  # 568: 5KB
    (0x4400, 0x4412),  # 569: 4KB
    (0x4413, 0x4419),  # 570: 1KB
    (0x441A, 0x4425),  # 571: 2KB
    (0x4426, 0x4431),  # 572: 2KB
    (0x4432, 0x4442),  # 573: 4KB
    (0x4443, 0x4460),  # 574: 7KB
    (0x4461, 0x447D),  # 575: 7KB
    (0x447E, 0x4485),  # 576: 1KB
    (0x4486, 0x4490),  # 577: 2KB
    (0x4491, 0x44A6),  # 578: 5KB
    (0x44A7, 0x44B9),  # 579: 4KB
    (0x44BA, 0x44CD),  # 580: 4KB
    (0x44CE, 0x44E8),  # 581: 6KB
    (0x44E9, 0x4519),  # 582: 12KB
    (0x451A, 0x452C),  # 583: 4KB
    (0x452D, 0x4536),  # 584: 2KB
    (0x4537, 0x4551),  # 585: 6KB
    (0x4552, 0x4587),  # 586: 13KB
    (0x4588, 0x45AA),  # 587: 8KB
    (0x45AB, 0x45DA),  # 588: 11KB
    (0x45DB, 0x45E4),  # 589: 2KB
    (0x45E5, 0x45FF),  # 590: 6KB
    (0x4600, 0x4607),  # 591: 1KB
    (0x4608, 0x460E),  # 592: 1KB
    (0x460F, 0x4619),  # 593: 2KB
    (0x461A, 0x4627),  # 594: 3KB
    (0x4628, 0x4633),  # 595: 2KB
    (0x4634, 0x463F),  # 596: 2KB
    (0x4640, 0x4649),  # 597: 2KB
    (0x464A, 0x4675),  # 598: 10KB
    (0x4676, 0x4682),  # 599: 3KB
    (0x4683, 0x46A1),  # 600: 7KB
    (0x46A2, 0x46B8),  # 601: 5KB
    (0x46B9, 0x46EF),  # 602: 13KB
    (0x46F0, 0x4719),  # 603: 10KB
    (0x471A, 0x4734),  # 604: 6KB
    (0x4735, 0x4746),  # 605: 4KB
    (0x4747, 0x475C),  # 606: 5KB
    (0x475D, 0x4774),  # 607: 5KB
    (0x4775, 0x477D),  # 608: 2KB
    (0x477E, 0x47B9),  # 609: 14KB
    (0x47BA, 0x47FF),  # 610: 17KB
    (0x4800, 0x480C),  # 611: 3KB
    (0x480D, 0x481B),  # 612: 3KB
    (0x481C, 0x4826),  # 613: 2KB
    (0x4827, 0x4854),  # 614: 11KB
    (0x4855, 0x4863),  # 615: 3KB
    (0x4864, 0x487A),  # 616: 5KB
    (0x487B, 0x4892),  # 617: 5KB
    (0x4893, 0x48C2),  # 618: 11KB
    (0x48C3, 0x48DC),  # 619: 6KB
    (0x48DD, 0x4900),  # 620: 8KB
    (0x4901, 0x492F),  # 621: 11KB
    (0x4930, 0x4944),  # 622: 5KB
    (0x4945, 0x494E),  # 623: 2KB
    (0x494F, 0x496A),  # 624: 6KB
    (0x496B, 0x4981),  # 625: 5KB
    (0x4982, 0x49CD),  # 626: 18KB
    (0x49CE, 0x49E6),  # 627: 6KB
    (0x49E7, 0x49FF),  # 628: 6KB
    (0x4A00, 0x4A0B),  # 629: 2KB
    (0x4A0C, 0x4A17),  # 630: 2KB
    (0x4A18, 0x4A23),  # 631: 2KB
    (0x4A24, 0x4A63),  # 632: 15KB
    (0x4A64, 0x4A8F),  # 633: 10KB
    (0x4A90, 0x4ABE),  # 634: 11KB
    (0x4ABF, 0x4AE9),  # 635: 10KB
    (0x4AEA, 0x4B17),  # 636: 11KB
    (0x4B18, 0x4B47),  # 637: 11KB
    (0x4B48, 0x4B7B),  # 638: 12KB
    (0x4B7C, 0x4BC6),  # 639: 18KB
    (0x4BC7, 0x4BFF),  # 640: 14KB
    (0x4C00, 0x4C0A),  # 641: 2KB
    (0x4C0B, 0x4C17),  # 642: 3KB
    (0x4C18, 0x4C23),  # 643: 2KB
    (0x4C24, 0x4C3B),  # 644: 5KB
    (0x4C3C, 0x4C55),  # 645: 6KB
    (0x4C56, 0x4C7F),  # 646: 10KB
    (0x4C80, 0x4CA9),  # 647: 10KB
    (0x4CAA, 0x4CC7),  # 648: 7KB
    (0x4CC8, 0x4CE4),  # 649: 7KB
    (0x4CE5, 0x4CFC),  # 650: 5KB
    (0x4CFD, 0x4D1D),  # 651: 8KB
    (0x4D1E, 0x4D2A),  # 652: 3KB
    (0x4D2B, 0x4D48),  # 653: 7KB
    (0x4D49, 0x4D6B),  # 654: 8KB
    (0x4D6C, 0x4D74),  # 655: 2KB
    (0x4D78, 0x4D9A),  # 656: 8KB
    (0x4D9B, 0x4DFF),  # 657: 25KB
    (0x4E00, 0x4E0C),  # 658: 3KB
    (0x4E0D, 0x4E55),  # 659: 18KB
    (0x4E56, 0x4EA6),  # 660: 20KB
    (0x4EA7, 0x4EC2),  # 661: 6KB
    (0x4EC3, 0x4EFE),  # 662: 14KB
    (0x4EFF, 0x4F38),  # 663: 14KB
    (0x4F39, 0x4F74),  # 664: 14KB
    (0x4F75, 0x4FBB),  # 665: 17KB
    (0x4FBC, 0x4FFF),  # 666: 16KB
    (0x5000, 0x500E),  # 667: 3KB
    (0x500F, 0x501F),  # 668: 4KB
    (0x5020, 0x5039),  # 669: 6KB
    (0x503A, 0x504C),  # 670: 4KB
    (0x504D, 0x5059),  # 671: 3KB
    (0x505A, 0x5074),  # 672: 6KB
    (0x5075, 0x509A),  # 673: 9KB
    (0x509B, 0x50B8),  # 674: 7KB
    (0x50B9, 0x50E4),  # 675: 10KB
    (0x50E5, 0x5109),  # 676: 9KB
    (0x510A, 0x511D),  # 677: 4KB
    (0x511E, 0x512F),  # 678: 4KB
    (0x5130, 0x5167),  # 679: 13KB
    (0x5168, 0x5197),  # 680: 11KB
    (0x5198, 0x51AF),  # 681: 5KB
    (0x51B0, 0x51D4),  # 682: 9KB
    (0x51D5, 0x51FF),  # 683: 10KB
    (0x5200, 0x5206),  # 684: 1KB
    (0x5207, 0x520E),  # 685: 1KB
    (0x520F, 0x5215),  # 686: 1KB
    (0x5216, 0x521D),  # 687: 1KB
    (0x521E, 0x522B),  # 688: 3KB
    (0x522C, 0x5235),  # 689: 2KB
    (0x5236, 0x5243),  # 690: 3KB
    (0x5244, 0x5255),  # 691: 4KB
    (0x5256, 0x5268),  # 692: 4KB
    (0x5269, 0x5281),  # 693: 6KB
    (0x5282, 0x52A5),  # 694: 8KB
    (0x52A6, 0x52BD),  # 695: 5KB
    (0x52BE, 0x52FF),  # 696: 16KB
    (0x5300, 0x5332),  # 697: 12KB
    (0x5333, 0x535C),  # 698: 10KB
    (0x535D, 0x538E),  # 699: 12KB
    (0x538F, 0x53A6),  # 700: 5KB
    (0x53A7, 0x53E3),  # 701: 15KB
    (0x53E4, 0x53FF),  # 702: 6KB
    (0x5400, 0x540F),  # 703: 3KB
    (0x5410, 0x541B),  # 704: 2KB
    (0x541C, 0x5430),  # 705: 5KB
    (0x5431, 0x543D),  # 706: 3KB
    (0x543E, 0x544D),  # 707: 3KB
    (0x544E, 0x5456),  # 708: 2KB
    (0x5457, 0x5486),  # 709: 11KB
    (0x5487, 0x54A9),  # 710: 8KB
    (0x54AA, 0x54CE),  # 711: 9KB
    (0x54CF, 0x54EE),  # 712: 7KB
    (0x54EF, 0x5513),  # 713: 9KB
    (0x5514, 0x5537),  # 714: 8KB
    (0x5538, 0x555F),  # 715: 9KB
    (0x5560, 0x5596),  # 716: 13KB
    (0x5597, 0x55B9),  # 717: 8KB
    (0x55BA, 0x55FF),  # 718: 17KB
    (0x5600, 0x5611),  # 719: 4KB
    (0x5612, 0x561B),  # 720: 2KB
    (0x561C, 0x5627),  # 721: 2KB
    (0x5628, 0x5636),  # 722: 3KB
    (0x5637, 0x5658),  # 723: 8KB
    (0x5659, 0x5676),  # 724: 7KB
    (0x5677, 0x5698),  # 725: 8KB
    (0x5699, 0x56B1),  # 726: 6KB
    (0x56B2, 0x56D0),  # 727: 7KB
    (0x56D1, 0x56E2),  # 728: 4KB
    (0x56E3, 0x5735),  # 729: 20KB
    (0x5736, 0x5749),  # 730: 4KB
    (0x574A, 0x5783),  # 731: 14KB
    (0x5784, 0x57C5),  # 732: 16KB
    (0x57C6, 0x57FF),  # 733: 14KB
    (0x5800, 0x580A),  # 734: 2KB
    (0x5800, 0x580B),  # 735: 2KB
    (0x580C, 0x581B),  # 736: 3KB
    (0x581C, 0x5828),  # 737: 3KB
    (0x5829, 0x5837),  # 738: 3KB
    (0x5838, 0x584A),  # 739: 4KB
    (0x584B, 0x586B),  # 740: 8KB
    (0x586C, 0x5897),  # 741: 10KB
    (0x5898, 0x58A3),  # 742: 2KB
    (0x58A4, 0x58B2),  # 743: 3KB
    (0x58B3, 0x58C5),  # 744: 4KB
    (0x58C6, 0x58EF),  # 745: 10KB
    (0x58F0, 0x5923),  # 746: 12KB
    (0x5924, 0x5958),  # 747: 13KB
    (0x5959, 0x598D),  # 748: 13KB
    (0x598E, 0x599B),  # 749: 3KB
    (0x599C, 0x59B1),  # 750: 5KB
    (0x59B2, 0x59BD),  # 751: 2KB
    (0x59B2, 0x59D4),  # 752: 8KB
    (0x59BE, 0x59D4),  # 753: 5KB
    (0x59D5, 0x59FF),  # 754: 10KB
    (0x5A00, 0x5A1F),  # 755: 7KB
    (0x5A20, 0x5A48),  # 756: 10KB
    (0x5A49, 0x5A6E),  # 757: 9KB
    (0x5A6F, 0x5A8B),  # 758: 7KB
    (0x5A8C, 0x5AAD),  # 759: 8KB
    (0x5AAE, 0x5ACC),  # 760: 7KB
    (0x5ACD, 0x5AE9),  # 761: 7KB
    (0x5AEA, 0x5B09),  # 762: 7KB
    (0x5B0A, 0x5B29),  # 763: 7KB
    (0x5B2A, 0x5B3F),  # 764: 5KB
    (0x5B40, 0x5B60),  # 765: 8KB
    (0x5B61, 0x5B7F),  # 766: 7KB
    (0x5B80, 0x5B9C),  # 767: 7KB
    (0x5B9D, 0x5BB9),  # 768: 7KB
    (0x5BBA, 0x5BE1),  # 769: 9KB
    (0x5BE2, 0x5BFF),  # 770: 7KB
    (0x5C00, 0x5C1B),  # 771: 6KB
    (0x5C1C, 0x5C34),  # 772: 6KB
    (0x5C35, 0x5C4C),  # 773: 5KB
    (0x5C4D, 0x5C65),  # 774: 6KB
    (0x5C66, 0x5C7D),  # 775: 5KB
    (0x5C7E, 0x5C98),  # 776: 6KB
    (0x5C99, 0x5CB3),  # 777: 6KB
    (0x5CB4, 0x5CC8),  # 778: 5KB
    (0x5CC9, 0x5CDF),  # 779: 5KB
    (0x5CE0, 0x5CFA),  # 780: 6KB
    (0x5CFB, 0x5D12),  # 781: 5KB
    (0x5D13, 0x5D2A),  # 782: 5KB
    (0x5D2B, 0x5D46),  # 783: 6KB
    (0x5D47, 0x5D5D),  # 784: 5KB
    (0x5D5E, 0x5D79),  # 785: 6KB
    (0x5D7A, 0x5D95),  # 786: 6KB
    (0x5D96, 0x5DB0),  # 787: 6KB
    (0x5DB1, 0x5DC7),  # 788: 5KB
    (0x5DC8, 0x5DE3),  # 789: 6KB
    (0x5DE4, 0x5DFF),  # 790: 6KB
    (0x5E94, 0x5EAD),  # 791: 6KB
    (0x5EAE, 0x5EDC),  # 792: 11KB
    (0x5EDD, 0x5EF5),  # 793: 6KB
    (0x5EF6, 0x5F11),  # 794: 6KB
    (0x5F12, 0x5F2B),  # 795: 6KB
    (0x5F2C, 0x5F45),  # 796: 6KB
    (0x5F46, 0x5F5E),  # 797: 6KB
    (0x5F5F, 0x5F77),  # 798: 6KB
    (0x5F78, 0x5F92),  # 799: 6KB
    (0x5F93, 0x5FBE),  # 800: 10KB
    (0x5FBF, 0x5FDF),  # 801: 8KB
    (0x5FE0, 0x5FFE),  # 802: 7KB
    (0x7200, 0x727F),  # 803: 31KB
    (0x7280, 0x72FE),  # 804: 31KB
    (0x7800, 0x7805),  # 805: 1KB
    (0x7D06, 0x7D3A),  # 806: 13KB
    (0x7DD6, 0x7DFF),  # 807: 10KB
    (0x7E2B, 0x7E56),  # 808: 10KB
    (0x7E57, 0x7E81),  # 809: 10KB
    (0x7F76, 0x7FA2),  # 810: 11KB
    (0x7F88, 0x7FAB),  # 811: 8KB
    (0x7FA3, 0x7FCE),  # 812: 10KB
    (0x8000, 0x8069),  # 813: 26KB
    (0x806A, 0x80D3),  # 814: 26KB
    (0x80D4, 0x813D),  # 815: 26KB
    (0x813E, 0x81A7),  # 816: 26KB
    (0x81A8, 0x81B1),  # 817: 2KB
    (0x81B2, 0x81F0),  # 818: 15KB
    (0x8200, 0x8227),  # 819: 9KB
    (0x8228, 0x824C),  # 820: 9KB
    (0x824D, 0x8272),  # 821: 9KB
    (0x8273, 0x829C),  # 822: 10KB
    (0x82C4, 0x82FD),  # 823: 14KB
    (0x82FE, 0x833A),  # 824: 15KB
    (0x833B, 0x839F),  # 825: 25KB
    (0x83A0, 0x83CA),  # 826: 10KB
    (0x8400, 0x8413),  # 827: 4KB
    (0x8414, 0x841D),  # 828: 2KB
    (0x84D1, 0x84EF),  # 829: 7KB
    (0x84F0, 0x850E),  # 830: 7KB
    (0x850F, 0x852D),  # 831: 7KB
    (0x852E, 0x854A),  # 832: 7KB
    (0x8570, 0x8593),  # 833: 8KB
    (0x8594, 0x85B7),  # 834: 8KB
    (0x8600, 0x860F),  # 835: 3KB
    (0x8630, 0x863F),  # 836: 3KB
    (0x8640, 0x864F),  # 837: 3KB
    (0x865D, 0x866C),  # 838: 3KB
    (0x868D, 0x869C),  # 839: 3KB
    (0x869D, 0x86AC),  # 840: 3KB
    (0x86C7, 0x86D6),  # 841: 3KB
    (0x86D7, 0x86E6),  # 842: 3KB
    (0x86FF, 0x870E),  # 843: 3KB
    (0x8727, 0x8736),  # 844: 3KB
    (0x8737, 0x8746),  # 845: 3KB
    (0x8753, 0x876F),  # 846: 7KB
    (0x8770, 0x878C),  # 847: 7KB
    (0x878D, 0x87A8),  # 848: 6KB
    (0x87A9, 0x87C5),  # 849: 7KB
    (0x87C6, 0x87E2),  # 850: 7KB
    (0x87E3, 0x87FF),  # 851: 7KB
    (0x8800, 0x89B7),  # 852: 109KB
    (0x8BE0, 0x8BFF),  # 853: 7KB
    (0x8C00, 0x8CAD),  # 854: 43KB
    (0x8C25, 0x8CB8),  # 855: 36KB
    (0x8E8F, 0x8F38),  # 856: 42KB
    (0x9000, 0x9082),  # 857: 32KB
    (0x9152, 0x91FF),  # 858: 43KB
    (0x92CB, 0x935D),  # 859: 36KB
    (0x935A, 0x93A2),  # 860: 18KB
    (0x9400, 0x9436),  # 861: 13KB
    (0x9437, 0x945C),  # 862: 9KB
    (0x961C, 0x9692),  # 863: 29KB
    (0x9713, 0x977F),  # 864: 27KB
    (0x9780, 0x97FF),  # 865: 31KB
    (0x9AA3, 0x9AE2),  # 866: 15KB
    (0x9AB1, 0x9AFB),  # 867: 18KB
    (0x9C25, 0x9C40),  # 868: 6KB
    (0x9E39, 0x9E6F),  # 869: 13KB
    (0x9F8C, 0x9FFF),  # 870: 28KB
    (0x8800, 0x89B7),  # 871: ADPCM-B 109KB
    (0x89B8, 0x89FF),  # 872: ADPCM-B 17KB
    (0x8BE0, 0x8BFF),  # 873: ADPCM-B 7KB
    (0x8C00, 0x8C24),  # 874: ADPCM-B 9KB
    (0x8E00, 0x8E23),  # 875: ADPCM-B 8KB
    (0x8E24, 0x8E8E),  # 876: ADPCM-B 26KB
    (0x8F39, 0x8FFF),  # 877: ADPCM-B 49KB
    (0x9000, 0x9082),  # 878: ADPCM-B 32KB
    (0x9577, 0x95FF),  # 879: ADPCM-B 34KB
    (0x9600, 0x961B),  # 880: ADPCM-B 6KB
    (0x9800, 0x9874),  # 881: ADPCM-B 29KB
    (0x98E5, 0x995A),  # 882: ADPCM-B 29KB
    (0x995B, 0x99B2),  # 883: ADPCM-B 21KB
    (0x9AE3, 0x9B18),  # 884: ADPCM-B 13KB
    (0x9B19, 0x9B64),  # 885: ADPCM-B 18KB
    (0x9B65, 0x9B8D),  # 886: ADPCM-B 10KB
    (0x9BCA, 0x9BFF),  # 887: ADPCM-B 13KB
    (0x9E00, 0x9E38),  # 888: ADPCM-B 14KB
    (0x9E39, 0x9E6F),  # 889: ADPCM-B 13KB
]

FM_FNUMS = [617, 654, 693, 734, 778, 824, 873, 925, 980, 1038, 1100, 1165]
SSG_PERIODS_OCT4 = [239, 225, 213, 201, 190, 179, 169, 159, 150, 142, 134, 127]

# ================================================================
# ORIGINAL NEOSYNTH FM PATCHES (0-3)
# ================================================================
FM_PATCH_SIMPLE = {
    'DT_MUL': [0x01, 0x00, 0x00, 0x00],
    'TL':     [0x00, 0x7F, 0x7F, 0x7F],
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x00, 0x00, 0x00, 0x00],
    'SR':     [0x00, 0x00, 0x00, 0x00],
    'SL_RR':  [0x0F, 0x0F, 0x0F, 0x0F],
    'FB_ALG': 0x07,
    'LR_AMS_PMS': 0xC0,
}
FM_PATCH_ORGAN = {
    'DT_MUL': [0x01, 0x02, 0x01, 0x02],
    'TL':     [0x23, 0x00, 0x23, 0x00],  # carriers (ops 1,3) at 0, mods at 0x23
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x05, 0x02, 0x05, 0x02],
    'SR':     [0x02, 0x01, 0x02, 0x01],
    'SL_RR':  [0x1A, 0x0F, 0x1A, 0x0F],  # carriers: SL=0, RR=15
    'FB_ALG': 0x35,  # algorithm 5 (2 carriers: ops 1 and 3), FB=6
    'LR_AMS_PMS': 0xC0,
}
FM_PATCH_BRASS = {
    'DT_MUL': [0x01, 0x01, 0x01, 0x01],
    'TL':     [0x1A, 0x00, 0x1C, 0x00],  # ops 1,3 are carriers at 0
    'KS_AR':  [0x1F, 0x1D, 0x1F, 0x1D],
    'AM_DR':  [0x08, 0x04, 0x0A, 0x04],
    'SR':     [0x02, 0x02, 0x02, 0x02],
    'SL_RR':  [0x1A, 0x1F, 0x1A, 0x1F],  # carriers: SL=1, RR=15
    'FB_ALG': 0x35,  # algorithm 5, FB=6
    'LR_AMS_PMS': 0xC0,
}
FM_PATCH_PIANO = {
    'DT_MUL': [0x02, 0x01, 0x03, 0x01],
    'TL':     [0x28, 0x00, 0x30, 0x00],  # ops 1,3 are carriers at 0
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x10, 0x0A, 0x10, 0x0A],
    'SR':     [0x06, 0x04, 0x06, 0x04],
    'SL_RR':  [0x2A, 0x2F, 0x2A, 0x2F],  # carriers: SL=2, RR=15
    'FB_ALG': 0x25,  # algorithm 5, FB=4
    'LR_AMS_PMS': 0xC0,
}

# ================================================================
# KOF96 EXTRACTED FM PATCHES (4-19) — via Z80 tracer
# ================================================================

# Patch 4: Lead synth with rich harmonics (ALG=5 FB=5)
# Used in KOF96 character select and stage themes
FM_PATCH_KOF_LEAD = {
    'DT_MUL': [0x70, 0x30, 0x20, 0x63],
    'TL':     [0x19, 0x00, 0x00, 0x00],
    'KS_AR':  [0x5A, 0x94, 0x98, 0xD4],
    'AM_DR':  [0x08, 0x07, 0x03, 0x10],
    'SR':     [0x01, 0x01, 0x01, 0x01],
    'SL_RR':  [0x3B, 0x9C, 0x58, 0x5A],
    'FB_ALG': 0x2D,
    'LR_AMS_PMS': 0xC0,
}

# Patch 5: Dual-carrier strings, gentle detune (ALG=4 FB=2)
# Lush ensemble sound from KOF96 opening
FM_PATCH_KOF_STRINGS = {
    'DT_MUL': [0x75, 0x72, 0x35, 0x32],
    'TL':     [0x1E, 0x00, 0x14, 0x00],
    'KS_AR':  [0x9F, 0x9F, 0x9F, 0x9F],
    'AM_DR':  [0x05, 0x05, 0x00, 0x0A],
    'SR':     [0x05, 0x05, 0x07, 0x05],
    'SL_RR':  [0x25, 0xF7, 0x05, 0x27],
    'FB_ALG': 0x14,
    'LR_AMS_PMS': 0xC0,
}

# Patch 6: FM percussion hit — metallic, all carriers (ALG=6 FB=7)
# Impact/crash sound used in KOF96 fight intros
FM_PATCH_KOF_PERC = {
    'DT_MUL': [0x01, 0x33, 0x02, 0x51],
    'TL':     [0x11, 0x00, 0x00, 0x00],
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x19, 0x1F, 0x1F, 0x1F],
    'SR':     [0x1E, 0x00, 0x00, 0x00],
    'SL_RR':  [0x3F, 0x0F, 0x0F, 0x0F],
    'FB_ALG': 0x3E,
    'LR_AMS_PMS': 0xC0,
}

# Patch 7: Slow-attack pad, warm and wide (ALG=4 FB=7)
# Used in KOF96 ending themes and character intros
FM_PATCH_KOF_PAD = {
    'DT_MUL': [0x74, 0x74, 0x34, 0x34],
    'TL':     [0x36, 0x00, 0x32, 0x00],
    'KS_AR':  [0x0E, 0x0A, 0x0D, 0x0A],
    'AM_DR':  [0x01, 0x01, 0x01, 0x01],
    'SR':     [0x00, 0x00, 0x00, 0x00],
    'SL_RR':  [0x48, 0x1A, 0x48, 0x1A],
    'FB_ALG': 0x3C,
    'LR_AMS_PMS': 0xC0,
}

# Patch 8: Aggressive lead, high FB distortion (ALG=5 FB=7)
# KOF96 boss battle theme lead voice
FM_PATCH_KOF_LEAD_HARD = {
    'DT_MUL': [0x71, 0x32, 0x22, 0x32],
    'TL':     [0x14, 0x00, 0x00, 0x00],
    'KS_AR':  [0x5A, 0x1F, 0x9F, 0x5F],
    'AM_DR':  [0x18, 0x0F, 0x06, 0x06],
    'SR':     [0x0D, 0x00, 0x02, 0x02],
    'SL_RR':  [0x28, 0x28, 0x58, 0x68],
    'FB_ALG': 0x3D,
    'LR_AMS_PMS': 0xC0,
}

# Patch 9: Orchestral strings, moderate attack (ALG=4 FB=4)
# Background strings in stage themes
FM_PATCH_KOF_ORCH_STR = {
    'DT_MUL': [0x71, 0x71, 0x30, 0x31],
    'TL':     [0x18, 0x00, 0x13, 0x00],
    'KS_AR':  [0x1C, 0x1C, 0x19, 0x1C],
    'AM_DR':  [0x0B, 0x00, 0x0C, 0x00],
    'SR':     [0x07, 0x05, 0x0B, 0x05],
    'SL_RR':  [0x73, 0x28, 0x16, 0x28],
    'FB_ALG': 0x24,
    'LR_AMS_PMS': 0xC0,
}

# Patch 10: Pure additive sine, soft bell-like (ALG=7 FB=0)
# Clean tones for melodic lines
FM_PATCH_KOF_SINE = {
    'DT_MUL': [0x01, 0x00, 0x00, 0x00],
    'TL':     [0x00, 0x00, 0x00, 0x00],
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x1A, 0x0A, 0x10, 0x00],
    'SR':     [0x01, 0x00, 0x00, 0x00],
    'SL_RR':  [0x68, 0x68, 0x68, 0x68],
    'FB_ALG': 0x07,
    'LR_AMS_PMS': 0xC0,
}

# Patch 11: Sustained power lead (ALG=5 FB=7)
# KOF96 theme melody lines
FM_PATCH_KOF_POWER = {
    'DT_MUL': [0x70, 0x30, 0x70, 0x30],
    'TL':     [0x1B, 0x00, 0x00, 0x00],
    'KS_AR':  [0x1F, 0x9F, 0x5F, 0x1F],
    'AM_DR':  [0x00, 0x00, 0x00, 0x00],
    'SR':     [0x00, 0x03, 0x00, 0x05],
    'SL_RR':  [0x0F, 0x0F, 0x0F, 0x0F],
    'FB_ALG': 0x3D,
    'LR_AMS_PMS': 0xC0,
}

# Patch 12: Heavy bass, serial chain (ALG=0 FB=4)
# KOF96 bass lines in fight themes
FM_PATCH_KOF_BASS = {
    'DT_MUL': [0x73, 0x33, 0x10, 0x00],
    'TL':     [0x17, 0x28, 0x19, 0x3A],
    'KS_AR':  [0x5F, 0xDD, 0xDF, 0xDF],
    'AM_DR':  [0x12, 0x0A, 0x04, 0x03],
    'SR':     [0x0F, 0x08, 0x08, 0x08],
    'SL_RR':  [0xB0, 0x50, 0xD0, 0xB6],
    'FB_ALG': 0x20,
    'LR_AMS_PMS': 0xC0,
}

# Patch 13: Distorted pluck, all ops at max attack (ALG=0 FB=6)
# Sharp hit sound, KOF96 percussion stabs
FM_PATCH_KOF_DIST_PLUCK = {
    'DT_MUL': [0x00, 0x00, 0x00, 0x00],
    'TL':     [0x12, 0x14, 0x13, 0x00],
    'KS_AR':  [0x1F, 0x1F, 0x1F, 0x1F],
    'AM_DR':  [0x02, 0x1F, 0x1F, 0x1F],
    'SR':     [0x00, 0x00, 0x00, 0x00],
    'SL_RR':  [0xFF, 0x0F, 0x0F, 0x0F],
    'FB_ALG': 0x30,
    'LR_AMS_PMS': 0xC0,
}

# Patch 14: Slow nasal lead (ALG=3 FB=7)
# Expressive lead in character themes
FM_PATCH_KOF_NASAL = {
    'DT_MUL': [0x74, 0x31, 0x24, 0x01],
    'TL':     [0x0A, 0x10, 0x1A, 0x00],
    'KS_AR':  [0x1F, 0x08, 0x08, 0x0A],
    'AM_DR':  [0x1F, 0x02, 0x02, 0x02],
    'SR':     [0x00, 0x01, 0x01, 0x01],
    'SL_RR':  [0x63, 0x85, 0x66, 0xB2],
    'FB_ALG': 0x3B,
    'LR_AMS_PMS': 0xC0,
}

# Patch 15: Distorted heavy, thick wall of sound (ALG=1 FB=7)
# Power chords and heavy riffs
FM_PATCH_KOF_DIST_HEAVY = {
    'DT_MUL': [0x75, 0x3D, 0x3F, 0x78],
    'TL':     [0x2C, 0x1D, 0x11, 0x00],
    'KS_AR':  [0x1F, 0x1F, 0x14, 0x1C],
    'AM_DR':  [0x03, 0x01, 0x05, 0x00],
    'SR':     [0x00, 0x00, 0x00, 0x00],
    'SL_RR':  [0x38, 0x38, 0x38, 0x09],
    'FB_ALG': 0x39,
    'LR_AMS_PMS': 0xC0,
}

# Patch 16: Rich evolving pad (ALG=6 FB=0)
# Atmospheric pad in KOF96 story sequences
FM_PATCH_KOF_PAD_RICH = {
    'DT_MUL': [0x01, 0x33, 0x72, 0x31],
    'TL':     [0x4D, 0x00, 0x00, 0x00],
    'KS_AR':  [0x0A, 0x8C, 0x4C, 0x52],
    'AM_DR':  [0x00, 0x00, 0x00, 0x00],
    'SR':     [0x01, 0x00, 0x01, 0x00],
    'SL_RR':  [0x03, 0x05, 0x26, 0x06],
    'FB_ALG': 0x06,
    'LR_AMS_PMS': 0xC0,
}

# Patch 17: Guitar-like pluck (ALG=4 FB=7)
# Acoustic guitar simulation in stage themes
FM_PATCH_KOF_GUITAR = {
    'DT_MUL': [0x32, 0x54, 0x51, 0x32],
    'TL':     [0x22, 0x00, 0x18, 0x00],
    'KS_AR':  [0x1F, 0x0C, 0x1F, 0x0C],
    'AM_DR':  [0x0F, 0x00, 0x1F, 0x00],
    'SR':     [0x00, 0x00, 0x00, 0x00],
    'SL_RR':  [0x21, 0x06, 0x01, 0x05],
    'FB_ALG': 0x3C,
    'LR_AMS_PMS': 0xC0,
}

# Patch 18: Bell/vibraphone tone (ALG=2 FB=7)
# Metallic bell hits in KOF96 victory themes
FM_PATCH_KOF_BELL = {
    'DT_MUL': [0x0C, 0x1F, 0x01, 0x53],
    'TL':     [0x1D, 0x36, 0x1B, 0x00],
    'KS_AR':  [0x1F, 0xDF, 0x1F, 0x9F],
    'AM_DR':  [0x0C, 0x02, 0x0C, 0x05],
    'SR':     [0x04, 0x04, 0x04, 0x07],
    'SL_RR':  [0x1A, 0xF6, 0x06, 0x27],
    'FB_ALG': 0x3A,
    'LR_AMS_PMS': 0xC0,
}

# Patch 19: Electric keys/clav (ALG=2 FB=5)
# Keyboard stabs and comping
FM_PATCH_KOF_KEYS = {
    'DT_MUL': [0x51, 0x05, 0x13, 0x01],
    'TL':     [0x23, 0x2D, 0x26, 0x00],
    'KS_AR':  [0x5F, 0x99, 0x5F, 0x94],
    'AM_DR':  [0x05, 0x05, 0x05, 0x07],
    'SR':     [0x02, 0x02, 0x02, 0x02],
    'SL_RR':  [0x11, 0x11, 0x11, 0xA6],
    'FB_ALG': 0x2A,
    'LR_AMS_PMS': 0xC0,
}

FM_PATCHES = [
    FM_PATCH_SIMPLE,         # 0: Simple sine
    FM_PATCH_ORGAN,          # 1: Organ
    FM_PATCH_BRASS,          # 2: Brass
    FM_PATCH_PIANO,          # 3: Piano
    FM_PATCH_KOF_LEAD,       # 4: KOF Lead
    FM_PATCH_KOF_STRINGS,    # 5: KOF Strings
    FM_PATCH_KOF_PERC,       # 6: KOF FM Perc
    FM_PATCH_KOF_PAD,        # 7: KOF Pad Soft
    FM_PATCH_KOF_LEAD_HARD,  # 8: KOF Lead Hard
    FM_PATCH_KOF_ORCH_STR,   # 9: KOF Orch Strings
    FM_PATCH_KOF_SINE,       # 10: KOF Sine Add
    FM_PATCH_KOF_POWER,      # 11: KOF Power Lead
    FM_PATCH_KOF_BASS,       # 12: KOF Bass Heavy
    FM_PATCH_KOF_DIST_PLUCK, # 13: KOF Dist Pluck
    FM_PATCH_KOF_NASAL,      # 14: KOF Nasal Lead
    FM_PATCH_KOF_DIST_HEAVY, # 15: KOF Dist Heavy
    FM_PATCH_KOF_PAD_RICH,   # 16: KOF Pad Rich
    FM_PATCH_KOF_GUITAR,     # 17: KOF Guitar
    FM_PATCH_KOF_BELL,       # 18: KOF Bell
    FM_PATCH_KOF_KEYS,       # 19: KOF Keys
]
NUM_FM_PATCHES = len(FM_PATCHES)

# FM patch display names (8 chars max, for fix layer)
FM_PATCH_NAMES = [
    "SINE    ",  # 0
    "ORGAN   ",  # 1
    "BRASS   ",  # 2
    "PIANO   ",  # 3
    "KOF LEAD",  # 4
    "KOF STR ",  # 5
    "KOF PERC",  # 6
    "KOF PAD ",  # 7
    "KOF HARD",  # 8
    "KOF ORCH",  # 9
    "KOF SINE",  # 10
    "KOF POWR",  # 11
    "KOF BASS",  # 12
    "KOF DIST",  # 13
    "KOF NASL",  # 14
    "KOF DHVY",  # 15
    "KOF RICH",  # 16
    "KOF GTR ",  # 17
    "KOF BELL",  # 18
    "KOF KEYS",  # 19
]

# ================================================================
# SSG PRESETS — volume envelope parameters for PSG channels
# Each preset: (initial_volume 0-15, decay_rate 0-15, noise_enable 0/1)
# Decay rate: 0=sustained, 1=very slow, 15=instant
# ================================================================
SSG_PRESET_SQUARE   = (15,  0, 0)  # Plain square, sustained
SSG_PRESET_PLUCK    = (15, 10, 0)  # Fast attack, medium decay (arpeggios)
SSG_PRESET_BELL     = (15,  3, 0)  # Fast attack, slow decay (bell)
SSG_PRESET_NOISE_HH = (12, 14, 1)  # Noise channel, fast decay (hi-hat)
SSG_PRESET_BUZZ     = ( 5,  0, 0)  # Low volume, sustained (background texture)

SSG_PRESETS = [
    SSG_PRESET_SQUARE,    # 0: Square
    SSG_PRESET_PLUCK,     # 1: Pluck
    SSG_PRESET_BELL,      # 2: Bell
    SSG_PRESET_NOISE_HH,  # 3: Noise HH
    SSG_PRESET_BUZZ,      # 4: Buzz
]
NUM_SSG_PRESETS = len(SSG_PRESETS)

SSG_PRESET_NAMES = [
    "SQUARE  ",  # 0
    "PLUCK   ",  # 1
    "BELL    ",  # 2
    "NOIZ HH ",  # 3
    "BUZZ    ",  # 4
]
NUM_SAMPLES = len(ADPCM_SAMPLES)

# RAM addresses ($F800-$FFFF)
RAM_CMD       = 0xF800
RAM_PARAM     = 0xF801
RAM_PARAM_FLAG = 0xF802
RAM_FM_PATCH  = 0xF810
RAM_FM_PAN    = 0xF814
RAM_SSG_VOL   = 0xF818
RAM_ADPCMA_PAN = 0xF81C
RAM_ADPCMA_CH = 0xF822
RAM_TEMP      = 0xF830

# Sequencer RAM
RAM_SEQ_PLAYING   = 0xF840   # 1=playing, 0=stopped
RAM_SEQ_ROW_LO    = 0xF841   # current row pointer low
RAM_SEQ_ROW_HI    = 0xF842   # current row pointer high
RAM_SEQ_START_LO  = 0xF843   # song start addr low
RAM_SEQ_START_HI  = 0xF844   # song start addr high
RAM_SEQ_END_LO    = 0xF845   # song end addr low (addr of $FF marker)
RAM_SEQ_END_HI    = 0xF846   # song end addr high
RAM_SEQ_TICK_CNT  = 0xF847   # tempo counter (decrements each IRQ)
RAM_SEQ_TICK_RATE = 0xF848   # tempo reload value
RAM_SEQ_FM_PATCH0 = 0xF849   # current sequencer FM patch ch0
RAM_SEQ_FM_PATCH1 = 0xF84A   # current sequencer FM patch ch1
RAM_SEQ_FM_PATCH2 = 0xF84B   # current sequencer FM patch ch2
RAM_SEQ_FM_PATCH3 = 0xF84C   # current sequencer FM patch ch3

# SSG preset/envelope RAM — 4 bytes per channel * 3 channels = 12 bytes
# Layout per channel (ch 0-2): preset_idx, cur_vol, decay_counter, active
RAM_SSG_PRESET    = 0xF850   # +ch*4: preset index (0-4)
                              # +ch*4+1: current volume (0-15)
                              # +ch*4+2: decay frame counter
                              # +ch*4+3: active flag (1=playing, 0=idle)

# Data table addresses (in ROM) - placed at $2000+ to avoid code conflicts
# Sample table: 325 entries * 4 bytes = 1300 bytes (0x2000-0x2514)
SAMPLE_TABLE   = 0x2000
FM_FNUM_TABLE  = 0x2E00
SSG_PERIOD_TABLE = 0x2E20
FM_PATCH_TABLE = 0x2E40
PATCH_SIZE = 26  # 6 params * 4 ops + FB_ALG + LR_AMS_PMS
SSG_PRESET_TABLE = 0x3060    # SSG presets: 3 bytes each (vol, decay, noise)
SONG_TABLE     = 0x3100      # song table: 5 bytes per song (moved forward for 20 FM patches)
SONG_DATA_BASE = 0x3200      # song data starts here

# Song data format:
# 8 bytes per row: [FM1] [FM2] [FM3] [FM4] [SSG1] [SSG2] [SSG3] [ADPCM_A_TRIG]
# Values: $00=sustain, $01=key-off, $02-$7F=note-on, $80-$BF=set-patch, $FF=end-of-song
SEQ_COLS = 8
SEQ_SUSTAIN = 0x00
SEQ_KEYOFF  = 0x01
SEQ_END     = 0xFF


class Asm:
    """Minimal Z80 assembler with helper methods for common instructions."""
    def __init__(self):
        self.code = bytearray(0x20000)
        self.pc = 0

    def org(self, addr):
        self.pc = addr

    def db(self, *bs):
        for b in bs:
            self.code[self.pc] = b & 0xFF
            self.pc += 1

    def dw(self, val):
        self.db(val & 0xFF, (val >> 8) & 0xFF)

    def here(self):
        return self.pc

    def patch_jr(self, jr_addr, target):
        offset = target - (jr_addr + 2)
        if offset < -128 or offset > 127:
            raise ValueError(f"JR offset {offset} out of range at 0x{jr_addr:04X} -> 0x{target:04X}")
        self.code[jr_addr + 1] = (offset & 0xFF)

    def patch_jp(self, jp_addr, target):
        self.code[jp_addr + 1] = target & 0xFF
        self.code[jp_addr + 2] = (target >> 8) & 0xFF

    # Emit JP nn, return address for patching
    def jp_ph(self):
        addr = self.pc; self.db(0xC3, 0x00, 0x00); return addr
    # Emit JR cc placeholders
    def jr_z_ph(self):
        addr = self.pc; self.db(0x28, 0x00); return addr
    def jr_nz_ph(self):
        addr = self.pc; self.db(0x20, 0x00); return addr
    def jr_c_ph(self):
        addr = self.pc; self.db(0x38, 0x00); return addr
    def jr_nc_ph(self):
        addr = self.pc; self.db(0x30, 0x00); return addr
    def jr_ph(self):
        addr = self.pc; self.db(0x18, 0x00); return addr

    # === Instructions as raw bytes ===
    def nop(self):       self.db(0x00)
    def halt(self):      self.db(0x76)
    def di(self):        self.db(0xF3)
    def ei(self):        self.db(0xFB)
    def ret(self):       self.db(0xC9)
    def retn(self):      self.db(0xED, 0x45)
    def reti(self):      self.db(0xED, 0x4D)
    def im1(self):       self.db(0xED, 0x56)
    def push_af(self):   self.db(0xF5)
    def push_bc(self):   self.db(0xC5)
    def push_de(self):   self.db(0xD5)
    def push_hl(self):   self.db(0xE5)
    def pop_af(self):    self.db(0xF1)
    def pop_bc(self):    self.db(0xC1)
    def pop_de(self):    self.db(0xD1)
    def pop_hl(self):    self.db(0xE1)
    def xor_a(self):     self.db(0xAF)
    def or_a(self):      self.db(0xB7)
    def or_e(self):      self.db(0xB3)
    def or_l(self):      self.db(0xB5)
    def add_a_c(self):   self.db(0x81)
    def sub_d(self):     self.db(0x92)
    def rlca(self):      self.db(0x07)
    def inc_hl(self):    self.db(0x23)
    def inc_d(self):     self.db(0x14)
    def inc_a(self):     self.db(0x3C)
    def dec_d(self):     self.db(0x15)
    def add_hl_hl(self): self.db(0x29)
    def add_hl_de(self): self.db(0x19)
    def add_hl_bc(self): self.db(0x09)
    def srl_h(self):     self.db(0xCB, 0x3C)
    def rr_l(self):      self.db(0xCB, 0x1D)

    # LD register moves
    def ld_a_b(self):    self.db(0x78)
    def ld_a_c(self):    self.db(0x79)
    def ld_a_d(self):    self.db(0x7A)
    def ld_a_e(self):    self.db(0x7B)
    def ld_a_h(self):    self.db(0x7C)
    def ld_a_l(self):    self.db(0x7D)
    def ld_a_hl(self):   self.db(0x7E)  # LD A,(HL)
    def ld_b_a(self):    self.db(0x47)
    def ld_c_a(self):    self.db(0x4F)
    def ld_d_a(self):    self.db(0x57)
    def ld_e_a(self):    self.db(0x5F)
    def ld_h_a(self):    self.db(0x67)
    def ld_l_a(self):    self.db(0x6F)
    def ld_e_hl(self):   self.db(0x5E)
    def ld_d_hl(self):   self.db(0x56)
    def ld_c_hl(self):   self.db(0x4E)
    def ld_b_hl(self):   self.db(0x46)
    def ld_hl_a(self):   self.db(0x77)  # LD (HL), A
    def ld_c_d(self):    self.db(0x4A)
    def ld_e_c(self):    self.db(0x59)
    def ld_c_e(self):    self.db(0x4B)
    def ld_h_d(self):    self.db(0x62)
    def ld_l_e(self):    self.db(0x6B)

    # LD immediate
    def ld_a_n(self, n):   self.db(0x3E, n & 0xFF)
    def ld_b_n(self, n):   self.db(0x06, n & 0xFF)
    def ld_c_n(self, n):   self.db(0x0E, n & 0xFF)
    def ld_d_n(self, n):   self.db(0x16, n & 0xFF)
    def ld_e_n(self, n):   self.db(0x1E, n & 0xFF)
    def ld_h_n(self, n):   self.db(0x26, n & 0xFF)
    def ld_l_n(self, n):   self.db(0x2E, n & 0xFF)
    def ld_sp_nn(self, nn): self.db(0x31, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_hl_nn(self, nn): self.db(0x21, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_de_nn(self, nn): self.db(0x11, nn & 0xFF, (nn >> 8) & 0xFF)
    def ld_bc_nn(self, nn): self.db(0x01, nn & 0xFF, (nn >> 8) & 0xFF)

    # LD memory
    def ld_mem_a(self, addr):  self.db(0x32, addr & 0xFF, (addr >> 8) & 0xFF)
    def ld_a_mem(self, addr):  self.db(0x3A, addr & 0xFF, (addr >> 8) & 0xFF)

    # ALU immediate
    def add_a_n(self, n):  self.db(0xC6, n & 0xFF)
    def sub_n(self, n):    self.db(0xD6, n & 0xFF)
    def cp_n(self, n):     self.db(0xFE, n & 0xFF)
    def and_n(self, n):    self.db(0xE6, n & 0xFF)
    def or_n(self, n):     self.db(0xF6, n & 0xFF)

    # I/O
    def out_n_a(self, port): self.db(0xD3, port & 0xFF)
    def in_a_n(self, port):  self.db(0xDB, port & 0xFF)
    # OUT (C), A = ED 79
    def out_c_a(self):       self.db(0xED, 0x79)

    # Additional register moves
    def ld_a_de(self):     self.db(0x1A)  # LD A,(DE)
    def ld_de_a(self):     self.db(0x12)  # LD (DE),A
    def ld_e_b(self):      self.db(0x58)
    def ld_b_c(self):      self.db(0x41)
    def ld_b_d(self):      self.db(0x42)
    def ld_b_e(self):      self.db(0x43)
    def ld_d_e(self):      self.db(0x53)
    def ld_d_b(self):      self.db(0x50)
    def ld_d_c(self):      self.db(0x51)
    def inc_de(self):      self.db(0x13)
    def inc_bc(self):      self.db(0x03)
    def inc_b(self):       self.db(0x04)
    def inc_c(self):       self.db(0x0C)
    def inc_e(self):       self.db(0x1C)
    def dec_a(self):       self.db(0x3D)
    def dec_b(self):       self.db(0x05)
    def dec_c(self):       self.db(0x0D)
    def dec_e(self):       self.db(0x1D)
    def add_a_a(self):     self.db(0x87)
    def add_a_e(self):     self.db(0x83)
    def add_a_l(self):     self.db(0x85)
    def add_a_d(self):     self.db(0x82)
    def or_b(self):        self.db(0xB0)
    def or_c(self):        self.db(0xB1)
    def or_d(self):        self.db(0xB2)
    def and_b(self):       self.db(0xA0)
    def and_c(self):       self.db(0xA1)
    def cp_b(self):        self.db(0xB8)
    def cp_c(self):        self.db(0xB9)
    def cp_d(self):        self.db(0xBA)
    def cp_e(self):        self.db(0xBB)
    def sub_b(self):       self.db(0x90)
    def sub_c(self):       self.db(0x91)
    def sub_e(self):       self.db(0x93)
    def ld_l_d(self):      self.db(0x6A)
    def ld_h_e(self):      self.db(0x63)
    def ld_h_b(self):      self.db(0x60)
    def ld_l_c(self):      self.db(0x69)
    def ld_b_l(self):      self.db(0x45)
    def ld_b_h(self):      self.db(0x44)
    def ld_c_b(self):      self.db(0x48)

    # Jumps and calls
    def jp(self, addr):    self.db(0xC3, addr & 0xFF, (addr >> 8) & 0xFF)
    def call(self, addr):  self.db(0xCD, addr & 0xFF, (addr >> 8) & 0xFF)

    # Patch a CALL instruction
    def patch_call(self, call_addr, target):
        self.code[call_addr + 1] = target & 0xFF
        self.code[call_addr + 2] = (target >> 8) & 0xFF


def build_test_songs():
    """Build test song data. Returns list of (song_bytes, tempo) tuples."""
    songs = []

    # Song 0: C major scale on FM1, bass on FM2, kick/snare on ADPCM-A
    # Each note = 2 rows (one 8th note at 120 BPM with 16th-note grid)
    song = []
    # Set FM1 to patch 2 (brass) and FM2 to patch 1 (organ) at the start
    song.append([0x82, 0x81, 0, 0, 0, 0, 0, 0])  # patch change row

    scale = [48, 50, 52, 53, 55, 57, 59, 60]  # C D E F G A B C (MIDI)
    for i, note in enumerate(scale):
        fm1 = note
        fm2 = 36 if i % 4 == 0 else SEQ_SUSTAIN  # C2 bass every 4 notes
        adpcm = 4 if i % 2 == 0 else 5           # kick(smp4)/snare(smp5) alternating
        song.append([fm1, fm2, 0, 0, 0, 0, 0, adpcm])
        song.append([SEQ_SUSTAIN, SEQ_SUSTAIN, 0, 0, 0, 0, 0, 0])  # sustain row

    # Descending back down
    for i, note in enumerate(reversed(scale[:-1])):
        fm1 = note
        fm2 = 36 if i % 4 == 0 else SEQ_SUSTAIN
        adpcm = 4 if i % 2 == 0 else 5
        song.append([fm1, fm2, 0, 0, 0, 0, 0, adpcm])
        song.append([SEQ_SUSTAIN, SEQ_SUSTAIN, 0, 0, 0, 0, 0, 0])

    # Key-off all, then end marker
    song.append([SEQ_KEYOFF, SEQ_KEYOFF, 0, 0, 0, 0, 0, 0])
    song.append([SEQ_END, 0, 0, 0, 0, 0, 0, 0])

    # Flatten to bytes
    song_bytes = bytearray()
    for row in song:
        for b in row:
            song_bytes.append(b & 0xFF)
    # Tempo: ~7 IRQs per tick at 55Hz IRQ rate = ~8 ticks/sec (120 BPM 16ths)
    songs.append((song_bytes, 7))

    # Song 1: Simple chord progression (FM chords + SSG melody)
    song = []
    # Set patches
    song.append([0x80, 0x80, 0x80, 0x80, 0, 0, 0, 0])  # all FM = simple

    # C major chord (C4, E4, G4) on FM1-3, melody on SSG1
    chords = [
        (48, 52, 55, 60),  # C major
        (48, 52, 55, 64),  # C major, melody E5
        (53, 57, 60, 65),  # F major, melody F5
        (53, 57, 60, 67),  # F major, melody G5
        (55, 59, 62, 67),  # G major, melody G5
        (55, 59, 62, 65),  # G major, melody F5
        (48, 52, 55, 64),  # C major, melody E5
        (48, 52, 55, 60),  # C major, melody C5
    ]
    for fm1, fm2, fm3, ssg1 in chords:
        song.append([fm1, fm2, fm3, 0, ssg1, 0, 0, 4])  # with kick
        for _ in range(3):
            song.append([0, 0, 0, 0, 0, 0, 0, 0])       # sustain 3 rows

    song.append([SEQ_KEYOFF, SEQ_KEYOFF, SEQ_KEYOFF, 0, SEQ_KEYOFF, 0, 0, 0])
    song.append([SEQ_END, 0, 0, 0, 0, 0, 0, 0])

    song_bytes = bytearray()
    for row in song:
        for b in row:
            song_bytes.append(b & 0xFF)
    songs.append((song_bytes, 7))

    # Song 2: Guile's Theme (Street Fighter 2) — C minor, 120 BPM
    songs.append(build_guile_theme())


    # Song 3: ADPCM-only drum beat (no FM to avoid stack bug)
    song = []
    S = SEQ_SUSTAIN
    # Pure ADPCM pattern — 4 bars, kick/snare/hihat
    # Samples: 1=kick, 3=snare, 5=hihat, 7=crash, 10=bass, 11=perc
    for bar in range(4):
        # Beat 1: kick + crash on bar 0
        song.append([S,S,S,S,S,S,S, 7 if bar==0 else 1])
        song.append([S,S,S,S,S,S,S, 5])
        # &
        song.append([S,S,S,S,S,S,S, 0])
        song.append([S,S,S,S,S,S,S, 5])
        # Beat 2: snare
        song.append([S,S,S,S,S,S,S, 3])
        song.append([S,S,S,S,S,S,S, 5])
        # &
        song.append([S,S,S,S,S,S,S, 0])
        song.append([S,S,S,S,S,S,S, 5])
        # Beat 3: kick
        song.append([S,S,S,S,S,S,S, 1])
        song.append([S,S,S,S,S,S,S, 5])
        # &
        song.append([S,S,S,S,S,S,S, 10])  # bass
        song.append([S,S,S,S,S,S,S, 5])
        # Beat 4: snare
        song.append([S,S,S,S,S,S,S, 3])
        song.append([S,S,S,S,S,S,S, 5])
        # & fill on last bar
        if bar == 3:
            song.append([S,S,S,S,S,S,S, 11])  # perc
            song.append([S,S,S,S,S,S,S, 11])
        else:
            song.append([S,S,S,S,S,S,S, 0])
            song.append([S,S,S,S,S,S,S, 5])
    song.append([0xFF,0,0,0,0,0,0,0])
    song_bytes = bytearray()
    for row in song:
        for b in row:
            song_bytes.append(b & 0xFF)
    songs.append((song_bytes, 7))

    return songs


def build_guile_theme():
    """Build Guile's Theme arranged for NeoSynth.

    Key: C minor.  Tempo: 120 BPM, 16th-note grid (8 ticks/sec).
    FM0 = lead melody (brass), FM1 = bass (organ),
    FM2 = chord voice 1 (piano), FM3 = chord voice 2 (piano).
    ADPCM-A = drums (kick/snare/hihat from KOF96 V-ROM).
    """
    # MIDI note constants
    C2, D2, Eb2, F2, G2, Ab2, Bb2 = 36, 38, 39, 41, 43, 44, 46
    C3, D3, Eb3, F3, G3, Ab3, Bb3 = 48, 50, 51, 53, 55, 56, 58
    C4, D4, Eb4, F4, G4, Ab4, Bb4 = 60, 62, 63, 65, 67, 68, 70
    C5 = 72
    # Bass octave (below C2)
    Ab1, Bb1 = 32, 34

    # Drum samples (ADPCM-A trigger values for sequencer column)
    KICK  = 4   # sample index in ADPCM_SAMPLES
    SNARE = 5
    HIHAT = 6

    # Patch set commands: $80+patch_id
    BRASS = 0x82   # FM patch 2
    ORGAN = 0x81   # FM patch 1
    PIANO = 0x83   # FM patch 3

    S = SEQ_SUSTAIN  # 0x00 = sustain
    OFF = SEQ_KEYOFF # 0x01 = key-off

    song = []

    def row(fm0=S, fm1=S, fm2=S, fm3=S, ssg0=S, ssg1=S, ssg2=S, adpcm=0):
        return [fm0, fm1, fm2, fm3, ssg0, ssg1, ssg2, adpcm]

    # --- Row 0: set patches ---
    song.append(row(BRASS, ORGAN, PIANO, PIANO))

    # Helper: standard drum pattern for a 16-row bar
    # Kick on beat 1,3 (rows 0,8), Snare on beat 2,4 (rows 4,12)
    # Hi-hat on every 8th note (every 2 rows)
    def drum(bar_pos):
        """Return ADPCM sample for position within a 16-row bar."""
        if bar_pos % 8 == 0:
            return KICK
        if bar_pos % 8 == 4:
            return SNARE
        if bar_pos % 2 == 0:
            return HIHAT
        return 0

    # ================================================================
    # INTRO — The iconic Eb-F-G stabs (bars 1-2)
    # ================================================================
    # Bar 1: Eb4(8th) F4(8th) G4(dotted quarter=6 rows) rest(4 rows)
    # Beat 1
    song.append(row(Eb3, C2, Eb3, G3, 0, 0, 0, KICK))     # row 0
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 1
    # Beat 1.5
    song.append(row(F3,  S,  S,   S,  0, 0, 0, 0))         # row 2
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 3
    # Beat 2 — G4 dotted quarter (6 rows)
    song.append(row(G3,  S,  S,   S,  0, 0, 0, SNARE))     # row 4
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 5
    song.append(row(S,   S,  S,   S,  0, 0, 0, 0))         # row 6
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 7
    # Beat 3 — G4 continues
    song.append(row(S,   S,  S,   S,  0, 0, 0, KICK))      # row 8
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 9
    # Beat 3.5 — rest
    song.append(row(OFF, S,  S,   S,  0, 0, 0, 0))         # row 10
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 11
    # Beat 4 — rest
    song.append(row(S,   S,  S,   S,  0, 0, 0, SNARE))     # row 12
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 13
    song.append(row(S,   S,  S,   S,  0, 0, 0, 0))         # row 14
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 15

    # Bar 2: Eb4(8th) F4(8th) Ab4(8th) G4(quarter=4) rest(8th) rest(quarter)
    # Beat 1
    song.append(row(Eb3, C2, Eb3, G3, 0, 0, 0, KICK))     # row 0
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 1
    # Beat 1.5
    song.append(row(F3,  S,  S,   S,  0, 0, 0, 0))         # row 2
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 3
    # Beat 2 — Ab4
    song.append(row(Ab3, S,  S,   S,  0, 0, 0, SNARE))     # row 4
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 5
    # Beat 2.5 — G4 quarter
    song.append(row(G3,  S,  S,   S,  0, 0, 0, 0))         # row 6
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 7
    # Beat 3 — G4 sustain
    song.append(row(S,   S,  S,   S,  0, 0, 0, KICK))      # row 8
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 9
    # Beat 3.5 — rest
    song.append(row(OFF, S,  OFF, OFF,0, 0, 0, 0))         # row 10
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 11
    # Beat 4 — rest
    song.append(row(S,   S,  S,   S,  0, 0, 0, SNARE))     # row 12
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 13
    song.append(row(S,   S,  S,   S,  0, 0, 0, 0))         # row 14
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))     # row 15

    # ================================================================
    # VERSE — Bars 3-4: Eb-F-G... Bb-Ab-G-F
    # ================================================================
    # Bar 3: Eb4(8th) F4(8th) G4(dotted quarter) rest(8th)
    # Same as Bar 1 pattern but with Ab bass chord
    song.append(row(Eb3, Ab1, Ab2, C3, 0, 0, 0, KICK))    # row 0
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 1
    song.append(row(F3,  S,   S,   S,  0, 0, 0, 0))       # row 2
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 3
    song.append(row(G3,  S,   S,   S,  0, 0, 0, SNARE))   # row 4
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 5
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 6
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 7
    song.append(row(S,   S,   S,   S,  0, 0, 0, KICK))    # row 8
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 9
    song.append(row(OFF, S,   S,   S,  0, 0, 0, 0))       # row 10
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 11
    song.append(row(S,   S,   S,   S,  0, 0, 0, SNARE))   # row 12
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 13
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 14
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 15

    # Bar 4: Bb4(8th) Ab4(8th) G4(8th) F4(quarter) rest(8th) rest
    song.append(row(Bb3, Bb1, Bb2, D3, 0, 0, 0, KICK))    # row 0
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 1
    song.append(row(Ab3, S,   S,   S,  0, 0, 0, 0))       # row 2
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 3
    song.append(row(G3,  S,   S,   S,  0, 0, 0, SNARE))   # row 4
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 5
    song.append(row(F3,  S,   S,   S,  0, 0, 0, 0))       # row 6
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 7
    song.append(row(S,   S,   S,   S,  0, 0, 0, KICK))    # row 8
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 9
    song.append(row(OFF, OFF, OFF, OFF,0, 0, 0, 0))       # row 10
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 11
    song.append(row(S,   S,   S,   S,  0, 0, 0, SNARE))   # row 12
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 13
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 14
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 15

    # ================================================================
    # VERSE — Bars 5-6: G-G-F-Bb... Ab-G-Ab...
    # ================================================================
    # Bar 5: G4(8th) G4(8th) F4(8th) Bb4(quarter+8th=6 rows)
    song.append(row(G3,  C2, Eb3, G3, 0, 0, 0, KICK))     # row 0
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 1
    song.append(row(G3,  S,  S,   S,  0, 0, 0, 0))        # row 2  re-trigger
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 3
    song.append(row(F3,  S,  S,   S,  0, 0, 0, SNARE))    # row 4
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 5
    song.append(row(Bb3, S,  S,   S,  0, 0, 0, 0))        # row 6
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 7
    song.append(row(S,   S,  S,   S,  0, 0, 0, KICK))     # row 8
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 9
    song.append(row(S,   S,  S,   S,  0, 0, 0, 0))        # row 10
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 11
    song.append(row(S,   S,  S,   S,  0, 0, 0, SNARE))    # row 12
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 13
    song.append(row(S,   S,  S,   S,  0, 0, 0, 0))        # row 14
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 15

    # Bar 6: Ab4(8th) G4(8th) Ab4(quarter+8th=6 rows) rest
    song.append(row(Ab3, Ab1, Ab2, C3, 0, 0, 0, KICK))    # row 0
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 1
    song.append(row(G3,  S,   S,   S,  0, 0, 0, 0))       # row 2
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 3
    song.append(row(Ab3, S,   S,   S,  0, 0, 0, SNARE))   # row 4
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 5
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 6
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 7
    song.append(row(S,   S,   S,   S,  0, 0, 0, KICK))    # row 8
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 9
    song.append(row(OFF, S,   S,   S,  0, 0, 0, 0))       # row 10
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 11
    song.append(row(S,   S,   S,   S,  0, 0, 0, SNARE))   # row 12
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 13
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 14
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 15

    # ================================================================
    # VERSE — Bars 7-8: D4... Eb4... F4... Bb3-D4-F4-Ab4(half)
    # ================================================================
    # Bar 7: D4(quarter+8th=6) Eb4(quarter+8th=6) F4(8th=2) fill(2)
    song.append(row(D3,  Bb1, Bb2, D3, 0, 0, 0, KICK))    # row 0
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 1
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 2
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 3
    song.append(row(S,   S,   S,   S,  0, 0, 0, SNARE))   # row 4
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 5
    song.append(row(Eb3, S,   S,   S,  0, 0, 0, 0))       # row 6
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 7
    song.append(row(S,   S,   S,   S,  0, 0, 0, KICK))    # row 8
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 9
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 10
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 11
    song.append(row(F3,  S,   S,   S,  0, 0, 0, SNARE))   # row 12
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 13
    song.append(row(S,   S,   S,   S,  0, 0, 0, 0))       # row 14
    song.append(row(S,   S,   S,   S,  0, 0, 0, HIHAT))   # row 15

    # Bar 8: Bb3(8th) D4(8th) F4(8th) Ab4(half=8 rows) rest(2)
    song.append(row(Bb2, C2, Eb3, G3, 0, 0, 0, KICK))     # row 0
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 1
    song.append(row(D3,  S,  S,   S,  0, 0, 0, 0))        # row 2
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 3
    song.append(row(F3,  S,  S,   S,  0, 0, 0, SNARE))    # row 4
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 5
    song.append(row(Ab3, S,  S,   S,  0, 0, 0, 0))        # row 6
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 7
    song.append(row(S,   S,  S,   S,  0, 0, 0, KICK))     # row 8
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 9
    song.append(row(S,   S,  S,   S,  0, 0, 0, 0))        # row 10
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 11
    song.append(row(S,   S,  S,   S,  0, 0, 0, SNARE))    # row 12
    song.append(row(S,   S,  S,   S,  0, 0, 0, HIHAT))    # row 13
    # Key off everything before loop
    song.append(row(OFF, OFF,OFF, OFF,0, 0, 0, 0))        # row 14
    song.append(row(S,   S,  S,   S,  0, 0, 0, 0))        # row 15

    # End marker (loops back to start)
    song.append([SEQ_END, 0, 0, 0, 0, 0, 0, 0])

    # Flatten to bytes
    song_bytes = bytearray()
    for r in song:
        for b in r:
            song_bytes.append(b & 0xFF)

    # Tempo: 7 = ~8 ticks/sec = 120 BPM at 16th note resolution
    return (song_bytes, 7)


def emit_ym_write_portB(a, reg, data_reg='a'):
    """Emit inline: set port B register to value in A."""
    # Assumes we have the register number and data to write.
    # reg is a constant. data_reg is where the value is.
    a.ld_a_n(reg)
    a.out_n_a(0x06)  # Port B addr
    if data_reg == 'e':
        a.ld_a_e()
    elif data_reg == 'b':
        a.ld_a_b()
    elif data_reg == 'c':
        a.ld_a_c()
    elif data_reg == 'd':
        a.ld_a_d()
    # else assume A already has the value
    a.out_n_a(0x07)  # Port B data


def build_driver(sample_table_path=None):
    a = Asm()

    # ================================================================
    # DATA TABLES
    # ================================================================
    # ADPCM-A sample table (4 bytes each: start_lo, start_hi, end_lo, end_hi)
    if sample_table_path and os.path.exists(sample_table_path):
        # Read external sample table (from wav_encoder.py output)
        with open(sample_table_path, 'rb') as f:
            table_data = f.read()
        sample_entries = []
        for i in range(0, len(table_data), 4):
            start, end = struct.unpack_from('<HH', table_data, i)
            sample_entries.append((start, end))
        print(f"  Using external sample table: {sample_table_path} ({len(sample_entries)} samples)")
    else:
        sample_entries = ADPCM_SAMPLES

    for i, (start, end) in enumerate(sample_entries):
        a.org(SAMPLE_TABLE + i * 4)
        a.db(start & 0xFF, (start >> 8) & 0xFF, end & 0xFF, (end >> 8) & 0xFF)

    # FM F-number table (12 entries, 2 bytes each, little-endian)
    a.org(FM_FNUM_TABLE)
    for fnum in FM_FNUMS:
        a.dw(fnum)

    # SSG period table for octave 4 (12 entries, 2 bytes each)
    a.org(SSG_PERIOD_TABLE)
    for period in SSG_PERIODS_OCT4:
        a.dw(period)

    # FM patch table (26 bytes each)
    a.org(FM_PATCH_TABLE)
    for patch in FM_PATCHES:
        for key in ['DT_MUL', 'TL', 'KS_AR', 'AM_DR', 'SR', 'SL_RR']:
            for op_i in range(4):
                a.db(patch[key][op_i])
        a.db(patch['FB_ALG'])
        a.db(patch['LR_AMS_PMS'])

    # SSG preset table (3 bytes each: volume, decay_rate, noise_enable)
    a.org(SSG_PRESET_TABLE)
    for vol, decay, noise in SSG_PRESETS:
        a.db(vol)
        a.db(decay)
        a.db(noise)

    # Signature
    a.org(0x0040)
    for b in b'NeoSynth v3.0':
        a.db(b)

    # FM key-on/off value tables
    # YM2610 FM channels: 1,2,4,5 (channels 0,3 are disabled for FM)
    # Key-on encoding: bits 4-7=operator mask, bits 0-1=ch within bank, bit 2=bank
    KEYON_TABLE = 0x0050
    a.org(KEYON_TABLE)
    a.db(0xF1, 0xF2, 0xF5, 0xF6)  # key-on: YM ch1,2,4,5
    KEYOFF_TABLE = 0x0054
    a.org(KEYOFF_TABLE)
    a.db(0x01, 0x02, 0x05, 0x06)  # key-off: YM ch1,2,4,5

    # ================================================================
    # SONG DATA
    # ================================================================
    test_songs = build_test_songs()
    num_songs = len(test_songs)

    # Song table at SONG_TABLE: 5 bytes per song
    # [start_lo, start_hi, length_lo, length_hi, tempo]
    song_data_addr = SONG_DATA_BASE
    a.org(SONG_TABLE)
    song_addrs = []
    for song_bytes, tempo in test_songs:
        song_addrs.append(song_data_addr)
        a.db(song_data_addr & 0xFF, (song_data_addr >> 8) & 0xFF)
        a.db(len(song_bytes) & 0xFF, (len(song_bytes) >> 8) & 0xFF)
        a.db(tempo)
        song_data_addr += len(song_bytes)

    # Write actual song data
    data_addr = SONG_DATA_BASE
    for song_bytes, tempo in test_songs:
        a.org(data_addr)
        for b in song_bytes:
            a.db(b)
        data_addr += len(song_bytes)

    # ================================================================
    # VECTORS
    # ================================================================
    a.org(0x0000)
    a.di()
    a.jp(0x0100)  # JP to init

    # IRQ at $0038: jump to sequencer tick handler
    a.org(0x0038)
    a.jp(0x0080)  # jump to IRQ handler (placed at $0080 for space)

    a.org(0x0066)  # NMI vector
    a.jp(0x0280)

    # ================================================================
    # IRQ HANDLER at $0080 — Timer A tick for sequencer
    # ================================================================
    a.org(0x0080)
    a.push_af()
    a.push_hl()
    a.push_de()
    a.push_bc()

    # Reset Timer A flag: reg $27 = $15 via Port A
    a.ld_a_n(0x27); a.out_n_a(0x04)
    a.ld_a_n(0x15); a.out_n_a(0x05)

    # Check if music is playing
    a.ld_a_mem(RAM_SEQ_PLAYING)
    a.or_a()
    jr_irq_not_playing = a.jr_z_ph()

    # Decrement tick counter
    a.ld_a_mem(RAM_SEQ_TICK_CNT)
    a.sub_n(1)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)
    jr_irq_no_tick = a.jr_nz_ph()

    # Counter reached 0: reload and call sequencer tick
    a.ld_a_mem(RAM_SEQ_TICK_RATE)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)
    # CALL sequencer tick subroutine (patched later)
    jp_seq_tick_call = a.here()
    a.call(0x0000)

    a.patch_jr(jr_irq_no_tick, a.here())
    a.patch_jr(jr_irq_not_playing, a.here())

    # CALL SSG envelope subroutine (patched later)
    jp_ssg_env_call = a.here()
    a.call(0x0000)

    # IRQ exit
    IRQ_DONE = a.here()
    a.pop_bc()
    a.pop_de()
    a.pop_hl()
    a.pop_af()
    a.ei()
    a.reti()

    # ================================================================
    # INIT at $0100
    # ================================================================
    a.org(0x0100)
    a.ld_sp_nn(0xFFFC)
    a.im1()

    # === YM2610 full hardware init (matches KOF96 reference) ===

    # FM key-off all 4 channels (reg $28 via Port A)
    # YM2610 FM channels: 1,2,4,5 (channels 0,3 disabled for FM)
    for ch_val in [0x01, 0x02, 0x05, 0x06]:
        a.ld_a_n(0x28); a.out_n_a(0x04)
        a.ld_a_n(ch_val); a.out_n_a(0x05)

    # SSG volumes to 0 (regs $08-$0A via Port A)
    for reg in [0x08, 0x09, 0x0A]:
        a.ld_a_n(reg); a.out_n_a(0x04)
        a.xor_a(); a.out_n_a(0x05)

    # SSG mixer: disable all tone + noise (reg $07 = $3F via Port A)
    a.ld_a_n(0x07); a.out_n_a(0x04)
    a.ld_a_n(0x3F); a.out_n_a(0x05)

    # ADPCM-A dump all channels (Port B reg $00 = $BF)
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0xBF); a.out_n_a(0x07)

    # ADPCM-A master volume: Port B reg $01 = $3F
    a.ld_a_n(0x01); a.out_n_a(0x06)
    a.ld_a_n(0x3F); a.out_n_a(0x07)

    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.xor_a(); a.out_n_a(0x05)

    a.ld_a_n(0x1C); a.out_n_a(0x04)
    a.ld_a_n(0x80); a.out_n_a(0x05)
    a.ld_a_n(0x1C); a.out_n_a(0x04)
    a.xor_a(); a.out_n_a(0x05)

    # Timer A + B flags reset (reg $27 = $30 via Port A)
    a.ld_a_n(0x27); a.out_n_a(0x04)
    a.ld_a_n(0x30); a.out_n_a(0x05)

    # Init RAM: FM pan = $C0 (center) for all 4 channels
    a.ld_a_n(0xC0)
    for i in range(4):
        a.ld_mem_a(RAM_FM_PAN + i)
    # ADPCM-A pan = $C0 for all 6 channels
    for i in range(6):
        a.ld_mem_a(RAM_ADPCMA_PAN + i)

    # Clear param and flags
    a.xor_a()
    a.ld_mem_a(RAM_ADPCMA_CH)
    a.ld_mem_a(RAM_PARAM)
    a.ld_mem_a(RAM_PARAM_FLAG)

    # Default SSG volumes
    a.ld_a_n(0x0F)
    for i in range(3):
        a.ld_mem_a(RAM_SSG_VOL + i)

    # Default FM patches (all ch = patch 0)
    a.xor_a()
    for i in range(4):
        a.ld_mem_a(RAM_FM_PATCH + i)

    # Init SSG preset RAM: preset=0 (SQUARE), vol=0, decay=0, active=0
    a.xor_a()
    for ch in range(3):
        base = RAM_SSG_PRESET + ch * 4
        a.ld_mem_a(base + 0)  # preset index = 0
        a.ld_mem_a(base + 1)  # current volume = 0
        a.ld_mem_a(base + 2)  # decay counter = 0
        a.ld_mem_a(base + 3)  # active = 0

    # Init sequencer RAM
    a.xor_a()
    a.ld_mem_a(RAM_SEQ_PLAYING)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)
    a.ld_a_n(7)  # default tempo
    a.ld_mem_a(RAM_SEQ_TICK_RATE)
    a.xor_a()
    for addr in [RAM_SEQ_ROW_LO, RAM_SEQ_ROW_HI,
                 RAM_SEQ_START_LO, RAM_SEQ_START_HI,
                 RAM_SEQ_END_LO, RAM_SEQ_END_HI,
                 RAM_SEQ_FM_PATCH0, RAM_SEQ_FM_PATCH1,
                 RAM_SEQ_FM_PATCH2, RAM_SEQ_FM_PATCH3]:
        a.ld_mem_a(addr)

    # Set up Timer A for IRQ (~55 Hz from KOF96 values)
    # reg $24 = Timer A lo 8 bits, reg $25 = Timer A hi 2 bits
    a.ld_a_n(0x24); a.out_n_a(0x04)
    a.ld_a_n(0xAC); a.out_n_a(0x05)
    a.ld_a_n(0x25); a.out_n_a(0x04)
    a.ld_a_n(0x03); a.out_n_a(0x05)
    # Enable Timer A: reg $27 = $15 (reset+load+enable Timer A)
    a.ld_a_n(0x27); a.out_n_a(0x04)
    a.ld_a_n(0x15); a.out_n_a(0x05)

    # Enable NMI
    a.ld_a_n(0x0F)  # just need any value
    a.out_n_a(0x08)
    a.ei()

    # Main loop
    MAIN_LOOP = a.here()
    a.halt()
    a.db(0x18, 0xFD)  # JR $-3 (back to HALT)

    # ================================================================
    # NMI HANDLER at $0280
    # ================================================================
    a.org(0x0280)
    a.push_af()
    a.push_hl()
    a.push_de()
    a.push_bc()

    a.in_a_n(0x00)       # read sound code
    a.out_n_a(0x0C)      # reply
    a.ld_mem_a(RAM_CMD)  # store

    # --- Check param flag first ---
    a.ld_a_mem(RAM_PARAM_FLAG)
    a.or_a()
    jr_no_param = a.jr_z_ph()
    # This byte IS the param value
    a.xor_a()
    a.ld_mem_a(RAM_PARAM_FLAG)
    a.ld_a_mem(RAM_CMD)
    a.ld_mem_a(RAM_PARAM)
    jp_done0 = a.jp_ph()
    a.patch_jr(jr_no_param, a.here())

    # --- Reload cmd and dispatch ---
    a.ld_a_mem(RAM_CMD)

    # $01: init/reset
    a.cp_n(0x01)
    jr_not_01 = a.jr_nz_ph()
    # We'll call stop_all subroutine (address TBD, use JP placeholder)
    jp_call_stop_reset = a.jp_ph()
    a.patch_jr(jr_not_01, a.here())

    # $03: stop all
    a.cp_n(0x03)
    jr_not_03 = a.jr_nz_ph()
    jp_call_stop_all = a.jp_ph()
    a.patch_jr(jr_not_03, a.here())

    # $08: set param flag
    a.cp_n(0x08)
    jr_not_08 = a.jr_nz_ph()
    a.ld_a_n(0x01)
    a.ld_mem_a(RAM_PARAM_FLAG)
    jp_done1 = a.jp_ph()
    a.patch_jr(jr_not_08, a.here())

    # $10-$1F: FM commands
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x10)
    jr_below_10 = a.jr_c_ph()
    a.cp_n(0x20)
    jr_above_1f = a.jr_nc_ph()
    jp_fm_dispatch = a.jp_ph()
    a.patch_jr(jr_below_10, a.here())
    a.patch_jr(jr_above_1f, a.here())

    # $20-$2F: SSG commands
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x20)
    jr_below_20 = a.jr_c_ph()
    a.cp_n(0x30)
    jr_above_2f = a.jr_nc_ph()
    jp_ssg_dispatch = a.jp_ph()
    a.patch_jr(jr_below_20, a.here())
    a.patch_jr(jr_above_2f, a.here())

    # $30-$3F: Pan commands
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x30)
    jr_below_30 = a.jr_c_ph()
    a.cp_n(0x40)
    jr_above_3f = a.jr_nc_ph()
    jp_pan_dispatch = a.jp_ph()
    a.patch_jr(jr_below_30, a.here())
    a.patch_jr(jr_above_3f, a.here())

    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x40)
    jr_not_40 = a.jr_nz_ph()
    jp_adpcmb_play = a.jp_ph()
    a.patch_jr(jr_not_40, a.here())

    a.cp_n(0x41)
    jr_not_41 = a.jr_nz_ph()
    jp_adpcmb_stop = a.jp_ph()
    a.patch_jr(jr_not_41, a.here())

    # $50-$5F: Play song N
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0x50)
    jr_below_50 = a.jr_c_ph()
    a.cp_n(0x60)
    jr_above_5f = a.jr_nc_ph()
    a.sub_n(0x50)
    a.ld_b_a()  # B = song index
    jp_play_song = a.jp_ph()
    a.patch_jr(jr_below_50, a.here())
    a.patch_jr(jr_above_5f, a.here())

    # $C0+: ADPCM-A trigger
    a.ld_a_mem(RAM_CMD)
    a.cp_n(0xC0)
    jr_below_c0 = a.jr_c_ph()
    a.sub_n(0xC0)
    jr_has_inline_smp = a.jr_nz_ph()  # if cmd > $C0, check $C1 vs inline
    # cmd == $C0: sample index from param (0-255)
    a.ld_a_mem(RAM_PARAM)
    a.ld_b_a()
    a.ld_c_n(0)  # C=0 = bank 0 (samples 0-255)
    jp_adpcma_trig = a.jp_ph()
    # cmd > $C0
    a.patch_jr(jr_has_inline_smp, a.here())
    a.cp_n(1)  # cmd - $C0 == 1? ($C1 = bank 1)
    jr_not_c1 = a.jr_nz_ph()
    # cmd == $C1: sample index from param + 256
    a.ld_a_mem(RAM_PARAM)
    a.ld_b_a()
    a.ld_c_n(1)  # C=1 = bank 1 (samples 256+)
    jp_adpcma_trig_b1 = a.jp_ph()
    # cmd > $C1: check $C2
    a.patch_jr(jr_not_c1, a.here())
    a.cp_n(2)  # $C2 = bank 2
    jr_not_c2 = a.jr_nz_ph()
    a.ld_a_mem(RAM_PARAM)
    a.ld_b_a()
    a.ld_c_n(2)
    jp_adpcma_trig_b2 = a.jp_ph()
    # cmd > $C2: check $C3
    a.patch_jr(jr_not_c2, a.here())
    a.cp_n(3)  # $C3 = bank 3
    jr_not_c3 = a.jr_nz_ph()
    a.ld_a_mem(RAM_PARAM)
    a.ld_b_a()
    a.ld_c_n(3)
    jp_adpcma_trig_b3 = a.jp_ph()
    # cmd > $C3: inline sample = cmd - $C0
    a.patch_jr(jr_not_c3, a.here())
    a.ld_b_a()
    a.ld_c_n(0)
    jp_adpcma_trig2 = a.jp_ph()
    a.patch_jr(jr_below_c0, a.here())

    # NMI done
    NMI_DONE = a.here()
    a.pop_bc()
    a.pop_de()
    a.pop_hl()
    a.pop_af()
    a.retn()

    # Collect all JP-to-done placeholders
    done_patches = [jp_done0, jp_done1]

    # ================================================================
    # SUBROUTINES - placed sequentially after NMI handler
    # ================================================================
    # Start subroutines at $0400 to have plenty of room
    a.org(0x0400)

    # ----------------------------------------------------------------
    # FM DISPATCH (cmd $10-$1F)
    # ----------------------------------------------------------------
    FM_DISPATCH = a.here()
    a.patch_jp(jp_fm_dispatch, FM_DISPATCH)

    a.ld_a_mem(RAM_CMD)
    a.sub_n(0x10)
    # 0-3: key-on, 4-7: key-off, 8-11: set patch
    a.cp_n(0x04)
    jr_not_fmon = a.jr_nc_ph()
    # FM key-on: A = channel (0-3)
    a.ld_b_a()
    jp_fmon = a.jp_ph()  # will patch to FM_KEY_ON
    a.patch_jr(jr_not_fmon, a.here())

    a.cp_n(0x08)
    jr_not_fmoff = a.jr_nc_ph()
    # FM key-off: A-4 = channel
    a.sub_n(0x04)
    a.ld_b_a()
    jp_fmoff = a.jp_ph()
    a.patch_jr(jr_not_fmoff, a.here())

    # FM set patch: A-8 = channel
    a.sub_n(0x08)
    a.ld_b_a()
    jp_fmpatch = a.jp_ph()

    # ----------------------------------------------------------------
    # SSG DISPATCH (cmd $20-$2F)
    # ----------------------------------------------------------------
    SSG_DISPATCH = a.here()
    a.patch_jp(jp_ssg_dispatch, SSG_DISPATCH)

    a.ld_a_mem(RAM_CMD)
    a.sub_n(0x20)
    a.cp_n(0x03)
    jr_not_ssgon = a.jr_nc_ph()
    a.ld_b_a()
    jp_ssgon = a.jp_ph()
    a.patch_jr(jr_not_ssgon, a.here())

    a.cp_n(0x07)
    jr_not_ssgoff = a.jr_nc_ph()
    a.sub_n(0x04)
    a.ld_b_a()
    jp_ssgoff = a.jp_ph()
    a.patch_jr(jr_not_ssgoff, a.here())

    # $28-$2A: SSG set patch (cmd - $20 = 0x08-0x0A, sub 0x08 = ch 0-2)
    a.cp_n(0x0B)
    jr_not_ssgpatch = a.jr_nc_ph()
    a.sub_n(0x08)
    a.ld_b_a()
    jp_ssgpatch = a.jp_ph()
    a.patch_jr(jr_not_ssgpatch, a.here())
    a.jp(NMI_DONE)

    # ----------------------------------------------------------------
    # PAN DISPATCH (cmd $30-$3F)
    # ----------------------------------------------------------------
    PAN_DISPATCH = a.here()
    a.patch_jp(jp_pan_dispatch, PAN_DISPATCH)

    a.ld_a_mem(RAM_CMD)
    a.sub_n(0x30)
    a.cp_n(0x04)
    jr_not_fmpan = a.jr_nc_ph()
    a.ld_b_a()
    jp_fmpan = a.jp_ph()
    a.patch_jr(jr_not_fmpan, a.here())

    a.sub_n(0x04)
    a.cp_n(0x06)
    jr_not_adpcmapan = a.jr_nc_ph()
    a.ld_b_a()
    jp_adpcmapan = a.jp_ph()
    a.patch_jr(jr_not_adpcmapan, a.here())
    a.jp(NMI_DONE)

    # ================================================================
    # STOP ALL (also stops sequencer)
    # ================================================================
    STOP_ALL = a.here()
    a.patch_jp(jp_call_stop_reset, STOP_ALL)
    a.patch_jp(jp_call_stop_all, STOP_ALL)

    # Stop sequencer
    a.xor_a()
    a.ld_mem_a(RAM_SEQ_PLAYING)

    # FM key-off all 4 channels (YM2610: ch 1,2,4,5)
    for val in [0x01, 0x02, 0x05, 0x06]:
        a.ld_a_n(0x28); a.out_n_a(0x04)
        a.ld_a_n(val);  a.out_n_a(0x05)

    # SSG silence: volumes to 0
    for reg in [0x08, 0x09, 0x0A]:
        a.ld_a_n(reg); a.out_n_a(0x04)
        a.xor_a();     a.out_n_a(0x05)

    # Clear SSG envelope active flags
    a.xor_a()
    for ch in range(3):
        a.ld_mem_a(RAM_SSG_PRESET + ch * 4 + 3)  # active = 0

    # ADPCM-A dump all: Port B reg $00 = $BF
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0xBF); a.out_n_a(0x07)

    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM KEY-ON (B = channel 0-3, note from RAM_PARAM)
    # ================================================================
    FM_KEY_ON = a.here()
    a.patch_jp(jp_fmon, FM_KEY_ON)

    # First load default patch for this channel
    a.push_bc()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.ld_a_hl()          # A = patch index for this channel
    a.ld_mem_a(RAM_TEMP)  # save patch index
    a.pop_bc()

    # --- Save channel to RAM_TEMP+2 ---
    a.ld_a_b()
    a.ld_mem_a(RAM_TEMP + 2)  # save channel number

    # --- Compute patch data pointer ---
    a.ld_a_mem(RAM_TEMP)
    a.cp_n(NUM_FM_PATCHES)
    jr_pok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_pok, a.here())

    # HL = FM_PATCH_TABLE + A * 26
    # 26 = 2 + 8 + 16  -> *2 + *8 + *16
    a.ld_c_a()           # C = patch index
    a.ld_b_n(0)
    a.ld_h_n(0); a.ld_l_a()  # HL = idx
    a.add_hl_hl()        # *2
    a.push_hl()          # save *2
    a.add_hl_hl()        # *4
    a.add_hl_hl()        # *8
    a.push_hl()          # save *8
    a.add_hl_hl()        # *16
    a.pop_de()           # DE = *8
    a.add_hl_de()        # HL = *24
    a.pop_de()           # DE = *2
    a.add_hl_de()        # HL = *26
    a.ld_de_nn(FM_PATCH_TABLE)
    a.add_hl_de()        # HL = patch data pointer

    # --- Restore channel into B ---
    a.ld_a_mem(RAM_TEMP + 2)
    a.ld_b_a()

    # --- Determine port and ch_offset from B ---
    # YM2610 FM uses channels 1,2,4,5 so offset = (ch & 1) + 1
    a.ld_a_b()
    a.and_n(0x01)
    a.inc_a()                 # offset 1 or 2 (not 0 or 1)
    a.ld_mem_a(RAM_TEMP + 1)  # ch_offset

    a.ld_a_b()
    a.and_n(0x02)
    jr_porta = a.jr_z_ph()
    # Port B: addr=$06, data=$07
    a.ld_c_n(0x06)
    a.ld_d_n(0x07)
    jr_port_done = a.jr_ph()
    a.patch_jr(jr_porta, a.here())
    a.ld_c_n(0x04)
    a.ld_d_n(0x05)
    a.patch_jr(jr_port_done, a.here())

    # --- Write all 24 operator registers ---
    # For each of 6 register groups, 4 operators
    # Reg groups: $30, $40, $50, $60, $70, $80
    # Op offsets: 0, 8, 4, 12
    for reg_base in [0x30, 0x40, 0x50, 0x60, 0x70, 0x80]:
        for op_off in [0, 8, 4, 12]:
            # Read data byte from (HL)
            a.ld_a_hl()       # A = data
            a.push_af()       # save data
            # Compute register: reg_base + op_off + ch_offset
            a.ld_a_mem(RAM_TEMP + 1)
            a.add_a_n(reg_base + op_off)
            # Write addr to port (C)
            a.out_c_a()       # OUT (C), A - sets register address
            # Write data to port (D) - swap C<->D temporarily
            a.pop_af()        # A = data
            a.ld_e_c()        # save C in E
            a.ld_c_d()        # C = data port
            a.out_c_a()       # OUT (C), A - write data
            a.ld_c_e()        # restore C = addr port
            a.inc_hl()        # next patch byte

    # --- Write FB_ALG: reg $B0 + ch_offset ---
    a.ld_a_hl()
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB0)
    a.out_c_a()
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()
    a.ld_c_e()
    a.inc_hl()

    # --- Write LR_AMS_PMS: reg $B4 + ch_offset, merged with panning ---
    a.ld_a_hl()
    a.and_n(0x3F)        # keep AMS/PMS
    a.ld_e_a()
    # Get pan from RAM
    a.ld_a_b()           # channel
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()          # pan value
    a.and_n(0xC0)
    a.or_e()             # merge
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB4)
    a.out_c_a()          # addr
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()          # data
    a.ld_c_e()

    # --- Set frequency ---
    # Get note from param, compute octave/semitone
    a.ld_a_mem(RAM_PARAM)
    a.ld_e_a()           # E = note
    a.ld_d_n(0)          # D = octave counter

    div12 = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_div_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)     # JR back to div12
    a.patch_jr(a.here() - 2, div12)
    a.patch_jr(jr_div_done, a.here())

    # D = octave (block), E = semitone
    # Lookup F-number
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()        # *2
    a.push_de()
    a.ld_de_nn(FM_FNUM_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()          # fnum_lo
    a.ld_e_a()
    a.inc_hl()
    a.ld_a_hl()          # fnum_hi (3 bits)
    a.ld_l_a()           # L = fnum_hi

    # Compute reg $A4 value: (block << 3) | fnum_hi
    a.ld_a_d()           # A = octave
    a.and_n(0x07)
    a.rlca(); a.rlca(); a.rlca()
    a.and_n(0x38)
    a.or_l()             # A = block_fnum_hi
    a.ld_d_a()           # D = block_fnum_hi

    # Write freq regs via correct port (C=addr port, from earlier)
    # But C/D were overwritten! We need to recompute port.
    a.ld_a_b()
    a.and_n(0x02)
    jr_freq_porta = a.jr_z_ph()
    # Port B
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA4)
    a.out_n_a(0x06)
    a.ld_a_d(); a.out_n_a(0x07)
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA0)
    a.out_n_a(0x06)
    a.ld_a_e(); a.out_n_a(0x07)
    jr_freq_done = a.jr_ph()

    a.patch_jr(jr_freq_porta, a.here())
    # Port A
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA4)
    a.out_n_a(0x04)
    a.ld_a_d(); a.out_n_a(0x05)
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xA0)
    a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.patch_jr(jr_freq_done, a.here())

    # --- Key-on via reg $28 (always port A) ---
    a.ld_a_b()           # channel
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(KEYON_TABLE)
    a.add_hl_de()
    a.ld_a_hl()          # key-on value
    a.ld_e_a()
    a.ld_a_n(0x28)
    a.out_n_a(0x04)
    a.ld_a_e()
    a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM KEY-OFF (B = channel 0-3)
    # ================================================================
    FM_KEY_OFF = a.here()
    a.patch_jp(jp_fmoff, FM_KEY_OFF)

    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(KEYOFF_TABLE)
    a.add_hl_de()
    a.ld_a_hl()
    a.ld_e_a()
    a.ld_a_n(0x28)
    a.out_n_a(0x04)
    a.ld_a_e()
    a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM LOAD PATCH (B = channel 0-3, patch from RAM_PARAM)
    # Just stores patch index in RAM for next key-on
    # ================================================================
    FM_LOAD_PATCH = a.here()
    a.patch_jp(jp_fmpatch, FM_LOAD_PATCH)

    a.ld_a_mem(RAM_PARAM)
    a.cp_n(NUM_FM_PATCHES)
    jr_lp_ok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_lp_ok, a.here())

    a.ld_e_a()           # E = patch index
    a.ld_a_b()           # channel
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.ld_a_mem(RAM_PARAM)
    a.cp_n(NUM_FM_PATCHES)
    jr_lp2 = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_lp2, a.here())
    a.ld_hl_a()

    a.jp(NMI_DONE)

    # ================================================================
    # SSG KEY-ON (B = channel 0-2, note from RAM_PARAM)
    # ================================================================
    SSG_KEY_ON = a.here()
    a.patch_jp(jp_ssgon, SSG_KEY_ON)

    # Compute octave and semitone from MIDI note
    a.ld_a_mem(RAM_PARAM)
    a.ld_e_a()
    a.ld_d_n(0)

    ssg_div = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_ssg_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)
    a.patch_jr(a.here() - 2, ssg_div)
    a.patch_jr(jr_ssg_done, a.here())

    # D = octave, E = semitone
    # Look up base period (octave 4)
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()
    a.push_de()
    a.ld_de_nn(SSG_PERIOD_TABLE)
    a.add_hl_de()
    a.pop_de()
    # HL -> period entry
    a.push_de()
    a.ld_e_hl()          # E = period_lo
    a.inc_hl()
    a.ld_d_hl()          # D = period_hi
    a.ld_h_d(); a.ld_l_e()  # HL = period
    a.pop_de()           # D = octave

    # Adjust period for octave
    a.ld_a_d()
    a.cp_n(4)
    jr_oct_eq = a.jr_z_ph()
    jr_oct_hi = a.jr_nc_ph()

    # Octave < 4: shift left (4-D) times
    a.ld_a_n(4)
    a.sub_d()
    a.ld_d_a()
    ssg_shl = a.here()
    a.add_hl_hl()
    a.dec_d()
    jr_shl_again = a.jr_nz_ph()
    a.patch_jr(jr_shl_again, ssg_shl)
    jr_ssg_adj_done = a.jr_ph()

    a.patch_jr(jr_oct_hi, a.here())
    # Octave > 4: shift right (D-4) times
    a.ld_a_d()
    a.sub_n(4)
    a.ld_d_a()
    ssg_shr = a.here()
    a.srl_h()
    a.rr_l()
    a.dec_d()
    jr_shr_again = a.jr_nz_ph()
    a.patch_jr(jr_shr_again, ssg_shr)

    a.patch_jr(jr_oct_eq, a.here())
    a.patch_jr(jr_ssg_adj_done, a.here())

    # HL = period. Write to SSG regs via Port A.
    # Tone period low: reg = B*2
    a.ld_a_b()
    a.add_a_n(0)         # A = channel
    a.db(0x87)           # ADD A, A = channel * 2
    a.ld_e_a()           # E = reg number
    a.out_n_a(0x04)      # reg addr
    a.ld_a_l()
    a.out_n_a(0x05)      # period low

    # Tone period high: reg = B*2 + 1
    a.ld_a_e()
    a.inc_a()
    a.out_n_a(0x04)
    a.ld_a_h()
    a.and_n(0x0F)
    a.out_n_a(0x05)

    # --- Look up preset for this channel ---
    # HL = SSG_PRESET_TABLE + preset_index * 3
    a.push_bc()                  # save B = channel
    a.push_hl()                  # save HL (period, not needed further)
    # Read preset index from RAM_SSG_PRESET + ch*4
    a.ld_a_b()
    a.add_a_a()                  # *2
    a.add_a_a()                  # *4
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_SSG_PRESET)
    a.add_hl_de()                # HL = &RAM_SSG_PRESET[ch*4]
    a.ld_a_hl()                  # A = preset index
    # Bounds check
    a.cp_n(NUM_SSG_PRESETS)
    jr_preset_ok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_preset_ok, a.here())
    # Compute ROM table pointer: SSG_PRESET_TABLE + A*3
    a.ld_e_a()                   # E = preset index
    a.ld_l_a(); a.ld_h_n(0)     # HL = idx
    a.add_hl_hl()                # HL = idx*2
    a.ld_d_n(0)
    a.add_hl_de()                # HL = idx*3
    a.ld_de_nn(SSG_PRESET_TABLE)
    a.add_hl_de()                # HL -> preset data (vol, decay, noise)
    # Read preset: C = initial_vol, D = decay_rate, E = noise_enable
    a.ld_c_hl(); a.inc_hl()      # C = initial_vol
    a.ld_d_hl(); a.inc_hl()      # D = decay_rate
    a.ld_e_hl()                  # E = noise_enable
    # Save initial_vol before POP BC overwrites C
    a.ld_a_c()
    a.ld_mem_a(RAM_TEMP)         # RAM_TEMP = initial_vol
    a.ld_a_d()
    a.ld_mem_a(RAM_TEMP + 1)     # RAM_TEMP+1 = decay_rate
    a.ld_a_e()
    a.ld_mem_a(RAM_TEMP + 2)     # RAM_TEMP+2 = noise_enable
    a.pop_hl()                   # discard saved HL (period)
    a.pop_bc()                   # restore B = channel
    a.ld_a_mem(RAM_TEMP + 2)
    a.ld_e_a()                   # E = noise_enable (restored)

    # --- Set mixer based on noise_enable ---
    # Read current mixer, modify bits for this channel
    # Tone enable: bit 0/1/2 for ch A/B/C (active LOW)
    # Noise enable: bit 3/4/5 for ch A/B/C (active LOW)
    a.push_de()                  # save D=decay, E=noise
    a.push_bc()                  # save B=channel, C=initial_vol
    # Build mixer value: start with all noise off ($38), all tone enabled ($00)
    # But we need to read-modify-write properly for the specific channel
    # Simple approach: tone always on for all, noise on only if preset says so
    a.ld_a_e()                   # A = noise_enable
    a.or_a()
    jr_no_noise = a.jr_z_ph()
    # Noise enabled: clear noise-disable bit for this channel
    # mixer = $38 & ~(1 << (3+ch)) = enable noise for this ch
    a.ld_a_b()                   # channel
    a.add_a_n(3)                 # bit position = 3+ch
    a.ld_e_a()                   # E = bit position
    a.ld_a_n(0x01)
    # Shift left by E positions
    a.ld_d_a()                   # D = mask being built
    a.ld_a_e()
    a.or_a()
    jr_shift_done_ssg = a.jr_z_ph()
    a.ld_a_d()
    ssg_noise_shift = a.here()
    a.rlca()
    a.dec_e()
    jr_noise_shift_again = a.jr_nz_ph()
    a.patch_jr(jr_noise_shift_again, ssg_noise_shift)
    a.patch_jr(jr_shift_done_ssg, a.here())
    # A = bit mask for noise (e.g., $08 for ch0, $10 for ch1, $20 for ch2)
    # Invert to clear that bit in $38
    a.ld_d_a()                   # D = noise bit
    a.ld_a_n(0x38)
    a.push_bc()
    a.ld_c_d()                   # C = noise bit to clear
    # XOR to flip the bit: $38 ^ noise_bit
    a.ld_a_n(0x38)
    a.ld_b_a()                   # save
    a.ld_a_c()
    a.db(0x2F)                   # CPL — complement A = ~noise_bit
    a.and_b()                    # $38 & ~noise_bit
    a.pop_bc()
    jr_mixer_set = a.jr_ph()

    a.patch_jr(jr_no_noise, a.here())
    # No noise: mixer = $38 (all noise off, all tone on)
    a.ld_a_n(0x38)
    a.patch_jr(jr_mixer_set, a.here())

    # Write mixer to reg $07
    a.ld_e_a()                   # save mixer value
    a.ld_a_n(0x07); a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)

    a.pop_bc()                   # restore B=channel, C=initial_vol
    a.pop_de()                   # restore D=decay_rate, E=noise_enable

    # --- Set initial volume from preset ---
    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.ld_a_mem(RAM_TEMP)         # A = initial_vol (from saved temp)
    a.and_n(0x0F)
    a.out_n_a(0x05)

    # --- Set up software envelope state ---
    # RAM_SSG_PRESET + ch*4 + 1 = current_vol
    # RAM_SSG_PRESET + ch*4 + 2 = decay_counter (init to decay_rate)
    # RAM_SSG_PRESET + ch*4 + 3 = active flag
    a.ld_a_b()                   # channel
    a.add_a_a()                  # *2
    a.add_a_a()                  # *4
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_SSG_PRESET)
    a.add_hl_de()
    a.pop_de()                   # HL = &RAM_SSG_PRESET[ch*4]
    a.inc_hl()                   # +1 = current_vol
    a.ld_a_mem(RAM_TEMP)         # A = initial_vol
    a.and_n(0x0F)
    a.ld_hl_a()                  # store current_vol = initial_vol
    a.inc_hl()                   # +2 = decay_counter
    a.ld_a_mem(RAM_TEMP + 1)     # decay_rate (saved to RAM_TEMP+1 earlier)
    a.ld_hl_a()                  # store decay_counter = decay_rate
    a.inc_hl()                   # +3 = active
    a.ld_a_n(0x01)
    a.ld_hl_a()                  # active = 1

    a.jp(NMI_DONE)

    # ================================================================
    # SSG KEY-OFF (B = channel 0-2)
    # ================================================================
    SSG_KEY_OFF = a.here()
    a.patch_jp(jp_ssgoff, SSG_KEY_OFF)

    # Set volume to 0
    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.xor_a()
    a.out_n_a(0x05)

    # Clear active flag in envelope state
    a.ld_a_b()
    a.add_a_a()                  # *2
    a.add_a_a()                  # *4
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_SSG_PRESET)
    a.add_hl_de()
    a.inc_hl(); a.inc_hl(); a.inc_hl()  # +3 = active
    a.xor_a()
    a.ld_hl_a()                  # active = 0

    a.jp(NMI_DONE)

    # ================================================================
    # SSG SET PATCH (B = channel 0-2, preset index from RAM_PARAM)
    # ================================================================
    SSG_SET_PATCH = a.here()
    a.patch_jp(jp_ssgpatch, SSG_SET_PATCH)

    # Read preset index from RAM_PARAM, bounds check
    a.ld_a_mem(RAM_PARAM)
    a.cp_n(NUM_SSG_PRESETS)
    jr_ssp_ok = a.jr_c_ph()
    a.xor_a()                    # default to 0 if out of range
    a.patch_jr(jr_ssp_ok, a.here())

    # Store at RAM_SSG_PRESET + ch*4 + 0
    a.ld_e_a()                   # E = preset index
    a.ld_a_b()                   # channel
    a.add_a_a()                  # *2
    a.add_a_a()                  # *4
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_SSG_PRESET)
    a.add_hl_de()                # HL = &RAM_SSG_PRESET[ch*4]
    a.ld_a_mem(RAM_PARAM)        # reload preset index
    a.cp_n(NUM_SSG_PRESETS)
    jr_ssp_ok2 = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_ssp_ok2, a.here())
    a.ld_hl_a()                  # store preset index

    a.jp(NMI_DONE)

    # ================================================================
    # ADPCM-A TRIGGER (B = sample index, channel from RAM_ADPCMA_CH)
    # ================================================================
    ADPCMA_TRIGGER = a.here()
    a.patch_jp(jp_adpcma_trig, ADPCMA_TRIGGER)
    a.patch_jp(jp_adpcma_trig_b1, ADPCMA_TRIGGER)
    a.patch_jp(jp_adpcma_trig_b2, ADPCMA_TRIGGER)
    a.patch_jp(jp_adpcma_trig_b3, ADPCMA_TRIGGER)
    a.patch_jp(jp_adpcma_trig2, ADPCMA_TRIGGER)

    # HL = SAMPLE_TABLE + (C*256 + B) * 4
    # C = bank (0 or 1), B = index within bank
    # LD L,B; LD H,C → HL = C*256 + B = full sample index
    a.db(0x68)  # LD L, B
    a.db(0x61)  # LD H, C
    # HL * 4 for table offset
    a.add_hl_hl(); a.add_hl_hl()
    a.ld_de_nn(SAMPLE_TABLE)
    a.add_hl_de()

    # Read: E=start_lo, D=start_hi, C=end_lo, B=end_hi
    a.ld_e_hl(); a.inc_hl()
    a.ld_d_hl(); a.inc_hl()
    a.ld_c_hl(); a.inc_hl()
    a.ld_b_hl()

    # Save addresses on stack
    a.push_bc()  # end addr
    a.push_de()  # start addr

    # Get channel (0-5)
    a.ld_a_mem(RAM_ADPCMA_CH)
    a.and_n(0x07)
    a.cp_n(6)
    jr_ch_ok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_ch_ok, a.here())
    a.ld_mem_a(RAM_TEMP)  # save channel

    # Compute channel bitmask: 1 << channel
    a.ld_e_a()
    a.ld_a_n(0x01)
    a.ld_d_a()            # default mask = 1
    a.ld_a_e()
    a.or_a()
    jr_no_shift = a.jr_z_ph()
    a.ld_d_a()            # D = shift count
    a.ld_a_n(0x01)
    shift_loop = a.here()
    a.rlca()
    a.dec_d()
    jr_shift = a.jr_nz_ph()
    a.patch_jr(jr_shift, shift_loop)
    jr_mask_done = a.jr_ph()
    a.patch_jr(jr_no_shift, a.here())
    a.ld_a_n(0x01)
    a.patch_jr(jr_mask_done, a.here())
    # A = channel mask
    a.ld_mem_a(RAM_TEMP + 1)  # save mask

    # Dump (stop) this channel: reg $00 = mask | $80
    a.or_n(0x80)
    a.ld_e_a()
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_e();     a.out_n_a(0x07)

    # Write start address
    a.ld_a_mem(RAM_TEMP)   # channel
    a.add_a_n(0x10)        # reg $10+ch = start_lo
    a.out_n_a(0x06)
    a.pop_de()             # DE = start addr (E=lo, D=hi)
    a.ld_a_e()
    a.out_n_a(0x07)

    a.ld_a_mem(RAM_TEMP)
    a.add_a_n(0x18)        # reg $18+ch = start_hi
    a.out_n_a(0x06)
    a.ld_a_d()
    a.out_n_a(0x07)

    # Write end address
    a.pop_bc()             # BC = end addr (C=lo, B=hi)
    a.ld_a_mem(RAM_TEMP)
    a.add_a_n(0x20)        # reg $20+ch = end_lo
    a.out_n_a(0x06)
    a.ld_a_c()
    a.out_n_a(0x07)

    a.ld_a_mem(RAM_TEMP)
    a.add_a_n(0x28)        # reg $28+ch = end_hi
    a.out_n_a(0x06)
    a.ld_a_b()
    a.out_n_a(0x07)

    # Volume + panning: reg $08+ch
    a.ld_a_mem(RAM_TEMP)   # channel
    a.add_a_n(0x08)
    a.out_n_a(0x06)
    # Get pan from RAM
    a.ld_a_mem(RAM_TEMP)
    a.ld_l_a(); a.ld_h_n(0)
    a.ld_de_nn(RAM_ADPCMA_PAN)
    a.add_hl_de()
    a.ld_a_hl()            # pan value ($C0, $80, $40)
    a.and_n(0xC0)
    a.or_n(0x1F)           # volume = 31
    a.out_n_a(0x07)

    # Trigger: reg $00 = mask (without $80)
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_mem(RAM_TEMP + 1)  # channel mask
    a.out_n_a(0x07)

    a.jp(NMI_DONE)

    # ================================================================
    # ================================================================
    ADPCMB_PLAY = a.here()
    a.patch_jp(jp_adpcmb_play, ADPCMB_PLAY)

    a.ld_a_mem(RAM_PARAM)
    a.cp_n(0xFF)  # bounds check handled by 68K side
    jr_ab_ok = a.jr_c_ph()
    a.jp(NMI_DONE)
    a.patch_jr(jr_ab_ok, a.here())

    ADPCMB_TABLE_OFFSET = SAMPLE_TABLE + 871 * 4
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl(); a.add_hl_hl()
    a.ld_de_nn(ADPCMB_TABLE_OFFSET)
    a.add_hl_de()

    a.ld_e_hl(); a.inc_hl()
    a.ld_d_hl(); a.inc_hl()
    a.ld_c_hl(); a.inc_hl()
    a.ld_b_hl()

    # Stop first
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)

    # L/R output
    a.ld_a_n(0x11); a.out_n_a(0x04)
    a.ld_a_n(0xC0); a.out_n_a(0x05)

    # Start addr
    a.ld_a_n(0x12); a.out_n_a(0x04)
    a.ld_a_e();     a.out_n_a(0x05)
    a.ld_a_n(0x13); a.out_n_a(0x04)
    a.ld_a_d();     a.out_n_a(0x05)

    # End addr
    a.ld_a_n(0x14); a.out_n_a(0x04)
    a.ld_a_c();     a.out_n_a(0x05)
    a.ld_a_n(0x15); a.out_n_a(0x04)
    a.ld_a_b();     a.out_n_a(0x05)

    # Delta-N: ~18.5kHz => $5555 (ADPCM-A native rate)
    a.ld_a_n(0x19); a.out_n_a(0x04)
    a.ld_a_n(0x55); a.out_n_a(0x05)
    a.ld_a_n(0x1A); a.out_n_a(0x04)
    a.ld_a_n(0x55); a.out_n_a(0x05)

    # Volume: $6D (matches KOF96)
    a.ld_a_n(0x1B); a.out_n_a(0x04)
    a.ld_a_n(0x6D); a.out_n_a(0x05)

    # Start playback
    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x80); a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # ================================================================
    ADPCMB_STOP = a.here()
    a.patch_jp(jp_adpcmb_stop, ADPCMB_STOP)

    a.ld_a_n(0x10); a.out_n_a(0x04)
    a.ld_a_n(0x01); a.out_n_a(0x05)

    a.jp(NMI_DONE)

    # ================================================================
    # FM SET PANNING (B = channel 0-3, param: 0=L, 1=C, 2=R)
    # ================================================================
    FM_SET_PAN = a.here()
    a.patch_jp(jp_fmpan, FM_SET_PAN)

    # Convert param to L/R bits
    a.ld_a_mem(RAM_PARAM)
    a.cp_n(0x00)
    jr_fn_l = a.jr_nz_ph()
    a.ld_a_n(0x80)          # L only
    jr_fp_set = a.jr_ph()
    a.patch_jr(jr_fn_l, a.here())
    a.cp_n(0x02)
    jr_fn_r = a.jr_nz_ph()
    a.ld_a_n(0x40)          # R only
    jr_fp_set2 = a.jr_ph()
    a.patch_jr(jr_fn_r, a.here())
    a.ld_a_n(0xC0)          # Center
    a.patch_jr(jr_fp_set, a.here())
    a.patch_jr(jr_fp_set2, a.here())

    # Store in RAM
    a.ld_e_a()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_e()
    a.ld_hl_a()

    # Write reg $B4+ch_offset via correct port
    # YM2610 FM uses channels 1,2,4,5 so offset = (ch & 1) + 1
    a.ld_a_b()
    a.and_n(0x01)
    a.inc_a()                # offset 1 or 2
    a.add_a_n(0xB4)
    a.ld_d_a()               # D = register

    a.ld_a_b()
    a.and_n(0x02)
    jr_fp_pa = a.jr_z_ph()
    # Port B
    a.ld_a_d(); a.out_n_a(0x06)
    a.ld_a_e(); a.out_n_a(0x07)
    jr_fp_pd = a.jr_ph()
    a.patch_jr(jr_fp_pa, a.here())
    # Port A
    a.ld_a_d(); a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.patch_jr(jr_fp_pd, a.here())

    a.jp(NMI_DONE)

    # ================================================================
    # ADPCM-A SET PANNING (B = channel 0-5, param: 0=L, 1=C, 2=R)
    # ================================================================
    ADPCMA_SET_PAN = a.here()
    a.patch_jp(jp_adpcmapan, ADPCMA_SET_PAN)

    a.ld_a_mem(RAM_PARAM)
    a.cp_n(0x00)
    jr_ap_l = a.jr_nz_ph()
    a.ld_a_n(0x80)
    jr_ap_set = a.jr_ph()
    a.patch_jr(jr_ap_l, a.here())
    a.cp_n(0x02)
    jr_ap_r = a.jr_nz_ph()
    a.ld_a_n(0x40)
    jr_ap_set2 = a.jr_ph()
    a.patch_jr(jr_ap_r, a.here())
    a.ld_a_n(0xC0)
    a.patch_jr(jr_ap_set, a.here())
    a.patch_jr(jr_ap_set2, a.here())

    # Store in RAM
    a.ld_e_a()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_ADPCMA_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_e()
    a.ld_hl_a()

    a.jp(NMI_DONE)

    # ================================================================
    # PLAY SONG (B = song index, called from NMI $50+N)
    # ================================================================
    PLAY_SONG = a.here()
    a.patch_jp(jp_play_song, PLAY_SONG)

    # Bounds check: B < num_songs
    a.ld_a_b()
    a.cp_n(num_songs)
    jr_song_ok = a.jr_c_ph()
    a.jp(NMI_DONE)
    a.patch_jr(jr_song_ok, a.here())

    # Look up song table: SONG_TABLE + B * 5
    # Compute B * 5 = B * 4 + B
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)  # HL = B
    a.add_hl_hl()             # HL = B*2
    a.add_hl_hl()             # HL = B*4
    a.ld_d_n(0); a.ld_e_b()
    a.add_hl_de()             # HL = B*5
    a.ld_de_nn(SONG_TABLE)
    a.add_hl_de()             # HL = SONG_TABLE + B*5

    # Read song entry: [start_lo, start_hi, length_lo, length_hi, tempo]
    # Read all 5 bytes into registers first
    a.ld_e_hl(); a.inc_hl()   # E = start_lo
    a.ld_d_hl(); a.inc_hl()   # D = start_hi
    a.ld_c_hl(); a.inc_hl()   # C = len_lo
    a.ld_b_hl(); a.inc_hl()   # B = len_hi
    a.ld_a_hl()               # A = tempo

    # Store tempo FIRST (before A gets clobbered)
    a.ld_mem_a(RAM_SEQ_TICK_RATE)
    a.ld_mem_a(RAM_SEQ_TICK_CNT)

    # Store start address
    a.ld_a_e(); a.ld_mem_a(RAM_SEQ_START_LO)
    a.ld_a_d(); a.ld_mem_a(RAM_SEQ_START_HI)
    a.ld_a_e(); a.ld_mem_a(RAM_SEQ_ROW_LO)
    a.ld_a_d(); a.ld_mem_a(RAM_SEQ_ROW_HI)

    # Compute end = start + length
    a.ld_h_d(); a.ld_l_e()    # HL = start
    a.add_hl_bc()             # HL = start + length = end
    a.ld_a_l(); a.ld_mem_a(RAM_SEQ_END_LO)
    a.ld_a_h(); a.ld_mem_a(RAM_SEQ_END_HI)

    # Clear sequencer patch state
    a.xor_a()
    a.ld_mem_a(RAM_SEQ_FM_PATCH0)
    a.ld_mem_a(RAM_SEQ_FM_PATCH1)
    a.ld_mem_a(RAM_SEQ_FM_PATCH2)
    a.ld_mem_a(RAM_SEQ_FM_PATCH3)

    # Set playing = 1
    a.ld_a_n(0x01)
    a.ld_mem_a(RAM_SEQ_PLAYING)

    a.jp(NMI_DONE)

    # ================================================================
    # SEQ_TICK: Advance one row of the sequencer
    # Called from IRQ handler. Uses AF, BC, DE, HL (all saved by caller).
    # Reads 8 bytes from current row pointer, processes each channel.
    # ================================================================
    SEQ_TICK = a.here()
    a.patch_call(jp_seq_tick_call, SEQ_TICK)

    # Load current row pointer into DE
    a.ld_a_mem(RAM_SEQ_ROW_LO)
    a.ld_e_a()
    a.ld_a_mem(RAM_SEQ_ROW_HI)
    a.ld_d_a()

    # Check first byte for end marker ($FF)
    a.ld_a_de()
    a.cp_n(SEQ_END)
    jr_not_end = a.jr_nz_ph()
    # End of song: loop back to start
    a.ld_a_mem(RAM_SEQ_START_LO)
    a.ld_mem_a(RAM_SEQ_ROW_LO)
    a.ld_e_a()
    a.ld_a_mem(RAM_SEQ_START_HI)
    a.ld_mem_a(RAM_SEQ_ROW_HI)
    a.ld_d_a()
    a.patch_jr(jr_not_end, a.here())

    # Now DE = current row pointer (valid data)
    # Process 8 columns: FM0-3 (cols 0-3), SSG0-2 (cols 4-6), ADPCM-A (col 7)

    # --- FM Channel 0 (col 0) ---
    a.ld_a_de()               # A = byte for FM ch0
    a.ld_b_n(0)               # B = FM channel 0
    a.push_de()
    a.call(0x0000)            # CALL SEQ_PROCESS_FM (patched below)
    jp_seq_fm_call_0 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- FM Channel 1 (col 1) ---
    a.ld_a_de()
    a.ld_b_n(1)
    a.push_de()
    a.call(0x0000)
    jp_seq_fm_call_1 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- FM Channel 2 (col 2) ---
    a.ld_a_de()
    a.ld_b_n(2)
    a.push_de()
    a.call(0x0000)
    jp_seq_fm_call_2 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- FM Channel 3 (col 3) ---
    a.ld_a_de()
    a.ld_b_n(3)
    a.push_de()
    a.call(0x0000)
    jp_seq_fm_call_3 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- SSG Channel 0 (col 4) ---
    a.ld_a_de()
    a.ld_b_n(0)
    a.push_de()
    a.call(0x0000)
    jp_seq_ssg_call_0 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- SSG Channel 1 (col 5) ---
    a.ld_a_de()
    a.ld_b_n(1)
    a.push_de()
    a.call(0x0000)
    jp_seq_ssg_call_1 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- SSG Channel 2 (col 6) ---
    a.ld_a_de()
    a.ld_b_n(2)
    a.push_de()
    a.call(0x0000)
    jp_seq_ssg_call_2 = a.pc - 3
    a.pop_de()
    a.inc_de()

    # --- ADPCM-A (col 7) ---
    a.ld_a_de()
    a.ld_b_a()                # B = sample index
    a.push_de()
    a.call(0x0000)
    jp_seq_adpcm_call = a.pc - 3
    a.pop_de()
    a.inc_de()

    # Update row pointer (DE now points to next row)
    a.ld_a_e(); a.ld_mem_a(RAM_SEQ_ROW_LO)
    a.ld_a_d(); a.ld_mem_a(RAM_SEQ_ROW_HI)

    a.ret()

    # ================================================================
    # SEQ_PROCESS_FM: Process one FM column byte
    # A = byte value, B = FM channel (0-3)
    # $00 = sustain, $01 = key-off, $02-$7F = note-on, $80-$BF = set patch
    # ================================================================
    SEQ_PROCESS_FM = a.here()
    for addr in [jp_seq_fm_call_0, jp_seq_fm_call_1,
                 jp_seq_fm_call_2, jp_seq_fm_call_3]:
        a.patch_call(addr, SEQ_PROCESS_FM)

    # Check for sustain ($00)
    a.or_a()
    jr_fm_not_sustain = a.jr_nz_ph()
    a.ret()
    a.patch_jr(jr_fm_not_sustain, a.here())

    # Check for key-off ($01)
    a.cp_n(SEQ_KEYOFF)
    jr_fm_not_keyoff = a.jr_nz_ph()
    # Key-off: look up keyoff table
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(KEYOFF_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()               # key-off value
    a.ld_e_a()
    a.ld_a_n(0x28); a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.ret()
    a.patch_jr(jr_fm_not_keyoff, a.here())

    # Check for set patch ($80-$BF)
    a.cp_n(0x80)
    jr_fm_not_patch = a.jr_c_ph()
    a.cp_n(0xC0)
    jr_fm_patch_too_high = a.jr_nc_ph()
    # Store patch: A & 0x3F = patch index
    a.and_n(0x3F)
    # Store in RAM_SEQ_FM_PATCHx (x = B)
    a.push_af()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_SEQ_FM_PATCH0)
    a.add_hl_de()
    a.pop_de()
    a.pop_af()
    a.ld_hl_a()               # store patch index
    # Also store in the main RAM_FM_PATCH for key-on to use
    a.push_af()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.pop_de()
    a.pop_af()
    a.ld_hl_a()
    a.ret()
    a.patch_jr(jr_fm_not_patch, a.here())
    a.patch_jr(jr_fm_patch_too_high, a.here())

    # Note-on ($02-$7F): A = MIDI note number
    # Full inline FM note-on with patch register write
    a.ld_mem_a(RAM_PARAM)     # store note

    # Save channel in RAM_TEMP+2
    a.ld_a_b()
    a.ld_mem_a(RAM_TEMP + 2)

    # --- Load patch for this channel ---
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PATCH)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()               # A = patch index
    a.ld_mem_a(RAM_TEMP)      # save patch index

    # Bounds check patch
    a.cp_n(NUM_FM_PATCHES)
    jr_seq_pok = a.jr_c_ph()
    a.xor_a()
    a.patch_jr(jr_seq_pok, a.here())

    # Compute patch pointer: HL = FM_PATCH_TABLE + A*26
    a.ld_c_a()
    a.ld_h_n(0); a.ld_l_a()
    a.add_hl_hl()             # *2
    a.push_hl()
    a.add_hl_hl()             # *4
    a.add_hl_hl()             # *8
    a.push_hl()
    a.add_hl_hl()             # *16
    a.pop_de()
    a.add_hl_de()             # *24
    a.pop_de()
    a.add_hl_de()             # *26
    a.ld_de_nn(FM_PATCH_TABLE)
    a.add_hl_de()             # HL = patch data pointer

    # Restore channel into B
    a.ld_a_mem(RAM_TEMP + 2)
    a.ld_b_a()

    # Determine port and ch_offset
    a.ld_a_b()
    a.and_n(0x01)
    a.inc_a()
    a.ld_mem_a(RAM_TEMP + 1)  # ch_offset

    a.ld_a_b()
    a.and_n(0x02)
    jr_seq_porta = a.jr_z_ph()
    a.ld_c_n(0x06)            # Port B addr
    a.ld_d_n(0x07)            # Port B data
    jr_seq_port_done = a.jr_ph()
    a.patch_jr(jr_seq_porta, a.here())
    a.ld_c_n(0x04)            # Port A addr
    a.ld_d_n(0x05)            # Port A data
    a.patch_jr(jr_seq_port_done, a.here())

    # Write 24 operator registers (same as FM_KEY_ON)
    for reg_base in [0x30, 0x40, 0x50, 0x60, 0x70, 0x80]:
        for op_off in [0, 8, 4, 12]:
            a.ld_a_hl()
            a.push_af()
            a.ld_a_mem(RAM_TEMP + 1)
            a.add_a_n(reg_base + op_off)
            a.out_c_a()
            a.pop_af()
            a.ld_e_c(); a.ld_c_d()
            a.out_c_a()
            a.ld_c_e()
            a.inc_hl()

    # Write FB_ALG
    a.ld_a_hl()
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB0)
    a.out_c_a()
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()
    a.ld_c_e()
    a.inc_hl()

    # Write LR_AMS_PMS with panning
    a.ld_a_hl()
    a.and_n(0x3F)
    a.ld_e_a()
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(RAM_FM_PAN)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()
    a.and_n(0xC0)
    a.or_e()
    a.push_af()
    a.ld_a_mem(RAM_TEMP + 1)
    a.add_a_n(0xB4)
    a.out_c_a()
    a.pop_af()
    a.ld_e_c(); a.ld_c_d()
    a.out_c_a()
    a.ld_c_e()

    # --- Set frequency ---
    a.ld_a_mem(RAM_PARAM)
    a.ld_e_a()
    a.ld_d_n(0)

    seq_fm_div12 = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_seq_fm_div_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)
    a.patch_jr(a.here() - 2, seq_fm_div12)
    a.patch_jr(jr_seq_fm_div_done, a.here())

    # D = octave, E = semitone. Look up F-number.
    a.push_de()
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()
    a.push_de()
    a.ld_de_nn(FM_FNUM_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_c_hl()               # C = fnum_lo
    a.inc_hl()
    a.ld_a_hl()               # A = fnum_hi
    a.ld_l_a()                # L = fnum_hi
    a.pop_de()                # D = octave

    # Compute block_fnum_hi
    a.ld_a_d()
    a.and_n(0x07)
    a.rlca(); a.rlca(); a.rlca()
    a.and_n(0x38)
    a.or_l()
    a.ld_d_a()                # D = block_fnum_hi
    a.ld_e_c()                # E = fnum_lo

    # Write freq regs
    a.ld_a_mem(RAM_TEMP + 1)  # ch_offset
    a.ld_c_a()

    a.ld_a_b()
    a.and_n(0x02)
    jr_seq_ffreq_pa = a.jr_z_ph()
    # Port B
    a.ld_a_c(); a.add_a_n(0xA4); a.out_n_a(0x06)
    a.ld_a_d(); a.out_n_a(0x07)
    a.ld_a_c(); a.add_a_n(0xA0); a.out_n_a(0x06)
    a.ld_a_e(); a.out_n_a(0x07)
    jr_seq_ffreq_done = a.jr_ph()
    a.patch_jr(jr_seq_ffreq_pa, a.here())
    # Port A
    a.ld_a_c(); a.add_a_n(0xA4); a.out_n_a(0x04)
    a.ld_a_d(); a.out_n_a(0x05)
    a.ld_a_c(); a.add_a_n(0xA0); a.out_n_a(0x04)
    a.ld_a_e(); a.out_n_a(0x05)
    a.patch_jr(jr_seq_ffreq_done, a.here())

    # Key-on
    a.ld_a_b()
    a.ld_l_a(); a.ld_h_n(0)
    a.push_de()
    a.ld_de_nn(KEYON_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.ld_a_hl()
    a.ld_c_a()
    a.ld_a_n(0x28); a.out_n_a(0x04)
    a.ld_a_c(); a.out_n_a(0x05)

    a.ret()

    # ================================================================
    # SEQ_PROCESS_SSG: Process one SSG column byte
    # A = byte value, B = SSG channel (0-2)
    # $00 = sustain, $01 = key-off, $02-$7F = note-on
    # ================================================================
    SEQ_PROCESS_SSG = a.here()
    for addr in [jp_seq_ssg_call_0, jp_seq_ssg_call_1, jp_seq_ssg_call_2]:
        a.patch_call(addr, SEQ_PROCESS_SSG)

    # Check sustain
    a.or_a()
    jr_ssg_not_sustain = a.jr_nz_ph()
    a.ret()
    a.patch_jr(jr_ssg_not_sustain, a.here())

    # Check key-off
    a.cp_n(SEQ_KEYOFF)
    jr_ssg_not_keyoff = a.jr_nz_ph()
    # Volume = 0
    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.xor_a()
    a.out_n_a(0x05)
    a.ret()
    a.patch_jr(jr_ssg_not_keyoff, a.here())

    # Note-on ($02-$7F): A = MIDI note
    # Compute period and write to SSG regs
    a.ld_mem_a(RAM_PARAM)
    a.ld_e_a()
    a.ld_d_n(0)

    seq_ssg_div = a.here()
    a.ld_a_e()
    a.cp_n(12)
    jr_seq_ssg_done = a.jr_c_ph()
    a.sub_n(12)
    a.ld_e_a()
    a.inc_d()
    a.db(0x18, 0x00)
    a.patch_jr(a.here() - 2, seq_ssg_div)
    a.patch_jr(jr_seq_ssg_done, a.here())

    # D = octave, E = semitone
    a.ld_a_e()
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl()
    a.push_de()
    a.ld_de_nn(SSG_PERIOD_TABLE)
    a.add_hl_de()
    a.pop_de()
    a.push_de()
    a.ld_e_hl(); a.inc_hl()
    a.ld_d_hl()
    a.ld_h_d(); a.ld_l_e()    # HL = period
    a.pop_de()                 # D = octave

    # Adjust period for octave
    a.ld_a_d()
    a.cp_n(4)
    jr_seq_oct_eq = a.jr_z_ph()
    jr_seq_oct_hi = a.jr_nc_ph()

    # Octave < 4: shift left
    a.ld_a_n(4)
    a.sub_d()
    a.ld_d_a()
    seq_ssg_shl = a.here()
    a.add_hl_hl()
    a.dec_d()
    jr_seq_shl = a.jr_nz_ph()
    a.patch_jr(jr_seq_shl, seq_ssg_shl)
    jr_seq_adj_done = a.jr_ph()

    a.patch_jr(jr_seq_oct_hi, a.here())
    # Octave > 4: shift right
    a.ld_a_d()
    a.sub_n(4)
    a.ld_d_a()
    seq_ssg_shr = a.here()
    a.srl_h()
    a.rr_l()
    a.dec_d()
    jr_seq_shr = a.jr_nz_ph()
    a.patch_jr(jr_seq_shr, seq_ssg_shr)

    a.patch_jr(jr_seq_oct_eq, a.here())
    a.patch_jr(jr_seq_adj_done, a.here())

    # HL = period, B = channel
    a.ld_a_b()
    a.add_a_a()               # A = channel * 2
    a.ld_e_a()
    a.out_n_a(0x04)
    a.ld_a_l()
    a.out_n_a(0x05)
    a.ld_a_e()
    a.inc_a()
    a.out_n_a(0x04)
    a.ld_a_h()
    a.and_n(0x0F)
    a.out_n_a(0x05)

    # Mixer: enable tone
    a.ld_a_n(0x07); a.out_n_a(0x04)
    a.ld_a_n(0x38); a.out_n_a(0x05)

    # Volume
    a.ld_a_b()
    a.add_a_n(0x08)
    a.out_n_a(0x04)
    a.ld_a_n(0x0F)
    a.out_n_a(0x05)

    a.ret()

    # ================================================================
    # SEQ_PROCESS_ADPCM: Process ADPCM-A column byte
    # B = sample byte (raw value from column)
    # $00 = no trigger, anything else = sample index to trigger
    # ================================================================
    SEQ_PROCESS_ADPCM = a.here()
    a.patch_call(jp_seq_adpcm_call, SEQ_PROCESS_ADPCM)

    # Check for no-trigger ($00)
    a.ld_a_b()
    a.or_a()
    jr_adpcm_not_zero = a.jr_nz_ph()
    a.ret()
    a.patch_jr(jr_adpcm_not_zero, a.here())

    # Check bounds
    a.cp_n(0xFF)  # bounds check handled by 68K side
    jr_adpcm_ok = a.jr_c_ph()
    a.ret()
    a.patch_jr(jr_adpcm_ok, a.here())

    # Trigger ADPCM-A sample B on channel 0 (sequencer always uses ch 0)
    # HL = sample table + B*4
    a.ld_l_a(); a.ld_h_n(0)
    a.add_hl_hl(); a.add_hl_hl()
    a.ld_de_nn(SAMPLE_TABLE)
    a.add_hl_de()

    a.ld_e_hl(); a.inc_hl()   # start_lo
    a.ld_d_hl(); a.inc_hl()   # start_hi
    a.ld_c_hl(); a.inc_hl()   # end_lo
    a.ld_b_hl()               # end_hi

    a.push_bc()               # save end addr
    a.push_de()               # save start addr

    # Dump ch0: reg $00 = $81
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0x81); a.out_n_a(0x07)

    # Start addr: regs $10+0, $18+0
    a.ld_a_n(0x10); a.out_n_a(0x06)
    a.pop_de()
    a.ld_a_e(); a.out_n_a(0x07)
    a.ld_a_n(0x18); a.out_n_a(0x06)
    a.ld_a_d(); a.out_n_a(0x07)

    # End addr: regs $20+0, $28+0
    a.pop_bc()
    a.ld_a_n(0x20); a.out_n_a(0x06)
    a.ld_a_c(); a.out_n_a(0x07)
    a.ld_a_n(0x28); a.out_n_a(0x06)
    a.ld_a_b(); a.out_n_a(0x07)

    # Volume + pan: reg $08+0 = $DF (center + vol 31)
    a.ld_a_n(0x08); a.out_n_a(0x06)
    a.ld_a_n(0xDF); a.out_n_a(0x07)

    # Trigger ch0: reg $00 = $01
    a.ld_a_n(0x00); a.out_n_a(0x06)
    a.ld_a_n(0x01); a.out_n_a(0x07)

    a.ret()

    # ================================================================
    # SSG_ENVELOPE: Software envelope tick for all 3 SSG channels
    # Called from IRQ handler every ~55Hz.
    # For each channel: if active and decay_rate > 0, decrement counter.
    # When counter hits 0: decrease volume, reload. Volume 0 = deactivate.
    # ================================================================
    SSG_ENVELOPE = a.here()
    a.patch_call(jp_ssg_env_call, SSG_ENVELOPE)

    for ch in range(3):
        base = RAM_SSG_PRESET + ch * 4
        # Check active flag
        a.ld_a_mem(base + 3)     # active?
        a.or_a()
        jr_ssg_env_skip = a.jr_z_ph()

        # Check if decay_counter > 0 (if decay_rate was 0, counter = 0 = sustained)
        a.ld_a_mem(base + 2)     # decay_counter
        a.or_a()
        jr_ssg_env_sustained = a.jr_z_ph()

        # Decrement counter
        a.dec_a()
        a.ld_mem_a(base + 2)
        jr_ssg_env_no_decay = a.jr_nz_ph()

        # Counter hit 0: decrease volume, reload counter
        a.ld_a_mem(base + 1)     # current_vol
        a.or_a()
        jr_ssg_env_vol_zero = a.jr_z_ph()
        a.dec_a()
        a.ld_mem_a(base + 1)     # store new volume

        # Write volume to SSG reg $08+ch
        a.ld_e_a()               # save volume
        a.ld_a_n(0x08 + ch)
        a.out_n_a(0x04)
        a.ld_a_e()
        a.out_n_a(0x05)

        # Reload counter from preset's decay_rate in ROM
        a.ld_a_mem(base + 0)     # preset index
        a.ld_l_a(); a.ld_h_n(0)
        a.add_hl_hl()            # *2
        a.ld_d_n(0); a.ld_e_a()
        a.add_hl_de()            # *3
        a.ld_de_nn(SSG_PRESET_TABLE + 1)  # +1 = decay_rate field
        a.add_hl_de()
        a.ld_a_hl()              # A = decay_rate
        a.ld_mem_a(base + 2)     # reload counter

        jr_ssg_env_done = a.jr_ph()

        # Volume reached 0: deactivate channel (silence)
        a.patch_jr(jr_ssg_env_vol_zero, a.here())
        a.ld_a_n(0x08 + ch)
        a.out_n_a(0x04)
        a.xor_a()
        a.out_n_a(0x05)
        # Clear active flag
        a.ld_mem_a(base + 3)

        a.patch_jr(jr_ssg_env_no_decay, a.here())
        a.patch_jr(jr_ssg_env_sustained, a.here())
        a.patch_jr(jr_ssg_env_skip, a.here())
        a.patch_jr(jr_ssg_env_done, a.here())

    a.ret()

    # ================================================================
    # Patch all done_patches
    # ================================================================
    for jp_addr in done_patches:
        a.patch_jp(jp_addr, NMI_DONE)

    # ================================================================
    # Summary
    # ================================================================
    print(f"NeoSynth v2.0 Driver Map:")
    print(f"  Init:          0x0100")
    print(f"  Main loop:     0x{MAIN_LOOP:04X}")
    print(f"  IRQ handler:   0x0080")
    print(f"  IRQ done:      0x{IRQ_DONE:04X}")
    print(f"  NMI handler:   0x0280")
    print(f"  NMI done:      0x{NMI_DONE:04X}")
    print(f"  Stop All:      0x{STOP_ALL:04X}")
    print(f"  Play Song:     0x{PLAY_SONG:04X}")
    print(f"  Seq Tick:      0x{SEQ_TICK:04X}")
    print(f"  Seq FM:        0x{SEQ_PROCESS_FM:04X}")
    print(f"  Seq SSG:       0x{SEQ_PROCESS_SSG:04X}")
    print(f"  Seq ADPCM:     0x{SEQ_PROCESS_ADPCM:04X}")
    print(f"  FM Key-On:     0x{FM_KEY_ON:04X}")
    print(f"  FM Key-Off:    0x{FM_KEY_OFF:04X}")
    print(f"  FM Load Patch: 0x{FM_LOAD_PATCH:04X}")
    print(f"  SSG Key-On:    0x{SSG_KEY_ON:04X}")
    print(f"  SSG Key-Off:   0x{SSG_KEY_OFF:04X}")
    print(f"  SSG Set Patch: 0x{SSG_SET_PATCH:04X}")
    print(f"  SSG Envelope:  0x{SSG_ENVELOPE:04X}")
    print(f"  ADPCM-A Trig:  0x{ADPCMA_TRIGGER:04X}")
    print(f"  FM Set Pan:    0x{FM_SET_PAN:04X}")
    print(f"  ADPCM-A Pan:   0x{ADPCMA_SET_PAN:04X}")
    print(f"  Sample table:  0x{SAMPLE_TABLE:04X} ({len(sample_entries)} entries)")
    print(f"  FM Fnum table: 0x{FM_FNUM_TABLE:04X}")
    print(f"  SSG Period tbl:0x{SSG_PERIOD_TABLE:04X}")
    print(f"  FM Patch table:0x{FM_PATCH_TABLE:04X} ({NUM_FM_PATCHES} patches)")
    print(f"  SSG Presets:   0x{SSG_PRESET_TABLE:04X} ({NUM_SSG_PRESETS} presets)")
    print(f"  Song table:    0x{SONG_TABLE:04X} ({num_songs} songs)")
    print(f"  Song data:     0x{SONG_DATA_BASE:04X}")
    print(f"  Code end:      0x{a.pc:04X}")

    return bytes(a.code)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-o', '--output', required=True)
    parser.add_argument('--sample-table', default=None,
                        help='External ADPCM-A sample table (sound_table.bin from wav_encoder)')
    args = parser.parse_args()
    mrom = build_driver(sample_table_path=args.sample_table)
    with open(args.output, 'wb') as f:
        f.write(mrom)
    print(f"Written: {args.output}")


if __name__ == '__main__':
    main()
