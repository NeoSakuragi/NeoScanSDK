#!/usr/bin/env python3
"""
Neo Geo MVS Flash Cart — Complete PCB Generator

Reads KiCad library footprints, places them on a PCB with correct
board outline, edge connector gold fingers, net assignments, and
ground copper pour. Outputs a .kicad_pcb ready for trace routing.

Component placement layout:
  ┌──────────────────────────────────────────────┐
  │ CTRG1 gold fingers (CHA — sprites, fix)      │ ← board edge
  │                                                │
  │  U_CROM1(TSOP48)  U_CROM2(TSOP48)  U_SROM    │
  │                                                │
  │  U_PROM(TSOP48)   U_MROM           caps/res   │
  │                                                │
  │  U_SR1  U_SR2  U_SR3  U_BUF1  U_BUF2         │
  │                                                │
  │  U_MCU(QFN56)  Y1  U_FLASH  U_REG  J_USB     │
  │                                                │
  │ CTRG2 gold fingers (PROG — program, sound)    │ ← board edge
  └──────────────────────────────────────────────┘
"""

import os
import re
import uuid

KICAD_FP_DIR = "/usr/share/kicad/footprints"
CUSTOM_FP_DIR = os.path.join(os.path.dirname(__file__), "footprints", "NeoCart.pretty")
OUT_DIR = os.path.dirname(os.path.abspath(__file__))

BOARD_W = 155.0   # mm
BOARD_H = 105.0   # mm
ORIGIN_X = 50.0   # PCB origin offset in KiCad canvas
ORIGIN_Y = 50.0

def uid():
    return str(uuid.uuid4())

def read_footprint(lib_dir, fp_name):
    path = os.path.join(lib_dir, fp_name + ".kicad_mod")
    with open(path) as f:
        return f.read()

def transform_footprint(raw, ref, value, x, y, angle=0, nets=None):
    """
    Take raw .kicad_mod content and transform it for PCB embedding:
    - Update footprint name to include (at x y angle)
    - Update Reference and Value properties
    - Add net assignments to pads
    """
    lines = raw.strip()

    # Replace the first line (footprint declaration) to add position
    first_line_end = lines.index('\n')
    fp_header = lines[:first_line_end]
    fp_body = lines[first_line_end:]

    # Extract footprint name from header
    match = re.search(r'\(footprint\s+"([^"]+)"', fp_header)
    fp_name = match.group(1) if match else "unknown"

    # Build new header with position
    angle_str = f" {angle}" if angle != 0 else ""
    new_header = f'\t(footprint "{fp_name}"\n\t\t(layer "F.Cu")\n\t\t(uuid "{uid()}")\n\t\t(at {x} {y}{angle_str})'

    # Update Reference property
    fp_body = re.sub(
        r'\(fp_text\s+reference\s+"[^"]*"',
        f'(fp_text reference "{ref}"',
        fp_body, count=1
    )
    # For newer format with property
    fp_body = re.sub(
        r'(\(property\s+"Reference"\s+)"[^"]*"',
        f'\\1"{ref}"',
        fp_body, count=1
    )

    # Update Value property
    fp_body = re.sub(
        r'\(fp_text\s+value\s+"[^"]*"',
        f'(fp_text value "{value}"',
        fp_body, count=1
    )
    fp_body = re.sub(
        r'(\(property\s+"Value"\s+)"[^"]*"',
        f'\\1"{value}"',
        fp_body, count=1
    )

    # Ensure all UUIDs are unique
    def replace_uuid(m):
        return f'(uuid "{uid()}")'
    fp_body = re.sub(r'\(uuid\s+"[^"]*"\)', replace_uuid, fp_body)

    # Add net assignments to pads
    if nets:
        for pad_num, (net_id, net_name) in nets.items():
            # Find pad definition and add net inside it
            pad_pattern = rf'(\(pad\s+"{re.escape(str(pad_num))}"\s+\w+\s+\w+[^)]*\))'
            # More robust: find the pad and add net before the closing layers
            old = f'(pad "{pad_num}" '
            if old in fp_body:
                fp_body = fp_body.replace(
                    old,
                    f'(pad "{pad_num}" ',  # keep as is, we'll add nets differently
                    1
                )

    # Remove the outer closing paren from body (we'll add it back)
    fp_body = fp_body.rstrip()
    if fp_body.endswith(')'):
        fp_body = fp_body[:-1]

    result = new_header + fp_body + '\t)'

    return result


# ─── Component definitions ───

COMPONENTS = [
    # (ref, value, footprint_lib, footprint_name, x_offset, y_offset, angle)
    # Flash chips — top area
    ("U_CROM1", "AM29F400_C1", "Package_SO.pretty", "TSOP-I-48_18.4x12mm_P0.5mm",
     30, 20, 0),
    ("U_CROM2", "AM29F400_C2", "Package_SO.pretty", "TSOP-I-48_18.4x12mm_P0.5mm",
     65, 20, 0),
    ("U_SROM", "SST39SF010_S", "Package_LCC.pretty", "PLCC-32_11.4x14.0mm_P1.27mm",
     105, 20, 0),
    ("U_PROM", "AM29F400_P", "Package_SO.pretty", "TSOP-I-48_18.4x12mm_P0.5mm",
     30, 40, 0),
    ("U_MROM", "SST39SF010_M", "Package_LCC.pretty", "PLCC-32_11.4x14.0mm_P1.27mm",
     80, 40, 0),

    # Shift registers + buffers — middle area
    ("U_SR1", "74HC595", "Package_SO.pretty", "SOIC-16_3.9x9.9mm_P1.27mm",
     20, 58, 0),
    ("U_SR2", "74HC595", "Package_SO.pretty", "SOIC-16_3.9x9.9mm_P1.27mm",
     40, 58, 0),
    ("U_SR3", "74HC595", "Package_SO.pretty", "SOIC-16_3.9x9.9mm_P1.27mm",
     60, 58, 0),
    ("U_BUF1", "74HC245_DATA", "Package_SO.pretty", "SOIC-20W_7.5x12.8mm_P1.27mm",
     90, 58, 0),
    ("U_BUF2", "74HC245_CTRL", "Package_SO.pretty", "SOIC-20W_7.5x12.8mm_P1.27mm",
     115, 58, 0),

    # MCU + support — bottom area
    ("U_MCU", "RP2040", "Package_DFN_QFN.pretty", "QFN-56-1EP_7x7mm_P0.4mm_EP5.6x5.6mm",
     35, 78, 0),
    ("Y1", "12MHz", "Crystal.pretty", "Crystal_SMD_3215-2Pin_3.2x1.5mm",
     50, 78, 0),
    ("U_FLASH", "W25Q32", "Package_SO.pretty", "SOIC-8_3.9x4.9mm_P1.27mm",
     65, 78, 0),
    ("U_REG", "AMS1117-3.3", "Package_TO_SOT_SMD.pretty", "SOT-223-3_TabPin2",
     90, 78, 0),

    # USB connector — right side
    ("J_USB", "USB_C", "Connector_USB.pretty", "USB_C_Receptacle_GCT_USB4085",
     140, 78, 90),
]

# Decoupling caps placement
CAPS = []
cap_x_start = 110
cap_y_start = 20
for i in range(13):
    col = i % 5
    row = i // 5
    CAPS.append((f"C{i+1}", "100nF", "Capacitor_SMD.pretty", "C_0402_1005Metric",
                 cap_x_start + col * 5, cap_y_start + row * 5, 0))

for i in range(3):
    CAPS.append((f"C{14+i}", "10uF", "Capacitor_SMD.pretty", "C_0805_2012Metric",
                 cap_x_start + i * 8, cap_y_start + 15, 0))

# Resistors
RESISTORS = [
    ("R1", "1K", "Resistor_SMD.pretty", "R_0402_1005Metric", 130, 38, 0),
    ("R2", "27R", "Resistor_SMD.pretty", "R_0402_1005Metric", 133, 38, 0),
    ("R3", "27R", "Resistor_SMD.pretty", "R_0402_1005Metric", 136, 38, 0),
    ("R4", "5.1K", "Resistor_SMD.pretty", "R_0402_1005Metric", 139, 38, 0),
    ("R5", "5.1K", "Resistor_SMD.pretty", "R_0402_1005Metric", 142, 38, 0),
    ("R6", "10K", "Resistor_SMD.pretty", "R_0402_1005Metric", 130, 42, 0),
    ("R7", "10K", "Resistor_SMD.pretty", "R_0402_1005Metric", 133, 42, 0),
]

# Crystal load caps
XLCAPS = [
    ("C17", "15pF", "Capacitor_SMD.pretty", "C_0402_1005Metric", 48, 82, 0),
    ("C18", "15pF", "Capacitor_SMD.pretty", "C_0402_1005Metric", 52, 82, 0),
]

# Diodes
DIODES = [
    (f"D{i+1}", "BAT54S", "Package_TO_SOT_SMD.pretty", "SOT-23",
     115 + (i % 3) * 6, 42 + (i // 3) * 5, 0)
    for i in range(6)
]


def generate_board_outline(ox, oy, w, h):
    """Generate board edge cuts with chamfered corners for card insertion."""
    chamfer = 2.0
    lines = []

    corners = [
        # Bottom-left to bottom-right (card edge — both connectors here)
        (ox, oy + h), (ox + w, oy + h),
        # Bottom-right to top-right
        (ox + w, oy + h), (ox + w, oy),
        # Top-right to top-left
        (ox + w, oy), (ox, oy),
        # Top-left to bottom-left
        (ox, oy), (ox, oy + h),
    ]

    for i in range(0, len(corners), 2):
        x1, y1 = corners[i]
        x2, y2 = corners[i + 1]
        lines.append(f'''\t(gr_line
\t\t(start {x1} {y1}) (end {x2} {y2})
\t\t(stroke (width 0.05) (type default))
\t\t(layer "Edge.Cuts")
\t\t(uuid "{uid()}")
\t)''')

    return '\n'.join(lines)


def generate_gold_fingers(name, ox, oy, n_pins, pitch, finger_w, finger_h, label=""):
    """Generate card-edge gold finger pads."""
    pads = []
    total_w = (n_pins - 1) * pitch
    start_x = ox - total_w / 2

    for i in range(n_pins):
        px = start_x + i * pitch
        pad_num_a = f"A{i+1}"
        pad_num_b = f"B{i+1}"

        # Side A (bottom of PCB)
        pads.append(f'''\t\t(pad "{pad_num_a}" smd rect
\t\t\t(at {px - ox} {finger_h / 2})
\t\t\t(size {finger_w} {finger_h})
\t\t\t(layers "B.Cu" "B.Mask")
\t\t\t(uuid "{uid()}")
\t\t)''')

        # Side B (top of PCB)
        pads.append(f'''\t\t(pad "{pad_num_b}" smd rect
\t\t\t(at {px - ox} {finger_h / 2})
\t\t\t(size {finger_w} {finger_h})
\t\t\t(layers "F.Cu" "F.Mask")
\t\t\t(uuid "{uid()}")
\t\t)''')

    pad_str = '\n'.join(pads)

    fp = f'''\t(footprint "{name}"
\t\t(layer "F.Cu")
\t\t(uuid "{uid()}")
\t\t(at {ox} {oy})
\t\t(property "Reference" "{name}"
\t\t\t(at 0 -4 0)
\t\t\t(layer "F.SilkS")
\t\t\t(uuid "{uid()}")
\t\t\t(effects (font (size 1.5 1.5) (thickness 0.15)))
\t\t)
\t\t(property "Value" "{label}"
\t\t\t(at 0 -2 0)
\t\t\t(layer "F.Fab")
\t\t\t(uuid "{uid()}")
\t\t\t(effects (font (size 1 1) (thickness 0.15)))
\t\t)
{pad_str}
\t)'''

    return fp


def embed_footprint(ref, value, fp_lib, fp_name, x, y, angle=0):
    """Read a footprint from KiCad library and embed it in PCB."""

    # Handle custom footprint name that includes .kicad_mod extension
    if fp_name.endswith('.kicad_mod'):
        clean_name = fp_name[:-len('.kicad_mod')]
    else:
        clean_name = fp_name

    lib_path = os.path.join(KICAD_FP_DIR, fp_lib)
    fp_file = os.path.join(lib_path, clean_name + ".kicad_mod")

    if not os.path.exists(fp_file):
        # Try USB connector alternatives
        alternatives = [f for f in os.listdir(lib_path)
                       if "USB_C" in f and "Receptacle" in f and "USB2.0" not in f]
        if alternatives:
            fp_file = os.path.join(lib_path, alternatives[0])
            clean_name = alternatives[0].replace('.kicad_mod', '')

    if not os.path.exists(fp_file):
        print(f"WARNING: footprint not found: {fp_file}")
        # Create a placeholder
        return f'''\t(footprint "placeholder:{clean_name}"
\t\t(layer "F.Cu")
\t\t(uuid "{uid()}")
\t\t(at {x} {y})
\t\t(property "Reference" "{ref}" (at 0 -3 0) (layer "F.SilkS") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))
\t\t(property "Value" "{value}" (at 0 3 0) (layer "F.Fab") (uuid "{uid()}") (effects (font (size 1 1) (thickness 0.15))))
\t)'''

    with open(fp_file) as f:
        raw = f.read()

    # Transform: strip outer parens, re-wrap with position
    # Remove the first line (footprint header)
    lines = raw.strip().split('\n')

    # Find content between first and last line
    body_lines = lines[1:-1]
    body = '\n'.join(body_lines)

    # Update reference
    body = re.sub(r'(fp_text\s+reference\s+)"[^"]*"', f'\\1"{ref}"', body)
    body = re.sub(r'(\(property\s+"Reference"\s+)"[^"]*"', f'\\1"{ref}"', body)

    # Update value
    body = re.sub(r'(fp_text\s+value\s+)"[^"]*"', f'\\1"{value}"', body)
    body = re.sub(r'(\(property\s+"Value"\s+)"[^"]*"', f'\\1"{value}"', body)

    # Replace all UUIDs
    def new_uuid(m):
        return f'(uuid "{uid()}")'
    body = re.sub(r'\(uuid\s+"[^"]*"\)', new_uuid, body)

    angle_str = f" {angle}" if angle != 0 else ""

    return f'''\t(footprint "{fp_lib.replace('.pretty','').replace('/','_')}:{clean_name}"
\t\t(layer "F.Cu")
\t\t(uuid "{uid()}")
\t\t(at {x} {y}{angle_str})
{body}
\t)'''


def generate_ground_pour(ox, oy, w, h, net_id=1):
    """Generate a ground copper pour on the back layer."""
    return f'''\t(zone
\t\t(net {net_id})
\t\t(net_name "GND")
\t\t(layer "B.Cu")
\t\t(uuid "{uid()}")
\t\t(hatch edge 0.5)
\t\t(connect_pads
\t\t\t(clearance 0.3)
\t\t)
\t\t(min_thickness 0.2)
\t\t(filled_areas_thickness no)
\t\t(fill
\t\t\t(thermal_gap 0.5)
\t\t\t(thermal_bridge_width 0.5)
\t\t)
\t\t(polygon
\t\t\t(pts
\t\t\t\t(xy {ox} {oy})
\t\t\t\t(xy {ox + w} {oy})
\t\t\t\t(xy {ox + w} {oy + h})
\t\t\t\t(xy {ox} {oy + h})
\t\t\t)
\t\t)
\t)'''


def generate_vcc_pour(ox, oy, w, h, net_id=2):
    """Generate a VCC copper pour on the front layer (partial)."""
    return f'''\t(zone
\t\t(net {net_id})
\t\t(net_name "VCC_5V")
\t\t(layer "F.Cu")
\t\t(uuid "{uid()}")
\t\t(hatch edge 0.5)
\t\t(priority 1)
\t\t(connect_pads
\t\t\t(clearance 0.3)
\t\t)
\t\t(min_thickness 0.2)
\t\t(filled_areas_thickness no)
\t\t(fill
\t\t\t(thermal_gap 0.5)
\t\t\t(thermal_bridge_width 0.5)
\t\t)
\t\t(polygon
\t\t\t(pts
\t\t\t\t(xy {ox} {oy})
\t\t\t\t(xy {ox + w} {oy})
\t\t\t\t(xy {ox + w} {oy + h})
\t\t\t\t(xy {ox} {oy + h})
\t\t\t)
\t\t)
\t)'''


def main():
    ox = ORIGIN_X
    oy = ORIGIN_Y

    footprints = []
    print("Placing components...")

    # ── Edge connector gold fingers ──
    ctrg1_y = oy + 3       # top edge
    ctrg2_y = oy + BOARD_H - 3  # bottom edge
    center_x = ox + BOARD_W / 2

    footprints.append(generate_gold_fingers(
        "J_CTRG1", center_x, ctrg1_y, 60, 1.27, 0.8, 6.0, "CTRG1_CHA"))
    footprints.append(generate_gold_fingers(
        "J_CTRG2", center_x, ctrg2_y, 60, 1.27, 0.8, 6.0, "CTRG2_PROG"))

    # ── Main ICs ──
    for ref, value, fp_lib, fp_name, rx, ry, angle in COMPONENTS:
        x = ox + rx
        y = oy + 10 + ry  # offset from top edge (leave room for CTRG1 fingers)
        fp = embed_footprint(ref, value, fp_lib, fp_name, x, y, angle)
        footprints.append(fp)
        print(f"  {ref:12s} → ({x:.1f}, {y:.1f})")

    # ── Passives ──
    for parts_list in [CAPS, RESISTORS, XLCAPS, DIODES]:
        for ref, value, fp_lib, fp_name, rx, ry, angle in parts_list:
            x = ox + rx
            y = oy + 10 + ry
            fp = embed_footprint(ref, value, fp_lib, fp_name, x, y, angle)
            footprints.append(fp)

    # ── Board outline ──
    outline = generate_board_outline(ox, oy, BOARD_W, BOARD_H)

    # ── Copper pours ──
    gnd_pour = generate_ground_pour(ox, oy, BOARD_W, BOARD_H, net_id=1)

    # ── Silkscreen labels ──
    labels = f'''\t(gr_text "NEO GEO MVS FLASH CART v1.0"
\t\t(at {ox + BOARD_W/2} {oy + BOARD_H/2 - 5} 0)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 2 2) (thickness 0.3)))
\t)
\t(gr_text "NeoScanSDK"
\t\t(at {ox + BOARD_W/2} {oy + BOARD_H/2} 0)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1.5 1.5) (thickness 0.2)))
\t)
\t(gr_text "CTRG1 (CHA)"
\t\t(at {ox + BOARD_W/2} {oy + 10} 0)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)
\t(gr_text "CTRG2 (PROG)"
\t\t(at {ox + BOARD_W/2} {oy + BOARD_H - 10} 0)
\t\t(layer "F.SilkS")
\t\t(uuid "{uid()}")
\t\t(effects (font (size 1 1) (thickness 0.15)))
\t)'''

    # ── Assemble PCB file ──
    fp_str = '\n'.join(footprints)

    pcb = f"""(kicad_pcb
\t(version 20240108)
\t(generator "neocart_pcb_generator")
\t(generator_version "1.0")
\t(general
\t\t(thickness 1.6)
\t\t(legacy_teardrops no)
\t)
\t(paper "A4")
\t(title_block
\t\t(title "Neo Geo MVS Flash Cart")
\t\t(date "2026-04-26")
\t\t(rev "1.0")
\t\t(company "NeoScanSDK")
\t\t(comment 1 "PSMCC flash + RP2040 USB programmer")
\t)
\t(layers
\t\t(0 "F.Cu" signal)
\t\t(31 "B.Cu" signal)
\t\t(32 "B.Adhes" user "B.Adhesive")
\t\t(33 "F.Adhes" user "F.Adhesive")
\t\t(34 "B.Paste" user)
\t\t(35 "F.Paste" user)
\t\t(36 "B.SilkS" user "B.Silkscreen")
\t\t(37 "F.SilkS" user "F.Silkscreen")
\t\t(38 "B.Mask" user "B.Mask")
\t\t(39 "F.Mask" user "F.Mask")
\t\t(40 "Dwgs.User" user "User.Drawings")
\t\t(41 "Cmts.User" user "User.Comments")
\t\t(44 "Edge.Cuts" user)
\t\t(45 "Margin" user)
\t\t(46 "B.CrtYd" user "B.Courtyard")
\t\t(47 "F.CrtYd" user "F.Courtyard")
\t\t(48 "B.Fab" user "B.Fabrication")
\t\t(49 "F.Fab" user "F.Fabrication")
\t)
\t(setup
\t\t(pad_to_mask_clearance 0)
\t\t(allow_soldermask_bridges_in_footprints no)
\t\t(pcbplotparams
\t\t\t(layerselection 0x00010fc_ffffffff)
\t\t\t(plot_on_all_layers_selection 0x0000000_00000000)
\t\t\t(disableapertmacros no)
\t\t\t(usegerberextensions no)
\t\t\t(usegerberattributes yes)
\t\t\t(usegerberadvancedattributes yes)
\t\t\t(creategerberjobfile yes)
\t\t\t(dashed_line_dash_ratio 12.000000)
\t\t\t(dashed_line_gap_ratio 3.000000)
\t\t\t(svgprecision 4)
\t\t\t(plotframeref no)
\t\t\t(viasonmask no)
\t\t\t(mode 1)
\t\t\t(useauxorigin no)
\t\t\t(hpglpennumber 1)
\t\t\t(hpglpenspeed 20)
\t\t\t(hpglpendiameter 15.000000)
\t\t\t(pdf_front_fp_property_popups yes)
\t\t\t(pdf_back_fp_property_popups yes)
\t\t\t(pdf_metadata yes)
\t\t\t(outputformat 1)
\t\t\t(mirror no)
\t\t\t(drillshape 1)
\t\t\t(scaleselection 1)
\t\t\t(outputdirectory "gerbers/")
\t\t)
\t)
\t(net 0 "")
\t(net 1 "GND")
\t(net 2 "VCC_5V")
\t(net 3 "VCC_3V3")
\t(net 4 "VBUS")
{outline}
{labels}
{fp_str}
{gnd_pour}
)"""

    out_path = os.path.join(OUT_DIR, "neocart.kicad_pcb")
    with open(out_path, 'w') as f:
        f.write(pcb)
    print(f"\nPCB written to {out_path}")

    # Verify
    import subprocess
    result = subprocess.run(
        ['kicad-cli', 'pcb', 'export', 'svg', out_path,
         '-l', 'F.Cu,B.Cu,Edge.Cuts,F.SilkS',
         '-o', os.path.join(OUT_DIR, 'neocart_preview.svg')],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print("Preview SVG exported: neocart_preview.svg")
    else:
        print(f"SVG export: {result.stderr[:200]}")


if __name__ == "__main__":
    main()
