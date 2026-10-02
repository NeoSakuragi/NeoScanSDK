#!/usr/bin/env python3
"""Host tool for the NeoCart P board programmer. Builds chip images from a .neo file and flashes them over USB.

  pboard_flash.py info                       identify the board and the flash chips
  pboard_flash.py image game.neo out_dir     write P.bin, VA.bin, VB.bin chip images (no hardware needed)
  pboard_flash.py flash game.neo [--port /dev/ttyACM0] [--groups P,VA,VB]
  pboard_flash.py verify game.neo

Chip images (see DESIGN.md): P (8 MB, 16-bit words, little-endian as the 68K reads them): P1 (first 1 MB of the .neo P region)
at 0, P2 bank n (each following 1 MB) at 4 MB + n*1 MB. VA (16 MB over two chips) = V1 region; VB = V2 region, or V1 again
when V2 is empty (MVS games read ADPCM-B from the same samples).
"""
import sys, struct, os, time, argparse
try: import serial
except ImportError: serial = None

def neo_regions(path):
    h = open(path, 'rb').read(0x1000)
    sizes = struct.unpack('<6I', h[4:0x1c]); names = ['P', 'S', 'M', 'V1', 'V2', 'C']
    data = open(path, 'rb').read()[0x1000:]; out = {}; off = 0
    for n, sz in zip(names, sizes): out[n] = data[off:off + sz]; off += sz
    return out

def images(path):
    r = neo_regions(path)
    P = bytearray(b'\xff' * (8 << 20))
    p = r['P']
    # The .neo P region already holds each 16-bit word low byte first (the file is MAME's word-swapped P, i.e. little-endian
    # words). The firmware assembles flash words as d[2i] | d[2i+1] << 8, so the region goes into the image unchanged:
    # the 68K then reads $000000 as 00 10 F3 00 (initial SP 0x0010F300).
    def to_flash(chunk): return chunk
    P[0:min(len(p), 1 << 20)] = to_flash(p[:1 << 20])
    banks = (len(p) - (1 << 20) + (1 << 20) - 1) // (1 << 20) if len(p) > (1 << 20) else 0
    assert banks <= 4, f'P region {len(p)} bytes needs {banks} banks, board holds 4'
    for n in range(banks):
        chunk = p[(1 + n) << 20:(2 + n) << 20]
        P[(4 + n) << 20:((4 + n) << 20) + len(chunk)] = to_flash(chunk)
    v1 = r['V1']; v2 = r['V2'] or v1
    assert len(v1) <= 16 << 20 and len(v2) <= 16 << 20
    VA = bytearray(b'\xff' * (16 << 20)); VA[:len(v1)] = v1
    VB = bytearray(b'\xff' * (16 << 20)); VB[:len(v2)] = v2
    return {'P': bytes(P), 'VA': bytes(VA), 'VB': bytes(VB)}, r

class Board:
    def __init__(self, port):
        self.s = serial.Serial(port, 921600, timeout=30)
    def cmd(self, c, payload=b''):
        self.s.write(c + payload); r = self.s.read(1)
        if r == b'E': raise RuntimeError(f'device error {self.s.read(1)[0]} on {c!r}')
        if r != b'K': raise RuntimeError(f'bad reply {r!r} on {c!r}')
    def info(self):
        self.cmd(b'I'); d = self.s.read(4 + 9)
        return {'version': d[0], 'proto': d[1], 'prog_mode': d[2], 'vbus': d[3], 'ids': [(d[4 + 3 * g], d[5 + 3 * g] | (d[6 + 3 * g] << 8)) for g in range(3)]}
    def chip_erase(self, g):
        self.s.timeout = 600; self.cmd(b'C', bytes([g])); self.s.timeout = 30
    def write(self, g, addr, data):
        for off in range(0, len(data), 4096):
            chunk = data[off:off + 4096]
            if chunk.count(0xFF) == len(chunk): continue            # erased already
            self.cmd(b'W', bytes([g]) + struct.pack('<IH', addr + off, len(chunk)) + chunk)
    def read(self, g, addr, n):
        out = bytearray()
        for off in range(0, n, 4096):
            k = min(4096, n - off); self.cmd(b'R', bytes([g]) + struct.pack('<IH', addr + off, k)); out += self.s.read(k)
        return bytes(out)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('action'); ap.add_argument('neo', nargs='?'); ap.add_argument('outdir', nargs='?')
    ap.add_argument('--port', default='/dev/ttyACM0'); ap.add_argument('--groups', default='P,VA,VB'); a = ap.parse_args()
    if a.action == 'image':
        imgs, r = images(a.neo); os.makedirs(a.outdir, exist_ok=True)
        for k, v in imgs.items(): open(os.path.join(a.outdir, k + '.bin'), 'wb').write(v)
        print({k: len(v) for k, v in r.items()}); return
    b = Board(a.port); info = b.info(); print(info)
    if a.action == 'info': return
    if not info['prog_mode']: sys.exit('MODE jumper is not on PROG')
    imgs, _ = images(a.neo); gid = {'P': 0, 'VA': 1, 'VB': 2}
    for name in a.groups.split(','):
        g = gid[name]; img = imgs[name]
        if a.action == 'flash':
            t = time.time(); print(f'{name}: chip erase'); b.chip_erase(g); print(f'  erased in {time.time() - t:.0f}s')
            t = time.time(); b.write(g, 0, img); print(f'  written in {time.time() - t:.0f}s')
        t = time.time(); back = b.read(g, 0, len(img))
        bad = next((i for i in range(len(img)) if img[i] != back[i]), None)
        print(f'{name}: verify {"OK" if bad is None else f"MISMATCH at 0x{bad:X}: wrote {img[bad]:02X} read {back[bad]:02X}"} in {time.time() - t:.0f}s')
        if bad is not None: sys.exit(1)

if __name__ == '__main__': main()
