"""
DRC — Design Rule Check.
Verifies the board has no manufacturing errors.
"""

from dataclasses import dataclass
from typing import List
import math


@dataclass
class Violation:
    type: str
    message: str
    x: float = 0
    y: float = 0


class DRC:
    def __init__(self, board):
        self.board = board

    def check(self) -> List[Violation]:
        violations = []
        violations.extend(self._check_orphan_pads())
        violations.extend(self._check_trace_clearance())
        violations.extend(self._check_board_edge())
        return violations

    def _check_orphan_pads(self) -> List[Violation]:
        """Check for pads with no net assigned."""
        v = []
        for comp in self.board.components.values():
            for pad in comp.package.pads:
                if not pad.net:
                    pos = comp.pad_abs(pad.number)
                    x, y = pos if pos else (0, 0)
                    v.append(Violation("orphan_pad",
                        f"{comp.ref} pad {pad.number} has no net", x, y))
        return v

    def _check_trace_clearance(self) -> List[Violation]:
        """Check minimum clearance between traces of different nets."""
        v = []
        traces = self.board.traces
        min_clr = self.board.min_clearance

        for i in range(len(traces)):
            for j in range(i + 1, len(traces)):
                t1, t2 = traces[i], traces[j]
                if t1.net == t2.net:
                    continue
                if t1.layer != t2.layer:
                    continue
                dist = self._segment_distance(t1.x1, t1.y1, t1.x2, t1.y2,
                                              t2.x1, t2.y1, t2.x2, t2.y2)
                actual_clr = dist - (t1.width + t2.width) / 2
                if actual_clr < min_clr:
                    mx = (t1.x1 + t2.x1) / 2
                    my = (t1.y1 + t2.y1) / 2
                    v.append(Violation("clearance",
                        f"{t1.net} and {t2.net}: {actual_clr:.2f}mm < {min_clr}mm", mx, my))
        return v

    def _check_board_edge(self) -> List[Violation]:
        """Check traces don't go outside board outline."""
        v = []
        for t in self.board.traces:
            for x, y in [(t.x1, t.y1), (t.x2, t.y2)]:
                if x < 0 or x > self.board.width or y < 0 or y > self.board.height:
                    v.append(Violation("edge", f"Trace {t.net} at ({x:.1f},{y:.1f}) outside board", x, y))
        return v

    @staticmethod
    def _segment_distance(x1, y1, x2, y2, x3, y3, x4, y4) -> float:
        """Minimum distance between two line segments."""
        def point_to_segment(px, py, ax, ay, bx, by):
            dx, dy = bx - ax, by - ay
            if dx == 0 and dy == 0:
                return math.sqrt((px - ax)**2 + (py - ay)**2)
            t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / (dx*dx + dy*dy)))
            nx, ny = ax + t*dx, ay + t*dy
            return math.sqrt((px-nx)**2 + (py-ny)**2)

        return min(
            point_to_segment(x1, y1, x3, y3, x4, y4),
            point_to_segment(x2, y2, x3, y3, x4, y4),
            point_to_segment(x3, y3, x1, y1, x2, y2),
            point_to_segment(x4, y4, x1, y1, x2, y2),
        )
