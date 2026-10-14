#!/usr/bin/env python3
"""Final Fight's throws as paired scripts (export96 throw layout: export_ff.throws), from FF's own play measured in FBNeo
(rec_ff.py: P1 grabs Bred by walking into him, then the action; every frame both objects).

    python3 throws_ff.py   -> tools/ffight/throws_ff.json (needs /data/tmp/ffight/rec/<name>_<scenario>.json)

Per throw, from the frame the thrower's throw animation starts:
- timeline: the thrower's frame record, tx / ty = px from his start (forward of his grab facing +, up +), turned (he
  faces the other way: Guy / Cody turn and throw behind them, Haggar turns for the backdrop) [meas];
- victim: Bred's place from the thrower (forward +, up +), facing bit (1: Bred faces the thrower's grab facing), key =
  Bred's frame ('B' + hex: victim_poses_ff.json gives its posture), the role once he lies ('down') and gets up ('getup');
  his frame for the posture in the MIRROR match = the fighter's own frame for it (VPOSE: FF draws each fighter thrown
  by enemies with these: hurt, knocked down, upside down, lying);
- impacts: the frames Bred's life drops (FF's damage: 'damage'), release = he leaves the hands (his own thrown state, else
  the slam's impact; from it the body is a thrown body), land = the first impact from the release on (the body's floor
  touch: the damage; a bounce after it deals none), else the first floor touch after an airborne frame, ret = the
  first frame the thrower is back in his idle (control returns).
Inputs (the brawler's hold, docs/brawler_data_model.md "Throws"): throw_c = hold + forward + A (FF: direction toward
the enemy + attack), throw_d = hold + back + A (FF: away + attack; FF plays the same animation turned), throw_x =
Haggar's piledriver (FF: jump in the hold, then attack; the brawler's hold + B, roster throws.b: forward / back + B
carried 94 px, FF's grab_jumpBf / grab_jumpBb: the same throw moved 95 / 94 px at a steady speed over its airborne rows)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ff
REC = '/data/tmp/ffight/rec'
OUT = os.path.join(HERE, 'throws_ff.json')

THROWS = {   # (scenario, the thrower's throw animation(s): the row 0 = the first frame one of them plays, name, inputs)
    'guy': {'throw_c': ('grab_fwd', (0x10480,), 'Guy throw (forward)', 'hold + forward + A'),
            'throw_d': ('grab_back', (0x10480,), 'Guy throw (back)', 'hold + back + A')},
    'cody': {'throw_c': ('grab_fwd', (0x118C0,), 'Cody throw (forward)', 'hold + forward + A'),
             'throw_d': ('grab_back', (0x118C0,), 'Cody throw (back)', 'hold + back + A')},
    'haggar': {'throw_c': ('grab_fwd', (0x13BFA,), 'Backdrop (forward)', 'hold + forward + A'),
               'throw_d': ('grab_back', (0x13BFA,), 'Backdrop (back)', 'hold + back + A'),
               'throw_x': ('grab_jumpB', (0x13450,), 'Piledriver', 'hold + B, forward / back + B carried 94 px (FF: jump, then attack)')},
}
# the fighter's own frame for each posture (the mirror match; FF's frames of him thrown by enemies) [ROM, by eye]
VPOSE = {
    'guy': {'standing': 0xF6BC, 'grabbed': 0x106E6, 'hit_reel': 0x106E6, 'hunched': 0x1072E, 'bent_back': 0x1094E,
            'launched': 0x1094E, 'horizontal': 0x1094E, 'curled': 0x1094E, 'falling': 0x10AB2, 'inverted': 0x10AB2,
            'inverted_diagonal': 0x10AB2, 'lying': 0x10992},
    'cody': {'standing': 0x111BE, 'grabbed': 0x1241E, 'hit_reel': 0x1241E, 'hunched': 0x12466, 'bent_back': 0x12392,
             'launched': 0x12392, 'horizontal': 0x12392, 'curled': 0x12392, 'falling': 0x1268A, 'inverted': 0x1268A,
             'inverted_diagonal': 0x1268A, 'lying': 0x123D6},
    'haggar': {'standing': 0x12D04, 'grabbed': 0x13F84, 'hit_reel': 0x13F84, 'hunched': 0x13FCC, 'bent_back': 0x13ECE,
               'launched': 0x13ECE, 'horizontal': 0x13ECE, 'curled': 0x13ECE, 'falling': 0x14A50, 'inverted': 0x14A50,
               'inverted_diagonal': 0x14AD6, 'lying': 0x13F3C},
}
POSES = json.load(open(os.path.join(HERE, 'victim_poses_ff.json')))
GETUP = set(POSES['getup'])
IDLE = {'guy': 0xF6B4, 'cody': 0x111B6, 'haggar': 0x12CFC}

def build(name, key):
    scen, anims, title, inputs = THROWS[name][key]
    rows = json.load(open(os.path.join(REC, f'{name}_{scen}.json')))['rows']
    i0 = next(i for i, r in enumerate(rows) if any(r['P']['anim'] == a for a in anims))
    if rows[i0 - 1]['P']['st'] in (2, 6, 8): i0 -= 1   # row 0 = the press frame, still the hold's picture: the brawler's
                                                        # hold draws a throw's row 0 (fighter.c grab, bthrow_t.gframe)
    p0 = rows[i0]['P']; d0 = 1 if p0['face'] == 0 else -1          # face 0 = facing right (FF's art)
    tl, vic, imp, dmg = [], [], [], []
    hp = rows[i0]['E']['hp']; st0 = rows[i0]['E']['st']; ret = None; rel = land = None; airborne = False; lying = False
    for k, r in enumerate(rows[i0:]):
        P, E = r['P'], r['E']
        if ret is None and P['anim'] == IDLE[name]: ret = k
        if E['hp'] < hp: imp.append(k); dmg.append(hp - E['hp']); hp = E['hp']
        if rel is None and (E['st'] != st0 or imp): rel = k   # out of the hands: his own state (thrown, st 6), else the slam
        if rel is not None and land is None:
            if E['y'] > E['gy'] + 1: airborne = True
            elif airborne or k > rel + 40: land = k
        vkey = 'B%05X' % E['frame']
        role = None
        if POSES['poses'].get(vkey, [''])[0] == 'lying' and land is not None: lying = True; role = 'down'
        if vkey in GETUP: role = 'getup'
        post = POSES['poses'].get(vkey)
        vf = VPOSE[name].get(post[0]) if post else None
        tl.append([P['frame'], (P['x'] - p0['x']) * d0, P['y'] - p0['y'], 1 if P['face'] != p0['face'] else 0])
        vic.append([vf, (E['x'] - P['x']) * d0, E['y'] - P['y'], 1 if E['face'] == p0['face'] else 0, 0, vkey, role])
        if ret is not None and k >= ret and (role == 'getup' or k > ret + 150): break
    after = [k for k in imp if rel is not None and k >= rel]
    if after: land = after[0]                         # the body's damage = its floor touch (Guy's / Cody's landing, the
                                                      # backdrop's / piledriver's slam; the bounce after it deals none)
    if land is None: land = rel
    tl = tl[:ret]                                     # the thrower's script ends where he acts again
    return {'anim': anims[0], 'name': title, 'inputs': inputs, 'timeline': tl, 'victim': vic, 'impacts': imp,
            'damage': dmg, 'release': rel, 'land': land, 'ret': ret, 'scenario': scen}

def main():
    out = {}
    for n, ts in THROWS.items():
        out[n] = {}
        for k in ts:
            t = build(n, k); out[n][k] = t
            print(n, k, t['name'], 'rows', len(t['timeline']), len(t['victim']), 'impacts', t['impacts'], t['damage'],
                  'rel', t['release'], 'land', t['land'], 'ret', t['ret'],
                  'keys w/o pose', sorted({r[5] for r in t['victim'] if r[5] not in POSES['poses'] and r[5] not in GETUP}))
    json.dump(out, open(OUT, 'w'), indent=0)

if __name__ == '__main__': main()
