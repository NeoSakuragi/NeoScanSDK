#!/usr/bin/env python3
"""The select screen's layout between the Brawler Lab and game.json (Bruno 2026-10-07: "a page in the lab where I can
position the characters myself, and you will apply the positioning in the game").

The Lab's Select screen tab (chainlab/selectscreen.js) saves Bruno's layout on the VPS (the feedback service,
tools/feedback/server.py: POST /api/select_layout -> /data/brawler/feedback/select_layout.json, the one before it kept
in select_layout/<time>.json). This tool moves it into game.json's "select_layout" block (build_tables.py
select_layout: per fighter x, y = its feet on the screen, z = its draw order, facing, pose = its select pose [frame,
step], slot = its place in the stick's order), the rest of game.json untouched; then make + publish.

    python3 select_layout.py pull [GAME_JSON]     the saved layout -> game.json select_layout (checked as the build checks it)
    python3 select_layout.py push [GAME_JSON]     game.json's layout (the block, or the first layout without one) -> the
                                                  server, as the saved one (what the Lab's "Load saved" shows)
    python3 select_layout.py show [GAME_JSON]     the saved layout next to game.json's: the fighters that differ"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import build_tables

HOST = 'root@195.201.91.211'
API = 'http://127.0.0.1:8920/api/select_layout'          # the feedback service on the box (localhost: no login)
GAME_JSON = os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')
KEYS = ('x', 'y', 'z', 'facing', 'pose', 'slot')


def ssh(cmd, data=None):
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, cmd], input=data, capture_output=True, text=True)
    if r.returncode: sys.exit(f'ssh: {r.stderr.strip() or r.returncode}')
    return r.stdout


def saved():
    out = ssh(f'curl -s -w "\\n%{{http_code}}" {API}')
    body, code = out.rsplit('\n', 1)
    if code.strip() != '200': sys.exit(f'no layout saved on the server ({code.strip()}: {body.strip()})')
    return json.loads(body)


def block(L):
    """the select_layout block as game.json text: a fighter a line, in the stick's order"""
    rows = [f'  {json.dumps(n)}: {json.dumps({k: L[n][k] for k in KEYS})}' for n in sorted(L, key=lambda n: L[n]['slot'])]
    return '{\n' + ',\n'.join(rows) + '\n }'


def write(path, L):
    """game.json with its select_layout block = L (replaced in place, or added after the "select" block); nothing else changes"""
    text = open(path).read(); g = json.loads(text)
    g2 = dict(g, select_layout=L); build_tables.select_layout(g2)   # the build's own checks, before writing
    dec = json.JSONDecoder()
    if '"select_layout"' in text:
        k = text.index('"select_layout"'); v = text.index(':', k) + 1
        while text[v] in ' \t\n': v += 1
        _, end = dec.raw_decode(text, v)
        text = text[:v] + block(L) + text[end:]
    else:
        k = text.index('\n "select":'); v = text.index(':', k) + 1
        while text[v] in ' \t\n': v += 1
        _, end = dec.raw_decode(text, v)
        text = text[:end] + ',\n "select_layout": ' + block(L) + text[end:]
    assert json.loads(text) == g2
    open(path, 'w').write(text)


def diff(a, b):
    return [n for n in sorted(set(a) | set(b)) if a.get(n) != b.get(n)]


if __name__ == '__main__':
    if len(sys.argv) < 2 or sys.argv[1] not in ('pull', 'push', 'show'): sys.exit(__doc__)
    path = sys.argv[2] if len(sys.argv) > 2 else GAME_JSON
    g = json.load(open(path)); cur = build_tables.select_layout(g)
    if sys.argv[1] == 'pull':
        doc = saved(); L = {n: {k: doc['layout'][n][k] for k in KEYS} for n in doc['layout']}
        ch = diff(cur, L)
        write(path, L)
        print(f'game.json select_layout <- the layout saved {doc["saved"]} by {doc["by"]} (Lab build {doc.get("game_version") or "?"}): '
              f'{len(ch)} fighter(s) changed{": " + ", ".join(ch) if ch else ""}')
    elif sys.argv[1] == 'push':
        v = open(os.path.join(os.path.dirname(os.path.abspath(path)), 'VERSION')).read().strip()
        out = ssh(f"curl -s -X POST -H 'Content-Type: application/json' --data-binary @- {API}",
                  json.dumps({'layout': cur, 'game_version': v}))
        print('server <-', 'game.json select_layout' if 'select_layout' in g else 'the first layout (no block)', out.strip())
    else:
        doc = saved(); L = doc['layout']
        print(f'saved {doc["saved"]} by {doc["by"]}')
        for n in diff(cur, L): print(f'  {n}: game.json {cur.get(n)}  saved {L.get(n)}')
