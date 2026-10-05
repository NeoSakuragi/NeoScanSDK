#!/usr/bin/env python3
"""The brawler's menu sounds (TODO #63): SSG cues played by KOF98's own generated-sound path (command type 5, $0AC0;
docs/kof98_sound_driver.md "SSG cues"), no driver code changed. build_snd.py calls build() with songs.json "ssg":

    "ssg": {"cues": [{"name": "CURSOR", "cmd": "74", "voices": [[["E7", 2, 12], ["E7", 2, 6]], ...]}, ...]}
    voice = [[note, ticks, level], ...] on SSG A, B, C in order; note "C#6" / "A5+" (a half semitone up) / "-" (a rest); ticks at the cue tempo ($5A:
    166.83 * 90 / 208 = 72.2 ticks/s, 13.9 ms); level 0-15 = the SSG volume register (the note's velocity, written as is)

What build() writes into the fixed 32 KB (every other byte of it stays KOF98's):
  $3038 + cmd - $20  type byte 5 (the cue commands are unused in KOF98: type 0)
  $331E + 2 (cmd - $60)  pointer to the cue's header (KOF98's own cues $65 $70-$73 $7A $7F stay)
  $2C56-$2DFF  free in KOF98 ($FF): the headers [4 enables][priority][noise mixer][4 stream pointers] (blocks SSG A, B, C,
               noise) and the streams: per step [length][$EA][note][level] (opcode $2A, gate = length), a rest =
               [length][$C1] (no-op), end [$01][$C6]. The first channel to reach its end ends the cue on every
               channel (measured), so every voice is padded with a rest to the longest
Note byte (driver $0B74): bits 7-5 octave shift o, bit 4 half-semitone, bits 3-0 semitone n: period = word($2AC8 + 8n) >> o
(the table is C1 = 32.7 Hz at 125 kHz / period), so o = octave - 1.

    python3 ssg_cues.py --check SND_DIR [--rom ROM.neo] [--wav-dir DIR]
        each cue alone in the brawler ROM (our emulator, capture_snd.py): the SSG state at every timer interrupt against
        the cue's data (same notes, levels, periods in the same order; each step's length within 2 interrupts)
    python3 ssg_cues.py --mix SND_DIR SONG OUT_DIR [--rom ROM.neo]
        song + fight effects ($1A hits), with and without the cues sent over it: every non-SSG write (song, effects)
        identical in value and order in both runs; reported: the frame-by-frame diff (diffcap.py: writes moved by a
        dropped timer interrupt) and the interrupts KOF98's re-entry guard dropped in each run"""
import json, os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__)); TOOLS = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(TOOLS, 'kof98snd'))

TYPES, CUE_TAB, AREA, AREA_END, PERIODS = 0x3038, 0x331E, 0x2C56, 0x2E00, 0x2AC8
TEMPO = 0x5A                                              # $0B5B: every cue's group tempo
PRIO = 1                                                  # lower = stronger ($0AFF); KOF98's own cues use 0-5
NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

def note_byte(name):
    h = name.endswith('+'); name = name.rstrip('+')           # "A5+" = A5 + a half semitone (note byte bit 4)
    n = NAMES.index(name[:-1]); o = int(name[-1]) - 1
    assert 0 <= o <= 7, name
    return o << 5 | h << 4 | n

def period(m1, nb):
    t = PERIODS + 8 * (nb & 0x0F) + (4 if nb & 0x10 else 0)
    return (m1[t] | m1[t + 1] << 8) >> (nb >> 5)

def stream(voice):
    s = bytearray()
    for nm, ticks, lvl in voice:
        assert 0 < ticks < 0x80 and 0 <= lvl <= 15
        s += bytes([ticks, 0xC1]) if nm == '-' else bytes([ticks, 0xEA, note_byte(nm), lvl])
    return s + bytes([0x01, 0xC6])

def build(m1, cfg):
    """write the cues into m1 (bytearray, KOF98's M ROM being built); -> (changed ranges, {name: cmd}, report)"""
    at = AREA; cmds = {}; rep = []
    for c in cfg['cues']:
        cmd = int(c['cmd'], 16); assert 0x61 <= cmd <= 0x7E and m1[TYPES + cmd - 0x20] == 0, f"${cmd:02X} is in use"
        vs = c['voices']; assert 1 <= len(vs) <= 3
        hdr = at; at += 14; ptrs = []
        total = max(sum(t for _, t, _ in v) for v in vs)
        for v in vs:                                      # the first channel to end ends the whole cue (measured): the
            pad = total - sum(t for _, t, _ in v)         # shorter voices wait out the longest with a rest
            s = stream(v + ([['-', pad, 0]] if pad else [])); ptrs.append(at); m1[at:at + len(s)] = s; at += len(s)
        en = [1] * len(vs) + [0] * (4 - len(vs))
        p = b''.join(bytes([a & 0xFF, a >> 8]) for a in ptrs + [0] * (4 - len(vs)))
        m1[hdr:hdr + 14] = bytes(en + [PRIO, 0]) + p
        m1[TYPES + cmd - 0x20] = 5
        m1[CUE_TAB + 2 * (cmd - 0x60):CUE_TAB + 2 * (cmd - 0x60) + 2] = bytes([hdr & 0xFF, hdr >> 8])
        cmds[c['name']] = cmd
        rep.append({'name': c['name'], 'cmd': cmd, 'header': hdr, 'ms': round(max(sum(t for _, t, _ in v) for v in vs) * 208 / (166.83 * TEMPO) * 1000)})
    assert at <= AREA_END, f'cues need {at - AREA} bytes, {AREA_END - AREA} free'
    ranges = [(AREA, AREA_END)] + [(TYPES + v - 0x20, TYPES + v - 0x1F) for v in cmds.values()] + \
             [(CUE_TAB + 2 * (v - 0x60), CUE_TAB + 2 * (v - 0x60) + 2) for v in cmds.values()]
    return ranges, cmds, {'cues': rep, 'bytes': at - AREA}

# -- checks in our emulator
def ssg_states(path):
    """capture -> [(interrupt, frame, ((period, level, on) x 3))]: the SSG state after every timer A interrupt"""
    regs = [0] * 14; regs[7] = 0x3F; out = []; f = 0; n = 0
    def snap():
        return tuple(((regs[2 * c] | (regs[2 * c + 1] & 15) << 8), regs[8 + c] & 15, not regs[7] >> c & 1) for c in range(3))
    for l in open(path):
        p = l.split()
        if p[0] == 'f': f = int(p[1])
        elif p[0] == 'a' and p[1] == '27': out.append((n, f, snap())); n += 1
        elif p[0] == 'a' and int(p[1], 16) <= 0x0D: regs[int(p[1], 16)] = int(p[2], 16)
    out.append((n, f, snap()))
    return out

def audible(st):
    return tuple((pe, lv) if on and lv else None for pe, lv, on in st)

def expected(m1, voices):
    """per voice: [(period, level) or None, ticks]"""
    return [[(None if nm == '-' else (period(m1, note_byte(nm)), lvl), t) for nm, t, lvl in v] for v in voices]

def runs(states, c):
    r = []
    for _, _, st in states:
        a = audible(st)[c]
        if r and r[-1][0] == a: r[-1][1] += 1
        else: r.append([a, 1])
    return r

def check_cue(m1, cue, cap):
    states = ssg_states(cap); errs = []
    for c, v in enumerate(expected(m1, cue['voices'])):
        got = [x for x in runs(states, c)]
        while got and got[0][0] is None: got.pop(0)       # before the cue's first tick
        if got and got[-1][0] is None: got.pop()         # silence after the end
        want = [list(x) for x in v]
        while want and want[0][0] is None: want.pop(0)
        if not want: continue
        # merge equal neighbours (a re-struck same note at the same level is one audible state)
        def merge(xs):
            o = []
            for a, n in xs:
                if o and o[-1][0] == a: o[-1][1] += n
                else: o.append([a, n])
            return o
        want = merge(want); got = merge(got)
        if [a for a, _ in got] != [a for a, _ in want]:
            errs.append(f'voice {c}: states {[a for a, _ in got]} != {[a for a, _ in want]}'); continue
        for (a, n), (_, t) in zip(got[:-1], want[:-1]):   # the last step's length ends at the cue's end, not compared
            if abs(n - t * 208 / TEMPO) > 2: errs.append(f'voice {c}: {a} {n} interrupts for {t} ticks ({t * 208 / TEMPO:.1f})')
        g, w = sum(n for _, n in got), sum(t for _, t in want) * 208 / TEMPO
        if abs(g - w) > 3: errs.append(f'voice {c}: sounds {g} interrupts, its data {w:.1f}')
    return errs

def capture(cmd_hex, sec, out, rom, then=None):
    a = [sys.executable, os.path.join(HERE, 'capture_snd.py'), 'brawler', cmd_hex, str(sec), out]
    if rom: a += ['--rom', rom]
    if then: a += ['--then', then]
    subprocess.run(a, check=True, stdout=subprocess.DEVNULL)

def check(snd_dir, rom=None, wav_dir=None):
    m1 = open(f'{snd_dir}/m1.bin', 'rb').read()
    man = json.load(open(os.path.join(TOOLS, '..', 'examples', 'brawler', 'songs.json')))
    wav_dir = wav_dir or f'{snd_dir}/cap'; ok = True
    for cue in man['ssg']['cues']:
        out = f"{wav_dir}/ssg_{cue['name'].lower()}"
        capture(cue['cmd'], 1.5, out, rom)
        e = check_cue(m1, cue, out + '.txt')
        non_ssg = [l for l in open(out + '.txt') if l[0] in 'ab' and not (l[0] == 'a' and (int(l.split()[1], 16) <= 0x0D or l.split()[1] == '27'))]
        if non_ssg: e.append(f'{len(non_ssg)} non-SSG writes: {non_ssg[:3]}')
        print(f"{cue['name']:8s} ${cue['cmd']}: {'OK' if not e else e}  ({out}.wav)")
        ok &= not e
    return ok

def mix(snd_dir, song, out_dir, rom=None):
    """the song + hits, then the same + every cue over it; diffcap: only SSG added, nothing removed"""
    import diffcap
    man = json.load(open(os.path.join(TOOLS, '..', 'examples', 'brawler', 'songs.json')))
    hits = ['2.0:1A11', '2.6:1A13', '3.3:1A15', '4.1:1A12', '5.0:1A14']
    cues = [f"{1.0 + 0.7 * i:.1f}:{c['cmd']}" for i, c in enumerate(man['ssg']['cues'])] + \
           [f"{4.0 + 0.4 * i:.1f}:{c['cmd']}" for i, c in enumerate(man['ssg']['cues'])]
    os.makedirs(out_dir, exist_ok=True)
    capture(song, 8, f'{out_dir}/base', rom, ','.join(hits))
    capture(song, 8, f'{out_dir}/cues', rom, ','.join(sorted(hits + cues, key=lambda x: float(x.split(':')[0]))))
    added, removed = diffcap.diff(f'{out_dir}/base.txt', f'{out_dir}/cues.txt')
    print('frame by frame, added:', {u: len(v) for u, v in added.items()}, 'removed:', {u: len(v) for u, v in removed.items()})
    def seq(p, flags):                                    # every non-SSG write in order (no timer re-arms); flags:
        o = []                                            # only the ADPCM end-flag resets, else everything but them
        for l in open(p):
            x = l.split()
            if x[0] in 'ab' and not (x[0] == 'a' and (int(x[1], 16) <= 0x0D or x[1] == '27')) and \
                    (x[0] == 'a' and x[1] == '1C') == flags: o.append(tuple(x))
        return o
    drops = lambda p: sum(l.startswith('q 2') for l in open(p))
    same = seq(f'{out_dir}/base.txt', False) == seq(f'{out_dir}/cues.txt', False)
    flags = len(seq(f'{out_dir}/base.txt', True)) == len(seq(f'{out_dir}/cues.txt', True))
    d0, d1 = drops(f'{out_dir}/base.txt'), drops(f'{out_dir}/cues.txt')
    print(f"song + effect writes identical in value and order: {same}; ADPCM end flags {'same count' if flags else 'DIFFER'}; "
          f"timer interrupts dropped by the re-entry guard: {d0} without cues, {d1} with (each = the music 6 ms later)")
    ok = same and flags
    print('MIX', 'OK: the cues add SSG writes only, no song / effect write lost or changed' if ok else 'FAIL', f'({out_dir}/cues.wav)')
    return ok

if __name__ == '__main__':
    a = sys.argv
    opt = lambda k: a[a.index(k) + 1] if k in a else None
    if a[1] == '--check': sys.exit(0 if check(a[2], opt('--rom'), opt('--wav-dir')) else 1)
    if a[1] == '--mix': sys.exit(0 if mix(a[2], a[3], a[4], opt('--rom')) else 1)
