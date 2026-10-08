#!/usr/bin/env python3
"""Brawler revamp phase 4: the per-fighter review pages' data (tools/brawler/chainlab/review.html, review.js), built
from tools/brawler/pieces.py (catalogue, appeal, proposal) and the build's own drawings.

Per fighter: OUT/review/<fighter>.png (every drawing its clips show, 1x RGBA, colour set 0; the back throw's victim in
colour set 1) and OUT/review/<fighter>.json:
  cells   [[x, y, w, h, ox, oy], ...]   a drawing's place in the sheet and its feet point (ox, oy) inside it
  pieces  the ranked catalogue (pieces.py tags, appeal and its parts, raw numbers) each with its clip
  proposal  archetype, the chain (links), the finishers by stick, each with my alternatives
  clips   {id: {frames: [[flags, [cell, x, y, mirror], ...], ...], box: [[x0, y0, x1, y1] | 0 per frame], links}}
          one entry per game frame at 1x (59.18 Hz): the drawings shown, x forward / y up px from the start's feet;
          flags 1 a live attack box, 2 a hit window's first frame (contact), 4 the hit-stop (frozen), 8 a new link
  checks  the frame counts the proof compares with the data (chainlab.json totals and 1C segments)
The chain clip: every link from its first frame to its last hit's contact frame, held for its hit-stop (the next
press on the first possible frame: the chain core takes it as the hit-stop ends), then the next link; the neutral
finisher played to its end. A finisher's clip: the whole chain the same way with that finisher (round 2: "too short,
nothing under 3 hits"; round 1 showed only the last link before it); the back throw's held for no hit-stop.
OUT/review/index.json lists the fighters built.

    python3 tools/brawler/review_build.py OUT GAME_DIR [FIGHTER ...]     (default: REVIEW, every roster fighter)"""
import json, os, sys
import numpy as np
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import pieces as PC
from move_images import Rom, colours

REVIEW = 'all'               # every roster fighter (4b, 2026-10-08; phase 4's first three were kim, terry, krauser)
ROUND = 2                    # the proposal's round: 2 = pieces.py's round-2 score (Bruno's three reviews); the page keys
                             # the proposal's answers by it (chain-r2, fin-up-r2...) so round 1's answers stay apart
SHEET_W = 2048


def hitstops(G, N):
    lo, hi = G['chain']['hitstop']
    return [lo + ((hi - lo) * k * 2 + (N - 1)) // (2 * (N - 1)) for k in range(N)] if N > 1 else [hi]


def box_of(fr):
    if not fr.get('live') or not any(fr['atk']): return 0
    x, y, w, h = fr['atk']
    return [-x - w + fr['x'], y - h - fr['y'], -x + w + fr['x'], y + h - fr['y']]


class Clips:
    def __init__(self, F):
        self.F = F; self.cells = {}; self.order = []

    def cell(self, frame, cset=0):
        k = (frame, cset)
        if k not in self.cells: self.cells[k] = len(self.order); self.order.append(k)
        return self.cells[k]

    def frames(self, p, dx=0, upto=None, first_link=False):
        """a piece's frames as clip entries (x shifted by dx), cut after frame index upto"""
        out = []
        fr = p['frames'] if upto is None else p['frames'][:upto + 1]
        prev = False
        for i, f in enumerate(fr):
            fl = (1 if f['live'] else 0) | (2 if f['live'] and not prev else 0) | (8 if i == 0 and first_link else 0)
            prev = f['live']
            mir = 1 if f.get('turned') else 0
            spr = [[self.cell(f['frame']), f['x'] + dx, f['y'], mir]]
            v = f.get('victim')
            if v:
                vs = [self.cell(v['frame'], 1 if self.F.nsets > 1 else 0), v['x'] + dx, v['y'], 1 if v['mirror'] else 0]
                spr = spr + [vs] if v['front'] else [vs] + spr
            b = box_of(f)
            if b: b = [b[0] + dx, b[1], b[2] + dx, b[3]]
            out.append([fl, spr, b])
        return out

    def piece(self, p):
        return self.frames(p)

    def seq(self, links, fin, hs):
        """links (pieces) then the finisher: each link to its last hit's contact + its hit-stop, the finisher whole"""
        out, dx, marks = [], 0, []
        for k, p in enumerate(links + [fin]):
            last = k == len(links)
            win = [i for i, f in enumerate(p['frames']) if f['live'] and (i == 0 or not p['frames'][i - 1]['live'])]
            cut = win[-1] if win else len(p['frames']) - 1
            marks.append(len(out))
            fr = self.frames(p, dx, None if last else cut, True)
            ci = cut                                               # the contact frame: held for the hit-stop
            body = fr[:ci + 1]
            hold = [[(fr[ci][0] & ~10) | 4, fr[ci][1], fr[ci][2]] for _ in range(hs[k])]
            out += body + hold + (fr[ci + 1:] if last else [])
            dx += p['frames'][cut]['x']
        return out, marks


def build(out, game, names, rom=None, lab=None, G=None):
    rom = rom or Rom(os.path.join(game, 'build'))
    lab = lab or json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    G = G or json.load(open(os.path.join(game, 'game.json')))
    os.makedirs(os.path.join(out, 'review'), exist_ok=True)
    if names in ('all', None): names = [r['name'] for r in G['roster']]
    index = []
    for name in names:
        F, ranked, prop = PC.review(game, name, rom, lab, G)
        C = Clips(F)
        by = {p['id']: p for p in ranked}
        clips, checks = {}, {}
        for p in ranked:
            clips[p['id']] = {'frames': C.piece(p)}
            c = dict(p['check'], clip=len(clips[p['id']]['frames']))
            if p['kind'] == 'special': c['want'] = sum(p['segs'])
            elif p['kind'] == 'throw': c['want'] = -(-c['rows'] * 256 // c['speed'])     # rows at speed / 256 a frame
            else: c['want'] = c['data_total'] if c['data_total'] is not None else sum(c['data_segs'] or [])
            checks[p['id']] = c
        links = [by[i] for i in prop['chain']['links']]
        N = prop['chain']['length']; hs = hitstops(G, N)
        fins = prop['finishers']
        if fins['neutral']['pick']:
            fr, marks = C.seq(links, by[fins['neutral']['pick']], hs)
            clips['chain'] = {'frames': fr, 'links': marks}
            checks['chain'] = {'clip': len(fr), 'hitstops': hs}
        for k in ('neutral', 'forward', 'up', 'down', 'back'):
            pid = fins[k]['pick']
            if not pid: continue
            p = by[pid]
            fr, marks = C.seq(links, p, hs[:-1] + [0 if k == 'back' else hs[-1]])   # the whole chain, then it
            clips['fin-' + k] = {'frames': fr, 'links': marks}
            checks['fin-' + k] = {'clip': len(fr), 'hits': sum(max(1, q['hits']) for q in links + [p])}
        # the sheet: every drawing once, rows of SHEET_W px
        pals = F.pals
        imgs = []
        for frame, cset in C.order:
            r = F.index(frame)
            if r is None: imgs.append((np.zeros((1, 1, 4), np.uint8), 0, 0)); continue
            ix, ox, oy = r
            base = cset * F.npal * 16
            imgs.append((colours(ix, pals[base:base + F.npal * 16]), ox, oy))
        x = y = rowh = 0; place = []
        for im, ox, oy in imgs:
            h, w = im.shape[:2]
            if x + w > SHEET_W: x = 0; y += rowh + 1; rowh = 0
            place.append([x, y, w, h, ox, oy]); x += w + 1; rowh = max(rowh, h)
        sheet = np.zeros((y + rowh, SHEET_W, 4), np.uint8)
        for (im, _, _), (px, py, w, h, _, _) in zip(imgs, place): sheet[py:py + h, px:px + w] = im
        used_w = max((p[0] + p[2] for p in place), default=1)
        Image.fromarray(sheet[:, :used_w], 'RGBA').save(os.path.join(out, 'review', f'{name}.png'), optimize=True)
        slim = [{k: v for k, v in p.items() if k not in ('frames', 'check')} for p in ranked]
        data = {'fighter': name, 'display': F.ros.get('display') or name.upper().replace('_', ' '), 'game': F.src_game,
                'archetype': prop['archetype'], 'fps': PC.FPS, 'sheet': f'review/{name}.png', 'cells': place,
                'pieces': slim, 'proposal': prop, 'clips': clips, 'checks': checks, 'hitstops': hs, 'round': ROUND}
        json.dump(data, open(os.path.join(out, 'review', f'{name}.json'), 'w'), separators=(',', ':'))
        index.append({'fighter': name, 'display': data['display'], 'game': F.src_game, 'archetype': prop['archetype'], 'pieces': len(ranked)})
        print(name, len(ranked), 'pieces', len(place), 'drawings', 'chain', ' > '.join(prop['chain']['links']))
    old = []
    ip = os.path.join(out, 'review', 'index.json')
    if os.path.exists(ip): old = [e for e in json.load(open(ip)).get('fighters', []) if e['fighter'] not in names]
    order = [r['name'] for r in G['roster']]
    allf = sorted(old + index, key=lambda e: order.index(e['fighter']) if e['fighter'] in order else 99)
    json.dump({'fighters': allf}, open(ip, 'w'), indent=1)
    return index


if __name__ == '__main__':
    out, game = sys.argv[1], sys.argv[2]
    build(out, game, sys.argv[3:] or REVIEW)
