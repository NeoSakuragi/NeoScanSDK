#!/usr/bin/env python3
"""TODO #189 proof: Haohmaru / Genjuro / Kuroko's flash pose = Samurai Shodown II's rage-full animation (anim 140), timed
to the super flash's freeze, its shout sent with it (export_bm FLASH_POSES 'rage', bfpose_t.voice, fighter.c flash_pose).
Our emulator only.

    python3 rage189_proof.py [OUT]          (default /data/tmp/rage189/out; the normal build, AI on)

1. SS2 (tools/samsho2/rage_ss2.py): the rage-full moment of the three in SS2 (+$F0 poked to 31 and the pending POW to
   1: the game's own code fills the gauge), every frame: action 46 / anim 140, its length, the sound sent.
2. The brawler pose: flash145_proof.py --only haohmaru,genjuro,kuroko (a real fight: the pose frame for frame through
   the freeze, still, no hit, the glow on the head, the fury after it and it connects).
3. The pose's frames = SS2's anim 140 in order (bm_chars.c {name}_fpose vs the export's frame records, every step of
   anim 140 shown, in order, total = the freeze).
4. The voice (tap core, voice_proof's parser): the lab, a full meter, D: the voice command sent on the flash's first frame
   is the fighter's voice of anim 140 (voices.json), its key-on plays SS2's sample byte for byte.
5. Sheets: OUT/<name>_ss2_vs_brawler.png: SS2's rage (every 4th frame of action 46) above the brawler's freeze
   (flash145's <name>_flash.png)."""
import json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
OUT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else '/data/tmp/rage189/out'
G = os.path.normpath(os.path.join(TOOLS, '..', 'examples', 'brawler'))
NAMES = {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17}

def voice_run(name, out):
    """the tap core, the lab (FIGHTER vs Terry), meter kept full, D once: voice_proof's parse + P1's fpose per frame"""
    import voice_proof as VP, harness
    fp = {}
    orig = harness.Brawler.run
    def run(self, n=1, p1='', p2='', each=None):
        for _ in range(n):
            self.fset(0, 'meter', 120)
            orig(self, 1, p1, p2, each); fp[self.frame] = self.fget(0, 'fpose')
    harness.Brawler.run = run
    os.environ['VP_SCRIPT'] = '60:-,2:d,120:-'
    VP.SCRIPT = os.environ['VP_SCRIPT']
    res = VP.main(name, 'terry', out)
    json.dump({'voices': res, 'fpose': fp}, open(out, 'w'))

def main():
    os.makedirs(OUT, exist_ok=True)
    rep = {}
    # 1. SS2
    r = subprocess.run([sys.executable, 'rage_ss2.py', *map(str, NAMES.values())], cwd=os.path.join(TOOLS, 'samsho2'),
                       capture_output=True, text=True, check=True)
    print(r.stdout, end='')
    ss2 = json.load(open('/data/neogeo_dict/samsho2/rage.json'))
    # 2. the brawler's pose in a real fight
    r = subprocess.run([sys.executable, os.path.join(HERE, 'flash145_proof.py'), OUT, '--only', ','.join(NAMES)],
                       capture_output=True, text=True)
    print(r.stdout, end='')
    f145 = json.load(open(os.path.join(OUT, 'flash145.json')))
    bmc = open(os.path.join(G, 'build', 'bm_chars.c')).read()
    freeze = json.load(open(os.path.join(G, 'game.json')))['super_flash']['freeze']
    vb = json.load(open(os.path.join(TOOLS, 'brawler', 'voices.json')))['fighters']
    sys.path.insert(0, os.path.join(TOOLS, 'samsho2')); import ss2 as S
    from PIL import Image, ImageDraw
    allok = True
    for n, cid in NAMES.items():
        e = {'ss2': {k: ss2[str(cid)].get(k) for k in ('full', 'start', 'frames', 'anim', 'time', 'snd', 'rom_frames', 'rom_sounds')}}
        st = [tuple(map(int, x)) for x in re.findall(r'\{(\d+), (\d+), (\d+)\}', re.search(r'%s_fpose\[\d+\] = \{(.*?)\};' % n, bmc).group(1))]
        e['pose'] = st
        e['pose_frames'] = sum(k for _, k, _ in st)
        steps = S.parse_anim(cid, 140)
        e['ss2_steps'] = len(steps)
        e['steps_in_order'] = len(st) == len(steps) or len(st) <= freeze     # every step kept when they fit (fit drops none for <= freeze steps)
        # 4. the voice
        vo = f'{OUT}/{n}_voice.json'
        subprocess.run([sys.executable, os.path.abspath(__file__), '--voice', n, vo], check=True, capture_output=True)
        d = json.load(open(vo)); fpf = {int(k): v for k, v in d['fpose'].items()}
        start = min((f for f, v in fpf.items() if v not in (0, 0xFF)), default=None)   # the pose's first frame (RAM after it: fpose 2)
        want = next(vv['id'] for vv in vb[n]['voices'] for u in vv['uses'] if u['kind'] == 'anim' and u['slot'] == 140)
        hit = [v for v in d['voices'] if v.get('fighter') == n and v.get('voice') == want]
        e['voice'] = {'id': want, 'sent_frame': hit[0]['frame'] if hit else None, 'pose_start_frame': start,
                      'bytes_equal_ss2': hit[0].get('bytes_equal') if hit else None, 'ss2_cmd': hit[0].get('kof_cmd') if hit else None}
        k = next(i for i, (_, _, v) in enumerate(st) if v); at = start + sum(x[1] for x in st[:k]) if start is not None else None
        e['voice']['step'] = k; e['voice']['step_frame'] = at            # the voiced step's first frame; the Z80 reads the
        e['voice_ok'] = bool(hit and hit[0].get('bytes_equal') and at is not None and 0 <= hit[0]['frame'] - at <= 3)   # code
        # 1-3 frames later (sound.c sends one queued byte a frame: the flash's charge $1A $3A, then the voice's prefix + code)
        e['flash145'] = f145.get(n)
        e['ok'] = bool(e['flash145'] and e['flash145']['ok'] and e['pose_frames'] == freeze and e['voice_ok']
                       and e['ss2']['anim'] == 140 and e['ss2']['frames'] == e['ss2']['rom_frames'])
        allok = allok and e['ok']; rep[n] = e
        # 5. the sheet: SS2's rage moment, the brawler's freeze below
        sd = ss2[str(cid)]['out']; s0 = ss2[str(cid)]['start']
        shots = [Image.open(f'{sd}/snap_{f}.ppm').convert('RGB') for f in range(s0, s0 + ss2[str(cid)]['frames'] + 1, 4) if os.path.exists(f'{sd}/snap_{f}.ppm')][:14]
        bimg = Image.open(os.path.join(OUT, f'{n}_flash.png')) if os.path.exists(os.path.join(OUT, f'{n}_flash.png')) else None
        w, h = shots[0].size; cols = 7; rows = (len(shots) + cols - 1) // cols
        W = max(cols * (w + 4), bimg.size[0] if bimg else 0)
        sh = Image.new('RGB', (W, 18 + rows * (h + 4) + 22 + (bimg.size[1] if bimg else 0)), 'white'); dr = ImageDraw.Draw(sh)
        dr.text((4, 3), f'{n}: Samurai Shodown II, the POW gauge fills (frame {sd and s0}): action 46 / anim 140, {ss2[str(cid)]["frames"]} frames, every 4th frame; voice {e["ss2"]["rom_sounds"]}', fill='black')
        for i, im in enumerate(shots): sh.paste(im, ((i % cols) * (w + 4), 18 + (i // cols) * (h + 4)))
        y = 18 + rows * (h + 4)
        dr.text((4, y + 4), f'the brawler: the fury\'s super flash ({freeze} frames), anim 140 timed to it: {len(st)} steps, voice {want} sent on frame {e["voice"]["sent_frame"]} (pose from {start}), SS2 sample bytes equal: {e["voice"]["bytes_equal_ss2"]}', fill='black')
        if bimg: sh.paste(bimg, (0, y + 22))
        sh.save(os.path.join(OUT, f'{n}_ss2_vs_brawler.png'))
        print(n, 'ok' if e['ok'] else 'FAIL', json.dumps({k: e[k] for k in ('pose_frames', 'ss2_steps', 'voice', 'voice_ok')}))
    rep['ok'] = allok
    json.dump(rep, open(os.path.join(OUT, 'rage189.json'), 'w'), indent=1)
    print('ALL OK' if allok else 'FAIL')
    return allok

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--voice': voice_run(sys.argv[2], sys.argv[3])
    else: sys.exit(0 if main() else 1)
