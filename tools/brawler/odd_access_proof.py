#!/usr/bin/env python3
"""The former release gate (2026-10-16: zero odd-address word / long accesses over power-on + 3 attract loops + a
short campaign, both BIOS). It never won a bonus game, so 0.10.153's reset at the won posts bonus (the referee's
rf_draw: a word read at an odd address) went through it. Now hw_strict_proof.py: the static lint, then the WHOLE game
(every stage, the bonus games won, the referee and his D quirk, the ending) on both BIOS with the address-error,
exception, watchdog, reset and stack checks. This name runs it (same options, same ALL OK / FAIL)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
args = [a for a in sys.argv[1:]]
if '--stage' in args:                                    # (the short campaign's option: the whole game now)
    i = args.index('--stage'); del args[i:i + 2]
os.execv(sys.executable, [sys.executable, os.path.join(HERE, 'hw_strict_proof.py')] + args)
