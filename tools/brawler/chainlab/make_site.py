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
want = ['lab', 'fighters', 'route_tab', 'rt_tab', 'bm_chars', 'mode', 'cam_x', 'projectiles', 'attract', 'phase', 'wave', 'lock_x', 'camp', 'game_ticks', 'ai_rank', 'ai_tokens', 'lab_fields']
json.dump({'fields': layout, 'fsize': fsize, 'states': states, 'syms': {k: syms[k] for k in want if k in syms}, 'sizeof_bchar': syms.get('sizeof_bchar'),
           'version': open(os.path.join(game, 'VERSION')).read().strip()},
          open(os.path.join(out, 'layout.json'), 'w'))
from move_images import Rom
import routes, move_images                      # the move picker's pictures: each move's impact frame(s), from the ROM's tables
lab = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
lab['pics'] = move_images.move_images(game, out, [f['name'] for f in lab['fighters']], routes.MOVE_NAMES)
# the chain tool (revamp 5, chaintool.js): the chain core's rules (game.json chain), the ROM's retime rows (build/retime.json:
# the RAM table the tool writes keeps the other fighters' rows) and each fighter's piece catalogue (pieces.py: tags, appeal,
# reach, the 1C segments; the attacker's travel to the contact frame for the spacing readout)
import pieces as PC
G0 = json.load(open(os.path.join(game, 'game.json')))
lab['chain'] = {k: v for k, v in G0['chain'].items() if k != 'about'}
lab['retime_rom'] = json.load(open(os.path.join(game, 'build', 'retime.json'))) if os.path.exists(os.path.join(game, 'build', 'retime.json')) else []
_rom = Rom(os.path.join(game, 'build'))
for f in lab['fighters']:
    F = PC.Fighter(game, f['name'], _rom, lab, G0)
    cat = PC.catalogue(F)
    f['pieces'] = [dict({k: p[k] for k in ('id', 'kind', 'move', 'label', 'limb', 'height', 'weight', 'reaction', 'effect', 'reach', 'segs',
                                          'startup', 'active', 'recovery', 'hits', 'damage', 'push', 'appeal') if k in p},
                        travel=p['frames'][min(p['startup'], len(p['frames']) - 1)]['x'] if p['frames'] else 0) for p in cat]
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
import char_images, copy, select_images
SL = build_tables.select_layout(G)              # the select screen (game.json select_layout, else the first layout)
eff = copy.deepcopy(G['roster'])                # the roster with the select poses the build exports (its watch)
for r in eff: r['watch'] = dict(r['watch'], frame=build_tables.watch_of(G, r)[0][0], step=build_tables.watch_of(G, r)[0][1])
poses = char_images.pose_candidates(eff, out, os.path.join('/data/tmp/chainlab', 'tmp_poses'))
chars = {'roster': G['roster'], 'slots': sorted(SL, key=lambda n: SL[n]['slot']), 'stages': len(G['stages']),
         'pool': {f['name']: f['pool'] for f in lab['fighters']}, 'suggest': {f['name']: f['suggest'] for f in lab['fighters']},
         'poses': {n: {k: v for k, v in p.items() if k not in ('ix', 'pals')} for n, p in poses.items()},
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
        t = x['input'] if x['kind'] in ('special', 'prog') else x['event'] if x['kind'] == 'event' else \
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
# the Select screen tab: the build's select screen as data (select_images.py: the ROM's pictures, the fix layer from our
# emulator, the pose candidates above as palette indices) for selectrender.js
json.dump(select_images.select_data(game, poses), open(os.path.join(out, 'select.json'), 'w'))
for f in ('index.html', 'app.js', 'chaintool.js', 'lab.js', 'gameplay.js', 'tryit.js', 'knobui.js', 'stagepack.js', 'stages.js', 'enemypack.js', 'enemies.js', 'characters.js', 'selectrender.js', 'selectscreen.js', 'fbreplay.js', 'feedback.js', 'quirks.js', 'expose.js', 'micnote.js', 'decide.js', 'decisions.json', 'decide.html', 'review.html', 'review.js', 'anims.html', 'anims.js', 'anims_core.js', 'arbitrage.html', 'arbitrage.js', 'workshop.html', 'workshop.js', 'lab.html', 'fighterlab.js', 'sounds.html', 'sounds.js', 'impacts.html', 'impacts.js', 'kim_size.png', 'krauser_size.png', 'kim_run_frames.png'): shutil.copy(os.path.join(HERE, f), os.path.join(out, f))
# the hit sounds page (sounds.html?f=kim): each hit's impact frame + sound, every effect of the sound ROM as a WAV
# (tools/brawler/hitsounds.py -> /data/neogeo_dict/hitsounds)
HS = '/data/neogeo_dict/hitsounds'
if os.path.isdir(HS): shutil.copytree(HS, os.path.join(out, 'sounds'), dirs_exist_ok=True)
# the impact sound library (impacts.html): every hit / impact sound of KOF94 / 95 / 96 and Kizuna, decoded from their ROMs
# (tools/brawler/impacts.py -> /data/neogeo_dict/sound/impacts: impacts.json + wav/)
IMP = '/data/neogeo_dict/sound/impacts'
if os.path.exists(os.path.join(IMP, 'impacts.json')):
    os.makedirs(os.path.join(out, 'impacts'), exist_ok=True)
    shutil.copy(os.path.join(IMP, 'impacts.json'), os.path.join(out, 'impacts', 'impacts.json'))
    shutil.copytree(os.path.join(IMP, 'wav'), os.path.join(out, 'impacts', 'wav'), dirs_exist_ok=True)
# the fighter review pages (revamp phase 4, review.html): pieces, appeal, my proposal, clips (tools/brawler/review_build.py)
import review_build
review_build.build(out, game, review_build.REVIEW, Rom(os.path.join(game, 'build')), lab, G)
# the animation dictionaries (anims.html?f=kim / krauser / robert, the review picker's "All animations"): every animation of the
# fighter's table (tools/brawler/animdict.py: Kim's Kizuna table, Krauser's KOF96 table, Robert's KOF98 table)
import animdict
animdict.build(out, game)
# the arbitration sheets (arbitrage.html?f=kim / krauser / robert): what the game plays now in each slot, as dictionary animations
import arbitrage
arbitrage.build(out, game)
# the Workshops (workshop.html?f=kim / krauser / robert): each fighter's specials / throws with their piece ids (S- / T-,
# tools/brawler/arb_pieces/<f>_ids.json), locked ones, every animation's hit classes (tools/brawler/workshop.py)
import workshop
workshop.build(out, game)
print('site data in', out)

# "Oldies quirks" tab: quirks.json + its images (paths in quirks.json are relative to QUIRK_SRC; copied under quirks/)
QUIRK_SRC = '/data/study'
qj = os.path.join(HERE, 'quirks.json')
if os.path.exists(qj):
    Q = json.load(open(qj))
    for q in Q.get('quirks', []):
        for sh in q.get('shots', []):
            src = os.path.join(QUIRK_SRC, sh['src'])
            if os.path.exists(src):
                dst = os.path.join(out, 'quirks', sh['src']); os.makedirs(os.path.dirname(dst), exist_ok=True); shutil.copy(src, dst)
    shutil.copy(qj, os.path.join(out, 'quirks.json'))

# "Classic Brawlers' Exposé" tab: the encyclopedia JSONs (/data/study/encyclopedia/<set>.json) -> expose/ + index.json
ENC = '/data/study/encyclopedia'
if os.path.isdir(ENC):
    os.makedirs(os.path.join(out, 'expose'), exist_ok=True)
    games = sorted(f for f in os.listdir(ENC) if f.endswith('.json'))
    for f in games: shutil.copy(os.path.join(ENC, f), os.path.join(out, 'expose', f))
    if os.path.exists(os.path.join(HERE, 'synthesis.json')): shutil.copy(os.path.join(HERE, 'synthesis.json'), os.path.join(out, 'expose', 'synthesis.json'))
    json.dump({'games': games, 'intro': "The beat 'em ups behind the brawler's gameplay revamp, measured: every playable character's movement, jump arc and moves (startup / active / recovery, damage, hit-stop, boxes), each game's system rules, and the enemies' AI."},
              open(os.path.join(out, 'expose', 'index.json'), 'w'))
# "Try in game" (tryit.js): the Lab builds of this game dir (make LAB_FIGHTER=<f>) under rom/ (tryit_site.py)
import tryit_site
tryit_site.write(out, game)
# the Fighter Lab (lab.html: the cast grid, then Info / Workshop / Assembly per fighter, fighterlab.js): cast.json + the
# HUD faces and win portraits, from game.json's roster and what this site now holds (fighterlab.py)
import fighterlab
fighterlab.build(out, game)
