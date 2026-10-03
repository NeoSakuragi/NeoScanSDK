#!/usr/bin/env python3
"""Compare a ported song with its original at the chip: both drivers' models play it (tools/makoto3 for FF3,
tools/kof98snd for the KOF98 port), their register writes go through a register file, and every key-on and key-off
of every channel is compared: music tick, and the channel's registers at the key-on (FM: the 30 patch registers,
carrier TLs, F-number, pan; ADPCM-A: start/end through the V relocation, pan/level; ADPCM-B: start/end, delta-N,
volume, pan).

    python3 compare_port.py 0x2F PORT_DIR [TICKS]"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'kof98snd'))
import song98, regs98
sys.path.insert(0, os.path.join(TOOLS, 'makoto3'))
import song as ff3song, regs as ff3regs

FMCH = {1: ('a', 1), 2: ('a', 2), 5: ('b', 1), 6: ('b', 2)}
NAME = {1: 'FM1', 2: 'FM2', 5: 'FM3', 6: 'FM4'}

def events(ws, tick_of):
    """register writes [(irq, port, reg, val)] -> {channel: [(tick, 'on'/'off', state)]}"""
    R = {'a': [0] * 256, 'b': [0] * 256}; out = {}; on = {}
    late = []; last_irq = None                       # FM key-ons whose F-number / TL follow in the same interrupt
    def settle():
        for n, i, pp, o in late:
            t, k, st = out[n][i]
            st.update(regs=tuple(R[pp][base + 4 * kk + o] for base in range(0x30, 0xA0, 0x10) for kk in range(4)),
                      fnum=R[pp][0xA4 + o] << 8 | R[pp][0xA0 + o], b0=R[pp][0xB0 + o], b4=R[pp][0xB4 + o])
        late.clear()
    for irq, p, r, v in ws:
        if irq != last_irq: settle(); last_irq = irq
        R[p][r] = v; t = tick_of(irq)
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
                    out.setdefault(n, []).append((t, 'on', st)); on[n] = True
        elif p == 'a' and r == 0x10 and v & 0x80:
            st = dict(start=R['a'][0x12] | R['a'][0x13] << 8, end=R['a'][0x14] | R['a'][0x15] << 8,
                      dn=R['a'][0x19] | R['a'][0x1A] << 8, vol=R['a'][0x1B])
            out.setdefault('B', []).append((t, 'on', st)); on['B'] = True
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

def compare(cmd, pdir, ticks):
    ff = open('/data/neogeo_dict/sound/snd98/ff3/ff3_m1.bin', 'rb').read()
    s1 = ff3song.Song(ff, cmd).run(ticks=ticks)
    e1 = events(ff3regs.writes(s1), tickmap(s1))
    k98 = open(f'{pdir}/kof98_m1.bin', 'rb').read()
    s2 = song98.Song(k98, 0x27).run(ticks=ticks)
    e2 = events(regs98.writes(s2), tickmap(s2))
    rep = json.load(open(f'{pdir}/port_{cmd:02X}.json'))
    vmap = {tuple(json.loads(k)): tuple(v) for k, v in rep.get('vmap', {}).items()}
    total = {}
    for ch in sorted(set(e1) | set(e2), key=lambda c: (c[0] != 'F', c)):
        a, b = e1.get(ch, []), e2.get(ch, [])
        ok = timing = state = 0; first = None
        for i in range(min(len(a), len(b))):
            (t1, k1, s1_), (t2, k2, s2_) = a[i], b[i]
            good_t = t1 == t2 and k1 == k2
            good_s = True
            if k1 == 'on' and k2 == 'on':
                if ch.startswith('FM'):
                    good_s = s1_['fnum'] == s2_['fnum'] and s1_['b0'] == s2_['b0'] and s1_['b4'] == s2_['b4'] and s1_['regs'] == s2_['regs']
                elif ch.startswith('A'):
                    good_s = vmap.get((s1_['start'], s1_['end'])) == (s2_['start'], s2_['end']) and s1_['lvl'] == s2_['lvl']
                else:
                    good_s = vmap.get((s1_['start'], s1_['end'])) == (s2_['start'], s2_['end']) and s1_['vol'] == s2_['vol'] \
                        and s1_['dn'] == s2_['dn']
            ok += good_t and good_s; timing += not good_t; state += good_t and not good_s
            if not (good_t and good_s) and first is None: first = (i, a[i], b[i])
        print(f'{ch:4s} FF3 {len(a):4d} events, KOF98 {len(b):4d}; identical {ok}, timing differs {timing}, '
              f'state differs {state}')
        if first:
            i, x, y = first
            print(f'      first difference #{i}: FF3 {x[0]} {x[1]} {short(x[2])}\n'
                  f'                          KOF98 {y[0]} {y[1]} {short(y[2])}')
        total[ch] = (ok, len(a), len(b))
    return total

def short(st):
    if not st: return ''
    return ' '.join(f'{k}={v:X}' if isinstance(v, int) else f'{k}=..{hash(v) & 0xFFFF:04X}' for k, v in st.items())

if __name__ == '__main__':
    compare(int(sys.argv[1], 16), sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 4700)
