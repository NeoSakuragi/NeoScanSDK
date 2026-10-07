#!/usr/bin/env python3
"""TODO #219 proof: every fighter theme of the brawler's song set (songs.json THEME_*) played by the built ROM and by its
source game, both in our emulator (capture_snd.py: the game's own driver, its command sent after power-on), the two
WAVs compared.

    python3 theme219_proof.py SND_DIR OUT_DIR [--rom ROM.neo] [--seconds S] [--only NAME,...] [--no-capture]

SND_DIR = build_snd.py's output (snd_report.json: each song's source game / command and its command in the brawler);
OUT_DIR gets src_<name>.wav / .txt (the source game) and bra_<name>.wav / .txt (the brawler) and theme219.json.
Similarity (both WAVs mixed to mono, 55,555 Hz): aligned on their first sound (the first sample above 1 % of full scale),
then cut in 1 s windows; each window's normalized cross-correlation with the other WAV at the best lag within +-60 ms
of the previous window's lag (a port's tempo differs by up to 0.1 %: the lag drifts, measured as 'drift_ms'); per song
the windows' median / 10th percentile / minimum correlation, the same for the windows' log-magnitude spectrograms
(46 ms frames to 8 kHz, dB: what is heard, insensitive to the few-ms timing of each channel's writes inside a driver
tick and to oscillator phase) and the level ratio (RMS brawler / source, dB). A KOF98 song
the brawler keeps (native) plays KOF98's own song data: 'bit_identical' tells whether the two WAVs are the same samples
after the alignment."""
import json, os, subprocess, sys, wave
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
RATE = 55555

def load(path):
    with wave.open(path) as w:
        a = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').reshape(-1, 2).astype(np.float64)
    return a.mean(axis=1)

def onset(x):
    i = np.flatnonzero(np.abs(x) > 327)
    return int(i[0]) if len(i) else 0

def spectrum(x, n=2048, hop=512):
    """log-magnitude spectrogram (dB, floor -80) of a window, bins to 8 kHz"""
    fr = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n)
    mag = np.abs(np.fft.rfft(fr, axis=1))[:, :int(8000 * n / RATE)]
    db = 20 * np.log10(mag / (n * 32768) + 1e-9)
    return np.maximum(db, db.max() - 80)

def similarity(src, bra):
    a, b = load(src), load(bra)
    a, b = a[onset(a):], b[onset(b):]
    n = min(len(a), len(b))
    exact = n > 0 and np.array_equal(a[:n], b[:n])
    W, L = RATE, int(0.06 * RATE)
    lag, cors, lags, specs = 0, [], [], []
    for s in range(0, n - W - 2 * L, W):
        x = a[s:s + W]
        if np.sqrt(np.mean(x * x)) < 30: continue                  # silence: nothing to compare
        best = (-2, lag)
        for d in range(lag - L, lag + L + 1, 8):                   # coarse search, then refine
            if s + d < 0 or s + d + W > len(b): continue
            y = b[s + d:s + d + W]
            c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
            if c > best[0]: best = (c, d)
        for d in range(best[1] - 8, best[1] + 9):
            if s + d < 0 or s + d + W > len(b): continue
            y = b[s + d:s + d + W]
            c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
            if c > best[0]: best = (c, d)
        cors.append(best[0]); lag = best[1]; lags.append(lag)
        sx, sy = spectrum(x), spectrum(b[s + lag:s + lag + W])
        if sx.std() > 0 and sy.std() > 0: specs.append(float(np.corrcoef(sx.ravel(), sy.ravel())[0, 1]))
    rms = lambda v: float(np.sqrt(np.mean(v[:n] * v[:n])) + 1e-9)
    c = np.array(cors) if cors else np.array([0.0])
    sp = np.array(specs) if specs else np.array([0.0])
    return {'seconds_compared': round(n / RATE, 1), 'windows': len(cors), 'bit_identical': bool(exact),
            'corr_median': round(float(np.median(c)), 4), 'corr_p10': round(float(np.percentile(c, 10)), 4),
            'corr_min': round(float(c.min()), 4), 'spec_median': round(float(np.median(sp)), 4),
            'spec_p10': round(float(np.percentile(sp, 10)), 4), 'level_db': round(20 * np.log10(rms(b) / rms(a)), 2),
            'drift_ms': round((lags[-1] - lags[0]) / RATE * 1000, 1) if lags else 0.0}

def main():
    a = sys.argv
    opt = lambda k, d=None: a[a.index(k) + 1] if k in a else d
    snd, out = a[1], a[2]
    os.makedirs(out, exist_ok=True)
    rep = json.load(open(f'{snd}/snd_report.json'))
    only = set(opt('--only').split(',')) if opt('--only') else None
    res = {}
    for s in rep['songs']:
        if (s['name'] not in only) if only else not s['name'].startswith('THEME_'): continue   # --only: any song (reference)
        game, scmd = s['source'].split(' $')
        cmd = s['cmd'] if isinstance(s['cmd'], int) else int(s['cmd'], 16)
        loops = s.get('loops') or {}
        hz = s.get('kof98_hz_after_losses')
        sec = float(opt('--seconds')) if opt('--seconds') else \
            min(150.0, max((x + y for x, y in loops.values()), default=3000) / hz + 2)   # intro + one loop
        name = s['name'].lower()
        if '--no-capture' not in a:
            for g, c, tag, rom in ((game, scmd, 'src', None), ('brawler', f'{cmd:02X}', 'bra', opt('--rom'))):
                subprocess.run([sys.executable, os.path.join(HERE, 'capture_snd.py'), g, c, f'{sec:.1f}', f'{out}/{tag}_{name}']
                               + (['--rom', rom] if rom else []), check=True, stdout=subprocess.DEVNULL)
        r = similarity(f'{out}/src_{name}.wav', f'{out}/bra_{name}.wav')
        r.update(source=s['source'], brawler_cmd=f'${cmd:02X}', native=bool(s.get('native')), seconds=round(sec, 1))
        res[s['name']] = r
        print(f"{s['name']:18s} {s['source']:12s} -> ${cmd:02X}  {r['seconds_compared']:6.1f} s  corr median {r['corr_median']:.4f}"
              f" p10 {r['corr_p10']:.4f} min {r['corr_min']:.4f}  spectrum median {r['spec_median']:.4f} p10 {r['spec_p10']:.4f}  level {r['level_db']:+.2f} dB  drift {r['drift_ms']:+.1f} ms"
              f"{'  BIT-IDENTICAL' if r['bit_identical'] else ''}", flush=True)
    old = json.load(open(f'{out}/theme219.json')) if os.path.exists(f'{out}/theme219.json') else {}
    old.update(res)
    json.dump(old, open(f'{out}/theme219.json', 'w'), indent=1)

if __name__ == '__main__':
    main()
