#!/usr/bin/env python3
"""The Lab builds for "Try in game" (tryit.js; Bruno 2026-10-10) into the Lab site: per built fighter f (make
LAB_FIGHTER=f in GAME_DIR: lab-<f>.neo + build_lab_<f>/) OUT/rom/lab-<f>.neo and OUT/rom/lab-<f>.json, the page's
manifest: export_bm.py's lab.json (his LAB special's animations, the pool, the throws, the moves' $NN), the build's
layout (harness._layout: fighter_t, the symbols, lab_t's "Try in game" offsets) and what the sheet's chain needs to
build a chain override (load 5: chainlab.json's entry of the fighter, the chain rules, the ROM's retime rows).
The Lab build is never the Player's game: it lives under rom/ behind the Oros login with the rest of the Lab.

    python3 tryit_site.py OUT [GAME_DIR]      (make_site.py runs it too)"""
import glob, json, os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness

WANT = ['lab', 'fighters', 'route_tab', 'rt_tab', 'bm_chars', 'mode', 'cam_x', 'projectiles', 'attract', 'phase', 'wave',
        'lock_x', 'camp', 'game_ticks', 'lab_fields']


def lab_builds(game):
    """[(fighter, build dir name, rom path)] of the Lab builds in game"""
    out = []
    for lj in sorted(glob.glob(os.path.join(game, 'build_lab_*', 'lab.json'))):
        b = os.path.basename(os.path.dirname(lj)); f = b[len('build_lab_'):]
        rom = os.path.join(game, f'lab-{f}.neo')
        if os.path.exists(rom): out.append((f, b, rom))
    return out


def write(out, game):
    os.makedirs(os.path.join(out, 'rom'), exist_ok=True)
    done = []
    for f, b, rom in lab_builds(game):
        man = json.load(open(os.path.join(game, b, 'lab.json')))
        layout, fsize, states, syms = harness._layout(game, b)
        man['layout'] = {'fields': layout, 'fsize': fsize, 'states': states, 'syms': {k: syms[k] for k in WANT if k in syms},
                         'sizeof_bchar': syms.get('sizeof_bchar'), 'version': open(os.path.join(game, 'VERSION')).read().strip()}
        cl = json.load(open(os.path.join(game, b, 'chainlab.json')))
        G = json.load(open(os.path.join(game, 'game.json')))
        rt = os.path.join(game, b, 'retime.json')
        man['chain'] = {'ba': cl['ba'], 'rules': {k: v for k, v in G['chain'].items() if k != 'about'},
                        'retime_rom': json.load(open(rt)) if os.path.exists(rt) else [],
                        'fighters': [{'name': x['name'], 'id': x['id']} for x in cl['fighters']],
                        'fighter': next(x for x in cl['fighters'] if x['name'] == f)}
        man['rom'] = f'rom/lab-{f}.neo'; man['size'] = os.path.getsize(rom)
        shutil.copy(rom, os.path.join(out, 'rom', f'lab-{f}.neo'))
        json.dump(man, open(os.path.join(out, 'rom', f'lab-{f}.json'), 'w'), ensure_ascii=False)
        done.append(f)
        print(f'rom/lab-{f}.neo ({os.path.getsize(rom):,} bytes), rom/lab-{f}.json: {len(man["anims"])} animations, '
              f'LAB special = pool {man["spec"]} of {len(man["pool"])}')
    json.dump(done, open(os.path.join(out, 'rom', 'index.json'), 'w'))
    return done


if __name__ == '__main__':
    write(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else harness.GAME)
