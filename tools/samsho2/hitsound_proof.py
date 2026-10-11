#!/usr/bin/env python3
"""SS2's impact sounds in the brawler (voice note 20261011-055133-5d29; hitsound_ss2.py): each SS2 fighter's A chain
(A pressed through his route: Hanzo A far > A close > B far > the A+B finisher) against the Chain Lab's dummy, in two
builds (before / after), in our emulator (harness.py, BRAWLER_CORE): per hit the move (fighter anim), the effect codes
the game queued on the hit's frame (sound.c's queue: $1A + code) and every ADPCM-A key-on the Z80 made for them (the
Z80 port tap); the keyed sample's bytes vs SS2's own sample for the move's impact list (hitsound_ss2.hit_sound);
WAVs of what each build keyed on + SS2's own samples.

    python3 hitsound_proof.py BEFORE.neo AFTER.neo [OUT]      (default OUT /data/tmp/ss2sound) -> OUT/proof.json"""
import ctypes as C, json, os, re, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, '..', 'brawler'))
import harness, voices as V
from ss2_proof import lab_req, GAME
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
NAMES = ['hanzo_ss2', 'haohmaru', 'genjuro']
OUT = sys.argv[3] if len(sys.argv) > 3 else '/data/tmp/ss2sound'

def v_of(rom):
    d = open(rom, 'rb').read(); h = struct.unpack('<6I', d[4:28]); o = 0x1000 + h[0] + h[1] + h[2]
    return d[o:o + h[3] + h[4]]

def child(tag, rom):
    b = harness.Brawler(rom=rom); S = b.syms
    log, reg = [], {}
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 6: tap.a = v
            elif p == 7:
                if tap.a == 0 and v and not v & 0x80:          # ADPCM-A key-on: each keyed channel's start / end pages
                    for ch in range(6):
                        if v >> ch & 1:
                            log.append((b.frame, ch, reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0),
                                        reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)))
                reg[tap.a] = v
        return v
    tap.a = 0; cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    hdr = open(os.path.join(GAME, 'build', 'bm_chars.h')).read()
    bcs = re.search(r'enum \{ (BC_[^}]*), BC_COUNT \}', hdr).group(1).split(', ')
    ba = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', hdr).group(1).split(', ')
    out = {}
    for rnd, name in enumerate(['haohmaru'] + NAMES):         # (a first run: the first Lab request after the boot is black;
                                                              # another fighter's: the same request twice does not reload)
        lab_req(b, 1, bcs.index('BC_' + name.upper()), 0); b.run(40)
        dm = next(i for i in range(1, 8) if b.states[b.fget(i, 'state')] != 'OFF')
        b.place(0, x=b.fget(dm, 'x') - (50 if name == 'haohmaru' else 70), z=b.fget(dm, 'z')); b.fset(0, 'facing', 1); b.run(5)
        h0 = len(b.hits); oqt = b.r(S['qt'], 1); sent = []; anims = {}; log.clear()
        for f in range(150):
            b.run(1, p1='a' if f % 16 < 2 and f < 64 else '')
            anims[b.frame] = ba[b.fget(0, 'anim')]
            qt = b.r(S['qt'], 1)
            while oqt != qt: sent.append((b.frame, b.r(S['q'] + oqt, 1))); oqt = (oqt + 1) & 31
        if rnd == 0: b.run(200); continue
        rows = []
        for h in b.hits[h0:]:
            fr = h[0]
            codes = [sent[i + 1][1] for i, (f2, v) in enumerate(sent) if v == 0x1A and i + 1 < len(sent) and abs(f2 - fr) <= 1]
            keys = [[f2, ch, s_, e_] for f2, ch, s_, e_ in log if fr - 1 <= f2 <= fr + 4]
            rows.append({'frame': fr, 'move': anims.get(fr) or anims.get(fr - 1), 'codes': [f'1A{c:02X}' for c in codes], 'keyons': keys})
        out[name] = rows
    json.dump(out, open(os.path.join(OUT, f'_{tag}.json'), 'w')); return True

def main():
    before, after = sys.argv[1], sys.argv[2]
    if len(sys.argv) > 4: return child(sys.argv[4], {'before': before, 'after': after}[sys.argv[4]])
    import subprocess, hitsound_ss2 as HS, export_ss2 as X
    os.makedirs(OUT, exist_ok=True)
    for tag in ('before', 'after'): subprocess.run([sys.executable, __file__, before, after, OUT, tag], check=True)
    runs = {t: json.load(open(os.path.join(OUT, f'_{t}.json'))) for t in ('before', 'after')}
    vs = {'before': v_of(before), 'after': v_of(after)}; v2 = V.v_rom('samsho2')
    rep = json.load(open(os.path.join(GAME, 'build', 'snd', 'snd_report.json')))['sfx_from']
    by_cmd = {f['cmd']: (c, f) for c, f in rep.items() if f['game'] == 'samsho2'}
    G = {r['name']: r for r in json.load(open(os.path.join(GAME, 'game.json')))['roster']}
    res, ok = {}, True
    for name in NAMES:
        ch = X.CAST[G[name]['bank'].split(':')[1]]
        over = {k: int(v.lstrip('$'), 16) for k, v in (G[name].get('moves') or {}).items()}
        for tag in ('before', 'after'):
            for k, r in enumerate(runs[tag][name]):
                mv = r['move'][3:].lower()
                slot = over.get(mv, X.MOVES.get(mv, (None,))[0])
                want = HS.hit_sound(ch, slot) if slot is not None else None
                r['ss2_slot'] = slot; r['ss2_impact'] = want
                keyed = [tuple(x[2:]) for x in r['keyons']]
                if tag == 'after':
                    exp = {by_cmd[w][1]['pages'][0]: (w, by_cmd[w]) for w in (want or [])}
                    hit = [(s_, e_) for s_, e_ in keyed if s_ in exp]
                    r['ss2_keyed'] = [exp[s_][0] for s_, _ in hit]
                    r['bytes_equal_ss2'] = bool(hit) and all(
                        vs['after'][s_ << 8:(e_ + 1) << 8] == V.sample_bytes(v2, [exp[s_][1][1]['source_pages']]) for s_, e_ in hit)
                    r['ok'] = want is None or (r['bytes_equal_ss2'] and all(f'1A{by_cmd[w][0]}' in r['codes'] for w in r['ss2_keyed']))
                    ok &= r['ok']
                for j, (s_, e_) in enumerate(keyed):
                    V.write_wav(os.path.join(OUT, f'{tag}_{name}_{k}_{r["move"][3:].lower()}_{j}.wav'), vs[tag], [(s_, e_)])
            res.setdefault(name, {})[tag] = runs[tag][name]
            for r in runs[tag][name]:
                print(tag, name, r['move'], 'codes', r['codes'], 'keyons', [x[2:] for x in r['keyons']],
                      'SS2', r['ss2_impact'], ('keyed ' + str(r['ss2_keyed']) + (' OK' if r['ok'] else ' FAIL')) if tag == 'after' else '', flush=True)
    for w, (c, f) in sorted(by_cmd.items()):
        V.write_wav(os.path.join(OUT, f'ss2_{w}.wav'), v2, [f['source_pages']])
    json.dump(res, open(os.path.join(OUT, 'proof.json'), 'w'), indent=1)
    print('ALL OK' if ok else 'FAIL'); return ok

if __name__ == '__main__':
    sys.exit(0 if main() else 1)
