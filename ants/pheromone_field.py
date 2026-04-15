"""Per-colony pheromone dots: discrete deposits with linear decay over a fixed lifetime.

Each dot now carries a ``depositor_id`` (the Python ``id()`` of the ant that
placed it).  This enables the trail-attribution reward system: when another ant
follows a dot and later finds food, the original depositor receives a deferred
credit stored in ``GameState.phero_pending_credits``.
"""

from __future__ import annotations

from ants.config import PHEROMONE_LIFETIME_MS, PHEROMONE_TYPES, WORLD_HEIGHT, WORLD_WIDTH

# Hard cap so lists cannot grow without bound if the sim runs for a very long time.
_MAX_DOTS_PER_COLONY = 12_000


def linear_pheromone_strength(now_ms: int, created_ms: int) -> float:
    elapsed = now_ms - int(created_ms)
    if elapsed >= PHEROMONE_LIFETIME_MS:
        return 0.0
    return 1.0 - (elapsed / float(PHEROMONE_LIFETIME_MS))


class PheromoneField:
    """Pheromone dot storage per colony.

    Dot tuple layout: ``(ix, iy, layer, created_ms, depositor_id)``
      - ``ix``, ``iy``      : map-pixel coordinates
      - ``layer``           : 0 = type-A ("follow me"), 1 = type-B ("warning")
      - ``created_ms``      : wall-clock ms when the dot was deposited
      - ``depositor_id``    : ``id(ant)`` of the ant that placed the dot
    """

    def __init__(self, map_w: int, map_h: int, colony_count: int) -> None:
        self.map_w = max(1, int(map_w))
        self.map_h = max(1, int(map_h))
        self.colony_count = max(1, int(colony_count))
        # Each element: list[tuple[int,int,int,int,int]]  (ix,iy,layer,t,did)
        self.dots: list[list[tuple[int, int, int, int, int]]] = [
            [] for _ in range(self.colony_count)
        ]

    def reset(self) -> None:
        for ci in range(self.colony_count):
            self.dots[ci].clear()

    def cull_expired(self, now_ms: int) -> None:
        for ci in range(self.colony_count):
            ds = self.dots[ci]
            self.dots[ci] = [d for d in ds if linear_pheromone_strength(now_ms, d[3]) > 0.0]

    def deposit_world(
        self,
        colony_index: int,
        wx: float,
        wy: float,
        mask: tuple[bool, bool],
        map_rw: int,
        map_rh: int,
        now_ms: int,
        depositor_id: int = 0,
    ) -> None:
        """Deposit pheromone dots at world position (wx, wy).

        ``depositor_id`` should be ``id(ant)`` so deferred rewards can be
        traced back to the ant that created the trail.
        """
        if colony_index < 0 or colony_index >= self.colony_count:
            return
        ix_f = wx / WORLD_WIDTH * map_rw
        iy_f = wy / WORLD_HEIGHT * map_rh
        ix = int(ix_f)
        iy = int(iy_f)
        if not (0 <= ix < self.map_w and 0 <= iy < self.map_h):
            return
        row = self.dots[colony_index]
        did = int(depositor_id)
        for k in range(PHEROMONE_TYPES):
            if mask[k]:
                row.append((ix, iy, k, int(now_ms), did))
        while len(row) > _MAX_DOTS_PER_COLONY:
            row.pop(0)

    def sample_world_avg(
        self,
        colony_index: int,
        wx: float,
        wy: float,
        radius_px: float,
        map_rw: int,
        map_rh: int,
        now_ms: int,
    ) -> tuple[float, float]:
        if colony_index < 0 or colony_index >= self.colony_count:
            return (0.0, 0.0)
        lx = wx / WORLD_WIDTH * map_rw
        ly = wy / WORLD_HEIGHT * map_rh
        r = max(1, int(radius_px))
        ix0 = int(lx)
        iy0 = int(ly)
        acc = [0.0, 0.0]
        cnt = 0
        for di in range(-r, r + 1):
            for dj in range(-r, r + 1):
                if di * di + dj * dj > r * r:
                    continue
                ix = ix0 + di
                iy = iy0 + dj
                if not (0 <= ix < self.map_w and 0 <= iy < self.map_h):
                    continue
                cnt += 1
        if cnt <= 0:
            return (0.0, 0.0)
        inv = 1.0 / cnt
        r2 = float(r * r)
        for ix, iy, layer, t0, _did in self.dots[colony_index]:
            dx = (ix + 0.5) - lx
            dy = (iy + 0.5) - ly
            if dx * dx + dy * dy > r2:
                continue
            st = linear_pheromone_strength(now_ms, t0)
            if st <= 0.0:
                continue
            acc[layer] += st
        return (acc[0] * inv, acc[1] * inv)

    def nearest_depositor_world(
        self,
        colony_index: int,
        wx: float,
        wy: float,
        phero_type: int,
        radius_px: float,
        map_rw: int,
        map_rh: int,
        now_ms: int,
        exclude_id: int = 0,
    ) -> int | None:
        """Return the ``depositor_id`` of the strongest live dot of ``phero_type``
        within ``radius_px`` map-pixels of world point (wx, wy).

        ``exclude_id`` (typically ``id(self_ant)``) is skipped so ants don't
        attribute their own trail to themselves.  Returns ``None`` if no
        matching dot is found.
        """
        if colony_index < 0 or colony_index >= self.colony_count:
            return None
        lx = wx / WORLD_WIDTH  * map_rw
        ly = wy / WORLD_HEIGHT * map_rh
        r2 = float(radius_px * radius_px)
        best_st = 0.0
        best_id: int | None = None
        for ix, iy, layer, t0, did in self.dots[colony_index]:
            if layer != phero_type:
                continue
            if did == exclude_id:
                continue
            dx = (ix + 0.5) - lx
            dy = (iy + 0.5) - ly
            if dx * dx + dy * dy > r2:
                continue
            st = linear_pheromone_strength(now_ms, t0)
            if st > best_st:
                best_st = st
                best_id = did
        return best_id
