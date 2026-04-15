"""Wall-aware Dijkstra distance field from a nest position.

Computes a shortest-path cost map on a coarse PATHFINDER_GRID_N × PATHFINDER_GRID_N
grid.  Cells adjacent to walls get an extra step cost so the resulting paths
keep ants a comfortable distance from wall edges.

The result is cached per colony; ``is_stale`` detects when the nest has moved
by more than one cell and the map needs rebuilding.  During a normal simulation
run, terrain is fixed and nest positions don't change, so the build runs exactly
once per colony (a one-time cost accepted on the first frame).

Public API
----------
NestPathfinder.build(nest_wx, nest_wy, walkable)
    Recompute the distance field.  ``walkable`` is the same callable used by
    the rest of the simulation.

NestPathfinder.is_stale(nest_wx, nest_wy) -> bool
    True if the cached field was built for a different nest position.

NestPathfinder.path_dist(wx, wy) -> float
    Path cost from world point (wx, wy) to the nest.  math.inf if unreachable.

NestPathfinder.best_heading(wx, wy) -> float | None
    World heading (radians) of the cheapest neighbouring cell, i.e. the
    direction an ant at (wx, wy) should face to follow the shortest path home.
    Returns None at the nest or for unreachable cells.
"""

from __future__ import annotations

import heapq
import math
from typing import Callable

from ants.config import (
    PATHFINDER_GRID_N,
    PATHFINDER_WALL_MARGIN_CELLS,
    PATHFINDER_WALL_STEP_PENALTY,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)

# Directions: cardinal (cost 1) + diagonal (cost √2)
_NEIGHBOURS: tuple[tuple[int, int], ...] = (
    (-1,  0), ( 1,  0), ( 0, -1), ( 0,  1),
    (-1, -1), (-1,  1), ( 1, -1), ( 1,  1),
)


class NestPathfinder:
    """BFS/Dijkstra distance field from a single nest position."""

    def __init__(self) -> None:
        self._grid_n: int = PATHFINDER_GRID_N
        self.dist: list[list[float]] = []
        self._nest_wx: float | None = None
        self._nest_wy: float | None = None

    # ------------------------------------------------------------------
    # Coordinate helpers
    # ------------------------------------------------------------------

    def _to_grid(self, wx: float, wy: float) -> tuple[int, int]:
        n = self._grid_n
        gx = max(0, min(n - 1, int(wx / WORLD_WIDTH  * n)))
        gy = max(0, min(n - 1, int(wy / WORLD_HEIGHT * n)))
        return gx, gy

    def _to_world_center(self, gx: int, gy: int) -> tuple[float, float]:
        n = self._grid_n
        return (gx + 0.5) * WORLD_WIDTH / n, (gy + 0.5) * WORLD_HEIGHT / n

    # ------------------------------------------------------------------
    # Staleness check
    # ------------------------------------------------------------------

    def is_stale(self, nest_wx: float, nest_wy: float) -> bool:
        """Return True if the cached field was built for a different nest."""
        if self._nest_wx is None:
            return True
        # Tolerance: one grid cell
        tol_x = WORLD_WIDTH  / self._grid_n
        tol_y = WORLD_HEIGHT / self._grid_n
        return (abs(self._nest_wx - nest_wx) > tol_x or
                abs(self._nest_wy - nest_wy) > tol_y)

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(
        self,
        nest_wx: float,
        nest_wy: float,
        walkable: Callable[[float, float], bool],
    ) -> None:
        """Recompute the Dijkstra distance field from the nest position.

        ``walkable(wx, wy) -> bool`` should return True for passable ground.
        Wall-adjacent cells receive PATHFINDER_WALL_STEP_PENALTY extra cost so
        that Dijkstra prefers routes that stay away from walls.
        """
        n = self._grid_n
        margin = PATHFINDER_WALL_MARGIN_CELLS
        INF = math.inf

        # ---- classify each cell ----------------------------------------
        passable: list[list[bool]] = [[False] * n for _ in range(n)]
        for gy in range(n):
            for gx in range(n):
                wx_c, wy_c = self._to_world_center(gx, gy)
                passable[gy][gx] = walkable(wx_c, wy_c)

        near_wall: list[list[bool]] = [[False] * n for _ in range(n)]
        for gy in range(n):
            for gx in range(n):
                if not passable[gy][gx]:
                    continue
                for dy in range(-margin, margin + 1):
                    for dx in range(-margin, margin + 1):
                        nx_ = gx + dx
                        ny_ = gy + dy
                        if 0 <= nx_ < n and 0 <= ny_ < n:
                            if not passable[ny_][nx_]:
                                near_wall[gy][gx] = True
                                break
                    if near_wall[gy][gx]:
                        break

        # ---- Dijkstra from nest ----------------------------------------
        dist: list[list[float]] = [[INF] * n for _ in range(n)]
        ngx, ngy = self._to_grid(nest_wx, nest_wy)
        dist[ngy][ngx] = 0.0
        heap: list[tuple[float, int, int]] = [(0.0, ngx, ngy)]

        while heap:
            cost, cx, cy = heapq.heappop(heap)
            if cost > dist[cy][cx]:
                continue
            for ddx, ddy in _NEIGHBOURS:
                nx_ = cx + ddx
                ny_ = cy + ddy
                if not (0 <= nx_ < n and 0 <= ny_ < n):
                    continue
                if not passable[ny_][nx_]:
                    continue
                step = math.sqrt(ddx * ddx + ddy * ddy)
                if near_wall[ny_][nx_]:
                    step += PATHFINDER_WALL_STEP_PENALTY
                nc = cost + step
                if nc < dist[ny_][nx_]:
                    dist[ny_][nx_] = nc
                    heapq.heappush(heap, (nc, nx_, ny_))

        self.dist    = dist
        self._nest_wx = nest_wx
        self._nest_wy = nest_wy

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def path_dist(self, wx: float, wy: float) -> float:
        """Return Dijkstra path cost from (wx, wy) to the nest.

        Returns ``math.inf`` if the field has not been built yet or the cell is
        unreachable (e.g. inside a wall).
        """
        if not self.dist:
            return math.inf
        gx, gy = self._to_grid(wx, wy)
        return self.dist[gy][gx]

    def best_heading(self, wx: float, wy: float) -> float | None:
        """Return the heading (radians) toward the lowest-cost neighbouring cell.

        This is the direction an ant should face to follow the shortest walkable
        path home.  Returns ``None`` when at/near the nest or in an unreachable
        cell.
        """
        if not self.dist:
            return None
        n = self._grid_n
        gx, gy = self._to_grid(wx, wy)
        d_here = self.dist[gy][gx]
        if d_here == math.inf:
            return None

        best_cost = d_here
        best_ddx = 0
        best_ddy = 0
        for ddx, ddy in _NEIGHBOURS:
            nx_ = gx + ddx
            ny_ = gy + ddy
            if 0 <= nx_ < n and 0 <= ny_ < n:
                if self.dist[ny_][nx_] < best_cost:
                    best_cost = self.dist[ny_][nx_]
                    best_ddx = ddx
                    best_ddy = ddy

        if best_ddx == 0 and best_ddy == 0:
            return None  # already at nest / no cheaper neighbour

        # Convert grid step to world-space angle.
        # Grid axes align with world axes (gx→x right, gy→y down).
        wx_step = best_ddx * (WORLD_WIDTH  / n)
        wy_step = best_ddy * (WORLD_HEIGHT / n)
        return math.atan2(wy_step, wx_step)
