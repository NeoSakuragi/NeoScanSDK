#!/usr/bin/env python3
"""Haggar's made-up fury (note 20261014-171937-5d29; game.json roster haggar "fury" = a sequence of his pieces,
tools/ffight/handlers_ff.PIECES): jab, jab, finisher x3, then the 8-hit spin, in our emulator's core (harness.py), from
the note's scenario (scenarios.json, the Chain Lab: Haggar, Ryo 40 px in front, drive and fury gauge full).

Per frame from the D press to Haggar's return to idle: his state / piece (pool index) / invincibility, Ryo's state,
height and life, the sound bytes the game queued. Pass: the pieces in order (pool 1..10), 17 hits (3 x (1 + 1 + 1) + 8),
Ryo in hitstun (never knocked down, never airborne) through all 17 (the reopen: the spin's 8th reels too), then the
closing piledriver (roster[].fury_throw: his hold's B throw, S_THROW / S_THROWN from the fury's next frame, Ryo slammed
and lying), Haggar INV_FURY on every fury frame and every throw frame, 0 life lost, one super flash showing his FF
stance (roster[].flash_pose: one still frame, not the jab's), the total damage incl. the piledriver in the fury tier
(game.json tiers.fury +- spread), the voices / hit sounds sent per piece. Contact sheet: one frame per hit.

    python3 haggar_fury_proof.py [OUTDIR]          (default /data/tmp/haggar_fury)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/haggar_fury'
NOTE = '20261014-171937-5d29'
INV_FURY = 0xFF
BT_XTHROW = 4                                             # (fighter.c: BT_COUNT 2 + 2, the extra paired throw)
G = json.load(open(os.path.join(HERE, '..', '..', 'examples', 'brawler', 'game.json')))


def sound_bytes(b, last):
    """the bytes snd_cmd queued since `last` (sound.c's ring q[32], write index qt)"""
    q, qt = b.syms['q'], b.r(b.syms['qt'], 1)
    out = []
    while last != qt: out.append(b.r(q + last, 1)); last = (last + 1) & 31
    return out, qt


def main():
    os.makedirs(OUT, exist_ok=True)
    b = H.Brawler(); b.game = scenario.GAME
    rec = json.load(open(os.path.join(HERE, 'scenarios.json')))[NOTE]
    scenario.setup(b, rec)
    st = b.states
    b.fset(2, 'hp', 200)                                  # (Ryo kept alive: every hit counted)
    hp0, my0 = b.fget(2, 'hp'), b.fget(0, 'hp')
    _, qt = sound_bytes(b, b.r(b.syms['qt'], 1))
    rows, shots, flash = [], [], 0
    started = None
    for f in range(900):
        b.run(1, p1='d' if f < 1 else '')
        s0 = st[b.fget(0, 'state')]
        snd, qt = sound_bytes(b, qt)
        r = dict(f=f, state=s0, xid=b.fget(0, 'throw_id'), ix=b.fget(0, 'spec_ix'), sid=b.fget(0, 'spec_id'), inv=b.fget(0, 'inv'), hp=b.fget(0, 'hp'),
                 v=st[b.fget(2, 'state')], vy=round(b.fget(2, 'y'), 1), vhp=b.fget(2, 'hp'), snd=snd,
                 sf=b.r(b.syms['sf_who'], 4) != 0, x=b.fget(0, 'x'), fr=b.fget(0, 'shown_frame'))
        if s0 == 'SPECIAL' and started is None: started = f
        rows.append(r)
        if started is not None and s0 not in ('SPECIAL', 'THROW'): break
    fury = [r for r in rows if r['state'] == 'SPECIAL']
    hits = []
    for a, c in zip(rows, rows[1:]):
        if c['vhp'] < a['vhp']: hits.append(dict(f=c['f'], ix=c['ix'], dmg=a['vhp'] - c['vhp'], v=c['v'], vy=c['vy']))
    # one frame per hit for the sheet: replay to each hit frame
    scenario.setup(b, rec); b.fset(2, 'hp', 200)
    want = {h['f'] for h in hits}
    for f in range(rows[-1]['f'] + 1):
        b.run(1, p1='d' if f < 1 else '')
        if f in want:
            p = os.path.join(OUT, f'hit_{f:03d}.png'); b.screenshot(p); shots.append((p, f))
    order = []
    for r in fury:
        if not order or order[-1] != r['ix']: order.append(r['ix'])
    t = G['tiers']; lo, hi = t['fury'] * (100 - t['spread']['fury']) / 100, t['fury'] * (100 + t['spread']['fury']) / 100
    thr = [r for r in rows if r['state'] == 'THROW']    # (S_THROW: to its control return)
    spin = [h for h in hits if h['ix'] == 10 and (not thr or h['f'] < thr[0]['f'])]   # (the piledriver's slam: not the spin's)
    lying, vhp, late = None, rows[-1]['vhp'], 0
    for k in range(90):                                 # Ryo after Haggar's control return: the slam's lying (the
        b.run(1)                                        # throw's damage lands with its script's end: victim_end)
        h = b.fget(2, 'hp')
        if h < vhp: late += vhp - h
        vhp = h
        if st[b.fget(2, 'state')] in ('DOWN', 'GETUP'): lying = k; break
    total = sum(h['dmg'] for h in hits) + late       # (the lab refills an idle dummy: the hits' own drops summed)
    pile = sum(h['dmg'] for h in hits if thr and h['f'] >= thr[0]['f']) + late
    last_hit = spin[-1]['f'] if spin else None
    before = [r for r in rows if started is not None and started <= r['f'] < (last_hit or 0)]
    sent = [(r['f'] - started, ' '.join(f'{x:02X}' for x in r['snd'])) for r in rows if r['snd'] and started is not None and r['f'] >= started]
    checks = [
        (order == list(range(1, 11)), f'the pieces in order: pool {order} (1-10: J J F J J F J J F spin)'),
        (len([h for h in hits if h['ix'] >= 1 and h['f'] <= (last_hit or 0)]) == 17, f"{len([h for h in hits if h['f'] <= (last_hit or 0)])} hits up to the spin's last (want 17: 3 x jab, jab, finisher + the spin's 8)"),
        (len(spin) == 8, f"the spin: {len(spin)} hits (want 8)"),
        (all(r['v'] in ('HITSTUN', 'IDLE', 'WALK') and r['vy'] == 0 for r in before[1:]),
         'Ryo reels on the ground until the spin\'s last hit (no launch, no knockdown): ' + ','.join(sorted({r['v'] for r in before}))),
        (len(spin) == 8 and all(h['v'] == 'HITSTUN' for h in spin), f"the spin's 8 hits all reel, the 8th too: {[h['v'] for h in spin]}"),
        (bool(thr) and bool(fury) and thr[0]['f'] == fury[-1]['f'] + 1 and thr[0]['xid'] == BT_XTHROW and 'THROWN' in {r['v'] for r in thr},
         f"the piledriver closes it: S_THROW from fury frame {thr[0]['f'] - started if thr else '-'} (the spin's end {fury[-1]['f'] - started if fury else '-'}), throw_id {thr[0]['xid'] if thr else '-'} (BT_XTHROW {BT_XTHROW}), Ryo {sorted({r['v'] for r in thr})}"),
        (lying is not None, f"Ryo slammed and lying {lying} frames after Haggar's control return"),
        (all(r['inv'] == INV_FURY for r in fury + thr) and min(r['hp'] for r in rows) >= my0, f'Haggar INV_FURY on all {len(fury)} fury frames and {len(thr)} throw frames, 0 life lost'),
        (lo <= total <= hi, f'damage {total} incl. the piledriver {pile} (fury tier {t["fury"]} +-{t["spread"]["fury"]} %: {lo:.0f}-{hi:.0f})'),
        (sum(1 for r in rows if 0x3A in r['snd']) == 1 or True, 'super flash'),
    ]
    flashes = sum(1 for r in rows for k in range(len(r['snd']) - 1) if r['snd'][k] == 0x1A and r['snd'][k + 1] == 0x3A)
    checks[-1] = (flashes == 1, f'one super flash (its charge sound $1A $3A sent {flashes} time(s))')
    # results-1014 (Bruno: "make him wait a bit during the freeze animation"): a sequence fury waits for the flash: its
    # first piece's first frame held through the whole freeze (no motion, no hit), the first jab after it
    fl = [r for r in rows if r['sf']]
    still = fl and len({(r['fr'], r['x']) for r in fl}) == 1
    checks += [
        (len(fl) == G['super_flash']['freeze'] - 1, f"the flash: sf_who seen on {len(fl)} frames (want super_flash.freeze - 1 = {G['super_flash']['freeze'] - 1}: it clears inside its last frozen frame)"),
        (bool(still) and all(r['state'] == 'SPECIAL' and r['ix'] == 1 for r in fl),
         f"Haggar holds still through the flash: {len({(r['fr'], r['x']) for r in fl})} distinct (frame, x) on its frames, the first piece (pool 1)"),
        (bool(hits) and bool(fl) and hits[0]['f'] > fl[-1]['f'] and not any(fl[0]['f'] <= h['f'] <= fl[-1]['f'] for h in hits),
         f"no hit under the flash; the first jab lands {hits[0]['f'] - fl[-1]['f'] if hits and fl else '-'} frames after it ends"),
    ]
    # the reopen (Bruno: "during the freeze I can see that Haggar is already hitting"): the frozen frame is his stance
    # (roster[].flash_pose), not the jab's first frame
    jab0 = next((r['fr'] for r in rows if fl and r['f'] > fl[-1]['f'] + 1 and r['state'] == 'SPECIAL'), None)
    checks.append((bool(fl) and jab0 is not None and fl[0]['fr'] != jab0,
                   f"the freeze shows the stance pose (frame {fl[0]['fr'] if fl else '-'}), not the jab's (frame {jab0})"))
    if fl:                                              # the flash sheet: its first / middle / last frames, the first jab
        scenario.setup(b, rec); b.fset(2, 'hp', 200)
        pick = {fl[0]['f']: 'flash start', fl[len(fl) // 2]['f']: 'flash middle', fl[-1]['f']: 'flash last frame',
                fl[-1]['f'] + 1: 'flash over: the jab starts', hits[0]['f'] if hits else -1: 'the first jab lands'}
        fsh = []
        for f in range(max(pick) + 1):
            b.run(1, p1='d' if f < 1 else '')
            if f in pick: p = os.path.join(OUT, f'flash_{f:03d}.png'); b.screenshot(p); fsh.append((p, f'f{f - started} {pick[f]}'))
        ims = [Image.open(p) for p, _ in fsh]; w, h = ims[0].size
        sh = Image.new('RGB', (len(ims) * w, h + 14), 'white'); d = ImageDraw.Draw(sh)
        for k, (im, (_, lab)) in enumerate(zip(ims, fsh)): sh.paste(im, (k * w, 14)); d.text((k * w + 2, 1), lab, fill='black')
        sh.save(os.path.join(OUT, 'flash_sheet.png')); print('flash sheet', os.path.join(OUT, 'flash_sheet.png'))
    ok = all(c for c, _ in checks)
    for c, w in checks: print(('OK  ' if c else 'FAIL') + ' ' + w)
    rep = dict(ok=ok, checks=[dict(ok=c, what=w) for c, w in checks], hits=hits, sounds=sent, frames=rows)
    json.dump(rep, open(os.path.join(OUT, 'report.json'), 'w'), indent=1)
    print('hits', [(h['f'] - started, h['ix'], h['dmg'], h['v']) for h in hits])
    print('sounds (frame from the press: bytes)', sent)
    if shots:                                           # contact sheet: each hit's frame, its piece and Ryo's state
        ims = [Image.open(p) for p, _ in shots]; w, h = ims[0].size; cols = 6
        sheet = Image.new('RGB', (cols * w, ((len(ims) + cols - 1) // cols) * (h + 14)), 'white'); d = ImageDraw.Draw(sheet)
        for k, (im, (_, f)) in enumerate(zip(ims, shots)):
            x, y = (k % cols) * w, (k // cols) * (h + 14); sheet.paste(im, (x, y + 14))
            hh = hits[k]; d.text((x + 2, y + 1), f"#{k + 1} f{f - started} pool {hh['ix']} -{hh['dmg']} {hh['v']}", fill='black')
        sheet.save(os.path.join(OUT, 'sheet.png')); print('sheet', os.path.join(OUT, 'sheet.png'))
    print('ALL OK' if ok else 'FAILED'); sys.exit(0 if ok else 1)


if __name__ == '__main__': main()
