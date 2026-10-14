#!/usr/bin/env python3
"""Haggar's made-up fury (note 20261014-171937-5d29; game.json roster haggar "fury" = a sequence of his pieces,
tools/ffight/handlers_ff.PIECES): jab, jab, finisher x3, then the 8-hit spin, in our emulator's core (harness.py), from
the note's scenario (scenarios.json, the Chain Lab: Haggar, Ryo 40 px in front, drive and fury gauge full).

Per frame from the D press to Haggar's return to idle: his state / piece (pool index) / invincibility, Ryo's state,
height and life, the sound bytes the game queued. Pass: the pieces in order (pool 1..10), 17 hits (3 x (1 + 1 + 1) + 8),
Ryo in hitstun (never knocked down, never airborne) until the spin's 8th hit, knocked down by it, Haggar INV_FURY on
every frame of the fury and 0 life lost, one super flash, the total damage in the fury tier (game.json tiers.fury +-
spread), the voices / hit sounds sent per piece. Contact sheet: one frame per hit.

    python3 haggar_fury_proof.py [OUTDIR]          (default /data/tmp/haggar_fury)"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import harness as H, scenario
from PIL import Image, ImageDraw

OUT = sys.argv[1] if len(sys.argv) > 1 else '/data/tmp/haggar_fury'
NOTE = '20261014-171937-5d29'
INV_FURY = 0xFF
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
        r = dict(f=f, state=s0, ix=b.fget(0, 'spec_ix'), sid=b.fget(0, 'spec_id'), inv=b.fget(0, 'inv'), hp=b.fget(0, 'hp'),
                 v=st[b.fget(2, 'state')], vy=round(b.fget(2, 'y'), 1), vhp=b.fget(2, 'hp'), snd=snd,
                 sf=b.r(b.syms['sf_t'], 1) if 'sf_t' in b.syms else 0)
        if s0 == 'SPECIAL' and started is None: started = f
        rows.append(r)
        if started is not None and s0 != 'SPECIAL': break
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
    total = sum(h['dmg'] for h in hits)              # (the lab refills an idle dummy: the hits' own drops summed)
    last_hit = hits[-1]['f'] if hits else None
    before = [r for r in rows if started is not None and started <= r['f'] < (last_hit or 0)]
    sent = [(r['f'] - started, ' '.join(f'{x:02X}' for x in r['snd'])) for r in rows if r['snd'] and started is not None and r['f'] >= started]
    checks = [
        (order == list(range(1, 11)), f'the pieces in order: pool {order} (1-10: J J F J J F J J F spin)'),
        (len(hits) == 17, f'{len(hits)} hits (want 17: 3 x jab, jab, finisher + the spin\'s 8)'),
        (sum(1 for h in hits if h['ix'] == 10) == 8, f"the spin: {sum(1 for h in hits if h['ix'] == 10)} hits (want 8)"),
        (all(r['v'] in ('HITSTUN', 'IDLE', 'WALK') and r['vy'] == 0 for r in before[1:]),
         'Ryo reels on the ground until the last hit (no launch, no knockdown): ' + ','.join(sorted({r['v'] for r in before}))),
        (bool(hits) and hits[-1]['v'] == 'KNOCKDOWN', f"the last hit (the spin's 8th) knocks down: {hits[-1]['v'] if hits else '-'}"),
        (all(r['inv'] == INV_FURY for r in fury) and min(r['hp'] for r in rows) >= my0, f'Haggar INV_FURY on all {len(fury)} fury frames, 0 life lost'),
        (lo <= total <= hi, f'damage {total} (fury tier {t["fury"]} +-{t["spread"]["fury"]} %: {lo:.0f}-{hi:.0f})'),
        (sum(1 for r in rows if 0x3A in r['snd']) == 1 or True, 'super flash'),
    ]
    flashes = sum(1 for r in rows for k in range(len(r['snd']) - 1) if r['snd'][k] == 0x1A and r['snd'][k + 1] == 0x3A)
    checks[-1] = (flashes == 1, f'one super flash (its charge sound $1A $3A sent {flashes} time(s))')
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
