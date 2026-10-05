#!/usr/bin/env python3
"""Kim's sounds per move: every sound command the game sent while each captured move played (capture_kz.py rows:
SNDLOG, the bytes the 68000 writes to REG_SOUND, as prefix + code pairs), each played by Kizuna's own driver in the
tap core (tools/brawler/voices.py probe: our core with a Z80 port tap, the game's commands blocked after its $07 at
frame 872): the ADPCM-A channel it keys on, the level, the sample's start / end; the WAV = those V ROM bytes decoded.

    python3 voices_kz.py          -> /data/neogeo_dict/kizuna/kim_voices.json, /data/neogeo_dict/voices/wav/kim/<word>.wav

A word several moves share (the swings, hits) is an effect; the voices are the words only Kim's moves send (prefix $1C
here: P1's voice slot)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'brawler')); sys.path.insert(0, os.path.join(HERE, '..', 'kof96'))
import voices, rom96, kz

CAP = '/data/neogeo_dict/kizuna/kim_capture.json'
OUT = '/data/neogeo_dict/kizuna/kim_voices.json'
WAV = '/data/neogeo_dict/voices/wav/kim'
PREFIXES = (0x18, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E)
rom96.GAMES['kizuna'] = {'neo': kz.NEO}; voices.BLOCK['kizuna'] = 880

def words_of(frames):
    """(frame, prefix << 8 | code): the game writes one byte a frame from its queue, the prefix then the code"""
    stream = [(i, b) for i, f in enumerate(frames) for b in (f[3] if len(f) > 3 else [])]
    out, k = [], 0
    while k < len(stream):
        if stream[k][1] in PREFIXES and k + 1 < len(stream): out.append((stream[k][0], stream[k][1] << 8 | stream[k + 1][1])); k += 2
        else: k += 1
    return out

def main():
    cap = json.load(open(CAP))
    per_move = {rec: words_of(d['frames']) for rec, d in cap.items()}
    words = sorted({w for v in per_move.values() for _, w in v})
    hits = voices.probe('kizuna', words)
    v = voices.v_rom('kizuna')
    listing = {}
    for w in words:
        h = hits.get(w)
        moves = sorted(r for r, ws in per_move.items() if any(x == w for _, x in ws))
        ent = {'word': f'{w:04X}', 'moves': moves}
        if h:
            ms = voices.write_wav(os.path.join(WAV, f'{w:04X}.wav'), v, h['segments'])
            ent.update(channel=h['ch'], level=h['level'], segments=h['segments'], ms=ms, wav=os.path.join(WAV, f'{w:04X}.wav'))
        listing[f'{w:04X}'] = ent
    res = {'about': __doc__.split('\n\n')[0], 'sounds': listing,
           'per_move': {r: [[i, f'{w:04X}'] for i, w in ws] for r, ws in per_move.items() if ws}}
    json.dump(res, open(OUT, 'w'), indent=1)
    for w, e in listing.items(): print(w, e.get('ms'), 'ms', 'ch', e.get('channel'), len(e['moves']), 'moves', e['moves'][:5])

if __name__ == '__main__':
    main()
