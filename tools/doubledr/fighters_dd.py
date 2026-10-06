#!/usr/bin/env python3
"""Double Dragon roster: character ids (object +$1B) [meas: select cursor -> HUD name; 1 / 3 / 12 / 13 by the voice
 commands their steps play, sound test ranges $1C-$2C Billy, $69-$79 Jimmy, $45-$4F Duke, $93-$9F Shuko], select-screen cursor moves
from Billy's square (P1), vs states (P1 = the fighter, P2 = Jimmy) made by mkvs.py at frame 1300.
1 / 3 = the transformed forms (A+B+C+D while powered, transform_dd.py); p1_01.state = transformed Billy (powered) vs Jimmy."""
CHARS = {0: 'Billy', 2: 'Jimmy', 4: 'Marian', 5: 'Abobo', 6: 'Amon', 7: 'Eddie', 8: 'Rebecca', 9: 'Dulton',
         10: 'Cheng-Fu', 11: 'Burnov', 1: 'Billy (transformed)', 3: 'Jimmy (transformed)', 12: 'Duke', 13: 'Shuko'}
MOVES = {0: '-', 11: 'D', 5: 'DD', 7: 'U', 4: 'UU', 2: 'R', 6: 'RD', 10: 'RDD', 8: 'RU', 9: 'RUU'}
STATE = '/data/neogeo_dict/doubledr/cap/p1_{:02d}.state'

if __name__ == '__main__':
    import mkvs, cap_dd as c, dd
    for ch, m in MOVES.items():
        mkvs.make(f'p1_{ch:02d}', m, '-')
        r = c.run('2:-', load=STATE.format(ch))[0]
        F = dd.fighter_fields(r['ram'], 0x10042A); G = dd.fighter_fields(r['ram'], 0x10052A)
        print(ch, CHARS[ch], 'P1 ch', F['ch'], 'pal', F['pal'], 'P2 ch', G['ch'])
