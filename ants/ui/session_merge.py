from ants.config import (
    BRUSH_RADIUS_PRESETS,
    COLONY_COLOR_ORDER,
    FOOD_SPEED_COUNT,
    SESSION_V1,
    SESSION_V2,
    SESSION_VERSION,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.models import (
    ColonyBlueprint,
    SimColony,
    _blueprint_from_dict,
    _sim_colony_from_dict,
    _v2_row_from_dict,
    default_blueprints,
)
from ants.ui.state import GameState


def merge_session_dict(sd: dict | None, state: GameState) -> None:
    if sd is None:
        return
    ver = sd.get("version")
    if ver == SESSION_VERSION:
        raw_bp = sd.get("blueprints")
        if isinstance(raw_bp, list) and raw_bp:
            parsed_bp: list[ColonyBlueprint] = []
            for item in raw_bp:
                b = _blueprint_from_dict(item)
                if b is not None:
                    parsed_bp.append(b)
            if parsed_bp:
                state.blueprints = parsed_bp
        raw_sim = sd.get("simulation_colonies")
        if isinstance(raw_sim, list):
            parsed_sim: list[SimColony] = []
            for item in raw_sim:
                row = _sim_colony_from_dict(item)
                if row is not None:
                    parsed_sim.append(row)
            state.simulation_colonies = parsed_sim
        if "edit_colony_index" in sd:
            try:
                state.edit_colony_index = int(sd["edit_colony_index"])
            except (TypeError, ValueError):
                pass
    elif ver in (SESSION_V2, SESSION_V1):
        raw_cols = sd.get("colonies")
        if isinstance(raw_cols, list) and raw_cols:
            parsed_sim = []
            for k, item in enumerate(raw_cols):
                row = _v2_row_from_dict(item)
                if row is not None:
                    cid = COLONY_COLOR_ORDER[k % len(COLONY_COLOR_ORDER)]
                    row.color_id = cid
                    parsed_sim.append(row)
            if parsed_sim:
                state.simulation_colonies = parsed_sim
    if "next_custom_id" in sd:
        try:
            state.next_custom_id = max(1, int(sd["next_custom_id"]))
        except (TypeError, ValueError):
            pass
    if "colony_scroll" in sd:
        try:
            state.colony_scroll = int(sd["colony_scroll"])
        except (TypeError, ValueError):
            pass
    if "brush_radius_index" in sd:
        try:
            bi = int(sd["brush_radius_index"])
            if 0 <= bi < len(BRUSH_RADIUS_PRESETS):
                state.brush_radius_index = bi
                state.brush_radius_px = BRUSH_RADIUS_PRESETS[bi]
        except (TypeError, ValueError):
            pass
    if "sim_running" in sd:
        state.sim_running = bool(sd["sim_running"])
    if "sim_paused" in sd:
        state.sim_paused = bool(sd["sim_paused"])
    raw_foods = sd.get("foods")
    if isinstance(raw_foods, list):
        loaded: list[tuple[float, float]] = []
        for it in raw_foods:
            if not isinstance(it, dict):
                continue
            try:
                fx = float(it.get("x", 0.0))
                fy = float(it.get("y", 0.0))
            except (TypeError, ValueError):
                continue
            fx = min(max(0.0, fx), WORLD_WIDTH)
            fy = min(max(0.0, fy), WORLD_HEIGHT)
            loaded.append((fx, fy))
        if loaded:
            state.foods = loaded
    if state.sim_running:
        state.foods_at_run_start = list(state.foods)
    et = sd.get("edit_tool")
    if et in ("food", "terrain", "colony"):
        state.edit_tool = et
    if "food_speed_index" in sd:
        try:
            fsi = int(sd["food_speed_index"])
            if 0 <= fsi < FOOD_SPEED_COUNT:
                state.food_speed_index = fsi
        except (TypeError, ValueError):
            pass


def init_game_state_from_session(sd: dict | None) -> GameState:
    state = GameState(blueprints=default_blueprints())
    state.brush_radius_px = BRUSH_RADIUS_PRESETS[state.brush_radius_index]
    merge_session_dict(sd, state)
    if state.simulation_colonies:
        state.edit_colony_index = min(
            max(0, state.edit_colony_index), len(state.simulation_colonies) - 1
        )
    else:
        state.edit_colony_index = 0
    return state
