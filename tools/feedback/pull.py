#!/usr/bin/env python3
"""Pull the voice-feedback bundles from the VPS and replay each one in the Geolith core (docs/feedback.md).

    tools/feedback/pull.py              fetch new bundles + transcripts into /data/feedback/<id>/ (+ the tracker DB's
                                        backups into /data/feedback/_server/), mark them read, replay, report
    tools/feedback/pull.py --all        redo every report (else only new bundles / new transcripts)
    tools/feedback/pull.py --local      no fetch, just the bundles already in /data/feedback
    tools/feedback/pull.py --replay DIR one bundle's replay (run in a subprocess per bundle: the core is a global)

A bundle (from the NeoScan Player's mic button) = snap_<W>.state (the oldest kept state) + inputs.bin (every frame's
pads from W to the press P) + snap_<f>.state checkpoints + press.state + screen.png + audio + meta.json (+ the
server's transcript.txt). The replay loads the same ROM (by sha256: cache, the repo build, /data/roms, else the VPS
builds), unserializes W, feeds the inputs frame by frame and checks every checkpoint and the press state byte for byte
(determinism) and the last picture against screen.png; then a contact sheet + a clip of the last seconds and
report.md (with the player's reply thread, Player 0.0.17). One line per bundle on stdout, reopened notes first, and
/data/feedback/report.md: every note in the tracker with its thread, the reopened ones first."""
import ctypes as C, glob, hashlib, json, os, struct, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, os.path.join(REPO, 'tools', 'brawler'))
import harness as H                                         # libretro ctypes types, OPTIONS, SYSDIR
sys.path.insert(0, HERE)
import fb                                                   # the tracker API (over ssh)

HOST = 'root@195.201.91.211'
REMOTE = '/data/brawler/feedback/bundles/'
BUILDS = '/data/brawler/builds'
OUT = '/data/feedback'
ROMS = os.path.join(OUT, '_roms')                           # ROMs by sha256 (the VPS keeps only the last 3 builds)
GEOLITH = os.path.join(REPO, 'geolith', 'libretro')
CORE = os.path.join(GEOLITH, 'geolith_libretro.so')         # built from the same source the APK links (Android.mk)
RESET_BIT = 0x8000
SHEET_S, CLIP_S = 4, 3                                      # seconds before the press: sheet, clip


def sha_file(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()


def find_rom(meta):
    sha, size = meta.get('rom_sha256'), meta.get('rom_size')
    os.makedirs(ROMS, exist_ok=True)
    cached = os.path.join(ROMS, sha + '.neo')
    if os.path.exists(cached): return cached
    cands = [os.path.join(REPO, 'examples', 'brawler', 'brawler.neo')] + glob.glob('/data/tmp/*/examples/brawler/brawler.neo') + \
        glob.glob('/data/roms/*.neo') + glob.glob('/data/roms/*/*.neo')
    for p in cands:
        if os.path.exists(p) and os.path.getsize(p) == size and sha_file(p) == sha:
            os.link(p, cached) if os.stat(p).st_dev == os.stat(ROMS).st_dev else subprocess.run(['cp', p, cached], check=True)
            return cached
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, f'cd {BUILDS} && sha256sum brawler-*.neo'], capture_output=True, text=True)
    for line in r.stdout.splitlines():
        s, name = line.split()
        if s == sha:
            subprocess.run(['rsync', '-q', f'{HOST}:{BUILDS}/{name}', cached + '.part'], check=True)
            os.replace(cached + '.part', cached); return cached
    return None


def build_core():
    """the core from the geolith tree the APK compiles (make is incremental)"""
    r = subprocess.run(['make', '-C', GEOLITH, '-j%d' % os.cpu_count()], capture_output=True, text=True)
    if r.returncode: raise RuntimeError('core build failed:\n' + r.stderr[-2000:])


class Core:
    """the Geolith core with the Android player's settings (player.c environ_cb: region us, system per bundle)"""
    def __init__(self, rom, systype, hw, memcard='on'):
        opts = dict(H.OPTIONS, geolith_region='us', geolith_system_type=systype, geolith_unibios_hw=hw, geolith_memcard=memcard)
        self._opt = {k.encode(): C.c_char_p(v.encode()) for k, v in opts.items()}
        self.save_dir = tempfile.mkdtemp(prefix='fbsave_', dir='/data/tmp')
        self._sys = C.c_char_p(H.SYSDIR.encode()); self._save = C.c_char_p(self.save_dir.encode())
        self.pads = [0, 0]; self.video = None; self.want_video = False
        core = self.core = C.CDLL(CORE)
        self._cbs = [H.ENV_CB(self._env), H.VIDEO_CB(self._vid), H.SAMPLE_CB(lambda l, r: None), H.BATCH_CB(lambda d, n: n),
                     H.POLL_CB(lambda: None), H.STATE_CB(self._input)]
        core.retro_set_environment(self._cbs[0]); core.retro_init()
        core.retro_set_video_refresh(self._cbs[1]); core.retro_set_audio_sample(self._cbs[2])
        core.retro_set_audio_sample_batch(self._cbs[3]); core.retro_set_input_poll(self._cbs[4]); core.retro_set_input_state(self._cbs[5])
        if not core.retro_load_game(C.byref(H.GameInfo(rom.encode(), None, 0, None))): raise RuntimeError('load failed: ' + rom)
        core.retro_set_controller_port_device(0, 1); core.retro_set_controller_port_device(1, 1)
        core.retro_serialize_size.restype = C.c_size_t

    def _env(self, cmd, data):
        if cmd in (9, 31):
            C.cast(data, C.POINTER(C.c_void_p))[0] = C.cast(self._sys if cmd == 9 else self._save, C.c_void_p); return True
        if cmd == 10: return C.cast(data, C.POINTER(C.c_uint))[0] == 1
        if cmd == 15:
            v = C.cast(data, C.POINTER(H.Variable))[0]; val = self._opt.get(v.key)
            C.cast(data, C.POINTER(H.Variable))[0].value = val.value if val else None; return val is not None
        if cmd == 17: C.cast(data, C.POINTER(C.c_bool))[0] = False; return True
        if cmd == 52: C.cast(data, C.POINTER(C.c_uint))[0] = 2; return True
        if cmd == 39: C.cast(data, C.POINTER(C.c_uint))[0] = 0; return True
        return cmd in (11, 37, 55, 67, 68, 69, 0x10000 | 36)

    def _vid(self, data, w, h, pitch):
        if data and self.want_video: self.video = (C.string_at(data, pitch * h), w, h, pitch)

    def _input(self, port, dev, idx, id):
        if dev != 1 or port > 1 or id > 15: return 0
        return (self.pads[port] >> id) & 1

    def save(self):
        n = self.core.retro_serialize_size(); b = C.create_string_buffer(n)
        assert self.core.retro_serialize(b, C.c_size_t(n)); return b.raw

    def load(self, blob):
        b = C.create_string_buffer(blob, len(blob)); assert self.core.retro_unserialize(b, C.c_size_t(len(blob)))

    def frame(self, p0, p1, video=False):
        if p0 & RESET_BIT: self.core.retro_reset()
        self.pads = [p0 & 0x7FFF, p1]; self.want_video = video; self.video = None
        self.core.retro_run()
        return self.picture() if video else None

    def picture(self):
        from PIL import Image
        if not self.video: return None
        data, w, h, pitch = self.video
        return Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')


def replay(d):
    """one bundle: replay + determinism check + sheet / clip; writes replay.json"""
    from PIL import Image, ImageChops, ImageDraw
    meta = json.load(open(os.path.join(d, 'meta.json')))
    res = {'ok': False}
    def done(**k):
        res.update(k); json.dump(res, open(os.path.join(d, 'replay.json'), 'w'), indent=1); return res
    if not os.path.exists(os.path.join(d, 'inputs.bin')): return done(error='no capture in the bundle (the game was not running)')
    raw = open(os.path.join(d, 'inputs.bin'), 'rb').read()
    magic, ver, W, P = struct.unpack_from('<4sIQQ', raw)
    if magic != b'NSIN' or ver != 1: return done(error='inputs.bin: unknown format')
    pads = [struct.unpack_from('<HH', raw, 24 + 4 * i) for i in range(P - W)]
    res.update(window_frame=W, press_frame=P, frames=P - W, seconds=round((P - W) / 59.185606, 1),
               resets=sum(1 for p in pads if p[0] & RESET_BIT))
    if meta.get('bios_sha256') and meta['bios_sha256'] != sha_file(os.path.join(H.SYSDIR, 'neogeo.zip')):
        return done(error='BIOS differs from ' + H.SYSDIR + '/neogeo.zip')
    rom = find_rom(meta)
    if not rom: return done(error=f"ROM sha256 {meta.get('rom_sha256')} (v{meta.get('rom_version')}) not found locally nor on the VPS")
    res['rom'] = rom
    core = Core(rom, meta.get('system_type', 'mvs'), meta.get('hw', 'mvs'), meta.get('memcard', 'on'))   # older bundles: on
    snaps = {int(os.path.basename(p)[5:-6]): p for p in glob.glob(os.path.join(d, 'snap_*.state'))}
    start = snaps.get(W)
    core.load(open(start or os.path.join(d, 'press.state'), 'rb').read())
    checks = sorted(f for f in snaps if W < f <= P) + [P]
    mismatch = None; ci = 0
    pics = []                                                   # (frame, picture) of the last CLIP/SHEET seconds
    keep = int(max(SHEET_S, CLIP_S) * 60)
    for i, (p0, p1) in enumerate(pads):
        f = W + i
        while ci < len(checks) and checks[ci] == f:               # the state before frame f
            want = open(snaps[f] if f in snaps and f != P else os.path.join(d, 'press.state'), 'rb').read()
            got = core.save()
            if got != want and mismatch is None:
                off = next((k for k in range(min(len(got), len(want))) if got[k] != want[k]), min(len(got), len(want)))
                prev = max([W] + [c for c in checks if c < f])
                mismatch = {'checkpoint': f, 'since': prev, 'byte': off, 'sizes': [len(got), len(want)]}
            ci += 1
        img = core.frame(p0, p1, video=P - f <= keep)
        if img is not None: pics.append((f, img))
    if ci < len(checks):                                        # the press itself (no frames ran after the last check)
        got = core.save(); want = open(os.path.join(d, 'press.state'), 'rb').read()
        if got != want and mismatch is None:
            off = next((k for k in range(min(len(got), len(want))) if got[k] != want[k]), min(len(got), len(want)))
            mismatch = {'checkpoint': P, 'since': max([W] + [c for c in checks if c < P]), 'byte': off}
    res['deterministic'] = mismatch is None; res['mismatch'] = mismatch; res['checkpoints'] = len(checks)
    # the last picture vs the player's screenshot
    shot = os.path.join(d, 'screen.png')
    if os.path.exists(shot) and pics:
        a = Image.open(shot).convert('RGB'); b = pics[-1][1]
        res['screen_match'] = a.size == b.size and ImageChops.difference(a, b).getbbox() is None
    # contact sheet: 16 frames over the last SHEET_S seconds + the press screenshot; clip: the last CLIP_S seconds
    if pics:
        sel = [p for p in pics if P - p[0] <= SHEET_S * 60]
        step = max(1, len(sel) // 15); sel = sel[::step][-15:]
        tw, th = sel[0][1].size
        sheet = Image.new('RGB', (tw * 4, (th + 14) * 4), (255, 255, 255)); dr = ImageDraw.Draw(sheet)
        marked = os.path.join(d, 'screen_marked.png')         # 0.0.15: his drawing over the screenshot (screen.png stays clean)
        press = (('press screenshot, his drawing', Image.open(marked).convert('RGB').resize((tw, th), Image.LANCZOS)) if os.path.exists(marked)
                 else ('press screenshot', Image.open(shot).convert('RGB')) if os.path.exists(shot) else None)
        tiles = [(f'frame {f} (P-{P - f})', im) for f, im in sel][-(15 if press else 16):] + ([press] if press else [])
        for k, (lab, im) in enumerate(tiles[:16]):
            x, y = k % 4 * tw, k // 4 * (th + 14)
            sheet.paste(im, (x, y + 14)); dr.text((x + 3, y + 1), lab, fill=(0, 0, 0))
        sheet.save(os.path.join(d, 'sheet.png'))
        clip = [im for f, im in pics if P - f <= CLIP_S * 60][::2]
        clip[0].save(os.path.join(d, 'clip.gif'), save_all=True, append_images=clip[1:], duration=33, loop=0)
        res['sheet'] = os.path.join(d, 'sheet.png'); res['clip'] = os.path.join(d, 'clip.gif')
    return done(ok=True)


def report(d, row=None):
    meta = json.load(open(os.path.join(d, 'meta.json')))
    rp = json.load(open(os.path.join(d, 'replay.json'))) if os.path.exists(os.path.join(d, 'replay.json')) else {}
    tx = open(os.path.join(d, 'transcript.txt')).read().strip() if os.path.exists(os.path.join(d, 'transcript.txt')) else '(no transcript yet)'
    tj = json.load(open(os.path.join(d, 'transcript.json'))) if os.path.exists(os.path.join(d, 'transcript.json')) else {}
    if not rp.get('ok'): det = 'replay failed: ' + rp.get('error', '?')
    elif rp['deterministic']: det = f"OK: byte-identical at all {rp['checkpoints']} checkpoints incl. the press"
    else:
        m = rp['mismatch']; det = f"MISMATCH: first differing state at frame {m['checkpoint']} (identical at {m['since']}), byte {m['byte']}"
    final = (row or {}).get('final_text') or meta.get('final_text', '')
    raw = (row or {}).get('raw_transcript') or meta.get('raw_transcript', '')
    if raw: tx = raw
    L = [f"# Feedback {meta['id']}", '']
    if row and row.get('user'): L += [f"From: {row['user']}", '']
    if row: L += [f"Status: {row['status']}" + (f" (release {row['release']})" if row['release'] else '') +
                  (f", category {row['category']}" if row['category'] else '') + (f", fighters {row['fighters']}" if row['fighters'] else ''), '']
    L += ['## Note (as sent)', '', final or '(none typed)', '', '## Transcript (raw)', '', tx, '']
    if row and row.get('replies'):
        L += ['## Thread (his replies)', ''] + ['- ' + t.strip() for t in fb.thread(row['replies'], '')] + ['']
        L += [f"  voice: {os.path.join(d, x['audio_path'])}" for x in row['replies'] if x.get('audio_path')] + ['']
    if tj: L += [f"_({tj.get('model')}, {tj.get('seconds')} s)_", '']
    elif meta.get('transcript_model'): L += [f"_({meta['transcript_model']}, in the player)_", '']
    L += ['## Versions', '', '| | |', '|---|---|',
          f"| Player | {meta.get('app_version')} (code {meta.get('app_code')}) |",
          f"| Game | v{meta.get('rom_version')} build {meta.get('rom_build')}, sha256 `{meta.get('rom_sha256')}` |",
          f"| System | {meta.get('system_type')} BIOS, {meta.get('hw')} hardware, region {meta.get('region')}, BIOS sha256 `{meta.get('bios_sha256', '')[:16]}...` |",
          f"| Device | {meta.get('device')}, Android {meta.get('android')} |",
          f"| Recorded | {meta.get('created')}, held {meta.get('held_ms')} ms |", '',
          '## Replay', '', f'- Determinism: {det}']
    if rp.get('frames') is not None:
        L.append(f"- Window: frames {rp['window_frame']}..{rp['press_frame']} ({rp['frames']} frames, {rp['seconds']} s), soft resets in it: {rp['resets']}")
    if 'screen_match' in rp: L.append(f"- Last replayed picture = the player's screenshot: {'yes' if rp['screen_match'] else 'NO'}")
    if rp.get('sheet'): L += [f"- Contact sheet: {rp['sheet']}", f"- Clip (last {CLIP_S} s): {rp['clip']}", f"- Screenshot: {os.path.join(d, 'screen.png')}"]
    marked = os.path.exists(os.path.join(d, 'screen_marked.png'))
    if marked: L.append(f"- Marked screenshot (drawn on in the player; the replay checks the clean screen.png): {os.path.join(d, 'screen_marked.png')}")
    L += [''] + (['![marked screenshot](screen_marked.png)', ''] if marked else []) + ['![sheet](sheet.png)', '']
    open(os.path.join(d, 'report.md'), 'w').write('\n'.join(L))
    short = (final or tx).replace('\n', ' ')[:70]
    return f"{meta['id']}  {(row or {}).get('user') or '-'}  {'marked  ' if marked else ''}player {meta.get('app_version')}  game v{meta.get('rom_version')}  {det.split(':')[0]}  \"{short}\""


def main():
    a = sys.argv[1:]
    if a[:1] == ['--replay']: replay(a[1]); return
    os.makedirs(OUT, exist_ok=True)
    if '--local' not in a:
        r = subprocess.run(['rsync', '-a', '--itemize-changes', f'{HOST}:{REMOTE}', OUT + '/'], capture_output=True, text=True)
        if r.returncode: print('fetch failed:', r.stderr.strip()); return
        os.makedirs(os.path.join(OUT, '_server', 'backups'), exist_ok=True)
        subprocess.run(['rsync', '-a', f'{HOST}:/data/brawler/feedback/backups/', os.path.join(OUT, '_server', 'backups') + '/'], capture_output=True)
    rows = {}
    try:
        rows = {r['id']: r for r in fb.api('list')['rows']}
        for bid, r in rows.items():
            if r['status'] == 'new' and os.path.isdir(os.path.join(OUT, bid)):
                rows[bid] = fb.api('status', {'id': bid, 'status': 'read', 'by': 'pull.py', 'note': 'pulled to ' + os.path.join(OUT, bid)})['row']
    except Exception as e: print('tracker:', e)
    dirs = sorted(p for p in glob.glob(os.path.join(OUT, '*')) if os.path.exists(os.path.join(p, 'meta.json')))
    built = False
    order = {'reopened': 0}                                 # reopened notes first
    dirs.sort(key=lambda d: order.get((rows.get(os.path.basename(d)) or {}).get('status'), 1))
    for d in dirs:
        rep = os.path.join(d, 'report.md')
        newest = max(os.path.getmtime(os.path.join(d, f)) for f in os.listdir(d) if f not in ('report.md', 'replay.json', 'sheet.png', 'clip.gif'))
        if '--all' not in a and os.path.exists(rep) and os.path.getmtime(rep) >= newest and os.path.basename(d) not in rows: continue
        if not os.path.exists(os.path.join(d, 'replay.json')) or '--all' in a:
            if not built: build_core(); built = True
            subprocess.run([sys.executable, os.path.abspath(__file__), '--replay', d])
        print(report(d, rows.get(os.path.basename(d))))
    if rows: overview(rows)


def overview(rows):
    """/data/feedback/report.md: every note with its status and thread, reopened first, then shipped (to verify), open,
    and the closed ones (verified, won't do, duplicate)"""
    rank = lambda r: {'reopened': 0, 'shipped': 1, 'verified': 3, 'wont_do': 3, 'duplicate': 3}.get(r['status'], 2)
    L = ['# Feedback overview', '', f'{len(rows)} notes; reopened first. Per note: /data/feedback/<id>/report.md', '']
    head = {0: 'Reopened (still broken)', 1: 'Shipped, to verify', 2: 'Open', 3: 'Closed (verified / won\'t do / duplicate)'}
    last = None
    for r in sorted(rows.values(), key=lambda r: (rank(r), r['created'])):
        if rank(r) != last: L += ([''] if last is not None else []) + [f'## {head[rank(r)]}', '']; last = rank(r)
        L.append('- ' + fb.line(r))
        L += ['  ' + t for t in fb.thread(r.get('replies'), '  ')]
    open(os.path.join(OUT, 'report.md'), 'w').write('\n'.join(L) + '\n')
    print('overview:', os.path.join(OUT, 'report.md'), f"({sum(r['status'] == 'reopened' for r in rows.values())} reopened)")


if __name__ == '__main__':
    main()
