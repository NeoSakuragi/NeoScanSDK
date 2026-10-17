#!/usr/bin/env python3
"""A brawler build's ANALYSIS PACK: everything a recorded session's replay needs besides the ROM itself, as one JSON,
so the replay analysis (analyze.py) runs where there is no build tree and no m68k compiler (the VPS worker, worker.py):
fighter_t's field offsets and size, the state names, every ROM symbol (build/rom.elf), the select-screen counts, each
fighter's special pool + slot table (build/chainlab.json), the fighters' HUD names, the stages' names and wave counts
(read from the built ROM: chainlab/ramsyms.py), the drive meter's chunk size and the bonus games' names (game.json).

    python3 pack.py OUT_DIR [GAME_DIR [ROM]] [--commit SHA]   -> OUT_DIR/<VERSION>/pack.json
    (GAME_DIR: examples/brawler of THAT build, BUILT: brawler.neo + build/ of the same make)

tools/brawler/publish_vps.sh writes one for every published build and sends it to the VPS:
/data/brawler/analysis/builds/<VERSION>/pack.json (the ROM stays in the feedback archive
/data/brawler/feedback/roms/<sha>.neo.gz, or /data/brawler/builds/). backfill_packs.sh rebuilds older builds."""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..')); sys.path.insert(0, os.path.join(HERE, '..', 'chainlab'))
import harness, ramsyms

FORMAT = 1


ROM_SYMS = {'bm_chars', 'SEL_SLOT', 'sel_stick', 'gstages_rom', 'gstage_names', 'gmeter', 'bm_chars_rom', 'gbonus', 'tblob_size'}   # + work RAM's


def make(game, rom=None, build='build', commit=None):
    rom = rom or os.path.join(game, 'brawler.neo')
    layout, fsize, states, syms = harness._layout(game, build)
    rs = ramsyms.make(game, build, rom)                      # HUD names, stages, meter, rom_sha256, version
    tab = open(os.path.join(game, build, 'game_tables.h')).read()
    m = re.search(r'#define SEL_NSLOT (\d+)', tab); nslot = int(m.group(1)) if m else 16
    m = re.search(r'#define SEL_NPLACE (\d+)', tab); nplace = int(m.group(1)) if m else nslot
    m = re.search(r'#define NF (\d+)', open(os.path.join(game, 'main.c')).read()); nfmax = int(m.group(1)) if m else 8
    lab = json.load(open(os.path.join(game, build, 'chainlab.json')))
    fighters = [{'id': f['id'], 'name': f['name'], 'game': f.get('game'), 'pool': [p['input'] for p in f['pool']],
                 'specials': f.get('specials') or {}} for f in lab['fighters']]
    g = json.load(open(os.path.join(game, 'game.json')))
    bonus = [x.get('name') or x.get('scene') or '?' for x in (g.get('bonus') or {}).get('games', [])]
    if commit is None:
        try: commit = subprocess.run(['git', '-C', game, 'rev-parse', '--short', 'HEAD'], capture_output=True, text=True).stdout.strip()
        except Exception: commit = ''
    keep = {k: v for k, v in syms.items() if isinstance(v, (dict, str)) or k.startswith('sizeof_') or k in ROM_SYMS
            or 0x100000 <= v < 0x110000}
    return {'format': FORMAT, 'version': rs['version'], 'rom_sha256': rs['rom_sha256'], 'commit': commit,
            'layout': layout, 'fsize': fsize, 'states': states, 'syms': keep, 'nslot': nslot, 'nplace': nplace,
            'nf_max': nfmax, 'chars': rs['chars'], 'stages': rs['stages'], 'meter': rs['meter'], 'fighters': fighters,
            'bonus_games': bonus}


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('out'); ap.add_argument('game', nargs='?', default=harness.GAME); ap.add_argument('rom', nargs='?')
    ap.add_argument('--commit', help='the build commit (a tree without .git: backfill_packs.sh)')
    a = ap.parse_args(); out = a.out
    p = make(a.game, rom=a.rom, commit=a.commit)
    d = os.path.join(out, p['version']); os.makedirs(d, exist_ok=True)
    json.dump(p, open(os.path.join(d, 'pack.json'), 'w'), separators=(',', ':'))
    print(os.path.join(d, 'pack.json'), p['version'], p['rom_sha256'][:12], len(p['fighters']), 'fighters', len(p['stages']), 'stages')
