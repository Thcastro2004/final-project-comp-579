"""Three forward lobes (N, NW, NE in ant frame) -> feature vector."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from ants.config import (
    ANT_LOBE_OFFSET,
    ANT_LOBE_RADIUS,
    ANT_LOBE_SAMPLE_N,
    ANT_LOBE_SIDE_ANGLE_RAD,
    RL_FEATURE_DIM,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.models import SimColony

if TYPE_CHECKING:
    from ants.agents import Ant
    from ants.pheromone_field import PheromoneField


def _lobe_centers(x: float, y: float, heading: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    off = ANT_LOBE_OFFSET
    a = ANT_LOBE_SIDE_ANGLE_RAD
    return (
        (x + math.cos(heading) * off, y + math.sin(heading) * off),
        (x + math.cos(heading - a) * off, y + math.sin(heading - a) * off),
        (x + math.cos(heading + a) * off, y + math.sin(heading + a) * off),
    )


def lobe_centers_world(x: float, y: float, heading: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float]]:
    return _lobe_centers(x, y, heading)


def _sample_circle(wx: float, wy: float, radius: float, n: int) -> list[tuple[float, float]]:
    if n <= 0:
        return [(wx, wy)]
    # Fixed Vogel disk — same geometry every step (no RNG in phi).
    g = math.pi * (3.0 - math.sqrt(5.0))
    out: list[tuple[float, float]] = []
    for i in range(n):
        rr = radius * math.sqrt((i + 0.5) / float(n))
        th = g * float(i)
        out.append((wx + math.cos(th) * rr, wy + math.sin(th) * rr))
    return out


def _food_in_lobe(
    foods: list[tuple[float, float]],
    cx: float,
    cy: float,
    radius: float,
) -> float:
    r2 = radius * radius
    for fx, fy in foods:
        dx, dy = fx - cx, fy - cy
        if dx * dx + dy * dy <= r2:
            return 1.0
    return 0.0


def _nest_flags_in_lobe(
    colonies: list[SimColony],
    colony_index: int,
    cx: float,
    cy: float,
    radius: float,
) -> tuple[float, float]:
    r2 = radius * radius
    own = 0.0
    other = 0.0
    for ci, sc in enumerate(colonies):
        if sc.nest_x is None or sc.nest_y is None:
            continue
        dx, dy = sc.nest_x - cx, sc.nest_y - cy
        if dx * dx + dy * dy > r2:
            continue
        if ci == colony_index:
            own = 1.0
        else:
            other = 1.0
    return own, other


def _ants_in_lobe(
    ants: list[Ant],
    self_idx: int,
    colony_index: int,
    cx: float,
    cy: float,
    radius: float,
) -> tuple[float, float]:
    r2 = radius * radius
    ally = 0.0
    enemy = 0.0
    for j, a in enumerate(ants):
        if j == self_idx:
            continue
        dx, dy = a.x - cx, a.y - cy
        if dx * dx + dy * dy > r2:
            continue
        if a.colony_index == colony_index:
            ally = 1.0
        else:
            enemy = 1.0
    return ally, enemy


def build_phi(
    ant: Ant,
    ant_index: int,
    colonies: list[SimColony],
    ants: list[Ant],
    foods: list[tuple[float, float]],
    walkable: Callable[[float, float], bool],
    phero: PheromoneField | None,
    map_rw: int,
    map_rh: int,
    now_ms: int,
    path_features: list[float] | None = None,
) -> list[float]:
    """Build the feature vector for one ant.

    ``path_features`` (optional, length 2) appended after the lobe features:
      [0] normalised Dijkstra path-distance to nest (0.0 at nest, ~1+ far away)
  [1] cos(ant_heading − optimal_path_heading) when carrying; 0.0 otherwise

    With ``path_features`` supplied the returned vector has length 32
    (``RL_FEATURE_DIM``); without it the caller must supply [0.0, 0.0] or the
    assertion will fire.
    """
    centers = lobe_centers_world(ant.x, ant.y, ant.heading)
    r = ANT_LOBE_RADIUS
    n_samp = ANT_LOBE_SAMPLE_N
    lobe_px_r = max(2.0, r / WORLD_WIDTH * map_rw)

    lobe_feats: list[float] = []
    for cx, cy in centers:
        samples = _sample_circle(cx, cy, r, n_samp)
        wall_hits = 0
        for sx, sy in samples:
            wx = min(max(0.0, sx), WORLD_WIDTH)
            wy = min(max(0.0, sy), WORLD_HEIGHT)
            if not walkable(wx, wy):
                wall_hits += 1
        wall_frac = wall_hits / max(1, len(samples))
        fd = _food_in_lobe(foods, cx, cy, r)
        al, en = _ants_in_lobe(ants, ant_index, ant.colony_index, cx, cy, r)
        own_nest, other_nest = _nest_flags_in_lobe(colonies, ant.colony_index, cx, cy, r)
        if phero is not None:
            p0, p1 = phero.sample_world_avg(
                ant.colony_index, cx, cy, lobe_px_r, map_rw, map_rh, now_ms
            )
            p0 = min(1.0, p0)
            p1 = min(1.0, p1)
        else:
            p0 = p1 = 0.0
        lobe_feats.extend([wall_frac, fd, al, en, own_nest, other_nest, p0, p1])

    carry = 1.0 if ant.carrying else 0.0
    if ant.colony_index < len(colonies):
        sc = colonies[ant.colony_index]
        nest_x = 0.0 if sc.nest_x is None else sc.nest_x / WORLD_WIDTH
        nest_y = 0.0 if sc.nest_y is None else sc.nest_y / WORLD_HEIGHT
    else:
        nest_x = 0.0
        nest_y = 0.0
    extra = path_features if path_features is not None else [0.0, 0.0]
    phi = [1.0, carry, ant.x / WORLD_WIDTH, ant.y / WORLD_HEIGHT, nest_x, nest_y] + lobe_feats + extra
    assert len(phi) == RL_FEATURE_DIM, (len(phi), RL_FEATURE_DIM)
    return phi


def phi_for_terminal() -> list[float]:
    return [1.0] + [0.0] * (RL_FEATURE_DIM - 1)
