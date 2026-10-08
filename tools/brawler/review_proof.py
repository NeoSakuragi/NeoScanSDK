#!/usr/bin/env python3
"""Proof of the fighter review pages (revamp phase 4): review_build.py's data and review.html in headless Chrome.

  1. every clip's frame count against the data: a piece = its move's length as the game plays it (chainlab.json
     moves[].total and its 1C segments; a special's first hit = its segments' startup + window + recovery, the
     special's whole segments = the export's; the throw = its rows at its speed); the chain = each link to its last
     hit's contact + its hit-stop, the neutral finisher whole + its hit-stop
  2. each page in headless Chrome at phone width (390) and desktop (1500): rendered, every card and clip there, a
     screenshot; a visible clip's frames played over 2 s = 2 s x 59.18 (+-3)

    python3 tools/brawler/review_proof.py SITE_DIR GAME_DIR OUT_DIR URL_BASE      (URL_BASE serves SITE_DIR)"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review_build as RB


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
        want = 0
        for k, p in enumerate(links):
            s = p['segs']; last_win = sum(s[:len(s) - 2])          # the last window's first frame
            want += last_win + 1 + hs[k]
        nf = by[d['proposal']['finishers']['neutral']['pick']]
        want += len(d['clips'][nf['id']]['frames']) + hs[-1]
        if len(d['clips']['chain']['frames']) != want: bad.append(('chain', len(d['clips']['chain']['frames']), want))
        print(f"{e['fighter']}: {len(d['pieces'])} piece clips + chain + {sum(1 for k in d['clips'] if k.startswith('fin-'))} finishers;",
              'frame counts OK' if not bad else f'MISMATCH {bad}')
        ok &= not bad
    return ok


def check_pages(site, out, base):
    ok = True
    js = os.path.join(HERE, 'chainlab', 'headless.js')
    for e in json.load(open(os.path.join(site, 'review', 'index.json')))['fighters']:
        f = e['fighter']
        steps = [{'wait': 2500},
                 {'eval': "JSON.stringify({ready: !!window.reviewReady, cards: document.querySelectorAll('.card').length, clips: document.querySelectorAll('.clip canvas').length})", 'save': f'{out}/{f}_desk.json'},
                 {'eval': "(async()=>{const s0=reviewStats(); await new Promise(r=>setTimeout(r,2000)); const s1=reviewStats(); const o={}; for (const k in s1) if (s1[k].ms>s0[k].ms) o[k]={len:s1[k].len, frames:s1[k].played-s0[k].played, ms:Math.round(s1[k].ms-s0[k].ms)}; return o;})()", 'save': f'{out}/{f}_rate.json'},
                 {'shot': f'{out}/{f}_desktop.png'},
                 {'width': 390, 'height': 844, 'mobile': True}, {'wait': 1200},
                 {'shot': f'{out}/{f}_phone.png'},
                 {'eval': "document.querySelector('#p-chain').scrollIntoView(); 1"}, {'wait': 800},
                 {'shot': f'{out}/{f}_phone_chain.png'},
                 {'eval': "JSON.stringify({w: document.documentElement.scrollWidth, cards: document.querySelectorAll('.card').length})", 'save': f'{out}/{f}_phone.json'}]
        sp = os.path.join(out, f + '_steps.json'); json.dump(steps, open(sp, 'w'))
        subprocess.run(['node', js, f'{base}/review.html?f={f}', sp], check=True, capture_output=True)
        desk = json.loads(json.load(open(f'{out}/{f}_desk.json'))); rate = json.load(open(f'{out}/{f}_rate.json'))
        ph = json.loads(json.load(open(f'{out}/{f}_phone.json')))
        d = json.load(open(os.path.join(site, 'review', f + '.json')))
        want_cards = len(d['pieces']) + 2 + sum(1 for k in d['clips'] if k.startswith('fin-')) + 1
        r_ok = all(abs(v['frames'] - v['ms'] * 59.18 / 1000) <= 3 for v in rate.values()) and rate
        good = desk['ready'] and desk['cards'] == want_cards and desk['clips'] == len(d['clips']) and ph['w'] <= 390 and r_ok
        print(f"{f}: page {'OK' if good else 'FAIL'}: {desk['cards']} cards ({want_cards}), {desk['clips']} clips ({len(d['clips'])}), phone width {ph['w']}, "
              + '; '.join(f"{k} {v['frames']} frames in {v['ms']} ms" for k, v in rate.items()))
        ok &= bool(good)
    return ok


if __name__ == '__main__':
    site, game, out, base = sys.argv[1:5]
    os.makedirs(out, exist_ok=True)
    a = check_data(site, game); b = check_pages(site, out, base)
    print('ALL OK' if a and b else 'FAILED')
