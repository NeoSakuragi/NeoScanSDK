#!/usr/bin/env python3
"""Every roster fighter's voices (TODO #55, docs/brawler_data_model.md "Voices"): layer 0 of the voice data.

    python3 voices.py capture [NAME ...]   sound captures in our emulator (emu/neogeo_sdl --capture, WLOG on the sound
                                           mapper's word: index, object, driver word of every sound the game sends):
                                           every specials pass the bank has (capture/specials96.py tries, as captured)
                                           and an events pass (P1 hit twice, P1's two throws, P1 KO'd)
                                           -> /data/neogeo_dict/voices/cap/<game>/
    python3 voices.py list [NAME ...]      the listing: tools/brawler/voices.json + one WAV per voice
                                           (/data/neogeo_dict/voices/wav/<name>/<id>.wav)

Where a voice comes from (measured 2026-10-05):
- KOF96 / KOF98 / KOF99 send every sound through one mapper (KOF96 $6AA8, KOF98 $7A98, KOF99 $6352): d0 = a sound
  index, looked up in a word table (KOF96 $6CAD4, KOF98 $A9BCE, KOF99 $B1B5C) = driver prefix << 8 | code, stored in a
  scratch word (a5 + $5936 / $593C / $58F0 = $10D936 / $10D93C / $10D8F0) and queued. At that store d1 = the index and
  a4 = the object that asked (P1 = $108100). WLOG on the scratch word logs both.
- An animation asks with a $FC record (`FC 00 <index:16> 00 00`, before the step it starts with: static scan), a move's
  code asks directly (Terry's specials in KOF98, K''s in KOF99: only the capture sees those).
- The driver word: prefix = the effect slot (KOF98 $1A hits / swings, the fighters' voices $1B / $1C / $1D / $1E / $16,
  intro and win lines $17: each fighter its own slot, so teammates never cut each other), code = the slot's sample.
- The sample: each game's own driver run in the tap core (tools/makoto3/capture.py: our emulator's core with a Z80 port
  tap) with prefix + code sent and the game's own commands blocked: the ADPCM-A start / end registers it writes, every
  key-on of that channel until the sound ends (a looped record replays parts). The WAV = those V ROM bytes decoded
  (YM2610 ADPCM-A, 18518 Hz).
A voice = one sample (its segments); the indices that play it are listed with it. Sounds of prefix $1A (hits, swings,
fire) are effects, not voices; a sample several characters of the game use (the super flash...) is common, not listed."""
import json, os, struct, subprocess, sys, wave
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
CAPDIR = os.path.join(TOOLS, 'kof96', 'capture')
sys.path.insert(0, os.path.join(TOOLS, 'kof96')); sys.path.insert(0, os.path.join(TOOLS, 'kof95', 'capture'))
import rom96, export96
OUT = '/data/neogeo_dict/voices'
JSON = os.path.join(HERE, 'voices.json')
GAME_JSON = os.path.join(TOOLS, '..', 'examples', 'brawler', 'game.json')
MAPPER = {'kof96': 0x6CAD4, 'kof98': 0xA9BCE, 'kof99': 0xB1B5C}          # index -> driver word
SCRATCH = {'kof96': 0x10D936, 'kof98': 0x10D93C, 'kof99': 0x10D8F0}       # WLOG: the mapper's scratch word
BLOCK = {'kof96': 880, 'kof98': 412, 'kof99': 410, 'samsho4': 877, 'whp': 842, 'samsho2': 850}       # the driver probe: frame after the game's $07 (tap core frames)
CAST = {'kof96': export96.CAST, 'kof98': export96.CAST98, 'kof99': export96.CAST99}
P1 = 0x108100
FX_PREFIX = 0x1A
COMMON = {}                                                                # game -> driver words known common (below)
RATE = 18518                                                               # ADPCM-A: 8 MHz / 432

# ---- ADPCM-A (YM2610) ----
STEPS = [16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118, 130, 143, 157, 173,
         190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658, 724, 796, 876, 963, 1060, 1166, 1282, 1411,
         1552]
ADJ = [-1, -1, -1, -1, 2, 5, 7, 9]
def adpcm_a(data):
    """4-bit ADPCM-A (high nibble first) -> 16-bit PCM, the chip's 12-bit accumulator; every key-on starts from 0"""
    acc, ix, out = 0, 0, []
    for b in data:
        for n in (b >> 4, b & 15):
            d = ((n & 7) * 2 + 1) * STEPS[ix] >> 3
            acc = (acc - d if n & 8 else acc + d) & 0xFFF
            if acc & 0x800: acc -= 0x1000
            ix = min(48, max(0, ix + ADJ[n & 7]))
            out.append(acc << 4)
    return out

def neo(game): return rom96.GAMES[game]['neo'] if game in rom96.GAMES else f'/data/roms/{game}.neo'

def v_rom(game):
    d = open(neo(game), 'rb').read()
    h = struct.unpack('<6I', d[4:28]); o = 0x1000 + h[0] + h[1] + h[2]
    return d[o:o + h[3]]

def sample_bytes(v, segments):
    return b''.join(v[s << 8:(e + 1) << 8] for s, e in segments)

def write_wav(path, v, segments):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pcm = []
    for s, e in segments: pcm += adpcm_a(v[s << 8:(e + 1) << 8])
    with wave.open(path, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
        w.writeframes(struct.pack(f'<{len(pcm)}h', *pcm))
    return len(pcm) * 1000 // RATE

# ---- the roster ----
def roster(names=None):
    g = json.load(open(GAME_JSON))
    out = []
    for r in g['roster']:
        game, name = r['bank'].split(':')
        if names and r['name'] not in names: continue
        if game in MAPPER: out.append((r['name'], game, name, CAST[game].index(name)))
        elif game in OWN: out.append((r['name'], game, name, OWN[game]['cast'][name]))
    return out

_MEM = {}
def mem(game):
    if game not in _MEM:
        p, _ = rom96.load(rom96.GAMES[game]['neo']); _MEM[game] = rom96.Mem(p, game)
    return _MEM[game]

def slot_states(m, cid):
    k98 = m.game != 'kof96'
    mp = None if k98 else rom96.shared_map(m)
    inv = {}
    for st in range(512):
        try: inv.setdefault(rom96.state_slot(m, cid, st) if k98 else mp[st], []).append(st)
        except Exception: pass
    return inv

def fc_records(m, cid):
    """static scan: every $FC record of the character's animation table: (slot, step it precedes, index)"""
    base = m.u32(m.g['anims'] + cid * 4); out = []
    for slot in range(512):
        try:
            a = m.u32(base + slot * 4)
            if not 0x080000 <= a < 0x300000: continue
            n, recs = 0, []
            for i in range(300):
                b0 = m.u8(a + 6 * i)
                if b0 in (0xFF, 0xFE): break
                if b0 == 0xFC: recs.append((slot, n, m.u16(a + 6 * i + 2)))
                elif b0 < 0x80: n += 1
            else: continue
            out += recs
        except Exception: pass
    return out

def word(m, index): return m.u16(MAPPER[m.game] + 2 * index)

# ---- captures ----
def cap_dir(game): return os.path.join(OUT, 'cap', game)

def wlog(path):
    """[(frame, driver word, index, object)] from a WLOG of the mapper's scratch word"""
    out = []
    if not os.path.exists(path): return out
    for l in open(path):
        p = l.split()
        if '=' not in p[1]: continue
        f = int(p[0]); w = int(p[1].split('=')[1].split('/')[0], 16)
        reg = {x.split('=')[0]: int(x.split('=')[1], 16) for x in p[2:] if '=' in x}
        out.append((f, w, reg['d1'] & 0xFFFF, reg['a4'] & 0xFFFFFF))
    return drop_stops(out)

STOP = 0x0014
def drop_stops(W):
    """the plays of a WLOG: KOF96 / KOF98 / KOF99 cut a voice still sounding with the driver's $14 + its word (KOF98
    $1B03C sends $0014 then each word the move queued at +$1BC.. ; the driver's $14 handler $0F43 keys off the channel
    playing that prefix + code: measured in the tap core 2026-10-06, KOF96's driver the same), so the word an object sends
    right after its $0014 in the same frame is a STOP, not a play (TODO #163: Rugal's Kaiser Wave logged "Kaiser" twice)"""
    out = []
    for k, e in enumerate(W):
        if e[1] == STOP: continue
        if k and W[k - 1][1] == STOP and W[k - 1][0] == e[0] and W[k - 1][3] == e[3]: continue
        out.append(e)
    return out

def capture(names=None):
    sys.path.insert(0, CAPDIR)
    import importlib.util
    spec = importlib.util.spec_from_file_location('spcap', os.path.join(CAPDIR, 'specials96.py'))
    sc = importlib.util.module_from_spec(spec); sys.modules['spcap'] = sc; spec.loader.exec_module(sc)
    import emu
    orig = emu.run
    def run(game, out, *a, **k):
        k['extra'] = dict(k.get('extra') or {}, WLOG=f'{SCRATCH[game]:X}')
        return orig(game, out, *a, **k)
    emu.run = run
    for rname, game, name, cid in roster(names):
        if game in OWN: OWN[game]['capture'](rname, name, cid); continue
        m = mem(game); d = cap_dir(game); os.makedirs(d, exist_ok=True)
        canon = sc.outdir(m)
        sc.outdir = lambda m_, d=d: d
        for tag in ('', '_max', '_sdm', '_close', '_ex'):         # the passes the bank has, with their tries as captured
            src = os.path.join(canon, f'{cid}{tag}.json')
            if not os.path.exists(src): continue
            T = json.load(open(src))
            sc.run(cid, m, T, tag, close=tag == '_close', ex=tag == '_ex')
            print(rname, tag or 'main', len(T), 'tries', flush=True)
        sc.outdir = lambda m_, c=canon: c
        events(sc, emu, game, cid, d)
        print(rname, 'events', flush=True)

EVENTS = ['hit_c', 'hit_d', 'throw_c', 'throw_d', 'ko']
def events(sc, emu, game, cid, d):
    """P1 = the fighter, P2 next to it: P2's close C and close D hit it, its forward + C / D throws, then its KO (life 1,
    P2's C). KOF98 / KOF99: each try from the fighter's prepared state; KOF96: one run from 'vs' (P1 swapped in)."""
    from timeline import seqs
    T, spec, pokes, reload = [], [], [], []
    near = '108118=01,108119=80,108318=01,108319=B0'
    full = lambda: emu.life_pokes(game, 0x108100, emu.GAMES[game]['life_full'])
    s = 40 if game != 'kof96' else sc.START
    for k, ev in enumerate(EVENTS):
        T.append({'event': ev, 'start': s, 'gap': 200}); reload.append(s - 4)
        life = emu.life_pokes(game, 0x108100, 1) if ev == 'ko' else full()
        tm = f',{emu.GAMES[game]["timer"]:X}=59'
        pokes.append(f'{s - 2}:{near},{life}{tm}')
        if ev.startswith('hit') or ev == 'ko': spec.append(f'p2 {s + 10} 3 {"d" if ev == "hit_d" else "c"}')
        else: spec += [f'p1 {s + 4} 6 R', f'p1 {s + 10} 3 R{ev[-1]}']
        s += 200
    s1, s2 = seqs('; '.join(spec), s + 20)
    out = os.path.join(d, f'{cid}_events.txt')
    if game != 'kof96':
        sc.prep(game, cid)
        emu.run(game, out, s1, s2, pokes, reload=f'c{cid}', reload_frames=reload)
    else:
        pokes.insert(0, f'2:108238=0,108239=1,108250=0,108251=1,10A846={cid:02X},10A847={cid:02X},10A848={cid:02X}')
        s1, s2 = seqs('; '.join(['p2 20 60 L', 'p2 85 3 c'] + spec), s + 20)
        emu.run('kof96', out, s1, s2, pokes)
    json.dump(T, open(os.path.join(d, f'{cid}_events.json'), 'w'), indent=1)

# ---- the driver probe ----
def probe(game, words, frames=150):
    """{word: {'ch', 'level', 'segments': [[start, end], ...]}} the game's own driver playing prefix + code"""
    sys.path.insert(0, os.path.join(TOOLS, 'makoto3'))
    code = f'''
import sys, json
sys.path.insert(0, {os.path.join(TOOLS, 'makoto3')!r})
import capture as mk
class Log:
    def __init__(self): self.lines = []
    def write(self, t): self.lines += [l for l in t.split(chr(10)) if l]
s = mk.Sound(rom={neo(game)!r}, work={os.path.join(OUT, 'save_' + game)!r})
s.run({BLOCK[game]}); s.block = {BLOCK[game]}; s.run(20)
base = s.save(); out = {{}}
for w in {sorted(words)!r}:
    pre, cd = w >> 8, w & 255
    s.load(base); L = Log(); s.out = L; s._lastf = -1
    if pre: s.send(pre); s.run()
    s.send(cd); s.run({frames})
    reg, hit, sent = {{}}, None, False
    for l in L.lines:
        p = l.split()
        if p[0] == 'c' and int(p[1], 16) == cd: sent = True
        if p[0] != 'b' or not sent: continue
        r, v = int(p[1], 16), int(p[2], 16)
        if r == 0 and v & 0x80 and hit and v & (1 << hit['ch']): break
        if r == 0 and not v & 0x80 and v:
            ch = (v & -v).bit_length() - 1
            if hit is None: hit = {{'ch': ch, 'level': reg.get(8 + ch), 'segments': []}}
            if ch == hit['ch']:
                hit['segments'].append([reg.get(0x18 + ch, 0) << 8 | reg.get(0x10 + ch, 0), reg.get(0x28 + ch, 0) << 8 | reg.get(0x20 + ch, 0)])
        reg[r] = v
    out[w] = hit
print(json.dumps(out))
'''
    r = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    return {int(k): v for k, v in json.loads(r.stdout.strip().split('\n')[-1]).items()}

# ---- the listing ----
def specials_of(game, cid):
    """[(try, special entry or None, g0)]: the captured specials of the voices pass, by the bank's own rules (specials96.load)"""
    import specials96 as S, analyze as A
    m = mem(game); d = cap_dir(game); out = []
    seen, first_of = set(), {}
    for tag in ('', '_max', '_sdm', '_close', '_ex'):
        p = os.path.join(d, f'{cid}{tag}.txt')
        if not os.path.exists(p): continue
        T = json.load(open(os.path.join(d, f'{cid}{tag}.json')))
        es = S.load_file(m, cid, p, T, seen, tag, first_of)
        r1 = A.load(p, 1)
        for tr in T:
            s = tr['start']
            g0 = next((i for i in range(s, min(len(r1), s + 200)) if S.special_state(game, A.state_of(r1[i][3]))), None)
            e = next((e for e in es if e['cmd'] == tr['cmd'] and e['button'] == tr['button'] and g0 is not None
                      and e['state'] == A.state_of(r1[g0][3]) and e.get('_g0') is None), None)
            if e is not None: e['_g0'] = g0
            out.append((tag, tr, e, g0, wlog(p + '.wlog')))
    return out

def prog_sends(rname, game, m, cid):
    """[(input, [(via, index, word, detail)])]: the fighter's ROM specials (tools/kof96/handlers98.ROM_SPECIALS, and the
    MAX version of a DM) and the voice words their programs may send (handlers98.voice_sends)"""
    import handlers98 as H
    if H.ROM_GAME.get(rname, 'kof98') != game: return []
    out = []
    for inp in sorted(H.ROM_SPECIALS.get(rname, ())):
        ex = inp.startswith('EX '); seen = None
        for sdm in (False, True):
            try:
                h, b = H.handler_of(cid, inp, ex, m.game); prog = H.decode(m, h, b, ex, cid=cid, sdm=sdm)
            except Exception: continue
            ops = [op for a, op in prog['ops']]
            if ops == seen: continue                       # no MAX version (+$E4 bit 0 never tested)
            seen = ops
            out.append((('MAX ' if sdm else '') + inp, H.voice_sends(m, cid, prog)))
    return out

def build_list(names=None):
    old = json.load(open(JSON)) if os.path.exists(JSON) else {}
    res = {'about': __doc__.split('\n\n')[0], 'rate': RATE, 'fighters': dict(old.get('fighters', {}))}
    by_game = {}
    for rname, game, name, cid in roster(names): by_game.setdefault(game, []).append((rname, name, cid))
    for game, fs in by_game.items():
        if game in OWN:
            for rname, name, cid in fs: res['fighters'][rname] = OWN[game]['list'](rname, name, cid)
            continue
        m = mem(game); v = v_rom(game)
        # common words: the static scan of the whole cast (a word several characters' animations use)
        users = {}
        for c in range(len(CAST[game])):
            try: recs = fc_records(m, c)
            except Exception: continue
            for slot, step, ix in recs: users.setdefault(word(m, ix), set()).add(c)
        per = {}
        for rname, name, cid in fs:
            uses = []                                    # (word, index, use)
            inv = slot_states(m, cid)
            for slot, step, ix in fc_records(m, cid):
                uses.append((word(m, ix), ix, {'kind': 'anim', 'slot': slot, 'states': inv.get(slot, [])[:6], 'step': step}))
            for tag, tr, e, g0, W in specials_of(game, cid):
                if e is None or g0 is None: continue
                s = tr['start']; end = s + tr.get('gap', 220) - 4
                for f, w, ix, a4 in W:
                    if s <= f < end and a4 == P1 and f >= g0 - 2:
                        uses.append((w, ix, {'kind': 'special', 'input': e['input'], 'at': max(0, f - g0)}))   # (0 = its first frame, as the
                                                                    # other games' lists; was f - g0 + 1: a frame late, TODO #163)
            for inp, sends in prog_sends(rname, game, m, cid):   # the ROM specials' programs: every voice they may send
                for via, ix, w, det in sends:                         # (a hit-only path, a DM the captures missed: TODO #163)
                    u = {'kind': 'prog', 'input': inp, 'via': via}
                    if via == 'step': u.update(state=det[0], step=det[1])
                    elif via == 'later': u['later'] = det
                    uses.append((w, ix, u))
            evp = os.path.join(cap_dir(game), f'{cid}_events.txt')
            if os.path.exists(evp):
                W = wlog(evp + '.wlog')
                for tr in json.load(open(os.path.join(cap_dir(game), f'{cid}_events.json'))):
                    s = tr['start']
                    for f, w, ix, a4 in W:
                        if s <= f < s + tr['gap'] - 4 and a4 == P1:
                            uses.append((w, ix, {'kind': 'event', 'event': tr['event'], 'at': f - s}))
            per[rname] = (cid, uses)
        # a fighter's own effects (TODO #168): the $1A words its ROM specials' code sends (Goenitz's wind $1AD1 with
        # each Yonokaze tornado), listed as voices of channel 'fx' (played on the other voice slot: fighter.c voice_id)
        own_fx = {rname: {w for w, ix, u in us if w >> 8 == FX_PREFIX and u['kind'] == 'prog' and u['via'] in ('code', 'later')}
                  for rname, (cid, us) in per.items()}
        words = {w for rname, (cid, us) in per.items() for w, ix, u in us if w >> 8 != 0 and (w >> 8 != FX_PREFIX or w in own_fx[rname])}
        print(game, len(words), 'driver words to probe', flush=True)
        hits = probe(game, words)
        # a word several characters' animations use (3+ of the cast), or 3+ roster fighters' captures send, is common
        # (the super flash $1D11 / index $8A in KOF98...)
        sent = {}
        for rname, (cid, us) in per.items():
            for w, ix, u in us: sent.setdefault(w, set()).add(rname)
        for rname, name, cid in fs:
            cid, uses = per[rname]
            voices = {}
            for w, ix, u in uses:
                if w >> 8 == 0 or (w >> 8 == FX_PREFIX and w not in own_fx[rname]) or not hits.get(w): continue
                if len(users.get(w, set())) >= 3 or len(sent.get(w, ())) >= 3 or w in COMMON.get(game, ()): continue
                h = hits[w]; key = tuple(map(tuple, h['segments']))
                vo = voices.setdefault(key, {'cmd': f'{w:04X}', 'cmds': [], 'indices': [], 'segments': h['segments'],
                                             'level': h['level'], 'uses': []})
                if f'{w:04X}' not in vo['cmds']: vo['cmds'].append(f'{w:04X}')
                if ix not in vo['indices']: vo['indices'].append(ix)
                if u not in vo['uses']: vo['uses'].append(u)
            # a sample several fighters of the cast share by sample (rare): kept; ids by first index, the ids of the
            # list before kept (game.json / data packs name voices by id): new voices after them
            was = {tuple(map(tuple, vo['segments'])): vo['id'] for vo in old.get('fighters', {}).get(rname, {}).get('voices', [])}
            lst = sorted(voices.values(), key=lambda x: (was.get(tuple(map(tuple, x['segments'])), 1 << 20), min(x['indices']), x['cmd']))
            assert all(was.get(tuple(map(tuple, x['segments']))) in (None, k) for k, x in enumerate(lst, 1)), (rname, 'a voice of the list before is gone')
            for k, vo in enumerate(lst, 1):
                vo['id'] = k
                if int(vo['cmd'], 16) >> 8 == FX_PREFIX: vo['channel'] = 'fx'
                vo['bytes'] = len(sample_bytes(v, vo['segments']))
                vo['ms'] = write_wav(os.path.join(OUT, 'wav', rname, f'{k}.wav'), v, vo['segments'])
                vo['indices'] = [f'{i:03X}' for i in sorted(vo['indices'])]
                vo['cmds'].sort()
            res['fighters'][rname] = {'game': game, 'cid': cid, 'voices': [{k: vo[k] for k in (
                'id', 'cmd', 'cmds', 'indices', 'segments', 'level', 'bytes', 'ms', 'uses', 'channel') if k in vo} for vo in lst]}
            print(rname, len(lst), 'voices', sum(x['bytes'] for x in lst) // 1024, 'KB', flush=True)
    order = [r['name'] for r in json.load(open(GAME_JSON))['roster']]
    res['fighters'] = {k: res['fighters'][k] for k in order if k in res['fighters']}
    with open(JSON, 'w') as f:
        f.write('{"about": ' + json.dumps(res['about']) + ',\n "rate": ' + str(RATE) + ',\n "fighters": {\n')
        f.write(',\n'.join(f'  {json.dumps(n)}: {{"game": "{d["game"]}", "cid": {d["cid"]}, "voices": [\n' +
                           ',\n'.join('   ' + json.dumps(vo) for vo in d['voices']) + ']}' for n, d in res['fighters'].items()))
        f.write('\n }\n}\n')
    return res

# ---- Samurai Shodown IV (measured 2026-10-05, our emulator; SNK's driver Ver 1.0, tools/kof98snd) ----
# Every sound goes through $542C: d0 = [bit 15: only when +$4C is clear][bits 12-14: handler][bits 0-10: index]; handler
# 0 / 4 = $55A4 (4 also spawns an effect object), 2 / 6 = $5570 (the same, index + 0..2 by screen position: pan); the
# index -> long at $55DE + 4 * index = $00 prefix code $00 (prefix $00: a one-byte command), queued at $108EEC ($55D0,
# a4 = the object that asked) and sent from there. Senders: an animation step whose box word has bit 3 (the extra word
# = d0, tools/samsho4/ss4.py 'extra': static scan) and code (the normals' shout $1C81, the hit grunts $1C8A-$1C8C sent
# by the hit's effect object, the specials' lines: the capture sees those). Haohmaru's voices are prefix $1C (every
# voice word P1 sends in the captures). KO voice: not found (its life byte not located; the lab can map one).
SS4_TABLE = 0x55DE
SS4_PREFIX = 0x1C
def _ss4():
    sys.path.insert(0, os.path.join(TOOLS, 'samsho4')); import ss4, cap, capture_ss4, export_ss4
    return ss4, cap, capture_ss4, export_ss4

def ss4_word(index):
    m = _ss4()[0].m                                    # the study's ROM reader (the .neo stores P byte-swapped)
    return m.u8(SS4_TABLE + 4 * index + 1) << 8 | m.u8(SS4_TABLE + 4 * index + 2)

def ss4_capture(rname, name, cid):
    """every capture_ss4 recipe again with WLOG on the queue ($108EEC): (frame, driver word, object) of each sound
    queued, P1's [animation, step pointer] per frame -> OUT/cap/samsho4/<name>.json"""
    ss4, cap, C, _ = _ss4()
    from concurrent.futures import ThreadPoolExecutor
    def one(rec):
        mode, p2x, seq, seq2 = C.RECIPES[rec]
        pk = ';'.join(f'{f}:103A2E={p2x >> 8:02X},103A2F={p2x & 255:02X}' for f in range(cap.nframes(seq)))
        d = os.path.join(cap_dir('samsho4'), 'tmp', rec.replace(' ', '_'))
        rows = cap.run(seq, seq2, pokes=pk, load=cap.VS if mode == 'slash' else C.BUST, extra={'WLOG': '108EEC'}, keep=d)
        sent = []
        for l in open(os.path.join(d, 'cap.txt.wlog')):
            p = l.split(); r = dict(x.split('=') for x in p[2:] if '=' in x)
            if r.get('pc') == '0055D0' and p[1].startswith('108EEC'): sent.append((int(p[0]), int(r['d1'], 16) >> 16, int(r['a4'], 16)))
        return rec, {'sent': sent, 'p1': [[cap.u16(r['p1'], 0x22), cap.u32(r['p1'], 0x4E)] for r in rows]}
    with ThreadPoolExecutor(8) as ex: res = dict(ex.map(one, C.RECIPES))
    os.makedirs(cap_dir('samsho4'), exist_ok=True)
    json.dump(res, open(os.path.join(cap_dir('samsho4'), f'{name}.json'), 'w'))
    print(rname, len(res), 'recipes', sum(len(v['sent']) for v in res.values()), 'sounds', flush=True)

def ss4_list(rname, name, cid):
    """the fighter's voices: the static records of its animations + what the captures saw it (and its hits) send"""
    ss4, cap, C, E = _ss4()
    uses = []                                           # (word, sound index or None, use)
    for a in range(1840):
        try: st = ss4.steps_of(cid, a)
        except Exception: continue
        for k, x in enumerate(st):
            w = x.get('extra')
            if w is None or (w >> 12) & 1: continue     # handlers 1 / 3 / 5 / 7: not a sound
            ix = w & 0x7FF
            uses.append((ss4_word(ix), ix, {'kind': 'anim', 'slot': a, 'states': [a], 'step': k}))
    capd = json.load(open(os.path.join(cap_dir('samsho4'), f'{name}.json')))
    inputs = {rec: inp for inp, (rec, anims) in E.SPECIALS.items()}
    P1 = 0x103600
    for rec, d in capd.items():
        p1 = d['p1']                                    # row i = frame i + 1; a write in frame n is logged as n - 1
        inp = inputs.get(rec)
        g0 = next((i for i, (a, _) in enumerate(p1) if a == E.SPECIALS[inp][1][0]), None) if inp else None
        for f, w, a4 in d['sent']:
            if w >> 8 != SS4_PREFIX: continue
            if a4 != P1:                                # a hit's effect object: the victim's grunt
                if rec in ('react_light', 'react_heavy'): uses.append((w, None, {'kind': 'event', 'event': 'hit_c', 'at': 0}))
                continue
            if inp and g0 is not None and f >= g0: uses.append((w, None, {'kind': 'special', 'input': inp, 'at': f - g0}))
            elif not inp and f < len(p1):
                a, ptr = p1[f]; k = ss4.step_index(cid, a, ptr)
                uses.append((w, None, {'kind': 'anim', 'slot': a, 'states': [a], 'step': max(0, (k or 1) - 1)}))
    words = {w for w, ix, u in uses if w >> 8 == SS4_PREFIX}
    hits = probe('samsho4', words); v = v_rom('samsho4')
    voices = {}
    for w, ix, u in uses:
        if w >> 8 != SS4_PREFIX or not hits.get(w): continue
        h = hits[w]; key = tuple(map(tuple, h['segments']))
        vo = voices.setdefault(key, {'cmd': f'{w:04X}', 'cmds': [], 'indices': [], 'segments': h['segments'], 'level': h['level'], 'uses': []})
        if f'{w:04X}' not in vo['cmds']: vo['cmds'].append(f'{w:04X}')
        if ix is not None and ix not in vo['indices']: vo['indices'].append(ix)
        if u not in vo['uses']: vo['uses'].append(u)
    lst = sorted(voices.values(), key=lambda x: x['cmd'])
    for k, vo in enumerate(lst, 1):
        vo['id'] = k; vo['bytes'] = len(sample_bytes(v, vo['segments']))
        vo['ms'] = write_wav(os.path.join(OUT, 'wav', rname, f'{k}.wav'), v, vo['segments'])
        vo['indices'] = [f'{i:03X}' for i in sorted(vo['indices'])]; vo['cmds'].sort()
    print(rname, len(lst), 'voices', sum(x['bytes'] for x in lst) // 1024, 'KB', flush=True)
    return {'game': 'samsho4', 'cid': cid, 'voices': [{k: vo[k] for k in ('id', 'cmd', 'cmds', 'indices', 'segments', 'level',
                                                                          'bytes', 'ms', 'uses')} for vo in lst]}

# ---- World Heroes Perfect (ADK's driver, not decoded; measured 2026-10-05 in our emulator) ----
# The game writes REG_SOUND from one place ($9CCA): one byte a sound, or $FC + a byte (a second page: $FC $A9 plays
# another sample than $A9 alone). No sound record in the animation steps (no step command carries one): every voice is
# sent by code, so the listing is the captures' (capture_whp recipes Hanzou plays alone: normals, jumps, specials as
# whiffs; SNDLOG). Its own driver in the tap core (probe, block after the boot's $FF) keys ADPCM-A channel 3 for the
# shouts and channel 5 for swings / hits: a voice = a word whose sample plays on channel 3. Not found: the hit / KO
# grunts (the reaction captures show only the attacker's sounds), intro / win lines (not captured).
WHP_VOICE_CH = 3
def _whp():
    sys.path.insert(0, os.path.join(TOOLS, 'whp')); import cap_whp, capture_whp, export_whp
    return cap_whp, capture_whp, export_whp

def whp_capture(rname, name, cid):
    cap, C, _ = _whp()
    from concurrent.futures import ThreadPoolExecutor
    def one(rec):
        p2x, seq, seq2 = C.RECIPES[rec]
        n = cap.nframes(seq)
        pk = ';'.join(f'{f}:100102={p2x * 128 >> 8 & 255:02X},100103={p2x * 128 & 255:02X}' for f in range(n)) if p2x else None
        d = os.path.join(cap_dir('whp'), 'tmp', rec); os.makedirs(d, exist_ok=True)
        env = dict(os.environ, SEQ=seq, SEQ2=seq2, OUT=os.path.join(d, 'cap.txt'), LOAD=cap.VS, SNDLOG=os.path.join(d, 'snd.txt'))
        if pk: env['POKE'] = pk
        subprocess.run([cap.NGSDL, cap.NEO, '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=600)
        return rec, [[int(l.split()[0]), int(l.split()[1], 16)] for l in open(os.path.join(d, 'snd.txt'))]
    recs = [k for k, (p2x, seq, seq2) in C.RECIPES.items() if not k.startswith('react')]
    with ThreadPoolExecutor(8) as ex: res = dict(ex.map(one, recs))
    json.dump(res, open(os.path.join(cap_dir('whp'), f'{name}.json'), 'w'))
    print(rname, len(res), 'recipes', sum(len(v) for v in res.values()), 'sound bytes', flush=True)

def whp_cast_users(nchars=16, nanims=0x140):
    """{word: {character}}: the step sound records (command 4) of every animation of WHP's cast (a word 3+ characters'
    animations send is common: the landing $51, the swings $0A / $0B, the projectile's launch $65)"""
    sys.path.insert(0, os.path.join(TOOLS, 'whp')); import handlers_whp as H
    users = {}
    for c in range(nchars):
        for a in range(nanims):
            try: es = H.entries(c, a)
            except Exception: continue
            for e in es:
                for k, x in e.get('cmds') or []:
                    if k == 4: users.setdefault(int(x, 16), set()).add(c)
    return users

def whp_special_uses(name):
    """the exported specials' own sends (TODO #181): WHP's step command 4 (a sound word) of every step each special's
    rows enter, read from the export (export_whp: the steps a program plays, the script rows of a scripted one). A
    program special (one per input, its rows = low / mid / high): {'kind': 'prog', 'via': 'step', 'state': the row's
    animation, 'step': the step index, 'row'}, sent as the program enters the step (bchar_t.pvox); a scripted one (the
    fury, its MAX): {'kind': 'special', 'at': the script row where the step starts}"""
    import tempfile, handlers_whp as H
    _, _, E = _whp()
    with tempfile.TemporaryDirectory(dir='/data/tmp') as d:
        ch = E.export([name], d)['characters'][name]
    uses = []
    for sp in ch['specials']:
        inp, r = sp['input'], sp.get('rom') or {}
        if r.get('prims'):
            for v, st in enumerate(r['states']):
                for i, s_ in enumerate(r['anims'][st]['steps']):
                    for w in s_.get('voices', []):
                        uses.append((w, {'kind': 'prog', 'input': inp, 'via': 'step', 'state': int(st.split(':')[1], 16), 'step': i, 'row': v}))
            continue
        prev = None
        for i, rs in enumerate(sp['row_steps']):
            k = (rs[0], rs[1])
            if k != prev:
                e = H.entries(H.CHARS[name], rs[0])[rs[1]]
                for c, x in e.get('cmds') or []:
                    if c == 4: uses.append((int(x, 16), {'kind': 'special', 'input': inp, 'at': i}))
            prev = k
    return uses

def whp_list(rname, name, cid):
    """the voices: the captures' sends by animation step (normals, jumps: the brawler's moves by slot), the specials'
    own step sends (whp_special_uses: every row of every exported special, the fury and its MAX; what the captures sent
    in a special's animation ($100 up) is not used, it holds the victim's cries too). A word on channel 3 = a voice; a word on channel 5
    one of his specials sends that fewer than 3 of the cast's animations send = his own effect (channel 'fx', TODO
    #168's rule: the MAX's $39 / $62); the common ones (landing, swings, the launch $65) are not listed"""
    cap, C, E = _whp()
    capd = json.load(open(os.path.join(cap_dir('whp'), f'{name}.json')))
    frames = json.load(open(E.CAPTURE))
    uses = []
    for rec, sent in capd.items():
        words, k = [], 0
        while k < len(sent):                               # $FC + the next byte = one word
            f, b = sent[k]
            if b == 0xFC and k + 1 < len(sent): words.append((f, 0xFC00 | sent[k + 1][1])); k += 2
            else: words.append((f, b)); k += 1
        p1 = [fr[0] for fr in frames[rec]['frames']]       # row i = frame i + 1; a write in frame n is logged as n - 1
        for f, w in words:
            if f < len(p1) and p1[f][0] < 0x100:           # (a special's animation, $100 up: its steps', below)
                uses.append((w, {'kind': 'anim', 'slot': p1[f][0], 'states': [p1[f][0]], 'step': p1[f][1]}))
    spu = whp_special_uses(name); uses += spu
    users = whp_cast_users()
    own_fx = {w for w, u in spu if len(users.get(w, ())) < 3}
    hits = probe('whp', {w for w, u in uses}); v = v_rom('whp')
    voices = {}
    for w, u in uses:
        h = hits.get(w)
        if not h or not (h['ch'] == WHP_VOICE_CH or w in own_fx): continue
        key = tuple(map(tuple, h['segments']))
        vo = voices.setdefault(key, {'cmd': f'{w:04X}', 'cmds': [], 'indices': [], 'segments': h['segments'], 'level': h['level'], 'uses': []})
        if h['ch'] != WHP_VOICE_CH: vo['channel'] = 'fx'
        if f'{w:04X}' not in vo['cmds']: vo['cmds'].append(f'{w:04X}')
        if u not in vo['uses']: vo['uses'].append(u)
    lst = sorted(voices.values(), key=lambda x: ('channel' in x, x['cmd']))   # his voices, then his effects: a step that
    for k, vo in enumerate(lst, 1):                                           # sends both plays the voice first (the
        vo['id'] = k; vo['bytes'] = len(sample_bytes(v, vo['segments']))      # MAX's $FCA8 $39: voices.extras' order)
        vo['ms'] = write_wav(os.path.join(OUT, 'wav', rname, f'{k}.wav'), v, vo['segments']); vo['cmds'].sort()
    print(rname, len(lst), 'voices', sum(x['bytes'] for x in lst) // 1024, 'KB', flush=True)
    return {'game': 'whp', 'cid': cid, 'voices': [{k: vo[k] for k in ('id', 'cmd', 'cmds', 'indices', 'segments', 'level',
                                                                      'bytes', 'ms', 'uses', 'channel') if k in vo} for vo in lst]}

# ---- Kizuna Encounter (Kim): its sounds are already captured with every move (tools/kizuna: capture_kz.py ->
# kim_capture.json, followups_kz.py -> kim_followups.json: the bytes written to REG_SOUND each frame) and each word's
# sample found by Kizuna's own driver (SNK Ver 0.0) in the tap core (voices_kz.py -> kim_voices.json: segments, level).
# Uses: a move = Kim's animation + step the frame a word was sent; a special = the script row it was sent on
# (export_kz.special_sounds: the rows the export plays, multipart moves included); hit / KO = his reaction captures.
# Voices: his voice samples (prefix $1C, his slot, codes $B0 up: $1CB0-$1CD2 yells, hit, KO), and an effect only one
# special sends (prefix $1A: [2]8C's $1A67, the Phoenix's cry $1A68, Kizuna plays it with the launch), listed first:
# a special's own effect is its sound (voices.py suggest takes a key's first voice in list order). ----
KZ_EVENTS = {'react_a': 'hit_c', 'react_b': 'hit_d', 'react_ko': 'ko'}
def _kz():
    sys.path.insert(0, os.path.join(TOOLS, 'kizuna')); import export_kz, voices_kz
    return export_kz, voices_kz

def kizuna_capture(rname, name, cid):
    print(rname, ': Kizuna captures are tools/kizuna/capture_kz.py, followups_kz.py, voices_kz.py', flush=True)

def kizuna_list(rname, name, cid):
    E, VK = _kz()
    cap = json.load(open(E.CAPTURE)); fc = json.load(open(E.FOLLOWUPS)); snd = json.load(open(VK.OUT))['sounds']
    uses = []                                              # (word, use)
    spw = {}                                               # word -> the specials that send it
    for inp in E.SPECIALS:
        for row, w in E.special_sounds(inp, cap, fc):
            uses.append((w, {'kind': 'special', 'input': inp, 'at': row})); spw.setdefault(w, set()).add(inp)
    for rec, d in cap.items():
        for f, w in VK.words_of(d['frames']):
            if rec in KZ_EVENTS: uses.append((w, {'kind': 'event', 'event': KZ_EVENTS[rec], 'at': 0}))
            else: p = d['frames'][f][0]; uses.append((w, {'kind': 'anim', 'slot': p[0], 'states': [p[0]], 'step': p[1]}))
    own_fx = {w for w, s in spw.items() if w >> 8 == FX_PREFIX and len(s) == 1}
    def is_voice(w): return (w >> 8 == 0x1C and w & 0xFF >= 0xB0) or w in own_fx
    v = v_rom('kizuna'); voices = {}
    for w, u in uses:
        if not is_voice(w) or f'{w:04X}' not in snd or 'segments' not in snd[f'{w:04X}']: continue
        e = snd[f'{w:04X}']
        vo = voices.setdefault(w, {'cmd': f'{w:04X}', 'cmds': [f'{w:04X}'], 'indices': [], 'segments': e['segments'], 'level': e['level'], 'uses': []})
        if u not in vo['uses']: vo['uses'].append(u)
    lst = [voices[w] for w in sorted(voices, key=lambda w: (w not in own_fx, w))]
    for k, vo in enumerate(lst, 1):
        vo['id'] = k; vo['bytes'] = len(sample_bytes(v, vo['segments']))
        vo['ms'] = write_wav(os.path.join(OUT, 'wav', rname, f'{k}.wav'), v, vo['segments'])
    print(rname, len(lst), 'voices', sum(x['bytes'] for x in lst) // 1024, 'KB', flush=True)
    for vo in lst:                                         # an effect (not his voice slot): Kizuna plays it on its
        if int(vo['cmd'], 16) in own_fx: vo['channel'] = 'fx'   # effects channel, over his voice (the Phoenix's cry
    return {'game': 'kizuna', 'cid': cid, 'voices': [{k: vo[k] for k in ('id', 'cmd', 'cmds', 'indices', 'segments', 'level',   # with $1CD2)
                                                                        'bytes', 'ms', 'uses', 'channel') if k in vo} for vo in lst]}

# ---- Double Dragon (Technos 1995, Billy Lee and his transformed form): every sound is a step's sound byte (the
# animation sends it on the step's first frame, model_dd; no code-sent voices among Billy's moves), so the listing is
# static: uses = the animations' steps, the specials' rows (the default row as the brawler plays it: export_dd's
# script), the hit (pain $1C) and KO ($23, the fall) events; the sample = what DD's own driver keys on (tools/ngss model:
# the ADPCM-A start / end and level registers of the command). Voices = Billy's range $1C-$2C (the sound test's map);
# the effects only his specials send ($C2 / $C3 / $D5, the 236 / 623 / super effects) as 'fx' (over his voice).
DD_VOICES, DD_FX = range(0x1C, 0x2D), (0xC2, 0xC3, 0xD5)
def doubledr_capture(rname, name, cid):
    print(rname, ': Double Dragon sounds are step data (static scan, voices.py list)', flush=True)

def dd_sample(cmd):
    sys.path.insert(0, os.path.join(TOOLS, 'ngss')); import song_ngss
    m1 = open('/data/neogeo_dict/sound/doubledr/doubledr_m1.bin', 'rb').read()
    w = [x for x in song_ngss.Song(m1, cmd).run(600).writes if x[1] == 'b']
    on = next(x for x in w if x[2] == 0 and not x[3] & 0x80)          # the key-on: its channel
    c = next(k for k in range(6) if on[3] >> k & 1)
    reg = {x[2]: x[3] for x in w[:w.index(on)]}
    st = reg[0x18 + c] << 8 | reg[0x10 + c]; en = reg[0x28 + c] << 8 | reg[0x20 + c]
    lvl = next(x[3] for x in w if x[2] == 0x08 + c)
    return [[st, en]], lvl

def doubledr_list(rname, name, cid):
    sys.path.insert(0, os.path.join(TOOLS, 'doubledr')); import dd, model_dd as M, export_dd as E
    uses = []
    for n in range(dd.anim_count(cid)):
        try: _, st = dd.steps(cid, n)
        except Exception: continue
        for k, s_ in enumerate(st):
            if s_['b5']: uses.append((s_['b5'], {'kind': 'anim', 'slot': n, 'states': [n], 'step': k}))
    for inp, (anims, _) in E.SPECIALS[cid].items():
        for i, r in enumerate(M.play(cid, anims[-1], limit=400)):
            if r['snd']: uses.append((r['snd'], {'kind': 'special', 'input': inp, 'at': i}))
    uses += [(0x1C, {'kind': 'event', 'event': 'hit_c', 'at': 0}), (0x1D, {'kind': 'event', 'event': 'ko', 'at': 0})]
    for w in (0x22, 0x24, 0x26, 0x28):             # Billy's special shouts in both forms' lists (one voice actor: the
        uses.append((w, None))                     # transformed form may share them, game.json voices.set)
    spw = {}
    for w, u in uses:
        if u and u['kind'] == 'special': spw.setdefault(w, set()).add(u['input'])
    own_fx = {w for w in DD_FX if w in spw}
    v = v_rom('doubledr'); voices = {}
    for w, u in uses:
        if w not in DD_VOICES and w not in own_fx: continue
        if w not in voices:
            seg, lvl = dd_sample(w)
            voices[w] = {'cmd': f'{w:04X}', 'cmds': [f'{w:04X}'], 'indices': [], 'segments': seg, 'level': lvl, 'uses': []}
        if u and u not in voices[w]['uses']: voices[w]['uses'].append(u)
    lst = [voices[w] for w in sorted(voices, key=lambda w: (w not in own_fx, w))]
    for k, vo in enumerate(lst, 1):
        vo['id'] = k; vo['bytes'] = len(sample_bytes(v, vo['segments']))
        vo['ms'] = write_wav(os.path.join(OUT, 'wav', rname, f'{k}.wav'), v, vo['segments'])
        if int(vo['cmd'], 16) in own_fx: vo['channel'] = 'fx'
    print(rname, len(lst), 'voices', sum(x['bytes'] for x in lst) // 1024, 'KB', flush=True)
    return {'game': 'doubledr', 'cid': cid, 'voices': [{k: vo[k] for k in ('id', 'cmd', 'cmds', 'indices', 'segments', 'level',
                                                                          'bytes', 'ms', 'uses', 'channel') if k in vo} for vo in lst]}

# ---- Samurai Shodown II (MAKOTO Ver 3.0, tools/makoto3; read in the code 2026-10-06, tools/samsho2) ----
# A sound = a 10-bit id -> word $5FD2[id] = [prefix][code] queued at $107000 and sent by $5F5E ($5FB0); a step's $08
# command sends its id on the step's first frame, $0C the panned one (id, id + 1, id + 2 by screen x: the middle id + 1
# here). Ids $000-$0FF are the game's common effects (swings, hits; but a routine's own send with its move: Kuroko's
# parody shouts $AC-$AF, $DE), $100 and up each fighter's own (Haohmaru $100-$116,
# Genjuro $200-$218): the listing takes those, from every animation of the fighter (uses 'anim') and from the specials
# as the brawler plays them (handlers_ss2: the frame each step starts, uses 'special'). An action entry's voice index
# (descriptor word bit 14, $27A00: ids $200 + the pair at $27A4C[char]) sends prefix $15 words for Haohmaru (his
# shouts' list): the driver plays nothing for them (measured: the game itself sends $15 $90 at Senpuu Retsu Zan's
# step 11 and no ADPCM write follows, in the tap core from the fight state), so they are left out. A word's sample:
# its own driver in the tap core (probe, after the boot's $07); prefix $1C = the fighter's voice slot, $18 / $1A =
# effect slots (channel 'fx': played on the other voice slot so they do not cut his voice).
SS2_FX = (0x18, 0x1A)
def _ss2():
    sys.path.insert(0, os.path.join(TOOLS, 'samsho2')); import ss2, neo2, handlers_ss2, export_ss2
    return ss2, neo2, handlers_ss2, export_ss2

def ss2_word(N, i): return N.u16(0x5FD2 + 2 * i)

def samsho2_capture(rname, name, cid):
    print(rname, ': Samurai Shodown II sounds are step data and the specials\' plays (voices.py list)', flush=True)

def samsho2_list(rname, name, cid):
    ss2, N, H, X = _ss2()
    uses = []
    for a in range(ss2.n_anims(cid)):
        try: st = ss2.parse_anim(cid, a, 400)
        except Exception: continue
        for k, x in enumerate(st):
            for c in x['cmds']:
                if c[0] not in ('sound', 'sound_pan'): continue
                i = c[1] + (1 if c[0] == 'sound_pan' else 0)
                if i >= 0x100: uses.append((ss2_word(N, i), i, {'kind': 'anim', 'slot': a, 'states': [a], 'step': k}))
    B = X.Builder(cid)
    for sp in H.specials(B, cid, name):
        for f, i in sp['ss2']['sounds']:
            if i >= 0x100 or i in sp['ss2'].get('code_sounds', ()): uses.append((ss2_word(N, i), i, {'kind': 'special', 'input': sp['input'], 'at': f}))
    words = {w for w, i, u in uses}
    hits = probe('samsho2', words); v = v_rom('samsho2')
    voices = {}
    for w, i, u in uses:
        if not hits.get(w): continue
        h = hits[w]; key = tuple(map(tuple, h['segments']))
        vo = voices.setdefault(key, {'cmd': f'{w:04X}', 'cmds': [], 'indices': [], 'segments': h['segments'], 'level': h['level'], 'uses': []})
        if f'{w:04X}' not in vo['cmds']: vo['cmds'].append(f'{w:04X}')
        if i not in vo['indices']: vo['indices'].append(i)
        if u not in vo['uses']: vo['uses'].append(u)
    lst = sorted(voices.values(), key=lambda x: (int(x['cmd'], 16) >> 8 in SS2_FX, x['cmd']))
    for k, vo in enumerate(lst, 1):
        vo['id'] = k; vo['bytes'] = len(sample_bytes(v, vo['segments']))
        vo['ms'] = write_wav(os.path.join(OUT, 'wav', rname, f'{k}.wav'), v, vo['segments'])
        vo['indices'] = [f'{x:03X}' for x in sorted(vo['indices'])]; vo['cmds'].sort()
        if int(vo['cmd'], 16) >> 8 in SS2_FX: vo['channel'] = 'fx'
    print(rname, len(lst), 'voices', sum(x['bytes'] for x in lst) // 1024, 'KB', flush=True)
    return {'game': 'samsho2', 'cid': cid, 'voices': [{k: vo[k] for k in ('id', 'cmd', 'cmds', 'indices', 'segments', 'level',
                                                                          'bytes', 'ms', 'uses', 'channel') if k in vo} for vo in lst]}

OWN = {'samsho4': {'cast': {'haohmaru': 0}, 'capture': ss4_capture, 'list': ss4_list},
       'doubledr': {'cast': {'billy': 0, 'billy_super': 1}, 'capture': doubledr_capture, 'list': doubledr_list},
       'whp': {'cast': {'hanzo': 0}, 'capture': whp_capture, 'list': whp_list},
       'kizuna': {'cast': {'kim': 5}, 'capture': kizuna_capture, 'list': kizuna_list},
       'samsho2': {'cast': {'haohmaru': 0, 'genjuro': 12, 'kuroko': 17}, 'capture': samsho2_capture, 'list': samsho2_list}}

# ---- the brawler side (export_bm.py, build_snd.py, build_tables.py, the lab) ----
# A fighter's voice table (bchar_t.voices, fighter.c voice_tab): one entry per voice key, 2 bytes [voice id, at]; id = the
# fighter's voice (voices.json, 1-based; 0 = silent), at = where in the move it starts: the animation step (KOF's $FC
# record precedes it), the special's script row (as played: frozen rows dropped), the throw's row; events at once.
# Keys: every brawler animation (BA_*), the throws (BT_*), the events, then the fighter's specials pool by input.
EVENT_KEYS = ['hit', 'ko', 'select']
INTRO = {'kof96': range(208, 240), 'kof98': range(348, 355), 'kof99': range(348, 355),
         'samsho4': [*range(119, 127), *range(129, 140), *range(141, 150)], 'whp': [0, 1, *range(32, 64)], 'kizuna': [], 'doubledr': [],
         'samsho2': [*range(142, 150)]}   # SS4 / WHP: the pose animations (char_images); SS2: the intro / taunt poses after the win 140

def keys(moves, throws, pool_inputs):
    return list(moves) + list(throws) + EVENT_KEYS + ['special:' + i for i in pool_inputs]

def bank(name):
    """the fighter's voice list (voices.json), [] when it has none"""
    return _bank().get(name, {}).get('voices', [])
_BANK = None
def _bank():
    global _BANK
    if _BANK is None: _BANK = json.load(open(JSON))['fighters'] if os.path.exists(JSON) else {}
    return _BANK

def suggest(name, game, slot_of, throw_rows, pool):
    """KOF's own voice per key: {key: [id, at]}. slot_of: brawler move -> its KOF animation slot (and its step count);
    throw_rows: throw key -> (KOF slot, [the thrower's KOF step index shown on each row]); pool: [(input, keep rows)]"""
    vs = bank(name); out = {}
    def first(pred):
        for vo in vs:
            for u in vo['uses']:
                r = pred(u)
                if r is not None: return vo['id'], r
        return None
    for m, v in slot_of.items():
        for slot, off, nsteps in parts_of(v):          # an animation made of several (the win: KOF's 336 + 337)
            f = first(lambda u: off + min(u['step'], nsteps - 1) if u['kind'] == 'anim' and u['slot'] == slot else None)
            if f: out[m] = list(f); break
    for t, (slot, steps) in throw_rows.items():         # the throw's animation record, else what its capture sent
        f = first(lambda u: next((i for i, k in enumerate(steps) if k >= u['step']), 0) if u['kind'] == 'anim' and u['slot'] == slot else None) \
            or first(lambda u: 0 if u['kind'] == 'event' and u['event'] == t else None)
        if f: out[t] = list(f)
    for ev, src in (('hit', ('hit_c', 'hit_d')), ('ko', ('ko',))):
        f = first(lambda u: 0 if u['kind'] == 'event' and u['event'] in src else None)
        if f: out[ev] = list(f)
    win = parts_of(slot_of['win'])[0][0] if 'win' in slot_of else None
    f = first(lambda u: 0 if u['kind'] == 'anim' and u['slot'] != win and any(s in INTRO[game] for s in u['states']) else None)
    if f: out['select'] = list(f)
    for inp, keep in pool:
        f = first(lambda u: sum(1 for i in keep if i < u['at']) if u['kind'] == 'special' and u['input'] == inp else None)
        if f: out['special:' + inp] = list(f)
    return out

def parts_of(v):
    """slot_of's value -> [(slot, first step, steps)]: (slot, steps), or ('parts', [[slot, first step, steps], ...])"""
    return [tuple(p) for p in v[1]] if v[0] == 'parts' else [(v[0], 0, v[1])]

def anim_extras(name, ks, sug, mp, key, v):
    """a move's other voices (TODO #184: the win pose: Iori's three shouts in KOF98's 336): every voice its animation
    steps send besides the key's first (suggest), [key index, voice id, at = step], where the roster keeps the suggestion"""
    if key not in sug or mp.get(key) != sug[key][0]: return []
    out, seen = [], {tuple(sug[key])}
    for slot, off, nsteps in parts_of(v):
        for vo in bank(name):
            for u in vo['uses']:
                if u['kind'] != 'anim' or u['slot'] != slot: continue
                e = (vo['id'], off + min(u['step'], nsteps - 1))
                if e not in seen: seen.add(e); out.append([ks.index(key), e[0] | fx_bit(name, e[0]), e[1]])
    return out

def mapping(field, sug):
    """game.json roster[].voices -> {key: id}: absent / null = no voices; "kof" = KOF's own on every move (the suggestion);
    {"kof": true|false, "set": {key: id | null}} = that base with these keys changed (null: silent)"""
    if not field: return {}
    if field == 'kof': return {k: v[0] for k, v in sug.items()}
    out = {k: v[0] for k, v in sug.items()} if field.get('kof', True) else {}
    for k, v in field.get('set', {}).items():
        if v: out[k] = v
        else: out.pop(k, None)
    return out

def extras(name, ks, sug, mp, pool):
    """a special's other voices: the source game sends several in one move (Kizuna: the Phoenix's shouts $1CD1 / $1CD2
    besides its cry, 236C's yell per part, [2]8C's shout before its effect); the table's [id, at] holds the key's first
    (suggest), these the rest: [key index, voice id, at] (at = the script row as played), sorted. Only where the roster
    keeps the suggestion for that key (a picked or silenced key plays what it was given). bchar_t.vmore, fighter.c voice_at"""
    out = []
    for inp, keep in pool:
        k = 'special:' + inp
        if k not in sug or mp.get(k) != sug[k][0]: continue
        seen = {tuple(sug[k])}
        for vo in bank(name):
            for u in vo['uses']:
                if u['kind'] != 'special' or u['input'] != inp: continue
                e = (vo['id'], min(255, sum(1 for i in keep if i < u['at'])))
                if e not in seen: seen.add(e); out.append([ks.index(k), e[0] | fx_bit(name, e[0]), e[1]])
    return sorted(out)

def table(ks, sug, mp, nvoices, nvoices_name=None):
    """the voice table bytes: [id, at] per key; at = the suggestion's place for that key (a picked voice starts where KOF's
    own did; a key KOF left silent: at its start)"""
    out = []
    for k in ks:
        i = mp.get(k, 0)
        assert 0 <= i <= nvoices, (k, i, nvoices)
        out += [i | fx_bit(nvoices_name, i), min(255, sug.get(k, [0, 0])[1]) if i else 0]
    return out

FX = 0x80
def fx_bit(name, i):
    """bit 7 of a voice id in the tables: the voice is a sound effect of its game (voices.json channel 'fx': Kizuna's
    own-effect sounds) played on the other voice slot so it does not cut the fighter's voice (fighter.c voice_play)"""
    vs = bank(name) if name else []
    return FX if i and i <= len(vs) and vs[i - 1].get('channel') == 'fx' else 0

if __name__ == '__main__':
    cmd, names = sys.argv[1], sys.argv[2:] or None
    if cmd == 'capture': capture(names)
    elif cmd == 'list': build_list(names)
