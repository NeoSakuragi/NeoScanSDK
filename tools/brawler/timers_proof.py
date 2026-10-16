#!/usr/bin/env python3
"""Notes 20261016-174640-e03d / 20261016-174702-e03d proof (game.json credit / select.time_limit_s; main.c title_go_tick,
sel_time_on): in our emulator (harness), per player system (scenario.SYSTEMS: SNK's MVS BIOS, UniBIOS on MVS hardware,
UniBIOS on AES = the console):
  MVS: a coin on the attract logo -> the title; nobody touches anything: the countdown shown beside PRESS START (title_go_s
       30 -> 1, fix row 18 col 28), then after credit.start_timeout_s the game starts by itself (the select), one credit
       taken (seen_credits: BCD, P1's coin slot); on the select nobody touches anything: after select.time_limit_s P1
       has picked the highlighted fighter, colour set A, then the fight starts.
  AES: START opens the title; nothing for longer than both limits: still the title, then START: still choosing on the
       select (no pick).
    python3 timers_proof.py [OUT.json]          (exit 1 on a failure)"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
GAME = os.path.normpath(os.path.join(HERE, '..', '..', 'examples', 'brawler'))


def worker(system):
    import harness, scenario
    harness.OPTIONS.update(scenario.SYSTEMS.get(system) or dict(geolith_system_type='uni', geolith_unibios_hw='mvs'))
    g = json.load(open(os.path.join(GAME, 'game.json')))
    T = int(g['credit']['start_timeout_s'] * 60); S = int(g['select']['time_limit_s'] * 60)
    b = harness.Brawler(); y = b.syms; r = lambda n, k=0: b.r(y[n] + k, 1)
    def until(cond, n, step=1):
        for i in range(0, n, step):
            if cond(): return i
            b.run(step)
        return None
    out = {'system': system}
    b.core.retro_reset()
    for _ in range(scenario.BOOT): b.core.retro_run()   # (the boot: no fighters in RAM yet, b.run's hit log reads them)
    until(lambda: r('mode') == 2, 3000); b.run(200)
    aes = b.r(0x10FD82, 1) == 0; out['aes'] = aes
    if not aes:
        b.seq('4:o')
        if until(lambda: r('mode') == 2 and r('attract') == 0, 600) is None: out['fail'] = 'no title after a coin'; return out
        c0 = r('seen_credits')
        secs = []
        t = until(lambda: (secs.append(r('title_go_s')) if not secs or secs[-1] != r('title_go_s') else None) or r('mode') == 0, T + 300)
        out['title_to_select_ticks'] = t; out['countdown_shown'] = secs
        b.run(5); out['credits_before_after'] = [c0, r('seen_credits')]
        out['auto_start_ok'] = t is not None and abs(t - T) <= 3 and r('mode') == 0 and c0 - r('seen_credits') == 1 \
            and [x for x in secs if x] == list(range(T // 60, 0, -1))   # (a leading 0: the title's first tick, before the clock)
        # the select: hands off
        s0 = b.frame
        t = until(lambda: r('picked') == 1, S + 300)
        out['select_to_pick_ticks'] = t; out['pick_set_p1'] = r('pick_set'); out['p2_cursor'] = r('cursor', 1)
        f = until(lambda: r('mode') == 1, 900)
        out['fight_started'] = f is not None
        out['auto_pick_ok'] = t is not None and abs(t - S) <= 6 and r('pick_set') == 0 and f is not None
        out['ok'] = out['auto_start_ok'] and out['auto_pick_ok']
    else:
        b.seq('4:s,60:-')
        if until(lambda: r('mode') == 2 and r('attract') == 0, 600) is None:
            b.seq('4:s,60:-')
        out['title'] = r('mode') == 2 and r('attract') == 0
        b.run(T + 300); out['title_after_limit'] = r('mode') == 2 and r('attract') == 0
        b.seq('4:s'); until(lambda: r('mode') == 0, 300)
        b.run(S + 300); out['still_choosing'] = r('mode') == 0 and r('sel_phase') == 0 and r('picked') == 0
        out['ok'] = out['title'] and out['title_after_limit'] and out['still_choosing']
    return out


def main():
    if len(sys.argv) > 2 and sys.argv[1] == '--worker':
        print('RESULT ' + json.dumps(worker(sys.argv[2]))); return
    res = []
    for system in ('mvs-mvs', 'uni-mvs', 'uni-aes'):
        p = subprocess.run([sys.executable, __file__, '--worker', system], capture_output=True, text=True)
        line = next((l for l in p.stdout.splitlines() if l.startswith('RESULT ')), None)
        res.append(json.loads(line[7:]) if line else {'system': system, 'ok': False, 'error': p.stderr[-2000:]})
        print(json.dumps(res[-1]), flush=True)
    if len(sys.argv) > 1: json.dump(res, open(sys.argv[1], 'w'), indent=1)
    ok = all(x.get('ok') for x in res)
    print('ALL OK' if ok else 'FAIL'); sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
