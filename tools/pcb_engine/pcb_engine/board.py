"""
Board — the central object. Holds components, nets, traces, and board outline.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from pcb_engine.component import Component, Package, Pad


@dataclass
class Via:
    x: float
    y: float
    drill: float = 0.3
    diameter: float = 0.6
    net: str = ""


@dataclass
class TraceSegment:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float = 0.25
    layer: str = "F.Cu"
    net: str = ""


@dataclass
class Zone:
    net: str
    layer: str
    outline: List[Tuple[float, float]] = field(default_factory=list)


@dataclass
class Net:
    name: str
    pads: List[Tuple[str, str]] = field(default_factory=list)  # (component_ref, pad_number)

    def connect(self, *pad_refs):
        """Connect pads to this net. Each pad_ref is (component_ref, pad_number)."""
        for ref in pad_refs:
            if ref not in self.pads:
                self.pads.append(ref)


class Board:
    def __init__(self, width_mm: float, height_mm: float, layers: int = 2):
        self.width = width_mm
        self.height = height_mm
        self.layers = layers
        self.components: Dict[str, Component] = {}
        self.nets: Dict[str, Net] = {}
        self.traces: List[TraceSegment] = []
        self.vias: List[Via] = []
        self.zones: List[Zone] = []
        self.outline: List[Tuple[float, float]] = [
            (0, 0), (width_mm, 0), (width_mm, height_mm), (0, height_mm)
        ]
        self.edge_cuts: List[Tuple[Tuple[float,float], Tuple[float,float]]] = []

        # Design rules
        self.min_trace_width = 0.2
        self.min_clearance = 0.2
        self.min_via_drill = 0.3
        self.min_via_diameter = 0.6

    def set_outline(self, points: List[Tuple[float, float]]):
        self.outline = points

    def place(self, ref: str, package: Package, x: float, y: float,
              value: str = "", angle: float = 0, lcsc: str = "") -> Component:
        comp = Component(ref=ref, value=value or ref, package=package,
                        x=x, y=y, angle=angle, lcsc=lcsc)
        self.components[ref] = comp
        return comp

    def net(self, name: str) -> Net:
        if name not in self.nets:
            self.nets[name] = Net(name=name)
        return self.nets[name]

    def connect(self, net_name: str, comp_ref: str, pad_num):
        """Shorthand: assign a pad to a net."""
        n = self.net(net_name)
        n.connect((comp_ref, str(pad_num)))
        # Also tag the pad
        comp = self.components.get(comp_ref)
        if comp:
            p = comp.pad(pad_num)
            if p:
                p.net = net_name

    def power_plane(self, net_name: str, layer: str):
        """Add a copper pour zone for a power net."""
        margin = 1.0
        outline = [
            (margin, margin),
            (self.width - margin, margin),
            (self.width - margin, self.height - margin),
            (margin, self.height - margin),
        ]
        self.zones.append(Zone(net=net_name, layer=layer, outline=outline))

    def get_pad_position(self, comp_ref: str, pad_num) -> Optional[Tuple[float, float]]:
        comp = self.components.get(comp_ref)
        if comp:
            return comp.pad_abs(str(pad_num))
        return None

    def get_net_pads(self, net_name: str) -> List[Tuple[float, float, str, str]]:
        """Get all pad positions for a net: [(x, y, comp_ref, pad_num), ...]"""
        n = self.nets.get(net_name)
        if not n:
            return []
        result = []
        for comp_ref, pad_num in n.pads:
            pos = self.get_pad_position(comp_ref, pad_num)
            if pos:
                result.append((pos[0], pos[1], comp_ref, pad_num))
        return result

    def add_trace(self, x1, y1, x2, y2, net="", layer="F.Cu", width=0.25):
        self.traces.append(TraceSegment(x1, y1, x2, y2, width, layer, net))

    def add_via(self, x, y, net=""):
        self.vias.append(Via(x, y, net=net))

    def route(self, power_nets=None):
        """Auto-route all signal nets."""
        from pcb_engine.router import Router
        router = Router(self, power_nets=power_nets or {"GND", "VCC", "VCC_3V3", "VCC_5V", "VCC_1V1"})
        return router.route_all()

    def check_drc(self):
        """Run Design Rule Check."""
        from pcb_engine.drc import DRC
        return DRC(self).check()

    def render(self, path: str, dpi: int = 300, side: str = "top"):
        """Render board to PNG."""
        from pcb_engine.renderer import Renderer
        Renderer(self).render(path, dpi=dpi, side=side)

    def export_gerbers(self, output_dir: str):
        """Export Gerber manufacturing files."""
        from pcb_engine.exporter import GerberExporter
        GerberExporter(self).export(output_dir)

    def export_bom(self, path: str):
        """Export Bill of Materials."""
        from pcb_engine.exporter import BOMExporter
        BOMExporter(self).export(path)

    def stats(self) -> dict:
        """Board statistics."""
        total_pads = sum(len(c.package.pads) for c in self.components.values())
        assigned_pads = sum(1 for c in self.components.values()
                          for p in c.package.pads if p.net)
        return {
            "components": len(self.components),
            "nets": len(self.nets),
            "total_pads": total_pads,
            "assigned_pads": assigned_pads,
            "orphan_pads": total_pads - assigned_pads,
            "traces": len(self.traces),
            "vias": len(self.vias),
            "board_size": f"{self.width}mm x {self.height}mm",
            "layers": self.layers,
        }
