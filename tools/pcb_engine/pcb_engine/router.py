"""
Router — A* pathfinding-based PCB trace router.

Uses a grid representation of the board. Each cell can be:
- Empty (routable)
- Occupied by a pad
- Occupied by a trace
- Occupied by a via

Routes are found using A* on the grid, with support for multi-layer routing
via layer transitions (vias).
"""

import numpy as np
import heapq
from typing import List, Set, Tuple, Optional


class Router:
    def __init__(self, board, grid_resolution=0.25, power_nets=None):
        """
        grid_resolution: mm per grid cell (0.25mm = good balance for TQFP-144)
        """
        self.board = board
        self.res = grid_resolution
        self.power_nets = power_nets or set()

        # Grid dimensions
        self.cols = int(board.width / self.res) + 1
        self.rows = int(board.height / self.res) + 1

        # Layer indices
        self.layer_names = ["F.Cu", "B.Cu"]
        if board.layers >= 4:
            self.layer_names = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]

        # Obstacle grid: 0=free, 1=occupied
        # Shape: (layers, rows, cols)
        n_signal_layers = 4  # route on all 4 layers (F.Cu, In1.Cu, In2.Cu, B.Cu)
        self.grid = np.zeros((n_signal_layers, self.rows, self.cols), dtype=np.uint8)

        # Mark component courtyards as obstacles
        self._mark_obstacles()

    def _to_grid(self, x_mm, y_mm):
        return (int(round(y_mm / self.res)), int(round(x_mm / self.res)))

    def _to_mm(self, row, col):
        return (col * self.res, row * self.res)

    def _in_bounds(self, layer, row, col):
        return 0 <= layer < 4 and 0 <= row < self.rows and 0 <= col < self.cols

    def _mark_obstacles(self):
        """Mark only board edges as obstacles. Component bodies are NOT obstacles
        because traces can run under chips on inner layers."""
        # Only mark board edges
        self.grid[:, 0, :] = 1
        self.grid[:, -1, :] = 1
        self.grid[:, :, 0] = 1
        self.grid[:, :, -1] = 1

        # Clear pad locations and surrounding area (pads are routable endpoints)
        # Scale clearing radius to grid resolution
        clear_radius = max(3, int(1.0 / self.res))  # 1mm radius in grid cells
        for comp in self.board.components.values():
            for pad_num, ax, ay, net in comp.all_pads_abs():
                r, c = self._to_grid(ax, ay)
                for dr in range(-clear_radius, clear_radius + 1):
                    for dc in range(-clear_radius, clear_radius + 1):
                        nr, nc = r + dr, c + dc
                        if self._in_bounds(0, nr, nc):
                            self.grid[0, nr, nc] = 0
                            self.grid[1, nr, nc] = 0

    def _astar(self, start, end) -> Optional[List[Tuple[int, int, int]]]:
        """
        A* pathfinding on the routing grid.
        start/end: (layer, row, col)
        Returns list of (layer, row, col) waypoints, or None if no path.
        """
        sl, sr, sc = start
        el, er, ec = end

        if not self._in_bounds(sl, sr, sc) or not self._in_bounds(el, er, ec):
            return None

        # Priority queue: (cost, layer, row, col)
        open_set = [(0, sl, sr, sc)]
        came_from = {}
        g_score = {(sl, sr, sc): 0}

        # Heuristic: Manhattan distance + layer change penalty
        def h(l, r, c):
            return abs(r - er) + abs(c - ec) + abs(l - el) * 50

        iterations = 0
        max_iterations = 1000000

        while open_set and iterations < max_iterations:
            iterations += 1
            cost, cl, cr, cc = heapq.heappop(open_set)

            if (cl, cr, cc) == (el, er, ec):
                # Reconstruct path
                path = [(el, er, ec)]
                pos = (el, er, ec)
                while pos in came_from:
                    pos = came_from[pos]
                    path.append(pos)
                path.reverse()
                return path

            # Neighbors: 4 cardinal directions on same layer
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = cr + dr, cc + dc
                if self._in_bounds(cl, nr, nc) and self.grid[cl, nr, nc] == 0:
                    new_cost = g_score[(cl, cr, cc)] + 1
                    key = (cl, nr, nc)
                    if key not in g_score or new_cost < g_score[key]:
                        g_score[key] = new_cost
                        heapq.heappush(open_set, (new_cost + h(cl, nr, nc), cl, nr, nc))
                        came_from[key] = (cl, cr, cc)

            # Via: switch to adjacent layers
            for other_layer in range(4):
                if other_layer == cl: continue
                if self._in_bounds(other_layer, cr, cc) and self.grid[other_layer, cr, cc] == 0:
                    new_cost = g_score[(cl, cr, cc)] + 50
                    key = (other_layer, cr, cc)
                    if key not in g_score or new_cost < g_score[key]:
                        g_score[key] = new_cost
                        heapq.heappush(open_set, (new_cost + h(other_layer, cr, cc),
                                                  other_layer, cr, cc))
                        came_from[key] = (cl, cr, cc)

        return None  # no path found

    def _path_to_traces(self, path: List[Tuple[int, int, int]], net_name: str):
        """Convert a grid path to trace segments and vias."""
        if not path:
            return

        # Simplify: remove intermediate points on straight lines
        simplified = [path[0]]
        for i in range(1, len(path) - 1):
            prev = path[i - 1]
            curr = path[i]
            next_ = path[i + 1]
            # Keep point if direction changes or layer changes
            if (curr[0] != prev[0] or curr[0] != next_[0] or
                (curr[1] - prev[1]) != (next_[1] - curr[1]) or
                (curr[2] - prev[2]) != (next_[2] - curr[2])):
                simplified.append(curr)
        simplified.append(path[-1])

        layers = ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        trace_width = 0.25
        clearance_cells = 1  # minimal clearance for routing flexibility

        for i in range(len(simplified) - 1):
            l1, r1, c1 = simplified[i]
            l2, r2, c2 = simplified[i + 1]

            if l1 != l2:
                # Via
                x, y = self._to_mm(r1, c1)
                self.board.add_via(x, y, net=net_name)
            else:
                # Trace
                x1, y1 = self._to_mm(r1, c1)
                x2, y2 = self._to_mm(r2, c2)
                self.board.add_trace(x1, y1, x2, y2, net=net_name,
                                    layer=layers[l1], width=trace_width)

            # Mark EVERY cell along the trace segment with 1-cell clearance
            if l1 == l2:
                # Same layer — mark all cells between start and end
                if r1 == r2:  # horizontal
                    for col in range(min(c1,c2), max(c1,c2)+1):
                        for dr in range(-1, 2):
                            nr = r1 + dr
                            if self._in_bounds(l1, nr, col):
                                self.grid[l1, nr, col] = 1
                elif c1 == c2:  # vertical
                    for row in range(min(r1,r2), max(r1,r2)+1):
                        for dc in range(-1, 2):
                            nc = c1 + dc
                            if self._in_bounds(l1, row, nc):
                                self.grid[l1, row, nc] = 1
                else:  # diagonal — mark both endpoints
                    for l,r,c in [(l1,r1,c1),(l2,r2,c2)]:
                        for dr in range(-1,2):
                            for dc in range(-1,2):
                                if self._in_bounds(l,r+dr,c+dc):
                                    self.grid[l,r+dr,c+dc] = 1

    def route_net(self, net_name: str) -> bool:
        """Route a single net. Returns True if successful."""
        pads = self.board.get_net_pads(net_name)
        if len(pads) < 2:
            return True  # nothing to route

        # Deduplicate pads within 3mm of each other (inline resistors)
        unique_pads = [pads[0]]
        for p in pads[1:]:
            too_close = False
            for u in unique_pads:
                if abs(p[0]-u[0]) + abs(p[1]-u[1]) < 3.0:
                    too_close = True
                    break
            if not too_close:
                unique_pads.append(p)
        pads = unique_pads
        if len(pads) < 2:
            return True

        # Sort pads by nearest-neighbor for chain routing
        remaining = list(pads)
        chain = [remaining.pop(0)]
        while remaining:
            last = chain[-1]
            best_idx = min(range(len(remaining)),
                          key=lambda i: abs(remaining[i][0] - last[0]) +
                                       abs(remaining[i][1] - last[1]))
            chain.append(remaining.pop(best_idx))

        # Route each consecutive pair
        success = True
        for i in range(len(chain) - 1):
            x1, y1 = chain[i][0], chain[i][1]
            x2, y2 = chain[i + 1][0], chain[i + 1][1]

            sr, sc = self._to_grid(x1, y1)
            er, ec = self._to_grid(x2, y2)

            # Clear start and end on grid
            for l in range(2):
                if self._in_bounds(l, sr, sc):
                    self.grid[l, sr, sc] = 0
                if self._in_bounds(l, er, ec):
                    self.grid[l, er, ec] = 0

            # Try routing on F.Cu first, then with layer changes
            path = self._astar((0, sr, sc), (0, er, ec))
            if not path:
                path = self._astar((1, sr, sc), (1, er, ec))
            if not path:
                path = self._astar((0, sr, sc), (1, er, ec))
            if not path:
                path = self._astar((1, sr, sc), (0, er, ec))

            if path:
                self._path_to_traces(path, net_name)
            else:
                success = False

        return success

    def route_all(self):
        """Route all signal nets. Power nets are skipped (handled by planes)."""
        signal_nets = [(name, net) for name, net in self.board.nets.items()
                      if name not in self.power_nets and len(net.pads) >= 2]

        # Sort: hardest nets first, then by span (longest first)
        priority_nets = set()  # no special priority needed with 4 layers
        def net_sort_key(item):
            name = item[0]
            pads = self.board.get_net_pads(name)
            if len(pads) < 2: return (2, 0)
            xs = [p[0] for p in pads]
            ys = [p[1] for p in pads]
            span = max(xs)-min(xs) + max(ys)-min(ys)
            if name in priority_nets: return (0, -span)
            return (1, -span)
        signal_nets.sort(key=net_sort_key)

        routed = 0
        failed = 0
        print(f"  Routing order: {[n for n,_ in signal_nets[:5]]}...")
        for name, net in signal_nets:
            if self.route_net(name):
                routed += 1
            else:
                failed += 1
                print(f"  FAIL: {name} ({len(net.pads)} pads)")

        if failed > 0:
            # Retry: clear grid, put failed nets first
            failed_names = [name for name, net in signal_nets 
                          if not any(t.net == name for t in self.board.traces)]
            if failed_names:
                # Reset grid
                self.grid[:] = 0
                self._mark_obstacles()
                # Clear pad areas again
                clear_radius = max(3, int(1.0 / self.res))
                for comp in self.board.components.values():
                    for pad_num, ax, ay, net in comp.all_pads_abs():
                        r, c = self._to_grid(ax, ay)
                        for dr in range(-clear_radius, clear_radius + 1):
                            for dc in range(-clear_radius, clear_radius + 1):
                                nr, nc = r + dr, c + dc
                                if self._in_bounds(0, nr, nc):
                                    self.grid[0, nr, nc] = 0
                                    self.grid[1, nr, nc] = 0
                # Re-mark existing successful traces
                for t in self.board.traces:
                    r1, c1 = self._to_grid(t.x1, t.y1)
                    r2, c2 = self._to_grid(t.x2, t.y2)
                    layer = 0 if t.layer == "F.Cu" else 1
                    if r1 == r2:
                        for c in range(min(c1,c2), max(c1,c2)+1):
                            if self._in_bounds(layer, r1, c): self.grid[layer, r1, c] = 1
                    elif c1 == c2:
                        for r in range(min(r1,r2), max(r1,r2)+1):
                            if self._in_bounds(layer, r, c1): self.grid[layer, r, c1] = 1
                # Retry failed nets
                retry_ok = 0
                for name in failed_names:
                    if self.route_net(name):
                        retry_ok += 1
                        routed += 1
                        failed -= 1
                if retry_ok: print(f"  Retry recovered {retry_ok} nets")
        return routed, failed
