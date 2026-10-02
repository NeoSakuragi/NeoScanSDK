#!/usr/bin/env python3
"""Delete every track and via of the given nets so route_one_net.py can redo them. Usage: AppRun python3.11 rip_net.py board NET [NET...]"""
import sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1]); nets = set(sys.argv[2:]); n = 0
for t in list(b.GetTracks()):
    if t.GetNetname() in nets: b.Remove(t); n += 1
b.Save(sys.argv[1]); print('ripped', n, 'items of', sorted(nets))
