#!/usr/bin/env python3
"""Compare a ported song with its original at the chip: both drivers' models play it (tools/makoto3 for MAKOTO
sources, tools/kof98snd for SNK-line sources and for the KOF98 port), their register writes go through a register
file, and every key-on and key-off of every channel is compared: music tick, and the channel's registers at the key-on
(FM: the 30 patch registers, carrier TLs, F-number, pan; ADPCM-A: the sample's bytes in the source V ROM and in the
built one, pan/level; ADPCM-B: the sample's bytes, delta-N, volume, pan), and pitch / level changes of sounding notes.
KOF98's own songs in the build (native) are compared with KOF98's original M1 / V ROM the same way.

    python3 compare_port.py SND_DIR NAME [TICKS]     a song of build_snd.py's output (SND_DIR/m1.bin, snd_report.json)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'kof98snd'))
import song98, regs98
sys.path.insert(0, os.path.join(TOOLS, 'makoto3'))
import song as ff3song, regs as ff3regs
import port98

FMCH = {1: ('a', 1), 2: ('a', 2), 5: ('b', 1), 6: ('b', 2)}
NAME = {1: 'FM1', 2: 'FM2', 5: 'FM3', 6: 'FM4'}

def events(ws, tick_of):
    """register writes [(irq, port, reg, val)] -> {channel: [(tick, 'on'/'off', state)]}"""
    R = {'a': [0] * 256, 'b': [0] * 256}; out = {}; on = {}
    late = []; late_a = []; last_irq = None                       # FM key-ons whose F-number / TL follow in the same interrupt
    pitch = {}; last_t = [0]; held = {}; keyed = set()                         # F-number of each held FM note: a change = a 'pitch' event
    def settle():
        for n, i, pp, o in late:
            t, k, st = out[n][i]
            st.update(regs=tuple(R[pp][base + 4 * kk + o] for base in range(0x30, 0xA0, 0x10) for kk in range(4)),
                      fnum=R[pp][0xA4 + o] << 8 | R[pp][0xA0 + o], b0=R[pp][0xB0 + o], b4=R[pp][0xB4 + o])
            pitch[n] = st['fnum']
        late.clear()
        for n, i, c in late_a:                       # ADPCM-A: the level as the interrupt leaves it (SDC_NGSS writes
            out[n][i][2]['lvl'] = R['b'][0x08 + c]   # it just after the key-on, $061E)
        late_a.clear()
        for c, n in NAME.items():                    # slurs / vibrato: the pitch of a held note changes
            pp, o = FMCH[c]
            if on.get(n) and pitch.get(n) is not None:
                f = R[pp][0xA4 + o] << 8 | R[pp][0xA0 + o]
                if f != pitch[n]: out.setdefault(n, []).append((last_t[0], 'pitch', {'fnum': f})); pitch[n] = f
        for c in range(6):                           # ADPCM-A level / pan while a sample plays
            n = f'A{c + 1}'; v = R['b'][0x08 + c]
            if n in keyed: held[n] = v
            elif on.get(n) and held.get(n) != v: out.setdefault(n, []).append((last_t[0], 'pitch', {'lvl': v})); held[n] = v
        v = (R['a'][0x19] | R['a'][0x1A] << 8, R['a'][0x1B])   # ADPCM-B delta-N / volume while it plays (slurs)
        if 'B' in keyed: held['B'] = v
        elif on.get('B') and held.get('B') != v: out.setdefault('B', []).append((last_t[0], 'pitch', {'dn': v[0], 'vol': v[1]})); held['B'] = v
        keyed.clear()
    for irq, p, r, v in ws:
        if irq != last_irq: settle(); last_irq = irq
        R[p][r] = v; t = tick_of(irq); last_t[0] = t
        if p == 'a' and r == 0x28:
            c = v & 7
            if c not in FMCH: continue
            pp, o = FMCH[c]; n = NAME[c]
            if v & 0xF0:
                if on.get(n): continue                      # key-on while on: no new note on the chip
                regs = tuple(R[pp][base + 4 * k + o] for base in range(0x30, 0xA0, 0x10) for k in range(4))
                st = dict(regs=regs, fnum=R[pp][0xA4 + o] << 8 | R[pp][0xA0 + o], b0=R[pp][0xB0 + o], b4=R[pp][0xB4 + o])
                out.setdefault(n, []).append((t, 'on', st)); on[n] = True
                late.append((n, len(out[n]) - 1, pp, o))
            else:
                if on.get(n): out.setdefault(n, []).append((t, 'off', None))
                on[n] = False
        elif p == 'b' and r == 0x00:
            for c in range(6):
                if not v >> c & 1: continue
                n = f'A{c + 1}'
                if v & 0x80:
                    if on.get(n): out.setdefault(n, []).append((t, 'off', None))
                    on[n] = False
                else:
                    st = dict(start=R['b'][0x10 + c] | R['b'][0x18 + c] << 8, end=R['b'][0x20 + c] | R['b'][0x28 + c] << 8,
                              lvl=R['b'][0x08 + c])
                    out.setdefault(n, []).append((t, 'on', st)); on[n] = True; keyed.add(n)
                    late_a.append((n, len(out[n]) - 1, c))
        elif p == 'a' and r == 0x1B and v == 0 and on.get('B'):     # volume 0: silent (the port's skipped key-off)
            out.setdefault('B', []).append((t, 'off', None)); on['B'] = False
        elif p == 'a' and r == 0x10 and v & 0x80:
            st = dict(start=R['a'][0x12] | R['a'][0x13] << 8, end=R['a'][0x14] | R['a'][0x15] << 8,
                      dn=R['a'][0x19] | R['a'][0x1A] << 8, vol=R['a'][0x1B])
            out.setdefault('B', []).append((t, 'on', st)); on['B'] = True; keyed.add('B')
        elif p == 'a' and r == 0x11 and v == 0 and on.get('B'):
            out.setdefault('B', []).append((t, 'off', None)); on['B'] = False
    settle()
    return out

def tickmap(s):
    m = {}
    for irq, tick, *_ in s.out: m[irq] = tick
    last = [0]
    def f(irq):
        if irq in m: last[0] = m[irq]
        return m.get(irq, last[0])
    return f

def source_events(game, cmd, ticks):
    m1, _, fn = port98.source(game)
    if fn is port98.ngss_notes.notes:
        ws, tick_of = port98.ngss_notes.ticks_writes(m1, cmd, ticks); return events(ws, tick_of)
    if fn is port98.ff3_notes.notes: s = ff3song.Song(m1, cmd).run(ticks=ticks); ws = ff3regs.writes(s)
    else: s = song98.Song(m1, cmd).run(ticks=ticks); ws = regs98.writes(s)
    return events(ws, tickmap(s))

def compare(snd_dir, name, ticks=None):
    rep = json.load(open(f'{snd_dir}/snd_report.json'))
    r = next(x for x in rep['songs'] if x.get('name') == name)
    game, cmd = r['source'].split(' $'); cmd = int(cmd, 16)
    if ticks is None: ticks = max(a + 2 * b for a, b in r['loops'].values()) + 1   # intro + the loop twice
    e1 = source_events(game, cmd, ticks)
    k = r.get('tick_scale', 1)                       # the port's ticks: source tick t = KOF98 tick (t - 1) * k + 1
    s2 = song98.Song(open(f'{snd_dir}/m1.bin', 'rb').read(), r['cmd']).run(ticks=(ticks - 1) * k + 1)
    tm = tickmap(s2)
    e2 = events(regs98.writes(s2), lambda irq: (tm(irq) - 1) // k + 1)
    src_v = port98.source(game)[1]; new_v = open(f'{snd_dir}/v1.bin', 'rb').read()
    same_smp = lambda a, b: src_v[a[0] << 8:(a[1] + 1) << 8] == new_v[b[0] << 8:(b[1] + 1) << 8] and a[1] - a[0] == b[1] - b[0]
    total = {}
    for ch in sorted(set(e1) | set(e2), key=lambda c: (c[0] != 'F', c)):
        a, b = e1.get(ch, []), e2.get(ch, [])
        ok = timing = state = 0; first = None
        for i in range(min(len(a), len(b))):
            (t1, k1, s1_), (t2, k2, s2_) = a[i], b[i]
            good_t = t1 == t2 and k1 == k2
            good_s = True
            if k1 == 'pitch' and k2 == 'pitch': good_s = s1_ == s2_
            if k1 == 'on' and k2 == 'on':
                if ch.startswith('FM'):
                    good_s = s1_['fnum'] == s2_['fnum'] and s1_['b0'] == s2_['b0'] and s1_['b4'] == s2_['b4'] and s1_['regs'] == s2_['regs']
                elif ch.startswith('A'):
                    good_s = same_smp((s1_['start'], s1_['end']), (s2_['start'], s2_['end'])) and s1_['lvl'] == s2_['lvl']
                else:
                    good_s = same_smp((s1_['start'], s1_['end']), (s2_['start'], s2_['end'])) and s1_['vol'] == s2_['vol'] \
                        and s1_['dn'] == s2_['dn']
            ok += good_t and good_s; timing += not good_t; state += good_t and not good_s
            if not (good_t and good_s) and first is None: first = (i, a[i], b[i])
        print(f'{ch:4s} source {len(a):4d} events, KOF98 {len(b):4d}; identical {ok}, timing differs {timing}, '
              f'state differs {state}')
        if first:
            i, x, y = first
            print(f'      first difference #{i}: source {x[0]} {x[1]} {short(x[2])}\n'
                  f'                              KOF98 {y[0]} {y[1]} {short(y[2])}')
        total[ch] = (ok, len(a), len(b))
    ok = sum(v[0] for v in total.values()); n = sum(max(v[1], v[2]) for v in total.values())
    print(f"{name}: {ok} / {n} chip events identical (key-ons with their state, key-offs, pitch / level changes of sounding notes; ticks 1-{ticks})")
    return total

def short(st):
    if not st: return ''
    return ' '.join(f'{k}={v:X}' if isinstance(v, int) else f'{k}=..{hash(v) & 0xFFFF:04X}' for k, v in st.items())

if __name__ == '__main__':
    compare(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else None)
