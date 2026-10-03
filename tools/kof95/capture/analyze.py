"""Read a record.lua capture and print, for one player, the per-state timeline of displayed frames and the movement.
python3 capture/analyze.py capture/terry_move.txt terry [player 1|2]"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import rom
from neogeo.sprite_decode import r32
import export

def load(path, player=1):
    """[(frame, p1 inputs, p2 inputs, object words of the chosen player)]"""
    rows = []
    for line in open(path):
        parts = line.split()
        if len(parts) == 6: parts = parts[:5]                 # record_spawn.lua: spawned objects in the last column
        if len(parts) == 4:                                   # old single-player format: n inp p1 p2
            n, i1, o1, o2 = parts; i2 = '-'
        else:
            n, i1, i2, o1, o2 = parts
        o = o1 if player == 1 else o2
        rows.append((int(n), i1, i2, [int(o[k:k + 4], 16) for k in range(0, len(o), 4)]))
    return rows

def x_of(w): return w[0x18 // 2] + w[0x1A // 2] / 65536
def y_of(w):
    v = w[0x20 // 2]; v = v - 65536 if v >= 32768 else v
    return v + w[0x22 // 2] / 65536
def frame_of(w): return ((w[0x28 // 2] << 16) | w[0x28 // 2 + 1]) & 0xFFFFFF
def state_of(w): return w[0x72 // 2]
def facing_of(w): return w[0x30 // 2] & 1

def slot_index(prom, cid, nslots=256):
    """frame record address -> ['slot.index(ticks)'] for every animation slot of the character"""
    st = r32(prom, 0x080000 + cid * 4); where = {}
    for s in range(nslots):
        a = r32(prom, st + s * 4)
        if 0x080000 <= a < 0x200000:
            try: steps, _ = export.parse_anim(prom, a)
            except ValueError: continue
            for i, (d, f, fl, b) in enumerate(steps): where.setdefault(f, []).append(f'{s}.{i}({d}t)')
    return where

def runs(rows):
    """[(first frame, state, frame record, ticks, inputs)] with consecutive identical (state, record) merged"""
    out = []
    for n, i1, i2, w in rows:
        s, f = state_of(w), frame_of(w)
        if out and out[-1][1] == s and out[-1][2] == f: out[-1][3] += 1
        else: out.append([n, s, f, 1, f'{i1}/{i2}'])
    return out

if __name__ == '__main__':
    path, name = sys.argv[1], sys.argv[2]; player = int(sys.argv[3]) if len(sys.argv) > 3 else 1
    prom, _ = rom.load(); where = slot_index(prom, rom.CHARS[name]); rows = load(path, player)
    cur = None
    for n, s, f, k, inp in runs(rows):
        if s != cur: print(f'\nstate {s:3} (inputs {inp}, frame {n}):', end=''); cur = s
        print(f'  {f:06X}x{k}[{",".join(where.get(f, ["?"])[:2])}]', end='')
    print()
