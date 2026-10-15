#!/usr/bin/env python3
"""Note 20261014-172113-5d29 proof: the stage clear's music starts only once the KO'd boss has come to rest on the floor
(its final landing, after every bounce) and the landing sound has played out (game.json hit_sounds.rest_music), never
earlier, nothing else starting it (main.c boss_ko_tick / ko_at_rest). Our emulator (harness), the scenario setups
(scenario.py setup: stage mode, the boss reached as scenarios.json boss-* do: wave 99, his scene played out). Cases (the
beta's four bosses): a light hit (an A string: the T9 bosses guard a lone normal, gd_max breaks it), a heavy hit, a fury
against the stage's right wall, the boss's life run out high in a knockdown flight there (an air KO off the wall), the
minions still up (their falls during the slow motion), 2 players. The boss keeps his full life until the killing hit
(at red_low % he plays his MAX and fury, untouchable): the first hit that lands (not guarded) is replayed with him at 1
life; the boss's AI may guard / jump away / attack, so P1 is put in front again and the keys replayed until one lands.
Per frame: the boss's state / y / anim, every byte sent to REG_SOUND (the sound queue's head), the phase.

    python3 rest_music_proof.py [OUT_DIR [CASE]]   -> rest_music.json (timelines + checks), exit 1 on a failed check"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from harness import Brawler
import scenario

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/rest_music/out'
os.makedirs(OUT, exist_ok=True)
G = json.load(open(os.path.join(scenario.GAME, 'game.json')))
REST = G['hit_sounds']['rest_music']
FURY_MAX = G['meter']['fury_max']
A6 = ','.join(['3:a,7:-'] * 6)                          # an A string (the T9 bosses guard a lone normal: gd_max breaks it)
C4 = ','.join(['3:c,14:-'] * 4)
CASES = {                                                # the beta's bosses as scenarios.json boss-* (wave 99): stage 0
    'light_a':    dict(setup=dict(mode='stage', fighter='terry', stage=0, wave=99, alone=True, gap=50), keys=A6),   # Mr. Big
    'heavy_c':    dict(setup=dict(mode='stage', fighter='terry', stage=1, wave=99, alone=True, gap=50), keys=C4),   # Krauser
    'wall_fury':  dict(setup=dict(mode='stage', fighter='terry', stage=2, wave=99, alone=True, gap=50, fury='full'), keys='3:d', wall=True),   # Geese
    'air_wall':   dict(setup=dict(mode='stage', fighter='terry', stage=0, wave=99, alone=True, gap=50, fury='full'), keys='3:d', wall=True, air_kill=True),   # Mr. Big
    'minions':    dict(setup=dict(mode='stage', fighter='terry', stage=1, wave=99, gap=50), keys=C4),
    'two_player': dict(setup=dict(mode='stage', fighter='terry', stage=3, wave=99, alone=True, gap=50), keys=A6, p2=True),   # Rugal
}

def run_case(name, c):
    b = Brawler(); b.game = scenario.GAME; S = b.syms; ST = b.states
    st = dict(c['setup']); alone = st.pop('alone', False); gap = st.pop('gap'); st.pop('wait', None)
    scenario.setup(b, dict(setup=st))                    # the boss's wave, then his scene (drama) played out
    for _ in range(3000):
        if b.r(S['dr_on'], 1) == 0 and b.r(S['phase'], 1) == 2 and b.fget(2, 'state') == ST.index('IDLE'): break
        b.run(1)
    b.run(60)
    if c.get('p2'):                                      # P2 joins (a credit, his START)
        b.seq('4:o,30:-'); b.seq('4:s,60:-', p=1)
    if alone:
        for i in range(3, 8): b.fset(i, 'state', ST.index('OFF'))
    for _ in range(600):                                 # the boss standing (not mid-attack) when P1 is put in front
        if b.fget(2, 'state') == ST.index('IDLE'): break
        b.run(1)
    full = b.fget(2, 'hp_max') or b.fget(2, 'hp'); b.fset(2, 'hp', full)   # full life: no red period before the
    # killing hit (at red_low % of his life the T9 boss blinks red and plays his MAX, then his fury: untouchable)
    def cam():
        x = b.r(S['cam_x'], 2); return x - 65536 if x > 32767 else x
    def place():                                         # P1 in front of the boss, on his line (or both at the wall)
        if c.get('wall'): b.fset(2, 'x', cam() + 300); b.fset(0, 'x', cam() + 260); b.fset(0, 'facing', 1)
        elif b.fget(2, 'x') - cam() > gap + 24: b.fset(0, 'x', b.fget(2, 'x') - gap); b.fset(0, 'facing', 1)
        else: b.fset(0, 'x', b.fget(2, 'x') + gap); b.fset(0, 'facing', -1 & 0xFF)
        b.fset(0, 'z', b.fget(2, 'z'))
        if 'fury' in st: b.fset(0, 'fgauge', FURY_MAX)
    place(); b.run(1)
    p2 = b.fget(1, 'state') != ST.index('OFF')
    qh = b.r(S['qh'], 1); rows = []; t = 0
    keys = [(int(n), k.replace('-', '')) for n, k in (p.split(':') for p in c['keys'].split(','))]
    seq = [k for n, k in keys for _ in range(n)]
    free = [ST.index(s) for s in ('IDLE', 'WALK')]; hurt = [ST.index(s) for s in ('HITSTUN', 'KNOCKDOWN', 'DOWN', 'GETUP', 'GRABBED', 'THROWN')]
    pos = 0                                              # the attempt: the case's keys from P1 placed; the boss's AI may
    while t < 1400:                                      # guard / jump away / attack: once both stand free, again
        ko = b.r(S['ko_seq'], 1)
        if not ko:
            b.fset(0, 'hp', b.fget(0, 'hp_max') or 120)  # (P1 never loses his life on the way)
            if pos >= len(seq) + 20 and b.fget(0, 'state') in free and b.fget(2, 'state') not in hurt: place(); pos = 0
        k = seq[pos] if pos < len(seq) else ''; pos += 1
        if not c.get('air_kill') and not ko:             # the first hit that LANDS (not guarded) is the killing one:
            snap, hp0 = b.save(), b.fget(2, 'hp')         # the frame replayed with the boss at 1 life
            b.run(1, p1=k)
            if 0 < b.fget(2, 'hp') < hp0:
                b.load(snap); b.fset(2, 'hp', 1); b.run(1, p1=k)
        else: b.run(1, p1=k)
        t += 1
        if c.get('air_kill') and not b.r(S['ko_seq'], 1) and b.fget(2, 'state') == ST.index('KNOCKDOWN') and b.fget(2, 'y') > 20 and b.fget(2, 'hp') > 0:
            b.fset(2, 'hp', 0)                           # its life runs out high in its flight (off the wall): an air KO
        h = b.r(S['qh'], 1); sent = []
        while qh != h: sent.append(b.r(S['q'] + qh, 1)); qh = (qh + 1) & 31
        rows.append(dict(f=t, ko=b.r(S['ko_seq'], 1), ko_t=b.r(S['ko_t'], 2), phase=b.r(S['phase'], 1), mode=b.r(S['mode'], 1),
                         state=ST[b.fget(2, 'state')], x=round(b.fget(2, 'x') - (b.r(S['cam_x'], 2) - (65536 if b.r(S['cam_x'], 2) > 32767 else 0))), y=round(b.fget(2, 'y'), 1), anim=b.fget(2, 'anim'),
                         thud=b.fget(2, 'kthud'), sent=sent,
                         up=sum(b.fget(i, 'state') not in (ST.index('OFF'), ST.index('DEAD')) for i in range(3, 8))))
        if rows[-1]['mode'] != 1 or (rows[-1]['phase'] != 4 and len(rows) > 2 and rows[-2]['phase'] == 4): break
    # events: the killing hit, every landing sound ($1A $B1), the rest (first S_DOWN / DEAD / OFF on the floor), the music
    ev = dict(p2_in=p2)
    flat = [(r['f'], x) for r in rows for x in r['sent']]
    ko = next((r['f'] for r in rows if r['ko']), None)
    lands = [flat[i + 1][0] for i in range(len(flat) - 1) if flat[i][1] == 0x1A and flat[i + 1][1] == G_BOUNCE]
    rest = next((r['f'] for r in rows if r['ko'] and r['state'] in ('DOWN', 'DEAD', 'OFF') and r['y'] <= 0), None)
    mus = [(flat[i][0], flat[i + 1][1]) for i in range(len(flat) - 1) if flat[i][1] == 0x07 and flat[i][0] > (ko or 0)]
    nxt = next((r['f'] for r in rows if r['mode'] != 1 or (r['phase'] != 4 and r['f'] > 1 and rows[r['f'] - 2]['phase'] == 4)), None)
    ev['minions_up_at_ko'] = next((r['up'] for r in rows if r['f'] == ko), None)
    ev.update(ko=ko, landing_sounds=lands, rest=rest, music=mus, next_screen=nxt)
    m = mus[0][0] if mus else None
    ev['checks'] = dict(
        one_music_start=len(mus) == 1,
        music_after_rest=bool(m and rest and m > rest),
        music_after_last_landing_sound_ends=bool(m and (not lands or m - lands[-1] >= REST)),
        no_landing_sound_after_music=bool(m and all(l < m for l in lands)),
        next_screen_after_music=bool(m and (nxt is None or nxt > m)))
    ev['gap_last_landing_to_music'] = m - lands[-1] if m and lands else None
    ev['timeline'] = [r for r in rows if ko and r['f'] >= ko - 2 and (r['sent'] or r['f'] == ko or r['f'] == rest)]
    return ev

songs = json.load(open(os.path.join(scenario.GAME, 'songs.json')))['sfx']['names']
G_BOUNCE = next(int(k, 16) for k, v in songs.items() if v.upper() == G['hit_sounds']['bounce'].upper())
if len(sys.argv) < 3:                                    # every case in its own process (one core per process)
    import subprocess
    res, ok = {}, True
    for n in CASES:
        d = os.path.join(OUT, n); r = subprocess.run([sys.executable, __file__, d, n]); ok &= r.returncode == 0
        res[n] = json.load(open(os.path.join(d, 'rest_music.json')))['cases'][n]
    json.dump(dict(rest_music=REST, cases=res), open(os.path.join(OUT, 'rest_music.json'), 'w'), indent=1)
    sys.exit(0 if ok else 1)
res = {}
only = sys.argv[2].split(',')
for n in only:
    res[n] = run_case(n, CASES[n])
    e = res[n]
    print(n, 'p2' if e['p2_in'] else '', 'ko', e['ko'], 'minions', e['minions_up_at_ko'], 'lands', e['landing_sounds'], 'rest', e['rest'], 'music', e['music'],
          'gap', e['gap_last_landing_to_music'], 'next', e['next_screen'], 'FAIL' if not all(e['checks'].values()) else 'ok',
          [k for k, v in e['checks'].items() if not v])
json.dump(dict(rest_music=REST, cases=res), open(os.path.join(OUT, 'rest_music.json'), 'w'), indent=1)
sys.exit(0 if all(all(e['checks'].values()) for e in res.values()) else 1)
