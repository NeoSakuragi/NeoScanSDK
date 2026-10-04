"""
Component, Package, and Pad definitions.
Represents physical electronic components with real pin maps.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Pad:
    number: str
    name: str
    x: float  # relative to component center, mm
    y: float
    width: float = 0.6
    height: float = 1.0
    net: Optional[str] = None
    layer: str = "F.Cu"

    @property
    def shape(self):
        return "rect"


@dataclass
class Package:
    name: str
    pads: List[Pad] = field(default_factory=list)
    width: float = 0
    height: float = 0
    courtyard: float = 0.25  # clearance around component

    @classmethod
    def smd_resistor(cls, name="R_0402"):
        """Standard 0402 SMD resistor (1.0mm x 0.5mm)."""
        return cls(name=name, width=1.0, height=0.5, pads=[
            Pad("1", "1", x=-0.5, y=0, width=0.5, height=0.5),
            Pad("2", "2", x=0.5, y=0, width=0.5, height=0.5),
        ])

    @classmethod
    def smd_cap(cls, name="C_0402"):
        return cls.smd_resistor(name)  # same footprint

    @classmethod
    def smd_resistor_0805(cls, name="R_0805"):
        return cls(name=name, width=2.0, height=1.25, pads=[
            Pad("1", "1", x=-1.0, y=0, width=1.0, height=1.25),
            Pad("2", "2", x=1.0, y=0, width=1.0, height=1.25),
        ])

    @classmethod
    def soic(cls, name="SOIC-8", pin_count=8, pitch=1.27, span=5.4):
        """Generic SOIC package."""
        pads = []
        half = pin_count // 2
        for i in range(half):
            y = (i - (half - 1) / 2) * pitch
            pads.append(Pad(str(i + 1), str(i + 1), x=-span / 2, y=y, width=0.6, height=1.5))
            pads.append(Pad(str(pin_count - i), str(pin_count - i), x=span / 2, y=y, width=0.6, height=1.5))
        return cls(name=name, width=span + 2, height=half * pitch, pads=pads)

    @classmethod
    def soic20w(cls, name="SOIC-20W"):
        return cls.soic(name, pin_count=20, pitch=1.27, span=10.0)

    @classmethod
    def sot223(cls, name="SOT-223"):
        return cls(name=name, width=7.0, height=3.5, pads=[
            Pad("1", "1", x=-3.0, y=-2.3, width=1.0, height=1.5),
            Pad("2", "2", x=-3.0, y=0, width=1.0, height=1.5),
            Pad("3", "3", x=-3.0, y=2.3, width=1.0, height=1.5),
            Pad("4", "4", x=3.0, y=0, width=3.0, height=1.5),
        ])

    @classmethod
    def db15_vga(cls, name="DB15_VGA"):
        """VGA connector — 15 pins in 3 rows."""
        pads = []
        for row in range(3):
            n = 5
            for col in range(n):
                pin = row * 5 + col + 1
                x = (col - 2) * 2.5
                y = (row - 1) * 2.8
                pads.append(Pad(str(pin), f"P{pin}", x=x, y=y, width=1.0, height=1.0))
        return cls(name=name, width=16, height=10, pads=pads)

    @classmethod
    def scart(cls, name="SCART"):
        """SCART connector — 21 pins."""
        pads = []
        for i in range(21):
            row = i % 2
            col = i // 2
            x = (col - 5) * 2.5
            y = (row - 0.5) * 3.0
            pads.append(Pad(str(i + 1), f"P{i + 1}", x=x, y=y, width=1.0, height=1.5))
        return cls(name=name, width=30, height=8, pads=pads)

    @classmethod
    def gold_fingers(cls, name="MVS_CTRG", pin_count=60, pitch=2.54):
        """MVS cart edge connector gold fingers."""
        pads = []
        total_w = (pin_count - 1) * pitch
        for i in range(pin_count):
            x = (i - (pin_count - 1) / 2) * pitch
            pads.append(Pad(f"A{i+1}", f"A{i+1}", x=x, y=0, width=1.5, height=10.0, layer="F.Cu"))
            pads.append(Pad(f"B{i+1}", f"B{i+1}", x=x, y=0, width=1.5, height=10.0, layer="B.Cu"))
        return cls(name=name, width=total_w + 2, height=10, pads=pads)

    @classmethod
    def tqfp(cls, name="TQFP-144", pin_count=144, pitch=0.5, body=20.0):
        """TQFP package — pins on all 4 sides."""
        pads = []
        side = pin_count // 4
        for s in range(4):
            for i in range(side):
                pin = s * side + i + 1
                offset = (i - (side - 1) / 2) * pitch
                if s == 0:    # bottom
                    pads.append(Pad(str(pin), str(pin), x=offset, y=body/2+0.8, width=0.3, height=1.5))
                elif s == 1:  # right
                    pads.append(Pad(str(pin), str(pin), x=body/2+0.8, y=offset, width=1.5, height=0.3))
                elif s == 2:  # top
                    pads.append(Pad(str(pin), str(pin), x=-offset, y=-body/2-0.8, width=0.3, height=1.5))
                elif s == 3:  # left
                    pads.append(Pad(str(pin), str(pin), x=-body/2-0.8, y=-offset, width=1.5, height=0.3))
        return cls(name=name, width=body+3, height=body+3, pads=pads)

    @classmethod
    def tsop54(cls, name="TSOP-54", pitch=0.8, span=10.16):
        """TSOP-II-54 package (SDRAM)."""
        pads = []
        half = 27
        for i in range(half):
            y = (i - (half - 1) / 2) * pitch
            pads.append(Pad(str(i + 1), str(i + 1), x=-span/2, y=y, width=0.5, height=1.2))
            pads.append(Pad(str(54 - i), str(54 - i), x=span/2, y=y, width=0.5, height=1.2))
        return cls(name=name, width=span+3, height=half*pitch+1, pads=pads)

    @classmethod
    def pin_header_2x20(cls, name="HDR_2x20", pitch=2.54):
        """2x20 pin header (40 pins)."""
        pads = []
        for row in range(2):
            for col in range(20):
                pin = row * 20 + col + 1
                x = (row - 0.5) * pitch
                y = (col - 9.5) * pitch
                pads.append(Pad(str(pin), str(pin), x=x, y=y, width=1.6, height=1.6))
        return cls(name=name, width=2*pitch+2, height=20*pitch+2, pads=pads)


@dataclass
class Component:
    ref: str
    value: str
    package: Package
    x: float = 0
    y: float = 0
    angle: float = 0
    lcsc: str = ""

    def pad(self, num) -> Optional[Pad]:
        for p in self.package.pads:
            if p.number == str(num):
                return p
        return None

    def pad_abs(self, num) -> Optional[Tuple[float, float]]:
        """Get absolute pad position."""
        p = self.pad(num)
        if not p:
            return None
        import math
        rad = math.radians(self.angle)
        rx = p.x * math.cos(rad) - p.y * math.sin(rad)
        ry = p.x * math.sin(rad) + p.y * math.cos(rad)
        return (self.x + rx, self.y + ry)

    def all_pads_abs(self) -> List[Tuple[str, float, float, Optional[str]]]:
        """Get all pad absolute positions with net info."""
        import math
        rad = math.radians(self.angle)
        result = []
        for p in self.package.pads:
            rx = p.x * math.cos(rad) - p.y * math.sin(rad)
            ry = p.x * math.sin(rad) + p.y * math.cos(rad)
            result.append((p.number, self.x + rx, self.y + ry, p.net))
        return result
