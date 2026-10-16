#!/usr/bin/env python3
"""Live wall proof (wall.js): fake LIVE sessions for a LOCAL feedback service. Each one replays a recorded session
(the storage layout: wall_synth_node.js output or /mnt/storagebox/brawler-sessions/<id>) under a new session id, in
real time: chunk k is posted when its last frame would have been played (as the Player sends it), starting at a
keyframe (session n starts n x --spread keyframes into the recording, so the tiles show different moments).
NEVER point it at the live server: it refuses any URL that is not 127.0.0.1 / localhost.

    wall_feed.py --api http://127.0.0.1:8972/ --oros http://127.0.0.1:8971/ --n 4 [--seconds 180] [--spread 2]
                 [--end-after N:SECONDS ...] TEMPLATE_DIR [TEMPLATE_DIR ...]
    (--end-after 2:60: session 2 stops after 60 s: an ended session leaving the wall)"""
import argparse, json, os, struct, sys, threading, time, urllib.request, urllib.error
ap = argparse.ArgumentParser()
ap.add_argument('--api', default='http://127.0.0.1:8972/'); ap.add_argument('--oros', default='http://127.0.0.1:8971/')
ap.add_argument('--n', type=int, default=1); ap.add_argument('--seconds', type=float, default=180); ap.add_argument('--spread', type=int, default=2)
ap.add_argument('--user', default='sp-tester'); ap.add_argument('--end-after', action='append', default=[])
ap.add_argument('templates', nargs='+')
a = ap.parse_args()
for u in (a.api, a.oros):
    if urllib.parse.urlparse(u).hostname not in ('127.0.0.1', 'localhost'): sys.exit('a LOCAL service only: ' + u)
FPS = 59.185606
tok = json.load(urllib.request.urlopen(urllib.request.Request(a.oros + 'api/login', json.dumps({'username': a.user, 'password': 'pw'}).encode(),
                                                              {'Content-Type': 'application/json'})))['token']
ends = {int(x.split(':')[0]): float(x.split(':')[1]) for x in a.end_after}


def post(body):
    try:
        r = urllib.request.urlopen(urllib.request.Request(a.api + 'sessions/chunk', body, {'X-Public': '1', 'Authorization': 'Bearer ' + tok}, method='POST'))
        return r.status
    except urllib.error.HTTPError as e: return e.code
    except OSError: return 0


def feed(n, src, t0):
    meta0 = json.load(open(os.path.join(src, 'meta.json')))
    seqs = sorted(int(f[:6]) for f in os.listdir(src) if f.endswith('.nsin'))
    keys = [q for q in seqs if os.path.exists(os.path.join(src, '%06d.state.gz' % q))]
    start = keys[min(len(keys) - 1, n * a.spread)]
    sid = '%08x-%s' % (0xfa000000 + n, time.strftime('%Y%m%d-%H%M%S', time.gmtime(t0)))
    stop = min(a.seconds, ends.get(n, a.seconds)); played = 0; sent = 0
    for q in [s for s in seqs if s >= start]:
        f = lambda e: os.path.join(src, '%06d%s' % (q, e))
        nsin = open(f('.nsin'), 'rb').read(); W, P = struct.unpack_from('<QQ', nsin, 8)
        played += (P - W) / FPS
        if played > stop: break
        wait = t0 + played - time.time()
        if wait > 0: time.sleep(wait)
        gz = open(f('.state.gz'), 'rb').read() if os.path.exists(f('.state.gz')) else b''
        m = dict(meta0, session=sid, seq=q, start_frame=W, frames=P - W, key=bool(gz), state='gzip' if gz else 'none',
                 state_sha256=open(f('.sha256')).read().strip(), started=int(t0 * 1000), sent=int(time.time() * 1000))
        for k in ('received', 'user', 'synth'): m.pop(k, None)
        mb = json.dumps(m).encode()
        s = post(b'NSCK' + struct.pack('<II', 1, len(mb)) + mb + struct.pack('<I', len(nsin)) + nsin + struct.pack('<I', len(gz)) + gz)
        if s != 200: print(sid, q, 'HTTP', s, flush=True)
        sent += 1
    print(sid, 'ended after', sent, 'chunks', flush=True)


t0 = time.time()
th = [threading.Thread(target=feed, args=(n, a.templates[n % len(a.templates)], t0), daemon=True) for n in range(a.n)]
for t in th: t.start()
print('feeding', a.n, 'sessions for', a.seconds, 's', flush=True)
for t in th: t.join()
