#!/usr/bin/env python3
"""Every move a player started in a recorded play session (docs/feedback.md "Session recording"), on the desktop from a
built tree: the replay and its measurements are analysis/analyze.py's (the same code the VPS replay worker runs from a
build's analysis pack, analysis/worker.py); this builds the pack from GAME_DIR on the fly and prints the move table.

    python3 tools/brawler/session_moves.py SESSION_DIR ROM.neo GAME_DIR [--bios DIR] [--out events.json]

SESSION_DIR = the storage layout (/mnt/storagebox/brawler-sessions/<id>: meta.json, <seq>.nsin, <seq>.sha256,
<seq>.state.gz for keyframes). ROM.neo = the session's build (meta rom_sha256). GAME_DIR = examples/brawler of THAT
build, built (a git worktree at its VERSION commit, `make`). --bios: the directory holding the Player's neogeo.zip (the
Lab's site copy; default /data/tmp/chainlab/site). --out: analyze.py's full result (events, screens, segments, summary).

Events per player fighter (0 = P1, 1 = P2): special (role, spec_ix -> the input in the fighter's pool, sthr), throw,
grab, death; + continue / gameover / coin / bonus_end; an event in a bonus game is flagged bonus."""
import argparse, json, os, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'analysis'))
import analyze, pack


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('session'); ap.add_argument('rom'); ap.add_argument('game')
    ap.add_argument('--bios', default='/data/tmp/chainlab/site'); ap.add_argument('--out')
    a = ap.parse_args()
    res = analyze.analyze(a.session, pack.make(a.game, rom=a.rom), a.rom, a.bios)
    if a.out: json.dump(res, open(a.out, 'w'), indent=1)
    print(json.dumps({k: v for k, v in res.items() if k not in ('events', 'screens', 'segments')}))
    for (p, ch, ev, kind, inp, bn), n in sorted(Counter((e['p'], e['char'], e['ev'], e['kind'], e.get('input', ''), e['bonus'])
                                                     for e in res['events'] if 'char' in e).items()):
        print(f'P{p + 1} {ch:10s} {ev:8s} {kind:30s} {inp:14s} {"bonus " if bn else ""}{n}')


if __name__ == '__main__':
    main()
