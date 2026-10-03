#!/usr/bin/env python3
"""Port a Fatal Fury 3 song (MAKOTO v3 driver) into KOF98's sound driver (SNK v1.7): the song becomes KOF98 command
$27 (an empty slot of the song table) in bank set 6 (Z80 $8000-$F7FF = M1 $38000-$3F7FF, free; no song uses the set),
its samples go into V ROM space only KOF98 stage themes the brawler does not play use, its sample records into
unused KOF98 table entries.

    python3 ff3_to_kof98.py 0x2F OUT_DIR      -> OUT_DIR/kof98_m1.bin, kof98_v1.bin (patched), port_2F.json (report)

Notes come from ff3_notes.py (the FF3 model: every note with its full chip state). Each is written so KOF98's driver
makes the same chip state (docs/kof98_sound_driver.md):
- level mode "direct" (KOF98's default until $26): FM TL = velocity, ADPCM-A level = velocity, ADPCM-B volume =
  velocity (header attenuations 0), so the velocity byte is FF3's register value;
- FM pitch: the KOF98 note whose table F-number is nearest in the same block, plus detune $2E (signed F-number add);
- FM patch: inline $34 with FF3's 28 operator registers, $B0 and the AMS/PMS bits (effects off) when it changes;
- pan $31/$32/$33; FF3 legato (no key-off before the next key-on) = a tie (gate > length: no new key-on);
- ADPCM-A: each FF3 sample gets an empty code of a KOF98 sample table (slots 0, 2, 6, then others), $0D switches the
  channel's table; level changes during a sample: untouched gate (tie) + $25 offset + $2C refresh, $0E before the
  next note;
- ADPCM-B: direct-mode notes (octave << 4 | semitone) index KOF98's delta-N table, which holds FF3's values; FF3's
  samples become instruments 1-6 (records 1-6, placeholders in KOF98); a slide (FF3 $083E) = a tie into the next note;
- tempo: FF3's tick rate, raised by the share of timer interrupts KOF98's driver loses (LOST: FF3's driver
  loses none): FF3 $2F 66.77 ticks/s -> tempo 84 = 67.37 nominal, 66.63 after the losses;
- loop: each channel's intro, then its loop body behind a label, ending in $0B goto label."""
import json, math, os, struct, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'kof98snd'))
from ff3_notes import notes, FM

KOF98_NEO, FF3_NEO = '/data/roms/kof98.neo', '/data/roms/fatfury3.neo'
FF3_M1 = '/data/neogeo_dict/sound/snd98/ff3/ff3_m1.bin'
FREE_V = '/data/neogeo_dict/sound/snd98/kof98_v_free_runs.json'   # V pages only songs the brawler skips use
CMD, BANKSET, SONG_AT, SONG_Z80, SONG_END = 0x27, 6, 0x38000, 0x8000, 0x3F800
BUDGET, PATCH_WRITES = 28, 31   # writes per tick that keep KOF98's handler inside one timer period (ISR_START 100 +
                                # 6.4 per write < 333 samples: 36, minus margin); one inline patch = 31 writes
LOST = 0.011        # timer interrupts KOF98's driver loses playing this song in the brawler (measured: 76 of 6774)
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
    def __init__(self, cmd):
        self.m1, self.v = roms(KOF98_NEO)
        self.ff3_m1 = open(FF3_M1, 'rb').read()
        _, self.ff3_v = roms(FF3_NEO)
        self.notes, self.loops, self.hz, _ = notes(self.ff3_m1, cmd)
        self.report = {'cmd': cmd, 'warnings': []}
        self.pitch_table()

    def warn(self, s): self.report['warnings'].append(s)

    # -- FM pitch: KOF98 note n -> (block, F-number) ($2447: $2BC8 note table, $2A68 F-number words)
    def pitch_table(self):
        m = self.m1; self.pitch = {}
        for n in range(0x80):
            v = m[0x2BC8 + n]
            if v >= 0xC0: continue
            idx = ((v & 0xF0) >> 1) & 0xFF
            self.pitch[n] = (v & 7, m[0x2A68 + idx] | m[0x2A69 + idx] << 8)

    def fm_note(self, word):
        blk, fn = word >> 11 & 7, word & 0x7FF
        best = min(((abs(fn - f), n, fn - f) for n, (b, f) in self.pitch.items() if b == blk), default=None)
        if best is None or best[0] > 127: raise ValueError(f'F-number {word:04X} out of reach')
        return best[1], best[2]

    # -- samples: FF3 V pages -> free KOF98 V pages
    def place_samples(self):
        a_s = sorted({(n.start, n.end) for ch in self.notes if ch.startswith('A') for n in self.notes[ch]})
        b_s = sorted({(n.start, n.end) for n in self.notes.get('B', [])})
        runs = [list(r) for r in json.load(open(FREE_V))]
        self.vmap = {}
        for st, en in sorted(set(a_s) | set(b_s), key=lambda r: r[0] - r[1]):     # largest first
            size = en - st + 1
            run = next((r for r in sorted(runs, key=lambda r: r[1] - r[0]) if r[1] - r[0] + 1 >= size), None)
            if run is None: raise ValueError(f'no V space for {size * 256} bytes')
            dst = run[0]; run[0] += size
            self.v[dst << 8:(en - st + 1 + dst) << 8] = self.ff3_v[st << 8:(en + 1) << 8]
            self.vmap[(st, en)] = (dst, dst + size - 1)
        self.report['samples'] = {'adpcm_a': len(a_s), 'adpcm_b': len(b_s),
                                  'bytes': sum((e - s + 1) * 256 for s, e in self.vmap)}
        # ADPCM-A: empty codes of the KOF98 tables, not played by any KOF98 song
        free = [(sl, c) for sl in A_SLOTS for c in range(256)
                if self.m1[A_TABLES[sl] + 6 * c + 1:A_TABLES[sl] + 6 * c + 5] == bytes(4)]
        if len(free) < len(a_s): raise ValueError('not enough free ADPCM-A codes')
        self.acode = {}
        for (st, en), (sl, c) in zip(a_s, free):
            ns, ne = self.vmap[(st, en)]
            r = A_TABLES[sl] + 6 * c
            self.m1[r:r + 6] = bytes([0x7F]) + w16(ns) + w16(ne) + bytes([0xDF])
            self.acode[(st, en)] = (sl, c)
        # ADPCM-B: instruments 1-6 -> records 1-6 (KOF98 placeholders), [prio][start][end][loops 0][ls][le][dn][$80]
        if len(b_s) > 6: raise ValueError('more than 6 ADPCM-B samples')
        imap = self.m1[0x2E08] | self.m1[0x2E09] << 8; recs = self.m1[0x2E1E] | self.m1[0x2E1F] << 8
        self.binst = {}
        for i, (st, en) in enumerate(b_s, 1):
            assert self.m1[imap + i] == i
            ns, ne = self.vmap[(st, en)]
            r = recs + 13 * i
            self.m1[r:r + 13] = bytes([0x7F]) + w16(ns) + w16(ne) + bytes([0]) + w16(0) + w16(0xFFFF) + w16(0x6EB3) + bytes([0x80])
            self.binst[(st, en)] = i
        dn = [self.m1[0x2B2A + 2 * i] | self.m1[0x2B2B + 2 * i] << 8 for i in range(96)]
        self.bnote = {}
        for v in {n.deltan for n in self.notes.get('B', [])} | {c[2] for n in self.notes.get('B', []) for c in n.changes if c[1] == 'bslur'}:
            if v in dn: i = dn.index(v)
            else:
                i = min(range(96), key=lambda j: abs(math.log(dn[j] / v)) if dn[j] else 9)
                self.warn(f'ADPCM-B delta-N {v:04X} not in KOF98\'s table: {dn[i]:04X} used, '
                          f'{1200 * math.log2(dn[i] / v):+.1f} cents')
            self.bnote[v] = (i // 12) << 4 | i % 12

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
                st = {'patch': st.get('patch')}                          # for both ways in) re-emitted after it
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
            if kind == 'slur':                                           # ADPCM-B: tie into the new pitch / volume
                b = self.bnote[mo[2]]
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
                if st.get('det') != det: out += ev(None, 0x2E, (det + 0x40) & 0xFF); st['det'] = det
                out += ev(delta, 0x00, *vl(gate), note, n.tl); st['vel'] = n.tl
            elif name.startswith('A'):
                sl, code = self.acode[(n.start, n.end)]
                if st.get('slot') != sl: out += ev(None, 0x0D, sl); st['slot'] = sl
                pan = n.level & 0xC0
                if st.get('pan') != pan: out += ev(None, PAN_OP[pan]); st['pan'] = pan
                out += ev(delta, 0x00, *vl(gate), code, n.level & 0x1F); st['vel'] = n.level & 0x1F
            else:
                if st.get('mode') is None: out += ev(None, 0x0F, 0); st['mode'] = 0
                inst = self.binst[(n.start, n.end)]
                if st.get('inst') != inst: out += ev(None, 0x03, inst); st['inst'] = inst
                if st.get('pan') != n.pan: out += ev(None, PAN_OP[n.pan]); st['pan'] = n.pan
                out += ev(delta, 0x00, *vl(gate), self.bnote[n.deltan], n.vol); st['vel'] = n.vol
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
        return nxt[1] in ('slur', 'level') or (nxt[1] == 'note' and getattr(nxt[2], 'legato', False))

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
        assert self.m1[0x243F:0x2442] == bytes([0xCD, 0x38, 0x15])
        self.m1[0x2440:0x2442] = bytes([0xB6, 0x14])
        self.patch_at = {}
        for it in range(12):
            song = self.build_once()
            moved = self.spread_patches()
            if not moved: break
        self.report['heaviest_tick_writes'] = self.max_load
        return song

    def tick_loads(self, m1):
        """writes per sequencer tick in KOF98's model of the song (both passes of the loop)"""
        import song98, regs98
        s = song98.Song(bytes(m1), CMD).run(ticks=2 * max(a + b for a, b in self.loops.values()) + 2)
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
        head[11] = round(self.hz * 208 / 166.83 / (1 - LOST)); head[12] = head[13] = 0
        body = bytearray(); addr = SONG_Z80 + len(head)
        for n in names:
            s = self.channel(n, addr)
            head[14 + 2 * CHAN_K[n]:16 + 2 * CHAN_K[n]] = w16(addr)
            body += s; addr += len(s)
        song = bytes(head) + bytes(body)
        if SONG_AT + len(song) > SONG_END: raise ValueError(f'song too long: {len(song)} bytes')
        if not hasattr(self, 'blank'): self.blank = bytes(self.m1[SONG_AT:SONG_END])
        assert all(b == 0xFF for b in self.blank[:len(song)])
        self.m1[SONG_AT:SONG_END] = self.blank
        self.m1[SONG_AT:SONG_AT + len(song)] = song
        i = CMD - 0x20
        self.m1[0x329E + 2 * i:0x329E + 2 * i + 2] = w16(SONG_Z80)
        bt = self.m1[0x2E06] | self.m1[0x2E07] << 8
        self.m1[bt + i] = BANKSET
        self.report['vmap'] = {json.dumps(list(k)): list(v) for k, v in self.vmap.items()}
        self.report.update(song_bytes=len(song), tempo=head[11], kof98_hz=166.83 * head[11] / 208,
                           kof98_hz_after_losses=166.83 * head[11] / 208 * (1 - LOST), ff3_hz=self.hz,
                           channels=names)
        return song

if __name__ == '__main__':
    cmd = int(sys.argv[1], 16); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    p = Port(cmd); p.build()
    open(f'{out}/kof98_m1.bin', 'wb').write(p.m1); open(f'{out}/kof98_v1.bin', 'wb').write(p.v)
    json.dump(p.report, open(f'{out}/port_{cmd:02X}.json', 'w'), indent=1)
    print(json.dumps(p.report, indent=1))
