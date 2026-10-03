#!/usr/bin/env python3
"""Song Lab data for a port: the original song from its own driver (A: Fatal Fury 3's real driver, the capture) and
the port played by KOF98's driver (B: song98.py's model of the patched M1, ff3_to_kof98.py), on one tick grid (FF3
tick k = KOF98 tick k), so the page's A/B switch lands on the same note.

    python3 songlab_port.py 0x2F PORT_DIR OUT_DIR       -> OUT_DIR/XX.json (+ index.json, game.json)"""
import base64, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'songlab')); sys.path.insert(0, os.path.join(TOOLS, 'kof98snd'))
import build_web as bw
import song98, regs98
import compare_port

def ranges(stream):
    out = set(); lat = {}
    for t, p, r, val in stream:
        lat[(p, r)] = val
        if p == 1 and r == 0 and not val & 0x80:
            for c in range(6):
                if val >> c & 1:
                    out.add((lat.get((1, 0x10 + c), 0) | lat.get((1, 0x18 + c), 0) << 8,
                             lat.get((1, 0x20 + c), 0) | lat.get((1, 0x28 + c), 0) << 8))
        if p == 0 and r == 0x10 and val & 0x80:
            out.add((lat.get((0, 0x12), 0) | lat.get((0, 0x13), 0) << 8, lat.get((0, 0x14), 0) | lat.get((0, 0x15), 0) << 8))
    return out

def blobs(rs, v):
    merged = []
    for st, en in sorted(rs):
        if en < st: continue
        if merged and st <= merged[-1][1] + 1: merged[-1][1] = max(merged[-1][1], en)
        else: merged.append([st, en])
    return merged, [[st << 8, base64.b64encode(v[st << 8:(en + 1) << 8]).decode()] for st, en in merged]

def build(cmd, pdir, out):
    g = bw.GAMES['ff3']
    ff3 = open(g['m1'], 'rb').read()
    d = bw.ff3_song(g, ff3, cmd)                                  # A = FF3 capture, tracks, tick grid
    m1 = open(f'{pdir}/kof98_m1.bin', 'rb').read()
    s = song98.Song(m1, 0x27).run(ticks=d['ticks'] + 2)
    ws = regs98.writes(s)
    nseq = s.irq
    count = {}
    for q, p, r, val in ws: count[q] = count.get(q, 0) + 1
    real = {}; free = 0; tim = 0                                  # KOF98's lost interrupts (build_web.kof98_song)
    for q in range(nseq + 2):
        while tim * bw.PERIOD < free: tim += 1
        real[q] = tim; n = count.get(q, 0)
        free = tim * bw.PERIOD + (bw.ISR_START + n * bw.WRITE_COST if n else 0); tim += 1
    B = []; j = 0; prev = None
    for q, p, r, val in ws:
        if q > nseq: break
        j = j + 1 if q == prev else 0; prev = q
        B.append([int(real[q] * bw.PERIOD + bw.ISR_START + j * bw.WRITE_COST), 0 if p == 'a' else 1, r, val])
    acc = 0; irq = 0; tick_irq = [0]                              # KOF98 tick -> its interrupt -> sample
    while len(tick_irq) <= d['ticks'] and irq <= nseq:
        irq += 1; acc += s.tempo
        if acc >= 0xD0: acc -= 0xD0; tick_irq.append(irq)
    irqB = [real[q] * bw.PERIOD for q in tick_irq] + [real[nseq] * bw.PERIOD] * (d['ticks'] + 1 - len(tick_irq))
    _, ff3_v = bw.vrom(g['neo']), None
    ff3_v = bw.vrom(g['neo'])
    port_v = open(f'{pdir}/kof98_v1.bin', 'rb').read()
    ma, sa = blobs(ranges(d['A']), ff3_v); mb, sb = blobs(ranges(B), port_v)
    for a0, a1 in ma:
        for b0, b1 in mb: assert a1 < b0 or b1 < a0, 'FF3 and port samples overlap'
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()): tot = compare_port.compare(cmd, pdir, d['ticks'])
    same = sum(v[0] for v in tot.values()); total = sum(max(v[1], v[2]) for v in tot.values())
    rep = json.load(open(f'{pdir}/port_{cmd:02X}.json'))
    data = dict(d, B=B, irqB=irqB[:d['ticks'] + 1], cmd=cmd, match=[same, total],
                name=f"Terry's stage (FF3 ${cmd:02X}) on KOF98's driver" if cmd == 0x2F else f'FF3 ${cmd:02X} on KOF98',
                samples=sa + sb, length=max(d['A'][-1][0], B[-1][0]) + bw.PERIOD)
    os.makedirs(out, exist_ok=True)
    json.dump(data, open(f'{out}/{cmd:02X}.json', 'w'), separators=(',', ':'))
    index = [{'cmd': cmd, 'name': data['name'], 'tempo': d['tempo'], 'ticks_per_s': d['ticks_per_s'], 'match': data['match'],
              'ticks': d['ticks'], 'seconds': round(data['length'] / 55555.56, 1), 'tracks': [t['name'] for t in d['tracks']]}]
    json.dump(index, open(f'{out}/index.json', 'w'), separators=(',', ':'))
    warn = ''.join(f'<li>{w}</li>' for w in rep['warnings'])
    game = {'title': 'Ports', 'bar': 96, 'beat': 24, 'start': cmd, 'capture': 'FF3 capture', 'unit': 'key events',
            'labelA': 'FF3 driver', 'labelB': 'KOF98 driver',
            'intro': ("Songs moved from one sound engine to another. <b>FF3 driver</b> is Fatal Fury 3's own driver "
                      "(\"Ver 3.0 by MAKOTO\") playing the song, captured in our emulator. <b>KOF98 driver</b> is the "
                      "same song converted into KOF98's song format (tools/port/ff3_to_kof98.py) and played by KOF98's "
                      "driver (SNK v1.7), as our brawler would. Switch while it plays; the playhead keeps its place."),
            'notes': ["<b>How.</b> Every FF3 note is written with its full chip state: KOF98's direct level mode carries "
                      "FF3's attenuation values as velocities, detune reaches FF3's exact F-numbers, FM patches go inline, "
                      "ADPCM-A samples sit in unused KOF98 sample-table codes, ADPCM-B notes use KOF98's delta-N table "
                      "(the same values as FF3's), samples are moved into V ROM space only unused KOF98 stage themes need.",
                      f"<b>Check.</b> The facts line counts key-ons and key-offs whose tick and chip state (patch, "
                      f"pitch, level, pan, sample) are identical in both drivers. Known differences: <ul>{warn}"
                      f"<li>tempo: KOF98 83 = {rep['kof98_hz']:.2f} ticks/s, FF3 {rep['ff3_hz']:.2f}; KOF98's driver also "
                      f"loses timer interrupts on heavy ticks, FF3's never does</li></ul>",
                      "<b>Measured on SNK's real KOF98 code</b>: the brawler with the port as its music, in our emulator: "
                      "every key-on of the first 40 s had the model's chip state (1804 of 1804 events)."]}
    json.dump(game, open(f'{out}/game.json', 'w'), separators=(',', ':'))
    print(f'{out}/{cmd:02X}.json: A {len(d["A"])} writes, B {len(B)} writes, samples {len(sa)}+{len(sb)} ranges, '
          f'key events identical {same}/{total}')

if __name__ == '__main__':
    build(int(sys.argv[1], 16), sys.argv[2], sys.argv[3])
