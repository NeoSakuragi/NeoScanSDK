#!/usr/bin/env python3
"""One recorded play session replayed in our Geolith core and measured: the session's first keyframe, then its chunks'
pads frame by frame (docs/feedback.md "Session recording"); at each chunk boundary that follows the previous chunk
without a gap, the SHA-256 of the core's state is compared with the one the Player recorded there (the drift check; a
mismatch or a gap resyncs at the next keyframe, the frames in between not measured). Only the fights count, never the
attract demo. No build tree needed: the build's analysis pack (pack.py) gives the layout and the symbols.

    python3 analyze.py SESSION_DIR PACK.json ROM.neo [--bios DIR] [--out result.json[.gz]]

Output (ANALYZER version, format below): the session's meta + the drift check (checked boundaries, mismatches, gaps,
resyncs), `events` (the session_moves.py events: special / throw / grab / death, + continue, gameover, coin, start,
bonus_end), `screens` (mode / stage / wave / phase / lives / continue count / bonus as they change), `segments` (one per
stage x wave, boss fight or bonus game in play order, each measured, below) and `summary` (the session in one row).
A segment: kind wave | boss | bonus, stage (1-based), wave (1-based), start / end frame, frames; per player in play
(`players`: '1' / '2'): fighter, life at start / end, lives at start / end, deaths, damage taken, hits taken, drive
gained / spent, fury gauge gained / spent, specials {"<role> <input>": n}, furies (fury + MAX), throws, grabs, idle
frames (no stick or button for >= 1 s), frames in play; the enemies' side: spawned {HUD name: n}, kills, damage dealt
(all enemies' life lost), hits landed, max combo (most hits on one enemy before it recovered); a bonus game: its name,
won; phase_s: seconds per game phase (wave, go = the walk to the next wave, boss, end, clear). Summary: furthest =
the furthest segment reached, furthest_fought = the furthest one with a hit landed or taken. Damage = life points (the life bar: 60 a full bar unless the fighter's hp_max says otherwise)."""
import argparse, ctypes as C, gzip, hashlib, json, os, struct, sys, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import harness
harness.WORK = os.environ.get('HARNESS_WORK', harness.WORK)       # the core's scratch save dirs (VPS: ANALYSIS/work)

ANALYZER = 3          # bump when the measurement changes: the worker re-runs every session analysed by an older one
ROLE = {0: 'C', 1: 'f+C', 2: 'd+C', 3: 'u+C', 4: 'df+C', 5: 'uf+C', 6: 'fury (D)', 8: 'form', 9: 'air special',
        10: 'down attack', 11: 'grab special', 12: 'Blitz'}
SLOT_ROLE = {'D': 'C', 'fD': 'f+C', 'dD': 'd+C', 'uD': 'u+C', 'dfD': 'df+C', 'ufD': 'uf+C'}   # chainlab.json specials keys
THROW = {0: 'forward throw (f+A)', 1: 'back throw (b+A)', 2: 'hold hit', 3: 'hold finisher (3rd A in hold)', 4: 'extra paired throw'}
MODE = {0: 'select', 1: 'fight', 2: 'title', 3: 'boss unlocked', 4: 'ending', 5: 'game over', 6: 'bonus', 7: 'ladder'}
PHASE = {0: 'wave', 1: 'go', 2: 'boss', 3: 'end', 4: 'clear'}
REACT = {'HITSTUN', 'KNOCKDOWN', 'GRABBED', 'THROWN'}       # a victim still in the combo
IDLE_MIN = 60                                               # idle = no stick / button this many frames in a row
PAD_PLAY = 0x0FF3                                           # B Y U D L R A X (libretro ids 0 1 4-9): not SELECT / START
FPS = 59.185606


class Replayer(harness.Brawler):
    """harness.Brawler fed raw pad words (bit = libretro joypad id, as player.c / web_core.c)"""
    raw = (0, 0)
    def _input(self, port, dev, idx, id):
        if dev != 1 or port > 1: return 0
        if id == 256: return self.raw[port]                     # RETRO_DEVICE_ID_JOYPAD_MASK
        return (self.raw[port] >> id) & 1


def chunks_of(d):
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith('.nsin'): continue
        seq = int(f[:6]); b = open(os.path.join(d, f), 'rb').read()
        if b[:4] != b'NSIN' or struct.unpack('<I', b[4:8])[0] != 1: continue
        W, P = struct.unpack('<QQ', b[8:24])
        if len(b) < 24 + 4 * (P - W): continue                  # a chunk still being written
        pads = struct.unpack('<%dH' % (2 * (P - W)), b[24:24 + 4 * (P - W)])
        sp = os.path.join(d, '%06d.sha256' % seq); kp = os.path.join(d, '%06d.state.gz' % seq)
        out.append({'seq': seq, 'W': W, 'P': P, 'pads': pads, 'sha': open(sp).read().strip() if os.path.exists(sp) else '',
                    'key': kp if os.path.exists(kp) else None})
    return out


class Seg:
    """one stage x wave / boss fight / bonus game being measured"""
    def __init__(self, key, f, pack):
        self.stage, self.wave, self.bonus = key
        self.start = f; self.end = f; self.frames = 0; self.phases = Counter()
        st = pack['stages'][self.stage - 1] if 0 < self.stage <= len(pack['stages']) else {}
        self.nw = st.get('nwaves')
        self.stage_name = st.get('name') or 'STAGE %d' % self.stage
        self.p = {}; self.spawned = Counter(); self.kills = 0; self.dealt = 0; self.landed = 0; self.max_combo = 0
        self.bonus_game = None; self.bonus_won = None; self.bn_won0 = None
    def pl(self, i):
        if i not in self.p:
            self.p[i] = {'fighter': None, 'hp_start': None, 'hp_end': None, 'lives_start': None, 'lives_end': None, 'deaths': 0,
                         'dmg_taken': 0, 'hits_taken': 0, 'drive_gain': 0, 'drive_spent': 0, 'fury_gain': 0, 'fury_spent': 0,
                         'specials': Counter(), 'furies': 0, 'throws': 0, 'grabs': 0, 'idle': 0, 'in_play': 0, '_idle_run': 0}
        return self.p[i]
    @property
    def kind(self):
        return 'bonus' if self.bonus else 'boss' if self.phases.get('boss') or (self.nw and self.wave > self.nw) else 'wave'
    def out(self):
        ps = {}
        for i, d in sorted(self.p.items()):
            d = dict(d); d.pop('_idle_run'); d['specials'] = dict(d['specials'].most_common()); ps[str(i + 1)] = d
        r = {'kind': self.kind, 'stage': self.stage, 'wave': self.wave, 'stage_name': self.stage_name, 'start_f': self.start,
             'end_f': self.end, 'frames': self.frames, 'seconds': round(self.frames / FPS, 1), 'players': ps,
             'spawned': dict(self.spawned), 'enemies': sum(self.spawned.values()), 'kills': self.kills, 'dmg_dealt': self.dealt,
             'hits_landed': self.landed, 'max_combo': self.max_combo,
             'phase_s': {k: round(v / FPS, 1) for k, v in self.phases.items()}}
        if self.kind == 'bonus': r.update({'bonus_game': self.bonus_game, 'won': self.bonus_won})
        return r


def analyze(session, pack, rom, bios=None, progress=None):
    meta = json.load(open(os.path.join(session, 'meta.json')))
    rsha = hashlib.sha256(open(rom, 'rb').read()).hexdigest()
    if rsha != meta['rom_sha256']: raise SystemExit(f'ROM {rsha} is not the session build {meta["rom_sha256"]}')
    if pack['rom_sha256'] != rsha: raise SystemExit('the pack is not this build')
    if bios: harness.SYSDIR = bios
    opts = {'geolith_region': meta.get('region', 'us'), 'geolith_system_type': meta.get('system_type', 'mvs'),
            'geolith_unibios_hw': meta.get('hw', 'mvs'), 'geolith_memcard': meta.get('memcard', 'off')}
    b = Replayer(rom=rom, game=None, options=opts, pack=pack)
    if hasattr(b.core, 'retro_neoscan_skip_render'): b.core.retro_neoscan_skip_render(1)   # no picture needed (the VPS core)
    S = pack['syms']; L = pack['layout']; FS = pack['fsize']; states = pack['states']; NFM = pack.get('nf_max', 8)
    pools = {f['id']: (f['name'], f['pool']) for f in pack['fighters']}
    hud = pack.get('chars') or []
    base = C.addressof(b.ram)
    def rd(addr, n): return C.string_at(base + addr - harness.RAM_BASE, n)
    def u8(a): return rd(a, 1)[0]
    def u16(a): return struct.unpack('>H', rd(a, 2))[0]
    # fighter fields: one read of the table per frame, unpacked with the pack's offsets
    want = [f for f in ('state', 'state_t', 'spec_id', 'spec_ix', 'sthr', 'fmax', 'throw_id', 'hp', 'hp_max', 'ch', 'team',
                        'drive', 'fgauge') if f in L]
    fmt = {f: '>' + {1: 'B', 2: 'H', 4: 'I'}[L[f][1]].lower() if f in ('hp', 'hp_max') else '>' + {1: 'B', 2: 'H', 4: 'I'}[L[f][1]] for f in want}
    offs = {f: L[f][0] for f in want}
    def fighters():
        blob = rd(S['fighters'], NFM * FS); out = []
        for i in range(NFM):
            o = i * FS; out.append({f: struct.unpack_from(fmt[f], blob, o + offs[f])[0] for f in want})
        return out
    sname = lambda s: states[s] if s < len(states) else str(s)
    def cname(ch):
        cid = (ch - S['bm_chars']) // S['sizeof_bchar'] if ch else -1
        return cid, (pools.get(cid, (None, []))[0] or (hud[cid].lower() if 0 <= cid < len(hud) else '?'))
    has = lambda k: k in S

    cs = chunks_of(session)
    events, screens, checked, mism, gaps, resync = [], [], 0, [], [], 0
    segs = []; seg = None; prev = None; scr = None; logged = 0; drift = True; last = None
    lastpad = [0, 0]; coins = starts = 0
    combo = {}; cont_prev = [0, 0]; lives_prev = [None, None]
    frames_by_mode = Counter(); attract_frames = 0; ending = False; gameovers = 0; continues = 0
    t0 = time.time()

    def close():
        nonlocal seg
        if seg is None: return
        if seg.bonus and has('bn_won') and seg.bn_won0 is not None:
            w = u8(S['bn_won']); g = u8(S['bn_game']) if has('bn_game') else None
            names = pack.get('bonus_games') or []
            seg.bonus_game = names[g] if g is not None and g < len(names) else ('game %d' % g if g is not None else None)
            seg.bonus_won = bool(g is not None and (w >> g & 1) and not (seg.bn_won0 >> g & 1))
            events.append({'ev': 'bonus_end', 'kind': seg.bonus_game, 'won': seg.bonus_won, 'f': seg.end, 'stage': seg.stage,
                           'wave': seg.wave, 'bonus': 1})
        segs.append(seg); seg = None

    for k, c in enumerate(cs):
        joined = last is not None and c['seq'] == last['seq'] + 1 and c['W'] == last['P']
        if not joined and last is not None: gaps.append(c['seq']); drift = True
        if joined and not drift and c['sha']:
            checked += 1
            if hashlib.sha256(b._save_core()).hexdigest() != c['sha']: mism.append(c['seq']); drift = True
        if drift:
            if not c['key']: last = c; continue                  # skipped up to the next keyframe
            b._load_core(gzip.decompress(open(c['key'], 'rb').read())); drift = False; resync += 1
            if c['sha'] and hashlib.sha256(b._save_core()).hexdigest() != c['sha']: raise SystemExit('keyframe sha mismatch')
            prev = None; close(); combo = {}
        for j in range(c['P'] - c['W']):
            frame = c['W'] + j; p0, p1 = c['pads'][2 * j], c['pads'][2 * j + 1]
            if p0 & 0x8000: b.core.retro_reset()
            pads = (p0 & 0x7FFF, p1)
            for i in (0, 1):                                    # coins (SELECT = libretro 2) and START (3), rising edges
                if pads[i] & 4 and not lastpad[i] & 4: coins += 1; events.append({'ev': 'coin', 'kind': 'coin', 'p': i, 'f': frame})
                if pads[i] & 8 and not lastpad[i] & 8: starts += 1
            lastpad = list(pads)
            b.raw = pads; b.core.retro_run(); logged += 1
            mode, camp, wave, phase, att = u8(S['mode']), u8(S['camp']), u8(S['wave']), u8(S['phase']), u8(S['attract'])
            lives = (u8(S['lives']), u8(S['lives'] + 1)); cont = (u16(S['cont_t']), u16(S['cont_t'] + 2))
            bon = u8(S['bonus_on']) if has('bonus_on') else 0
            sc = (mode, camp, wave, phase, att, lives[0], cont[0], bon)
            if sc != scr:
                screens.append({'f': frame, 'mode': MODE.get(mode, mode), 'stage': camp + 1, 'wave': wave + 1,
                                'phase': PHASE.get(phase, phase), 'attract': att, 'lives': lives[0], 'cont_t': cont[0], 'bonus': bon,
                                'lives2': lives[1]})
                if scr and mode == 5 and scr[0] != 5: gameovers += 1; events.append({'ev': 'gameover', 'kind': 'game over', 'f': frame, 'stage': camp + 1, 'wave': wave + 1})
                if mode == 4: ending = True
                scr = sc
            if att: attract_frames += 1
            else: frames_by_mode[MODE.get(mode, mode)] += 1
            if mode != 1 or att:
                prev = None; close(); combo = {}; cont_prev = [0, 0]; continue      # only the fights, never the attract demo
            key = (camp + 1, wave + 1, int(bon != 0))
            if seg is None or (seg.stage, seg.wave, seg.bonus) != key:
                close()
                if segs and (segs[-1].stage, segs[-1].wave, segs[-1].bonus) == key and frame - segs[-1].end < 600:
                    seg = segs.pop()                            # the same wave again after a short break (an overlay)
                else:
                    seg = Seg(key, frame, pack)
                    if bon and has('bn_won'): seg.bn_won0 = u8(S['bn_won'])
            seg.end = frame; seg.frames += 1; seg.phases[PHASE.get(phase, str(phase))] += 1
            fs = fighters()
            for i in (0, 1):                                    # continues: the count stopped with the lives back
                if cont_prev[i] and not cont[i]:
                    if lives[i] >= 2: continues += 1; events.append({'ev': 'continue', 'kind': 'continue', 'p': i, 'f': frame, 'stage': key[0], 'wave': key[1]})
                cont_prev[i] = cont[i]
            for i, s in enumerate(fs):
                p = prev[i] if prev else None
                st = sname(s['state']); pst = sname(p['state']) if p else None
                alive = s['ch'] and st not in ('OFF', 'PROJ')
                if i < 2:                                           # a player
                    if not s['ch'] or st == 'OFF': continue
                    d = seg.pl(i); cid, name = cname(s['ch']); d['fighter'] = name
                    hp = s['hp']
                    if not d['hp_start'] and hp > 0: d['hp_start'] = hp; d['lives_start'] = lives[i]   # (spawn frame: hp 0)
                    elif seg.frames < 30: d['lives_start'] = max(d['lives_start'] or 0, lives[i])   # (set a few frames in)
                    d['hp_end'] = hp; d['lives_end'] = lives[i]
                    if st != 'DEAD': d['in_play'] += 1
                    if pads[i] & PAD_PLAY or st == 'DEAD': d['_idle_run'] = 0
                    else:
                        d['_idle_run'] += 1
                        if d['_idle_run'] == IDLE_MIN: d['idle'] += IDLE_MIN
                        elif d['_idle_run'] > IDLE_MIN: d['idle'] += 1
                    if p is None or p['ch'] != s['ch']:
                        continue
                    if hp < p['hp']: d['dmg_taken'] += p['hp'] - hp; d['hits_taken'] += 1
                    if 'drive' in s:
                        dv = s['drive'] - p['drive']
                        if dv > 0: d['drive_gain'] += dv
                        elif dv < 0: d['drive_spent'] -= dv
                    if 'fgauge' in s:
                        dv = s['fgauge'] - p['fgauge']
                        if dv > 0: d['fury_gain'] += dv
                        elif dv < 0: d['fury_spent'] -= dv
                    pool = pools.get(cid, (None, []))[1]
                    ev = None
                    if st == 'SPECIAL' and (pst != 'SPECIAL' or s['spec_id'] != p['spec_id'] or s['spec_ix'] != p['spec_ix']
                                            or s['state_t'] < p['state_t']):
                        role = s['spec_id']
                        kind = 'MAX (d+D)' if role == 6 and s.get('fmax') else ROLE.get(role, role)
                        if s.get('sthr') == 2: kind = 'super throw (f/b+C in hold)'
                        elif s.get('sthr') == 1: kind = 'grab special'
                        inp = pool[s['spec_ix']] if s['spec_ix'] < len(pool) else '#%d' % s['spec_ix']
                        ev = {'ev': 'special', 'kind': kind, 'spec_ix': s['spec_ix'], 'input': inp, 'from': pst}
                        d['specials']['%s %s' % (kind, inp)] += 1
                        if role == 6: d['furies'] += 1
                    elif st == 'THROW' and pst != 'THROW':
                        t = s['throw_id']; kind = THROW.get(t, t)
                        if t == 4: kind = 'hold+B throw' if pads[i] & (1 << 8) else 'extra paired throw (u/d+A)'
                        if pst != 'GRAB': kind = 'chain/MAX-chain throw (' + kind + ')'
                        ev = {'ev': 'throw', 'kind': kind, 'from': pst}; d['throws'] += 1
                    elif st == 'GRAB' and pst != 'GRAB': ev = {'ev': 'grab', 'kind': 'grab (hold)', 'from': pst}; d['grabs'] += 1
                    elif st == 'DEAD' and pst != 'DEAD': ev = {'ev': 'death', 'kind': 'death', 'from': pst}; d['deaths'] += 1
                    if ev:
                        ev.update({'f': frame, 'p': i, 'char': name, 'stage': key[0], 'wave': key[1], 'bonus': key[2]})
                        events.append(ev)
                else:                                               # an enemy slot
                    if not alive or s['team'] != 1: combo.pop(i, None); continue
                    pal = p and p['ch'] == s['ch'] and sname(p['state']) not in ('OFF', 'PROJ')
                    if not pal or (sname(p['state']) == 'DEAD' and st != 'DEAD'):
                        if st != 'DEAD': seg.spawned[(hud[cname(s['ch'])[0]] if 0 <= cname(s['ch'])[0] < len(hud) else cname(s['ch'])[1])] += 1
                        combo.pop(i, None); continue
                    if s['hp'] < p['hp']:
                        seg.dealt += p['hp'] - s['hp']; seg.landed += 1
                        n = combo.get(i, 0) + 1 if sname(p['state']) in REACT or sname(p['state']) == 'DEAD' else 1
                        combo[i] = n; seg.max_combo = max(seg.max_combo, n)
                    elif st not in REACT and st != 'DEAD': combo.pop(i, None)
                    if st == 'DEAD' and sname(p['state']) != 'DEAD': seg.kills += 1
            prev = fs
        last = c
        if progress: progress(k + 1, len(cs))
    close()
    total = sum(c['P'] - c['W'] for c in cs)
    sg = [s.out() for s in segs]
    res = {'analyzer': ANALYZER, 'session': meta['session'], 'user': meta.get('user'), 'device': meta.get('device'),
           'rom_version': meta.get('rom_version'), 'rom_sha256': meta.get('rom_sha256'), 'pack_commit': pack.get('commit'),
           'chunks': len(cs), 'frames': total, 'frames_logged': logged, 'checked': checked, 'mismatches': mism, 'gaps': gaps,
           'resyncs': resync, 'cpu_s': round(time.process_time(), 1), 'wall_s': round(time.time() - t0, 1),
           'events': events, 'screens': screens, 'segments': sg}
    res['summary'] = summarize(res, pack, frames_by_mode, attract_frames, coins, starts, continues, gameovers, ending)
    return res


def summarize(res, pack, by_mode, attract, coins, starts, continues, gameovers, ending):
    sg = res['segments']; ev = res['events']
    fights = [s for s in sg if s['kind'] != 'bonus']
    fighters = []
    for s in sg:
        for p, d in s['players'].items():
            if d['fighter'] and d['fighter'] not in fighters: fighters.append(d['fighter'])
    rank = lambda s: (s['stage'], 1 if s['kind'] == 'boss' else 0, s['wave'])
    top = max(fights, key=rank) if fights else None
    fought = [s for s in fights if s['hits_landed'] or any(d['hits_taken'] for d in s['players'].values())]
    topf = max(fought, key=rank) if fought else None
    specials = Counter(); taken = dealt = deaths = furies = throws = grabs = idle = 0
    for s in sg:
        dealt += s['dmg_dealt']
        for d in s['players'].values():
            if s['kind'] != 'bonus': specials.update(d['specials'])
            taken += d['dmg_taken']; deaths += d['deaths']; furies += d['furies']; throws += d['throws']; grabs += d['grabs']; idle += d['idle']
    used_roles = {k.split(' ')[0] for k in specials} | {' '.join(k.split(' ')[:2]) for k in specials}
    unused = []
    for f in pack['fighters']:
        if f['name'] not in fighters: continue
        for slot, inp in (f.get('specials') or {}).items():
            role = SLOT_ROLE.get(slot)
            if role and inp and not any(k.startswith(role + ' ') for k in specials): unused.append('%s: %s %s' % (f['name'], role, inp))
        if not any(k.startswith('fury') or k.startswith('MAX') for k in specials): unused.append(f['name'] + ': fury (D)')
    last = sg[-1] if sg else None
    end = 'game over' if gameovers and res['screens'] and res['screens'][-1]['mode'] == 'game over' else \
          'ending' if ending else 'quit in a fight' if last and res['screens'] and res['screens'][-1]['mode'] == 'fight' else \
          'quit in the menus' if res['screens'] else 'no play'
    return {'seconds': round(res['frames'] / FPS, 1), 'fight_s': round(sum(s['frames'] for s in fights) / FPS, 1),
            'bonus_s': round(sum(s['frames'] for s in sg if s['kind'] == 'bonus') / FPS, 1),
            'menu_s': round((by_mode.get('select', 0) + by_mode.get('title', 0)) / FPS, 1), 'attract_s': round(attract / FPS, 1),
            'fighters': fighters,
            'furthest': {'stage': top['stage'], 'wave': top['wave'], 'kind': top['kind'], 'stage_name': top['stage_name']} if top else None,
            'furthest_fought': {'stage': topf['stage'], 'wave': topf['wave'], 'kind': topf['kind']} if topf else None,
            'deaths': deaths, 'continues': continues, 'gameovers': gameovers, 'coins': coins, 'starts': starts,
            'ending': ending, 'dmg_taken': taken, 'dmg_dealt': dealt, 'specials': sum(specials.values()), 'furies': furies,
            'throws': throws, 'grabs': grabs, 'idle_s': round(idle / FPS, 1), 'top_specials': dict(specials.most_common(12)),
            'unused': unused, 'segments': len(sg), 'end': end,
            'end_at': {'stage': last['stage'], 'wave': last['wave'], 'kind': last['kind']} if last else None,
            'kills': sum(s['kills'] for s in sg), 'max_combo': max([s['max_combo'] for s in sg] + [0]),
            'drift_ok': not res['mismatches']}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('session'); ap.add_argument('pack'); ap.add_argument('rom')
    ap.add_argument('--bios', default='/data/tmp/chainlab/site'); ap.add_argument('--out')
    ap.add_argument('--progress', help='a JSON file rewritten every 10 chunks: {session, done, total, at} (the worker)')
    a = ap.parse_args()
    sid = os.path.basename(os.path.normpath(a.session))
    def progress(done, total):
        if not a.progress or (done % 10 and done != total): return
        with open(a.progress + '.part', 'w') as f: json.dump({'session': sid, 'done': done, 'total': total, 'at': time.time()}, f)
        os.replace(a.progress + '.part', a.progress)
    res = analyze(a.session, json.load(open(a.pack)), a.rom, a.bios, progress)
    if a.out:
        data = json.dumps(res, separators=(',', ':')).encode()
        tmp = a.out + '.part'
        with (gzip.open(tmp, 'wb') if a.out.endswith('.gz') else open(tmp, 'wb')) as f: f.write(data)
        os.replace(tmp, a.out)
    print(json.dumps({k: v for k, v in res.items() if k not in ('events', 'screens', 'segments')}))


if __name__ == '__main__':
    main()
