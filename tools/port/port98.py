#!/usr/bin/env python3
"""Port a song from another Neo Geo sound driver into KOF98's (SNK "Sound Driver(ROM)Ver 1.7"): the engine behind
tools/port/build_snd.py, which assembles the brawler's M ROM and V ROM from examples/brawler/songs.json.

Sources: MAKOTO v3 builds (Fatal Fury 3 / Special, KOF94/95, Art of Fighting 1-3: tools/makoto3, notes from
ff3_notes.py) and SNK's own line (KOF96's Ver 0.1, Kizuna, KOF97, Samurai Shodown IV, Garou: tools/kof98snd, notes
from snk_notes.py). The song becomes a KOF98 music command in a bank set the builder picks (Z80 $8000-$F7FF), its
samples go where the builder's V ROM allocator puts them, its sample records into KOF98 table entries no kept song uses.

Notes are engine-neutral (every note with its full chip state). Each is written so KOF98's driver makes the same chip
state (docs/kof98_sound_driver.md):
- level mode "direct" (KOF98's default until $26): FM TL = velocity, ADPCM-A level = velocity, ADPCM-B volume =
  velocity (header attenuations 0), so the velocity byte is FF3's register value;
- FM pitch: the KOF98 note whose table F-number is nearest in the same block, plus detune $2E (signed F-number add);
- FM patch: inline $34 with FF3's 28 operator registers, $B0 and the AMS/PMS bits (effects off) when it changes;
- pan $31/$32/$33; FF3 legato (no key-off before the next key-on) = a tie (gate > length: no new key-on);
- ADPCM-A: each source sample gets a free code of a KOF98 sample table (slots 0, 2, 6, then others), $0D switches the
  channel's table; level changes during a sample: untouched gate (tie) + $25 offset + $2C refresh, $0E before the
  next note;
- ADPCM-B: direct-mode notes (octave << 4 | semitone) index KOF98's delta-N table, which holds the MAKOTO and SNK
  values (others: the nearest, warned); each sample becomes a free instrument record; a slide = a tie into the next note;
- changes inside a held FM note (TL, pan, patch registers) have no KOF98 event that keeps the note: counted in the
  report ('dropped'), never silently;
- tempo: KOF98 runs a tick when its accumulator passes 208 (+tempo per timer-A interrupt, 166.83 Hz), and drops an
  interrupt that arrives while its handler still runs; the port's tempo T and tick scale k (every source tick = k KOF98
  ticks, T * k <= 208: k > 1 refines the tempo step for slow songs) are chosen so that 166.83 * T / 208 * (1 - loss) / k
  is nearest the source's real tick rate; loss = the share of interrupts the port's own writes make KOF98 drop
  (ISR cost model of tools/songlab/build_web.py: 100 + 6.4 cycles-units per write against 333 per period; measured in
  the brawler within 0.15 % for Mr. Big / Geese / FF3, 0.6 % high for Goenitz) and the source's real rate is its tick
  rate less its own driver's drops (SNK-line sources, same model; MAKOTO drivers drop none);
- loop: each channel's intro, then its loop body behind a label, ending in $0B goto label."""
import json, math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'kof98snd'))
from ff3_notes import FM
import ff3_notes, snk_notes
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'makoto3'))
import games as makoto_games, games98
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'ngss'))
import games_ngss, ngss_notes

SONG_Z80, SONG_Z80_END = 0x8000, 0xF800          # a bank set's window: Z80 $8000-$F7FF (RAM from $F800)

def source(game):
    """(M1 bytes, V bytes, notes function) of a source game: MAKOTO builds (tools/makoto3/games.py), Technos' SDC_NGSS
    (tools/ngss/games_ngss.py: Double Dragon, Super Dodge Ball) or SNK's line (tools/kof98snd/games98.py)"""
    if game in makoto_games.GAMES:
        g = makoto_games.GAMES[game]; m1 = open(os.path.join(g['dir'], g['m1']), 'rb').read(); fn = ff3_notes.notes
    elif game in games_ngss.GAMES:
        g = games_ngss.GAMES[game]; m1 = open(games_ngss.m1_path(game), 'rb').read(); fn = ngss_notes.notes
    else:
        g = games98.GAMES[game]; m1 = open(g['m1'], 'rb').read(); fn = snk_notes.notes
    return m1, roms(g['rom'])[1], fn
BUDGET, PATCH_WRITES = 28, 31   # writes per tick that keep KOF98's handler inside one timer period (ISR_START 100 +
                                # 6.4 per write < 333 samples: 36, minus margin); one inline patch = 31 writes
PERIOD, ISR_START, WRITE_COST = 333, 100, 6.4     # KOF98's interrupt handler cost model (tools/songlab/build_web.py)

def drops(m1, cmd, ticks):
    """share of timer-A interrupts the driver drops playing cmd for ticks ticks (the ISR cost model)"""
    import song98, regs98
    s = song98.Song(bytes(m1), cmd).run(ticks=ticks)
    count = {}
    for q, p, r, v in regs98.writes(s): count[q] = count.get(q, 0) + 1
    lost = sum(int((ISR_START + n * WRITE_COST) // PERIOD) for q, n in count.items() if q and ISR_START + n * WRITE_COST > PERIOD)
    return lost / max(1, s.irq)
A_SLOTS = (0, 2, 6, 3, 4, 1, 5)
A_TABLES = (0x3C4C, 0x424C, 0x484C, 0x4E4C, 0x544C, 0x5A4C, 0x604C)
CHAN_K = {'FM1': 0, 'FM2': 1, 'FM3': 2, 'FM4': 3, 'A1': 4, 'A2': 5, 'A3': 6, 'A4': 7, 'A5': 8, 'A6': 9, 'B': 10}
PAN_OP = {0xC0: 0x31, 0x80: 0x32, 0x40: 0x33}

def roms(path):
    d = open(path, 'rb').read()
    h = struct.unpack('<7I', d[4:32]); o = 4096 + h[0] + h[1]
    return bytearray(d[o:o + h[2]]), bytearray(d[o + h[2]:o + h[2] + h[3]])

def vl(d):
    assert 0 <= d < 0x2000, d
    return bytes([d]) if d < 0x80 else bytes([0x80 | d >> 7, d & 0x7F])

def ev(delta, op, *p):
    return (vl(delta) if delta is not None else b'') + bytes([0xC0 | op]) + bytes(p)

def w16(v): return bytes([v & 0xFF, v >> 8 & 0xFF])

class Port:
    """one song: src_game's command src_cmd -> KOF98 command dst_cmd in target (build_snd.Target: the M1 being
    built, the V ROM allocator, the free sample codes / records and the bank sets)"""
    def __init__(self, target, src_game, src_cmd, dst_cmd):
        self.t = target; self.m1 = target.m1; self.CMD = dst_cmd
        src_m1, self.src_v, fn = source(src_game)
        self.src = src_game
        self.notes, self.loops, self.hz, _ = fn(src_m1, src_cmd, passes=2)
        # MAKOTO and SDC_NGSS lose no interrupt (a pending flag waits; SDC_NGSS: the captures stay pass-aligned)
        self.src_loss = 0.0 if fn in (ff3_notes.notes, ngss_notes.notes) else drops(src_m1, src_cmd, max(a + b for a, b in self.loops.values()))
        self.noloop = set()
        for ch in list(self.notes):                    # a channel without a loop: its notes up to the song's end
            if ch not in self.loops: self.loops[ch] = (1, max(n.tick for n in self.notes[ch]) + 1); self.noloop.add(ch)
        self.report = {'source': f'{src_game} ${src_cmd:02X}', 'cmd': dst_cmd, 'warnings': []}
        self.steady_body()
        self.report['dropped'] = self.dropped()
        self.pitch_table()

    def steady_body(self):
        """the loop body each looping channel's goto replays: a source channel's state can differ on its first pass
        (a level or a pan the intro left), so the first pass and the second are compared at the chip (key-on state,
        key-off, changes); equal: the body is played once and looped; different: the first pass joins the intro and
        the second becomes the body ('unrolled' in the report; the third pass is the second's, checked by compare_port)"""
        CAR = (8, 8, 8, 8, 0x0C, 0x0E, 0x0E, 0x0F)
        def key(n, shift):
            off = None if n.off is None else n.off - shift
            ch = tuple((c[0] - shift,) + tuple(c[1:]) for c in n.changes)
            if hasattr(n, 'fnum'):
                regs = tuple(0 if 4 <= i < 8 and CAR[n.alg] >> (i - 4) & 1 else x for i, x in enumerate(n.regs[:28]))
                return (n.tick - shift, off, n.fnum, n.tl, n.pan, regs, n.regs[28], n.regs[29] & 0x3F, n.legato)
            if hasattr(n, 'deltan'): return (n.tick - shift, off, n.start, n.end, n.deltan, n.vol, n.pan, ch)
            return (n.tick - shift, off, n.start, n.end, n.level, ch)
        unrolled = {}
        for ch, lst in self.notes.items():
            if ch in self.noloop: continue
            L, length = self.loops[ch]
            p1 = [key(n, 0) for n in lst if L <= n.tick < L + length]
            p2 = [key(n, length) for n in lst if L + length <= n.tick < L + 2 * length]
            if p1 == p2: self.notes[ch] = [n for n in lst if n.tick < L + length]
            else:
                unrolled[ch] = sum(x != y for x, y in zip(p1, p2)) + abs(len(p1) - len(p2))
                self.notes[ch] = [n for n in lst if n.tick < L + 2 * length]
                self.loops[ch] = (L + length, length)
        if unrolled: self.report['unrolled'] = unrolled

    def dropped(self):
        """FM register changes after a note's key-on that alter a value, none of them written in KOF98's format:
        'held' = while the key is down (heard), 'release' = after the key-off, before the channel's next key-on (the
        release tail; changes in the next key-on's own tick are that note's state and are written)"""
        out = {}
        for ch in FM:
            lst = self.notes.get(ch, [])
            for i, n in enumerate(lst):
                nxt = lst[i + 1].tick if i + 1 < len(lst) else 1 << 30
                end = n.off if n.off is not None else nxt
                state = {'tl': n.tl, 'pan': n.pan, 'fnum': n.fnum, 'vib': n.fnum}
                for c in n.changes:
                    k = c[1]
                    if k in state and c[2] == state[k]: continue
                    if k in state: state[k] = c[2]
                    if k in ('fnum', 'vib'): state['fnum'] = state['vib'] = c[2]
                    if c[0] >= nxt: continue
                    w = f"{ch} {k} {'held' if c[0] < end else 'release'}"
                    out[w] = out.get(w, 0) + 1
        return out

    def warn(self, s): self.report['warnings'].append(s)

    # -- FM pitch: KOF98 note n -> (block, F-number) ($2447: $2BC8 note table, $2A68 F-number words)
    def pitch_table(self):
        m = self.m1; self.pitch = {}
        for n in range(0x80):
            v = m[0x2BC8 + n]
            if v >= 0xC0: continue
            idx = ((v & 0xF0) >> 1) & 0xFF
            self.pitch[n] = (v & 7, m[0x2A68 + idx] | m[0x2A69 + idx] << 8)

    def fm_note(self, word, avoid=None):
        """(KOF98 note, detune) for an F-number word: the nearest note of the same block. avoid: a note number not to
        use (a tie into the same note writes nothing, $2447: a pitch step of a slide that lands on the previous note's
        number goes through the neighbouring note with the detune that makes the same F-number; detune -64..127)"""
        blk, fn = word >> 11 & 7, word & 0x7FF
        best = min(((abs(fn - f), n, fn - f) for n, (b, f) in self.pitch.items() if b == blk and n != avoid
                    and (avoid is None or -64 <= fn - f <= 127)), default=None)
        if best is None or best[0] > 127: raise ValueError(f'F-number {word:04X} out of reach')
        return best[1], best[2]

    # -- samples: source V pages -> pages of the V ROM being built; records into free table entries
    def place_samples(self):
        a_s = sorted({(n.start, n.end) for ch in self.notes if ch.startswith('A') for n in self.notes[ch]})
        b_s = sorted({(n.start, n.end) for n in self.notes.get('B', [])})
        self.vmap = {}
        for st, en in sorted(set(a_s) | set(b_s), key=lambda r: r[0] - r[1]):     # largest first
            self.vmap[(st, en)] = self.t.place(self.src, st, en, self.src_v, adpcm_a=(st, en) in a_s)
        self.report['samples'] = {'adpcm_a': len(a_s), 'adpcm_b': len(b_s),
                                  'bytes': sum((e - s + 1) * 256 for s, e in self.vmap)}
        self.acode = {}
        for st, en in a_s:
            sl, c = self.t.free_acode()
            ns, ne = self.vmap[(st, en)]
            r = A_TABLES[sl] + 6 * c
            self.m1[r:r + 6] = bytes([0x7F]) + w16(ns) + w16(ne) + bytes([0xDF])
            self.acode[(st, en)] = (sl, c)
        # ADPCM-B: [prio][start][end][loops 0][ls][le][dn][$80] in a free record (instrument n = record n)
        recs = self.m1[0x2E1E] | self.m1[0x2E1F] << 8
        self.binst = {}
        for st, en in b_s:
            i = self.t.free_brec()
            ns, ne = self.vmap[(st, en)]
            r = recs + 13 * i
            self.m1[r:r + 13] = bytes([0x7F]) + w16(ns) + w16(ne) + bytes([0]) + w16(0) + w16(0xFFFF) + w16(0x6EB3) + bytes([0x80])
            self.binst[(st, en)] = i
        # pitches: KOF98's delta-N table in note mode (octave << 4 | semitone); a delta-N the table lacks plays in kit
        # mode ($0F 1: the note number is the record, whose own delta-N is used, $088E) from a record of its own
        self.dn = [self.m1[0x2B2A + 2 * i] | self.m1[0x2B2B + 2 * i] << 8 for i in range(96)]
        self.kit = {}
        for n in self.notes.get('B', []):
            for v in [n.deltan] + [c[2] for c in n.changes if c[1] == 'bslur']:
                if v in self.dn or (n.start, n.end, v) in self.kit: continue
                i = self.t.free_brec(); ns, ne = self.vmap[(n.start, n.end)]
                self.m1[recs + 13 * i:recs + 13 * i + 13] = bytes([0x7F]) + w16(ns) + w16(ne) + bytes([0]) + w16(0) + \
                    w16(0xFFFF) + w16(v) + bytes([0x80])
                self.kit[(n.start, n.end, v)] = i
        if self.kit: self.report['adpcm_b_kit_records'] = len(self.kit)

    def b_pitch(self, smp, v):
        """(sample mode, note byte) of an ADPCM-B pitch"""
        if v in self.dn: i = self.dn.index(v); return 0, (i // 12) << 4 | i % 12
        return 1, self.kit[(smp[0], smp[1], v)]

    # -- one channel: moments (tick, kind, data) -> bytes
    def channel(self, name, base_addr):
        lst = self.notes[name]; L, length = self.loops[name]; end = L + length
        moments = []                        # (tick, 'note', Note, gate_ticks or None, retrigger) / (tick, 'level', v)
        for i, n in enumerate(lst):
            if n.tick >= end: break
            nxt = lst[i + 1].tick if i + 1 < len(lst) else end
            moments.append([n.tick, 'note', n])
            for c in n.changes:
                if not n.tick < c[0] < min(nxt, n.off if n.off is not None else nxt, end): continue
                if c[1] == 'alevel': moments.append([c[0], 'level', c[2]])
                elif c[1] == 'bslur': moments.append([c[0], 'slur', c[2], c[3]])
            if name == 'B' and n.tick in self.b_silent and n.off is not None and n.off < min(nxt, end):
                moments.append([n.off, 'bsilent'])
        if name in FM:
            for t, regs in self.patch_plan(name): moments.append([t, 'patch', regs])
        moments.sort(key=lambda m: (m[0], m[1] != 'patch'))        # a patch before a note of the same tick
        if not any(m[0] == L for m in moments): moments.append([L, 'label']); moments.sort(key=lambda m: (m[0], m[1] != 'patch'))
        if lst[0].tick > 1: moments.insert(0, [1, 'rest'])
        for i, n in enumerate(lst):              # a note sounding across the loop point
            nxt = lst[i + 1].tick if i + 1 < len(lst) else end
            if n.tick < L < (n.off if n.off is not None else nxt) and not (name.startswith('A') and n.off is None):
                self.warn(f'{name}: note at tick {n.tick} sounds across the loop point {L}')
        out = bytearray(); label_at = None
        st = {}                                  # emitted state
        for k, mo in enumerate(moments):
            t = mo[0]
            nt = moments[k + 1][0] if k + 1 < len(moments) else end
            delta = nt - t
            if t == L and label_at is None and mo[1] != 'patch' or (t > L and label_at is None):
                label_at = base_addr + len(out)                          # every state field but the patch (planned
                st = {'patch': st.get('patch'), 'smp': st.get('smp')}    # for both ways in) re-emitted after it
            kind = mo[1]
            if kind == 'patch':
                out += ev(None, 0x34, *mo[2][:28], mo[2][28], mo[2][29] & 0x3F, *([0] * 11)); st['patch'] = mo[2]
                if delta: out += ev(delta, 0x01)
                continue
            if kind in ('rest', 'label'):
                if delta: out += ev(delta, 0x01)
                continue
            if kind == 'level':                                          # ADPCM-A level during the sample
                v = mo[2]; lvl = v & 0x1F; off = (lvl - st['vel']) & 0xFF
                out += ev(None, 0x25, (off + 0x80) & 0xFF) + ev(delta, 0x2C, 0)
                st['off'] = off; continue
            if kind == 'bsilent':                                        # ADPCM-B key-off KOF98 would skip: a tie
                out += ev(delta, 0x00, *vl(delta), st['b'], 0); continue   # into the same note at volume 0
            if kind == 'slur':                                           # ADPCM-B: tie into the new pitch / volume
                mode, b = self.b_pitch(st['smp'], mo[2])
                if st.get('mode') != mode: out += ev(None, 0x0F, mode); st['mode'] = mode
                gate = self.gate_for(lst, mo[0], nt, end, tie_ahead=self.slur_ahead(moments, k))
                out += ev(delta, 0x00, *vl(gate), b, mo[3]); continue
            n = mo[2]
            if st.get('off', 0): out += ev(None, 0x0E) + ev(None, 0x25, 0x80 if name.startswith('A') else 0x88); st['off'] = 0
            gate = self.gate_for(lst, t, nt, end, tie_ahead=self.slur_ahead(moments, k))
            if name in FM:
                assert st.get('patch') == tuple(n.regs), (name, t)
                if st.get('pan') != n.pan:
                    out += ev(None, PAN_OP[n.pan]); st['pan'] = n.pan
                note, det = self.fm_note(n.fnum)
                if getattr(n, 'legato', False) and st.get('note') == note and st.get('fnum') != n.fnum:
                    note, det = self.fm_note(n.fnum, avoid=note)
                if st.get('det') != det: out += ev(None, 0x2E, (det + 0x40) & 0xFF); st['det'] = det
                out += ev(delta, 0x00, *vl(gate), note, n.tl); st['vel'] = n.tl; st['note'] = note; st['fnum'] = n.fnum
            elif name.startswith('A'):
                sl, code = self.acode[(n.start, n.end)]
                if st.get('slot') != sl: out += ev(None, 0x0D, sl); st['slot'] = sl
                pan = n.level & 0xC0
                if st.get('pan') != pan: out += ev(None, PAN_OP[pan]); st['pan'] = pan
                out += ev(delta, 0x00, *vl(gate), code, n.level & 0x1F); st['vel'] = n.level & 0x1F
            else:
                mode, b = self.b_pitch((n.start, n.end), n.deltan); st['smp'] = (n.start, n.end)
                if st.get('mode') != mode: out += ev(None, 0x0F, mode); st['mode'] = mode
                inst = self.binst[(n.start, n.end)]
                if mode == 0 and st.get('inst') != inst: out += ev(None, 0x03, inst); st['inst'] = inst
                if st.get('pan') != n.pan: out += ev(None, PAN_OP[n.pan]); st['pan'] = n.pan
                out += ev(delta, 0x00, *vl(gate), b, n.vol); st['vel'] = n.vol; st['b'] = b
        assert label_at is not None
        out += ev(None, 0x0B, *w16(label_at))
        return bytes(out)

    def patch_needs(self, name):
        """the patch loads an FM channel needs: [(note tick, regs, earliest tick)]: before a note whose patch is not the
        one the previous note left (the loop's first note: from both the intro's last note and the body's last),
        anywhere from the previous note's key-off on (a legato note: only at the note itself)"""
        lst = [n for n in self.notes[name] if n.tick < self.loops[name][0] + self.loops[name][1]]
        L, length = self.loops[name]; end = L + length
        need = []; first_body = next(i for i, n in enumerate(lst) if n.tick >= L)
        for i, n in enumerate(lst):
            regs = tuple(n.regs)
            prev = lst[i - 1] if i else None
            if i == first_body:
                last_body = lst[-1]
                if tuple(last_body.regs) != regs:            # back from the goto: load it at the body's end
                    need.append((end, regs, last_body.off if last_body.off is not None else end, 'end'))
                if prev is None or tuple(prev.regs) != regs:  # from the intro: before the label
                    lo = (prev.off if prev and prev.off is not None else (prev.tick + 1 if prev else 1))
                    need.append((n.tick, regs, lo, 'intro'))
                continue
            if prev is not None and tuple(prev.regs) == regs: continue
            if prev is None: lo = 1
            elif getattr(n, 'legato', False) or prev.off is None: lo = n.tick
            else: lo = prev.off
            need.append((n.tick, regs, lo, 'note'))
        return need

    def patch_plan(self, name):
        return [(self.patch_at.get((name, t, why), t if why != 'end' else lo), regs)
                for t, regs, lo, why in self.patch_needs(name)]

    def slur_ahead(self, moments, k):
        """the next moment continues this sound (ADPCM-B slide, ADPCM-A level change, FM legato note)"""
        if k + 1 >= len(moments): return False
        nxt = moments[k + 1]
        return nxt[1] in ('slur', 'level', 'bsilent') or (nxt[1] == 'note' and getattr(nxt[2], 'legato', False))

    def gate_for(self, lst, t, nt, end, tie_ahead):
        """gate ticks for the moment at t (length nt - t). The sound's own end E: its key-off, else (an FM note
        going on into a legato one, a sample) none. Continued by the next moment: a tie, whose overhang ends the
        sound at E (KOF98 counts it down through the following events: $1BE0). Not continued: key-off at E."""
        n = max((x for x in lst if x.tick <= t), key=lambda x: x.tick)
        E = n.off
        if tie_ahead:
            if E is not None and E > nt: return min(0x1FFF, E - t)
            return min(0x1FFF, nt - t + (0x1000 if E is None else 1))
        if E is None: return nt - t
        return max(1, min(E, nt) - t)

    def build(self):
        self.place_samples()
        # KOF98 driver bug: opcode $34 (inline patch, no KOF98 song uses it) flushes the registers through $1538, a
        # copy of $14B6 without its DI / EI around each address-data pair; a timer interrupt landing inside a pair
        # re-arms $27 and the pair's data byte then goes to $27: timer A off, the music dead for good (measured in
        # the brawler: frame 1104, PC $1567 / $156B with interrupts on). $243F: CALL $1538 -> CALL $14B6.
        if self.m1[0x243F:0x2442] == bytes([0xCD, 0x38, 0x15]): self.m1[0x2440:0x2442] = bytes([0xB6, 0x14])
        assert self.m1[0x243F:0x2442] == bytes([0xCD, 0xB6, 0x14])
        # tempo: trial builds in a copy of the M1 (bank set 6) until the tempo / tick scale settle
        import copy
        self.notes0, self.loops0 = copy.deepcopy(self.notes), dict(self.loops)
        real = self.m1; self.m1 = bytearray(real); self.at = (6, SONG_Z80)
        self.k, self.T = 1, min(208, round(self.hz * (1 - self.src_loss) * 208 / 166.83))
        for it in range(4):
            self.rescale(); self.passes()
            loss = drops(self.m1, self.CMD, max(a + b for a, b in self.loops.values()))
            k, T = self.pick_tempo(loss)
            if (k, T) == (self.k, self.T): break
            self.k, self.T = k, T
        self.m1 = real; del self.at
        song = self.passes()
        hz = 166.83 * self.T / 208
        self.report.update(tempo=self.T, tick_scale=self.k, kof98_hz=hz / self.k, loss_estimate=round(loss, 4),
                           kof98_hz_after_losses=hz * (1 - loss) / self.k, source_hz=self.hz,
                           source_hz_after_losses=self.hz * (1 - self.src_loss),
                           tempo_error_pct=round(100 * (hz * (1 - loss) / self.k / (self.hz * (1 - self.src_loss)) - 1), 2))
        if self.b_silent: self.report['adpcm_b_silent_offs'] = len(self.b_silent)
        self.report['heaviest_tick_writes'] = self.max_load
        self.report['loops'] = {k: list(v) for k, v in self.loops0.items()}   # in source ticks
        return song

    def passes(self):
        self.patch_at = {}; self.b_silent = set()
        for it in range(12):
            song = self.build_once()
            moved = self.spread_patches() | self.b_offs()
            if not moved: break
        return song

    def pick_tempo(self, loss):
        """(k, T) whose real KOF98 tick rate / k is nearest the source's; the smallest k within 0.05 %"""
        want = self.hz * (1 - self.src_loss); best = None
        for k in range(1, 9):
            for T in range(1, 209):
                err = abs(166.83 * T / 208 * (1 - loss) / k / want - 1)
                if best is None or err < best[0] - 0.0005: best = (err, k, T)
        return best[1], best[2]

    def rescale(self):
        """the notes and loops in KOF98 ticks: source tick t -> (t - 1) * k + 1"""
        import copy
        k = self.k; f = lambda t: None if t is None else (t - 1) * k + 1
        self.notes = copy.deepcopy(self.notes0)
        for lst in self.notes.values():
            for n in lst:
                n.tick, n.off = f(n.tick), f(n.off)
                n.changes = [(f(c[0]),) + tuple(c[1:]) for c in n.changes]
        self.loops = {ch: (f(L), length * k) for ch, (L, length) in self.loops0.items()}

    def b_offs(self):
        """KOF98 skips an ADPCM-B key-off in note mode while the last note-on anywhere was a tie into another note
        ($1E9B: $FD9C is global; a slur on FM or ADPCM-B sets it): the source's key-offs the model of the port does
        not make become a tie into the same note at volume 0 (silent, the sample runs on). True when the set grew."""
        import song98
        lst = self.notes.get('B', [])
        if not lst: return False
        L, length = self.loops['B']; end = L + length
        s = song98.Song(bytes(self.m1), self.CMD).run(ticks=end + 1)
        offs = {t for irq, t, ch, kind, kw in s.out if ch == 'B' and kind == 'boff'}
        grew = False
        for i, n in enumerate(lst):
            nxt = lst[i + 1].tick if i + 1 < len(lst) else end
            if n.off is None or n.off >= min(nxt, end) or n.tick in self.b_silent: continue
            if any(c[0] >= n.off for c in n.changes if c[1] == 'bslur'): continue
            if n.off not in offs: self.b_silent.add(n.tick); grew = True
        return grew

    def tick_loads(self, m1):
        """writes per sequencer tick in KOF98's model of the song (both passes of the loop)"""
        import song98, regs98
        s = song98.Song(bytes(m1), self.CMD).run(ticks=2 * max(a + b for a, b in self.loops.values()) + 2)
        tick = {}
        for irq, t, *_ in s.out: tick[irq] = t
        load = {}
        for irq, p, r, v in regs98.writes(s): load[tick.get(irq, 0)] = load.get(tick.get(irq, 0), 0) + 1
        return load

    def spread_patches(self):
        """move patch loads off ticks whose interrupt would run past the next one (KOF98 then re-enters its handler,
        and the nested timer re-arm makes the outer handler's next port-A data byte land in $27: timer A off, the
        music clock dead; measured in the brawler, frame 1104): latest earlier tick with room, channel silent"""
        load = self.tick_loads(self.m1)
        self.max_load = max(load.values())
        moved = False
        for name in FM:
            if name not in self.notes: continue
            for t, regs, lo, why in self.patch_needs(name):
                key = (name, t, why)
                cur = self.patch_at.get(key, t if why != 'end' else lo)
                if load.get(cur, 0) <= BUDGET: continue
                hi = (self.loops[name][0] - 1) if why == 'intro' else (self.loops[name][0] + self.loops[name][1] - 1 if why == 'end' else t)
                cands = [x for x in range(max(lo, 1), min(hi, cur) + 1) if x != cur and load.get(x, 0) + PATCH_WRITES <= BUDGET]
                if not cands:
                    self.warn(f'{name}: patch load at tick {cur} ({load.get(cur, 0)} writes) has no lighter silent tick')
                    continue
                new = max(cands)
                self.patch_at[key] = new
                load[cur] = load.get(cur, 0) - PATCH_WRITES; load[new] = load.get(new, 0) + PATCH_WRITES
                moved = True
        return moved

    def build_once(self):
        names = [n for n in CHAN_K if n in self.notes]
        head = bytearray(14 + 22)
        for n in names: head[CHAN_K[n]] = 1
        head[11] = self.T; head[12] = head[13] = 0
        if not hasattr(self, 'at'):                    # the song's place: one pass to learn its length, then the target's
            self.at = (None, SONG_Z80)
            size = len(self.assemble(head, names))
            self.at = self.t.reserve(size + 256)       # (bank set, Z80 address); room for the patch moves
        song = self.assemble(head, names)
        bank, z = self.at
        off = self.t.m1_offset(bank, z)
        self.m1[off:off + len(song)] = song
        i = self.CMD - 0x20
        self.m1[0x329E + 2 * i:0x329E + 2 * i + 2] = w16(z)
        bt = self.m1[0x2E06] | self.m1[0x2E07] << 8
        self.m1[bt + i] = bank
        self.report['vmap'] = {json.dumps(list(k)): list(v) for k, v in self.vmap.items()}
        self.report.update(song_bytes=len(song), bank_set=bank, z80=f'${z:04X}', channels=names)
        return song

    def assemble(self, head, names):
        head = bytearray(head); body = bytearray(); addr = self.at[1] + len(head)
        for n in names:
            s = self.channel(n, addr)
            head[14 + 2 * CHAN_K[n]:16 + 2 * CHAN_K[n]] = w16(addr)
            body += s; addr += len(s)
        song = bytes(head) + bytes(body)
        if self.at[1] + len(song) > SONG_Z80_END: raise ValueError(f'song too long: {len(song)} bytes')
        return song

if __name__ == '__main__':
    sys.exit('used by build_snd.py (examples/brawler/songs.json); see its docstring')
