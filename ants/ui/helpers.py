import math
from typing import Any

from ants.config import (
    CARD_GAP,
    CARD_HEIGHT,
    COLONY_COLOR_ORDER,
    COLONY_COLOR_RGB,
    FOOD_GROW_PER_MS,
    MAP_ZOOM_MAX,
    MAP_ZOOM_MIN,
    MAP_ZOOM_STEP,
    REWARD_SYSTEMS,
    TERRAIN_TUNNEL_MAX_DIST_SQ,
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


def reset_map_view(state: GameState) -> None:
    state.map_zoom = MAP_ZOOM_MIN
    state.map_pan_x = 0.0
    state.map_pan_y = 0.0
    state.map_dragging = False


def map_sim_view_active(state: GameState) -> bool:
    return state.sim_running and not state.edit_map


def effective_map_zoom(state: GameState) -> float:
    return state.map_zoom if map_sim_view_active(state) else MAP_ZOOM_MIN


def clamp_map_pan(state: GameState, panel: PanelLayout) -> None:
    if not map_sim_view_active(state):
        state.map_pan_x = 0.0
        state.map_pan_y = 0.0
        return
    tw, th = panel.map_rw, panel.map_rh
    z = max(MAP_ZOOM_MIN, min(state.map_zoom, MAP_ZOOM_MAX))
    state.map_zoom = z
    sw = tw / z
    sh = th / z
    state.map_pan_x = min(max(0.0, state.map_pan_x), max(0.0, tw - sw))
    state.map_pan_y = min(max(0.0, state.map_pan_y), max(0.0, th - sh))


def apply_map_zoom_wheel(
    state: GameState,
    panel: PanelLayout,
    wheel_y: int,
    mx: int,
    my: int,
) -> None:
    if not map_sim_view_active(state):
        return
    rx, ry, rw, rh = panel.map_rx, panel.map_ry, panel.map_rw, panel.map_rh
    if not panel.map_screen_rect.collidepoint(mx, my):
        return
    lx = mx - rx
    ly = my - ry
    if not (0 <= lx < rw and 0 <= ly < rh):
        return
    tw, th = panel.map_rw, panel.map_rh
    z_old = max(MAP_ZOOM_MIN, min(state.map_zoom, MAP_ZOOM_MAX))
    sw_old = tw / z_old
    sh_old = th / z_old
    tlx = state.map_pan_x + (lx / rw) * sw_old
    tly = state.map_pan_y + (ly / rh) * sh_old
    z_new = z_old * (MAP_ZOOM_STEP**wheel_y)
    z_new = max(MAP_ZOOM_MIN, min(z_new, MAP_ZOOM_MAX))
    if abs(z_new - z_old) < 1e-9:
        return
    sw_new = tw / z_new
    sh_new = th / z_new
    state.map_zoom = z_new
    state.map_pan_x = tlx - (lx / rw) * sw_new
    state.map_pan_y = tly - (ly / rh) * sh_new
    if z_new <= MAP_ZOOM_MIN + 1e-9:
        state.map_pan_x = 0.0
        state.map_pan_y = 0.0
    clamp_map_pan(state, panel)


def world_to_map_screen(
    wx: float,
    wy: float,
    panel: PanelLayout,
    state: GameState,
) -> tuple[float, float]:
    tw, th = panel.map_rw, panel.map_rh
    tx = wx / WORLD_WIDTH * tw
    ty = wy / WORLD_HEIGHT * th
    rx, ry, rw, rh = panel.map_rx, panel.map_ry, panel.map_rw, panel.map_rh
    z = effective_map_zoom(state)
    if z <= MAP_ZOOM_MIN + 1e-9:
        return rx + tx / tw * rw, ry + ty / th * rh
    src_w = tw / z
    src_h = th / z
    sx = rx + (tx - state.map_pan_x) / src_w * rw
    sy = ry + (ty - state.map_pan_y) / src_h * rh
    return sx, sy


def map_texel_to_screen(
    tx: float,
    ty: float,
    panel: PanelLayout,
    state: GameState,
) -> tuple[float, float]:
    rx, ry, rw, rh = panel.map_rx, panel.map_ry, panel.map_rw, panel.map_rh
    tw, th = panel.map_rw, panel.map_rh
    z = effective_map_zoom(state)
    if z <= MAP_ZOOM_MIN + 1e-9:
        return rx + tx / tw * rw, ry + ty / th * rh
    src_w = tw / z
    src_h = th / z
    return (
        rx + (tx - state.map_pan_x) / src_w * rw,
        ry + (ty - state.map_pan_y) / src_h * rh,
    )


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
    return tw < ww and tw <= TERRAIN_TUNNEL_MAX_DIST_SQ


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
