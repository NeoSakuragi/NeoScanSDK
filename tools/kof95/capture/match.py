"""Match each captured frame's on-screen tiles to the KOF95 animation frame that produced them.
python3 capture/match.py terry capture/terry_vram.bin -> per game state: which (anim slot, frame index) is displayed."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import numpy as np, rom
from neogeo.sprite_decode import r32
from neogeo.animation import parse_animation, follow_fragment_chain
def sdef_tiles(sdef):
    tiles, code = [], sdef['base_tile']
    bits = 16 if any(b > 0xFF for b in sdef['bitmasks']) else 8
    for col in range(sdef['cols']):
        bm = sdef['bitmasks'][col] if col < len(sdef['bitmasks']) else (1 << bits) - 1
        for t in range(sdef['tiles_per_col']):
            if t >= bits or (bm >> (bits - 1 - t)) & 1: tiles.append(code); code += 1
    return tiles
def frame_table(prom, cid, nstates=250):
    st = r32(prom, 0x080000 + cid * 4); sd = r32(prom, 0x080080 + cid * 4); out = {}
    for s in range(nstates):
        a = r32(prom, st + s * 4)
        if not (0x080000 <= a < 0x200000): continue
        for i, (d, f, fl) in enumerate(parse_animation(prom, a)):
            ts = set()
            for _, _, sdef in follow_fragment_chain(prom, f, sd): ts |= set(sdef_tiles(sdef))
            if ts: out[(s, i)] = (frozenset(ts), d, f)
    return out
def load_capture(path):
    rec = 0x200 + 381 * 32 * 4
    raw = np.fromfile(path, dtype=np.uint8); n = len(raw) // rec; raw = raw[:n * rec].reshape(n, rec)
    obj = raw[:, :0x200].view('>u2'); w = raw[:, 0x200:].view('>u2').reshape(n, -1, 2)
    tiles = w[:, :, 0].astype(np.uint32) | (((w[:, :, 1].astype(np.uint32) >> 4) & 0xF) << 16)   # SCB1 attr bits 4-7 = tile bits 16-19
    return obj, tiles
if __name__ == '__main__':
    name, path = sys.argv[1], sys.argv[2]; cid = rom.CHARS[name]
    prom, _ = rom.load(); ft = frame_table(prom, cid)
    obj, tiles = load_capture(path)
    prev = None
    for n in range(len(obj)):
        on = set(tiles[n].tolist()) - {0}
        best = max(ft.items(), key=lambda kv: len(kv[1][0] & on) / len(kv[1][0]))
        (s, i), (ts, d, f) = best; score = len(ts & on) / len(ts)
        key = (int(obj[n][0x72 // 2]), s, i)
        if key != prev:
            print(f'frame {n + 1:4}  game state {key[0]:3}  -> anim slot {s:3} frame {i:2} ({d}t, frag {f:06X})  match {score:.2f}')
            prev = key
