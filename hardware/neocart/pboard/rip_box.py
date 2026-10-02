#!/usr/bin/env python3
"""Delete the tracks of one net lying entirely inside a box. Usage: AppRun python3.11 rip_box.py board NET x0,y0,x1,y1"""
import pcbnew, sys
b=pcbnew.LoadBoard(sys.argv[1]); net=sys.argv[2]; x0,y0,x1,y1=map(float,sys.argv[3].split(',')); n=0
for t in list(b.GetTracks()):
    if t.GetNetname()!=net: continue
    pts=[t.GetStart(),t.GetEnd()]
    if all(x0<=q.x/1e6<=x1 and y0<=q.y/1e6<=y1 for q in pts): b.Remove(t); n+=1
b.Save(sys.argv[1]); print('removed',n,net,'items inside',(x0,y0,x1,y1))
