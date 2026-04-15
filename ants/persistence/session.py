import json
import os

from ants.config import (
    BRUSH_RADIUS_PRESETS,
    COLONY_COLOR_ORDER,
    FOOD_SPEED_COUNT,
    SAVE_DIR,
    SESSION_SAVE_FILE,
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
    _blueprint_to_dict,
    _sim_colony_from_dict,
    _sim_colony_to_dict,
    _v2_row_from_dict,
)


def session_read() -> dict | None:
    if not SESSION_SAVE_FILE.is_file():
        return None
    try:
        d = json.loads(SESSION_SAVE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    ver = d.get("version")
    if ver not in (SESSION_VERSION, SESSION_V2, SESSION_V1):
        return None
    return d


def session_write(
    blueprints: list[ColonyBlueprint],
    simulation_colonies: list[SimColony],
    next_custom_id: int,
    colony_scroll: int,
    brush_radius_index: int,
    sim_running: bool,
    sim_paused: bool,
    foods: list[tuple[float, float]],
    edit_tool: str,
    food_speed_index: int,
    edit_colony_index: int,
) -> None:
    tmp = SESSION_SAVE_FILE.with_suffix(".tmp.json")
    et = edit_tool if edit_tool in ("terrain", "food", "colony") else "terrain"
    payload = {
        "version": SESSION_VERSION,
        "blueprints": [_blueprint_to_dict(b) for b in blueprints],
        "simulation_colonies": [_sim_colony_to_dict(c) for c in simulation_colonies],
        "next_custom_id": next_custom_id,
        "colony_scroll": colony_scroll,
        "brush_radius_index": brush_radius_index,
        "sim_running": sim_running,
        "sim_paused": sim_paused,
        "foods": [{"x": fx, "y": fy} for fx, fy in foods],
        "edit_tool": et,
        "food_speed_index": food_speed_index,
        "edit_colony_index": edit_colony_index,
    }
    try:
        SAVE_DIR.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(str(tmp), str(SESSION_SAVE_FILE))
    except (OSError, TypeError, ValueError):
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass
