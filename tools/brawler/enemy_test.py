#!/usr/bin/env python3
"""Enemy definitions in the running game (harness, our emulator's core; never MAME): the lab mailbox's enemy test
(fighter.h lab_t req 3: P1 against one enemy definition with its own AI, respawned when beaten) and the data-pack
write path (lab.load 3, gamedata.h gdpack_t, build_tables.py pack).

    python3 enemy_test.py OUTDIR [ENEMY ...]     each enemy (game.json name; default YAKUZA VIPER SNIPER) against Terry
                                                 standing still (life refilled): screenshots, its name / life / colours /
                                                 AI row / route tree as the game holds them, what its AI did in 600 frames
    python3 enemy_test.py OUTDIR --pack          the write path: YAKUZA's life 60 -> 90 in an edited game.json, packed,
                                                 sent while YAKUZA fights (pending), installed at its respawn; a bad pack
                                                 refused; back to the ROM's tables
"""
import copy, json, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
import harness, build_tables as BT
from labdrive import Lab, PACK_OFF, PACK_STAT_OFF
GAME = harness.GAME
STAT = {0: 'none', 1: 'pending', 2: 'installed', 3: 'rom'}


def main():
    out = sys.argv[1]; os.makedirs(out, exist_ok=True)
    g = json.load(open(os.path.join(GAME, 'game.json')))
    en = [e['name'] for e in g['enemies']]
    L = Lab(); b = L.b; S = b.syms
    def stat(): v = b.r(L.lab + PACK_STAT_OFF, 1); return f'bad (check {v & 0x7F})' if v & 0x80 else STAT[v]
    prom = open(os.path.join(GAME, 'brawler.neo'), 'rb').read()[4096:]   # P ROM ($000000-$0FFFFF), 16-bit words byte-swapped
    def byte(a): return b.r(a, 1) if a >= 0x100000 else prom[a ^ 1]
    def cstr(a):                                            # a C string in the ROM or RAM (0: none)
        s = b''
        while a and byte(a + len(s)) and len(s) < 16: s += bytes([byte(a + len(s))])
        return s.decode('latin-1') if a else None
    def enemy_test(name):
        L.b.core.retro_reset(); b.frame = 0
        for _ in range(400): b.core.retro_run()
        L.poke(0, b'LAB1'); L.poke(5, [0, en.index(name)]); L.poke(4, [3])
        for _ in range(600):
            b.run(1)
            if b.r(L.lab + 8, 1) == 2: break
        else: raise RuntimeError('enemy test not active')
        b.run(2)
    def info():
        f = lambda k: b.fget(2, k)
        base = S['fighters'] + 2 * b.fsize
        rd = lambda field: b.r(base + harness_off(field), 4)
        return {'fighter': b.char_of(2), 'hp': f('hp'), 'hp_max': f('hp_max'), 'set': f('set'), 'tint': f('tint'), 'power': f('power'),
                'name': cstr(rd('name')), 'custom_colours': bool(rd('cpal')), 'own_tree': bool(rd('tree'))}
    if len(sys.argv) > 2 and sys.argv[2] == '--pack':
        enemy_test('YAKUZA'); print('YAKUZA from the ROM:', info())
        g2 = copy.deepcopy(g); next(e for e in g2['enemies'] if e['name'] == 'YAKUZA')['life'] = 90
        pk = BT.pack(g2, os.path.join(GAME, 'build'))
        print('pack', len(pk), 'bytes: stages / enemies / AI rows', pk[3], pk[4], pk[5])
        b.run(30); L.poke(PACK_OFF, pk); L.poke(7, [3]); b.run(2)
        print('sent while it fights:', stat(), '| its life now', b.fget(2, 'hp_max'))
        b.fset(2, 'hp', 0); b.fset(2, 'state', b.states.index('DEAD')); b.fset(2, 'state_t', 0)   # test poke: beaten
        for k in range(200):
            b.run(1)
            if b.fget(2, 'state') != b.states.index('DEAD'): break
        b.run(30); print(f'respawned {k} frames later:', stat(), '|', info()); b.screenshot(os.path.join(out, 'pack_yakuza90.png'))
        bad = bytearray(pk); bad[2] = 9                              # a version the game does not know
        L.poke(PACK_OFF, bad); L.poke(7, [3]); b.run(2); print('a pack of version 9:', stat())
        bad = bytearray(pk); struct.pack_into('>I', bad, struct.unpack_from('>H', pk, 10)[0] + 14 + 6 * BT.EN_SIZE, 0x7FFF0)   # a name past the end
        L.poke(PACK_OFF, bad); L.poke(7, [3]); b.run(2); print('a pack with a name offset past its end:', stat())
        L.poke(7, [4]); b.run(2); print('back to the ROM (load 4):', stat())
        b.fset(2, 'hp', 0); b.fset(2, 'state', b.states.index('DEAD')); b.fset(2, 'state_t', 0)
        for k in range(200):
            b.run(1)
            if b.fget(2, 'state') != b.states.index('DEAD'): break
        b.run(2); print('respawned:', stat(), '| life', b.fget(2, 'hp_max'))
        return
    for name in sys.argv[2:] or ['YAKUZA', 'VIPER', 'SNIPER']:
        enemy_test(name)
        b.run(20); b.screenshot(os.path.join(out, f'{name.lower()}_0.png')); print(name, info())
        seen = {}; prev = None; shots = 1
        for k in range(600):
            b.run(1); s = b.states[b.fget(2, 'state')]
            if s != prev: seen[s] = seen.get(s, 0) + 1
            if s != prev and s in ('GRAB', 'SPECIAL', 'ATTACK') and shots < 4 and seen[s] == 1:
                b.run(6); b.screenshot(os.path.join(out, f'{name.lower()}_{shots}_{s.lower()}.png')); shots += 1
            prev = s
        print('  its states entered in 600 frames:', {k: v for k, v in seen.items() if k in ('WALK', 'ATTACK', 'GRAB', 'SPECIAL', 'PREJUMP')})


_OFFS = {}
def harness_off(field):
    """offsets of fighter_t's enemy fields (not in harness._layout's list)"""
    if not _OFFS:
        import subprocess, tempfile, re
        src = '#include <stddef.h>\n#include "fighter.h"\nvoid f(void){' + ''.join(
            f'asm volatile(".equ O_{k}, %c0" :: "i"(offsetof(fighter_t, {k})));' for k in ('name', 'cpal', 'tree')) + '}\n'
        with tempfile.NamedTemporaryFile('w', suffix='.c', delete=False) as t: t.write(src)
        asm = subprocess.run(['m68k-linux-gnu-gcc', '-m68000', '-O2', '-I' + GAME, '-I' + os.path.join(GAME, 'build'),
                              '-I' + os.path.join(GAME, '..', '..', 'sdk', 'include'), '-S', '-o', '-', t.name], capture_output=True, text=True, check=True).stdout
        os.unlink(t.name)
        _OFFS.update({k[2:]: int(v) for k, v in re.findall(r'\.equ (O_\w+), (\d+)', asm)})
    return _OFFS[field]


if __name__ == '__main__':
    main()
