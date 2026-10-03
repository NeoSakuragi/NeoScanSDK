"""Build record.lua SEQ/SEQ2 strings from absolute-frame events: python3 timeline.py 'p1|p2 frame len inputs; ...' total
Prints two lines: SEQ and SEQ2 (unset frames = '-')."""
import sys
def seqs(spec, total):
    lanes = {'p1': ['-'] * total, 'p2': ['-'] * total}
    for ev in filter(None, (e.strip() for e in spec.split(';'))):
        who, start, n, inp = ev.split()
        for f in range(int(start), min(total, int(start) + int(n))): lanes[who][f] = inp
    out = []
    for who in ('p1', 'p2'):
        runs, l = [], lanes[who]
        for x in l:
            if runs and runs[-1][1] == x: runs[-1][0] += 1
            else: runs.append([1, x])
        out.append(','.join(f'{n}:{x}' for n, x in runs))
    return out
if __name__ == '__main__':
    for s in seqs(sys.argv[1], int(sys.argv[2])): print(s)
