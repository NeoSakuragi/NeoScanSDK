#!/usr/bin/env python3
"""Proof of the THROW REVIEW page (review.html?q=throws, review.js "the throw review", data tools/brawler/throw_review.py):

  1. the data: every row's sheet holds its frames, its per-frame file has one entry per frame
  2. the page in headless Chrome at the 6" split-view phone width (360 x 640) and desktop (1500): every row there, no
     sideways scroll on the phone, a row opened (its frame drawn, a strip button per frame), screenshots
  3. (with --answer) an answer round-trips through the feedback service (an ssh tunnel to it on the VPS): on ROW
     (default robert-fwd) IMPACT is pressed and "Damage here" on its first impact frame; the store must hold choice 0
     and that dmg flag, the reloaded page must show them; then the test answer is deleted from the store (ssh:
     DATA/decisions/throws.json; the file removed when the test made it). Skipped when ROW is answered already.

    python3 tools/brawler/throw_review_proof.py SITE_DIR OUT_DIR [--set throws2] [--answer [ROW]]
--set throws2: round 2 (review.html?q=throws2: impact / launch / held): every row links the capture judged in round 1
(served next to it), the open row shows both captures (now / judged) and, with --answer (the store reachable), its
proposal from the round-1 answer (set "throws"); --answer presses "Confirm proposed" on ROW (the store must hold choice 0
and the proposal's impact flag), then deletes it as above.
SITE_DIR: throw_review.py's OUT (review/throws/); the pages (review.html, review.js, micnote.js) are copied into it."""
import json, os, shutil, subprocess, sys, time, urllib.request
from PIL import Image
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from review_proof import serve, headless, VPS, STORE

PORT = 18921


SET = 'throws'
API_ON = False


def check_data(site):
    IX = json.load(open(os.path.join(site, 'review', SET, 'index.json')))
    ok = True
    for r in IX['rows']:
        im = Image.open(os.path.join(site, r['sheet'])); d = json.load(open(os.path.join(site, r['data'])))
        rows_needed = -(-r['frames'] // r['cols'])
        good = im.size == (r['cols'] * r['w'], rows_needed * r['h']) and len(d['rows']) == len(d['states']) == len(d['hp']) == r['frames']
        if SET == 'throws2':                                       # (the judged capture it links: served next to it)
            good &= 'prev' in r and os.path.exists(os.path.join(site, r['prev']['sheet'])) and os.path.exists(os.path.join(site, r['prev']['data']))
        ok &= good
        print(f"{r['id']:16s} {r['frames']:3d} frames, sheet {im.size[0]}x{im.size[1]}: {'OK' if good else 'MISMATCH'}")
    return IX, ok


def check_page(site, out, base, IX):
    n = len(IX['rows']); first = IX['rows'][0]
    js_open = ("(async()=>{document.querySelector('.thead').click(); await new Promise(r=>setTimeout(r,1500));"
               "const cv=document.querySelector('canvas.tframe'); const px=cv.getContext('2d').getImageData(0,0,cv.width,cv.height).data;"
               "let ink=0; for(let i=0;i<px.length;i+=4) if(px[i]+px[i+1]+px[i+2]<700) ink++;"
               "return JSON.stringify({ink, strip: document.querySelectorAll('.tstrip button').length, w: document.documentElement.scrollWidth,"
               " line: document.querySelector('.fline').textContent, mic: document.querySelectorAll('.micbtn').length,"
               " prop: (document.querySelector('.prop:not([hidden])') || {}).textContent || '',"
               " caps: document.querySelectorAll('.tbody [aria-label=\"Which capture\"] button').length});})()")
    steps = [{'width': 360, 'height': 640, 'mobile': True}, {'wait': 2500},
             {'eval': "JSON.stringify({ready: !!window.reviewReady, rows: document.querySelectorAll('li.trow').length, w: document.documentElement.scrollWidth, status: document.querySelector('.sub[role=status]').textContent})", 'save': f'{out}/list.json'},
             {'shot': f'{out}/phone_list.png'},
             {'eval': js_open, 'save': f'{out}/open.json'},
             {'shot': f'{out}/phone_open.png'}, {'eval': 'window.scrollBy(0, 560); 1'}, {'wait': 300}, {'shot': f'{out}/phone_open2.png'},
             {'width': 1500, 'height': 1000}, {'wait': 800}, {'eval': 'window.scrollTo(0, 0); 1'}, {'shot': f'{out}/desktop.png'}]
    headless(f'{base}/review.html?q={SET}', steps, out, 'page')
    L = json.loads(json.load(open(f'{out}/list.json'))); O = json.loads(json.load(open(f'{out}/open.json')))
    ok = L['ready'] and L['rows'] == n and L['w'] <= 360 and O['ink'] > 1000 and O['strip'] == first['frames'] and O['w'] <= 360 and O['mic'] == 1
    if SET == 'throws2':
        ok &= O['caps'] == 2 and (O['prop'].startswith('Proposed') or not API_ON)
        print(f"round 2: {O['caps']} captures shown, proposal '{O['prop']}'")
    print(f"page: {'OK' if ok else 'FAIL'}: {L['rows']} rows ({n}), phone width {L['w']} / {O['w']} (360), {L['status']}; "
          f"{first['id']} open: frame drawn ({O['ink']} ink px), {O['strip']} strip frames ({first['frames']}), mic {O['mic']}; '{O['line']}'")
    return ok


def api_get(api, st):
    try: return json.load(urllib.request.urlopen(api + 'decisions/' + st))
    except Exception: return {}


def delete_answer(api, st, rid, before):
    prog = ("import json, os, sys; p = sys.argv[1]; k = sys.argv[2]; d = json.load(open(p)); d.pop(k, None)\n"
            "if d: json.dump(d, open(p + '.part', 'w'), indent=1, ensure_ascii=False); os.replace(p + '.part', p)\n"
            "else: os.remove(p)\nprint('left', len(d))")
    rr = subprocess.run(['ssh', '-o', 'BatchMode=yes', VPS, 'python3', '-', f'{STORE}/{st}.json', rid], input=prog, capture_output=True, text=True)
    after = api_get(api, st)
    gone = rid not in after and after == before
    print(f"answer deleted ({rr.stdout.strip() or rr.stderr.strip()}): store as before {gone}")
    return gone


def check_answer2(site, out, base, api, IX, rid):
    st = IX['set']
    before = api_get(api, st)
    if rid in before: print(f'answer: {st}/{rid} already answered (by Bruno): not touched, test skipped'); return True
    sel = f"#t-{rid}"
    steps = [{'width': 360, 'height': 640, 'mobile': True}, {'wait': 2500},
             {'eval': f"(async()=>{{const li=document.querySelector('{sel}'); li.querySelector('.thead').click(); await new Promise(r=>setTimeout(r,800));"
                      f"const p=li.querySelector('.prop').textContent; li.querySelector('.prop button').click(); await new Promise(r=>setTimeout(r,1500));"
                      f"return JSON.stringify({{prop: p, saved: li.querySelector('.saved').textContent}});}})()", 'save': f'{out}/answer_saved.json'},
             {'shot': f'{out}/phone_answer.png'},
             {'eval': f"location.href = location.pathname + '?q={st}&t={rid}'; 1"}, {'wait': 3000},
             {'eval': f"JSON.stringify({{mine: document.querySelector('{sel} .mine').textContent, prop_hidden: document.querySelector('{sel} .prop').hidden, status: document.querySelector('.sub[role=status]').textContent}})", 'save': f'{out}/answer_back.json'}]
    headless(f'{base}/review.html?q={st}', steps, out, 'answer')
    saved = json.loads(json.load(open(f'{out}/answer_saved.json'))); back = json.loads(json.load(open(f'{out}/answer_back.json')))
    stored = api_get(api, st).get(rid, {})
    old = api_get(api, 'throws').get(rid, {})
    dmg = next((int(f[4:]) for f in old.get('flags') or [] if f.startswith('dmg-')), None)
    ok = saved['saved'] == 'Saved' and stored.get('choice') == 0 and f'impact-{dmg}' in (stored.get('flags') or []) and back['prop_hidden'] and back['mine'].startswith('✓')
    print(f"answer: {st}/{rid} '{saved['prop']}' confirmed -> '{saved['saved']}'; store: choice {stored.get('choice')}, flags {stored.get('flags')}, "
          f"label '{stored.get('label')}'; after reload: '{back['mine']}' ({back['status']})")
    json.dump({rid: stored}, open(f'{out}/answer_stored.json', 'w'), indent=1)   # (throw_answers.py apply --dry reads it)
    return ok and delete_answer(api, st, rid, before)


def check_answer(site, out, base, api, IX, rid):
    if SET == 'throws2': return check_answer2(site, out, base, api, IX, rid)
    r = next(x for x in IX['rows'] if x['id'] == rid)
    st = IX['set']
    before = api_get(api, st)
    if rid in before: print(f'answer: {st}/{rid} already answered (by Bruno): not touched, test skipped'); return True
    j = (r['now'].get('impacts') or r['now']['damage'])[0]
    sel = f"#t-{rid}"
    steps = [{'width': 360, 'height': 640, 'mobile': True}, {'wait': 2500},
             {'eval': f"(async()=>{{const li=document.querySelector('{sel}'); li.querySelector('.thead').click(); await new Promise(r=>setTimeout(r,800));"
                      f"li.querySelector('input[type=range]').value='{j + 1}'; li.querySelector('input[type=range]').dispatchEvent(new Event('input'));"
                      f"li.querySelector('.kinds button[data-kind=\"0\"]').click(); await new Promise(r=>setTimeout(r,800));"
                      f"li.querySelector('button[data-set=dmg]').click(); await new Promise(r=>setTimeout(r,1500));"
                      f"return li.querySelector('.saved').textContent;}})()", 'save': f'{out}/answer_saved.json'},
             {'shot': f'{out}/phone_answer.png'},
             {'eval': f"location.href = location.pathname + '?q=throws&t={rid}'; 1"}, {'wait': 3000},
             {'eval': f"JSON.stringify({{pressed: document.querySelector('{sel} .kinds button[data-kind=\"0\"]').getAttribute('aria-pressed'), mine: document.querySelector('{sel} .mine').textContent, status: document.querySelector('.sub[role=status]').textContent}})", 'save': f'{out}/answer_back.json'}]
    headless(f'{base}/review.html?q=throws', steps, out, 'answer')
    saved = json.load(open(f'{out}/answer_saved.json')); back = json.loads(json.load(open(f'{out}/answer_back.json')))
    stored = api_get(api, st).get(rid, {})
    ok = saved == 'Saved' and back['pressed'] == 'true' and stored.get('choice') == 0 and f'dmg-{j + 1}' in (stored.get('flags') or [])
    print(f"answer: {st}/{rid} IMPACT + damage frame {j + 1} -> '{saved}'; store: choice {stored.get('choice')}, flags {stored.get('flags')}, "
          f"label '{stored.get('label')}'; after reload: pressed {back['pressed']}, '{back['mine']}' ({back['status']})")
    json.dump({rid: stored}, open(f'{out}/answer_stored.json', 'w'), indent=1)   # (throw_answers.py apply --dry reads it)
    return ok and delete_answer(api, st, rid, before)


if __name__ == '__main__':
    a = sys.argv[1:]
    site, out = a[0], a[1]; os.makedirs(out, exist_ok=True)
    rid = None
    if '--set' in a:
        i = a.index('--set'); SET = a[i + 1]; del a[i:i + 2]
    if '--answer' in a:
        i = a.index('--answer'); rid = a[i + 1] if len(a) > i + 1 else 'robert-fwd'
    for f in ('review.html', 'review.js', 'micnote.js'): shutil.copy(os.path.join(HERE, 'chainlab', f), os.path.join(site, f))
    IX, a_ok = check_data(site)
    tun, api = None, None
    if rid:
        tun = subprocess.Popen(['ssh', '-o', 'BatchMode=yes', '-N', '-L', f'{PORT}:127.0.0.1:8920', VPS]); time.sleep(3)
        api = f'http://127.0.0.1:{PORT}/api/'
    API_ON = api is not None
    srv, base = serve(site, api)
    try:
        b_ok = check_page(site, out, base, IX)
        c_ok = check_answer(site, out, base, api, IX, rid) if rid else True
    finally:
        srv.shutdown()
        if tun: tun.terminate()
    print('ALL OK' if a_ok and b_ok and c_ok else 'FAILED')
