import math
from typing import Any

from ants.config import (
    FOOD_ERASE_SEARCH_RADIUS_PX,
    TERRAIN_SAVE_FILE,
    TERRAIN_TUNNEL,
    TERRAIN_WALL,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.persistence.session import session_write
from ants.persistence.terrain import terrain_save_bin, terrain_tmp_path
from ants.ui.helpers import in_editable, is_tunnel_at_world
from ants.ui.state import GameState, PanelLayout


def cull_food_not_on_tunnel(
    pygame_mod: Any,
    terrain_surf: Any,
    state: GameState,
    panel: PanelLayout,
) -> None:
    map_rw, map_rh = panel.map_rw, panel.map_rh
    state.foods[:] = [
        f
        for f in state.foods
        if is_tunnel_at_world(
            pygame_mod,
            terrain_surf,
            f[0],
            f[1],
            map_rw,
            map_rh,
            TERRAIN_TUNNEL,
            TERRAIN_WALL,
        )
    ]


def erase_foods_by_proximity(
    state: GameState,
    panel: PanelLayout,
    lx_map: float,
    ly_map: float,
) -> None:
    k = state.food_speed_index + 1
    r_lim = FOOD_ERASE_SEARCH_RADIUS_PX
    map_rw, map_rh = panel.map_rw, panel.map_rh
    scored: list[tuple[float, int]] = []
    for i, f in enumerate(state.foods):
        flx = f[0] / WORLD_WIDTH * map_rw
        fly = f[1] / WORLD_HEIGHT * map_rh
        d = math.hypot(flx - lx_map, fly - ly_map)
        if d <= r_lim:
            scored.append((d, i))
    scored.sort(key=lambda t: t[0])
    drop = {scored[j][1] for j in range(min(k, len(scored)))}
    if not drop:
        return
    state.foods[:] = [f for i, f in enumerate(state.foods) if i not in drop]


def stamp_brush(
    pygame_mod: Any,
    terrain_surf: Any,
    state: GameState,
    panel: PanelLayout,
    lx: float,
    ly: float,
    radius: int,
    color: tuple[int, int, int],
) -> None:
    if radius < 1 or not in_editable(lx, ly, panel.editable_inner):
        return
    old = terrain_surf.get_clip()
    terrain_surf.set_clip(panel.editable_inner)
    pygame_mod.draw.circle(terrain_surf, color, (int(lx), int(ly)), int(radius))
    terrain_surf.set_clip(old)
    if color == TERRAIN_WALL:
        cull_food_not_on_tunnel(pygame_mod, terrain_surf, state, panel)


def paint_brush_line(
    pygame_mod: Any,
    terrain_surf: Any,
    state: GameState,
    panel: PanelLayout,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    radius: int,
    color: tuple[int, int, int],
    *,
    step_frac: float = 0.5,
) -> None:
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    if dist < 0.5:
        stamp_brush(pygame_mod, terrain_surf, state, panel, x1, y1, radius, color)
        return
    step = max(1.0, radius * step_frac)
    n = max(1, int(math.ceil(dist / step)))
    for i in range(n + 1):
        t = i / n
        stamp_brush(pygame_mod, terrain_surf, state, panel, x0 + dx * t, y0 + dy * t, radius, color)


def save_terrain_and_session(pygame_mod: Any, terrain_surf: Any, state: GameState) -> None:
    tmp = terrain_tmp_path(TERRAIN_SAVE_FILE)
    try:
        terrain_save_bin(TERRAIN_SAVE_FILE, terrain_surf, pygame_mod)
    except (pygame_mod.error, OSError, TypeError, ValueError):
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
    session_write(
        state.blueprints,
        state.simulation_colonies,
        state.next_custom_id,
        state.colony_scroll,
        state.brush_radius_index,
        state.sim_running,
        state.sim_paused,
        state.foods,
        state.edit_tool,
        state.food_speed_index,
        state.edit_colony_index,
    )
