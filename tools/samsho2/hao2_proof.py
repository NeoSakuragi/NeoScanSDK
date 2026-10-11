#!/usr/bin/env python3
"""Haohmaru round 2 (notes 20261011-112056 / 112545 / 120326 / 115835-5d29) in the brawler, our emulator's core with the
Z80 port tap (voice_proof's build), the Chain Lab's training (scenario.setup: the game's own path), Ryo the dummy.

  voices    C (623AB Kogetsuzan) and the MAX (down + D, red, gauge full: 34123421BC Tenha Fuujinzan): the voice command the
            Z80 reads in the move's first frames (the player's voice prefix + code -> his voice id, snd_report), its
            ADPCM-A key-on, the keyed V ROM bytes == SS2's own sample (voices.json segments in samsho2's V ROM) and the
            voice = the one SS2 sends at that move's start (voices.json 'special' use at 0)
  tenha     the MAX's hits: count, the wind's row (= its SS2 step) at each, the dummy standing (HITSTUN, y 0) after every
            hit but the last, launched (KNOCKDOWN, rising) by the last; Haohmaru held in each hit-stop (his freeze);
            against SS2's decode (handlers_ss2.TENHA_HITS: his steps the wind's 12 SS2 hits land on,
            11 reels then the launch; measured by tenha_ss2.py), the total = the MAX tier
  hitstop   every SS2 special hit of the runs (C, the dd Blitz 214A, the MAX, the uu Blitz 623C): attacker and victim
            frozen on a hit of his own step, the victim on an object's (the Kogetsuzan crescent: objects never hold
            their thrower, the engine's rule)
  juggle    dd + A (214A, knocks down) then C (623AB) cancelled on the hit: the knocked-down dummy is hittable in the air
            (kmode KM_HURT) and 623AB hits it there (a second hit, the dummy airborne)
  low       A, A, down + A: the down finisher plays atk_ab_close = SS2's crouching C+D (anim 352, moves "$160") and hits

    python3 hao2_proof.py ROM OUT.json"""
import ctypes as C, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, HERE); sys.path.insert(0, B)
import harness, voices as V, scenario as S
harness.CORE = '/data/neogeo_dict/sound/snd98/ff3/geolith_tap.so'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
KM_HURT = 4

def main(rom, out):
    game = S.snapshot(rom)
    b = harness.Brawler(rom=rom, game=game); b.game = game
    log = []; a = [0, 0]
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 4: a[0] = v
            elif p == 6: a[1] = v
            elif p == 7: log.append((b.frame, 'b', a[1], v))
        elif p == 0 and v: log.append((b.frame, 'c', v, 0))
        return v
    cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    rep = json.load(open(os.path.join(harness.GAME, 'build', 'snd', 'snd_report.json')))['voices']
    m1 = open(os.path.join(harness.GAME, 'build', 'snd', 'm1.bin'), 'rb').read()
    vrom = open(os.path.join(harness.GAME, 'build', 'snd', 'v1.bin'), 'rb').read()
    hdr = open(os.path.join(harness.GAME, 'build', 'bm_chars.h')).read()
    ba = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', hdr).group(1).split(', ')
    bank = json.load(open(V.JSON))['fighters']['haohmaru']['voices']; v2 = V.v_rom('samsho2')
    codes = {int(c): int(i) for i, c in rep['fighters']['haohmaru']['codes'].items()}
    ov = rep['overflow']
    TAB = {int(p, 16): 0x484C for p in rep['prefixes']}; TAB.update({int(p, 16): 0x544C for p in ov['prefixes']})
    PL = {int(rep['prefixes'][0], 16): 0, int(ov['prefixes'][0], 16): 0x100,     # his voice slot, and the other one his
          int(rep['prefixes'][1], 16): 0, int(ov['prefixes'][1], 16): 0x100}    # 'fx' voices play on (SS2's $1A sounds)

    def voices_in(f0, f1):
        """the player's voice commands read in frames f0..f1 -> [(frame, voice id, keyed bytes == SS2's)]"""
        res, want, pend, reg = [], None, None, {}
        for f, kind, x, y in log:
            if kind == 'c':
                if want is not None:
                    if f0 <= f <= f1 and want in PL: pend = (want, x, f)
                    want = None
                elif x in TAB: want = x
                continue
            reg[x] = y
            if pend and x == 0 and y and not y & 0x80:
                ch = (y & -y).bit_length() - 1
                st, en = reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0), reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)
                r = TAB[pend[0]] + 6 * pend[1]
                if (st, en) != (m1[r + 1] | m1[r + 2] << 8, m1[r + 3] | m1[r + 4] << 8): continue
                vid = codes.get(pend[1] | PL[pend[0]])
                vo = bank[vid - 1] if vid else None
                eq = bool(vo) and vrom[st << 8:(en + 1) << 8] == V.sample_bytes(v2, vo['segments'])
                res.append({'frame': pend[2], 'voice': vid, 'ss2_cmd': vo['cmd'] if vo else None, 'bytes_equal_ss2': eq})
                pend = None
        return res

    def run(rec, watch=None):
        S.setup(b, rec); del log[:]; t0 = b.frame; h0 = len(b.hits); rows = []
        def each():
            r = {'t': b.frame - t0, 'p1': b.states[b.fget(0, 'state')], 'anim': ba[b.fget(0, 'anim')] if b.fget(0, 'anim') < len(ba) else b.fget(0, 'anim'),
                 'spec_ix': b.fget(0, 'spec_ix'), 'fz1': b.fget(0, 'freeze'), 'd': b.states[b.fget(2, 'state')], 'y': b.fget(2, 'y'),
                 'fz2': b.fget(2, 'freeze'), 'kmode': b.fget(2, 'kmode'), 'srow': b.fget(0, 'srow')}
            if watch: r.update(watch(b))
            rows.append(r)
        for part in [p for p in rec['do_keys'].split(',') if p]:
            n, k = part.split(':')
            for _ in range(int(n)): b.run(1, p1=k.replace('-', '')); each()
        for _ in range(rec.get('proof', 60)): b.run(1); each()
        hits = []
        for f, i, d, st in b.hits[h0:]:
            if i != 2: continue
            k = f - t0 - 1
            hits.append(dict(rows[k], dmg=d, after=[(x['d'], x['y']) for x in rows[k + 1:k + 4]], flew=max([x['y'] for x in rows[k + 1:k + 16]] or [0])))
        return rows, hits, t0

    R, ok = {}, True
    lab = lambda **k: {'setup': dict({'mode': 'lab', 'fighter': 'haohmaru', 'dummy': 'ryo', 'gap': 40, 'drive': 'full'}, **k.pop('setup', {})), **k}
    # voices + hit-stop: C (623AB)
    rows, hits, t0 = run(lab(do_keys='2:c,100:-'))
    start = next(r['t'] for r in rows if r['p1'] == 'SPECIAL')
    vs = voices_in(t0 + start - 1, t0 + start + 3)
    want = next(vo['id'] for vo in bank if any(u.get('kind') == 'special' and u['input'] == '623AB' and u['at'] == 0 for u in vo['uses']))
    R['voice_623AB'] = {'special_starts': start, 'voices': vs, 'ss2_voice': want,
                        'ok': any(v['voice'] == want and v['bytes_equal_ss2'] for v in vs)}
    R['hitstop_623AB'] = {'hits': hits, 'ok': bool(hits) and all(h['fz2'] > 0 for h in hits)}   # (its crescent's hit: the
                                                                    # victim held; an object never holds its thrower)
    # the MAX: voice, Tenha's hits
    import handlers_ss2 as H
    rows, hits, t0 = run(lab(setup={'gap': 60, 'hp': 15, 'fury': 'full'}, do_keys='2:Dd,300:-', proof=60),
                         watch=lambda b: {'pstep': b.fget(0, 'pstep')})
    start = next(r['t'] for r in rows if r['p1'] == 'SPECIAL')
    prog0 = next(r['t'] for r in rows if r['p1'] == 'SPECIAL' and r['srow'] > 0)   # (after the super flash's freeze and its
    vs = voices_in(t0 + start - 1, t0 + prog0 + 3)                                   # flash pose, which shouts the rage line)
    want = next(vo['id'] for vo in bank if any(u.get('kind') == 'special' and u['input'] == '34123421BC' and u['at'] == 0 for u in vo['uses']))
    R['voice_max'] = {'special_starts': start, 'program_starts': prog0, 'voices': vs, 'ss2_voice': want,
                      'ok': any(v['voice'] == want and v['bytes_equal_ss2'] and abs(v['frame'] - t0 - prog0) <= 2 for v in vs)}
    want_steps = [k for a_ in (336, 264) for k in sorted(H.TENHA_HITS[a_])]
    stand, last = hits[:-1], (hits[-1] if hits else None)
    R['tenha'] = {'ss2_steps': want_steps, 'brawler_hits': len(hits), 'brawler_steps': [h['pstep'] for h in hits],
                  'damage': [h['dmg'] for h in hits], 'total': sum(h['dmg'] for h in hits),
                  'standing': [(h['after'][0][0], h['after'][0][1]) for h in stand], 'last': last and (last['after'], last['flew']),
                  'held': [(h['fz1'], h['fz2']) for h in hits]}
    R['tenha']['ok'] = (R['tenha']['brawler_steps'] == want_steps and all(a[0] == 'HITSTUN' and a[1] == 0 for a in R['tenha']['standing'])
                        and last is not None and last['after'][-1][0] == 'KNOCKDOWN' and last['flew'] > 0
                        and all(h['fz1'] > 0 and h['fz2'] > 0 for h in hits) and abs(R['tenha']['total'] - 180) <= 20)
    # juggle: dd Blitz 214A knocks down, C (623AB) cancelled on the hit hits the dummy in the air
    rows, hits, t0 = run(lab(do_keys='2:D,2:-,2:Da,14:-,2:c,100:-', proof=40))
    first = hits[0] if hits else None
    R['juggle'] = {'hits': [(h['t'], h['spec_ix'], h['d'], h['y'], h['kmode'], h['fz1'], h['fz2']) for h in hits],
                   'first_kmode_after': next((r['kmode'] for r in rows if first and r['t'] > first['t'] + 1), None)}
    R['juggle']['ok'] = len(hits) >= 2 and hits[1]['y'] > 0 and bool(R['juggle']['first_kmode_after'] & KM_HURT) and \
        hits[0]['fz1'] > 0 and all(h['fz2'] > 0 for h in hits)   # (214A's body hit holds both; 623AB's crescent the victim)
    # uu Blitz 623C: hit-stop
    rows, hits, t0 = run(lab(do_keys='2:U,2:-,2:Ua,80:-'))
    R['hitstop_623C'] = {'hits': [(h['t'], h['fz1'], h['fz2']) for h in hits], 'ok': bool(hits) and all(h['fz1'] > 0 and h['fz2'] > 0 for h in hits)}
    # the low finisher: A, A, down + A
    rows, hits, t0 = run(lab(do_keys='2:a,10:-,2:a,10:-,2:Da,60:-'))
    fin = [r['anim'] for r in rows if r['p1'] == 'ATTACK']
    R['low_finisher'] = {'anims': sorted(set(fin), key=fin.index), 'hits': [(h['t'], h['anim'], h['d']) for h in hits]}
    R['low_finisher']['ok'] = 'BA_ATK_AB_CLOSE' in fin and any(h['anim'] == 'BA_ATK_AB_CLOSE' for h in hits)
    for k, v in R.items():
        ok &= v['ok']
        print(k, 'OK' if v['ok'] else 'FAIL', json.dumps({x: y for x, y in v.items() if x not in ('hits',)})[:600])
    json.dump(R, open(out, 'w'), indent=1, default=str)
    print('ALL OK' if ok else 'FAIL'); return ok

if __name__ == '__main__':
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)
