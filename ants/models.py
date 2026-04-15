"""Colony blueprint and simulation row models + JSON helpers."""

from dataclasses import dataclass

from ants.config import COLONY_COLOR_RGB, REWARD_SYSTEMS, WORLD_HEIGHT, WORLD_WIDTH


def _norm_reward(v: object, default: str = "individualist") -> str:
    s = default if v is None else str(v)
    return s if s in REWARD_SYSTEMS else default


@dataclass
class ColonyBlueprint:
    name: str
    soldiers_str: str = "0"
    fetchers_str: str = "30"
    respawn_str: str = "5"
    reward_soldier: str = "individualist"
    reward_fetcher: str = "individualist"


@dataclass
class SimColony:
    name: str
    soldiers_str: str = "0"
    fetchers_str: str = "30"
    respawn_str: str = "5"
    reward_soldier: str = "individualist"
    reward_fetcher: str = "individualist"
    color_id: str = "black"
    nest_x: float | None = None
    nest_y: float | None = None


def default_blueprints() -> list[ColonyBlueprint]:
    out: list[ColonyBlueprint] = []
    for label, rw in (
        ("Individualist", "individualist"),
        ("Cooperative", "cooperative"),
        ("Safe", "safe"),
        ("Explorer", "explorer"),
    ):
        out.append(
            ColonyBlueprint(
                name=label,
                reward_soldier=rw,
                reward_fetcher=rw,
            )
        )
    return out


def _blueprint_to_dict(b: ColonyBlueprint) -> dict:
    return {
        "name": b.name,
        "soldiers_str": b.soldiers_str,
        "fetchers_str": b.fetchers_str,
        "respawn_str": b.respawn_str,
        "reward_soldier": b.reward_soldier,
        "reward_fetcher": b.reward_fetcher,
    }


def _blueprint_from_dict(o: object) -> ColonyBlueprint | None:
    if not isinstance(o, dict):
        return None
    name = o.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    rs = _norm_reward(o.get("reward_soldier", "individualist"))
    rf = _norm_reward(o.get("reward_fetcher", "individualist"))
    return ColonyBlueprint(
        name=name.strip(),
        soldiers_str=str(o.get("soldiers_str", "0")),
        fetchers_str=str(o.get("fetchers_str", "30")),
        respawn_str=str(o.get("respawn_str", "5")),
        reward_soldier=rs,
        reward_fetcher=rf,
    )


def _sim_colony_to_dict(c: SimColony) -> dict:
    d: dict = {
        "name": c.name,
        "soldiers_str": c.soldiers_str,
        "fetchers_str": c.fetchers_str,
        "respawn_str": c.respawn_str,
        "reward_soldier": c.reward_soldier,
        "reward_fetcher": c.reward_fetcher,
        "color_id": c.color_id if c.color_id in COLONY_COLOR_RGB else "black",
    }
    if c.nest_x is not None and c.nest_y is not None:
        d["nest_x"] = c.nest_x
        d["nest_y"] = c.nest_y
    return d


def _sim_colony_from_dict(o: object) -> SimColony | None:
    if not isinstance(o, dict):
        return None
    name = o.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    cid = o.get("color_id", "black")
    if cid not in COLONY_COLOR_RGB:
        cid = "black"
    nx = o.get("nest_x")
    ny = o.get("nest_y")
    nest_x: float | None
    nest_y: float | None
    try:
        nest_x = float(nx) if nx is not None else None
        nest_y = float(ny) if ny is not None else None
    except (TypeError, ValueError):
        nest_x, nest_y = None, None
    if nest_x is not None:
        nest_x = min(max(0.0, nest_x), WORLD_WIDTH)
    if nest_y is not None:
        nest_y = min(max(0.0, nest_y), WORLD_HEIGHT)
    if nest_x is None or nest_y is None:
        nest_x, nest_y = None, None
    if "reward_soldier" in o or "reward_fetcher" in o:
        rs = _norm_reward(o.get("reward_soldier"))
        rf = _norm_reward(o.get("reward_fetcher"))
    else:
        leg = _norm_reward(o.get("reward"))
        rs, rf = leg, leg
    return SimColony(
        name=name.strip(),
        soldiers_str=str(o.get("soldiers_str", "0")),
        fetchers_str=str(o.get("fetchers_str", "30")),
        respawn_str=str(o.get("respawn_str", "5")),
        reward_soldier=rs,
        reward_fetcher=rf,
        color_id=cid,
        nest_x=nest_x,
        nest_y=nest_y,
    )


def _v2_row_from_dict(o: object) -> SimColony | None:
    if not isinstance(o, dict):
        return None
    name = o.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    rw = _norm_reward(o.get("reward"))
    return SimColony(
        name=name.strip(),
        soldiers_str=str(o.get("soldiers_str", "0")),
        fetchers_str=str(o.get("fetchers_str", "30")),
        respawn_str=str(o.get("respawn_str", "5")),
        reward_soldier=rw,
        reward_fetcher=rw,
        color_id="black",
        nest_x=None,
        nest_y=None,
    )
