#!/usr/bin/env python3
"""
Neo Geo MVS Flash Cart — PCB Auto-Router

Uses pcbnew Python API to route all traces on the board.
Strategy:
  - Horizontal segments on F.Cu, vertical segments on B.Cu
  - Vias at corners for layer transitions
  - Ground pour on B.Cu handles GND net
  - VCC routed as fat traces on F.Cu
  - Signal traces at 0.25mm width, 0.3mm clearance
"""

import pcbnew
import os
import sys
from collections import defaultdict

PCB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neocart.kicad_pcb")

TRACE_WIDTH = pcbnew.FromMM(0.25)
TRACE_WIDTH_POWER = pcbnew.FromMM(0.5)
VIA_DRILL = pcbnew.FromMM(0.3)
VIA_SIZE = pcbnew.FromMM(0.6)

def get_pad_position(board, ref, pad_num):
    """Get the absolute position of a pad on a footprint."""
    fp = board.FindFootprintByReference(ref)
    if not fp:
        return None
    for pad in fp.Pads():
        if pad.GetNumber() == str(pad_num):
            pos = pad.GetPosition()
            return (pos.x, pos.y)
    return None

def get_net_item(board, net_name):
    """Get the NETINFO_ITEM for a named net."""
    netinfo = board.GetNetInfo()
    net = netinfo.GetNetItem(net_name)
    return net

def add_track(board, x1, y1, x2, y2, layer, net_item, width=None):
    """Add a PCB track segment."""
    if x1 == x2 and y1 == y2:
        return
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(int(x1), int(y1)))
    track.SetEnd(pcbnew.VECTOR2I(int(x2), int(y2)))
    track.SetWidth(width or TRACE_WIDTH)
    track.SetLayer(layer)
    if net_item:
        track.SetNet(net_item)
    board.Add(track)

def add_via(board, x, y, net_item):
    """Add a via at the given position."""
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    via.SetDrill(VIA_DRILL)
    via.SetWidth(VIA_SIZE)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    if net_item:
        via.SetNet(net_item)
    board.Add(via)

def route_L(board, x1, y1, x2, y2, net_item, width=None, h_first=True):
    """Route an L-shaped connection: horizontal on F.Cu, vertical on B.Cu with via."""
    w = width or TRACE_WIDTH

    if abs(x1 - x2) < pcbnew.FromMM(0.1) and abs(y1 - y2) < pcbnew.FromMM(0.1):
        return  # same position

    if abs(x1 - x2) < pcbnew.FromMM(0.1):
        # Same X — straight vertical on F.Cu
        add_track(board, x1, y1, x2, y2, pcbnew.F_Cu, net_item, w)
        return

    if abs(y1 - y2) < pcbnew.FromMM(0.1):
        # Same Y — straight horizontal on F.Cu
        add_track(board, x1, y1, x2, y2, pcbnew.F_Cu, net_item, w)
        return

    if h_first:
        # Horizontal on F.Cu, via, vertical on B.Cu
        mid_x = x2
        mid_y = y1
        add_track(board, x1, y1, mid_x, mid_y, pcbnew.F_Cu, net_item, w)
        add_via(board, mid_x, mid_y, net_item)
        add_track(board, mid_x, mid_y, x2, y2, pcbnew.B_Cu, net_item, w)
    else:
        # Vertical on F.Cu, via, horizontal on B.Cu
        mid_x = x1
        mid_y = y2
        add_track(board, x1, y1, mid_x, mid_y, pcbnew.F_Cu, net_item, w)
        add_via(board, mid_x, mid_y, net_item)
        add_track(board, mid_x, mid_y, x2, y2, pcbnew.B_Cu, net_item, w)


def route_direct(board, x1, y1, x2, y2, net_item, layer=pcbnew.F_Cu, width=None):
    """Route a straight trace on a single layer."""
    add_track(board, x1, y1, x2, y2, layer, net_item, width or TRACE_WIDTH)


def collect_net_pads(board):
    """Collect all pads grouped by net name."""
    net_pads = defaultdict(list)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            net = pad.GetNet()
            if net and net.GetNetname():
                pos = pad.GetPosition()
                net_pads[net.GetNetname()].append({
                    'ref': ref,
                    'pad': pad.GetNumber(),
                    'x': pos.x,
                    'y': pos.y,
                    'net_item': net,
                })
    return net_pads


def route_net_chain(board, pads, h_first=True, width=None):
    """Route a net by connecting pads in a chain (nearest-neighbor order)."""
    if len(pads) < 2:
        return

    net_item = pads[0]['net_item']

    # Sort pads by position to create a reasonable chain
    # For horizontal buses, sort by X; for vertical, sort by Y
    remaining = list(pads)
    chain = [remaining.pop(0)]

    while remaining:
        last = chain[-1]
        best_idx = 0
        best_dist = float('inf')
        for i, p in enumerate(remaining):
            dist = abs(p['x'] - last['x']) + abs(p['y'] - last['y'])
            if dist < best_dist:
                best_dist = dist
                best_idx = i
        chain.append(remaining.pop(best_idx))

    # Route connections along the chain
    for i in range(len(chain) - 1):
        p1 = chain[i]
        p2 = chain[i + 1]

        # Alternate H-first and V-first to reduce crossings
        use_h = h_first if (i % 2 == 0) else (not h_first)
        route_L(board, p1['x'], p1['y'], p2['x'], p2['y'],
                net_item, width, h_first=use_h)


def main():
    print(f"Loading PCB: {PCB_PATH}")
    board = pcbnew.LoadBoard(PCB_PATH)

    net_pads = collect_net_pads(board)

    routed = 0
    skipped = 0
    skip_nets = {"GND", ""}  # GND handled by copper pour

    print(f"Found {len(net_pads)} nets to route")

    # Route power nets with fat traces
    power_nets = {"VCC_5V", "VCC_3V3", "VBUS"}
    for net_name in power_nets:
        if net_name in net_pads and len(net_pads[net_name]) >= 2:
            print(f"  Routing power net: {net_name} ({len(net_pads[net_name])} pads)")
            route_net_chain(board, net_pads[net_name], h_first=True,
                          width=TRACE_WIDTH_POWER)
            routed += 1

    # Route signal nets
    for net_name, pads in sorted(net_pads.items()):
        if net_name in skip_nets or net_name in power_nets:
            continue
        if len(pads) < 2:
            skipped += 1
            continue

        # Determine routing direction preference based on net type
        # Address buses tend to run vertically (connector at edge → chip in middle)
        # Data buses similar
        h_first = True

        # For connector-to-chip nets, prefer vertical-first
        refs = set(p['ref'] for p in pads)
        if any(r.startswith('J_CTRG') for r in refs):
            h_first = False  # vertical from connector to chip

        route_net_chain(board, pads, h_first=h_first)
        routed += 1

    print(f"\nRouted {routed} nets, skipped {skipped} single-pad nets")
    print(f"GND net skipped (handled by copper pour)")

    # Refresh zone fills
    filler = pcbnew.ZONE_FILLER(board)
    zones = board.Zones()
    zone_list = list(zones)
    if zone_list:
        print("Filling copper zones...")
        filler.Fill(zone_list)

    # Save
    pcbnew.SaveBoard(PCB_PATH, board)
    print(f"PCB saved: {PCB_PATH}")

    # Export updated preview
    import subprocess
    subprocess.run([
        'kicad-cli', 'pcb', 'export', 'pdf',
        PCB_PATH,
        '-l', 'F.Cu,B.Cu,Edge.Cuts,F.SilkS',
        '-o', os.path.join(os.path.dirname(PCB_PATH), 'neocart_routed.pdf')
    ], capture_output=True)
    print("Preview exported: neocart_routed.pdf")


if __name__ == "__main__":
    main()
