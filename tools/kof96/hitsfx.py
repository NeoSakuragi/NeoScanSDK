#!/usr/bin/env python3
"""KOF96 / KOF98 / KOF99 hit sounds from the P-ROM: a move sets its hit kind in the attacker (+$1B8); on a hit the
victim copies it (+$131) and its dispatcher (found by its code: moveq #0,d0; move.b +$131(a4),d0; bmi) calls the
kind's handler from a table; handlers pass sound indices to the mapper (found by its code: lea abs,a0; move d0,d1;
add d0,d0; move (a0,d0),...) whose word table gives prefix << 8 | code. Kinds are numbered alike in the three games
(1 heavy hit, 11 hit + fire); the codes are each game's own driver's. 'sub:' = a handler calling further code.

    python3 hitsfx.py kof98 [kof99 kof96]"""
import os, re, struct, subprocess, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rom96

def decode(game):
    p = bytes(rom96.load(rom96.GAMES[game]['neo'])[0])
    path = os.path.join(tempfile.gettempdir(), f'{game}_prom.bin'); open(path, 'wb').write(p)
    d = re.search(re.escape(bytes.fromhex('7000102c01316b00')), p).start()
    # ... bmi.w; add d0,d0 x2; lea (pc,disp),a0
    q = d + 10
    assert p[q:q + 4] == bytes.fromhex('d040d040'), p[q:q+8].hex()
    assert p[q + 4:q + 6] == bytes.fromhex('41fa')
    table = q + 6 + struct.unpack('>h', p[q + 6:q + 8])[0]
    m = re.search(re.escape(bytes.fromhex('3200d0403b70')), p).start() - 6
    assert p[m:m + 2] == bytes.fromhex('41f9')
    words = struct.unpack('>I', p[m + 2:m + 6])[0]
    w = lambda i: struct.unpack('>H', p[words + 2 * i:words + 2 * i + 2])[0]
    src = [hex(struct.unpack('>H', p[x.start() + 2:x.start() + 4])[0]) for x in re.finditer(re.escape(bytes.fromhex('1968')), p)
           if p[x.start() + 4:x.start() + 6] == bytes.fromhex('0131') and x.start() % 2 == 0]
    out = {}
    for k in range(64):
        a = struct.unpack('>I', p[table + 4 * k:table + 4 * k + 4])[0]
        if not (table - 0x2000 < a < table + 0x2000): break
        dis = subprocess.run(['m68k-linux-gnu-objdump', '-D', '-b', 'binary', '-m', 'm68k', f'--start-address={a}',
                              f'--stop-address={a + 48}', path], capture_output=True, text=True).stdout
        ins = [l.split('\t')[-1] for l in dis.split('\n') if re.match(r'\s+[0-9a-f]+:\t', l)]
        codes, pend = [], None
        for t in ins:
            mm = re.match(r'movew #(-?\d+),%d([01])', t)
            if mm: pend = (int(mm.group(1)), mm.group(2), pend); continue
            if 'jsr' in t and pend is not None:
                if '0x33a8' in t or 'random' in t: continue
                if f'{m:#x}' in t or t.endswith(hex(m)):
                    i = pend[0]; codes.append(f'{w(i) >> 8:02X} {w(i) & 0xFF:02X}')
                else: codes.append('sub:' + t.split()[-1])
                pend = None; continue
            if t.startswith('rts'): break
            if 'jsr' in t: codes.append('sub:' + t.split()[-1])
        out[k] = codes
    return dict(dispatch=hex(d), table=hex(table), mapper=hex(m), words=hex(words), victim_from=src[:4], kinds=out)
for g in sys.argv[1:]:
    r = decode(g)
    print(g, {k: v for k, v in r.items() if k != 'kinds'})
    for k, v in r['kinds'].items(): print(f'  {k}: {" + ".join(v)}')
