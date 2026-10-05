#!/usr/bin/env python3
"""Projectile / effect blocks (main.c block_w: the pool's PJ_SPRS sprites shared by width, each entity its thrower's
widest projectile or effect frame): every roster fighter's widest such frame, measured from the build's data (the
game's bm_chars.c / bm_spec.c compiled on the host: every special's script objects, projectiles with their end rows and
trails, the ROM specials' P_SPAWN objects), the game's own pj_cols (RAM) against it, and the frame shown by a pool
entity in the Chain Lab (harness, our emulator's core): the columns it drew (ncols) = the frame's, a screenshot each.

    python3 pj_widths_proof.py [OUTDIR]        (default /data/tmp/phoenix/out/pj_widths: <fighter>.png, pj_widths.json)"""
import json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from harness import Brawler, GAME
from PIL import Image
OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/phoenix/out/pj_widths'
MEAS = r'''#include <stdio.h>
#include "bm_chars.h"
static int mx, mf;
static void pj(const bchar_t *c, const bproj_t *d) {
    int r;
    for (; d; d = d->child == d ? 0 : d->child) {
        for (r = 0; r < d->nrows; r++) if (d->rows[r].frame != 0xFFFF && c->frames[d->rows[r].frame].ncols > mx) { mx = c->frames[d->rows[r].frame].ncols; mf = d->rows[r].frame; }
        if (d->end) for (r = 0; r < d->nend; r++) if (d->end[r].frame != 0xFFFF && c->frames[d->end[r].frame].ncols > mx) { mx = c->frames[d->end[r].frame].ncols; mf = d->end[r].frame; }
    }
}
int main(void) {
    int i, s, j, k;
    for (i = 0; i < BC_COUNT; i++) {
        const bchar_t *c = &bm_chars[i];
        mx = 0; mf = -1;
        for (s = 0; s < c->nspec; s++) {
            const bspec_t *sp = &c->specials[s];
            for (j = 0; j < sp->nrows; j++) for (k = 0; k < 2; k++) { unsigned f = sp->rows[j].obj[k].frame; if (f != 0xFFFF && c->frames[f].ncols > mx) { mx = c->frames[f].ncols; mf = f; } }
            for (j = 0; j < sp->nproj; j++) pj(c, &sp->proj[j]);
            if (sp->prog) { const bprim_t *p; for (p = sp->prog; p->op != P_END; p++) if (p->op == P_SPAWN) pj(c, &sp->robj[p->a]); }
        }
        printf("%d %s %d %d\n", i, c->name, mx, mf);
    }
    return 0;
}
'''

def measure():
    b = os.path.join(GAME, 'build')
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, 'm.c'), 'w').write(MEAS)
        subprocess.run(['gcc', '-w', '-o', os.path.join(d, 'm'), os.path.join(d, 'm.c'), os.path.join(b, 'bm_chars.c'),
                        os.path.join(b, 'bm_spec.c'), '-I' + b], check=True)
        out = subprocess.run([os.path.join(d, 'm')], capture_output=True, text=True, check=True).stdout
    return [(int(i), n, int(w), int(f)) for i, n, w, f in (l.split() for l in out.split('\n') if l)]

def main():
    os.makedirs(OUT, exist_ok=True)
    meas = measure()
    b = Brawler(); S = b.syms
    names = [r['name'] for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']]
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bc = [x[3:].lower() for x in re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')]
    b.pick(0)
    P = S['projectiles']; L, FS = b.layout, b.fsize
    def pset(i, f, v): o, sz = L[f]; b.w(P + i * FS + o, sz, v)
    res = []; ok = True
    for i, name, w, fr in meas:
        game_w = b.r(S['pj_cols'] + i, 1)
        row = {'fighter': name, 'widest': w, 'frame': fr, 'pj_cols': game_w}
        if w and name.lower() in bc and name.lower() in names:
            k = names.index(name.lower())
            L_ = S['lab']
            for j, ch in enumerate(b'LAB1'): b.w(L_ + j, 1, ch)
            b.w(L_ + 5, 1, k); b.w(L_ + 6, 1, 0); b.w(L_ + 4, 1, 1); b.run(40)
            dm = next(j for j in range(1, 8) if b.states[b.fget(j, 'state')] != 'OFF')
            b.place(dm, x=b.r(S['cam_x'], 2) + 300)          # the dummy out of the way
            f0 = S['fighters']
            for f, v in (('ch', b.fget(0, 'ch')), ('palbase', b.fget(0, 'palbase')), ('team', 0), ('owner', f0),
                         ('frame_ovr', fr), ('shown_frame', 0xFFFF), ('pdef', 0), ('spec_atk', 0), ('facing', 1),
                         ('x', (b.r(S['cam_x'], 2) + 200) << 16), ('z', b.fget(0, 'z') * 65536 // 1), ('y', 40 << 16),
                         ('state', b.states.index('PROJ'))):
                pset(0, f, int(v) & ((1 << 8 * L[f][1]) - 1))
            b.run(3)
            row['drawn_cols'] = b.pget(0, 'ncols')
            p = os.path.join(OUT, f'{name.lower()}.png'); b.screenshot(p)
            row['shot'] = p
            pset(0, 'state', b.states.index('OFF')); b.run(2)
        row['ok'] = game_w == w and row.get('drawn_cols', w) == w
        ok &= row['ok']; res.append(row)
        print(f"{name:10s} widest {w:2d} (frame {fr}) game pj_cols {game_w:2d} drawn {row.get('drawn_cols')} {'ok' if row['ok'] else 'FAIL'}")
    json.dump({'all_ok': ok, 'fighters': res}, open(os.path.join(OUT, 'pj_widths.json'), 'w'), indent=1)
    shots = [r for r in res if r.get('shot')]
    sheet = Image.new('RGB', (320 * 4, 224 * ((len(shots) + 3) // 4)), 'white')
    for j, r in enumerate(shots): sheet.paste(Image.open(r['shot']), (320 * (j % 4), 224 * (j // 4)))
    sheet.save(os.path.join(OUT, 'sheet.png'))
    print('all ok' if ok else 'FAILURES')

if __name__ == '__main__':
    main()
