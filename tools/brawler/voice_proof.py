#!/usr/bin/env python3
"""Voices proof (TODO #55) in our emulator's core with the Z80 port tap (tools/makoto3/capture.py's build of Geolith):
the brawler's Chain Lab training (lab req 1: FIGHTER against DUMMY), the four specials and the normals played; every
voice command the Z80 reads ($1C / $1E + code) with the ADPCM-A key-on it starts (start / end registers), the move P1
(or the dummy) was in, and the check: the sample played = the voice's sample in its source game's V ROM, byte for byte;
the voice = KOF's own for that move (voices.json uses).

    python3 voice_proof.py FIGHTER DUMMY OUT.json [GAME_DIR] [--pack PACK.bin]   (a lab data pack installed with the start)
    python3 voice_proof.py --all OUTDIR [NAME ...]   every fighter's specials and furies vs the source's sound log (proof_all)"""
import ctypes as C, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness, voices as V
harness.CORE = '/data/neogeo_dict/sound/snd98/ff3/geolith_tap.so'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
SCRIPT = os.environ.get('VP_SCRIPT') or '60:-,2:d,110:-,2:Rd,110:-,2:Dd,110:-,2:Ud,110:-,2:a,40:-,2:b,40:-,2:c,40:-,2:Ra,60:-'   # VP_SCRIPT: another

def main(fighter, dummy, out, game=harness.GAME, pack=None):
    G = json.load(open(os.path.join(game, 'game.json'))); names = [r['name'] for r in G['roster']]
    rep = json.load(open(os.path.join(game, 'build', 'snd', 'snd_report.json')))['voices']
    lab = {f['name']: f for f in json.load(open(os.path.join(game, 'build', 'chainlab.json')))['fighters']}
    code_of = {(n, int(i)): c for n, d in rep['fighters'].items() for i, c in d['codes'].items()}
    by_code = {c: k for k, c in code_of.items()}
    b = harness.Brawler(game=game); S = b.syms
    log, a = [], [0, 0]
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 4: a[0] = v
            elif p == 6: a[1] = v
            elif p == 7: log.append((b.frame, 'b', a[1], v))
        elif p == 0 and v: log.append((b.frame, 'c', v, 0))
        return v
    cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    for _ in range(400): b.core.retro_run()                  # ramtrace.BOOT_FRAMES
    L = S['lab']
    for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
    if pack:                                                  # a lab data pack (the Characters tab's), installed with the start
        from chainlab.labdrive import PACK_OFF, PACK_STAT_OFF
        for i, v in enumerate(open(pack, 'rb').read()): b.w(L + PACK_OFF + i, 1, v)
        b.w(L + 7, 1, 3)
    b.w(L + 5, 1, names.index(fighter)); b.w(L + 6, 1, names.index(dummy)); b.w(L + 4, 1, 1)
    moves = {}                                                # frame -> (P1 state, anim, spec_id (role), srow; dummy state)
    for part in SCRIPT.split(','):
        n, k = part.split(':')
        for _ in range(int(n)):
            b.run(1, p1=k.replace('-', ''))
            moves[b.frame] = (b.states[b.fget(0, 'state')], b.fget(0, 'anim'), b.fget(0, 'spec_id'), b.fget(0, 'srow'),
                              b.states[b.fget(1, 'state')], b.fget(0, 'spec_ix'))
    vrom = open(os.path.join(game, 'build', 'snd', 'v1.bin'), 'rb').read()
    m1 = open(os.path.join(game, 'build', 'snd', 'm1.bin'), 'rb').read()
    bank = json.load(open(V.JSON))['fighters']
    res = []
    pending = None; reg = {}
    PAIRED = {0x14, 0x15, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E}   # KOF98: commands that take the next byte
    ov = rep.get('overflow') or {'slots': [], 'prefixes': []}  # the overflow slots (codes | $100 in the report)
    TAB = {int(p, 16): 0x484C for p in rep['prefixes']}       # prefix -> its sample table (slot 2; slot 3 holds the same)
    TAB.update({int(p, 16): 0x544C for p in ov['prefixes']})  # (slot 4; slot 5 the same)
    VP = tuple(TAB)
    PLAYER = {int(rep['prefixes'][0], 16)} | ({int(ov['prefixes'][0], 16)} if ov['prefixes'] else set())
    want, fresh = None, set()                                 # a prefix waiting for its code; registers written since
    for f, kind, x, y in log:
        if kind == 'c':
            if want is not None:
                if want in VP: pending = [want, x, f]; fresh = set()
                want = None
            elif x in PAIRED: want = x
            continue
        reg[x] = y; fresh.add(x)
        if pending and f > pending[2] + 3:                    # no key-on of its record: the driver dropped it (every
            res.append({'frame': pending[2], 'prefix': f'{pending[0]:02X}', 'code': f'{pending[1]:02X}', 'dropped': True})
            pending = None                                    # effect channel busy with higher priorities)
        if x == 0 and not y & 0x80 and y and pending and pending[1] is not None:
            ch = (y & -y).bit_length() - 1
            st, en = reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0), reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)
            r = TAB[pending[0]] + 6 * pending[1]              # its record
            if (st, en) != (m1[r + 1] | m1[r + 2] << 8, m1[r + 3] | m1[r + 4] << 8): continue
            pre = pending[0]; who = by_code.get(pending[1] | (0x100 if pre in TAB and TAB[pre] != 0x484C else 0))
            e = {'frame': pending[2], 'prefix': f'{pre:02X}', 'code': f'{pending[1]:02X}', 'start': st, 'end': en, 'level': reg.get(8 + ch)}
            if who:
                n, i = who; vo = bank[n]['voices'][i - 1]; src = V.v_rom(bank[n]['game'])
                s0, e0 = vo['segments'][0]
                e.update(fighter=n, voice=i, kof_cmd=vo['cmd'], source=[s0, e0], level_kof=vo['level'],
                         bytes_equal=vrom[st << 8:(en + 1) << 8] == src[s0 << 8:(e0 + 1) << 8], nbytes=(en - st + 1) << 8)
                mv = moves.get(pending[2]) or moves.get(pending[2] + 1)
                if mv:
                    side = 0 if pre in PLAYER else 1
                    e['p1'] = list(mv[:4]); e['dummy_state'] = mv[4]
                    vk = lab[n]['voices']['keys']
                    if side == 0 and mv[0] == 'SPECIAL':           # the role's special (lab req 1: the ROM's map)
                        sv = list(lab[n]['specials'].values())   # (a fury / MAX / form transition: the special played)
                        inp = sv[mv[2]] if mv[2] < len(sv) else lab[n]['pool'][mv[5]]['input']; key = 'special:' + inp
                    elif side == 0 and mv[0] in ('ATTACK', 'AIR_ATTACK'): key = vk[mv[1]]
                    elif side == 1: key = 'hit'
                    else: key = vk[mv[1]]
                    e['key'] = key
                    e['kof_uses'] = [u.get('input') or u.get('event') or u.get('slot') for u in vo['uses']]
                    e['kof_own'] = lab[n]['voices']['suggest'].get(key, [None])[0] == i
                    if pack: e['pack_status'] = b.r(L + PACK_STAT_OFF, 1)
            res.append(e); pending = None
    json.dump({'fighter': fighter, 'dummy': dummy, 'voices': res, 'v_rom_bytes': len(vrom)}, open(out, 'w'), indent=1)
    for e in res:
        if e.get('dropped'): print(e['frame'], e['prefix'], e['code'], 'DROPPED by the driver (channels busy)'); continue
        print(e.get('frame'), e['prefix'], e['code'], e.get('fighter'), e.get('voice'), e.get('key'), 'KOF', e.get('kof_cmd'),
              'own' if e.get('kof_own') else 'NOT OWN', f"${e['start']:04X}-${e['end']:04X}", 'level', e.get('level'), e.get('level_kof'), 'bytes equal' if e.get('bytes_equal') else 'BYTES DIFFER')
    return res

def proof_all(out, game=harness.GAME, names=None):
    """TODO #163: every roster fighter's every special (its pool, game.json's picks and the rest) and its fury / MAX,
    each played twice in the Chain Lab (the dummy out of reach: the whiff; at point blank: the hit path), every voice
    command the Z80 reads (player prefix + code -> the fighter's voice id, snd_report) with its frame from the special's
    first frame; against the source game's sound log for that input (voices.json: the captured plays, $14 stops left
    out, 'at' 1 = its first frame) and the program's own sends (voices.json 'prog' uses, KOF ROM specials). A special is
    played as role D (spec_tab repointed to a map in the lab's pack buffer, C pressed), a fury with D, a MAX with
    down+D (meter full). -> OUT/voices_all.json, a line per move"""
    G = json.load(open(os.path.join(game, 'game.json'))); names_all = [r['name'] for r in G['roster']]
    rep = json.load(open(os.path.join(game, 'build', 'snd', 'snd_report.json')))['voices']
    lab = {f['name']: f for f in json.load(open(os.path.join(game, 'build', 'chainlab.json')))['fighters']}
    bank = json.load(open(V.JSON))['fighters']
    ov = rep.get('overflow') or {'prefixes': []}
    P1 = {int(rep['prefixes'][0], 16): 0} | ({int(ov['prefixes'][0], 16): 0x100} if ov['prefixes'] else {})
    b = harness.Brawler(game=game); S = b.syms
    log = []
    def tap(write, port, v):
        if not write and port & 0xFF == 0 and v: log.append((b.frame, v))
        return v
    cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    for _ in range(400): b.core.retro_run()
    from chainlab.labdrive import PACK_OFF
    L = S['lab']; MAP = L + PACK_OFF                         # (the pack buffer, never installed here)
    for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
    st = b.states
    res = {}
    for n in (names or names_all):
        fi = names_all.index(n); code_of = {int(c): int(i) for i, c in rep['fighters'].get(n, {'codes': {}})['codes'].items()}
        rf = next(r for r in G['roster'] if r['name'] == n); fury = rf.get('fury')
        pool = [p['input'] for p in lab[n]['pool']]
        vo = bank.get(n, {'voices': []})['voices']
        rows = []
        for k, inp in enumerate(pool):
            keys = 'd' if fury and inp == fury else 'Dd' if fury and inp == 'MAX ' + fury else 'c'
            runs = {}
            for case in ('whiff', 'close'):
                b.w(L + 5, 1, fi); b.w(L + 6, 1, names_all.index('terry') if n != 'terry' else names_all.index('ryo')); b.w(L + 4, 1, 1)
                b.run(30)
                b.w(S['spec_tab'] + 4 * fi, 4, MAP)
                for j in range(6): b.w(MAP + j, 1, k if j == 0 else 0xFF)
                b.fset(0, 'meter', 120); b.fset(0, 'facing', 1)
                if case == 'close': b.place(2, x=b.fget(0, 'x') + 34, z=b.fget(0, 'z'))
                else: b.place(2, x=b.fget(0, 'x') + 260, z=b.fget(0, 'z') + 40)
                b.run(2)
                log.clear(); f0 = None; end = None
                for f in range(700):
                    b.run(1, p1=keys if f < 3 else '')
                    sname = st[b.fget(0, 'state')]
                    if f0 is None and sname == 'SPECIAL': f0 = b.frame
                    if f0 is not None and end is None and sname != 'SPECIAL': end = b.frame
                    if end is not None and b.frame > end + 40: break
                got, want = [], None
                for fr, v in log:
                    if want is not None:
                        i = code_of.get(v | want)
                        if i and f0 is not None: got.append([fr - f0, i])
                        want = None
                    elif v in P1: want = P1[v]
                runs[case] = {'voices': got, 'played': f0 is not None, 'frames': (end or b.frame) - (f0 or 0),
                              'spec_ix': b.fget(0, 'spec_ix')}
            cap = sorted([u['at'] - 1, x['id']] for x in vo for u in x['uses'] if u['kind'] == 'special' and u['input'] == inp)
            prog = sorted({x['id'] for x in vo for u in x['uses'] if u['kind'] == 'prog' and u['input'] == inp})
            ours = {i for r in runs.values() for _, i in r['voices']}
            src = {i for _, i in cap} | set(prog)
            # the captured plays: each found among ours (either run) at its frame
            timing = [[at, i, any([at, i] in r['voices'] for r in runs.values()),
                       min((abs(a - at) for r in runs.values() for a, j in r['voices'] if j == i), default=None)] for at, i in cap]
            row = {'input': inp, 'keys': keys, 'runs': runs, 'source_plays': cap, 'program_sends': prog,
                   'missing': sorted(src - ours), 'extra': sorted(ours - src), 'timing': timing,
                   'ok': not (src - ours) and not (ours - src) and all(t[2] for t in timing)}
            rows.append(row)
            print(n, inp, 'OK' if row['ok'] else 'DIFF', 'whiff', runs['whiff']['voices'], 'close', runs['close']['voices'],
                  '| source', cap, 'prog', prog, ('missing ' + str(row['missing'])) if row['missing'] else '',
                  ('extra ' + str(row['extra'])) if row['extra'] else '', flush=True)
        res[n] = rows
    os.makedirs(out, exist_ok=True)
    json.dump(res, open(os.path.join(out, 'voices_all.json'), 'w'), indent=1)
    return res

if __name__ == '__main__':
    if sys.argv[1:2] == ['--all']:
        proof_all(sys.argv[2], names=sys.argv[3:] or None); sys.exit()
    a = sys.argv[1:]; pk = a[a.index('--pack') + 1] if '--pack' in a else None
    a = [x for i, x in enumerate(a) if x != '--pack' and (i == 0 or a[i - 1] != '--pack')]
    main(*a[:3], *(a[3:4] or [harness.GAME]), pack=pk)
