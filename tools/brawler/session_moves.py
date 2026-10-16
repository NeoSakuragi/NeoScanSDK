#!/usr/bin/env python3
"""Every move a player started in a recorded play session (docs/feedback.md "Session recording"), replayed in the
repo's Geolith core through harness.py: the session's keyframe, then its chunks' pads frame by frame; at each chunk
boundary that follows the previous chunk without a gap, the SHA-256 of the core's state is compared with the one the
Player recorded there (the drift check; a mismatch or a gap resyncs at the next keyframe, its frames not logged).

    python3 tools/brawler/session_moves.py SESSION_DIR ROM.neo GAME_DIR [--bios DIR] [--out events.json]

SESSION_DIR = the storage layout (/mnt/storagebox/brawler-sessions/<id>: meta.json, <seq>.nsin, <seq>.sha256,
<seq>.state.gz for keyframes). ROM.neo = the session's build (meta rom_sha256). GAME_DIR = examples/brawler of THAT
build, built (a git worktree at its VERSION commit, `make`: harness.py's fighter_t offsets come from its fighter.h,
the symbols from its build/rom.elf, the pools from its build/chainlab.json). --bios: the directory holding the
Player's neogeo.zip (the Lab's site copy; default /data/tmp/chainlab/site).

Logged per player fighter (0 = P1, 1 = P2), polled after every frame:
  special   S_SPECIAL entered, or a new special started in it (spec_id / spec_ix changed, or state_t restarted):
            role (spec_id: the six C slots, fury, MAX, form, air, down attack, grab special, Blitz), spec_ix -> the
            special's input in the fighter's pool (chainlab.json fighters[].pool, export_bm special_pool order),
            sthr (1 a grab special out of the hold, 2 the super throw)
  throw     S_THROW entered: throw_id (C = forward + A, D = back + A, XTHROW = hold + B / up-down + A paired throw)
            and the state it came from (GRAB: out of the hold; else the chain's back throw / the MAX chain)
  grab      S_GRAB entered (a hold)
  death     S_DEAD entered
and the game's screen (mode, stage camp, wave, phase, attract, lives, continue count, bonus_on) as it changes; an
event in a bonus game (bonus_on: mode 1 with the bonus posts) is flagged bonus."""
import argparse, gzip, hashlib, json, os, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness

ROLE = {0: 'C', 1: 'f+C', 2: 'd+C', 3: 'u+C', 4: 'df+C', 5: 'uf+C', 6: 'fury (D)', 8: 'form', 9: 'air special',
        10: 'down attack', 11: 'grab special', 12: 'Blitz'}
THROW = {0: 'forward throw (f+A)', 1: 'back throw (b+A)', 2: 'hold hit', 3: 'hold finisher (3rd A in hold)', 4: 'extra paired throw'}
MODE = {0: 'select', 1: 'fight', 2: 'title', 3: 'boss unlocked', 4: 'ending', 5: 'game over', 6: 'bonus', 7: 'ladder'}
PHASE = {0: 'wave', 1: 'go', 2: 'boss', 3: 'end', 4: 'clear'}


class Replayer(harness.Brawler):
    """harness.Brawler fed raw pad words (bit = libretro joypad id, as player.c / web_core.c)"""
    raw = (0, 0)
    def _input(self, port, dev, idx, id):
        if dev != 1 or port > 1: return 0
        if id == 256: return self.raw[port]                     # RETRO_DEVICE_ID_JOYPAD_MASK
        return (self.raw[port] >> id) & 1


def chunks_of(d):
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith('.nsin'): continue
        seq = int(f[:6]); b = open(os.path.join(d, f), 'rb').read()
        assert b[:4] == b'NSIN' and struct.unpack('<I', b[4:8])[0] == 1, f
        W, P = struct.unpack('<QQ', b[8:24])
        pads = struct.unpack('<%dH' % (2 * (P - W)), b[24:24 + 4 * (P - W)])
        sp = os.path.join(d, '%06d.sha256' % seq); kp = os.path.join(d, '%06d.state.gz' % seq)
        out.append({'seq': seq, 'W': W, 'P': P, 'pads': pads, 'sha': open(sp).read().strip() if os.path.exists(sp) else '',
                    'key': kp if os.path.exists(kp) else None})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('session'); ap.add_argument('rom'); ap.add_argument('game')
    ap.add_argument('--bios', default='/data/tmp/chainlab/site'); ap.add_argument('--out')
    a = ap.parse_args()
    meta = json.load(open(os.path.join(a.session, 'meta.json')))
    rsha = hashlib.sha256(open(a.rom, 'rb').read()).hexdigest()
    assert rsha == meta['rom_sha256'], f'ROM {rsha} is not the session build {meta["rom_sha256"]}'
    harness.SYSDIR = a.bios
    opts = {'geolith_region': meta.get('region', 'us'), 'geolith_system_type': meta.get('system_type', 'mvs'),
            'geolith_unibios_hw': meta.get('hw', 'mvs'), 'geolith_memcard': meta.get('memcard', 'off')}
    b = Replayer(rom=a.rom, game=a.game, options=opts)
    lab = json.load(open(os.path.join(a.game, 'build', 'chainlab.json')))
    pools = {f['id']: (f['name'], [p['input'] for p in f['pool']]) for f in lab['fighters']}
    S = b.syms; ram = lambda addr, n: b.r(addr, n)
    F = ['state', 'state_t', 'spec_id', 'spec_ix', 'sthr', 'fmax', 'throw_id', 'hp', 'facing', 'ch', 'team']
    F = [f for f in F if f in b.layout]
    def snap(i): return {f: b.fget(i, f) for f in F}

    cs = chunks_of(a.session)
    events, screens, checked, mism, gaps, resync = [], [], 0, [], [], 0
    prev = [None, None]; scr = None; logged = 0; drift = True; last = None
    for k, c in enumerate(cs):
        joined = last is not None and c['seq'] == last['seq'] + 1 and c['W'] == last['P']
        if not joined and last is not None: gaps.append(c['seq']); drift = True
        if joined and not drift and c['sha']:
            checked += 1
            if hashlib.sha256(b._save_core()).hexdigest() != c['sha']: mism.append(c['seq']); drift = True
        if drift:
            if not c['key']: last = c; continue                  # skipped up to the next keyframe
            b._load_core(gzip.decompress(open(c['key'], 'rb').read())); drift = False; resync += 1
            if hashlib.sha256(b._save_core()).hexdigest() != c['sha'] and c['sha']: raise SystemExit('keyframe sha mismatch')
            prev = [None, None]
        for j in range(c['P'] - c['W']):
            frame = c['W'] + j; p0, p1 = c['pads'][2 * j], c['pads'][2 * j + 1]
            if p0 & 0x8000: b.core.retro_reset()
            b.raw = (p0 & 0x7FFF, p1); b.core.retro_run(); logged += 1
            sc = (ram(S['mode'], 1), ram(S['camp'], 1), ram(S['wave'], 1), ram(S['phase'], 1), ram(S['attract'], 1),
                  ram(S['lives'], 1), ram(S['cont_t'], 2), ram(S['bonus_on'], 1))
            if sc != scr:
                screens.append({'f': frame, 'mode': MODE.get(sc[0], sc[0]), 'stage': sc[1] + 1, 'wave': sc[2] + 1,
                                'phase': PHASE.get(sc[3], sc[3]), 'attract': sc[4], 'lives': sc[5], 'cont_t': sc[6],
                                'bonus': sc[7]})
                scr = sc
            if sc[0] != 1 or sc[4]: prev = [None, None]; continue   # only the fights, never the attract demo
            for i in (0, 1):
                s = snap(i); p = prev[i]; prev[i] = s
                if not s['ch'] or p is None: continue
                cid = (s['ch'] - S['bm_chars']) // S['sizeof_bchar']; name, pool = pools.get(cid, ('?', []))
                st = b.states[s['state']] if s['state'] < len(b.states) else s['state']
                pst = b.states[p['state']] if p['state'] < len(b.states) else p['state']
                ev = None
                if st == 'SPECIAL' and (pst != 'SPECIAL' or s['spec_id'] != p['spec_id'] or s['spec_ix'] != p['spec_ix']
                                        or s['state_t'] < p['state_t']):
                    role = s['spec_id']
                    kind = 'MAX (d+D)' if role == 6 and s.get('fmax') else ROLE.get(role, role)
                    if s.get('sthr') == 2: kind = 'super throw (f/b+C in hold)'
                    elif s.get('sthr') == 1: kind = 'grab special'
                    ev = {'ev': 'special', 'kind': kind, 'spec_ix': s['spec_ix'],
                          'input': pool[s['spec_ix']] if s['spec_ix'] < len(pool) else '#%d' % s['spec_ix'], 'from': pst}
                elif st == 'THROW' and pst != 'THROW':
                    t = s['throw_id']; kind = THROW.get(t, t)
                    if t == 4: kind = 'hold+B throw' if (p0, p1)[i] & (1 << 8) else 'extra paired throw (u/d+A)'
                    if pst != 'GRAB': kind = 'chain/MAX-chain throw (' + kind + ')'
                    ev = {'ev': 'throw', 'kind': kind, 'from': pst}
                elif st == 'GRAB' and pst != 'GRAB': ev = {'ev': 'grab', 'kind': 'grab (hold)', 'from': pst}
                elif st == 'DEAD' and pst != 'DEAD': ev = {'ev': 'death', 'kind': 'death', 'from': pst}
                if ev:
                    ev.update({'f': frame, 'p': i, 'char': name, 'stage': sc[1] + 1, 'wave': sc[2] + 1, 'bonus': int(sc[7] != 0)})
                    events.append(ev)
        last = c
    total = sum(c['P'] - c['W'] for c in cs)
    res = {'session': meta['session'], 'user': meta.get('user'), 'device': meta.get('device'), 'rom_version': meta['rom_version'],
           'chunks': len(cs), 'frames': total, 'frames_logged': logged, 'checked': checked, 'mismatches': mism, 'gaps': gaps,
           'resyncs': resync, 'events': events, 'screens': screens}
    if a.out: json.dump(res, open(a.out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('events', 'screens')}))
    from collections import Counter
    for (p, ch, ev, kind, inp, bn), n in sorted(Counter((e['p'], e['char'], e['ev'], e['kind'], e.get('input', ''), e['bonus'])
                                                     for e in events).items()):
        print(f'P{p + 1} {ch:10s} {ev:8s} {kind:30s} {inp:14s} {"bonus " if bn else ""}{n}')


if __name__ == '__main__':
    main()
