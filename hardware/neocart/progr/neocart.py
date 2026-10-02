#!/usr/bin/env python3
"""neocart - PC side of the NeoCart programmer (firmware/neocart_progr.c, protocol 2).

  neocart.py image game.neo outdir           P.bin + V.bin chip images, no hardware needed
  neocart.py info                            programmer + cart state, flash IDs (PROG board: JP1 must be on PROGRAM for IDs)
  neocart.py power on|off
  neocart.py flash game.neo [--only P|V]     chip erase, program, verify (NeoCart PROG board, JP1 on 1-2 PROGRAM)
  neocart.py verify game.neo [--bus A|B]
  neocart.py dump out.bin --group P|V [--size N] [--bus A|B]   read any PROG board, ours or SNK's
  neocart.py test                            line tests: walking ones on D0-D15 / A1-A19 / sample buses against a known image
  neocart.py uf2 firmware.bin out.uf2        firmware image for the RP2350 USB bootloader (hold BOOTSEL, plug USB, copy)

Images (v3 board, ../pboard/PROGRAMMING.md section 5):
  P (8 MB, S29GL064N word mode): flash MB 7 = P1 (the first 1 MB of the .neo P region), MB n = P2 bank n (each following
    1 MB, n = 0..6). Words are big-endian 68K words; a .neo stores P little-endian per word, so each byte pair is swapped.
  V (16 MB, S29GL128P byte mode): the .neo V1 region at byte address = YM2610 address, shared by ADPCM-A and ADPCM-B.
    A game with a separate V2 region does not fit the v3 board (its ADPCM-B data would need its own address space).
"""
import argparse, os, struct, sys, time
try: import serial
except ImportError: serial = None

MB = 1 << 20
def neo_regions(path):
    raw = open(path, 'rb').read()
    sizes = struct.unpack('<6I', raw[4:0x1C]); out = {}; off = 0x1000
    for n, sz in zip(('P', 'S', 'M', 'V1', 'V2', 'C'), sizes): out[n] = raw[off:off + sz]; off += sz
    return out

def images(path):
    r = neo_regions(path); p = r['P']
    swapped = bytes(b for i in range(0, len(p) - 1, 2) for b in (p[i + 1], p[i]))
    P = bytearray(b'\xff' * (8 * MB))
    P[7 * MB:7 * MB + min(MB, len(swapped))] = swapped[:MB]
    banks = max(0, (len(swapped) - MB + MB - 1) // MB)
    if banks > 7: raise SystemExit(f'P is {len(p)} bytes: {banks} P2 banks, the board holds 7')
    for n in range(banks):
        chunk = swapped[(1 + n) * MB:(2 + n) * MB]; P[n * MB:n * MB + len(chunk)] = chunk
    if r['V2']: raise SystemExit('this game has a separate V2 (ADPCM-B) region: it does not fit the v3 board (one shared sample flash)')
    if len(r['V1']) > 16 * MB: raise SystemExit(f'V1 is {len(r["V1"])} bytes, the board holds 16 MB')
    V = bytearray(b'\xff' * (16 * MB)); V[:len(r['V1'])] = r['V1']
    return {'P': bytes(P), 'V': bytes(V)}, r

def uf2(binfile, out, base=0x10000000, family=0xE48BFF59):          # RP2350 ARM secure family id
    data = open(binfile, 'rb').read(); blocks = [data[i:i + 256] for i in range(0, len(data), 256)]
    with open(out, 'wb') as f:
        for n, blk in enumerate(blocks):
            hdr = struct.pack('<8I', 0x0A324655, 0x9E5D5157, 0x2000, base + n * 256, 256, n, len(blocks), family)
            f.write(hdr + blk.ljust(476, b'\0') + struct.pack('<I', 0x0AB16F30))

class Programmer:
    G = {'P': 0, 'V': 1}
    def __init__(self, port):
        if serial is None: raise SystemExit('pip install pyserial')
        self.s = serial.Serial(port, 921600, timeout=30)
    def cmd(self, c, payload=b''):
        self.s.write(c + payload); r = self.s.read(1)
        if r == b'E': raise RuntimeError(f'device error {self.s.read(1)[0]} on {c!r}')
        if r != b'K': raise RuntimeError(f'bad reply {r!r} on {c!r}')
    def info(self):
        self.cmd(b'I'); d = self.s.read(7 + 8 + 4)
        ver, proto, powered, fault, inputs, mv = d[0], d[1], d[2], d[3], d[4], d[5] | d[6] << 8
        pid = struct.unpack('<4H', d[7:15]); vid = tuple(d[15:19])
        return dict(version=ver, proto=proto, cart_power=bool(powered), fault=bool(fault), vcart_mV=mv,
                    wait_inputs={'/ROMWAIT': inputs & 1, '/PWAIT0': inputs >> 1 & 1, '/PWAIT1': inputs >> 2 & 1, '/PDTACK': inputs >> 3 & 1},
                    P_id=[f'{x:04X}' for x in pid], V_id=[f'{x:02X}' for x in vid])
    def power(self, on): self.cmd(b'P', bytes([1 if on else 0]))
    def erase(self, g): self.s.timeout = 900; self.cmd(b'C', bytes([self.G[g]])); self.s.timeout = 30
    def write(self, g, data, progress=None):
        unit = 2 if g == 'P' else 1
        for off in range(0, len(data), 4096):
            chunk = data[off:off + 4096]
            if chunk.count(0xFF) == len(chunk): continue
            self.cmd(b'W', bytes([self.G[g]]) + struct.pack('<IH', off // unit, len(chunk)) + chunk)
            if progress: progress(off + len(chunk), len(data))
    def read(self, g, n, bus=0, start=0, progress=None):
        unit = 2 if g == 'P' else 1; out = bytearray()
        for off in range(start, start + n, 4096):
            k = min(4096, start + n - off)
            self.cmd(b'R', bytes([self.G[g]]) + struct.pack('<IH', off // unit, k) + bytes([bus])); out += self.s.read(k)
            if progress: progress(off - start + k, n)
        return bytes(out)
    # raw bus access (agentic tests)
    def latch(self, which, v): self.cmd(b'L', bytes([which]) + struct.pack('<H', v))
    def strobes(self, mask, v): self.cmd(b'G', struct.pack('<HH', mask, v))
    def read_d(self): self.cmd(b'T', b'\0'); return struct.unpack('<H', self.s.read(2))[0]

def bar(done, total):
    sys.stdout.write(f'\r  {done * 100 // total:3d}%'); sys.stdout.flush()

def compare(name, img, back):
    bad = [i for i in range(len(img)) if img[i] != back[i]]
    if not bad: print(f'{name}: verify OK ({len(img)} bytes)'); return True
    # name the data line: which bits differ, always the same way?
    diff = 0
    for i in bad[:4096]: diff |= img[i] ^ back[i]
    print(f'{name}: {len(bad)} bytes differ, first at 0x{bad[0]:X} (wrote {img[bad[0]]:02X} read {back[bad[0]]:02X}); bits involved: {diff:08b}')
    return False

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('args', nargs='*')
    ap.add_argument('--port', default='/dev/ttyACM0'); ap.add_argument('--only'); ap.add_argument('--bus', default='A')
    ap.add_argument('--group', default='P'); ap.add_argument('--size', type=lambda x: int(x, 0))
    a = ap.parse_args()
    if a.action == 'image':
        imgs, r = images(a.args[0]); os.makedirs(a.args[1], exist_ok=True)
        for k, v in imgs.items(): open(os.path.join(a.args[1], k + '.bin'), 'wb').write(v)
        print({k: len(v) for k, v in r.items()}); return
    if a.action == 'uf2': uf2(a.args[0], a.args[1]); return
    pr = Programmer(a.port)
    if a.action == 'info': print(pr.info()); return
    if a.action == 'power': pr.power(a.args[0] == 'on'); print(pr.info()); return
    pr.power(True); info = pr.info(); print(info)
    bus = 0 if a.bus.upper() == 'A' else 1
    try:
        if a.action in ('flash', 'verify'):
            imgs, _ = images(a.args[0]); groups = [a.only] if a.only else ['P', 'V']
            ok = True
            for g in groups:
                img = imgs[g]
                if a.action == 'flash':
                    t = time.time(); print(f'{g}: chip erase'); pr.erase(g); print(f'  {time.time() - t:.0f} s')
                    t = time.time(); print(f'{g}: program'); pr.write(g, img, bar); print(f'\n  {time.time() - t:.0f} s')
                t = time.time(); print(f'{g}: read back'); back = pr.read(g, len(img), bus, progress=bar); print(f'\n  {time.time() - t:.0f} s')
                ok &= compare(g, img, back)
            sys.exit(0 if ok else 1)
        if a.action == 'dump':
            n = a.size or (8 * MB if a.group == 'P' else 16 * MB)
            open(a.args[0], 'wb').write(pr.read(a.group, n, bus, progress=bar)); print(f'\n{n} bytes -> {a.args[0]}')
        if a.action == 'test':
            # walking one on A1-A16 through the P1 window: the read value must change for every address bit
            base = pr.read('P', 2, start=7 * MB * 0)
            seen = {}
            for bit in range(19):
                w = 1 << bit; v = pr.read('P', 2, start=(7 * MB) + 2 * w)
                seen[f'A{bit + 1}'] = v.hex()
            dup = {k for k, v in seen.items() if list(seen.values()).count(v) > 1}
            print('address lines with identical data (suspect open/short):', sorted(dup) or 'none')
    finally:
        pr.power(False)

if __name__ == '__main__': main()
