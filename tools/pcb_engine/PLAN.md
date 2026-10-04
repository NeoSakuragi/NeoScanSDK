# AI PCB Design Engine — Project Plan

## The Problem
An AI can design circuits (architecture, pin assignments, net lists) but cannot
produce physical PCBs. The gap is a clean programmatic interface between
"these pins connect to those pins" and "here are your Gerber files."

## The Solution
A Python library that takes a verified netlist + component list and produces
manufacturing-ready PCB files. No GUI needed. AI-friendly API.

## Who uses it
Claude Code (or any AI) describes the circuit → library produces the PCB.
Bruno (or any human) reviews, tweaks, orders.

## Target projects (Bruno's immediate needs)
1. MVS dev cart — FPGA + SDRAM serving P/V ROM to Neo Geo motherboard
2. FPGA Neo Geo console — full Neo Geo clone playing real MVS carts
3. VGA → SCART adapter — R2R DAC + sync combiner
4. VGA → HDMI with CRT shader — scaler FPGA + HDMI encoder
5. Any future small board — the engine makes them all trivial

---

## Architecture

```
┌─────────────────────────────────────┐
│           User / AI                  │
│  "connect FPGA pin 73 to SDRAM DQ0" │
└──────────────┬──────────────────────┘
               │
        Python API (our library)
               │
    ┌──────────┼──────────────┐
    │          │              │
    ▼          ▼              ▼
Schematic   Placement      Routing
Engine      Engine         Engine
    │          │              │
    ▼          ▼              ▼
 Netlist    Component     Trace
 (.net)     positions     geometry
    │          │              │
    └──────────┼──────────────┘
               │
          DRC Engine
               │
          Export Engine
          │    │    │
        Gerber BOM  CPL
        (.gbr) (.csv)(.csv)
```

---

## Modules to build

### Module 1: Component Database
**What:** A library of components with real pin maps from datasheets.
**Input:** Datasheet PDF or LCSC part number
**Output:** Python object with pin names, functions, package dimensions

```python
from pcb_engine import Component
sdram = Component.from_lcsc("C62246")  # W9825G6KH
print(sdram.pin(2))   # → Pin(name="DQ0", type="IO")
print(sdram.package)   # → TSOP54(width=22.2, height=10.16, pitch=0.8)
```

**Data sources:**
- KiCad footprint library (already on disk at /usr/share/kicad/footprints)
- KiCad symbol library (pin names + functions)
- LCSC API for part metadata
- Manual datasheet entries for critical parts

**Effort:** 2 weeks
**Dependencies:** None

---

### Module 2: Board & Netlist
**What:** Define a PCB with components and connections.
**Input:** Component list + net definitions
**Output:** Internal board representation with netlist

```python
from pcb_engine import Board, Net

board = Board(width_mm=174, height_mm=134, layers=4)
board.set_outline_from_kicad("path/to/outline.kicad_pcb")  # reuse proven outlines

u1 = board.place("U1", sdram, x=120, y=50)
u2 = board.place("U2", fpga, x=140, y=80)

board.net("SD_DQ0").connect(u1.pin("DQ0"), u2.pin("IO_73"))
board.net("GND").connect(u1.pin("VSS"), u2.pin("GND_8"))
# ... etc

board.power_plane("GND", layer="In1.Cu")
board.power_plane("VCC_3V3", layer="In2.Cu")
```

**Effort:** 1 week
**Dependencies:** Module 1

---

### Module 3: Placement Engine
**What:** Optimize component positions to minimize trace lengths and crossings.
**Input:** Board with components placed (user positions or auto)
**Output:** Optimized positions

```python
board.auto_place()  # or
board.optimize_placement(iterations=1000)
```

**Algorithm:** Simulated annealing or force-directed placement
- Components attract connected components (short traces)
- Components repel overlapping components (no collisions)
- Edge connectors are anchored (fixed positions)
- Decoupling caps snap to their IC

**Effort:** 2 weeks
**Dependencies:** Module 2

---

### Module 4: Routing Engine
**What:** Route all traces between connected pads.
**Input:** Board with placed components and netlist
**Output:** Board with copper traces on all layers

```python
board.route()  # auto-route all nets
board.route_net("SD_DQ0")  # route one net
```

**Algorithm options (pick one, start simple):**
1. **Lee/maze router** — guaranteed to find a path, slow. Good starting point.
2. **Channel router** — assign traces to horizontal/vertical channels. Fast.
3. **A* pathfinding** — weighted graph on a grid, avoids obstacles.

**Key features:**
- Multi-layer: use vias to switch layers
- Power nets: skip routing, handled by copper pours
- Bus routing: parallel traces for data/address buses
- DQS groups: matched length for DDR (future)

**This is the hardest module.** Start with a simple grid-based maze router,
improve later.

**Effort:** 4 weeks for basic, ongoing improvement
**Dependencies:** Module 2, Module 3

---

### Module 5: DRC Engine
**What:** Check the board for errors before manufacturing.
**Input:** Routed board
**Output:** List of violations (or clean pass)

```python
errors = board.check_drc()
for e in errors:
    print(e)  # "Clearance violation: SD_DQ0 and SD_DQ1 at (45.2, 30.1), 0.15mm < 0.2mm"
```

**Checks:**
- Trace-to-trace clearance (minimum spacing)
- Trace-to-pad clearance
- Via-to-via spacing
- Unconnected nets (orphan pads)
- Short circuits (two nets touching)
- Copper-to-edge clearance
- Drill size minimums

**Effort:** 1 week
**Dependencies:** Module 4

---

### Module 6: Export Engine
**What:** Produce manufacturing files.
**Input:** DRC-clean board
**Output:** Gerber files, drill files, BOM, CPL, 3D model

```python
board.export_gerbers("output/gerbers/")
board.export_bom("output/bom.csv", format="jlcpcb")
board.export_cpl("output/cpl.csv", format="jlcpcb")
board.export_3d("output/board.step")
board.render("output/top.png", side="top", dpi=300)
```

**Formats:**
- Gerber RS-274X (industry standard)
- Excellon drill files
- JLCPCB BOM format (Comment, Designator, Footprint, LCSC#)
- JLCPCB CPL format (Designator, X, Y, Rotation, Side)

**Effort:** 2 weeks
**Dependencies:** Module 4

---

## Timeline

```
Week 1-2:   Module 1 (Component Database)
Week 3:     Module 2 (Board & Netlist)
Week 4-5:   Module 3 (Placement Engine)
Week 6-9:   Module 4 (Routing Engine)  ← the hard one
Week 10:    Module 5 (DRC Engine)
Week 11-12: Module 6 (Export Engine)
```

**Total: ~3 months to a working prototype**

First usable output (simple 2-layer board with manual placement): **Week 6**
First production-ready output (4-layer auto-routed board): **Week 12**

---

## First test case: VGA → SCART adapter
The simplest possible board to prove the engine works:
- 1 VGA connector (DB15)
- 1 SCART connector
- 12 resistors (R2R DAC)
- 2 capacitors (audio coupling)
- 1 XOR gate (sync combiner)
- Single layer, ~5cm x 3cm

If the engine can produce this board correctly, it can scale to anything.

---

## Second test case: MVS PROG dev cart
- 1 FPGA dev board header (40-pin)
- 2x 74LVC245 (level shifters)
- 22 series resistors
- MVS edge connector (60 pins)
- 2-layer, proven outline

This is the adapter board between the Wukong and the MVS slot.

---

## Technology choices
- **Language:** Python (AI-friendly, rapid prototyping)
- **Geometry:** Shapely library (2D computational geometry)
- **Routing grid:** NumPy array (fast grid operations)
- **Gerber output:** gerber-writer or custom (RS-274X is a simple text format)
- **Footprints:** Read directly from KiCad .kicad_mod files
- **Rendering:** Cairo or Pillow for PNG output

---

## What makes this AI-friendly
1. **Text in, files out** — no GUI needed at any step
2. **Verifiable** — every connection can be checked programmatically
3. **Iterative** — place, check, adjust, re-route, check again
4. **Datasheet-driven** — pin maps come from verified databases, not guessing
5. **DRC before export** — never produces a board with known errors

---

## Open source?
Yes. This should be open source. The world needs a programmatic PCB design
library that isn't tied to any GUI. KiCad's API was an afterthought.
This would be purpose-built for automation.

Repository: github.com/NeoSakuragi/pcb-engine (proposed)
License: MIT
