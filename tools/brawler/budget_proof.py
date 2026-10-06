#!/usr/bin/env python3
"""TODO #170 / #158 sprite budget proof: sprites per scanline read from VRAM (SCB2-4) in our emulator's core (harness),
counted the way the LSPC does (geolith geo_lspc_sprcalc: sprites 1-381 in order, sticky chains, a sprite on a line when
the line falls in its height; the 97th and after are dropped): exactly with the probe core (a copy of geolith whose
geo_lspc_sprcalc keeps counting past the limit: per line the sprites on it and the ones dropped, retro_get_memory_data(106);
BRAWLER_CORE=/data/tmp/budget170/geolith/libretro/geolith_libretro.so), else from the VRAM after the frame, plus the game's own line guard (main.c line_guard:
guard_hidden, hidden[]). Per frame: the worst line's count, the lines past 96, the actors whose sprites the LSPC dropped
and the actors the guard hid for the budget = what blinks.

Cases: the select screen (every boss unlocked: 22 actors, 60 frames), Geese's Raging Storm (fury D and MAX down+D) with
6 enemies crowding him, Kuroko's and Genjuro's furies the same way.

    python3 budget_proof.py GAME_DIR OUT TAG        one build: OUT/TAG.json + OUT/TAG_*.png sheets (one core per process)
    python3 budget_proof.py report OUT              OUT/budget.txt: before (TAG base) / after (TAG new) per case"""
import ctypes as C, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)

LIMIT = 96
VIS = range(16, 240)                           # LSPC lines of the 224 visible ones (screen y = line - 16)

def roster_names(game):
    return [c['name'] for c in json.load(open(os.path.join(game, 'game.json')))['roster']]

class Probe:
    def __init__(self, b, game):
        self.b = b; S = b.syms; self.S = S
        n = b.core.retro_get_memory_size(3)
        self.vram = (C.c_uint16 * (n // 2)).from_address(b.core.retro_get_memory_data(3))
        self.names = roster_names(game)
        a = b.core.retro_get_memory_data(106)          # the probe core's per-line LSPC stats (see the module doc)
        self.stat = (C.c_uint16 * (264 * 34)).from_address(a) if a else None
        self.NPJ = 8
    def u8(self, n, k=0): return self.b.r(self.S[n] + k, 1)
    def u16(self, n, k=0): return self.b.r(self.S[n] + 2 * k, 2)
    def u32(self, n, k=0): return self.b.r(self.S[n] + 4 * k, 4)
    def entity(self, p):
        """a fighter_t pointer -> (label, i, base)"""
        b, fs = self.b, self.b.fsize
        if self.S['fighters'] <= p < self.S['fighters'] + 8 * fs: i = (p - self.S['fighters']) // fs; kind = 'F'
        elif self.S['projectiles'] <= p < self.S['projectiles'] + self.NPJ * fs: i = (p - self.S['projectiles']) // fs; kind = 'PJ'
        else:                                       # the select screen's actors (actor(a): fighters, projectiles, then more)
            kind = 'A'; i = p
        return kind, i
    def field(self, p, f):
        off, sz = self.b.layout[f]; return self.b.r(p + off, sz)
    def label(self, p):
        ch = self.field(p, 'ch'); k = (ch - self.S['bm_chars']) // self.S['sizeof_bchar']
        nm = self.names[k] if 0 <= k < len(self.names) else '?'
        kind, i = self.entity(p)
        st = self.b.states[self.field(p, 'state')] if self.field(p, 'state') < len(self.b.states) else '?'
        if kind == 'F': return f"{'P' if i < 2 else 'E'}{i}:{nm}", st
        if kind == 'PJ': return f"pj{i}:{nm}", st
        return f"{nm}", st
    def frame(self):
        V = self.vram
        mode, nf = self.u8('mode'), self.u8('nf')
        owners = {}                                  # sprite -> label
        ents = []
        for i in range(min(nf, 22)):
            p = self.u32('order', i); lab, st = self.label(p)
            s0, n = self.u16('block_spr', i), self.u8('block_placed', i)
            for s in range(s0, s0 + n): owners[s] = lab
            ents.append(dict(label=lab, state=st, hidden=self.u8('hidden', i), cols=n, i=i, p=p))
        gh = self.u8('guard_hidden')
        # the guard's budget victims: hidden although in play, alive (not the dead blink) and on screen
        cam = self.b.r(self.S['cam_x'], 2); cam = cam - 65536 if cam > 32767 else cam
        hid = []
        for e in ents:
            if not e['hidden'] or e['state'] in ('OFF',): continue
            if e['state'] == 'PROJ' and self.field(e['p'], 'frame_ovr') == 0xFFFF: continue
            if e['state'] == 'DEAD': continue
            x = self.field(e['p'], 'x'); x = (x - (1 << 32) if x & 0x80000000 else x) >> 16
            if not -128 <= x - cam <= 448: continue
            hid.append(e['label'])
        thin = self.u8('guard_thinned') if 'guard_thinned' in self.S else 0
        cur = dict(owners=owners, gh=gh, hid=hid, thin=thin, shown=[e['label'] for e in ents if e['hidden'] == 0 and e['state'] != 'OFF'])
        prv = getattr(self, 'prev', None) or cur; self.prev = cur   # VRAM now = the command queue of the frame before
        owners = prv['owners']                                     # (flushed at this frame's vblank): its RAM view
        def owner(s):
            if s in owners: return owners[s]
            if 1 <= s < 22: return 'sf_glow'
            if 22 <= s < 43: return 'stage'
            if 43 <= s < 60: return 'shadow'
            if 300 <= s < 348: return 'banner/dbg'
            if 348 <= s < 364: return 'sf_rays'
            if 364 <= s < 376: return 'spark'
            if 376 <= s < 381: return 'throwfx'
            return f'spr{s}'
        # LSPC per line
        lines = {l: [] for l in VIS}
        ypos = size = 0
        for s in range(1, 382):
            y3 = V[0x8200 + s]
            if not (y3 & 0x40): ypos = (y3 >> 7) & 0x1FF; size = y3 & 0x3F
            if size == 0: continue
            top = (0x200 - ypos) & 0x1FF
            for l in VIS:
                if ((l - top) & 0x1FF) < size * 16: lines[l].append(s)
        if self.stat is not None:                  # the LSPC's own count while it drew this picture
            T = self.stat
            counts = [T[l * 34] for l in VIS]
            dropped = sorted({owner(T[l * 34 + 2 + k]) for l in VIS for k in range(T[l * 34 + 1])})
        else:                                      # the VRAM at the end of the frame (a long vblank flush may be
            counts = [len(lines[l]) for l in VIS]  # half done: approximate)
            dropped = sorted({owner(s) for l in VIS for s in lines[l][LIMIT:]})
        by = {}
        for l in VIS:
            for s in lines[l]: o = owner(s); by.setdefault(l, {}); by[l][o] = by[l].get(o, 0) + 1
        worst = VIS[max(range(len(counts)), key=lambda k: counts[k])]
        return dict(max=max(counts), over=sum(1 for c in counts if c > LIMIT), dropped=dropped, guard_hidden=prv['gh'],
                    guard_victims=prv['hid'], thinned=prv['thin'], worst_line=worst - 16, worst_mix=by.get(worst, {}), mode=mode, nf=nf,
                    shown=prv['shown'], counts=counts)

def shoot(b, path):
    b.screenshot(path)

def sheet(paths, labels, out, cols=4, title=''):
    from PIL import Image, ImageDraw
    ims = [Image.open(p).convert('RGB') for p in paths]
    w, h = ims[0].size; th = 26
    rows = (len(ims) + cols - 1) // cols
    sh = Image.new('RGB', (cols * w, rows * (h + th) + 18), 'white'); d = ImageDraw.Draw(sh)
    d.text((4, 3), title, fill='black')
    for k, (im, lab) in enumerate(zip(ims, labels)):
        x, y = k % cols * w, 18 + k // cols * (h + th)
        sh.paste(im, (x, y + th))
        for j, t in enumerate(lab.split('\n')[:2]): d.text((x + 3, y + 2 + 12 * j), t, fill='black')
    sh.save(out)

def measure(game, out, tag):
    from harness import Brawler
    b = Brawler(rom=os.path.join(game, 'brawler.neo'), game=game)
    pr = Probe(b, game); res = {}
    tmp = os.path.join(out, '_shots'); os.makedirs(tmp, exist_ok=True)
    names = pr.names
    # ---- the select screen, every boss unlocked
    b.core.retro_reset(); b.seq('600:-,4:o,100:-'); b.unlock_all(); b.seq('4:s,40:-')
    rows, shots = [], []; pr.prev = None; pr.frame()
    for f in range(60):
        p = os.path.join(tmp, f'{tag}_sel{f}.png')
        if f in (40, 41): shoot(b, p); shots.append(p)
        else: b.run(1)
        r = pr.frame(); r['f'] = f; rows.append(r)
    res['select'] = rows
    sheet(shots, [f'select frame {40 + k}: worst line {rows[40 + k]["max"]} sprites, guard hid {rows[40 + k]["guard_victims"] or "none"}\n'
                  f'shown {len(rows[40 + k]["shown"])} actors, LSPC dropped {rows[40 + k]["dropped"] or "none"}' for k in range(2)],
          os.path.join(out, f'{tag}_select.png'), cols=2, title=f'{tag}: the select screen, frames n / n+1 (22 actors)')
    # ---- furies with 6 enemies crowding the attacker
    st = b.states.index
    for who, keys, nm in (('geese', 'd', 'geese_fury'), ('geese', 'Dd', 'geese_max'), ('kuroko', 'd', 'kuroko_fury'),
                          ('genjuro', 'd', 'genjuro_fury'), ('kuroko', 'Dd', 'kuroko_max'), ('genjuro', 'Dd', 'genjuro_max')):
        k = names.index(who)
        b.pick(k, unlock=True)
        b.run(30)
        src = b.base + 2 * b.fsize
        alive = [i for i in range(2, 8) if b.fget(i, 'state') != st('OFF')]
        tpl = bytes(b.ram[src - 0x100000:src - 0x100000 + b.fsize]) if b.fget(2, 'state') != st('OFF') else None
        for i in range(2, 8):
            if b.fget(i, 'state') == st('OFF') and tpl is not None:      # a wave of 6: clones of enemy 2 (its colours)
                a = b.base + i * b.fsize - 0x100000; b.ram[a:a + b.fsize] = list(tpl); b.fset(i, 'idx', i)
        X = [150, 190, 230, 120, 260, 175]; Z = [6, 30, 18, 40, 10, 50]
        for j, i in enumerate(range(2, 8)):
            b.fset(i, 'state', st('IDLE')); b.fset(i, 'hp', 200); b.fset(i, 'y', 0); b.fset(i, 'freeze', 0)
            b.place(i, x=X[j] + 30, z=Z[j]); b.fset(i, 'facing', 0xFF)
        b.place(0, x=130, z=24); b.fset(0, 'facing', 1); b.fset(0, 'meter', 120); b.fset(0, 'state', st('IDLE'))
        b.run(2)
        rows, shots, started = [], [], None; pr.prev = None; pr.frame()
        for f in range(320):
            p = os.path.join(tmp, f'{tag}_{nm}{f}.png')
            for i in range(2, 8): b.fset(i, 'hp', 200)
            if f < 320: b.pad = [set(keys if f < 3 else ''), set()]; shoot(b, p)
            else: b.run(1)
            r = pr.frame(); r['f'] = f; r['p1'] = b.states[b.fget(0, 'state')]; rows.append(r)
            if f < 320: shots.append(p)
            if started is None and r['p1'] == 'SPECIAL': started = f
            if started is not None and f > started + 20 and r['p1'] != 'SPECIAL': break
        res[nm] = rows
        sel = list(range(len(shots)))
        # the sheet: frames of the fury, the worst ones first in time order (24 frames)
        sp = [f for f in sel if rows[f]['p1'] == 'SPECIAL'] or sel
        step = max(1, len(sp) // 24); pick = sp[::step][:24]
        sheet([shots[f] for f in pick],
              [f'+{f} worst line {rows[f]["max"]}{" OVER" if rows[f]["max"] > LIMIT else ""}\n'
               f'hid {",".join(x.split(":")[0] for x in rows[f]["guard_victims"]) or "-"} thin {rows[f]["thinned"] or "-"} drop {",".join(rows[f]["dropped"]) or "-"}' for f in pick],
              os.path.join(out, f'{tag}_{nm}.png'), cols=6, title=f'{tag}: {nm} with 6 enemies (frames from the press)')
    json.dump(res, open(os.path.join(out, f'{tag}.json'), 'w'))
    # the shot files are kept only for the sheets
    if not os.environ.get('KEEP'):
        for f in os.listdir(tmp): os.unlink(os.path.join(tmp, f))

def report(out):
    L = []
    for tag in ('base', 'new', 'stress64'):
        p = os.path.join(out, f'{tag}.json')
        if not os.path.exists(p): continue
        d = json.load(open(p))
        L.append(f'== {tag} ==')
        for case, rows in d.items():
            mx = max(r['max'] for r in rows); over = sum(1 for r in rows if r['max'] > LIMIT)
            gh = sum(1 for r in rows if r['guard_victims']); dr = sum(1 for r in rows if r['dropped'])
            vic = sorted({v for r in rows for v in r['guard_victims']}); drp = sorted({v for r in rows for v in r['dropped']})
            hist = {}
            for r in rows: hist[r['max'] // 8 * 8] = hist.get(r['max'] // 8 * 8, 0) + 1
            th = sum(1 for r in rows if r.get('thinned')); thl = max([r.get('thinned', 0) for r in rows] or [0])
            L.append(f'{case:14s} frames {len(rows):3d}  worst line {mx:3d}  frames over 96: {over:3d}  '
                     f'frames with a guard-hidden actor: {gh:3d} {vic}  frames with LSPC drops: {dr:3d} {drp}'
                     + (f'  frames with a thinned fury effect: {th} (up to {thl} a frame)' if th else ''))
            L.append('               worst-line histogram (per frame, 8-sprite bins): ' + ' '.join(f'{k}-{k + 7}:{v}' for k, v in sorted(hist.items())))
            w = max(rows, key=lambda r: r['max'])
            L.append(f'               worst frame +{w["f"]}: line y {w["worst_line"]}: ' + ', '.join(f'{k} {v}' for k, v in sorted(w['worst_mix'].items(), key=lambda t: -t[1])))
    open(os.path.join(out, 'budget.txt'), 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))

if __name__ == '__main__':
    if sys.argv[1] == 'report': report(sys.argv[2])
    else: measure(sys.argv[1], sys.argv[2], sys.argv[3])
