#!/usr/bin/env python3
"""Backfill each note's lifecycle from the repo (docs/feedback.md "Lifecycle"): its TODO item(s) (examples/brawler/TODO.md
items that quote the note's id, or "TODO #N" in its status history), the commits on the brawler branch that name the
item (git log --grep "#N"), the fix commit (the item's last commit before the release that shipped the note) and the
release (the "Brawler <version>:" commit that bumped examples/brawler/VERSION). Posted as timeline events through the
tracker's API (idempotent: an event is keyed by its kind and ref, so a rerun changes nothing).

    backfill_history.py [--dry] [--only ID,...]"""
import argparse, datetime, json, os, re, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import fb

TODO = os.path.join(REPO, 'examples', 'brawler', 'TODO.md')


def utc(iso):
    return datetime.datetime.fromisoformat(iso).astimezone(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def items():
    """TODO item number -> its text (the line and its continuation lines)"""
    out, cur = {}, None
    for line in open(TODO):
        m = re.match(r'^- \[[ x]\] (\d+)\.', line)
        if m: cur = int(m.group(1)); out[cur] = line
        elif cur is not None and line.startswith('  '): out[cur] += line
        else: cur = None
    return out


def items_of(fid, row, todo):
    """the items that quote the note: its full id, or its time with its install tag in the same item"""
    date, hms, tag = fid.split('-')[:3]
    found = {n for n, t in todo.items() if fid in t or (re.search(r'\b' + hms + r'\b', t) and tag in t and date in t)}
    for h in row.get('history', []):
        found |= {int(n) for n in re.findall(r'TODO #(\d+)', h.get('note') or '')}
    if row.get('todo'): found |= {int(n) for n in row['todo'].split(',')}
    return sorted(found)


def commits():
    r = subprocess.run(['git', '-C', REPO, 'log', 'brawler', '--format=%H\t%cI\t%an\t%s'], capture_output=True, text=True, check=True)
    return [dict(zip(('sha', 'at', 'by', 'subject'), l.split('\t', 3))) for l in r.stdout.splitlines()][::-1]   # oldest first


def code_commit(sha):
    files = subprocess.run(['git', '-C', REPO, 'show', '--format=', '--name-only', sha], capture_output=True, text=True).stdout.split()
    return any(not f.endswith('.md') for f in files)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--dry', action='store_true'); ap.add_argument('--only', default='')
    a = ap.parse_args()
    todo, log = items(), commits()
    rows = fb.api('list')['rows']
    for row in rows:
        fid = row['id']
        if a.only and fid not in a.only.split(','): continue
        hist = fb.api('item/' + fid)['history']; row['history'] = hist
        its = items_of(fid, row, todo)
        rel = row.get('release') or ''
        relc = next((c for c in log if re.match(r'^Brawler %s[: ]' % re.escape(rel), c['subject'])), None) if rel else None
        ev = []
        if its: ev.append({'kind': 'triaged', 'at': row['created'], 'ref': 'todo', 'text': 'TODO #' + ', #'.join(map(str, its)) + ' (from TODO.md)',
                           'todo': ','.join(map(str, its))})
        mine = [c for c in log if any(re.search(r'#%d\b' % n, c['subject']) for n in its)]
        if relc: mine = [c for c in mine if c['at'] <= relc['at']]
        for c in mine:
            ev.append({'kind': 'commit', 'at': utc(c['at']), 'ref': c['sha'][:10], 'text': f"commit {c['sha'][:10]}: {c['subject'][:200]}"})
        code = [c for c in mine if code_commit(c['sha'])]          # a commit that only edits notes (*.md) fixes nothing
        fix = code[-1] if code else relc
        if fix and row['status'] in ('shipped', 'verified', 'reopened', 'fixed'):
            ev.append({'kind': 'fixed', 'at': utc(fix['at']), 'ref': 'fix', 'fix_commit': fix['sha'][:10],
                       'text': f"fixed in commit {fix['sha'][:10]} on brawler" + ('' if fix is relc else f" (TODO item commit)")})
        if relc:
            ev.append({'kind': 'released', 'at': utc(relc['at']), 'ref': 'release ' + rel,
                       'text': f"in build {rel} (commit {relc['sha'][:10]}: {relc['subject'][:160]})"})
        print(fid, row['status'], rel or '-', 'TODO', its or '-', f'{len(mine)} commits', 'fix', fix['sha'][:10] if fix else '-')
        if a.dry: continue
        for e in ev: fb.api('event', dict(e, id=fid, by='backfill_history.py'))


if __name__ == '__main__':
    main()
