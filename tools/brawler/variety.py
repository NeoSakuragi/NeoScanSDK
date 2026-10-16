#!/usr/bin/env python3
"""The enemies' move variety and difficulty per wave (Bruno 2026-10-16, after Wael's 0.10.150 run: "the enemies are too
boring - give them a WIDE RANGE OF MOVES"; "more difficulty but fewer of them"), measured in our emulator (harness.py,
never MAME): a scripted Terry bot (Wael's moves: A chains, Crack Shoot uu+A, Burn Knuckle f+C, Rising Tackle C against
an attack, walk-in grabs) fights each wave of a stage from its start (the lab's stage request: P1 alone, the enemies'
own AI, rank_start), his life refilled every frame so every wave runs to its end.

    python3 variety.py [--game DIR] [--stage 0] [--waves 0,1,2,3,4] [--runs 3] [--json OUT]
    python3 variety.py --compare BEFORE.json AFTER.json      the two as a markdown table

Per wave: the enemies spawned, every move each enemy STARTED by type (a state entered: a normal from neutral (stand /
crouch / dash attack), its specials by role (projectile / anti-air / rush / other, build_tables.ai_roles), grabs and
throws, jumps / jump attacks / back-hops, runs, guards), the distinct types, the damage dealt to P1 and the frames to
clear (every enemy beaten; capped at --cap). --game: a copy of examples/brawler with its build/ (another build's
offsets: the before ROM)."""
import argparse, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import harness as H, scenario as SC, build_tables as BT

ABLE = ('IDLE', 'WALK', 'RUN')
ROLE_NAMES = ['proj', 'aa', 'rush']


def roles_of(game):
    """fighter name -> {slot index: role name} (build_tables.ai_roles on that build's export)"""
    g = json.load(open(os.path.join(game, 'game.json')))
    lab = json.load(open(os.path.join(game, 'build', 'chainlab.json')))
    out = {}
    for name, row in BT.ai_roles(g, lab):
        out[name] = {s: ROLE_NAMES[k] for k, s in enumerate(row) if s != 0xFF}
    return out


class Bot:
    """Terry as Wael played him (/data/tmp/wael_moves/report.md: Crack Shoot 17, Rising Tackle 11, Burn Knuckle 10 in a
    stage 1 run, chains and walk-in grabs between)"""
    def __init__(self, seed):
        self.r = random.Random(seed); self.jumps = 0; self.cd = 0; self.plan = []; self.follow = 0; self.t = 0

    def keys(self, b):
        self.t += 1
        if self.cd: self.cd -= 1
        if self.plan: return self.plan.pop(0)
        st = b.states[b.fget(0, 'state')]
        mx, mz, face = b.fget(0, 'x'), b.fget(0, 'z'), b.fget(0, 'facing')
        if st == 'GRAB':                                       # the hold: knees, then a throw
            return ('a' if self.t % 12 == 0 else '') + ('R' if face > 0 else 'L') * (b.fget(0, 'grab_hits') >= 2)
        if st == 'ATTACK':                                     # the chain: tap A on
            return 'a' if self.follow and self.t % 6 == 0 and self.r.random() < 0.8 else ''
        if st not in ABLE: return ''
        best = None
        for i in range(2, 8):
            s = b.states[b.fget(i, 'state')]
            if s in ('OFF', 'DEAD', 'DOWN', 'KNOCKDOWN', 'GETUP', 'THROWN', 'GRABBED'): continue
            dx, dz = b.fget(i, 'x') - mx, b.fget(i, 'z') - mz
            d = abs(dx) + abs(dz)
            if s in ('ATTACK', 'SPECIAL') and abs(dx) < 60 and abs(dz) < 10 and not self.cd and self.r.random() < 0.35:
                self.cd = 50; return 'c'                       # threatened: Rising Tackle (neutral C)
            if best is None or d < best[0]: best = (d, dx, dz)
        if best is None: return 'R' if self.t % 4 else ''
        _, dx, dz = best
        fwd = 'R' if dx > 0 else 'L'
        k = ''
        if abs(dz) > 3: k += 'D' if dz > 0 else 'U'
        if (fwd == 'R') != (face > 0): return fwd + k          # turn to it
        if abs(dz) <= 6 and 60 <= abs(dx) <= 130 and not self.cd and self.r.random() < 0.06:
            self.cd = 70
            if self.r.random() < 0.5: self.plan = ['', 'U', '', 'Ua']; return 'U'   # Crack Shoot: up, up + A (uu Blitz)
            self.plan = [fwd + 'c']; return fwd                 # Burn Knuckle: forward + C
        if abs(dz) <= 6 and 70 <= abs(dx) <= 110 and not self.cd and self.r.random() < 0.02:
            self.cd = 60; self.jumps += 1
            self.plan = [fwd + 'b'] * 9 + [fwd] * 14 + [fwd + 'a']; return fwd + 'b'   # a jump-in, A coming down
        if abs(dx) > 44: return fwd + k
        if abs(dx) < 16: return ('L' if fwd == 'R' else 'R') + k
        if abs(dz) <= 5 and not self.cd:
            if self.r.random() < 0.08: return fwd + k          # walk in: the grab
            self.follow = 3; self.cd = 20; return 'a'
        return k


def kind_of(b, i, s, prev, ba, roles, chname, a0):
    """the move enemy i started entering state s (None: not a move)"""
    if s == 'ATTACK' and prev not in ('ATTACK',):
        nm = ba[b.fget(i, 'anim')] if b.fget(i, 'anim') < len(ba) else '?'
        if prev == 'RUN': return 'dash_attack'
        return 'crouch_attack' if 'crouch' in nm else 'normal'
    if s == 'SPECIAL':
        sid = b.fget(i, 'spec_id')
        if sid >= 6: return {6: 'fury', 7: 'fury', 8: 'form', 9: 'air_special', 10: 'down_attack', 11: 'throw_special', 12: 'blitz'}.get(sid, 'special_%d' % sid)
        return 'special_' + roles.get(chname, {}).get(sid, 'other')
    if s == 'GRAB': return 'grab'
    if s == 'THROW': return 'throw'
    if s == 'AIR_ATTACK': return 'jump_attack'
    if s == 'RUN': return 'run'
    if s == 'GUARD': return 'guard'
    return None


def wave(b, stage, w, seed, ba, roles, names, cap):
    SC.setup(b, {'setup': {'mode': 'stage', 'fighter': 'terry', 'stage': stage, 'wave': w}})
    bot = Bot(seed); moves = {}; dmg = 0; hits = 0
    prev = {i: b.states[b.fget(i, 'state')] for i in range(8)}
    jumped = {}; node = {i: None for i in range(8)}
    on = [i for i in range(2, 8) if prev[i] != 'OFF']
    hpmax = b.fget(0, 'hp_max') or b.fget(0, 'hp')
    seen = set(on)
    for f in range(cap):
        b.run(1, p1=bot.keys(b))
        hp = b.fget(0, 'hp')
        if hp < hpmax: dmg += hpmax - hp; hits += 1; b.fset(0, 'hp', hpmax)
        if b.states[b.fget(0, 'state')] == 'DEAD': b.fset(0, 'state', b.states.index('IDLE'))
        alive = 0
        for i in range(2, 8):
            s = b.states[b.fget(i, 'state')]
            if s != 'OFF': seen.add(i)
            if s not in ('OFF', 'DEAD'): alive += 1
            if s == 'ATTACK':                                  # a string's links; its down finisher (the sweep)
                nd, an = b.fget(i, 'node'), b.fget(i, 'anim')
                if prev[i] == 'ATTACK' and node[i] is not None and nd != node[i][0]:
                    moves['chain_link'] = moves.get('chain_link', 0) + 1
                    if 'crouch' in ba[an] and 'crouch' not in ba[node[i][1]]: moves['sweep'] = moves.get('sweep', 0) + 1
                node[i] = (nd, an)
            else: node[i] = None
            if s != prev[i]:
                if s == 'PREJUMP': jumped[i] = b.fget(i, 'x')
                if s == 'AIR' and i in jumped:
                    k = 'back_hop' if b.fget(i, 'jump_dir') == 2 else 'jump'
                    moves[k] = moves.get(k, 0) + 1
                k = kind_of(b, i, s, prev[i], ba, roles, names[b.char_of(i)], None)
                if k: moves[k] = moves.get(k, 0) + 1
                prev[i] = s
        if not alive and f > 30: return {'enemies': len(seen), 'moves': moves, 'damage': dmg, 'hits': hits, 'frames': f + 1, 'bot_jumps': bot.jumps}
    return {'enemies': len(seen), 'moves': moves, 'damage': dmg, 'hits': hits, 'frames': None}


def compare(fa, fb):
    """the before / after table (markdown) of two --json runs"""
    A, B = json.load(open(fa)), json.load(open(fb))
    avg = lambda rs, k: sum(r[k] or 0 for r in rs) / len(rs)
    print('| wave | enemies | distinct move types | moves started (all runs) | damage to P1 (avg) | frames to clear (avg) |')
    print('|---|---|---|---|---|---|')
    for w in A:
        for tag, X in (('before', A), ('after', B)):
            rs = X[w]; mv = {}
            for r in rs:
                for k, v in r['moves'].items(): mv[k] = mv.get(k, 0) + v
            top = ', '.join(f'{k} {v}' for k, v in sorted(mv.items(), key=lambda t: -t[1]))
            print(f"| {int(w) + 1} {tag} | {rs[0]['enemies']} | {len(mv)} | {top} | {avg(rs, 'damage'):.0f} | {avg(rs, 'frames'):.0f} |")
    for tag, X in (('before', A), ('after', B)):
        print(f"stage total {tag}: frames {sum(avg(X[w], 'frames') for w in X):.0f}, damage {sum(avg(X[w], 'damage') for w in X):.0f}")


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--compare': return compare(sys.argv[2], sys.argv[3])
    ap = argparse.ArgumentParser()
    ap.add_argument('--game', default=H.GAME); ap.add_argument('--stage', type=int, default=0)
    ap.add_argument('--waves', default='0,1,2,3,4'); ap.add_argument('--runs', type=int, default=3)
    ap.add_argument('--cap', type=int, default=5400); ap.add_argument('--json')
    a = ap.parse_args()
    b = H.Brawler(rom=os.path.join(a.game, 'brawler.neo'), game=a.game); b.game = a.game
    ba = json.load(open(os.path.join(a.game, 'build', 'chainlab.json')))['ba']
    roles = roles_of(a.game); names = SC.roster(a.game)
    out = {}
    for w in map(int, a.waves.split(',')):
        rs = [wave(b, a.stage, w, 1000 + k, ba, roles, names, a.cap) for k in range(a.runs)]
        out[w] = rs
        mv = {}
        for r in rs:
            for k, v in r['moves'].items(): mv[k] = mv.get(k, 0) + v
        fr = [r['frames'] for r in rs]
        print(f"wave {w + 1}: enemies {rs[0]['enemies']}, frames {fr}, damage {[r['damage'] for r in rs]}, bot jumps {sum(r.get('bot_jumps', 0) for r in rs)}, "
              f"types {len(mv)}: " + ', '.join(f'{k} {v}' for k, v in sorted(mv.items(), key=lambda t: -t[1])), flush=True)
    if a.json: json.dump(out, open(a.json, 'w'), indent=1)


if __name__ == '__main__':
    main()
