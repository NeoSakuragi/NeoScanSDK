#!/usr/bin/env python3
"""The chain tool's save path (revamp phase 5, tools/brawler/chainlab/chaintool.js; docs/brawler_data_model.md "The
chain tool"). The Lab's "Save" posts the edited chain to the feedback service's decisions store (POST
feedback-api/decision: set "chain-tool", id = the fighter, choice "save", note = the game.json entry as JSON); this
applies such an entry to examples/brawler/game.json: the fighter's roster keys `archetype`, `finishers` and `chain`
{links, hitstop} replaced by the entry's when its chain changed (the entry has `chain`; else the generator's chain
stays), `retime` by the entry's whole map ({} removes it), only that fighter's roster object rewritten (build_tables.py's layout), the diff printed. Bruno accepts it, I commit it; the build then
plays exactly what the Lab pushed (chain_tool_proof: the rebuilt ROM tree = the pushed bytes).

    python3 tools/brawler/chain_save.py pull [OUT.json]             the store's set from the VPS (default: stdout)
    python3 tools/brawler/chain_save.py apply GAME.json SET.json FIGHTER [--dry]
    python3 tools/brawler/chain_save.py entry GAME.json ENTRY.json FIGHTER [--dry]   a downloaded entry (the Lab's "Download")"""
import difflib, json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_tables as BT

HOST = 'root@195.201.91.211'
STORE = '/data/brawler/feedback/decisions/chain-tool.json'
KEYS = ('archetype', 'finishers', 'chain', 'retime')        # the roster keys an entry owns


def entry_of(saved, fighter):
    """a decisions-store set -> the fighter's entry (its note, JSON)"""
    a = saved.get(fighter)
    assert a, f'no saved chain for {fighter} in the set (saved: {", ".join(sorted(saved)) or "none"})'
    e = a['note'] if isinstance(a['note'], dict) else json.loads(a['note'])
    return e.get('entry', e)


def apply(game_path, entry, fighter, dry=False):
    text = open(game_path).read()
    g = json.loads(text)
    r = next((x for x in g['roster'] if x['name'] == fighter), None)
    assert r, f'{fighter}: not in the roster'
    bad = set(entry) - set(KEYS)
    assert not bad, f'entry keys {sorted(bad)}: only {KEYS}'
    for k in ('archetype', 'finishers', 'chain'):               # the chain changed: all three come with it
        if 'chain' in entry and k in entry: r[k] = entry[k]
    if 'retime' in entry:                                     # the fighter's whole retime map ({} = none)
        if entry['retime']: r['retime'] = entry['retime']
        else: r.pop('retime', None)
    BT.chain_cfg(g, r)                                        # the build's own checks of the keys
    # only the fighter's roster object is rewritten (build_tables' layout at its depth): the rest of the file stays
    # byte for byte (game.json is partly hand laid out; other jobs edit it too)
    at = text.index(f'"name": "{fighter}"')
    a = text.rindex('\n  {', 0, at) + 3; b = text.index('\n  }', at) + 4
    out = text[:a] + BT.fmt(r, 2) + text[b:]
    assert json.loads(out) == g, 'the patched file does not read back as the edited game'
    diff = ''.join(difflib.unified_diff(text.splitlines(True), out.splitlines(True), game_path, game_path + ' (chain tool)'))
    if not dry: open(game_path, 'w').write(out)
    return diff


if __name__ == '__main__':
    a = sys.argv[1:]
    dry = '--dry' in a; a = [x for x in a if x != '--dry']
    if a[0] == 'pull':
        s = subprocess.run(['ssh', HOST, f'cat {STORE}'], capture_output=True, text=True, check=True).stdout
        if len(a) > 1: open(a[1], 'w').write(s)
        else: print(s)
    elif a[0] in ('apply', 'entry'):
        game, src, fighter = a[1], a[2], a[3]
        d = json.load(open(src))
        e = entry_of(d, fighter) if a[0] == 'apply' else d.get('entry', d)
        print(apply(game, e, fighter, dry) or '(no change)')
    else: sys.exit(__doc__)
