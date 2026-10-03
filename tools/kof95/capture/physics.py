"""Movement constants from a capture: walk speeds, jump launch speed, gravity, jump horizontal speeds.
python3 capture/physics.py capture/kyo_move.txt [player]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import Counter
import analyze as A
def measure(path, player=1):
    rows = A.load(path, player); w = [r[3] for r in rows]
    X = [A.x_of(v) for v in w]; Y = [A.y_of(v) for v in w]; S = [A.state_of(v) for v in w]
    def mode_dx(state):
        d = [X[k + 1] - X[k] for k in range(len(w) - 1) if S[k] == state and S[k + 1] == state]
        return Counter(round(v, 6) for v in d).most_common(1)[0][0] if d else None
    out = {'walk_fwd': mode_dx(1), 'walk_back': mode_dx(2)}
    i4 = next(k for k, s in enumerate(S) if s == 4)                     # first frame of a neutral jump's rising phase
    dy = [Y[k + 1] - Y[k] for k in range(i4 - 1, i4 + 60)]
    out['jump_vy0'] = round(max(dy), 6)
    out['gravity'] = Counter(round(dy[k + 1] - dy[k], 6) for k in range(len(dy) - 1) if dy[k] > 0 and dy[k + 1] != 0).most_common(1)[0][0]
    air = [k for k in range(i4, len(S)) if Y[k] > 0]; out['air_frames'] = next(k for k in range(i4, len(S)) if Y[k] <= 0 and k > i4) - i4 + 1
    out['apex'] = round(max(Y), 3)
    out['jump_fwd_dx'] = mode_dx(8); out['jump_back_dx'] = mode_dx(12)
    return out
if __name__ == '__main__':
    print(measure(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1))
