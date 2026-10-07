#!/usr/bin/env python3
"""TODO #155 proof: the MAX fury's super flash plays KOF2000's SDM flash sound (the high whistle), the fury keeps KOF98's
charge. Both sides in the tap core (tools/makoto3/capture.py's Geolith build with the Z80 port tap), our emulator only:

  KOF2000: from a fight state (/data/neogeo_dict/ngsdl_sta/kof2000, made with neogeo_sdl --capture: Terry with three
  stocks), Power Geyser as DM (A) and as SDM (A+C): every sound command the Z80 reads and every ADPCM-A key-on.
  Measured: the DM's flash sends $1E $BC, the SDM's $1E $8F (K' too: same two codes) -> slot 3 record $541E.
  Brawler: the Chain Lab, FIGHTER's fury (D) and MAX (down+D), meter full, the dummy out of reach: the codes queued
  (sound.c q[]) and read, the key-on each starts.
  Check: the brawler's MAX flash sends $1A $8F at the flash (state_t = gflash.start), its key-on plays the same bytes as
  KOF2000's SDM flash key-on; the fury's flash sends $1A $3A (KOF98's charge, unchanged).

    python3 max155_proof.py OUTDIR [FIGHTER ...]        (default terry ryo) -> OUTDIR/max155.json, WAVs
    (internal: --kof2000 STATE KEYS OUT / --brawler FIGHTER KEYS OUT: one core per process)"""
import ctypes as C, json, os, subprocess, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(TOOLS, 'makoto3'))
STA = '/data/neogeo_dict/ngsdl_sta/kof2000'
K2 = '/data/roms/kof2000.neo'
RATE = 55555
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
PG = '20:-,3:D,3:DL,3:L,3:DL,4:R{},150:-'          # Power Geyser (2 1 4 1 6), P1 on the left

def keyons(log):
    """[(frame, kind, a, b)] -> commands read ('c', v) and key-ons ('k', ch, start, end)"""
    reg, out = {}, []
    for f, kind, x, y in log:
        if kind == 'c': out.append((f, 'c', x)); continue
        reg[x] = y
        if x == 0 and y and not y & 0x80:
            for ch in range(6):
                if y >> ch & 1:
                    out.append((f, 'k', ch, reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0),
                                reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)))
    return out

def after(ev, pre, code, m1, table):
    """the frame of pre + code and the key-on of its record (start / end as the record holds them)"""
    r = table + 6 * code; st, en = m1[r + 1] | m1[r + 2] << 8, m1[r + 3] | m1[r + 4] << 8
    for i in range(1, len(ev)):
        if ev[i][1] == 'c' and ev[i][2] == code and ev[i - 1][1] == 'c' and ev[i - 1][2] == pre:
            k = next((e for e in ev[i + 1:] if e[1] == 'k' and (e[3], e[4]) == (st, en) and e[0] <= ev[i][0] + 3), None)
            return {'frame': ev[i][0], 'record': m1[r:r + 6].hex(), 'keyon': list(k) if k else None, 'start': st, 'end': en}
    return None

def wav(path, data):
    with wave.open(path, 'wb') as w: w.setnchannels(2); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(data)

def run_kof2000(state, keys, out):
    import capture as mk
    s = mk.Sound(rom=K2, work=os.path.dirname(out) + '/save')
    log, a = [], [0, 0]
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 6: a[1] = v
            elif p == 7: log.append((s.frame, 'b', a[1], v))
        elif p == 0 and v: log.append((s.frame, 'c', v, 0))
        return v
    s._keep = TAP(tap); s.core.retro_neoscan_z80_tap(s._keep)
    s.run(2); s.load(open(state, 'rb').read()); s.frame = 0
    pcm = bytearray(); s.wav = type('W', (), {'write': lambda self, d: pcm.extend(d)})()
    for item in PG.format(keys).split(','):
        n, k = item.split(':')
        for _ in range(int(n)): s.pad = set(k.replace('-', '')); s.core.retro_run(); s.frame += 1
    wav(out + '.wav', bytes(pcm))
    json.dump(keyons(log), open(out + '.json', 'w'))

def run_brawler(fighter, keys, out):
    import harness
    harness.CORE = '/data/neogeo_dict/sound/snd98/ff3/geolith_tap.so'
    b = harness.Brawler(); S = b.syms; G = harness.GAME
    log, a = [], [0, 0]
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 6: a[1] = v
            elif p == 7: log.append((b.frame, 'b', a[1], v))
        elif p == 0 and v: log.append((b.frame, 'c', v, 0))
        return v
    cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    pcm = bytearray(); rec = [False]
    def audio(d, n):
        if rec[0]: pcm.extend(C.string_at(d, 4 * n))
        return n
    acb = harness.BATCH_CB(audio); b.core.retro_set_audio_sample_batch(acb)
    for _ in range(400): b.core.retro_run()
    names = [r['name'] for r in json.load(open(os.path.join(G, 'game.json')))['roster']]
    L = S['lab']
    for i, v in enumerate(b'LAB1'): b.w(L + i, 1, v)
    b.w(L + 5, 1, names.index(fighter)); b.w(L + 6, 1, names.index('terry' if fighter != 'terry' else 'ryo')); b.w(L + 4, 1, 1)
    b.run(30)
    b.fset(0, 'meter', 120); b.fset(0, 'facing', 1); b.place(2, x=b.fget(0, 'x') + 260, z=b.fget(0, 'z') + 40)
    b.run(2)
    log.clear(); rec[0] = True
    sent, oqt, flash = [], b.r(S['qt'], 1), None
    import re
    start = int(re.search(r'\.start = (\d+)', open(os.path.join(G, 'build', 'game_tables.c')).read()).group(1))
    for f in range(240):
        b.run(1, p1=keys if f < 3 else '')
        qt = b.r(S['qt'], 1)
        while oqt != qt: sent.append((b.frame, b.r(S['q'] + oqt, 1))); oqt = (oqt + 1) & 31
        if flash is None and b.states[b.fget(0, 'state')] == 'SPECIAL' and b.fget(0, 'state_t') == start: flash = b.frame
    rec[0] = False
    wav(out + '.wav', bytes(pcm))
    json.dump({'events': keyons(log), 'sent': sent, 'flash': flash}, open(out + '.json', 'w'))

def main(outdir, fighters):
    os.makedirs(outdir, exist_ok=True)
    sys.path.insert(0, os.path.join(TOOLS, 'port'))
    from port98 import roms
    k2m, k2v = roms(K2)
    G = os.path.join(os.path.dirname(TOOLS), 'examples', 'brawler')
    bm = open(os.path.join(G, 'build', 'snd', 'm1.bin'), 'rb').read(); bv = open(os.path.join(G, 'build', 'snd', 'v1.bin'), 'rb').read()
    k2tab = lambda sl: k2m[0x2E0E + 2 * sl] | k2m[0x2E0F + 2 * sl] << 8
    me = [sys.executable, os.path.abspath(__file__)]
    rep = {'kof2000': {}, 'brawler': {}}
    for name, keys in (('dm', 'a'), ('sdm', 'ac')):
        o = f'{outdir}/kof2000_{name}'
        subprocess.run(me + ['--kof2000', f'{STA}/full_terry.state', keys, o], check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
        ev = json.load(open(o + '.json'))
        hit = {c: after(ev, 0x1E, c, k2m, k2tab(3)) for c in (0xBC, 0x8F)}
        rep['kof2000'][name] = {f'1E{c:02X}': h for c, h in hit.items() if h}
    sdm = rep['kof2000']['sdm']['1E8F']; dm = rep['kof2000']['dm']['1EBC']
    ok = sdm['keyon'] is not None and '1E8F' not in rep['kof2000']['dm'] and '1EBC' not in rep['kof2000']['sdm'] and dm['keyon']
    k2bytes = k2v[sdm['start'] << 8:(sdm['end'] + 1) << 8]
    print(f"KOF2000 Terry Power Geyser: DM flash $1E $BC (key-on ${dm['start']:04X}-${dm['end']:04X}), SDM flash $1E $8F "
          f"(key-on ${sdm['start']:04X}-${sdm['end']:04X}, {len(k2bytes)} bytes, record {sdm['record']})")
    for n in fighters:
        r = {}
        for name, keys in (('fury', 'd'), ('max', 'Dd')):
            o = f'{outdir}/brawler_{n}_{name}'
            subprocess.run(me + ['--brawler', n, keys, o], check=True, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            d = json.load(open(o + '.json'))
            want = 0x8F if name == 'max' else 0x3A
            h = after(d['events'], 0x1A, want, bm, 0x424C)
            q = [i for i in range(1, len(d['sent'])) if d['sent'][i - 1][1] == 0x1A and d['sent'][i][1] == want]
            other = 0x3A if want == 0x8F else 0x8F
            wrong = any(d['sent'][i - 1][1] == 0x1A and d['sent'][i][1] == other for i in range(1, len(d['sent'])))
            e = {'code': f'1A{want:02X}', 'flash_frame': d['flash'], 'queued': d['sent'][q[0] - 1][0] if q else None, 'read': h, 'other_code_sent': wrong}
            if name == 'max' and h:
                e['bytes_equal_kof2000'] = bv[h['start'] << 8:(h['end'] + 1) << 8] == k2bytes
                e['record_vs_kof2000'] = [h['record'], sdm['record']]
            e['ok'] = bool(h and h['keyon'] and q and e['queued'] == d['flash'] and not wrong and e.get('bytes_equal_kof2000', True))
            ok = ok and e['ok']; r[name] = e
            print(f"{n:8s} {name:4s} $1A ${want:02X} queued frame {e['queued']} (flash {d['flash']}), read frame "
                  f"{h and h['frame']}, key-on {h and h['keyon']}" + (f", bytes = KOF2000's: {e['bytes_equal_kof2000']}" if 'bytes_equal_kof2000' in e else '')
                  + ('' if not wrong else ' OTHER FLASH CODE SENT') + ('  ok' if e['ok'] else '  FAIL'))
        rep['brawler'][n] = r
    rep['ok'] = bool(ok)
    json.dump(rep, open(f'{outdir}/max155.json', 'w'), indent=1)
    print('ALL OK' if ok else 'FAIL')
    return ok

if __name__ == '__main__':
    a = sys.argv
    if a[1] == '--kof2000': run_kof2000(a[2], a[3], a[4])
    elif a[1] == '--brawler': run_brawler(a[2], a[3], a[4])
    else: sys.exit(0 if main(a[1], a[2:] or ['terry', 'ryo']) else 1)
