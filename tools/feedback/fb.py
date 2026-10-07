#!/usr/bin/env python3
"""The feedback tracker from the desktop (docs/feedback.md): every call goes to the service's API on the VPS
(tools/feedback/server.py, 127.0.0.1:8920 over ssh = authenticated by the ssh key); never a direct DB edit.

    fb.py list [--status new|read|in_progress|shipped|wont_do|duplicate|verified|reopened] [--category gameplay] [--cost]
    fb.py show <id>
    fb.py status <id> read|in_progress|wont_do|verified|reopened [--note "..."] [--commit SHA]
    fb.py status <id> fixed --commit SHA [--note "..."]     (on the brawler branch, not yet in a published build)
    fb.py status <id> shipped --release 0.0.71 [--note "..."]
    fb.py status <id> duplicate --of <other id>
    (verified / reopened are normally set by the player himself: thumbs up / down in his list, Player 0.0.17)
    fb.py set <id> [--category sound|graphics|gameplay|integration|scripting|other] [--fighters geese,terry] [--notes "..."]
    fb.py set <id> --title "Krauser: Kaiser Wave impact drawn at floor level"   (the note's one-line headline, <= 70)
    fb.py set <id> --todo 166                                (its TODO item(s): 163,173)
    fb.py set <id> --fix "..." --rca "..."                   the fix and its root cause, one or two plain sentences each
                                                             (the player's card and the Lab show them under [FIX 0.0.x])
    fb.py timeline <id>                                      the note's whole life (found, triaged, in progress, fixed,
                                                             shipped, test states, test attempts, verified / reopened, replies)
Decisions (Player 0.0.24, docs/feedback.md "Decisions"): a visual choice put to Bruno, answered in the player / the Lab.
    fb.py review add --title "HUD font" --question "Which font should the HUD and system text use?" --kind before_after \
        --image "BEFORE: 0.0.88, system font=/path/before.png" --image "AFTER: Kizuna's font=/path/after.png" \
        --option "Kizuna's font (gradient + shadow), as shown=EFFECT" --option "The old font=EFFECT" [--todo 182] [--note ID] [--for bruno]
        Rules (the server refuses otherwise): ONE question ending in "?"; each image labelled with what it is; 2 to 5
        buttons LABEL=EFFECT, the label = the exact outcome in game terms (never Keep / Change / Yes / No / Ship it alone),
        the effect = one line saying what changes in the game if he picks it; a "Needs work: ..." button requires his note.
        --kind before_after | pick | single: the card's layout only. --for: the Oros account it is put to (default bruno).
    fb.py review list [--status open|answered]      fb.py review show <id>      fb.py review delete <id>
    fb.py review answer <id> --answer "LABEL" --by bruno --source artifact|chat [--text "..."]   an answer he gave elsewhere
Lifecycle: new -> read -> in_progress -> fixed (commit) -> shipped (release) -> tested on the player (👍 verified / 👎
reopened); wont_do and duplicate close a note. Every step is a timestamped event with who (docs/feedback.md "Lifecycle").
"""
import argparse, base64, json, os, re, shlex, subprocess, sys

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


def timeline(events, indent='  '):
    """the note's life, oldest first: one line per event"""
    return [f"{indent}{e['at'][:16].replace('T', ' ')}  {e['kind']:<11} {e.get('by') or '-':<14} {e['text']}" for e in events or []]


def review_line(v):
    a = f"  -> {v['answer']}" if v.get('answer') else ''
    return f"#{v['id']}  {v['created'][:16]}  {v['kind']}  for {v.get('audience') or 'everyone'}  {v['status'].upper()}{a}  \"{v['title']}\"" + \
           (f"  TODO #{v['todo']}" if v.get('todo') else '')


def review_cmd(a):
    if a.rcmd == 'add':
        imgs = []
        for spec in a.image:
            lab, _, path = spec.rpartition('=')
            if not lab or not os.path.isfile(path): sys.exit(f'fb.py: --image "LABEL=path": {spec!r}')
            base = re.sub(r'[^a-z0-9_-]+', '_', lab.lower()).strip('_')[:50] or 'image'
            name, k = base, 2
            while any(i['name'].rsplit('.', 1)[0] == name for i in imgs): name = f'{base}_{k}'; k += 1
            ext = os.path.splitext(path)[1].lower().lstrip('.') or 'png'
            imgs.append({'label': lab, 'name': f'{name}.{ext}', 'b64': base64.b64encode(open(path, 'rb').read()).decode()})
        opts = []
        for spec in a.option:
            lab, sep, eff = spec.partition('=')
            if not sep: sys.exit(f'fb.py: --option "LABEL=EFFECT" (what changes in the game if he picks it): {spec!r}')
            opts.append({'label': lab.strip(), 'effect': eff.strip()})
        body = {'title': a.title, 'question': a.question, 'kind': a.kind, 'images': imgs, 'options': opts, 'todo': a.todo or '',
                'notes': ','.join(a.note or []), 'audience': a.for_, 'by': 'fb.py'}
        v = api('review', body)['review']; print(review_line(v))
    elif a.rcmd == 'list':
        vs = api('reviews' + (f'?status={a.status}' if a.status else ''))['reviews']
        for v in vs: print(review_line(v))
        if not vs: print('(none)')
    elif a.rcmd == 'show':
        v = api(f'review/{a.id}')['review']
        print(review_line(v)); print(f"  question: {v['question']}")
        for o in v['options']: print(f"  button: {o['label']}  ->  {o['effect']}")
        for i in v['images']: print(f"  image: {i['label']}  ({i['file']})")
        if v.get('notes') or v.get('todo'): print(f"  linked: TODO #{v.get('todo') or '-'}, notes {v.get('notes') or '-'}")
        if v['status'] == 'answered':
            print(f"  ANSWER: {v['answer']}  by {v['answered_by']} from the {v['answer_source']} at {v['answered_at']}")
            if v.get('answer_text'): print(f"  note: {v['answer_text']}")
            if v.get('answer_raw') and v['answer_raw'] != v.get('answer_text'): print(f"  transcript: {v['answer_raw']}")
            if v.get('answer_audio'): print(f"  voice: DATA/reviews/{v['id']}/{v['answer_audio']}")
            if v.get('answer_origin') and v['answer_origin'] != '{}': print(f"  origin: {v['answer_origin']}")
        print('  history:')
        for h in v['history']: print(f"    {h['at'][:16].replace('T', ' ')}  {h['kind']:<9} {h['by'] or '-':<14} {h['text']}" + (f" (voice {h['audio']})" if h.get('audio') else ''))
    elif a.rcmd == 'answer':
        v = api('review_answer', {'id': int(a.id), 'answer': a.answer, 'text': a.text or '', 'source': a.source, 'by': a.by})['review']
        print(review_line(v))
    elif a.rcmd == 'delete':
        print('deleted #%s' % api('review_delete', {'id': int(a.id), 'by': 'fb.py'})['deleted'])


def money(v): return f'${v:.4f}' if v is not None else '-'


def line(r, cost=False):
    text = r.get('title') or (r['final_text'] or r['raw_transcript'] or '').replace('\n', ' ')
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
    p.add_argument('--commit', default='')
    p = sub.add_parser('set'); p.add_argument('id'); p.add_argument('--category'); p.add_argument('--fighters'); p.add_argument('--notes'); p.add_argument('--title'); p.add_argument('--todo')
    p.add_argument('--fix'); p.add_argument('--rca')
    p = sub.add_parser('timeline'); p.add_argument('id')
    p = sub.add_parser('review'); rs = p.add_subparsers(dest='rcmd', required=True)
    q = rs.add_parser('add'); q.add_argument('--title', required=True); q.add_argument('--question', required=True)
    q.add_argument('--kind', required=True, choices=('before_after', 'pick', 'single'))
    q.add_argument('--image', action='append', required=True, help='"LABEL=path" (repeat; in display order)')
    q.add_argument('--option', action='append', default=[], help='"LABEL=EFFECT" (repeat, 2 to 5)')
    q.add_argument('--todo'); q.add_argument('--note', action='append', help='a linked feedback note id (repeat)')
    q.add_argument('--for', dest='for_', default='bruno', help='the Oros account it is put to ("" = every account)')
    q = rs.add_parser('list'); q.add_argument('--status', choices=('open', 'answered'))
    q = rs.add_parser('show'); q.add_argument('id')
    q = rs.add_parser('delete'); q.add_argument('id')
    q = rs.add_parser('answer'); q.add_argument('id'); q.add_argument('--answer', required=True); q.add_argument('--by', required=True)
    q.add_argument('--source', required=True, choices=('artifact', 'chat', 'lab')); q.add_argument('--text')
    a = ap.parse_args()
    try:
        if a.cmd == 'review': return review_cmd(a)
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
            for k in ('title', 'raw_transcript', 'final_text', 'notes', 'rom_sha', 'audio_path', 'bundle_path'): print(f'  {k}: {r[k]}')
            print(f"  from: {r.get('user') or '-'}, install {r.get('install_id') or '-'}, {r.get('device') or '-'} (Android {r.get('android') or '-'}), "
                  f"IP {r.get('ip') or '-'}, UA {r.get('user_agent') or '-'}")
            for t in it['transcriptions']:
                print(f"  cost {money(t['cost_usd'])} ({t['cost_source']}, prices {t['prices_checked']}): {t['model']}, {t['audio_seconds']} s audio, "
                      f"tokens in text {t['input_text_tokens']} audio {t['input_audio_tokens']} out {t['output_tokens']}; "
                      f"from {t.get('user') or '-'}, install {t.get('install_id') or '-'}, IP {t.get('ip') or '-'}, UA {t.get('user_agent') or '-'}")
            for h in it['history']: print(f"  {h['at']}  {h['from_status'] or '-'} -> {h['to_status']}  by {h['by']}  {h['note']}")
            if r.get('fix'): print(f"  fix: {r['fix']}")
            if r.get('rca'): print(f"  root cause: {r['rca']}")
            if r.get('todo') or r.get('fix_commit'): print(f"  TODO #{r.get('todo') or '-'}, fix commit {r.get('fix_commit') or '-'}")
            if it.get('scenario'):
                sc = it['scenario']; print(f"  test: {sc['title']}\n    do: {sc['do']}\n    expect: {sc['expect']}")
                print('    states: ' + (', '.join(b[:12] + b[64:] for b in it.get('scenario_builds', [])) or 'none yet'))
            if it.get('replies'):
                print('  thread:'); print('\n'.join(thread(it['replies'], '    ')))
            print('  timeline:'); print('\n'.join(timeline(it.get('timeline'), '    ')))
        elif a.cmd == 'timeline':
            print('\n'.join(timeline(api('item/' + a.id).get('timeline'), '')))
        elif a.cmd == 'status':
            body = {'id': a.id, 'status': a.status, 'note': a.note, 'by': 'fb.py'}
            if a.release is not None: body['release'] = a.release
            if a.of: body['duplicate_of'] = a.of
            if a.commit: body['commit'] = a.commit
            print(line(api('status', body)['row']))
        elif a.cmd == 'set':
            body = {'id': a.id, 'by': 'fb.py'}
            for k in ('category', 'fighters', 'notes', 'title', 'todo', 'fix', 'rca'):
                if getattr(a, k) is not None: body[k] = getattr(a, k)
            print(line(api('set', body)['row']))
    except RuntimeError as e:
        sys.exit('fb.py: ' + str(e))


if __name__ == '__main__':
    main()
