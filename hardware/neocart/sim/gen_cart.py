#!/usr/bin/env python3
"""Generate NeoCart PROG CPLD schematic with individual gold finger pins."""
import os

out = os.path.expanduser("~/CLProjects/NeoGeo/hardware/neocart/sim/neocart_cart.dig")

elements = []
wires = []

def inp(label, x, y, bits=1, fmt=None, default=None):
    a = f'<entry><string>Label</string><string>{label}</string></entry>'
    if bits > 1: a += f'<entry><string>Bits</string><int>{bits}</int></entry>'
    if fmt: a += f'<entry><string>intFormat</string><intFormat>{fmt}</intFormat></entry>'
    if default is not None: a += f'<entry><string>InDefault</string><value v="{default}" z="false"/></entry>'
    elements.append(f'<visualElement><elementName>In</elementName><elementAttributes>{a}</elementAttributes><pos x="{x}" y="{y}"/></visualElement>')

def out_pin(label, x, y, bits=1, fmt=None):
    a = f'<entry><string>Label</string><string>{label}</string></entry>'
    if bits > 1: a += f'<entry><string>Bits</string><int>{bits}</int></entry>'
    if fmt: a += f'<entry><string>intFormat</string><intFormat>{fmt}</intFormat></entry>'
    elements.append(f'<visualElement><elementName>Out</elementName><elementAttributes>{a}</elementAttributes><pos x="{x}" y="{y}"/></visualElement>')

def comp(name, attrs, x, y):
    a = ''.join(f'<entry><string>{k}</string>{v}</entry>' for k,v in attrs.items())
    elements.append(f'<visualElement><elementName>{name}</elementName><elementAttributes>{a}</elementAttributes><pos x="{x}" y="{y}"/></visualElement>')

def wire(x1, y1, x2, y2):
    wires.append(f'<wire><p1 x="{x1}" y="{y1}"/><p2 x="{x2}" y="{y2}"/></wire>')

# === GOLD FINGER INPUTS: Address bus A1-A19 ===
for i in range(19):
    inp(f"A{i+1}", 60, 40 + i*24)

# === Control signals from gold fingers ===
ctrl_y = 520
inp("nAS", 60, ctrl_y, default=1)
inp("ROMOEU", 60, ctrl_y + 40, default=1)
inp("nRW", 60, ctrl_y + 80, default=1)
inp("68KCLK", 60, ctrl_y + 120)

# === GOLD FINGER OUTPUTS: Data bus D0-D15 ===
for i in range(16):
    out_pin(f"D{i}", 1100, 40 + i*24)

out_pin("PDTACK", 1100, 440)
out_pin("ROMWAIT", 1100, 470)

# === Address bus combiner: 19 x 1-bit → 19-bit ===
comp("Splitter", {
    "Input Splitting": "<string>1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1</string>",
    "Output Splitting": "<string>19</string>"
}, 240, 40)

# === Data bus splitter: 16-bit → 16 x 1-bit ===
comp("Splitter", {
    "Input Splitting": "<string>16</string>",
    "Output Splitting": "<string>1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1</string>"
}, 1000, 40)

# === NOT gates for active-low ===
comp("Not", {}, 200, ctrl_y)       # nAS
comp("Not", {}, 200, ctrl_y + 40)  # ROMOEU

# === AND3: is_read = ~nAS & ~ROMOEU & nRW (nRW=1 means read) ===
comp("And", {"Inputs": "<int>3</int>"}, 320, ctrl_y)

# === NOT for DTACK_n ===
comp("Not", {}, 500, ctrl_y + 60)

# === NOR FLASH ROM ===
comp("ROM", {
    "Label": "<string>P-ROM</string>",
    "AddrBits": "<int>19</int>",
    "Bits": "<int>16</int>",
    "intFormat": "<intFormat>hex</intFormat>",
    "Data": "<data>10,f300,c0,402,c0,408,c0,40e,c0,414,0,186,0,186,0,186</data>"
}, 600, 40)

# === WIRES ===

# A1-A19 → combiner (19 inputs at pos.y + i*20)
for i in range(19):
    wire(60, 40 + i*24, 240, 40 + i*20)

# Combiner output → ROM address
wire(260, 40, 600, 40)

# nAS → NOT → AND
wire(60, ctrl_y, 200, ctrl_y)
wire(240, ctrl_y, 320, ctrl_y)

# ROMOEU → NOT → AND
wire(60, ctrl_y + 40, 200, ctrl_y + 40)
wire(240, ctrl_y + 40, 300, ctrl_y + 20)
wire(300, ctrl_y + 20, 320, ctrl_y + 20)

# nRW → AND (nRW HIGH = read, no inversion)
wire(60, ctrl_y + 80, 300, ctrl_y + 80)
wire(300, ctrl_y + 80, 300, ctrl_y + 40)
wire(300, ctrl_y + 40, 320, ctrl_y + 40)

# AND output → ROM sel
wire(380, ctrl_y + 20, 460, ctrl_y + 20)
wire(460, ctrl_y + 20, 460, 80)
wire(460, 80, 600, 80)

# AND output → NOT → PDTACK
wire(460, ctrl_y + 20, 460, ctrl_y + 60)
wire(460, ctrl_y + 60, 500, ctrl_y + 60)
wire(540, ctrl_y + 60, 1100, 440)

# ROM data out → splitter
wire(660, 60, 1000, 40)

# Splitter → D0-D15
for i in range(16):
    wire(1020, 40 + i*20, 1100, 40 + i*24)

# Write output
with open(out, 'w') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n<circuit>\n<version>1</version>\n<attributes/>\n<visualElements>\n')
    f.write('\n'.join(elements))
    f.write('\n</visualElements>\n<wires>\n')
    f.write('\n'.join(wires))
    f.write('\n</wires>\n</circuit>\n')

print(f"Written {out}")
