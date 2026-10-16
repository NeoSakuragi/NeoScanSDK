#!/usr/bin/env python3
"""Per-buyer brawler ROMs (Bruno 2026-10-16, memory project_copy_protection): the owner's name on the title screen
(visible, patchable) + a HIDDEN owner ID written many times into bytes the game never reads, to trace a leaked copy.

    make -C examples/brawler OWNER="Ismael C." [OWNER_ID=XXXXXXXX] [OWNER_OUT=/data/roms]
        -> OWNER_OUT/brawler-<VERSION>-<slug>.neo (the Makefile runs `header` and `stamp`)
    python3 watermark.py find ROM [ROM ...]     the owner ID(s) in a ROM (.neo, or a split/converted P, C1, C2, ...
                                                file) + the registry's name for them; exit 1 if none
    python3 watermark.py list                   the registry
    python3 watermark.py header OUT.h           (make) owner.h for main.c from $BRAWLER_OWNER (rewritten on change)
    python3 watermark.py slug NAME              (make) the file-name form of a name
    python3 watermark.py stamp IN.neo --elf rom.elf --build BUILD_DIR --version V -o OUT.neo
                                                (make) the records + the registry entry

PRIVATE STATE (outside the repo; $BRAWLER_WM_DIR, default /data/brawler-share): watermark.key (32 random bytes, made
on first use, the only secret: without it nobody can read, forge or recognise a record) and watermarks.json (the
registry: per owner its ID and every build made for it: version, file, sha256, date, source commit, copies).

THE RECORD (32 bytes): nonce(4) + 28 bytes XOR SHA-256(key | "ks" | nonce): ID(5) version(8, ASCII) region(1)
copy(1) tag(13) = HMAC-SHA256(key, nonce | ID | version | region | copy)[:13]. The nonce is derived from the key and the
record's fields (a rebuild gives the same bytes); without the key a record is 32 random-looking bytes and every
copy differs from the others.

WHERE (only bytes no code, table or sample reads; every target byte must be 0 before the stamp, else it refuses):
  P   each P2 bank's tail: after its .p2bankN section (rom.elf) + 4 KB, up to 4 KB before the bank's end ($2FFFF0 =
      the bank latch). MB 1 (the always-mapped first MB) is left alone: bank_proof.py checks it byte for byte.
  C   the C ROM's tail: after the build's last tile (build/rom_c1.bin's length) + 4 KB (auto-animation reaches at most
      7 tiles on), up to the padded end; each record byte written twice (even + odd byte) so a C1 / C2 split keeps whole
      records in both chips.
  S   fix tiles $800-$FFF (make_hud.py fills $000-$37F; nothing addresses the fix layer above $3FF).
  V   the V ROM's tail: after build_snd's last sample byte (snd/snd_report.json v_used) + 4 KB.
  Copies per region: P 8 per bank, C 32, S 8, V 4, each at a key-derived place in its own slice of the region.
`find` needs no layout: it scans the file as is, byte-swapped, and its even / odd bytes for 32 non-zero bytes between
zero blocks and keeps the records whose tag checks; patching the name string out leaves every record in place.
Limits: someone who diffs two buyers' ROMs sees the differing padding and can zero it; nothing short of the cart's own
hardware stops that (memory project_copy_protection)."""
import sys, os, json, hashlib, hmac, struct, subprocess, re, datetime, secrets

WM_DIR = os.environ.get('BRAWLER_WM_DIR', '/data/brawler-share')
KEY_PATH = os.path.join(WM_DIR, 'watermark.key')
REG_PATH = os.path.join(WM_DIR, 'watermarks.json')
B32 = '0123456789ABCDEFGHJKMNPQRSTVWXYZ'           # Crockford base32: the ID as 8 characters (5 bytes)
REGIONS = {'P': 1, 'C': 2, 'S': 3, 'V': 4}
COPIES = {'P': 8, 'C': 32, 'S': 8, 'V': 4}          # (P: per bank)
MARGIN = 0x1000
S_FREE = (0x800 * 32, 0x1000 * 32)                  # S ROM byte range: fix tiles $800-$FFF
NAME_MAX = 28
LINE1 = 'THIS COPY BELONGS TO'


# --- the ID, the key, the registry ----------------------------------------------------------------------------------
def id_str(b):
    n = int.from_bytes(b, 'big'); return ''.join(B32[(n >> (5 * (7 - i))) & 31] for i in range(8))
def id_bytes(s):
    s = s.upper().replace('-', '').replace('O', '0').replace('I', '1').replace('L', '1')
    if len(s) != 8 or any(c not in B32 for c in s): sys.exit(f'watermark: bad owner ID {s!r} (8 base32 characters)')
    n = 0
    for c in s: n = n << 5 | B32.index(c)
    return n.to_bytes(5, 'big')

def key():
    if not os.path.exists(KEY_PATH):
        os.makedirs(WM_DIR, exist_ok=True)
        fd = os.open(KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.write(fd, secrets.token_hex(32).encode() + b'\n'); os.close(fd)
        print(f'watermark: new key {KEY_PATH} (keep it: without it no record can be read)')
    return bytes.fromhex(open(KEY_PATH).read().strip())

def registry():
    return json.load(open(REG_PATH)) if os.path.exists(REG_PATH) else {
        'about': 'Brawler per-buyer ROMs: owner name, hidden owner ID (tools/brawler/watermark.py), builds. PRIVATE.',
        'owners': []}
def registry_save(r):
    tmp = REG_PATH + '.tmp'; json.dump(r, open(tmp, 'w'), indent=1, ensure_ascii=False); os.replace(tmp, REG_PATH)
def owner_by_id(r, i): return next((o for o in r['owners'] if o['id'] == i), None)
def owner_by_name(r, name): return next((o for o in r['owners'] if o['name'].casefold() == name.casefold()), None)


# --- the name -------------------------------------------------------------------------------------------------------
def check_name(name):
    name = ' '.join(name.split())
    if not name: sys.exit('watermark: empty owner name')
    if len(name) > NAME_MAX: sys.exit(f'watermark: owner name over {NAME_MAX} characters (one title-screen line)')
    if any(not (0x20 <= ord(c) <= 0x7E) for c in name): sys.exit('watermark: owner name must be plain ASCII (the fix font)')
    return name
def slug(name): return re.sub(r'[^a-z0-9]+', '-', check_name(name).lower()).strip('-')

def header(out):
    name = check_name(os.environ.get('BRAWLER_OWNER', ''))
    shown = name.upper()                                             # (the font's a-z are its capitals anyway)
    c = lambda s: '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'
    h = ('/* Generated by tools/brawler/watermark.py header ($BRAWLER_OWNER). Do not edit. */\n'
         f'#define OWNER_LINE1 {c(LINE1)}\n#define OWNER_COL1 {(40 - len(LINE1)) // 2}\n'
         f'#define OWNER_NAME {c(shown)}\n#define OWNER_COL {(40 - len(shown)) // 2}\n')
    if not os.path.exists(out) or open(out).read() != h:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True); open(out, 'w').write(h)


# --- the record -----------------------------------------------------------------------------------------------------
def _ver(v): return v.encode('ascii')[:8].ljust(8, b'\0')
def record(k, oid, version, region, copy):
    fields = oid + _ver(version) + bytes([region, copy])
    nonce = hmac.new(k, b'nonce' + fields, hashlib.sha256).digest()[:4]
    pt = fields + hmac.new(k, nonce + fields, hashlib.sha256).digest()[:13]
    ks = hashlib.sha256(k + b'ks' + nonce).digest()[:28]
    return nonce + bytes(a ^ b for a, b in zip(pt, ks))
def decode(k, rec):
    nonce, ct = rec[:4], rec[4:32]
    ks = hashlib.sha256(k + b'ks' + nonce).digest()[:28]
    pt = bytes(a ^ b for a, b in zip(ct, ks)); fields, tag = pt[:15], pt[15:]
    if not hmac.compare_digest(hmac.new(k, nonce + fields, hashlib.sha256).digest()[:13], tag): return None
    return id_str(fields[:5]), fields[5:13].rstrip(b'\0').decode('ascii', 'replace'), fields[13], fields[14]
def place(k, oid, region, copy, lo, hi, span):
    """a key-derived 32-aligned offset for the copy in [lo, hi) leaving 32 zero bytes either side"""
    room = (hi - lo - span - 64) // 32
    assert room > 0, 'watermark: region slice too small'
    r = int.from_bytes(hmac.new(k, b'place' + oid + bytes([region, copy]), hashlib.sha256).digest()[:8], 'big')
    return lo + 32 + (r % room) * 32


# --- stamp ----------------------------------------------------------------------------------------------------------
def neo_layout(d):
    if d[:3] != b'NEO': sys.exit('watermark: not a .neo file')
    sizes = struct.unpack('<6I', d[4:0x1C]); off = 0x1000; out = {}
    for n, sz in zip(['P', 'S', 'M', 'V1', 'V2', 'C'], sizes): out[n] = (off, sz); off += sz
    return out

def free_ranges(d, elf, build):
    """[(region, lo, hi, stride)]: file offsets of bytes the game never reads (see the module doc)"""
    L = neo_layout(d); out = []
    p0, psz = L['P']
    secs = {}
    for l in subprocess.run(['m68k-linux-gnu-objdump', '-h', elf], capture_output=True, text=True, check=True).stdout.split('\n'):
        f = l.split()
        if len(f) >= 7 and re.match(r'\d+$', f[0]) and f[1].startswith('.p2bank'): secs[int(f[1][7:])] = int(f[2], 16)
    for n in sorted(secs):
        at = p0 + (1 + n) * 0x100000
        if at + 0x100000 > p0 + psz: sys.exit(f'watermark: bank {n} outside the P region')
        out.append(('P', at + ((secs[n] + MARGIN + 31) & ~31), at + 0x100000 - MARGIN, 1))
    c0, csz = L['C']
    c_used = 2 * os.path.getsize(os.path.join(build, 'rom_c1.bin'))  # (interleaved C1 / C2 bytes)
    out.append(('C', c0 + ((c_used + MARGIN + 63) & ~63), c0 + csz, 2))
    s0, ssz = L['S']
    if ssz >= S_FREE[1]: out.append(('S', s0 + S_FREE[0], s0 + S_FREE[1], 1))
    v0, vsz = L['V1']
    v_used = json.load(open(os.path.join(build, 'snd', 'snd_report.json')))['v_used']
    if vsz - v_used > 4 * MARGIN: out.append(('V', v0 + ((v_used + MARGIN + 31) & ~31), v0 + vsz, 1))
    return out

def stamp(src, elf, build, version, dst):
    k = key(); name = check_name(os.environ.get('BRAWLER_OWNER', '')); r = registry()
    o = owner_by_name(r, name)
    want = os.environ.get('OWNER_ID', '').strip()
    if want: want = id_str(id_bytes(want))
    if o and want and o['id'] != want: sys.exit(f'watermark: {name} already has ID {o["id"]} in the registry')
    if not o:
        oid = want or id_str(secrets.token_bytes(5))
        while not want and owner_by_id(r, oid): oid = id_str(secrets.token_bytes(5))
        if owner_by_id(r, oid): sys.exit(f'watermark: ID {oid} belongs to {owner_by_id(r, oid)["name"]}')
        o = {'id': oid, 'name': name, 'builds': []}; r['owners'].append(o)
    ob = id_bytes(o['id'])
    d = bytearray(open(src, 'rb').read())
    placed = {}
    for reg, lo, hi, stride in free_ranges(d, elf, build):
        if any(d[lo:hi]): sys.exit(f'watermark: {reg} range {lo:#x}-{hi:#x} is not empty: the layout changed, refusing')
        n = COPIES[reg]; sl = ((hi - lo) // n) & ~63                 # (64-aligned slices: every record 32-aligned)
        for j in range(n):
            cp = placed.get(reg, 0)
            rec = record(k, ob, version, REGIONS[reg], cp)
            if stride == 2: rec = bytes(b for x in rec for b in (x, x))
            at = place(k, ob, REGIONS[reg], cp, lo + j * sl, lo + (j + 1) * sl, len(rec))
            d[at:at + len(rec)] = rec; placed[reg] = cp + 1
    found = find_records(bytes(d), k)                                # read back before anything is written
    ids = {f[1] for f in found}; got = {(f[3], f[4]) for f in found}   # (C: read in its even and its odd bytes)
    if ids != {o['id']} or len(got) != sum(placed.values()):
        sys.exit(f'watermark: read back {len(got)} of {sum(placed.values())} records {ids}: stamp FAILED, nothing written')
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    tmp = dst + '.tmp'; open(tmp, 'wb').write(d); os.replace(tmp, dst)
    sha = hashlib.sha256(d).hexdigest()
    here = os.path.dirname(os.path.abspath(__file__))                # (the repo the build ran from)
    try: commit = subprocess.run(['git', 'rev-parse', 'HEAD'], capture_output=True, text=True, cwd=here).stdout.strip()
    except OSError: commit = ''
    entry = {'version': version, 'file': os.path.abspath(dst), 'sha256': sha, 'size': len(d),
             'date': datetime.datetime.now().astimezone().isoformat(timespec='seconds'), 'source_commit': commit,
             'copies': placed}
    o['builds'] = [b for b in o['builds'] if b['file'] != entry['file']] + [entry]
    registry_save(r)
    print(f'watermark: {name} = {o["id"]}, {sum(placed.values())} records {placed}, read back OK; {dst} sha256 {sha}')


# --- find -----------------------------------------------------------------------------------------------------------
def find_records(d, k):
    """[(file offset, id, version, region, copy, view)] of every record in d, in any of the four views"""
    import numpy as np
    raw = np.frombuffer(d, dtype=np.uint8)
    ev = len(raw) & ~1
    views = [('raw', raw, lambda i: i), ('swap16', raw[:ev].reshape(-1, 2)[:, ::-1].reshape(-1), lambda i: i),
             ('even', raw[0::2], lambda i: 2 * i), ('odd', raw[1::2], lambda i: 2 * i + 1)]
    out = []; seen = set()
    for vn, v, back in views:
        for phase in (0, 16):                                        # (records are 32-aligned in the .neo; a file cut
            w = v[phase:]; n = len(w) // 16                          #  at another 16-byte boundary still reads)
            if n < 4: continue
            nz = w[:n * 16].reshape(n, 16).any(axis=1)
            c = np.nonzero(nz[1:-2] & nz[2:-1] & ~nz[:-3] & ~nz[3:])[0] + 1
            vb = w.tobytes() if len(c) else b''
            for i in c:
                if i % 2: continue
                rec = decode(k, vb[i * 16:i * 16 + 32])
                if rec:
                    at = back(phase + i * 16)
                    if (at, vn) not in seen: seen.add((at, vn)); out.append((at,) + rec + (vn,))
    return out

def region_of(d, at):
    try: L = neo_layout(d)
    except SystemExit: return '?'
    return next((n for n, (o, s) in L.items() if o <= at < o + s), 'header')

def find(paths):
    k = key(); r = registry(); hit = False
    for p in paths:
        d = open(p, 'rb').read()
        recs = find_records(d, k)
        print(f'{p}: {len({(x[3], x[4]) for x in recs})} watermark records')
        by = {}
        for at, i, ver, reg, cp, vn in recs: by.setdefault(i, []).append((at, ver, reg, cp, vn))
        for i, rs in by.items():
            o = owner_by_id(r, i); hit = True
            regs = {}
            for reg, cp in sorted({(x[2], x[3]) for x in rs}):          # distinct copies (a C record reads twice)
                rn = {v: kk for kk, v in REGIONS.items()}.get(reg, '?'); regs[rn] = regs.get(rn, 0) + 1
            vers = sorted({x[1] for x in rs})
            print(f'  owner ID {i}: {o["name"] if o else "(not in the registry)"}; build {", ".join(vers)}; '
                  f'copies by region {regs}')
            if o:
                sha = hashlib.sha256(d).hexdigest()
                b = next((b for b in o['builds'] if b['sha256'] == sha), None)
                print('  the file is ' + (f'byte-identical to the build delivered {b["date"]} ({b["file"]})' if b else
                                          'NOT byte-identical to any registered build (modified or converted)'))
    return hit

def main():
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(2)
    cmd = a[0]
    if cmd == 'slug': print(slug(' '.join(a[1:]) or os.environ.get('BRAWLER_OWNER', '')))
    elif cmd == 'header': header(a[1])
    elif cmd == 'stamp':
        import argparse
        ap = argparse.ArgumentParser(); ap.add_argument('src'); ap.add_argument('--elf', required=True)
        ap.add_argument('--build', required=True); ap.add_argument('--version', required=True); ap.add_argument('-o', required=True)
        x = ap.parse_args(a[1:]); stamp(x.src, x.elf, x.build, x.version, x.o)
    elif cmd == 'find': sys.exit(0 if find(a[1:]) else 1)
    elif cmd == 'list':
        for o in registry()['owners']:
            print(f'{o["id"]}  {o["name"]}')
            for b in o['builds']: print(f'    {b["version"]}  {b["date"]}  {b["sha256"][:16]}  {b["file"]}')
    else: print(__doc__); sys.exit(2)

if __name__ == '__main__':
    main()
