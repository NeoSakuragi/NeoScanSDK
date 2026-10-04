# PCB Design Process — Rules

Every step must PASS before the next step begins.
No step is "done" until its verification passes.
No exceptions.

## Step 1: Circuit Definition
- List every component with exact part number
- For each component, list EVERY pin with its function (from datasheet)
- Define every net: which pin connects to which pin
- **VERIFY:** count total pads, count assigned pads. They must be equal. Zero orphans.

## Step 2: Netlist Validation
- For each net, confirm it makes electrical sense (output drives input, power goes to power pins, ground to ground)
- No pin assigned to two different nets
- No net with only 1 pad (useless)
- Every power pin has a power net
- Every ground pin has GND
- **VERIFY:** automated check. Print every net, every pad. Human reviews.

## Step 3: Component Placement
- Place components on the board
- No overlaps (check bounding box collision for every pair)
- Components grouped by function (SDRAM near FPGA, decoupling near IC)
- Signal flow goes in one direction (connector → processing → memory)
- **VERIFY:** render image. Visually inspect. Check no component overlaps programmatically.

## Step 4: Routing
- Route one net at a time
- Before placing a trace segment, check EVERY cell it occupies
- If any cell is already occupied by a different net on the same layer: REJECT, find alternate path
- After placing a trace, mark its cells as occupied on that layer
- **VERIFY:** after ALL nets routed, scan entire grid. For each cell, confirm at most one net per layer. Short count must be ZERO.

## Step 5: DRC
- Minimum trace width: check every trace
- Minimum clearance: check distance between every pair of traces on same layer
- No traces outside board outline
- All nets fully connected (no broken paths)
- **VERIFY:** DRC report. Zero violations or the board does not proceed.

## Step 6: Export
- Generate Gerbers only if DRC passes with zero violations
- Generate BOM with every component
- Generate CPL with every component position
- **VERIFY:** re-import Gerbers and check layer count, board dimensions, pad count matches.

## What we were doing wrong

| Step | Should do | What we did |
|------|-----------|-------------|
| 1 | Connect every pin | Forgot USB, JTAG, RP2040, flash, crystal, buttons, DAC |
| 2 | Validate netlist | Never checked, assumed it was right |
| 3 | Check overlaps | Never checked, placed blindly |
| 4 | Reject overlapping traces | Placed traces on top of each other, 7441 shorts |
| 5 | DRC before export | Exported broken Gerbers |
| 6 | Verify exports | Never verified |

## The rule

**Nothing proceeds until the current step verifies clean.**
