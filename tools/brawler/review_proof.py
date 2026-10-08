#!/usr/bin/env python3
"""Proof of the fighter review pages (revamp phase 4): review_build.py's data and review.html in headless Chrome.

  1. every clip's frame count against the data: a piece = its move's length as the game plays it (chainlab.json
     moves[].total and its 1C segments; a special's first hit = its segments' startup + window + recovery, the
     special's whole segments = the export's; the throw = its rows at its speed); the chain and every finisher's clip
     = each link to its last hit's contact + its hit-stop, then the finisher whole + its hit-stop (the back throw: none);
     every proposed sequence has 3 hits or more (pieces.MIN_HITS)
  2. each page in headless Chrome at phone width (390) and desktop (1500): rendered, every card and clip there, no
     sideways scroll at phone width, a screenshot; a visible clip's frames played over 2 s = 2 s x 59.18 (+-3)
  3. (with API_BASE) an answer saves and reads back: on FIGHTER's page the first piece's Drop is pressed, the page is
     reloaded and must show it pressed (read back from the store), then the test answer is deleted from the store
     (ssh to the VPS: DATA/decisions/review-FIGHTER.json; the file removed when the test made it)

    python3 tools/brawler/review_proof.py SITE_DIR GAME_DIR OUT_DIR [API_BASE [FIGHTER]]
SITE_DIR is served on a local port by this script; feedback-api/ is passed to API_BASE (e.g. an ssh tunnel to the
feedback service: ssh -L 18920:127.0.0.1:8920 root@VPS, API_BASE http://127.0.0.1:18920/api/)."""
import functools, http.server, json, os, subprocess, sys, threading, urllib.error, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review_build as RB
import pieces as PC
VPS = 'root@195.201.91.211'
STORE = '/data/brawler/feedback/decisions'


def check_data(site, game):
    lab = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    G = json.load(open(os.path.join(game, 'game.json')))
    ok = True
    for e in json.load(open(os.path.join(site, 'review', 'index.json')))['fighters']:
        d = json.load(open(os.path.join(site, 'review', e['fighter'] + '.json')))
        lf = next(f for f in lab['fighters'] if f['name'] == e['fighter'])
        bad = []
        for p in d['pieces']:
            n = len(d['clips'][p['id']]['frames']); c = d['checks'][p['id']]
            if p['kind'] in ('normal', 'command'):
                want = lf['moves'][p['id']]['total']
                if n != want or lf['segs']['moves'][p['id']] != p['segs']: bad.append((p['id'], n, want))
            elif p['kind'] == 'air':
                if n != sum(lf['segs']['moves'][p['id']]): bad.append((p['id'], n, lf['segs']['moves'][p['id']]))
            elif p['kind'] == 'special':
                if n != sum(p['segs']) or (c['data_segs'] and c['data_segs'] != c['segs_all']): bad.append((p['id'], n, c['data_segs'], c['segs_all']))
            elif p['kind'] == 'throw':
                if n != -(-c['rows'] * 256 // c['speed']): bad.append((p['id'], n, c))
        by = {p['id']: p for p in d['pieces']}
        hs = RB.hitstops(G, d['proposal']['chain']['length'])
        links = [by[i] for i in d['proposal']['chain']['links']]
        head = 0
        for k, p in enumerate(links):
            s = p['segs']; last_win = sum(s[:len(s) - 2])          # the last window's first frame
            head += last_win + 1 + hs[k]
        fins = d['proposal']['finishers']
        for key, stick in [('chain', 'neutral')] + [('fin-' + k, k) for k in ('neutral', 'forward', 'up', 'down', 'back')]:
            pid = fins[stick]['pick']
            if not pid: continue
            want = head + len(d['clips'][pid]['frames']) + (0 if stick == 'back' else hs[-1])
            got = len(d['clips'][key]['frames'])
            hits = sum(max(1, q['hits']) for q in links + [by[pid]])
            if got != want or hits < PC.MIN_HITS: bad.append((key, got, want, 'hits', hits))
        nfin = sum(1 for k in d['clips'] if k.startswith('fin-'))
        print(f"{e['fighter']}: {len(d['pieces'])} piece clips + chain + {nfin} finishers (whole chain each, {d['proposal']['chain']['hits']}+ hits);",
              'frame counts OK' if not bad else f'MISMATCH {bad}')
        ok &= not bad
    return ok


class Handler(http.server.SimpleHTTPRequestHandler):
    api = None

    def log_message(self, *a): pass

    def proxy(self, method):
        if not self.api: return self.send_error(404)
        n = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(n) if n else None
        req = urllib.request.Request(self.api + self.path.split('feedback-api/', 1)[1], data=body, method=method,
                                     headers={'Content-Type': self.headers.get('Content-Type', 'application/json')})
        try:
            with urllib.request.urlopen(req, timeout=20) as r: code, data = r.status, r.read()
        except urllib.error.HTTPError as e: code, data = e.code, e.read()
        self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if '/feedback-api/' in self.path: return self.proxy('GET')
        return super().do_GET()

    def do_POST(self):
        if '/feedback-api/' in self.path: return self.proxy('POST')
        self.send_error(405)


def serve(site, api):
    Handler.api = api
    srv = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(Handler, directory=site))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f'http://127.0.0.1:{srv.server_address[1]}'


def headless(url, steps, out, name):
    sp = os.path.join(out, name + '_steps.json'); json.dump(steps, open(sp, 'w'))
    subprocess.run(['node', os.path.join(HERE, 'chainlab', 'headless.js'), url, sp], check=True, capture_output=True)


def check_pages(site, out, base):
    ok = True
    for e in json.load(open(os.path.join(site, 'review', 'index.json')))['fighters']:
        f = e['fighter']
        steps = [{'wait': 2500},
                 {'eval': "JSON.stringify({ready: !!window.reviewReady, cards: document.querySelectorAll('.card').length, clips: document.querySelectorAll('.clip canvas').length, nav: document.querySelectorAll('nav.who a').length, groups: document.querySelectorAll('nav.who .group').length})", 'save': f'{out}/{f}_desk.json'},
                 {'eval': "(async()=>{const s0=reviewStats(); await new Promise(r=>setTimeout(r,2000)); const s1=reviewStats(); const o={}; for (const k in s1) if (s1[k].ms>s0[k].ms) o[k]={len:s1[k].len, frames:s1[k].played-s0[k].played, ms:Math.round(s1[k].ms-s0[k].ms)}; return o;})()", 'save': f'{out}/{f}_rate.json'},
                 {'shot': f'{out}/{f}_desktop.png'},
                 {'width': 390, 'height': 844, 'mobile': True}, {'wait': 1200},
                 {'shot': f'{out}/{f}_phone.png'},
                 {'eval': "document.querySelector('#p-chain').scrollIntoView(); 1"}, {'wait': 800},
                 {'shot': f'{out}/{f}_phone_chain.png'},
                 {'eval': "JSON.stringify({w: document.documentElement.scrollWidth, cards: document.querySelectorAll('.card').length})", 'save': f'{out}/{f}_phone.json'}]
        headless(f'{base}/review.html?f={f}', steps, out, f)
        desk = json.loads(json.load(open(f'{out}/{f}_desk.json'))); rate = json.load(open(f'{out}/{f}_rate.json'))
        ph = json.loads(json.load(open(f'{out}/{f}_phone.json')))
        d = json.load(open(os.path.join(site, 'review', f + '.json')))
        want_cards = len(d['pieces']) + 2 + sum(1 for k in d['clips'] if k.startswith('fin-')) + 1 + 1   # + roles, general
        nfight = len(json.load(open(os.path.join(site, 'review', 'index.json')))['fighters'])
        r_ok = all(abs(v['frames'] - v['ms'] * 59.18 / 1000) <= 3 for v in rate.values()) and rate
        good = (desk['ready'] and desk['cards'] == want_cards and desk['clips'] == len(d['clips']) and ph['w'] <= 390 and r_ok
                and desk['nav'] == nfight and desk['groups'] == 3)
        print(f"{f}: page {'OK' if good else 'FAIL'}: {desk['cards']} cards ({want_cards}), {desk['clips']} clips ({len(d['clips'])}), "
              f"nav {desk['nav']} fighters in {desk['groups']} groups, phone width {ph['w']}, "
              + '; '.join(f"{k} {v['frames']} frames in {v['ms']} ms" for k, v in list(rate.items())[:3]))
        ok &= bool(good)
    return ok


def check_answer(site, out, base, api, f):
    """press Drop on the first piece of f's page, reload, read it back, delete the test answer"""
    d = json.load(open(os.path.join(site, 'review', f + '.json')))
    pid = d['pieces'][0]['id']; st = 'review-' + f
    before = json.load(urllib.request.urlopen(api + 'decisions/' + st))
    if pid in before:
        print(f'answer: {st}/{pid} already answered (by Bruno): not touched, test skipped'); return False
    sel = f"#p-{pid} .dopts button[data-opt=\"1\"]"
    steps = [{'wait': 2500}, {'eval': f"document.querySelector('{sel}').click(); 1"}, {'wait': 1500},
             {'eval': "document.querySelector('#p-%s .dsaved').textContent" % pid, 'save': f'{out}/answer_saved.json'},
             {'eval': 'location.reload(); 1'}, {'wait': 3000},
             {'eval': f"JSON.stringify({{pressed: document.querySelector('{sel}').getAttribute('aria-pressed'), status: document.querySelector('.status').textContent}})", 'save': f'{out}/answer_back.json'}]
    headless(f'{base}/review.html?f={f}', steps, out, 'answer')
    saved = json.load(open(f'{out}/answer_saved.json')); back = json.loads(json.load(open(f'{out}/answer_back.json')))
    stored = json.load(urllib.request.urlopen(api + 'decisions/' + st)).get(pid, {})
    ok = saved == 'Saved' and back['pressed'] == 'true' and stored.get('choice') == 1
    # delete it: the store's file without that id (removed when the test made the file)
    prog = ("import json, os, sys; p = sys.argv[1]; k = sys.argv[2]; d = json.load(open(p)); d.pop(k, None)\n"
            "if d: json.dump(d, open(p + '.part', 'w'), indent=1, ensure_ascii=False); os.replace(p + '.part', p)\n"
            "else: os.remove(p)\nprint('left', len(d))")
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', VPS, 'python3', '-', f'{STORE}/{st}.json', pid], input=prog,
                       capture_output=True, text=True)
    after = json.load(urllib.request.urlopen(api + 'decisions/' + st))
    gone = pid not in after and after == before
    print(f"answer: {st}/{pid} Drop -> '{saved}', after reload pressed={back['pressed']} ({back['status']}), store choice "
          f"{stored.get('choice')}; deleted ({r.stdout.strip() or r.stderr.strip()}): store as before {gone}")
    return ok and gone


if __name__ == '__main__':
    site, game, out = sys.argv[1:4]
    api = sys.argv[4] if len(sys.argv) > 4 else None
    os.makedirs(out, exist_ok=True)
    srv, base = serve(site, api)
    a = check_data(site, game); b = check_pages(site, out, base)
    c = check_answer(site, out, base, api, sys.argv[5] if len(sys.argv) > 5 else 'ryo') if api else True
    srv.shutdown()
    print('ALL OK' if a and b and c else 'FAILED')
