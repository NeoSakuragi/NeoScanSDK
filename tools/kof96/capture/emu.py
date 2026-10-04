#!/usr/bin/env python3
"""The capture interface: our emulator's recorder (`emu/neogeo_sdl --capture`, headless, the contract of the former
MAME recorder record96.lua): env SEQ / SEQ2 (inputs), POKE, RELOAD + RELOAD_STATE, SAVE, LOAD, SNAPS, OUT; output one
line per frame (both fighters' objects + P1-owned pool objects); `extra` = more env (WLOG, SNDLOG, VFRAMES, RAMDUMP...:
see the comment block in emu/neogeo_sdl.c).

    run(game, out, seq1, seq2, pokes=[], start='vs', reload=None, reload_frames=[], save=[], snaps=[], extra={})

States are files in /data/neogeo_dict/ngsdl_sta/<game>/ ('vs': a 2P fight, Kyo vs Yuri (KOF99 K' vs Shingo), saved
at frame 1500 of the boot in tools/kof96/capture/boot_ngsdl.py; c<id> / c<id>x: specials96.prep).
GAMES holds what differs per game: ROM, RAM addresses (team record ids, life copies, timer, stocks).
2026-10-04: KOF96 and KOF98 moved from MAME to our emulator. The canonical captures in /data/neogeo_dict/captures are
still the MAME ones (the re-capture in /data/neogeo_dict/captures_ngsdl is equivalent frame by frame but its brawler
export is not byte-identical: tools/kof96/README.md "Capture in our emulator")."""
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
NGSDL = os.path.join(HERE, '..', '..', '..', 'emu', 'neogeo_sdl')
NGSDL_STA = '/data/neogeo_dict/ngsdl_sta'
LIFE = (0x138, 0x13E, 0x146, 0x150)          # object offsets of the life copies (KOF96: first and last only)

GAMES = {
    # input_lag: the recorder's INPUT_LAG (1 = line n's inputs read in frame n + 1, the timing of the MAME recorder the
    # canonical KOF96 / KOF98 captures were made with; KOF99's were made in our emulator with 0)
    'kof96': {'neo': '/data/roms/kof96.neo', 'input_lag': 1, 'team': 0x10A846, 'members': 3, 'timer': 0x10A836, 'life_full': 103, 'victim': 8,
              'load_frames': 1100},
    # KOF98 'prep': specials96.prep's timeline as the first KOF98 states were made (MAME, prep98.lua): P2 walks frames
    # 21-79 and presses C 86-87, P1's C presses and the place pokes start at the load frame (positions then end the same:
    # P1 x $149, P2 $249 against the screen edges)
    'kof98': {'neo': '/data/roms/kof98.neo', 'input_lag': 1, 'team': 0x10A84E, 'members': 3, 'timer': 0x10A83A, 'life_full': 103, 'victim': 8,
              'ex': 0x10A85A, 'stock': 0x15E, 'load_frames': 1400, 'prep': {'p2': ('p2 21 59 L', 'p2 86 2 c'), 'fill_first': 0}},
    # KOF99: team record P1 $10A7F6: +4..+7 the four member ids (3 fighters + striker); P2 $10A80B. Timer $10A7E6.
    # Vs state: K' vs Shingo.
    'kof99': {'input_lag': 0, 'neo': '/data/roms/kof99.neo', 'team': 0x10A7FA, 'members': 4, 'timer': 0x10A7E6,
              'life_full': 101, 'victim': 3, 'stock': 0x15F, 'load_frames': 700,      # stock count +$15F (+$15E = 4)
              'fill_frames': 2400},             # enough hits for 3 stocks: SDMs (DM motion + A+C / B+D) need 3
}

def state_ref(game, name):
    """the state file"""
    d = os.path.join(NGSDL_STA, game); os.makedirs(d, exist_ok=True)
    return os.path.join(d, f'{name}.state')

def state_exists(game, name): return os.path.exists(state_ref(game, name))

def life_pokes(game, base, value):
    offs = (0x138, 0x150) if game == 'kof96' else LIFE
    return ','.join(f'{base + o:X}={value >> 8:02X},{base + o + 1:X}={value & 255:02X}' for o in offs)

def swap_pokes(game, cid, ex=False):
    """frame-2 pokes: P1's team ids = cid, P1 life 1 (P2's next hit ends the round and loads cid)"""
    g = GAMES[game]
    p = [life_pokes(game, 0x108100, 1)] + [f'{g["team"] + k:X}={cid:02X}' for k in range(g['members'])]
    if ex and 'ex' in g: p.append(f'{g["ex"]:X}=07')
    return ','.join(p)

def run(game, out, seq1, seq2='', pokes=(), start='vs', reload=None, reload_frames=(), save=(), snaps=(), snapdir=None,
        timeout=1800, extra=None):
    g = GAMES[game]
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, POKE=';'.join(pokes), OUT=out, INPUT_LAG=str(g['input_lag']), **(extra or {}))
    if reload: env.update(RELOAD=','.join(map(str, reload_frames)), RELOAD_STATE=state_ref(game, reload))
    if save: env['SAVE'] = ';'.join(f'{f}:{state_ref(game, n)}' for f, n in save)
    if snaps: env.update(SNAPS=','.join(map(str, snaps)), SNAPDIR=snapdir or '/tmp')
    if not state_exists(game, start): raise FileNotFoundError(state_ref(game, start))
    env['LOAD'] = state_ref(game, start)
    subprocess.run([NGSDL, g['neo'], '--capture'], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=timeout)
    return out
