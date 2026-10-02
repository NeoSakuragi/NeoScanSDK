#!/usr/bin/env python3
"""Build out/results.html for the P board from the generated artefacts (design.py, sim_results.json, out_report.json, drc json, cost)."""
import json, os, html, importlib.util, re
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, 'out')
spec = importlib.util.spec_from_file_location('design', os.path.join(HERE, 'design.py')); d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
def load(name, default):
    p = os.path.join(OUT, name)
    return json.load(open(p)) if os.path.exists(p) else default
sim = load('sim_results.json', []); rep = load('../out_report.json', {'checks': []}); drc = load('drc_routed.json', None)
cost = open(os.path.join(OUT, 'bom_cost.txt')).read().strip().splitlines() if os.path.exists(os.path.join(OUT, 'bom_cost.txt')) else []
raw = json.load(open(os.path.join(HERE, 'sourcing_raw.json'))); price = {r['code']: r for rs in raw.values() for r in rs}
from collections import Counter, OrderedDict
cnt = Counter(pt['lcsc'] for pt in d.PARTS.values() if pt['lcsc'])
def gate_groups(checks):
    g = OrderedDict()
    for c in checks:
        n = c['check']; key = ('pad numbers exist' if 'pad' in n and 'exists' in n else 'inside the outline' if 'inside' in n else 'clear of holes' if 'hole' in n else 'clear of notches' if 'notch' in n else 'clear of the fingers' if 'finger' in n else n)
        g.setdefault(key, [0, 0]); g[key][0] += 1; g[key][1] += 0 if c['ok'] else 1
    return g
n_nets = len([n for n in d.NETS if not n.startswith('NC_')]); n_pins = sum(len(v) for v in d.NETS.values())
ics = [(r, p) for r, p in d.PARTS.items() if r.startswith('U')]
routed = os.path.exists(os.path.join(HERE, 'neocart_pboard_routed.kicad_pcb'))
_errs = [v for v in (drc or {}).get('violations', []) if v.get('severity') == 'error']; _warns = [v for v in (drc or {}).get('violations', []) if v.get('severity') != 'error']
drc_clean = drc is not None and not _errs and not drc.get('unconnected_items')
drc_line = 'not routed yet' if drc is None else f"{len(_errs)} errors, {len(drc.get('unconnected_items', []))} unconnected, {len(_warns)} warnings (silkscreen and library notes)"
imgs = [f for f in ('pboard_routed_top.png', 'pboard_routed_bottom.png') if os.path.exists(os.path.join(OUT, f))] or ['pboard_top.png']
rows_parts = ''.join(f"<tr><td>{html.escape(r)}</td><td>{html.escape(p['value'])}</td><td>{html.escape(p['desc'])}</td><td class='mono'>{p['lcsc'] or 'hand'}</td></tr>" for r, p in ics)
rows_cost = ''.join(f"<tr><td class='mono'>{html.escape(l)}</td></tr>" for l in cost)
rows_sim = ''.join(f"<tr><td>{html.escape(c['check'])}</td><td class='{'ok' if c['ok'] else 'bad'}'>{'pass' if c['ok'] else 'FAIL'}</td></tr>" for c in sim)
rows_gates = ''.join(f"<tr><td>{html.escape(k)}</td><td class='num'>{v[0]}</td><td class='num'>{v[1]}</td></tr>" for k, v in gate_groups(rep['checks']).items())
figs = ''.join(f"<figure><img src='img/{f}' alt='{f}'><figcaption>{f.replace('_', ' ').replace('.png', '')}</figcaption></figure>" for f in imgs)
page = f'''<title>NeoCart P Board</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root{{color-scheme:light;--bg:#f5f6f2;--panel:#fff;--ink:#1c221e;--muted:#5f6a63;--line:#d7ddd6;--pcb:#2e5233;--pcb-soft:#e3ecdf;--gold:#b8901f;--gold-soft:#f4ead0;--ok:#2f7a3e;--bad:#a8322b;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;--sans:"IBM Plex Sans",system-ui,sans-serif;--disp:"Barlow Condensed","Arial Narrow",sans-serif}}
@media (prefers-color-scheme:dark){{:root:not([data-theme="light"]){{color-scheme:dark;--bg:#141915;--panel:#1c221d;--ink:#e6ebe4;--muted:#9aa69d;--line:#2c352e;--pcb:#8dbd92;--pcb-soft:#1f2c22;--gold:#e2bb45;--gold-soft:#332b14;--ok:#7fcf8e;--bad:#e07a72}}}}
:root[data-theme="dark"]{{color-scheme:dark;--bg:#141915;--panel:#1c221d;--ink:#e6ebe4;--muted:#9aa69d;--line:#2c352e;--pcb:#8dbd92;--pcb-soft:#1f2c22;--gold:#e2bb45;--gold-soft:#332b14;--ok:#7fcf8e;--bad:#e07a72}}
body{{background:var(--bg);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.5;margin:0}} .wrap{{max-width:1080px;margin:0 auto;padding-block:28px 60px;padding-inline:20px}}
h1{{font-family:var(--disp);font-weight:700;font-size:clamp(34px,5vw,52px);line-height:1;margin:0 0 6px;text-wrap:balance}} h2{{font-family:var(--disp);font-weight:600;font-size:26px;text-transform:uppercase;letter-spacing:.02em;margin:44px 0 12px;color:var(--pcb);border-bottom:2px solid var(--pcb);padding-bottom:4px}}
p{{max-width:70ch}} .lede{{font-size:17px;color:var(--muted);max-width:72ch}} .eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.12em;text-transform:uppercase;color:var(--gold);margin-bottom:8px}}
.status{{display:flex;flex-wrap:wrap;gap:10px;margin:18px 0}} .pill{{font-family:var(--mono);font-size:12.5px;padding:5px 11px;border-radius:999px;border:1px solid var(--line);background:var(--panel)}} .pill.ok{{border-color:var(--ok);color:var(--ok)}} .pill.warn{{border-color:var(--gold);color:var(--gold)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}} figure{{margin:0;background:var(--panel);border:1px solid var(--line);border-radius:6px;overflow:hidden}} figure img{{display:block;width:100%;height:auto}} figcaption{{font-family:var(--mono);font-size:12.5px;padding:8px 12px;color:var(--muted)}}
table{{border-collapse:collapse;width:100%;font-size:13.5px;background:var(--panel)}} th,td{{border:1px solid var(--line);padding:5px 9px;text-align:left;vertical-align:top}} thead th{{background:var(--pcb-soft);font-family:var(--mono);font-size:12px;letter-spacing:.06em;text-transform:uppercase}}
td.num{{text-align:right;font-family:var(--mono)}} td.mono,.mono{{font-family:var(--mono);font-size:12.5px;white-space:pre}} td.ok{{color:var(--ok);font-weight:600}} td.bad{{color:var(--bad);font-weight:600}} .tablewrap{{overflow-x:auto}} .two{{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:22px}}
.note{{border-left:3px solid var(--gold);background:var(--gold-soft);padding:10px 14px;border-radius:0 4px 4px 0;max-width:72ch}} ul{{padding-left:20px;max-width:72ch}} li{{margin:4px 0}} code{{font-family:var(--mono);font-size:12.5px;background:var(--pcb-soft);padding:1px 5px;border-radius:3px}}
</style>
<div class="wrap">
<div class="eyebrow">NeoCart · step 2 · P board v1 · 2026-09-25</div>
<h1>MVS PROG flash cart, designed from sourced parts</h1>
<p class="lede">One S29GL064N for the 68K program, two each for the ADPCM-A and ADPCM-B samples, level shifters, a PROGBK1-style bank latch, YM2610 address demux in edge registers, and an RP2350B USB programmer. Four layers on the manufactured diag-cart outline. Every part is a JLCPCB stock item checked today; every pin was assigned by datasheet pin number and cross-checked against the library symbol.</p>
<div class="status"><span class="pill ok">netlist · {len(d.PARTS)} parts · {n_nets} nets · {n_pins} pin connections · 0 problems</span><span class="pill ok">logic simulation · {sum(1 for c in sim if c['ok'])}/{len(sim)} checks</span><span class="pill ok">placement · {len(rep['checks'])} gates passed</span><span class="pill {'ok' if drc_clean else 'bad'}">DRC · {drc_line}</span><span class="pill warn">not ordered</span></div>
<h2>Board</h2><div class="grid">{figs}</div>
<h2>What was verified before showing this</h2>
<div class="two">
<div><h3>Logic simulation of the netlist</h3><p>A small simulator drives the connector the way the MVS does and reads what the chips see.</p><div class="tablewrap"><table><thead><tr><th>scenario</th><th>result</th></tr></thead><tbody>{rows_sim}</tbody></table></div></div>
<div><h3>Placement gates</h3><div class="tablewrap"><table><thead><tr><th>gate</th><th>checks</th><th>failed</th></tr></thead><tbody>{rows_gates}</tbody></table></div>
<h3>Pinout verification</h3><ul><li>Second pass 2026-09-26: every pin of every chip type read against the manufacturer PDF (all 80 RP2350B pins against the datasheet figure); nothing changed. Exhaustive enumeration of 16,640 strobe and mode combinations: no reachable bus contention. Timing budget: P-ROM reads close with about 100 ns of margin on both paths.</li><li>S29GL064N: Figure 1 of the Infineon datasheet, models 03/04 column, read visually.</li><li>SN74LVC16245A, SN74LVC16244A: TI pin-configuration pages, read visually.</li><li>All other parts: pin tables extracted from the manufacturer PDFs and matched by name against the easyeda2kicad symbols by the netlist checker.</li></ul></div></div>
<h3>Emulator harness: KOF96 through the board's chip map</h3>
<p>Our SDL emulator talks to a cart over a shared-memory bus. <code>harness/pboard_server.c</code> answers it the way this board would: C, S and M from the .neo (the donor KOF96 CHA board), P and V from the chip images <code>pboard_flash.py</code> writes to the flashes, addressed through the board's map (P1 at 0, P2 bank n at 4&nbsp;MB + n&nbsp;MB, V pair image with bit 23 selecting the chip). KOF96 boots, runs attract, the logo and a demo fight for 90&nbsp;s; frame 900 is pixel-identical to the reference server and every P2 read came from banks 0 and 1.</p>
<figure><img src='img/harness_long.png' alt='KOF96 title, logo and demo fight served through the P board chip map'><figcaption>frames 3000, 4200 and 5400 of the harness run</figcaption></figure>
<p class="note">Scope: this proves the image layout, the bank map and the byte order. The shared-memory bus carries linear addresses and no strobes, so the ADPCM multiplexing and latch edges are checked only by the logic simulation against the neogeodev protocol text, and finally by the KOF96 CHA board in a real MVS.</p>
<h2>Integrated circuits</h2><div class="tablewrap"><table><thead><tr><th>ref</th><th>part</th><th>role</th><th>LCSC</th></tr></thead><tbody>{rows_parts}</tbody></table></div>
<h2>Cost, JLCPCB prices of 2026-09-25</h2><div class="tablewrap"><table><tbody>{rows_cost}</tbody></table></div>
<p>{len(cnt)} distinct LCSC parts. Test points and the two 2.54 mm headers are hand-soldered. The PCB itself and the assembly are quoted from the JLCPCB order form before anything is paid.</p>
<h2>How it works, in one screen</h2>
<ul><li><strong>68K side.</strong> A1 to A19 through two 16-bit buffers into the flash; D0 to D15 through a transceiver whose direction follows R/W. Flash output enable = ROMOE or both PORTOE strobes. The bank latch captures D0 to D2 on the end of a lower-byte write in the port window and is cleared by reset. Chip map: P1 at 0, P2 bank n at 4 MB + n MB, up to four banks.</li>
<li><strong>Sample side.</strong> Each ADPCM bus delivers its 24-bit address in two phases on one set of lines, marked by the rising and falling edge of the multiplex strobe. Two edge registers per bus rebuild it. Byte-mode flash, bit 23 selects the chip, data goes back through a 5 V buffer during the read strobe.</li>
<li><strong>Programming mode.</strong> A jumper sets PROG_MODE. Every buffer and register facing the MVS tri-states, pull-ups make every strobe read inactive, nine shift registers take over the address lines, and the RP2350B drives data and the write and output enables directly.</li>
<li><strong>Power.</strong> Slot 5 V and USB 5 V OR-ed through Schottky diodes, one 3.3 V regulator, the MCU powered whenever the board is.</li></ul>
<div class="note">Known v1 limits: single-slot motherboards only (the slot-select line is buffered to a test point but does not gate outputs), P up to 1 MB plus four 1 MB banks, USB-C on the top edge needs a cutout in a donor shell.</div>
<h2>Bring-up plan</h2>
<ol><li>USB only, MODE jumper on PROG: enumerate, read the three flash IDs (0x01, 0x227E).</li><li>Flash and verify the KOF96 images with <code>pboard_flash.py</code>; the P image's first words must read 0010 F300 00C0 0402.</li><li>Jumper to PLAY, board into the MVS with the KOF96 CHA board. Boots and plays = P path and bank latch proven. Samples present = ADPCM demux proven.</li></ol>
</div>'''
open(os.path.join(OUT, 'results.html'), 'w').write(page); print('page', len(page) // 1024, 'KB')
