#!/usr/bin/env python3
"""Where KOF95's Terry animations come from (/data/neogeo_dict/kof95/terry_provenance.md).

Decodes Terry's animations in KOF94 (id 15), KOF95 (id 15) and KOF96 (id 3) with the existing parsers (kof94/ids94,
kof95/export, kof96/rom96), renders every frame they use to a 4-bit index image (palette independent), and matches each
KOF95 frame against the others by C-ROM tile content (the 128 bytes of each 16x16 tile) and by composited pixels.
Fatal Fury Special has no decoder of ours: its tiles are matched against the whole FFS C ROM, and FFS frames are
assembled from the matching tile runs (see ffs_frames()).

    python3 terry_provenance.py table           -> per-animation provenance table (stdout + JSON)
    python3 terry_provenance.py sheets OUTDIR   -> one contact sheet per provenance category
"""
import hashlib, json, os, sys
from collections import Counter, defaultdict
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'kof94')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import numpy as np
import rom, export
import ids94, export94
import rom96
from neogeo.sprite_decode import r32, decode_tile

ROMS = {'kof94': '/data/roms/kof94.neo', 'kof95': '/data/roms/kof95.neo', 'kof96': '/data/roms/kof96.neo',
        'ffs': '/data/roms/fatfursp.neo'}
TERRY = {'kof94': 15, 'kof95': 15, 'kof96': 3}
OUT_JSON = '/data/tmp/terry95/provenance.json'

def tile_key(crom, code):
    """content hash of one tile (the C-ROM bytes are in the same interleaved layout in every .neo)"""
    return hashlib.md5(crom[code * 128:(code + 1) * 128]).hexdigest()[:16]

def canon(img):
    """palette-permutation-free form of an index image: colours renumbered in order of first appearance"""
    flat = img.ravel(); out = np.zeros_like(flat); m = {0: 0}
    for i, v in enumerate(flat):
        if v not in m: m[v] = len(m)
        out[i] = m[v]
    return out.reshape(img.shape)

def compose(crom, parts, cache):
    """parts [{'dx','dy','hflip','vflip','columns'}] -> (index image cropped to its pixels, (x0, y0) of the crop
    relative to the frame origin, tile codes used)"""
    boxes = []
    for p in parts:
        w, h = len(p['columns']) * 16, len(p['columns'][0]) * 16 if p['columns'] else 0
        boxes.append((p['dx'], p['dy'], w, h))
    if not boxes: return None, (0, 0), []
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    canvas = np.zeros((max(1, y1 - y0), max(1, x1 - x0)), np.uint8); tiles = []
    for p, (dx, dy, w, h) in zip(parts, boxes):
        a = np.zeros((h, w), np.uint8)
        for c, col in enumerate(p['columns']):
            for r, t in enumerate(col):
                if t is None: continue
                if t not in cache: cache[t] = decode_tile(crom, t)
                a[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = cache[t]; tiles.append(t)
        if p['hflip']: a = a[:, ::-1]
        if p['vflip']: a = a[::-1, :]
        sub = canvas[dy - y0:dy - y0 + h, dx - x0:dx - x0 + w]
        np.copyto(sub, a, where=a != 0)          # later parts drawn over earlier ones
    ys, xs = np.nonzero(canvas)
    if not len(ys): return canvas[:1, :1], (x0, y0), tiles
    return canvas[ys.min():ys.max() + 1, xs.min():xs.max() + 1], (x0 + xs.min(), y0 + ys.min()), tiles

class Game:
    """Terry's animations of one game: anims {slot: (addr, mode, [(ticks, frame key)])}, frames {key: dict}"""
    def __init__(self, name):
        self.name = name; self.anims = {}; self.frames = {}; self.cache = {}
        getattr(self, 'load_' + name)()
        for f in self.frames.values():
            f['hashes'] = [tile_key(self.crom, t) for t in f['tiles']]
            f['digest'] = hashlib.md5(f['img'].tobytes() + bytes(f['img'].shape)).hexdigest()[:16]
            f['cdigest'] = hashlib.md5(canon(f['img']).tobytes() + bytes(f['img'].shape)).hexdigest()[:16]

    def add(self, key, parts):
        if key in self.frames: return
        img, org, tiles = compose(self.crom, parts, self.cache)
        self.frames[key] = {'img': img, 'org': org, 'tiles': tiles, 'parts': len(parts)}

    def load_kof95(self):
        p, self.crom = rom.load(ROMS['kof95']); self.prom = p
        st, sd = r32(p, 0x080000 + 15 * 4), r32(p, 0x080080 + 15 * 4)
        for s in range(256):
            a = r32(p, st + s * 4); steps, mode = export.parse_anim(p, a)
            for t, rec, fl, bx in steps: self.add(rec, export.frame_parts(p, rec, sd))
            self.anims[s] = (a, mode, [(t, rec, fl) for t, rec, fl, bx in steps])

    def load_kof94(self):
        p, self.crom = rom.load(ROMS['kof94']); self.prom = p
        st, sd = r32(p, 0x080000 + 15 * 4), r32(p, 0x080080 + 15 * 4)
        for s in range(256):
            a = r32(p, st + s * 4)
            try: steps, mode = export94.parse_anim(p, a)
            except (ValueError, IndexError): continue
            ok = []
            for x in steps:
                try: self.add(x['rec'], ids94.frame_parts(p, x['rec'], sd)); ok.append((x['ticks'], x['rec'], x['flags'] & ~0x4000))   # export94 adds $4000 to active steps
                except (ValueError, IndexError, TypeError): pass
            self.anims[s] = (a, mode, ok)

    def load_kof96(self):
        p, self.crom = rom96.load(ROMS['kof96']); m = rom96.Mem(p, 'kof96'); self.prom = p
        for s in range(512):
            try: a = rom96.anim_addr(m, 3, s); steps, mode = rom96.parse_anim(m, a)
            except Exception: continue
            ok = []
            for t, idx, fl, bx, raw, dx in steps:
                try:
                    parts = []
                    for q in rom96.frame_parts(m, 3, idx):
                        d = rom96.sdef(m, 3, q['sdef'])
                        parts.append({'dx': q['dx'], 'dy': q['dy'], 'hflip': q['hflip'], 'vflip': q['vflip'], 'columns': d['cols']})
                    self.add(idx, parts); ok.append((t, idx, fl))
                except Exception: pass
            self.anims[s] = (a, mode, ok)

    # Fatal Fury Special (decoded 2026-10-06 from its code: animation $6574, display list $1B6C8, sprite writer $1BC42).
    # Object: +$5C character (Terry = 1), +$6A state; state -> animation id: word table $6994[char] (state*2);
    # animation id -> frame list $84BD4 + 4 * word $81800[id] (characters >= 18: $807BC / $80000);
    # step = [frame word: bits 0-10 frame index, bit 12 = last step (hold), bit 14 = last step (loop)][dims word:
    # columns-1 | rows-1]; durations: words at base + offset, ($69E4 + char*8) = (offset table [state], base).
    # Frames live in "sheets" pooled by size: sheet = byte $200000[(dims >> 8 & 31) * 16 + (dims & 255)];
    # tiles = long $25D4A0[sheet] + index * stride, stride = word $25D682[sheet], tile words column-major
    # (left column first, rows top-down, $00FF = blank), then at + word $25D680[sheet]: one palette byte and 2 bits
    # per tile (bit 7: tile code bit 16, bit 6: vertical flip). Frames face left like KOF's; no part chains, no offsets
    # in the frame itself (the anchor is the grid's bottom centre plus a per-frame offset elsewhere, not needed here).
    FFS_TERRY, FFS_STATES = 1, 289
    def ffs_u16(self, a): a = a - 0x100000 if a >= 0x200000 else a; return (self.prom[a] << 8) | self.prom[a + 1]
    def ffs_u32(self, a): return (self.ffs_u16(a) << 16) | self.ffs_u16(a + 2)
    def ffs_frame(self, dims, idx):
        u8 = lambda a: self.prom[a - 0x100000 if a >= 0x200000 else a]
        cols, rows = ((dims >> 8) & 31) + 1, (dims & 255) + 1
        sheet = u8(0x200000 + ((dims >> 8) & 31) * 16 + (dims & 255))
        ao, stride = self.ffs_u16(0x25D680 + sheet * 4), self.ffs_u16(0x25D682 + sheet * 4)
        t0 = self.ffs_u32(0x25D4A0 + sheet * 4) + idx * stride
        img = np.zeros((rows * 16, cols * 16), np.uint8); tiles = []
        for k in range(cols * rows):
            w = self.ffs_u16(t0 + 2 * k); fl = (u8(t0 + ao + 1 + k // 4) >> (6 - 2 * (k % 4))) & 3
            code = w | (0x10000 if fl & 2 else 0)
            if code == 0xFF: continue
            if code not in self.cache: self.cache[code] = decode_tile(self.crom, code)
            t = self.cache[code][::-1] if fl & 1 else self.cache[code]
            c, r = divmod(k, rows); img[r * 16:(r + 1) * 16, c * 16:(c + 1) * 16] = t; tiles.append(code)
        ys, xs = np.nonzero(img)
        if len(ys): img = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        return img, tiles, sheet

    def load_ffs(self):
        p, self.crom = rom.load(ROMS['ffs']); self.prom = p
        ch = self.FFS_TERRY
        st = self.ffs_u32(0x6994 + ch * 4); ti, tb = self.ffs_u32(0x69E4 + ch * 8), self.ffs_u32(0x69E4 + ch * 8 + 4)
        for s in range(self.FFS_STATES):
            an = self.ffs_u16(st + 2 * s)
            if an == 0: continue
            fl = 0x84BD4 + 4 * self.ffs_u16(0x81800 + an * 2); tl = tb + self.ffs_u16(ti + 2 * s); steps = []
            for k in range(64):
                fw, dw = self.ffs_u16(fl + 4 * k), self.ffs_u16(fl + 4 * k + 2)
                key = (dw & 0x1FFF, fw & 0x7FF)
                if key not in self.frames:
                    img, tiles, sheet = self.ffs_frame(dw & 0x1F1F, fw & 0x7FF)
                    self.frames[key] = {'img': img, 'org': (0, 0), 'tiles': tiles, 'parts': 1}
                steps.append((self.ffs_u16(tl + 2 * k), key, fw >> 12))
                if fw & 0x5000: break
            self.anims[s] = (an, 'loop' if steps[-1][2] & 4 else 'hold', steps)

def tile_index(g):
    """tile hash -> set of frame keys"""
    ix = defaultdict(set)
    for k, f in g.frames.items():
        for h in f['hashes']: ix[h].add(k)
    return ix

def best_match(f, g, ix, by_digest, by_cdigest):
    """KOF95 frame f vs game g -> (kind, key, shared tile fraction, pixel diff fraction)"""
    if f['digest'] in by_digest: return ('identical', by_digest[f['digest']], 1.0, 0.0)
    if f['cdigest'] in by_cdigest: return ('identical_recoloured', by_cdigest[f['cdigest']], None, 0.0)
    hs = set(f['hashes'])
    if not hs: return (None, None, 0.0, None)
    votes = Counter(k for h in hs for k in ix.get(h, ()))
    if not votes: return ('none', None, 0.0, None)
    k, n = votes.most_common(1)[0]
    return ('tiles', k, n / len(hs), pixdiff(f['img'], g.frames[k]['img']))

def pixdiff(a, b):
    """fraction of differing pixels over the union of the two crops, best of small alignments (crops anchored top-left
    and bottom-centre)"""
    best = 1.0
    H, W = max(a.shape[0], b.shape[0]) + 8, max(a.shape[1], b.shape[1]) + 8
    for anchor in ('tl', 'bc'):
        for oy in range(-2, 3):
            for ox in range(-2, 3):
                A = np.zeros((H, W), np.uint8); B = np.zeros((H, W), np.uint8)
                if anchor == 'tl':
                    A[4:4 + a.shape[0], 4:4 + a.shape[1]] = a
                    y, x = 4 + oy, 4 + ox
                else:
                    ya, xa = H - 4 - a.shape[0], (W - a.shape[1]) // 2
                    A[ya:ya + a.shape[0], xa:xa + a.shape[1]] = a
                    y, x = H - 4 - b.shape[0] + oy, (W - b.shape[1]) // 2 + ox
                if y < 0 or x < 0 or y + b.shape[0] > H or x + b.shape[1] > W: continue
                B[y:y + b.shape[0], x:x + b.shape[1]] = b
                union = np.count_nonzero((A != 0) | (B != 0))
                if union: best = min(best, np.count_nonzero(A != B) / union)
    return best

def place(img, H, W, y, x):
    c = np.zeros((H, W), np.uint8); c[y:y + img.shape[0], x:x + img.shape[1]] = img; return c

def compare(a, b, slack=16):
    """drawing distance between two cropped index images: the share of differing pixels over the union of both
    silhouettes, after the best alignment (crop corners / bottom centre, +-2 px) and the best colour mapping (each of a's
    colours -> b's colour it most often lands on: palette order may differ between games). b is tried mirrored too.
    -> (distance, mirrored) or (1.0, None) when the crops differ by more than `slack` px"""
    if abs(a.shape[0] - b.shape[0]) > slack or abs(a.shape[1] - b.shape[1]) > slack: return 1.0, None
    H, W = max(a.shape[0], b.shape[0]) + 6, max(a.shape[1], b.shape[1]) + 6
    A0 = place(a, H, W, 3, 3); best = (1.0, None)
    for mir in (False, True):
        bb = b[:, ::-1] if mir else b
        cands = []
        for ay, by in ((3, 3), (3 + a.shape[0] - bb.shape[0], None)):
            for ax in (3, 3 + a.shape[1] - bb.shape[1], 3 + (a.shape[1] - bb.shape[1]) // 2):
                for dy in (-2, -1, 0, 1, 2):
                    for dx in (-2, -1, 0, 1, 2):
                        y, x = (ay if by is None else by) + dy, ax + dx
                        if y < 0 or x < 0 or y + bb.shape[0] > H or x + bb.shape[1] > W: continue
                        B = place(bb, H, W, y, x)
                        inter = np.count_nonzero((A0 != 0) & (B != 0)); union = np.count_nonzero((A0 != 0) | (B != 0))
                        cands.append((-inter / union, y, x, B))
        cands.sort(key=lambda c: c[0])
        for _, y, x, B in cands[:3]:
            both = (A0 != 0) & (B != 0)
            lut = np.arange(16, dtype=np.uint8)
            if both.any():
                pairs = A0[both].astype(np.int32) * 16 + B[both]
                cnt = np.bincount(pairs, minlength=256).reshape(16, 16)
                for k in range(1, 16):
                    if cnt[k].any(): lut[k] = cnt[k].argmax()
            union = np.count_nonzero((A0 != 0) | (B != 0))
            d = np.count_nonzero(lut[A0] != B) / union
            if d < best[0]: best = (d, mir)
    return best

def match_all(g5, g, keys=None):
    """every KOF95 frame -> (kind, other key, distance, mirrored): 'exact' = same pixels and colour indices, else the
    nearest drawing by compare()"""
    by_digest = {f['digest']: k for k, f in g.frames.items()}
    out = {}
    for k, f in g5.frames.items():
        if keys is not None and k not in keys: continue
        if f['digest'] in by_digest: out[k] = ('exact', by_digest[f['digest']], 0.0, False); continue
        best = (1.0, None, None)
        for k2, f2 in g.frames.items():
            d, mir = compare(f['img'], f2['img'])
            if d < best[0]: best = (d, k2, mir)
        out[k] = ('nearest', best[1], best[0], best[2])
    return out

FFS_TERRY_PAL = [0, 0x7FEA, 0x6FC8, 0x5E92, 0x7B51, 0x4820, 0x7AFF, 0x18CD, 0x468C, 0x1469, 0x2F61, 0x4E11, 0x0B11, 0x5FF0,
                 0x7FFF, 0x4244]     # palette RAM 16 in a fight, P1 Terry (our emulator, PALDUMP 2026-10-06)

def body_palette(g):
    """the game's Terry body palette as RGB (every part drawn with it: accessories in other palettes come out in body
    colours, enough to recognise a drawing)"""
    from neogeo.sprite_decode import decode_color
    if g.name == 'kof95': words = rom.palettes(g.prom, 15)[0]
    elif g.name == 'kof94': words = export94.palettes(g.prom, 15)[0][0]
    elif g.name == 'kof96':
        import export96; words = export96.palettes(rom96.Mem(g.prom, 'kof96'), 3)[0][0]
    else: words = FFS_TERRY_PAL
    return np.array([(255, 255, 255)] + [decode_color(w)[:3] for w in words[1:]], np.uint8)

def strip(g, keys, pal=None, gap=4, h=None):
    """frames side by side, feet on one line -> RGB array"""
    pal = body_palette(g) if pal is None else pal
    imgs = [g.frames[k]['img'] for k in keys] or [np.zeros((1, 1), np.uint8)]
    H = h or max(i.shape[0] for i in imgs); W = sum(i.shape[1] + gap for i in imgs)
    out = np.zeros((H, W), np.uint8); x = 0
    for i in imgs:
        i = i[-H:]; out[H - i.shape[0]:, x:x + i.shape[1]] = i; x += i.shape[1] + gap
    return pal[out]

NAMES = {0: 'idle', 1: 'walk forward', 2: 'walk back', 3: 'prejump / land', 4: 'land (2)', 5: 'jump up rise', 6: 'jump up fall',
         7: 'jump forward rise', 8: 'jump forward fall', 9: 'jump back rise', 10: 'jump back fall', 11: 'crouch down',
         12: 'crouch up', 13: 'crouch', 14: 'turn', 15: 'crouch turn', 16: 'guard stand in', 17: 'guard stand',
         22: 'guard crouch in', 23: 'guard crouch', 34: 'C+D body toss', 35: 'C+D air', 54: 'hit stand light', 59: 'hit stand mid',
         60: 'hit stand heavy', 61: 'hit crouch light', 62: 'hit crouch heavy', 65: 'hit air', 66: 'blowback', 67: 'trip',
         74: 'knockdown fall', 78: 'down', 80: 'get-up', 81: 'dizzy', 102: 'taunt?', 103: 'Power Wave (A)', 104: 'Power Wave (C) / Power Geyser',
         105: 'Burning Knuckle A start', 106: 'Burning Knuckle C start', 107: 'Burning Knuckle flight', 108: 'Burning Knuckle A end',
         109: 'Burning Knuckle C end', 110: 'Rising Tackle A start', 111: 'Rising Tackle C start', 112: 'Rising Tackle spin',
         113: 'Rising Tackle top', 114: 'Rising Tackle land A', 115: 'Rising Tackle land C', 116: 'Crack Shoot start',
         117: 'Crack Shoot B', 118: 'Crack Shoot D', 119: 'Crack Shoot land', 120: 'Crack Shoot end B', 121: 'Crack Shoot end D',
         122: 'Power Dunk start B', 123: 'Power Dunk start D', 124: 'Power Dunk rise', 125: 'Power Dunk rise D',
         126: 'Power Dunk', 127: 'Power Dunk land', 128: 'Power Geyser effect a', 129: 'Power Geyser effect b',
         130: 'throw (forward C)', 131: 'Power Geyser effect', 145: 'Power Geyser?', 146: 'Power Geyser (full)',
         160: 'intro / win', 161: 'win pose', 162: 'win pose (cap throw)', 164: 'cap (effect)'}
for b, nm in enumerate('ABCD'):
    for j, v in enumerate(('close', 'far', 'jump', 'jump diagonal', 'crouch')): NAMES[82 + 5 * b + j] = f'{nm} {v}'

def slot_name(s):
    if s in NAMES: return NAMES[s]
    if s < 24: return 'movement / guard'
    if s < 54: return 'system (dash, rolls, poses)'
    if s < 82: return 'reaction'
    return 'own move / pose'

D94 = 0.10          # drawing distance below which a frame counts as a retouch of the other game's frame

def table(cache='/data/tmp/terry95/match.pkl'):
    """per distinct KOF95 animation: frames, the KOF94 animation in the same slot (frames + timing), the nearest KOF96
    drawings, the nearest FFS drawing -> list of rows"""
    import pickle
    G = {n: Game(n) for n in ('kof95', 'kof94', 'kof96', 'ffs')}
    g5 = G['kof95']
    if os.path.exists(cache): M = pickle.load(open(cache, 'rb'))
    else:
        M = {n: match_all(g5, G[n]) for n in ('kof94', 'kof96', 'ffs')}; pickle.dump(M, open(cache, 'wb'))
    rows, seen = [], {}
    for s in range(256):
        a, mode, steps = g5.anims[s]
        if a in seen: seen[a]['slots'].append(s); continue
        keys = [k for _, k, _ in steps]
        uniq = list(dict.fromkeys(keys))
        m4 = [M['kof94'][k] for k in uniq]; m6 = [M['kof96'][k] for k in uniq]; mf = [M['ffs'][k] for k in uniq]
        ex4 = sum(x[0] == 'exact' for x in m4); near4 = sum(x[0] != 'exact' and x[2] < D94 for x in m4)
        ex6 = sum(x[0] == 'exact' for x in m6); near6 = sum(x[0] != 'exact' and x[2] < D94 for x in m6)
        # the KOF94 animation: the same slot when it plays the same drawings in the same order, else any slot that
        # does, else the slot sharing most drawings
        seq95 = [g5.frames[k]['digest'] for k in keys]          # drawings compared by their pixels (a game may
        def seq(sl):                                              # hold the same drawing in two records)
            return [G['kof94'].frames[k]['digest'] for _, k, _ in G['kof94'].anims.get(sl, (None, None, []))[2]]
        s4 = s if seq(s) == seq95 else next((sl for sl in sorted(G['kof94'].anims) if seq(sl) == seq95), None)
        if s4 is None:
            ov = Counter({sl: len(set(seq(sl)) & set(seq95) - {None}) for sl in G['kof94'].anims})
            s4 = ov.most_common(1)[0][0] if ov and ov.most_common(1)[0][1] else None
        st4 = G['kof94'].anims[s4][2] if s4 is not None else []
        same_frames = seq95 == seq(s4) if s4 is not None else False
        same_ticks = [t for t, _, _ in steps] == [t for t, _, _ in st4]
        same_flags = [f for _, _, f in steps] == [f for _, _, f in st4]
        n = len(uniq)
        if ex4 == n:
            if same_frames and same_ticks: cat = 'from 94' if same_flags else 'from 94, flags changed'
            elif same_frames: cat = 'from 94, retimed'
            else: cat = 'from 94 drawings, new sequence'
        elif ex4 + near4 == n: cat = 'from 94, retouched'
        elif ex4 + near4 > 0: cat = 'modified from 94'
        else: cat = 'new in 95'
        k96 = 'all exact' if ex6 == n else 'retouched' if ex6 + near6 == n else 'partly' if ex6 + near6 else 'no'
        # KOF96 animation with most of these drawings, and its timing
        best96 = Counter()
        for x in m6:
            if x[2] < D94:
                for s6, (_, _, st6) in G['kof96'].anims.items():
                    if x[1] in [k for _, k, _ in st6]: best96[s6] += 1
        s96 = best96.most_common(1)[0][0] if best96 else None
        t96 = [t for t, _, _ in G['kof96'].anims[s96][2]] if s96 is not None else None
        rows.append({'slot': s, 'slots': [s], 'name': slot_name(s), 'addr': f'{a:06X}', 'mode': mode, 'steps': len(steps),
                     'frames': n, 'ticks': [t for t, _, _ in steps], 'flags': [f'{f:04X}' for _, _, f in steps],
                     'exact94': ex4, 'near94': near4, 'exact96': ex6, 'near96': near6,
                     'ffs_min': round(min(x[2] for x in mf), 3),
                     'kof94': {'slot': s4, 'frames_equal': same_frames, 'ticks_equal': same_ticks, 'flags_equal': same_flags,
                                         'ticks': [t for t, _, _ in st4], 'flags': [f'{f:04X}' for _, _, f in st4]},
                     'kof96_slot': s96, 'kof96_ticks': t96, 'category': cat, 'in96': k96,
                     'keys': uniq, 'm94': [[x[0], x[1], round(x[2], 3)] for x in m4], 'm96': [[x[0], x[1], round(x[2], 3)] for x in m6],
                     'mffs': [[x[0], list(x[1]) if x[1] else None, round(x[2], 3)] for x in mf]})
        seen[a] = rows[-1]
    return rows, G, M

CATS = ['new in 95', 'modified from 94', 'from 94, retouched', 'from 94 drawings, new sequence', 'from 94, retimed',
        'from 94, flags changed', 'from 94']

def label(img_rgb, text, scale=1):
    from PIL import Image, ImageDraw
    im = Image.fromarray(img_rgb); d = ImageDraw.Draw(im); d.text((1, 1), text, fill=(0, 0, 0)); return np.array(im)

def anim_block(row, G):
    """one animation: KOF95's distinct drawings on top, under each its nearest KOF94, KOF96 and FFS drawing with the
    distance (0 = same pixels; 'ex' = same pixels and colour indices) -> RGB array"""
    gap, cell_rows = 6, []
    games = [('kof95', None), ('kof94', 'm94'), ('kof96', 'm96'), ('ffs', 'mffs')]
    cols = []
    for j, k in enumerate(row['keys']):
        cells = []
        for gname, mk in games:
            g = G[gname]
            if mk is None: key, txt = k, f'95'
            else:
                kind, key, d = row[mk][j][:3]
                key = tuple(key) if isinstance(key, list) else key
                txt = ('ex' if kind == 'exact' else f'{d:.2f}') if key is not None else '-'
            if key is None or key not in g.frames: img = np.full((24, 24, 3), 255, np.uint8)
            else: img = body_palette(g)[g.frames[key]['img']]
            cells.append((img, txt))
        cols.append(cells)
    hs = [max(c[i][0].shape[0] for c in cols) + 12 for i in range(4)]
    ws = [max(c[i][0].shape[1] for i in range(4)) + gap for c in cols]
    H, W = sum(hs) + 14, max(sum(ws), 260) + 40
    out = np.full((H, W, 3), 255, np.uint8)
    x = 40
    for c, w in zip(cols, ws):
        y = 14
        for (img, txt), h in zip(c, hs):
            out[y + h - img.shape[0]:y + h, x:x + img.shape[1]] = img
            out[y:y + 12, x:x + w - gap] = label(np.full((12, w - gap, 3), 255, np.uint8), txt)
            y += h
        x += w
    y = 14
    for (gname, _), h in zip(games, hs):
        out[y + h // 2:y + h // 2 + 12, 0:38] = label(np.full((12, 38, 3), 255, np.uint8), {'kof95': 'KOF95', 'kof94': 'KOF94', 'kof96': 'KOF96', 'ffs': 'FFS'}[gname])
        out[y + h - 1, :] = 0
        y += h
    sl = ','.join(map(str, row['slots'][:4])) + ('...' if len(row['slots']) > 4 else '')
    k4 = row['kof94']
    t = f"slot {sl} {row['name']}: {row['category']} | in 96: {row['in96']} | ticks {row['ticks'][:12]}"
    if k4['slot'] is not None: t += f" | KOF94 slot {k4['slot']} ticks {k4['ticks'][:12]}"
    out[0:13, :] = label(np.full((13, W, 3), 255, np.uint8), t[:W // 6])
    out[-2:, :] = 0
    return out

def sheets(outdir, rows=None, G=None, per_page=10):
    from PIL import Image
    if rows is None: rows, G, _ = table()
    os.makedirs(outdir, exist_ok=True); written = []
    groups = [(c, [r for r in rows if r['category'] == c]) for c in CATS]
    groups.append(('kept in 96', [r for r in rows if r['in96'] in ('all exact', 'retouched') and r['category'] in ('new in 95', 'modified from 94')]))
    for cat, rs in groups:
        for p in range(0, len(rs), per_page):
            blocks = [anim_block(r, G) for r in rs[p:p + per_page]]
            W = max(b.shape[1] for b in blocks); H = sum(b.shape[0] for b in blocks)
            page = np.full((H, W, 3), 255, np.uint8); y = 0
            for b in blocks: page[y:y + b.shape[0], :b.shape[1]] = b; y += b.shape[0]
            name = os.path.join(outdir, cat.replace(' ', '_').replace(',', '') + f'_{p // per_page + 1}.png')
            Image.fromarray(page).save(name); written.append((name, len(blocks)))
    return written

def idle_walk_sheet(outdir, G):
    """the claim: idle and walk of the four games, whole animations in play order"""
    from PIL import Image
    spec = [('KOF95 idle (slot 0)', 'kof95', 0), ('KOF94 idle (slot 0)', 'kof94', 0), ('KOF96 idle', 'kof96', 0), ('FFS idle (state 3)', 'ffs', 3),
            ('KOF95 walk fwd (slot 1)', 'kof95', 1), ('KOF94 walk fwd (slot 1)', 'kof94', 1), ('KOF96 walk fwd', 'kof96', 1), ('FFS walk fwd (state 1)', 'ffs', 1),
            ('KOF95 walk back (slot 2)', 'kof95', 2), ('KOF94 walk back (slot 2)', 'kof94', 2), ('KOF96 walk back', 'kof96', 2), ('FFS walk back (state 2)', 'ffs', 2)]
    strips = []
    for lab, gname, s in spec:
        g = G[gname]; steps = g.anims[s][2]
        st = strip(g, [k for _, k, *_ in steps])
        strips.append(label(np.vstack([np.full((12, st.shape[1], 3), 255, np.uint8), st]), f"{lab}  ticks {[t for t, *_ in steps]}"))
    W = max(s.shape[1] for s in strips) + 8; H = sum(s.shape[0] + 6 for s in strips)
    page = np.full((H, max(W, 420), 3), 255, np.uint8); y = 0
    for s in strips: page[y:y + s.shape[0], :s.shape[1]] = s; y += s.shape[0] + 6
    path = os.path.join(outdir, 'idle_walk_all_games.png'); Image.fromarray(page).save(path); return path

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'table'
    rows, G, M = table()
    json.dump([{k: v for k, v in r.items() if k not in ('keys',)} | {'keys': [hex(k) for k in r['keys']]} for r in rows],
              open(OUT_JSON, 'w'), default=str)
    if cmd == 'sheets':
        out = sys.argv[2] if len(sys.argv) > 2 else '/data/tmp/terry95/out'
        for name, n in sheets(out, rows, G): print(name, n)
        print(idle_walk_sheet(out, G))
    else:
        print(Counter(r['category'] for r in rows)); print(Counter(r['in96'] for r in rows))
