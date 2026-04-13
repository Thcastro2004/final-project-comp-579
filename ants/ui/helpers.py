import math
from typing import Any

from ants.config import (
    CARD_GAP,
    CARD_HEIGHT,
    COLONY_COLOR_ORDER,
    COLONY_COLOR_RGB,
    FOOD_GROW_PER_MS,
    REWARD_SYSTEMS,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.models import ColonyBlueprint, SimColony
from ants.ui.state import GameState, PanelLayout


def cycle_reward(current: str, delta: int) -> str:
    opts = list(REWARD_SYSTEMS)
    try:
        i = opts.index(current)
    except ValueError:
        i = 0
    return opts[(i + delta) % len(opts)]


def colonies_content_height(state: GameState) -> int:
    if not state.simulation_colonies:
        return 40
    return len(state.simulation_colonies) * (CARD_HEIGHT + CARD_GAP) + CARD_GAP


def clamp_scroll(state: GameState, panel: PanelLayout) -> None:
    max_scroll = max(0, colonies_content_height(state) - panel.scroll_rect.height)
    state.colony_scroll = min(max(0, state.colony_scroll), max_scroll)


def used_colony_colors(state: GameState) -> set[str]:
    return {c.color_id for c in state.simulation_colonies if c.color_id in COLONY_COLOR_RGB}


def first_free_color(state: GameState) -> str:
    for cid in COLONY_COLOR_ORDER:
        if cid not in used_colony_colors(state):
            return cid
    return "black"


def apply_colony_color(state: GameState, sim_idx: int, new_cid: str) -> None:
    if new_cid not in COLONY_COLOR_RGB:
        return
    c = state.simulation_colonies[sim_idx]
    old = c.color_id
    if old == new_cid:
        return
    for j, other in enumerate(state.simulation_colonies):
        if j != sim_idx and other.color_id == new_cid:
            other.color_id = old
            break
    c.color_id = new_cid


def sim_colony_from_blueprint(state: GameState, bp: ColonyBlueprint) -> SimColony:
    return SimColony(
        name=f"{bp.name} {state.next_custom_id}",
        soldiers_str=bp.soldiers_str,
        fetchers_str=bp.fetchers_str,
        respawn_str=bp.respawn_str,
        reward_soldier=bp.reward_soldier,
        reward_fetcher=bp.reward_fetcher,
        color_id=first_free_color(state),
        nest_x=None,
        nest_y=None,
    )


def in_editable(lx: float, ly: float, editable_inner: Any) -> bool:
    return (
        editable_inner.left <= lx < editable_inner.right
        and editable_inner.top <= ly < editable_inner.bottom
    )


def is_tunnel_at_map_pixel(
    pygame_mod: Any,
    terrain_surf: Any,
    lx: float,
    ly: float,
    map_rw: int,
    map_rh: int,
    terrain_tunnel: tuple[int, int, int],
    terrain_wall: tuple[int, int, int],
) -> bool:
    if not (0.0 <= lx < map_rw and 0.0 <= ly < map_rh):
        return False
    ix = int(min(map_rw - 1, max(0, lx)))
    iy = int(min(map_rh - 1, max(0, ly)))
    try:
        c = terrain_surf.get_at((ix, iy))
        rgb = (int(c[0]), int(c[1]), int(c[2]))
    except (ValueError, pygame_mod.error, IndexError, TypeError):
        return False
    if rgb == terrain_tunnel:
        return True
    tw = sum((rgb[i] - terrain_tunnel[i]) ** 2 for i in range(3))
    ww = sum((rgb[i] - terrain_wall[i]) ** 2 for i in range(3))
    return tw < ww


def is_colony_ground_at_map_pixel(
    pygame_mod: Any,
    terrain_surf: Any,
    lx: float,
    ly: float,
    map_rw: int,
    map_rh: int,
    editable_inner: Any,
    terrain_tunnel: tuple[int, int, int],
    terrain_wall: tuple[int, int, int],
) -> bool:
    return in_editable(lx, ly, editable_inner) and is_tunnel_at_map_pixel(
        pygame_mod, terrain_surf, lx, ly, map_rw, map_rh, terrain_tunnel, terrain_wall
    )


def is_tunnel_at_world(
    pygame_mod: Any,
    terrain_surf: Any,
    wx: float,
    wy: float,
    map_rw: int,
    map_rh: int,
    terrain_tunnel: tuple[int, int, int],
    terrain_wall: tuple[int, int, int],
) -> bool:
    lx = wx / WORLD_WIDTH * map_rw
    ly = wy / WORLD_HEIGHT * map_rh
    return is_tunnel_at_map_pixel(
        pygame_mod, terrain_surf, lx, ly, map_rw, map_rh, terrain_tunnel, terrain_wall
    )


def map_pixel_to_world(lx: float, ly: float, map_rw: int, map_rh: int) -> tuple[float, float]:
    return (lx / map_rw * WORLD_WIDTH, ly / map_rh * WORLD_HEIGHT)


def food_spawn_burst(
    pygame_mod: Any,
    terrain_surf: Any,
    state: GameState,
    panel: PanelLayout,
    lx_center: float,
    ly_center: float,
    elapsed_ms: int,
    terrain_tunnel: tuple[int, int, int],
    terrain_wall: tuple[int, int, int],
) -> None:
    import random

    R = min(panel.food_r_max_px, FOOD_GROW_PER_MS * max(0, elapsed_ms))
    R = max(2.0, R)
    k = state.food_speed_index + 1
    map_rw, map_rh = panel.map_rw, panel.map_rh
    for hi in range(k):
        if hi == 0 and is_tunnel_at_map_pixel(
            pygame_mod, terrain_surf, lx_center, ly_center, map_rw, map_rh, terrain_tunnel, terrain_wall
        ):
            state.foods.append(map_pixel_to_world(lx_center, ly_center, map_rw, map_rh))
            continue
        for _attempt in range(32):
            u = random.random() * 2 * math.pi
            v = random.random()
            rr = math.sqrt(v) * R
            clx = lx_center + math.cos(u) * rr
            cly = ly_center + math.sin(u) * rr
            if not (0.0 <= clx < map_rw and 0.0 <= cly < map_rh):
                continue
            if is_tunnel_at_map_pixel(
                pygame_mod, terrain_surf, clx, cly, map_rw, map_rh, terrain_tunnel, terrain_wall
            ):
                state.foods.append(map_pixel_to_world(clx, cly, map_rw, map_rh))
                break
