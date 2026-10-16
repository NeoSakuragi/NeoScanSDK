#!/usr/bin/env python3
"""One player's play analysis as a static HTML page (Bruno 2026-10-16: "an artifact of data analysis of Wael's play"):
the event logs of tools/brawler/session_moves.py (one JSON per session) -> OUT.html, served from /brawler-admin/reports/.
    python3 player_report.py OUT.html NAME SESSION.json [SESSION.json ...]"""
import json, sys, html
from collections import Counter

NAMES = {'214D': 'Crack Shoot', '623C': 'Rising Tackle', '214C': 'Burn Knuckle', '426B': 'Blitz 426B', '623B': 'Power Dunk',
         'EX 236C': 'Power Wave', '21416C': 'Fury', '236C': 'Power Wave'}

def mmss(f): return f"{f // 3600}:{f // 60 % 60:02d}"

def session_block(d):
    ev = d['events']; frames = d['frames']
    moves = Counter(); bonus = Counter(); throws = Counter(); deaths = []; grabs = 0
    tl = []; last = None
    for e in ev:
        k = (e['stage'], e['wave'], bool(e.get('bonus')))
        if k != last and e['ev'] != 'death':
            tl.append((e['f'], 'BONUS GAME' if e.get('bonus') else (f"Stage {e['stage']} BOSS" if e['wave'] == 6 else f"Stage {e['stage']} wave {e['wave']}")))
        last = k
        if e['ev'] == 'death': deaths.append(e); tl.append((e['f'], f"✗ death (stage {e['stage']}, {'boss' if e['wave'] == 6 else 'wave ' + str(e['wave'])})"))
        elif e['ev'] == 'special':
            key = (e['kind'], e['input'])
            (bonus if e.get('bonus') else moves)[key] += 1
        elif e['ev'] == 'grab': grabs += 1
        elif e['ev'] == 'throw': throws[e['kind']] += 1
    chars = sorted({e['char'] for e in ev if e.get('char')})
    top = max((e['stage'], e['wave']) for e in ev) if ev else (0, 0)
    mx = max(list(moves.values()) + [1])
    rows = ''.join(f"<tr><td>{html.escape(NAMES.get(i, i))}</td><td class=k>{html.escape(k)} <small>({html.escape(i)})</small></td>"
                   f"<td class=n>{n}</td><td class=n>{bonus.get((k, i), 0) or ''}</td><td><span class=bar style='width:{n * 100 // mx}%'></span></td></tr>"
                   for (k, i), n in moves.most_common())
    used = {NAMES.get(ii, ii) for (_, ii) in list(moves) + list(bonus)}
    unused = [n for n in set(NAMES.values()) if n not in used]
    trs = ''.join(f"<li>{html.escape(k)}: <b>{n}</b></li>" for k, n in throws.most_common())
    tline = ''.join(f"<li><span class=t>{mmss(f)}</span> {html.escape(s)}</li>" for f, s in sorted(tl))
    return f"""
<section>
 <h2>Session {html.escape(d['session'])}</h2>
 <p class=meta>{html.escape(d.get('device', ''))} · game {html.escape(d.get('rom_version', ''))} · {mmss(frames)} of play ·
   fighter: <b>{', '.join(c.title() for c in chars)}</b> · reached <b>stage {top[0]} {'boss' if top[1] == 6 else 'wave ' + str(top[1])}</b> ·
   deaths <b>{len(deaths)}</b> · replay check: {d.get('checked', '?')} boundaries, {len(d.get('mismatches', []))} mismatches</p>
 <div class=cols>
  <div><h3>Specials</h3><table><tr><th>Move</th><th>Input</th><th>Fights</th><th>Bonus</th><th></th></tr>{rows}</table>
   <p><b>{sum(moves.values())}</b> specials in fights, <b>{sum(bonus.values())}</b> in bonus games.
   {'Never used: ' + ', '.join(sorted(set(unused))) + '.' if unused else ''}</p>
   <h3>Grabs and throws</h3><p>{grabs} grabs</p><ul>{trs}</ul></div>
  <div><h3>Timeline</h3><ul class=tl>{tline}</ul></div>
 </div>
</section>"""

def main():
    out, name, files = sys.argv[1], sys.argv[2], sys.argv[3:]
    ds = [json.load(open(f)) for f in files]
    tot_f = sum(d['frames'] for d in ds); tot_d = sum(sum(1 for e in d['events'] if e['ev'] == 'death') for d in ds)
    tot_s = sum(sum(1 for e in d['events'] if e['ev'] == 'special' and not e.get('bonus')) for d in ds)
    best = max(max((e['stage'], e['wave']) for e in d['events']) for d in ds)
    page = f"""<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(name)}: play analysis</title>
<style>
:root{{--bg:#fff;--ink:#000;--soft:#555;--line:#000}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--ink:#eee;--soft:#aaa;--line:#eee}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 system-ui,sans-serif}}
main{{max-width:980px;margin:0 auto;padding:18px 14px 40px}}
h1{{margin:0 0 4px}} h2{{font-size:18px;border-bottom:2px solid var(--line);padding-bottom:4px;margin-top:30px}} h3{{font-size:15px;margin:14px 0 6px}}
.meta{{color:var(--soft)}} .kpi{{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}}
.kpi div{{border:2px solid var(--line);border-radius:8px;padding:8px 12px;min-width:120px}} .kpi b{{display:block;font-size:22px}}
table{{border-collapse:collapse;width:100%}} td,th{{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left}} td.n{{text-align:right}}
.bar{{display:inline-block;height:10px;background:var(--ink)}} .cols{{display:grid;grid-template-columns:3fr 2fr;gap:20px}}
@media (max-width:720px){{.cols{{grid-template-columns:1fr}}}}
ul.tl{{list-style:none;padding:0;margin:0}} ul.tl li{{padding:2px 0;border-bottom:1px dotted var(--line)}} .t{{display:inline-block;width:46px;font-variant-numeric:tabular-nums}}
small{{color:var(--soft)}}
</style><main>
<h1>{html.escape(name)}: play analysis</h1>
<p class=meta>From his recorded sessions, replayed frame-exact in our emulator (tools/brawler/session_moves.py). Sessions played by Bruno on this login are left out.</p>
<div class=kpi><div>Sessions<b>{len(ds)}</b></div><div>Play time<b>{mmss(tot_f)}</b></div><div>Furthest<b>Stage {best[0]} {'boss' if best[1] == 6 else 'w' + str(best[1])}</b></div>
<div>Deaths<b>{tot_d}</b></div><div>Specials (fights)<b>{tot_s}</b></div></div>
{''.join(session_block(d) for d in ds)}
</main></html>"""
    open(out, 'w').write(page)

if __name__ == '__main__':
    main()
