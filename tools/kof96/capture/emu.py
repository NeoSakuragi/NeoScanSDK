#!/usr/bin/env python3
"""One capture interface over two emulators. Both implement the same recorder contract (record96.lua in MAME,
`neogeo_sdl --capture` in our emulator): env SEQ / SEQ2 (inputs), POKE, RELOAD + RELOAD_STATE, SAVE, LOAD (ngsdl) /
-state (MAME), SNAPS, OUT; output one line per frame (both fighters' objects + P1-owned pool objects).

    run(game, out, seq1, seq2, pokes=[], start='vs', reload=None, reload_frames=[], save=[], snaps=[])

States: MAME uses named states in ~/.mame/sta/<game>/; neogeo_sdl uses files in /data/neogeo_dict/ngsdl_sta/<game>/.
GAMES holds what differs per game: emulator, ROM set, RAM addresses (team record ids, life copies, timer, stocks)."""
import os, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
REC96 = os.path.join(HERE, 'record96.lua')
NGSDL = os.path.join(HERE, '..', '..', '..', 'emu', 'neogeo_sdl')
MAME_ROMPATH = '/home/bruno/roms/neogeo;/home/bruno/Downloads'
NGSDL_STA = '/data/neogeo_dict/ngsdl_sta'
LIFE = (0x138, 0x13E, 0x146, 0x150)          # object offsets of the life copies (KOF96: first and last only)

GAMES = {
    'kof96': {'emu': 'mame', 'team': 0x10A846, 'members': 3, 'timer': 0x10A836, 'life_full': 103, 'victim': 8,
              'load_frames': 1100},
    'kof98': {'emu': 'mame', 'team': 0x10A84E, 'members': 3, 'timer': 0x10A83A, 'life_full': 103, 'victim': 8,
              'ex': 0x10A85A, 'stock': 0x15E, 'load_frames': 1400},
    # KOF99 runs in our emulator (MAME has no set for it here and cannot run a .neo). Team record P1 $10A7F6:
    # +4..+7 the four member ids (3 fighters + striker); P2 $10A80B. Timer $10A7E6. Vs state: K' vs Shingo.
    'kof99': {'emu': 'ngsdl', 'neo': '/data/roms/kof99.neo', 'team': 0x10A7FA, 'members': 4, 'timer': 0x10A7E6,
              'life_full': 101, 'victim': 3, 'stock': 0x15F, 'load_frames': 700,      # stock count +$15F (+$15E = 4)
              'fill_frames': 2400},             # enough hits for 3 stocks: SDMs (DM motion + A+C / B+D) need 3
}

def state_ref(game, name):
    """what the emulator wants for a state: MAME a name, neogeo_sdl a file path"""
    if GAMES[game]['emu'] == 'mame': return name
    d = os.path.join(NGSDL_STA, game); os.makedirs(d, exist_ok=True)
    return os.path.join(d, f'{name}.state')

def state_exists(game, name):
    if GAMES[game]['emu'] == 'mame': return os.path.exists(os.path.expanduser(f'~/.mame/sta/{game}/{name}.sta'))
    return os.path.exists(state_ref(game, name))

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
        timeout=1800):
    g = GAMES[game]
    env = dict(os.environ, SEQ=seq1, SEQ2=seq2, POKE=';'.join(pokes), OUT=out)
    if reload: env.update(RELOAD=','.join(map(str, reload_frames)), RELOAD_STATE=state_ref(game, reload))
    if save: env['SAVE'] = ';'.join(f'{f}:{state_ref(game, n)}' for f, n in save)
    if snaps: env.update(SNAPS=','.join(map(str, snaps)), SNAPDIR=snapdir or '/tmp')
    if g['emu'] == 'mame':
        cmd = ['mame', game, '-rompath', MAME_ROMPATH, '-state', start, '-video', 'none', '-sound', 'none', '-nothrottle',
               '-skip_gameinfo', '-noplugin', 'cart_bridge', '-autoboot_script', REC96]
    else:
        env['LOAD'] = state_ref(game, start)
        cmd = [NGSDL, g['neo'], '--capture']
    subprocess.run(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout)
    return out
