#!/usr/bin/env python3
"""The Last Blade 2 fighters in the export96 layout: the brawler's export_bm.py reads them like a KOF96/98/99 export (layer
0 of docs/brawler_data_model.md, one code path), the way tools/samsho2 (export_ss2) does.

    python3 export_lb2.py OUTDIR [moriya]   -> OUTDIR/kof95_export.json, kof95_c1.bin, kof95_c2.bin

Everything comes from the ROM (study /data/neogeo_dict/lastbld2/README.md, decoder lb2.py = the game's VRAM pen for pen,
model_lb2.py = the game's animation interpreter frame for frame, check_model.py):
- frames: a frame record's layers (up to 6, $E48C) drawn in the display list's order (each next layer's priority
  = the first's - its w3 bits 12-14: lower draws below), full size (LB2 shows its fighters 1:1 up close). LB2's art faces
  LEFT, as the brawler's: no mirroring; a layer's own flips (accumulated, $E4EA) baked into flipped tile copies.
- steps: what the game shows, played by model_lb2 (a frame word lasts its $81 ticks; a motion segment holds the step it
  reaches until it ends): runs of the same frame and the same boxes, ticks = frames - 1 (the export96 rule).
- boxes: the slots +$100 ($91 / $B5 records, [type][shift][x1][x2][y1][y2] << shift from the feet, art facing left: x
  negative = forward, y negative = up); type 1-$BF = attack, $C0+ = body ($34F26: cmpi #$C0) -> KOF keys '31' (the
  body union) and '11' (the attack union), centre / half extents.
- palettes: a sprite definition's palette = its byte 0 + the player's base, loaded from ROM palette word 4 ($1023C:
  Moriya's every definition: word 4 = byte 0 + 464, all 1476); the export's palette key = that ROM index; his own
  set (slots $60-$97) at + 56 per colour set ($17378: the colour byte x 56), the common effects' (char 24) fixed.
- physics: the walk / jump scripts' segments ($84: vx, vy, gravity in 8.8, x forward = -value).
- specials, throws: handlers_lb2.py (the moves' descriptors and scripts as programs)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lb2 as L, model_lb2 as M

TILE_BASE = 256                                   # = export96.TILE_BASE (export_bm slices from it)
CAST = {'moriya': 1}
PAL0 = {1: 464}                                   # ROM palette index of palette key 0 (key = definition byte 0)
SET_STRIDE = 56                                   # palettes per colour set ($17378: muluw #56)
COLOURS = 2                                       # colour sets exported (A, B: the second player's)

# brawler move -> LB2 animation (Moriya; the move table $A0000 from the standing class 1, README "Moves"): A = weak
# slash, B = strong slash, C = kick (the brawler's A / B / C / D: LB2's A / B / C / forward + C, the kick that steps in),
# body_toss = forward + B (Ittou Kannazuki, the stepping reap: the heaviest standing slash, the chain's finisher)
MOVES = {
    'idle': 0x00, 'walk_fwd': 0x04, 'run': 0x11, 'walk_back': 0x05,
    'jump_up_rise': 0x0C, 'jump_up_fall': 0x0C, 'jump_fwd_rise': 0x0D, 'jump_fwd_fall': 0x0D,
    'jump_back_rise': 0x0E, 'jump_back_fall': 0x0E, 'land': 0x47,
    'atk_a_close': 0x31, 'atk_a_far': 0x31, 'atk_b_close': 0x34, 'atk_b_far': 0x34,
    'atk_c_close': 0x35, 'atk_c_far': 0x35, 'atk_d_close': 0x36, 'atk_d_far': 0x36,
    'atk_a_crouch': 0x37, 'atk_b_crouch': 0x38, 'atk_c_crouch': 0x39, 'atk_d_crouch': 0x3A,
    'atk_a_jump': 0x3B, 'atk_b_jump': 0x3C, 'atk_c_jump': 0x3D, 'atk_d_jump': 0x3C,
    'atk_c_jump_diag': 0x3D, 'atk_d_jump_diag': 0x3C, 'atk_a_jump_diag': 0x3B, 'atk_b_jump_diag': 0x3C,
    'body_toss': 0x91,
    'cmd_fwd_a': 0x30, 'cmd_fwd_b': 0x91, 'cmd_df_c': 0x3A, 'cmd_df_d': 0x90,
    'hit_stand_light': 0x100, 'hit_stand_heavy': 0x101, 'hit_air': 0x10F, 'blowback': 0x10F, 'blowback_n': 0x10F,
    'knockdown_flight': 0x10F, 'knockdown_bounce': 0x119, 'knockdown_fall': 0x119, 'down': 0x11D, 'getup': 0x16,
    'trip': 0x101,
}
LOOP = {'idle', 'walk_fwd', 'run', 'walk_back'}

def flip_tile(t, hf, vf):
    """a 128-byte C tile mirrored (hf) / flipped (vf) (export_ss2.flip_tile)"""
    import numpy as np
    sys.path.insert(0, os.path.join(HERE, '..', 'samsho2'))
    import export_ss2 as X
    return X.flip_tile(t, hf, vf)

class Builder:
    """frames as brawler parts; palettes by LB2 palette key (definition byte 0, the player's base 0)"""
    def __init__(self, ch):
        self.ch = ch; self.c = L.load()[1]
        self.tile_map, self.tiles, self.frames, self.index, self.pals = {}, [], [], {}, []
    def tile(self, code, hf, vf):
        k = (code, hf, vf)
        if k not in self.tile_map:
            o = (code * 128) % len(self.c); raw = self.c[o:o + 128]
            if not any(raw): return 0
            self.tile_map[k] = TILE_BASE + len(self.tiles); self.tiles.append(flip_tile(raw, hf, vf))
        return self.tile_map[k]
    def pal(self, p):
        if p not in self.pals: self.pals.append(p)
        return self.pals.index(p)
    def frame(self, fid, ch=None):
        """a frame record of character ch (default the fighter's; an effect object's: another table, e.g. 24 the
        common effects) as brawler parts"""
        ch = self.ch if ch is None else ch
        key = fid if ch == self.ch else (ch, fid)
        if key in self.index: return self.index[key]
        lay = L.frame_layers(ch, fid)
        order = sorted(range(len(lay)), key=lambda k: (lay[k]['prio'], -k), reverse=True)   # P0 - prio, list order
        parts = []
        for k in order: parts += self.layer(lay[k], ch)
        self.index[key] = len(self.frames)
        self.frames.append({'record': f'{ch}:{fid}', 'parts': parts, 'weapon': None, 'lb2': {'frame': fid, 'char': ch,
                            'layers': [[l['sid'], l['x'], l['y'], l['flips']] for l in lay]}})
        return self.index[key]
    def pal_order(self):
        """(T4) the palettes in their first use by the frames WITHOUT a trail (the order before the trails: the trail
        frames only use palettes other frames use, but registered them early, and a Lab slot over the game's 8 palettes
        shows its later ones in other colours, export_bm pal_slots), the parts renumbered"""
        order = []
        for fr in self.frames:
            if fr['lb2'].get('lnk'): continue
            for p in fr['parts']:
                if self.pals[p['pal']] not in order: order.append(self.pals[p['pal']])
        order += [k for k in self.pals if k not in order]
        new = {i: order.index(k) for i, k in enumerate(self.pals)}
        for fr in self.frames:
            for p in fr['parts']: p['pal'] = new[p['pal']]
        self.pals[:] = order
    def frame_lnk(self, fid, lnk):
        """T4 (2026-10-14): his frame fid with a linked-frame trail drawn on it (lnk = (frame id, x, y): the OBJ LNK object
        of a normal's script, at his place + (x, y) in the art's own orientation, in front of him: its layers after his)"""
        if lnk is None: return self.frame(fid)
        key = ('lnk', fid) + tuple(lnk)
        if key in self.index: return self.index[key]
        parts = list(self.frames[self.frame(fid)]['parts'])
        lay = [dict(l, x=l['x'] + lnk[1], y=l['y'] + lnk[2]) for l in L.frame_layers(self.ch, lnk[0])]
        for k in sorted(range(len(lay)), key=lambda k: (lay[k]['prio'], -k), reverse=True): parts += self.layer(lay[k])
        self.index[key] = len(self.frames)
        self.frames.append({'record': f'{self.ch}:{fid}+{lnk[0]}', 'parts': parts, 'weapon': None,
                            'lb2': {'frame': fid, 'char': self.ch, 'lnk': list(lnk)}})
        return self.index[key]
    def layer(self, L_, ch=None):
        sd = L.sprite_def(self.ch if ch is None else ch, L_['sid'])
        if sd is None or not sd['cols'] or not sd['rows']: return []
        cells, at = L.sprite_cells(sd)
        fl = L_['flips']
        hf, vf = fl & 1, fl >> 1 & 1
        x0 = -(sd['cols'] * 16 + L_['x']) if hf else L_['x']
        y0 = -(sd['rows'] * 16 + L_['y']) if vf else L_['y']
        pal = sd['w2'] + (at >> 8 if sd['fmt'] == 3 and at else 0)   # the key: its ROM palette index (word 4, $1023C)
        vis = cells[::-1] if hf else cells
        cols = []
        for ci, col in enumerate(vis):
            col = col[::-1] if vf else col
            rows = {r: self.tile(t, hf, vf) for r, t in enumerate(col) if t}
            rows = {r: t for r, t in rows.items() if t}
            if rows: cols.append((x0 + 16 * ci, y0, [rows.get(r, 0) for r in range(len(col))]))
        parts = []
        for x, tp, t in cols:                           # adjacent columns with the same top: one part
            while t and not t[-1]: t = t[:-1]
            lead = 0
            while t and not t[0]: t = t[1:]; lead += 1
            if not t: continue
            q = parts[-1] if parts else None
            if q and q['_top'] == tp + 16 * lead and q['_x'] + 16 * len(q['tiles']) == x:
                q['tiles'].append(t); continue
            parts.append({'_top': tp + 16 * lead, '_x': x, 'tiles': [t]})
        out = []
        for q in parts:
            n = max(len(t) for t in q['tiles'])
            out.append({'dx': q['_x'], 'dy': q['_top'], 'hflip': 0, 'vflip': 0, 'pal': self.pal(pal),
                        'tiles': [t + [0] * (n - len(t)) for t in q['tiles']]})
        return out

# ---- boxes ----
def kof_box(recs):
    """slot records (type, shift, x1, x2, y1, y2) -> KOF (cx, cy, hw, hh): x forward negative, y up negative"""
    l = min(r[2] << r[1] for r in recs); r_ = max(r[3] << r[1] for r in recs)
    t = min(r[4] << r[1] for r in recs); b = max(r[5] << r[1] for r in recs)
    cx, cy = (l + r_) // 2, (t + b) // 2
    return [max(-128, min(127, cx)), max(-128, min(127, cy)), min(255, max(1, (r_ - l + 1) // 2)), min(255, max(1, (b - t + 1) // 2))]

def kof_boxes(boxes):
    body = [v for v in boxes.values() if v[0] >= 0xC0]
    atk = [v for v in boxes.values() if 0 < v[0] < 0xC0]
    out = {}
    if body: out['31'] = kof_box(body)
    if atk: out['11'] = kof_box(atk)
    return out

# ---- an animation as the game plays it ----
def timeline(ch, a, mode=0, limit=600, loop=False):
    """model_lb2 rows of animation a alone (no descriptor), to its end ($FFFF: its last frame held once more by the
    game, not included) or, loop, one cycle (the $9F restart)"""
    o = M.Obj(ch, mode); o.set_anim(a); o.events = []
    rows = []
    for _ in range(limit):
        if o.ended: break
        r = o.frame()
        if loop and rows and o.off == 0 and r['step'] == 0 and len(rows) > 1 and o.step == 0: rows.append(r); break
        rows.append(r)
        if loop and o.off == 0 and len(rows) > 1: break
    return rows, o.events

def collapse(B, rows, cuts=()):
    """frames -> steps: runs of the same frame id and boxes; the boxes' writes open a new hit; cuts: row indices where a
    step must start anyway (an effect object born there, handlers_lb2.program)"""
    steps = []
    for k, r in enumerate(rows):
        bx = kof_boxes(r['boxes'])
        key = (r['frame'], json.dumps(bx, sort_keys=True), r.get('lnk'))
        if steps and steps[-1]['_key'] == key and k not in cuts: steps[-1]['ticks'] += 1; continue
        steps.append({'_key': key, 'frame': B.frame_lnk(r['frame'], r.get('lnk')), 'ticks': 0, 'flags': 0x100 if '11' in bx else 0,
                      'dx': 0, 'boxes': bx, 'lb2': [r['anim'], r['frame']] + ([r['lnk'][0]] if r.get('lnk') else []),
                      'lb2_atk': sorted({v[0] for v in r['boxes'].values() if 0 < v[0] < 0xC0}),
                      '_atk': [v for v in r['boxes'].values() if 0 < v[0] < 0xC0]})
    for i, s in enumerate(steps):                     # an attack continued by the next step (the same records): one hit
        n = steps[i + 1] if i + 1 < len(steps) else None
        if s['_atk'] and n is not None and n['_atk'] == s['_atk']: s['flags'] |= 0x4000
    for s in steps: s.pop('_key'); s.pop('_atk')
    return steps

def trails(rows, ev):
    """T4 (2026-10-14): each row's linked-frame trail (frame id, x, y) or None: an $AE / $9A spawn (OBJ LNK, $2D8F6) shows
    from its row while his step index and frame stay the ones it was born on ($2D99E: +$B8 / +$C6 unchanged, else it frees
    itself) [code]; (x, y) = the command's offset in the art's own orientation (handlers_lb2.spawn_info: fwd = -x, up = -y)"""
    import handlers_lb2 as H
    born = {}
    for e in ev:
        if e[1] == 'spawn' and H.SPAWN_KIND.get(e[2]) == 'lnk':
            i = H.spawn_info(e[2], e[3]); born[e[0]] = (i['word'] & 0xFFF, -i['fwd'], -i['up'])
    cur, at = None, None
    for k, r in enumerate(rows):
        if k in born: cur, at = born[k], (r['step'], r['frame'])
        elif cur is not None and (r['step'], r['frame']) != at: cur = None
        r['lnk'] = cur
    return rows

def anim_steps(B, ch, a, loop=False, lnk=True):
    """lnk: its OBJ LNK trails drawn on its frames (T4); off for the Lab's dictionary (handlers_lb2.lab_special): its
    every animation with trails takes a 30th palette and the Lab slot's palettes no longer fold into the 8 the game loads
    (pal_pack: the effects' palettes then show other colours)"""
    rows, ev = timeline(ch, a, loop=loop)
    return collapse(B, trails(rows, ev) if lnk else rows)

def physics(ch):
    """walk: measured px / frame (the walk script's $84 gives 1.5; the control adds: README); jump: anim $0C's $84
    ($8000 until landing): vy0 = 8.8125, gravity 0.53125 a frame (its ah, applied before the move: the first frame
    rises vy0 - g); jump_dx: anim $0D's vx (2 px a frame)"""
    def seg(a):
        for it in L.parse(ch, a):
            if it[0] == 'cmd' and it[2] == 0x84:
                b = it[3]; w = lambda k: M.s16(b[k] << 8 | b[k + 1])
                return -w(6) / 256, w(8) / 256, -w(10) / 256, w(12) / 256
    vx, vy, ax, ay = seg(0x0C); fx = seg(0x0D)[0]
    return {'walk_fwd': WALK.get(ch, 2.0), 'walk_back': WALK.get(ch, 2.0) * 0.75, 'jump_vy0': vy + ay, 'gravity': -ay,
            'jump_dx': fx, 'prejump': 2}
WALK = {1: 2.125}                                 # [meas] play_lb2: 60 frames holding forward from vs.state, 2.125 px a frame

def colours(B, ch):
    """per colour set the palettes of every key B uses (a key = the ROM palette index a definition loads, $1023C: word 4
    of the definition): the fighter's own set (PAL0 + 96 .. + 151: slots $60-$97) + 56 per colour set ($17378), the
    common effects' (char 24's: slots $98+, loaded with +$68 cleared, $2D542) as they are ($FF9A: $A9000 + 32 index)"""
    sets = []
    own = range(PAL0[ch] + 96, PAL0[ch] + 96 + SET_STRIDE)
    for s in range(COLOURS):
        row = []
        for k in B.pals:
            a = 0xA9000 + 32 * (k + (SET_STRIDE * s if k in own else 0))
            row.append([0] + [L.u16(a + 2 * q) for q in range(1, 16)])
        sets.append(row)
    return sets

def export(names, outdir, only=None, extra=None, lab=None):
    import handlers_lb2 as H
    out = {'game': 'lastbld2', 'tile_base': TILE_BASE, 'characters': {}}
    allt, tmap = [], {}
    for name in names:
        ch = CAST[name]; B = Builder(ch); B.tiles = allt; B.tile_map = tmap
        anims = {}
        for mv, a in MOVES.items():
            if only is not None and mv not in only and mv != 'watch': continue
            anims[mv] = {'slot': a, 'mode': 'loop' if mv in LOOP else 'hold', 'steps': anim_steps(B, ch, a, loop=mv in LOOP),
                         **({'hitsnd': 'LB2 ' + H.NORMAL_SND[a]} if a in H.NORMAL_SND else {})}   # (T5: its impacts' pick list)
        w = (extra or {}).get(name, {}).get('watch')
        if w: anims['watch'] = {'slot': w[0], 'mode': 'hold', 'steps': anim_steps(B, ch, w[0])[w[1]:][:1]}
        for mv, hx in ((extra or {}).get(name, {}).get('moves') or {}).items():
            a = int(str(hx).lstrip('$'), 16); anims[mv] = {'slot': a, 'mode': 'hold', 'steps': anim_steps(B, ch, a)}
        anims.update(H.win_anims(B, ch, name))
        Lb = (lab or {}).get(name)
        sps = H.specials(B, ch, name, lab=Lb is not None, inputs=(extra or {}).get(name, {}).get('inputs'))
        throws = H.throws(B, ch, name)
        if Lb is not None:
            e, bad = H.lab_special(B, ch, Lb); sps.append(e)
            if bad: print(f'{name}: LAB special: {len(bad)} animations left out:', bad[:8])
        for t, th in throws.items(): anims[t] = th.pop('anim')
        B.pal_order()
        sets = colours(B, ch)
        out['characters'][name] = {'id': ch, 'frames': B.frames, 'anims': anims, 'block_palettes': sets,
                                   'palette': sets[0][0], 'palette_mirror': sets[1][0], 'physics': physics(ch),
                                   'throws': throws, 'specials': sps, 'hit_sparks': [],
                                   'modes': {'sets': ['A', 'B'], 'palettes': [str(p) for p in B.pals]}}
    out['tiles'] = len(allt)
    os.makedirs(outdir, exist_ok=True)
    region = bytearray(128 * TILE_BASE) + b''.join(allt)
    open(os.path.join(outdir, 'kof95_c1.bin'), 'wb').write(bytes(region[0::2]))
    open(os.path.join(outdir, 'kof95_c2.bin'), 'wb').write(bytes(region[1::2]))
    json.dump(out, open(os.path.join(outdir, 'kof95_export.json'), 'w'))
    return out

if __name__ == '__main__':
    names = sys.argv[2:] or ['moriya']
    ex = export(names, sys.argv[1])
    for n, ch in ex['characters'].items():
        print(n, len(ch['frames']), 'frames', len(ch['anims']), 'moves', ch['physics'], 'palettes', ch['modes']['palettes'])
        for sp in ch['specials']:
            print('  ', sp['input'], sp['condition'], len(sp['rom']['prims']), 'ops', sp['rom']['length'], 'frames', sp.get('name'))
    print(ex['tiles'], 'tiles')
