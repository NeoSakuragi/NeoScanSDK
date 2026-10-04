#!/usr/bin/env python3
"""
Neo Geo MVS Flash Cart — 4-Layer PCB Router

Layer stack:
  F.Cu   — signal routing (horizontal preference)
  In1.Cu — GND plane (full copper pour)
  In2.Cu — VCC_5V plane (full copper pour)
  B.Cu   — signal routing (vertical preference)

Power connections just need a via to the right plane.
Signal routing uses F.Cu and B.Cu with vias at corners.
"""

import pcbnew
import os
from collections import defaultdict

PCB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "neocart.kicad_pcb")

TRACE_W = pcbnew.FromMM(0.25)
TRACE_W_PWR = pcbnew.FromMM(0.4)
VIA_DRILL = pcbnew.FromMM(0.3)
VIA_SIZE = pcbnew.FromMM(0.6)
MM = pcbnew.FromMM


def add_track(board, x1, y1, x2, y2, layer, net, width=None):
    if abs(x1 - x2) < MM(0.05) and abs(y1 - y2) < MM(0.05):
        return
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(int(x1), int(y1)))
    t.SetEnd(pcbnew.VECTOR2I(int(x2), int(y2)))
    t.SetWidth(width or TRACE_W)
    t.SetLayer(layer)
    if net:
        t.SetNet(net)
    board.Add(t)


def add_via(board, x, y, net):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pcbnew.VECTOR2I(int(x), int(y)))
    v.SetDrill(VIA_DRILL)
    v.SetWidth(VIA_SIZE)
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    if net:
        v.SetNet(net)
    board.Add(v)


def route_L(board, x1, y1, x2, y2, net, h_first=True):
    """L-route: one segment on F.Cu, via, other segment on B.Cu."""
    if abs(x1 - x2) < MM(0.1) and abs(y1 - y2) < MM(0.1):
        return
    if abs(x1 - x2) < MM(0.1):
        add_track(board, x1, y1, x2, y2, pcbnew.F_Cu, net)
        return
    if abs(y1 - y2) < MM(0.1):
        add_track(board, x1, y1, x2, y2, pcbnew.F_Cu, net)
        return

    if h_first:
        add_track(board, x1, y1, x2, y1, pcbnew.F_Cu, net)
        add_via(board, x2, y1, net)
        add_track(board, x2, y1, x2, y2, pcbnew.B_Cu, net)
    else:
        add_track(board, x1, y1, x1, y2, pcbnew.F_Cu, net)
        add_via(board, x1, y2, net)
        add_track(board, x1, y2, x2, y2, pcbnew.B_Cu, net)


def collect_net_pads(board):
    net_pads = defaultdict(list)
    for fp in board.GetFootprints():
        ref = fp.GetReference()
        for pad in fp.Pads():
            n = pad.GetNet()
            if n and n.GetNetname():
                pos = pad.GetPosition()
                net_pads[n.GetNetname()].append({
                    'ref': ref, 'pad': pad.GetNumber(),
                    'x': pos.x, 'y': pos.y, 'net': n,
                })
    return net_pads


def nearest_neighbor_chain(pads):
    """Order pads by nearest-neighbor to minimize total trace length."""
    if len(pads) <= 1:
        return pads
    remaining = list(pads)
    chain = [remaining.pop(0)]
    while remaining:
        last = chain[-1]
        best_i = min(range(len(remaining)),
                     key=lambda i: abs(remaining[i]['x'] - last['x']) +
                                   abs(remaining[i]['y'] - last['y']))
        chain.append(remaining.pop(best_i))
    return chain


def main():
    print(f"Loading: {PCB_PATH}")
    board = pcbnew.LoadBoard(PCB_PATH)

    # ── Step 1: Remove all existing tracks and vias ──
    tracks = list(board.GetTracks())
    print(f"Removing {len(tracks)} existing tracks/vias...")
    for t in tracks:
        board.Remove(t)

    # Remove existing zones
    zones = list(board.Zones())
    print(f"Removing {len(zones)} existing zones...")
    for z in zones:
        board.Remove(z)

    # ── Step 2: Enable 4 layers ──
    board.SetCopperLayerCount(4)
    print("Set to 4-layer board")

    # ── Step 3: Add power plane zones ──
    # GND plane on In1.Cu
    board_box = board.GetBoardEdgesBoundingBox()
    bx1 = board_box.GetLeft()
    by1 = board_box.GetTop()
    bx2 = board_box.GetRight()
    by2 = board_box.GetBottom()

    gnd_net = board.GetNetInfo().GetNetItem("GND")
    vcc_net = board.GetNetInfo().GetNetItem("VCC_5V")
    v33_net = board.GetNetInfo().GetNetItem("VCC_3V3")

    def add_zone(net_item, layer, name):
        zone = pcbnew.ZONE(board)
        zone.SetNet(net_item)
        zone.SetLayer(layer)
        zone.SetIsRuleArea(False)
        zone.SetDoNotAllowTracks(False)
        zone.SetDoNotAllowVias(False)
        zone.SetDoNotAllowPads(False)
        zone.SetDoNotAllowCopperPour(False)

        outline = zone.Outline()
        outline.NewOutline()
        margin = MM(1)
        outline.Append(int(bx1 + margin), int(by1 + margin))
        outline.Append(int(bx2 - margin), int(by1 + margin))
        outline.Append(int(bx2 - margin), int(by2 - margin))
        outline.Append(int(bx1 + margin), int(by2 - margin))

        zone.SetMinThickness(MM(0.2))
        zone.SetThermalReliefGap(MM(0.5))
        zone.SetThermalReliefSpokeWidth(MM(0.5))
        zone.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)

        board.Add(zone)
        print(f"  Added {name} zone on layer {layer}")
        return zone

    gnd_zone = add_zone(gnd_net, pcbnew.In1_Cu, "GND")
    vcc_zone = add_zone(vcc_net, pcbnew.In2_Cu, "VCC_5V")
    # Also add GND pour on B.Cu for extra ground coverage
    gnd_zone_b = add_zone(gnd_net, pcbnew.B_Cu, "GND_back")
    gnd_zone_b.SetAssignedPriority(0)

    # ── Step 4: Route all signal nets ──
    net_pads = collect_net_pads(board)
    print(f"\nRouting {len(net_pads)} nets...")

    power_nets = {"GND", "VCC_5V", "VCC_3V3", "VBUS"}
    routed = 0
    skipped_single = 0

    for net_name, pads in sorted(net_pads.items()):
        if net_name in {"", "GND"}:
            # GND handled by In1.Cu plane — just add vias to plane for each pad
            for p in pads:
                add_via(board, p['x'], p['y'], p['net'])
            continue

        if net_name in {"VCC_5V"}:
            # VCC handled by In2.Cu plane — add vias
            for p in pads:
                add_via(board, p['x'], p['y'], p['net'])
            continue

        if net_name == "VCC_3V3":
            # Route 3V3 as traces from regulator output + vias
            chain = nearest_neighbor_chain(pads)
            for i in range(len(chain) - 1):
                p1, p2 = chain[i], chain[i + 1]
                route_L(board, p1['x'], p1['y'], p2['x'], p2['y'],
                        p1['net'], h_first=(i % 2 == 0))
            routed += 1
            continue

        if net_name == "VBUS":
            chain = nearest_neighbor_chain(pads)
            for i in range(len(chain) - 1):
                p1, p2 = chain[i], chain[i + 1]
                route_L(board, p1['x'], p1['y'], p2['x'], p2['y'],
                        p1['net'], h_first=True)
            routed += 1
            continue

        if len(pads) < 2:
            skipped_single += 1
            continue

        # Signal routing
        chain = nearest_neighbor_chain(pads)

        # Determine preferred direction
        has_connector = any(p['ref'].startswith('J_CTRG') for p in pads)

        for i in range(len(chain) - 1):
            p1, p2 = chain[i], chain[i + 1]
            # Alternate H-first to spread traces
            if has_connector:
                h_first = (i % 2 == 1)  # vertical-first from connectors
            else:
                h_first = (i % 2 == 0)
            route_L(board, p1['x'], p1['y'], p2['x'], p2['y'],
                    p1['net'], h_first=h_first)

        routed += 1

    print(f"\nRouted {routed} signal nets")
    print(f"Skipped {skipped_single} single-pad nets")
    print(f"GND/VCC handled by internal planes + vias")

    # ── Step 5: Fill zones ──
    print("Filling zones...")
    filler = pcbnew.ZONE_FILLER(board)
    filler.Fill(list(board.Zones()))

    # ── Step 6: Save ──
    pcbnew.SaveBoard(PCB_PATH, board)
    print(f"Saved: {PCB_PATH}")

    # Export preview
    import subprocess
    subprocess.run([
        'kicad-cli', 'pcb', 'export', 'pdf', PCB_PATH,
        '-l', 'F.Cu,In1.Cu,In2.Cu,B.Cu,Edge.Cuts,F.SilkS',
        '-o', os.path.join(os.path.dirname(PCB_PATH), 'neocart_4layer.pdf')
    ], capture_output=True)
    print("Preview: neocart_4layer.pdf")

    # Run DRC
    result = subprocess.run([
        'kicad-cli', 'pcb', 'drc', PCB_PATH,
        '-o', os.path.join(os.path.dirname(PCB_PATH), 'drc_4layer.json'),
        '--format', 'json'
    ], capture_output=True, text=True)
    print(f"DRC: {result.stdout.strip()}")

    import json
    try:
        with open(os.path.join(os.path.dirname(PCB_PATH), 'drc_4layer.json')) as f:
            drc = json.load(f)
        v = len(drc.get('violations', []))
        u = len(drc.get('unconnected_items', []))
        print(f"  Violations: {v}, Unconnected: {u}")
        if v > 0:
            types = {}
            for viol in drc.get('violations', []):
                t = viol.get('type', '?')
                types[t] = types.get(t, 0) + 1
            for t, c in sorted(types.items(), key=lambda x: -x[1])[:5]:
                print(f"    {t}: {c}")
    except:
        pass


if __name__ == "__main__":
    main()
