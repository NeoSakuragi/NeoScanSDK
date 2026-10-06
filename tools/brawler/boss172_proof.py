#!/usr/bin/env python3
"""TODO #172 proof: the boss's death sequence (main.c "the boss's death", docs/brawler_move_vocabulary.md
stage.boss_death), our emulator's core (harness), a normal build (the enemies' AI on).

    python3 boss172_proof.py [OUT_DIR] [STAGE] [FIGHTER]   (default /data/tmp/boss172/out, stage 1 = STAGE 2 Krauser
                                                            + 3 minions, P1 Terry)

The Brawler Lab's "play from here" (lab req 4) at the boss; after his scene and the minions' walk-in the boss's life is
set to 1 (test poke) and placed in front of P1, who presses A until the killing hit lands. From there, every frame:
P1's keys keep pressing (A, B, the stick) and must do nothing; the log: the input-off frame (ko_seq set), the slow
motion's span (the boss's state_t: one logic tick in KO_RATE frames, then every frame), the voices sent (the sound
queue: prefix $1E / $17 = an enemy's voice), each minion's fall (life 0, its state), PH_END, STAGE CLEAR.
Out: boss172.json (timing log + pass checks), boss172_sheet.png."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/boss172/out'
STAGE = int(sys.argv[2]) if len(sys.argv) > 2 else 1
FIGHTER = int(sys.argv[3]) if len(sys.argv) > 3 else 0
os.makedirs(OUT, exist_ok=True)
BOOT_FRAMES = 400
PH_BOSS, PH_END, PH_CLEAR = 2, 3, 4
b = Brawler(); S = b.syms; ST = b.states
def r1(n): return b.r(S[n], 1)
def r2(n): return b.r(S[n], 2)
OFF, DEAD = ST.index('OFF'), ST.index('DEAD')

b.core.retro_reset(); b.frame = 0
for _ in range(BOOT_FRAMES): b.core.retro_run()
L = S['lab']
for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
b.w(L + 13, 1, 99); b.w(L + 5, 1, FIGHTER); b.w(L + 6, 1, STAGE); b.w(L + 4, 1, 4)   # req 4: the boss of STAGE
b.run(1)
for k in range(3000):                                       # the boss's scene, then his fight
    if r1('mode') == 1 and r1('phase') == PH_BOSS and not r1('dr_on'): break
    b.run(1, p1='a' if k % 20 == 0 else '')
b.run(200)                                                  # the minions walk in
mins = [i for i in range(3, 8) if b.fget(i, 'state') != OFF]
print('boss', b.char_of(2), 'hp', b.fget(2, 'hp'), 'minions', mins, [b.states[b.fget(i, 'state')] for i in mins])
assert len(mins) >= 3, mins

shots = []
def shot(label):
    p = f'{OUT}/_{len(shots):02d}.png'; b.screenshot(p); shots.append((p, label))

# the killing hit: the boss at life 1 in front of P1, A pressed
qprev = r1('qt'); sounds = []
def sound_log(bb):
    global qprev
    qt = bb.r(S['qt'], 1)
    while qprev != qt:
        sounds.append((bb.frame, bb.r(S['q'] + qprev, 1))); qprev = (qprev + 1) & 31
for t in range(200):
    if r1('ko_seq'): break
    if t % 30 == 0:
        b.fset(2, 'hp', 1); b.fset(2, 'inv', 0)
        b.place(2, x=b.fget(0, 'x') + 45 * b.fget(0, 'facing'), z=b.fget(0, 'z'))
        b.fset(2, 'facing', -b.fget(0, 'facing') & 0xFF)
    b.run(1, p1='a' if t % 6 < 2 else '', each=sound_log)
assert r1('ko_seq'), 'no killing hit'
f0 = b.frame; shot('the killing hit (input off, slow motion on)')
print('killing hit at frame', f0, 'minions alive', [(i, b.fget(i, 'hp')) for i in mins])
log = []; prev_st = {}; falls = {}; p1x = []; bt = []; phase_at = {}
keys = ['R', 'a', 'L', 'b', 'Ra', 'U', 'c', 'd']
SHOT_AT = (20, 60, 100, 140, 180, 230, 290, 320, 380)
for t in range(1, 1200):
    k = keys[(t // 7) % len(keys)] if t % 7 < 3 else ''   # P1 keeps pressing: nothing may happen
    if t in SHOT_AT:
        b.pad = [set(k), set()]; p = f'{OUT}/_{len(shots):02d}.png'; b._want_video = True
        b.run(1, p1=k, each=sound_log); b._want_video = False
        from PIL import Image as I
        data, w, h, pitch = b._video
        I.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB').save(p)
        shots.append((p, f'+{t} f: ko_t {r2("ko_t")} ' + ' '.join(f'{i}:{ST[b.fget(i, "state")][:4]}' for i in [2] + mins)))
    else:
        b.run(1, p1=k, each=sound_log)
    row = dict(t=t, ko_seq=r1('ko_seq'), ko_t=r2('ko_t'), phase=r1('phase'), boss=(ST[b.fget(2, 'state')], b.fget(2, 'state_t')),
               p1=(ST[b.fget(0, 'state')], round(b.fget(0, 'x'), 2), b.fget(0, 'hp'), b.fget(0, 'inv')),
               mins={i: (ST[b.fget(i, 'state')], b.fget(i, 'hp')) for i in mins})
    log.append(row); bt.append(b.fget(2, 'state_t'))
    for i in mins:
        if i not in falls and b.fget(i, 'hp') <= 0: falls[i] = t
    if row['phase'] not in phase_at: phase_at[row['phase']] = t
    if row['phase'] == PH_CLEAR and t > phase_at[PH_CLEAR] + 40:
        shot(f'+{t}: STAGE CLEAR'); break

# slow motion: the boss's state_t (it counts logic ticks) per frame
ticks = [i for i in range(1, len(bt)) if bt[i] != bt[i - 1] or log[i]['boss'][0] != log[i - 1]['boss'][0]]
slow_end = next(r['t'] for r in log if r['ko_seq'] == 2)
gaps_slow = sorted(set(ticks[j + 1] - ticks[j] for j in range(len(ticks) - 1) if ticks[j + 1] < slow_end - 3))
pairs, j = [], 0                                            # the queue: a prefix byte, then its code
while j + 1 < len(sounds):
    if sounds[j][1] in (0x1A, 0x07, 0x1C, 0x1B, 0x1E, 0x17): pairs.append((sounds[j][0], sounds[j][1], sounds[j + 1][1])); j += 2
    else: j += 1
voices = [(f - f0, p, c) for f, p, c in pairs if p in (0x1E, 0x17, 0x1C, 0x1B) and f >= f0 - 1]
enemy_voices = [v for v in voices if v[1] in (0x1E, 0x17)]
idle_at = next(r['t'] for r in log if r['p1'][0] == 'IDLE')   # its attack in progress at the kill ends (slowed)
p1_moves = [r for r in log if r['p1'][0] != 'IDLE' and r['t'] > idle_at]
res = dict(stage=STAGE, fighter=FIGHTER, kill_frame=f0, input_off_frame=f0, slow_motion=[0, slow_end],
           logic_tick_gaps_in_slow_motion=gaps_slow, minion_falls={str(i): falls.get(i) for i in mins},
           voices_after_kill=voices, phase_end_at=phase_at.get(PH_END), stage_clear_at=phase_at.get(PH_CLEAR),
           p1_attack_at_kill_ends=idle_at, p1_not_idle_after=len(p1_moves), p1_hp=[min(r['p1'][2] for r in log), max(r['p1'][2] for r in log)],
           p1_x=[min(r['p1'][1] for r in log), max(r['p1'][1] for r in log)])
fall_t = sorted(v for v in falls.values() if v is not None)
res['checks'] = dict(
    slow_motion_rate_3=gaps_slow == [3],
    slow_motion_5s=abs(slow_end - 300) <= 1,
    boss_scream_first=bool(enemy_voices) and enemy_voices[0][0] <= 1,
    one_death_voice_per_minion=len(enemy_voices) == 1 + len(mins),
    minions_staggered=len(fall_t) == len(mins) and all(fall_t[j + 1] - fall_t[j] >= 30 for j in range(len(fall_t) - 1)),
    voices_staggered=all(enemy_voices[j + 1][0] - enemy_voices[j][0] >= 30 for j in range(len(enemy_voices) - 1)),
    p1_frozen=len(p1_moves) == 0 and res['p1_x'][1] - res['p1_x'][0] < 40,
    no_life_lost=res['p1_hp'][0] == res['p1_hp'][1],
    stage_clear=phase_at.get(PH_CLEAR) is not None)
json.dump(dict(res, log=log[:420]), open(f'{OUT}/boss172.json', 'w'), indent=1)
for k, v in res.items():
    if k != 'checks': print(k, v)
print('checks', res['checks'], 'ALL PASS' if all(res['checks'].values()) else 'FAIL')
ims = [(Image.open(p), l) for p, l in shots]
w, h = ims[0][0].size; cols = 4; rows = (len(ims) + cols - 1) // cols
sheet = Image.new('RGB', (cols * w, rows * (h + 14)), 'white'); d = ImageDraw.Draw(sheet)
for i, (im, l) in enumerate(ims):
    x, y = (i % cols) * w, (i // cols) * (h + 14); sheet.paste(im, (x, y + 14)); d.rectangle([x, y + 14, x + w - 1, y + 13 + h], outline='black'); d.text((x + 2, y + 1), l, fill='black')
sheet.save(f'{OUT}/boss172_sheet.png')
for p, _ in shots: os.remove(p)
print('sheet', f'{OUT}/boss172_sheet.png')
