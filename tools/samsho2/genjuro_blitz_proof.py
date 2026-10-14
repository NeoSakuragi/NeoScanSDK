#!/usr/bin/env python3
"""Genjuro's forward,forward + A Blitz = SS2's far A+B (voice note 20261014-141046-5d29, Bruno: "use the far forward A
plus B from the original game ... and use the screaming sound as well"), the brawler vs Samurai Shodown II.

SS2 side (measured in our emulator, capture_cmds.py --normals -> /data/neogeo_dict/samsho2/moves/12.json 'far_ab'; and
read in the 68000 code): far A+B = class 1 sub 11, animation 278 (= "$116"); P1 does not move (x constant: no lunge, the
blade reaches 160 px); at the move's start the code ($275D6) sends the whiff swing ($C9EC[flag] -> $5A9C: $CC) and the
ATTACK VOICE: $5BA4 with list $CA00[flag] (A+B: list 1), whose 8-step pattern ($5B64[pattern * 8 + counter], counter
$7106[list] + 1 a use) cycles Genjuro's $20F.. voices; counter 0 (the first A+B of a match, the capture's) = $1C $DD =
voices.json id 5, his 774 ms scream (the only long, sustained, high one of the five: f0 ~510 Hz). The hit sends P2's
hurt voice and the A+B impact $C6 (SLASH L, hitsound_ss2).

Brawler side (the Chain Lab, Ryo the dummy, our emulator's core with the Z80 port tap): forward, forward, A from GAP px
plays BA_ATK_AB_FAR (game.json roster genjuro moves atk_ab_far "$116", blitz ff atk_ab_far, voices set atk_ab_far 5),
its steps and their frames vs SS2's capture, his x (no travel, as SS2), the hit (damage, both held in the hit-stop), the
voice command read by the Z80 at the move's start = id 5 with the keyed V ROM bytes == SS2's own sample; the sheet
(SS2's steps from the ROM over the brawler's screenshots of the same steps).

    python3 genjuro_blitz_proof.py ROM OUTDIR"""
import ctypes as C, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__)); B = os.path.join(HERE, '..', 'brawler')
sys.path.insert(0, HERE); sys.path.insert(0, B)
import harness, voices as V, scenario as S
harness.CORE = '/data/neogeo_dict/sound/snd98/ff3/geolith_tap.so'
TAP = C.CFUNCTYPE(C.c_uint8, C.c_int, C.c_uint16, C.c_uint8)
CH, ANIM, GAP = 12, 278, 120


def ss2_side():
    import neo2 as N, ss2, hitsound_ss2 as HS
    cap = next(m for m in json.load(open('/data/neogeo_dict/samsho2/moves/12.json')) if m['name'] == 'far_ab')
    st = ss2.parse_anim(CH, ANIM, 400); at = {s['addr']: k for k, s in enumerate(st)}
    rows = [r for r in cap['rows'] if r['p1']['a'] == ANIM]
    runs = []
    for r in rows:
        k = at.get(r['p1']['st'])
        if runs and runs[-1][0] == k: runs[-1][1] += 1
        else: runs.append([k, 1])
    hit_f = next(r['f'] for r in rows if r['p2']['cls'] == 3) - rows[0]['f']
    snd = [(r['f'] - rows[0]['f'], [f'{x:02X}' for x in r['snd']]) for r in rows if r['snd']]
    flag = HS.action_flag(CH, ANIM)[0]
    lst = N.u8(0xCA00 + flag); e = N.u32(0x5BE2 + 4 * CH) + 4 * lst; pat, base = N.u16(e), N.u16(e + 2)
    cycle = [f'{N.u16(0x5FD2 + 2 * (base + N.u8(0x5B64 + pat * 8 + c))):04X}' for c in range(8)]
    return {'anim': ANIM, 'steps': [[k, n] for k, n in runs], 'frames': len(rows), 'hit_frame': hit_f,
            'x': sorted({r['p1']['x'] for r in rows}), 'sounds': snd, 'action_flag': flag, 'voice_list': lst,
            'voice_cycle': cycle, 'impact': [f'{w:04X}' for w in HS.impact_cmds(flag)]}


def main(rom, outdir):
    os.makedirs(outdir, exist_ok=True)
    R = {'ss2': ss2_side()}
    game = S.snapshot(rom)
    b = harness.Brawler(rom=rom, game=game); b.game = game
    log = []; a = [0, 0]
    def tap(write, port, v):
        p = port & 0xFF
        if write:
            if p == 4: a[0] = v
            elif p == 6: a[1] = v
            elif p == 7: log.append((b.frame, 'b', a[1], v))
        elif p == 0 and v: log.append((b.frame, 'c', v, 0))
        return v
    cb = TAP(tap); b.core.retro_neoscan_z80_tap(cb)
    snd = os.path.join(harness.GAME, 'build', 'snd')
    rep = json.load(open(os.path.join(snd, 'snd_report.json')))['voices']
    m1 = open(os.path.join(snd, 'm1.bin'), 'rb').read(); vrom = open(os.path.join(snd, 'v1.bin'), 'rb').read()
    hdr = open(os.path.join(harness.GAME, 'build', 'bm_chars.h')).read()
    ba = re.search(r'enum \{ (BA_[^}]*), BA_COUNT \}', hdr).group(1).split(', ')
    bank = json.load(open(V.JSON))['fighters']['genjuro']['voices']; v2 = V.v_rom('samsho2')
    codes = {int(c): int(i) for i, c in rep['fighters']['genjuro']['codes'].items()}
    ov = rep['overflow']
    TAB = {int(p, 16): 0x484C for p in rep['prefixes']}; TAB.update({int(p, 16): 0x544C for p in ov['prefixes']})
    PL = {int(rep['prefixes'][0], 16): 0, int(ov['prefixes'][0], 16): 0x100,
          int(rep['prefixes'][1], 16): 0, int(ov['prefixes'][1], 16): 0x100}

    def voices_in(f0, f1):                                  # (hao2_proof's reader: command -> key-on -> sample bytes)
        res, want, pend, reg = [], None, None, {}
        for f, kind, x, y in log:
            if kind == 'c':
                if want is not None:
                    if f0 <= f <= f1 and want in PL: pend = (want, x, f)
                    want = None
                elif x in TAB: want = x
                continue
            reg[x] = y
            if pend and x == 0 and y and not y & 0x80:
                ch = (y & -y).bit_length() - 1
                st, en = reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0), reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)
                r = TAB[pend[0]] + 6 * pend[1]
                if (st, en) != (m1[r + 1] | m1[r + 2] << 8, m1[r + 3] | m1[r + 4] << 8): continue
                vid = codes.get(pend[1] | PL[pend[0]]); vo = bank[vid - 1] if vid else None
                res.append({'frame': pend[2], 'voice': vid, 'ss2_cmd': vo['cmd'] if vo else None,
                            'bytes_equal_ss2': bool(vo) and vrom[st << 8:(en + 1) << 8] == V.sample_bytes(v2, vo['segments'])})
                pend = None
        return res

    rec = {'setup': {'mode': 'lab', 'fighter': 'genjuro', 'dummy': 'ryo', 'gap': GAP}, 'do_keys': '1:R,1:-,1:R,1:Ra', 'proof': 150}
    shots = {}
    def run(shoot):
        S.setup(b, rec); del log[:]; t0 = b.frame; h0 = len(b.hits); rows = []; seen = set()
        def each():
            an = b.fget(0, 'anim')
            rows.append({'t': b.frame - t0, 'p1': b.states[b.fget(0, 'state')], 'anim': ba[an] if an < len(ba) else an,
                         'step': b.fget(0, 'step'), 'x': round(b.fget(0, 'x'), 1), 'fz1': b.fget(0, 'freeze'),
                         'd': b.states[b.fget(2, 'state')], 'dx': round(b.fget(2, 'x'), 1), 'hp2': b.fget(2, 'hp'), 'fz2': b.fget(2, 'freeze')})
        for part in rec['do_keys'].split(','):
            n, k = part.split(':')
            for _ in range(int(n)): b.run(1, p1=k.replace('-', '')); each()
        for _ in range(rec['proof']):
            r = rows[-1]
            key = (r['anim'], r['step'])
            if shoot and r['anim'] == 'BA_ATK_AB_FAR' and key not in seen:
                seen.add(key); p = os.path.join(outdir, f'br_step{r["step"]:02d}.png'); b.screenshot(p); shots[r['step']] = p
            else: b.run(1)
            each()
        hits = [(f - t0, d) for f, i, d, st in b.hits[h0:] if i == 2]
        return rows, hits, t0
    rows, hits, t0 = run(False)
    mv = [r for r in rows if r['anim'] == 'BA_ATK_AB_FAR']
    runs = []
    for r in mv:
        if runs and runs[-1][0] == r['step']: runs[-1][1] += 1
        else: runs.append([r['step'], 1])
    start = mv[0]['t'] if mv else None
    vs = voices_in(t0 + start - 1, t0 + start + 3) if mv else []
    first_hit = hits[0][0] if hits else None
    hr = next((r for r in rows if r['t'] == first_hit), None)
    R['brawler'] = {'gap': GAP, 'anim': 'BA_ATK_AB_FAR', 'starts': start, 'steps': runs, 'frames': len(mv),
                    'x': sorted({r['x'] for r in mv}), 'hits': hits, 'hit_frame_in_move': first_hit - start if hits and mv else None,
                    'hold_at_hit': hr and (hr['fz1'], hr['fz2']), 'dummy_after': [(r['d'], r['hp2']) for r in rows if first_hit and first_hit <= r['t'] <= first_hit + 3],
                    'voices': vs}
    ss = R['ss2']; bw = R['brawler']
    no_hs = lambda st: [k for k, n in st]
    R['checks'] = {
        'plays_far_ab': bool(mv),
        'steps_in_order': no_hs(bw['steps']) == no_hs(ss['steps']),
        'step_frames_outside_hitstop': [(k, n, m) for (k, n), (_, m) in zip(bw['steps'], ss['steps'])],
        'no_travel': len(bw['x']) == 1 and len(ss['x']) == 1,
        'hits': bool(hits),
        'held_in_hitstop': bool(hr) and hr['fz1'] > 0 and hr['fz2'] > 0,
        'scream': any(v['voice'] == 5 and v['ss2_cmd'] == ss['voice_cycle'][0] and v['bytes_equal_ss2'] for v in vs),
    }
    R['ok'] = all(R['checks'][k] for k in ('plays_far_ab', 'steps_in_order', 'no_travel', 'hits', 'held_in_hitstop', 'scream'))
    # the sheet: SS2's steps (ROM render) over the brawler's screenshots of the same steps
    run(True)
    from PIL import Image, ImageDraw
    import sheet_ss2
    cells = sheet_ss2.anim_cells(CH, ANIM, 200, 200)
    W, H = 200, 200
    img = Image.new('RGB', (W * len(cells), H * 2 + 40), 'white'); d = ImageDraw.Draw(img)
    for k, (im, st) in enumerate(cells):
        img.paste(im, (k * W, 0)); d.rectangle([k * W, 0, (k + 1) * W - 1, H - 1], outline='black')
        d.text((k * W + 4, 4), f'SS2 278 step {k} t{st["ticks"]}', fill='black')
        if k in shots:
            s = Image.open(shots[k]); x = int(round(next(r['x'] for r in mv if r['step'] == k)))
            crop = s.crop((max(0, x - 120), max(0, s.height - 210), max(0, x - 120) + W, s.height - 10)).resize((W, H))
            img.paste(crop, (k * W, H + 20))
        d.rectangle([k * W, H + 20, (k + 1) * W - 1, 2 * H + 19], outline='black')
        d.text((k * W + 4, H + 4), f'brawler step {k}', fill='black')
    img.save(os.path.join(outdir, 'sheet.png'))
    R['sheet'] = os.path.join(outdir, 'sheet.png')
    json.dump(R, open(os.path.join(outdir, 'proof.json'), 'w'), indent=1)
    print(json.dumps(R['checks']), 'OK' if R['ok'] else 'FAIL')


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
