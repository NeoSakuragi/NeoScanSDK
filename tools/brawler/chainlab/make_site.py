#!/usr/bin/env python3
"""Chain Lab site files from a brawler build: the ROM, a BIOS archive with only SNK's MVS BIOS (region US: sp-u2.sp1,
its fix / sound / zoom ROMs; no UniBIOS), the game's layout (symbol addresses, fighter_t offsets: harness._layout) and
the fighters' move / route data (build/chainlab.json, export_bm.py).

    python3 make_site.py OUTDIR [GAME_DIR]      (GAME_DIR: examples/brawler, built)"""
import json, os, shutil, sys, zipfile
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness
out = sys.argv[1]; game = sys.argv[2] if len(sys.argv) > 2 else harness.GAME
os.makedirs(out, exist_ok=True)
shutil.copy(os.path.join(game, 'brawler.neo'), os.path.join(out, 'game.neo'))
with zipfile.ZipFile('/data/roms/neogeo.zip') as src, zipfile.ZipFile(os.path.join(out, 'neogeo.zip'), 'w', zipfile.ZIP_DEFLATED) as dst:
    for n in ('sp-u2.sp1', '000-lo.lo', 'sfix.sfix', 'sm1.sm1'): dst.writestr(n, src.read(n))
layout, fsize, states, syms = harness._layout(game)
want = ['lab', 'fighters', 'route_tab', 'bm_chars', 'mode', 'cam_x', 'projectiles', 'attract', 'phase', 'wave', 'lock_x', 'camp', 'game_ticks', 'fade_in']
json.dump({'fields': layout, 'fsize': fsize, 'states': states, 'syms': {k: syms[k] for k in want if k in syms}, 'sizeof_bchar': syms.get('sizeof_bchar'),
           'version': open(os.path.join(game, 'VERSION')).read().strip()},
          open(os.path.join(out, 'layout.json'), 'w'))
import routes, move_images                      # the move picker's pictures: each move's impact frame(s), from the ROM's tables
lab = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
lab['pics'] = move_images.move_images(game, out, [f['name'] for f in lab['fighters']], routes.MOVE_NAMES)
json.dump(lab, open(os.path.join(out, 'chainlab.json'), 'w'), ensure_ascii=False)
# the Stages tab: the campaign's stages and the pack's first part (build_tables.py labstages), the stage art in the ROM
# as strips (build/stage<n>.png, make_stage_ra.py), the extracted backgrounds that need a ROM build as thumbnails, faces
import build_tables, make_stage_ra, glob
from PIL import Image
G = json.load(open(os.path.join(game, 'game.json')))
st = build_tables.lab_stages(G, os.path.join(game, 'build'))
os.makedirs(os.path.join(out, 'stages'), exist_ok=True)
bgs = []
for n, (area, _, cols, _) in enumerate(make_stage_ra.STAGES):
    im = Image.open(os.path.join(game, 'build', f'stage{n}.png')).convert('RGB')
    im.resize((im.width // 2, im.height // 2), Image.LANCZOS).save(os.path.join(out, 'stages', f'bg{n}.jpg'), quality=85)
    bgs.append({'i': n, 'name': f'Robo Army area {area} street', 'w': cols * 16, 'img': f'stages/bg{n}.jpg'})
used = {f'area{a}_h.png' for a, *_ in make_stage_ra.STAGES}
other = []
for d, game_name in (('roboarmy', 'Robo Army'), ('mutnat', 'Mutation Nation'), ('sengoku2', 'Sengoku 2')):
    for f in sorted(glob.glob(f'/data/neogeo_dict/{d}/maps/*.png')):
        b = os.path.basename(f)
        if d == 'roboarmy' and b in used: continue
        im = Image.open(f).convert('RGB'); w, h = im.size
        im.thumbnail((240, 60), Image.LANCZOS)
        t = f'stages/x_{d}_{b[:-4]}.jpg'; im.save(os.path.join(out, t), quality=75)
        other.append({'game': game_name, 'name': b[:-4], 'size': [w, h], 'img': t})
faces = Image.new('RGB', (32 * len(st['roster']), 32), 'white')
for i, r in enumerate(G['roster']):
    f = next((f for f in ('/data/neogeo_dict/portraits/' + r['bank'].replace(':', '_') + x for x in ('.png', '_select.png', '_square.png'))
              if os.path.exists(f)), '')                # KOF: its face; SS4 / WHP: their select-screen portrait
    if f: faces.paste(Image.open(f).convert('RGB').resize((32, 32), Image.LANCZOS), (32 * i, 0))
faces.save(os.path.join(out, 'stages', 'faces.png'))
st.update(bgs=bgs, other_bgs=other, song_list=[s_['name'] for s_ in json.load(open(os.path.join(game, 'songs.json')))['songs']])
json.dump(st, open(os.path.join(out, 'stages.json'), 'w'))
# the Enemies tab: game.json's enemies, presets, tints, routes files (build_tables.py labenemies) and each fighter's
# select pose / idle / close C as palette indices with every colour set (move_images.enemy_images), recoloured in the page
en = build_tables.lab_enemies(G)
en['images'] = move_images.enemy_images(game, out, en['roster'])
json.dump(en, open(os.path.join(out, 'enemies.json'), 'w'))
# the Characters tab: the roster (game.json form, select slots), each fighter's pool of specials with its frame / hit
# data (chainlab.json 'pool', export_bm.special_info) and the auto-suggestion; pictures rendered here (char_images.py):
# select-pose candidates in colour, the select pose in every colour set, each special's impact / projectile frames
import char_images
chars = {'roster': G['roster'], 'slots': G['select']['slots'], 'stages': len(G['stages']),
         'pool': {f['name']: f['pool'] for f in lab['fighters']}, 'suggest': {f['name']: f['suggest'] for f in lab['fighters']},
         'poses': char_images.pose_candidates(G['roster'], out, os.path.join('/data/tmp/chainlab', 'tmp_poses')),
         'sets': char_images.colour_sets(game, out, [r['name'] for r in G['roster']]),
         'specpics': char_images.special_images(game, out, lab['fighters']),
         'boss_of': [s_['boss']['enemy'] for s_ in G['stages']]}
# the Voices section (TODO #55): each fighter's voice list (tools/brawler/voices.json), its voice keys, KOF's own voice per
# key and the ROM's mapping (chainlab.json), the voices this ROM's V ROM holds (build/snd/snd_report.json), a WAV each
import voices as V
srep = json.load(open(os.path.join(game, 'build', 'snd', 'snd_report.json'))).get('voices', {'fighters': {}})
def what(vo, sug):
    u = [k.replace('special:', '').replace('_', ' ') for k, v in sug.items() if v[0] == vo['id']]   # the moves it is KOF's own for
    for x in ([] if u else vo['uses']):                                                             # else where KOF plays it
        t = x['input'] if x['kind'] == 'special' else x['event'] if x['kind'] == 'event' else \
            ('intro' if any(st in V.INTRO[lab_g[n]] for st in x['states']) else 'win' if any(336 <= st < 344 for st in x['states']) else f"anim {x['slot']}")
        if t not in u: u.append(t)
    return ', '.join(u[:4]) + (' ...' if len(u) > 4 else '')
chars['voices'] = {}
for f in lab['fighters']:
    n = f['name']; lab_g = {n: f['game']}
    vl = V.bank(n)
    for vo in vl:
        src = os.path.join(V.OUT, 'wav', n, f"{vo['id']}.wav"); dst = os.path.join(out, 'voices', n)
        os.makedirs(dst, exist_ok=True); shutil.copy(src, os.path.join(dst, f"{vo['id']}.wav"))
    chars['voices'][n] = dict(f['voices'], game=f['game'], list=[{'id': vo['id'], 'cmd': vo['cmd'], 'ms': vo['ms'], 'what': what(vo, f['voices']['suggest'])} for vo in vl],
                              inrom=sorted(int(i) for i, c in srep['fighters'].get(n, {}).get('codes', {}).items() if c))
json.dump(chars, open(os.path.join(out, 'chars.json'), 'w'))
for f in ('index.html', 'app.js', 'lab.js', 'stagepack.js', 'stages.js', 'enemypack.js', 'enemies.js', 'characters.js'): shutil.copy(os.path.join(HERE, f), os.path.join(out, f))
print('site data in', out)
