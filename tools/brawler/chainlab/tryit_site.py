#!/usr/bin/env python3
"""The Lab builds for "Try in game" (tryit.js; Bruno 2026-10-10) into the Lab site: per built fighter f (make
LAB_FIGHTER=f in GAME_DIR: lab-<f>.neo + build_lab_<f>/) OUT/rom/lab-<f>.neo and OUT/rom/lab-<f>.json, the page's
manifest: export_bm.py's lab.json (his LAB special's animations, the pool, the throws, the moves' $NN), the build's
layout (harness._layout: fighter_t, the symbols, lab_t's "Try in game" offsets) and what the sheet's chain needs to
build a chain override (load 5: chainlab.json's entry of the fighter, the chain rules, the ROM's retime rows).
The Lab build is never the Player's game: it lives under rom/ behind the Oros login with the rest of the Lab.

The Character Lab SHELL + PACKS (docs/character_lab.md "Character Lab: shell and packs"; the Fighter Lab's "Try in game" plays
them, the same files the Player downloads from the catalogue): the page fetches the bytes from the catalogue
(/brawler/lab/dl/...) and needs, beside them, what a .neo / .pack does not say:
  OUT/rom/shell-<engine>.json   the shell build's layout (harness._layout of build_shell), its lab.json (the roster
                                order with "slot", the throws) and the chain rules: one per engine, so the layout of
                                every shell published stays on the server (the deploy's rsync never deletes)
  OUT/rom/pack-<f>-<sha12>.json the pack's chain data (its build's chainlab.json "slot" entry, retime.json) and his LAB
                                special's animations when he has one, keyed by the pack file's sha256: the page uses it
                                only for that exact pack (the pool and the RAM map come from the pack itself)

    python3 tryit_site.py OUT [GAME_DIR]      (make_site.py runs it too)"""
import glob, json, os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness

WANT = ['lab', 'fighters', 'route_tab', 'rt_tab', 'bm_chars', 'mode', 'cam_x', 'projectiles', 'attract', 'phase', 'wave',
        'lock_x', 'camp', 'game_ticks', 'lab_fields', 'prac']   # prac: the practice settings (fighter.h prac_t)


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
    shell_and_packs(out, game)
    return done


def sha256(p):
    import hashlib
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def shell_and_packs(out, game):
    """rom/shell-<engine>.json + rom/pack-<f>-<sha12>.json from the shell build and the packs of game (make LAB_SHELL=1,
    make LAB_PACK=<f>): the shell's engine is the one the packs built against it carry"""
    os.makedirs(os.path.join(out, 'rom'), exist_ok=True)
    shell = os.path.join(game, 'lab-shell.neo'); B = os.path.join(game, 'build_shell')
    if not (os.path.exists(shell) and os.path.exists(os.path.join(B, 'lab.json'))): print('no shell build: no shell / pack data'); return
    ssha = sha256(shell)
    packs = {}
    for pj in sorted(glob.glob(os.path.join(game, 'packs', '*.json'))):
        m = json.load(open(pj))
        if m.get('format') == 'brawler character pack': packs[m['fighter']] = m
    engine = next((m['engine'] for m in packs.values() if m.get('shell_sha256') == ssha), None)
    if engine:
        lab = json.load(open(os.path.join(B, 'lab.json')))
        layout, fsize, states, syms = harness._layout(game, 'build_shell')
        G = json.load(open(os.path.join(game, 'game.json')))
        doc = {'engine': engine, 'shell_sha256': ssha, 'slot': lab['id'], 'fighters': lab['fighters'], 'throws': lab['throws'],
               'layout': {'fields': layout, 'fsize': fsize, 'states': states, 'syms': {k: syms[k] for k in WANT if k in syms},
                          'sizeof_bchar': syms.get('sizeof_bchar'), 'version': open(os.path.join(game, 'VERSION')).read().strip()},
               'chain_rules': {k: v for k, v in G['chain'].items() if k != 'about'}}
        for n in (f'shell-{engine}.json', 'shell-latest.json'):   # (latest: a newer shell of the same game version, checked by the boot)
            json.dump(doc, open(os.path.join(out, 'rom', n), 'w'), ensure_ascii=False)
        print(f'rom/shell-{engine}.json (the shell {ssha[:12]}, slot {lab["id"]})')
    else: print(f'lab-shell.neo {ssha[:12]}: no pack built against it, its engine unknown: no shell data written')
    for f, m in packs.items():
        b = os.path.join(game, 'build_pack_' + f)
        if not os.path.exists(os.path.join(b, 'chainlab.json')):           # (the shell's own slot fighter: the shell build)
            cl = json.load(open(os.path.join(B, 'chainlab.json')))
            if (next((x for x in cl['fighters'] if x['name'] == 'slot'), {}).get('tree') or {}).get('fighter') != f: continue
            b = B
        cl = json.load(open(os.path.join(b, 'chainlab.json')))
        fe = next(x for x in cl['fighters'] if x['name'] == 'slot')
        sj = os.path.join(out, 'rom', f'shell-{m["engine"]}.json')
        if m['engine'] != engine and not os.path.exists(sj) and os.path.exists(os.path.join(b, 'rom.elf')):
            # a pack of another shell than the one built now: its build's layout IS its shell's (lab_pack.py refuses a
            # pack whose build differs from the shell outside the slot), so that shell gets its layout too
            layout, fsize, states, syms = harness._layout(game, os.path.basename(b))
            G = json.load(open(os.path.join(game, 'game.json')))
            json.dump({'engine': m['engine'], 'shell_sha256': m['shell_sha256'], 'slot': m['slot']['id'],
                       'fighters': [x['name'] for x in sorted(cl['fighters'], key=lambda x: x['id'])], 'throws': ['throw_c', 'throw_d', 'hold_hit', 'hold_fin', 'throw_x'],
                       'layout': {'fields': layout, 'fsize': fsize, 'states': states, 'syms': {k: syms[k] for k in WANT if k in syms},
                                  'sizeof_bchar': syms.get('sizeof_bchar'), 'version': m['game_version']},
                       'chain_rules': {k: v for k, v in G['chain'].items() if k != 'about'}, 'from': os.path.basename(b)},
                      open(sj, 'w'), ensure_ascii=False)
            print(f'rom/shell-{m["engine"]}.json (from {os.path.basename(b)}: the layout of the shell {f}\'s pack was built against)')
        lj = os.path.join(b, 'lab.json'); L = json.load(open(lj)) if os.path.exists(lj) else None
        L = L if L and L.get('fighter') == 'slot' else None
        rt = os.path.join(b, 'retime.json')
        doc = {'fighter': f, 'engine': m['engine'], 'sha256': m['sha256'], 'slot': m['slot']['id'],
               'anims': L['anims'] if L else [], 'lab_spec': L['spec'] if L else None, 'moves': L['moves'] if L else {},
               'chain': {'ba': cl['ba'], 'retime_rom': json.load(open(rt)) if os.path.exists(rt) else [], 'fighter': fe}}
        for n in (f'pack-{f}-{m["sha256"][:12]}.json', f'pack-{f}-latest.json'):   # (latest: a pack published after this build)
            json.dump(doc, open(os.path.join(out, 'rom', n), 'w'), ensure_ascii=False)
        print(f'rom/pack-{f}-{m["sha256"][:12]}.json (engine {m["engine"]}, LAB special: {len(doc["anims"])} animations)')


if __name__ == '__main__':
    write(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else harness.GAME)
