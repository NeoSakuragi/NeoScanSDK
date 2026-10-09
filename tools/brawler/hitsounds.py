#!/usr/bin/env python3
"""A fighter's hit sounds, for the Lab's sounds page (sounds.html?f=kim, Bruno 2026-10-09: "the sounds played during
the chains of Kim, I'm not happy: each hit (snapshot) + sound; I want to listen and change them via a drop down").

    BRAWLER_CORE=<core> python3 hitsounds.py hits [FIGHTER]    every hit of the fighter's chain, finishers and hold, played
                                                              in our emulator (the Chain Lab's training mode, harness.py):
                                                              the impact frame (cropped on the fighter + the dummy) and the
                                                              sound command the game queued on that frame (sound.c's queue:
                                                              $1A + code) -> OUT/<fighter>/hits.json + <key>.png
    python3 hitsounds.py sfx                                  every effect of the build's sound ROM (songs.json "sfx"): its
                                                              ADPCM-A sample decoded straight from build/snd (m1.bin record,
                                                              v1.bin bytes), trimmed + normalised -> OUT/sfx/<code>.wav
                                                              + OUT/sfx.json
OUT = /data/neogeo_dict/hitsounds (make_site.py copies it to the site's sounds/). One emulator process at a time."""
import json, os, sys, wave
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, 'chainlab'))
GAME = os.path.join(HERE, '..', '..', 'examples', 'brawler')
OUT = '/data/neogeo_dict/hitsounds'

# readable names (the source tables: KOF98's per-button hits, fighter.c HIT_SFX's kinds, songs.json "from")
NAMES = {'11': 'Light punch hit (KOF98 A)', '12': 'Light kick hit (KOF98 B)', '13': 'Heavy punch hit (KOF98 C)',
         '14': 'Heavy kick hit (KOF98 D)', '15': 'Blowback hit (KOF98 C+D, knockdowns)', '17': 'Blocked hit',
         '18': 'Throw start', '19': 'Grab start', '1E': 'Swing, light (whiff)', '1F': 'Swing, heavy (whiff)',
         '2A': 'Slash, second', '2B': 'Sword slash (Haohmaru)', '2E': 'Fire hit (KOF96)', '31': 'Electric crackle',
         '37': 'Flame roar', '3A': 'Fury charge (super flash)', '3D': 'Back break (bone crunch)', '42': 'Fire impact',
         '4D': 'Huge boom', '61': 'Metal clang', '69': 'Ringing hit', '7A': 'Iron ball, second', '7C': 'Iron ball hit',
         '8F': 'MAX charge (KOF2000 whistle)', '9C': 'Super desperation impact', 'EB': 'Ki blast (Art of Fighting)'}
IMPACT = ['11', '12', '13', '14', '15', '17', '2A', '2B', '2E', '31', '3D', '42', '4D', '61', '69', '7A', '7C', '9C', 'EB',
          'A0', 'A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8', 'A9', 'AB', 'AC', 'AD', 'AE', 'AF', 'B0']   # (+ Bruno's KOF94 / KOF95 picks, 2026-10-09)


def sfx():
    """each effect code's ADPCM-A record in the built M ROM (slot 1's table, KOF98's 6-byte [priority][start][end][level],
    256-byte pages; build_snd.py writes them, the "from" imports included) decoded from the built V ROM (voices.adpcm_a:
    the YM2610's 12-bit ADPCM-A at 18,518 Hz). Every code is one sample, keyed on once: checked 2026-10-09 on the driver
    in the tap core (capture_snd.py's register log: one ADPCM-A key-on, no FM / SSG), so none needs a capture"""
    sys.path.insert(0, os.path.join(HERE, '..', 'port')); sys.path.insert(0, os.path.join(HERE, '..', 'kof98snd'))
    from port98 import A_TABLES
    from voices import adpcm_a
    S = json.load(open(os.path.join(GAME, 'songs.json')))['sfx']
    m1 = open(os.path.join(GAME, 'build', 'snd', 'm1.bin'), 'rb').read(); v = open(os.path.join(GAME, 'build', 'snd', 'v1.bin'), 'rb').read()
    rate = 18518
    d = os.path.join(OUT, 'sfx'); os.makedirs(d, exist_ok=True)
    out = []
    for c in S['codes']:
        r = A_TABLES[S['slot']] + 6 * int(c, 16); rec = m1[r:r + 6]
        st, en = rec[1] | rec[2] << 8, rec[3] | rec[4] << 8
        a = np.array(adpcm_a(v[st << 8:(en + 1) << 8]), np.float64)
        loud = np.nonzero(np.abs(a) > 64)[0]                                      # (the record's tail is silence)
        a = a[:loud[-1] + int(rate * 0.03)] if len(loud) else a
        a = a / max(1, np.abs(a).max()) * 0.89 * 32767                             # normalised to -1 dBFS
        n = int(rate * 0.006); a[-n:] *= np.linspace(1, 0, n)                     # (no click at the end)
        with wave.open(os.path.join(d, c + '.wav'), 'wb') as o:
            o.setnchannels(1); o.setsampwidth(2); o.setframerate(rate); o.writeframes(a.astype(np.int16).tobytes())
        out.append(dict(code=c, name=NAMES.get(c, S.get('from', {}).get(c, {}).get('what', f'unnamed ${c}').split(': ', 1)[-1][:80]), rom=S['names'].get(c, ''), impact=c in IMPACT,
                        ms=round(len(a) * 1000 / rate), pages=[st, en], record=rec.hex(),
                        src=S.get('from', {}).get(c, {}).get('game', 'kof98')))
        print(c, out[-1], flush=True)
    json.dump(out, open(os.path.join(OUT, 'sfx.json'), 'w'), indent=1)


# ---- the hits --------------------------------------------------------------------------------------------------------
# Kim (docs/brawler_gold.md, 0.9.4): chain A x5 = $48 > $5D (2 hits) > $5A > $96 (3 hits) > $98; after link 4 the stick
# picks the finisher (forward $9A, up $54, down $4D (2 hits) then $57, back the throw); the hold: A, A ($6D), A ($6E x2)
SEQS = {'kim': [
    ('chain', 'Chain (A x5, neutral)', '', [('$48', 1), ('$5D', 2), ('$5A', 1), ('$96', 3), ('$98', 1)]),
    ('fwd', 'Finisher: forward', 'R', [('$9A', 1)]),
    ('up', 'Finisher: up', 'U', [('$54', 1)]),
    ('down', 'Finisher: down', 'D', [('$4D', 2), ('$57', 1)]),
    ('back', 'Finisher: back (throw)', 'L', [('throw', 0)]),
    ('hold', 'Hold (walk in, A x3)', None, [('$6D', 1), ('$6D', 1), ('$6E', 2)])]}


def hits(name):
    from labdrive import Lab, PACK_STAT_OFF
    import export_bm
    from PIL import Image
    G = json.load(open(os.path.join(GAME, 'game.json'))); NM = [r['name'] for r in G['roster']]
    D = G['meter']['chunk'] * G['meter']['chunks']
    L = Lab(); b = L.b; ST = b.states
    q, qt = b.syms['q'], b.syms['qt']
    L.start(NM.index(name), NM.index('ryo')); b.run(30); base = b.save()
    st = lambda i=0: ST[b.fget(i, 'state')]
    od = os.path.join(OUT, name); os.makedirs(od, exist_ok=True)
    b._want_video = True

    def reset(dist):
        b.load(base); cam = b.r(b.syms['cam_x'], 2); x0 = cam + 160
        b.w(L.lab + PACK_STAT_OFF + 1, 1, 0)
        b.place(0, x=x0, z=30); b.fset(0, 'facing', 1)
        b.place(2, x=x0 + dist, z=30); b.fset(2, 'facing', 0xFF); b.fset(2, 'hp', 100)
        b.fset(0, 'drive', D); b.fset(0, 'fgauge', 0); b.run(2)

    class Run:
        def __init__(s):
            s.qt = b.r(qt, 1); s.pend = None; s.log = []; s.f = 0; s.hits = []
        def step(s, keys=''):
            hp0, fz0 = b.fget(2, 'hp'), b.fget(2, 'freeze')
            b.run(1, p1=keys); s.f += 1
            new = []
            t = b.r(qt, 1)
            while s.qt != t: new.append(b.r(q + s.qt, 1)); s.qt = (s.qt + 1) & 31
            codes = []
            for v in new:                                      # $1A + code pairs (voices: their own prefixes)
                if s.pend is not None: codes.append((s.pend, v)); s.pend = None
                elif v in (0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x16, 0x17): s.pend = v
            s.log.append(dict(f=s.f, codes=codes))
            hp, fz = b.fget(2, 'hp'), b.fget(2, 'freeze')
            if hp < hp0 or (fz > fz0 and fz >= 8):
                data, w, h, pitch = b._video
                im = Image.frombuffer('RGBX', (w, h), data, 'raw', 'BGRX', pitch, 1).convert('RGB')
                s.hits.append(dict(f=s.f, dmg=hp0 - hp, anim=export_bm.MOVES[b.fget(0, 'anim')], p1=st(0), victim=st(2), im=im,
                                   x=(b.fget(0, 'x'), b.fget(2, 'x')), cam=b.r(b.syms['cam_x'], 2)))
        def until(s, cond, n=120):
            for _ in range(n):
                if cond(): return True
                s.step()
            return cond()
        def sound_at(s, f):                                   # the hit sound queued with the hit (else a frame around)
            for df in (0, -1, 1, -2, 2):
                for row in s.log:
                    if row['f'] == f + df:
                        c = [v for p, v in row['codes'] if p == 0x1A and v not in (0x1E, 0x1F)]
                        if c: return c
            return []

    # the brawler move -> the source's animation number (export_kz's table, game.json roster[].moves overrides)
    import re
    KZ = {m: f'${int(n, 16):02X}' for m, n in re.findall(r"'(\w+)': \('anim', 0x([0-9A-Fa-f]+)", open(os.path.join(HERE, '..', 'kizuna', 'export_kz.py')).read())}
    R = next(x for x in G['roster'] if x['name'] == name); KZ.update(R.get('moves', {}))
    hold_hit, hold_fin = KZ.get('atk_b_close', '?'), '$6E'
    # the code a hit sends, from the data and fighter.c's rule (hit_sound / hit_btn): the button the move sounds as ($11 A
    # .. $14 D; C+D $15), a route node's "sound": "heavy" = D's, the knockdown hit (the last hit of the chain's last link
    # and of each finisher) = $15; roster[].hit_sfx overrides a button. The hold and the throw run their own scripts: for
    # them the code read from the game's queue on that hit (sound.c q[]) stands; for the rest it checks the rule
    BTN = {'a': 0, 'b': 1, 'ab': 1, 'c': 2, 'd': 3}
    heavy = {n['move'] for rt in json.load(open(os.path.join(HERE, 'routes', name + '.json')))['routes'] for n in rt
             if isinstance(n, dict) and n.get('sound') == 'heavy'}
    sfx_over = R.get('hit_sfx', {})
    # a hit's own sound (Bruno's picks, 2026-10-09): a route node's "sound" list (per hit of its move) and the hold
    # scripts' (game.json throws.hold.sound {hit, fin}: per impact), fighter.c own_sound
    import routes as RT
    own = RT.hit_sounds({'links': RT.merge_routes(json.load(open(os.path.join(HERE, 'routes', name + '.json')))['routes'])[0]['links']})
    hold_own = (R.get('throws') or {}).get('hold', {}).get('sound') or {}
    def rule_sound(group, anim, last_of_move, last_of_seq, hit=1, hold_k=None):
        if hold_k is not None:
            v = hold_own.get(hold_k) or []
            return f'{int(v[hit - 1], 16):02X}' if hit <= len(v) else None
        if group in ('hold', 'back'): return None
        if anim in own and hit <= len(own[anim]): return f'{own[anim][hit - 1]:02X}'
        p = anim.split('_')
        b = 3 if anim in heavy else BTN.get(p[1] if p[0] == 'atk' else p[-1], 4)
        if last_of_move and last_of_seq: return '15'
        if b < 4 and sfx_over.get('ABCD'[b]): return sfx_over['ABCD'[b]].upper()
        return None                                    # (A-D: the hit cycles, game.json hit_sounds: the attacker's count)
    out = []
    for key, title, stick, links in SEQS[name]:
        if key == 'hold':
            reset(40); r = Run()
            for _ in range(60):
                if st(0) == 'GRAB': break
                r.step('R')
            for k in range(3):                                # A until the hold hit lands (an A during the last
                n = len(r.hits)                                  # one's script is not taken)
                for _ in range(40):
                    r.step('a'); r.step(''); r.step(''); r.step('')
                    if len(r.hits) > n: break
                if k < 2: r.until(lambda: st(0) == 'GRAB' and b.fget(2, 'freeze') == 0, 60)
            r.until(lambda: len(r.hits) >= 4, 120)
        else:
            reset(44); r = Run()
            chain = SEQS[name][0][3]
            for k, (lab, nh) in enumerate(chain if key == 'chain' else chain[:4]):
                n = len(r.hits); r.step('a'); r.step('')
                r.until(lambda: len(r.hits) >= n + nh, 80)
            if key != 'chain':
                n = len(r.hits); r.step(stick + 'a'); r.step(stick)
                tot = sum(nh for _, nh in links) or 1
                r.until(lambda: len(r.hits) >= n + tot, 150)
        r.until(lambda: st(0) == 'IDLE' and st(2) in ('IDLE', 'WALK'), 400)
        # the hits of this sequence that are its own (the chain's first 4 links are shared by the finishers)
        mine = r.hits if key in ('chain', 'hold') else r.hits[7:]
        if key == 'hold':                                    # the hold's hits: its hit move, the finisher's last two
            labs = [f'{hold_hit} (A no. {k + 1})' for k in range(len(mine) - 2)] + [hold_fin] * 2
        elif key == 'back': labs = ['back throw'] * len(mine)
        else: labs = [KZ.get(h['anim'], h['anim']) for h in mine]
        for i, hh in enumerate(mine):
            lab = labs[i]; j = labs[:i + 1].count(lab); nh = labs.count(lab)
            snd = r.sound_at(hh['f'])
            k = f'{key}-{i + 1}'
            ax, vx = [x - hh['cam'] for x in hh['x']]
            cx = int((ax + vx) / 2); x0 = max(0, min(hh['im'].width - 200, cx - 100))
            hh['im'].crop((x0, 30, x0 + 200, 194)).save(os.path.join(od, k + '.png'))
            rule = rule_sound(key, hh['anim'], j == nh, i == len(mine) - 1, j,
                              ('fin' if lab == hold_fin else 'hit') if key == 'hold' else None)
            out.append(dict(key=k, group=key, title=title, move=lab, hit=j, of=nh, anim=hh['anim'], frame=hh['f'], dmg=hh['dmg'],
                            victim=hh['victim'], sound=[f'{c:02X}' for c in snd], rule=rule, img=f'{k}.png'))
            if rule and [rule] != out[-1]['sound']: print('!! the game sent', out[-1]['sound'], 'the rule says', rule, flush=True)
            print(out[-1], flush=True)
    json.dump(out, open(os.path.join(od, 'hits.json'), 'w'), indent=1)


if __name__ == '__main__':
    if sys.argv[1] == 'sfx': sfx()
    else: hits(sys.argv[2] if len(sys.argv) > 2 else 'kim')
