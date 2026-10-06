#!/usr/bin/env python3
"""The feedback tracker from the desktop (docs/feedback.md): every call goes to the service's API on the VPS
(tools/feedback/server.py, 127.0.0.1:8920 over ssh = authenticated by the ssh key); never a direct DB edit.

    fb.py list [--status new|read|in_progress|shipped|wont_do|duplicate|verified|reopened] [--category gameplay] [--cost]
    fb.py show <id>
    fb.py status <id> read|in_progress|wont_do|verified|reopened [--note "..."]
    fb.py status <id> shipped --release 0.0.71 [--note "..."]
    fb.py status <id> duplicate --of <other id>
    (verified / reopened are normally set by the player himself: thumbs up / down in his list, Player 0.0.17)
    fb.py set <id> [--category sound|graphics|gameplay|integration|scripting|other] [--fighters geese,terry] [--notes "..."]"""
import argparse, json, shlex, subprocess, sys

HOST = 'root@195.201.91.211'
BASE = 'http://127.0.0.1:8920/api/'


def api(path, body=None):
    cmd = f'curl -s -S --max-time 30 {shlex.quote(BASE + path)}'
    if body is not None: cmd += " -X POST -H 'Content-Type: application/json' --data-binary @-"
    r = subprocess.run(['ssh', '-o', 'BatchMode=yes', HOST, cmd], input=json.dumps(body) if body is not None else None,
                       capture_output=True, text=True)
    if r.returncode: raise RuntimeError('ssh/curl: ' + r.stderr.strip())
    out = json.loads(r.stdout)
    if 'error' in out: raise RuntimeError(out['error'])
    return out


def thread(replies, indent='  '):
    """the player's replies to a note (Player 0.0.17), oldest first: one line each"""
    KIND = {'up': 'THUMBS UP (verified fixed)', 'down': 'THUMBS DOWN (still broken)', 'voice': 'voice', 'text': 'text'}
    out = []
    for x in replies or []:
        st = f" [{x['status_from']} -> {x['status_to']}]" if x.get('status_to') else ''
        au = f" (audio {x['audio_path']})" if x.get('audio_path') else ''
        out.append(f"{indent}{x['at'][:16].replace('T', ' ')}  {x.get('user') or '-'}  {KIND.get(x['kind'], x['kind'])}{st}{au}" +
                   (f": \"{x['text']}\"" if x.get('text') else ''))
    return out


def money(v): return f'${v:.4f}' if v is not None else '-'


def line(r, cost=False):
    text = (r['final_text'] or r['raw_transcript'] or '').replace('\n', ' ')
    rel = f" {r['release']}" if r['status'] == 'shipped' else f" of {r['duplicate_of']}" if r['status'] == 'duplicate' else ''
    n = len(r.get('replies') or [])
    tags = ' '.join(x for x in (r['category'], r['fighters']) if x)
    return f"{r['id']}  {r['created'][:16]}  {r.get('user') or '-'}  player {r['apk_version']}  game v{r['game_version']}  {r['status']}{rel}" + \
           (f"  [{tags}]" if tags else '') + (f"  {money(r.get('cost_usd'))}" + (' (est.)' if 'duration' in (r.get('cost_source') or '') else '') if cost else '') + \
           f"  \"{text[:80]}\"" + (f"  ({n} repl{'y' if n == 1 else 'ies'})" if n else '')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list'); p.add_argument('--status'); p.add_argument('--category'); p.add_argument('--cost', action='store_true')
    p = sub.add_parser('show'); p.add_argument('id')
    p = sub.add_parser('status'); p.add_argument('id'); p.add_argument('status')
    p.add_argument('--release', default=None); p.add_argument('--note', default=''); p.add_argument('--of', default='')
    p = sub.add_parser('set'); p.add_argument('id'); p.add_argument('--category'); p.add_argument('--fighters'); p.add_argument('--notes')
    a = ap.parse_args()
    try:
        if a.cmd == 'list':
            q = '&'.join(f'{k}={v}' for k, v in (('status', a.status), ('category', a.category)) if v)
            res = api('list' + ('?' + q if q else '')); rows = res['rows']
            for r in rows: print(line(r, a.cost))
            if not rows: print('(none)')
            if a.cost:
                c = res['cost']; P = c['prices']
                print(f"total: {money(c['usd'])} for {c['transcriptions']} transcriptions ({c['audio_seconds']} s of audio; "
                      f"{money(c['usd_in_notes'])} in sent notes, the rest cancelled); prices {P['source']} checked {P['checked']}")
        elif a.cmd == 'show':
            it = api('item/' + a.id); r = it['row']
            print(line(r))
            for k in ('raw_transcript', 'final_text', 'notes', 'rom_sha', 'audio_path', 'bundle_path'): print(f'  {k}: {r[k]}')
            print(f"  from: {r.get('user') or '-'}, install {r.get('install_id') or '-'}, {r.get('device') or '-'} (Android {r.get('android') or '-'}), "
                  f"IP {r.get('ip') or '-'}, UA {r.get('user_agent') or '-'}")
            for t in it['transcriptions']:
                print(f"  cost {money(t['cost_usd'])} ({t['cost_source']}, prices {t['prices_checked']}): {t['model']}, {t['audio_seconds']} s audio, "
                      f"tokens in text {t['input_text_tokens']} audio {t['input_audio_tokens']} out {t['output_tokens']}; "
                      f"from {t.get('user') or '-'}, install {t.get('install_id') or '-'}, IP {t.get('ip') or '-'}, UA {t.get('user_agent') or '-'}")
            for h in it['history']: print(f"  {h['at']}  {h['from_status'] or '-'} -> {h['to_status']}  by {h['by']}  {h['note']}")
            if it.get('replies'):
                print('  thread:'); print('\n'.join(thread(it['replies'], '    ')))
        elif a.cmd == 'status':
            body = {'id': a.id, 'status': a.status, 'note': a.note, 'by': 'fb.py'}
            if a.release is not None: body['release'] = a.release
            if a.of: body['duplicate_of'] = a.of
            print(line(api('status', body)['row']))
        elif a.cmd == 'set':
            body = {'id': a.id, 'by': 'fb.py'}
            for k in ('category', 'fighters', 'notes'):
                if getattr(a, k) is not None: body[k] = getattr(a, k)
            print(line(api('set', body)['row']))
    except RuntimeError as e:
        sys.exit('fb.py: ' + str(e))


if __name__ == '__main__':
    main()
