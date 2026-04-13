import argparse
import io
import json
import math
import os
import random
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from ants.world import Viewport, World

# World size in abstract units (shown as a letterboxed rectangle on screen).
WORLD_WIDTH = 5600.0
WORLD_HEIGHT = 4800.0
WINDOW_WIDTH = 1500
WINDOW_HEIGHT = 800
PANEL_WIDTH = 500
PANEL_MARGIN = 10
CARD_GAP = 10
CARD_HEIGHT = 268
COLONY_CARD_WIDTH = 300
COLONY_DD_ROW_H = 26
BLUEPRINT_ARROW_W = 40
BLUEPRINT_ARROW_GAP = 12
REWARD_SYSTEMS = ("individualist", "cooperative", "safe", "explorer")
COLONY_COLOR_ORDER = ("black", "blue", "red", "purple", "yellow")
COLONY_COLOR_RGB: dict[str, tuple[int, int, int]] = {
    "black": (48, 48, 52),
    "blue": (88, 152, 255),
    "red": (235, 92, 92),
    "purple": (180, 120, 255),
    "yellow": (240, 210, 80),
}
MAX_SIM_COLONIES = 5
COLONY_SPRITE_SCALE = 1.5
COLONY_CURSOR_PREVIEW_MAX_PX = 72
# Debug: True = no colony hue tint, and skip white-punch so the raw PNG (incl. white pixels) shows.
DEBUG_COLONY_NO_TINT = False
# Debug: True = skip convert_alpha / convert after load (isolates load vs display-format issues).
DEBUG_COLONY_NO_CONVERT_ALPHA = False

TERRAIN_WALL = (78, 60, 51)  # #4e3c33
TERRAIN_TUNNEL = (133, 102, 88)  # #856658
BORDER_LOCK = 10
BRUSH_RADIUS_PRESETS = (12, 20, 32, 48, 72, 96)
BRUSH_PRESET_ROW_H = 42
BRUSH_PRESET_GAP = 6
BRUSH_PRESET_MAX = max(BRUSH_RADIUS_PRESETS)
BRUSH_PREVIEW_WHITE = (255, 255, 255)
BRUSH_PREVIEW_FAINT = (200, 210, 230)
FOOD_SPAWN_INTERVAL_MS = 72
FOOD_GROW_PER_MS = 0.028
FOOD_R_MAX_FRAC = 0.1
FOOD_ERASE_SEARCH_RADIUS_PX = 88
FOOD_SPEED_COUNT = 5
FOOD_CURSOR_PREVIEW_MAX_PX = 20
_ASSET_DIR = Path(__file__).resolve().parent / "asset"
_SAVE_DIR = Path(__file__).resolve().parent / "save"
# Raw RGB grid: magic "CMP1", uint32 LE width, uint32 LE height, then w*h*3 bytes row-major RGB.
TERRAIN_BIN_MAGIC = b"CMP1"
_TERRAIN_HEADER = struct.Struct("<4sII")
TERRAIN_SAVE_FILE = _SAVE_DIR / "terrain.bin"
_LEGACY_TERRAIN_FILE = Path(__file__).resolve().parent / "terrain_map.png"
SESSION_SAVE_FILE = _SAVE_DIR / "session.json"
SESSION_VERSION = 3
_SESSION_V2 = 2
_SESSION_V1 = 1


def _terrain_tmp_path(path: Path) -> Path:
    return path.parent / f"{path.stem}.tmp{path.suffix}"


def _terrain_candidate_paths() -> tuple[Path, ...]:
    return (
        TERRAIN_SAVE_FILE,
        _SAVE_DIR / "terrain_map.bmp",
        _SAVE_DIR / "terrain_map.png",
        _LEGACY_TERRAIN_FILE,
    )


def _terrain_pack_rgb(surf: object, pygame_mod: object) -> tuple[int, int, bytes]:
    w, h = surf.get_size()
    try:
        raw = pygame_mod.image.tobytes(surf, "RGB")
    except (pygame_mod.error, TypeError, ValueError):
        c = pygame_mod.Surface((w, h), depth=24)
        c.blit(surf, (0, 0))
        raw = pygame_mod.image.tobytes(c, "RGB")
    need = w * h * 3
    if len(raw) != need:
        raise ValueError("terrain rgb size mismatch")
    return w, h, raw


def _terrain_save_bin(path: Path, surf: object, pygame_mod: object) -> None:
    w, h, raw = _terrain_pack_rgb(surf, pygame_mod)
    tmp = _terrain_tmp_path(path)
    blob = _TERRAIN_HEADER.pack(TERRAIN_BIN_MAGIC, w, h) + raw
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_bytes(blob)
    os.replace(str(tmp), str(path))


def _terrain_decode_bin(data: bytes, pygame_mod: object) -> tuple[int, int, object] | None:
    if len(data) < _TERRAIN_HEADER.size:
        return None
    magic, w, h = _TERRAIN_HEADER.unpack_from(data, 0)
    if magic != TERRAIN_BIN_MAGIC:
        return None
    need = _TERRAIN_HEADER.size + w * h * 3
    if len(data) != need:
        return None
    raw = bytes(data[_TERRAIN_HEADER.size :])
    img = pygame_mod.image.frombuffer(raw, (w, h), "RGB")
    return w, h, img.convert()


def _terrain_blit_file_into(path: Path, pygame_mod: object, dest: object, map_rw: int, map_rh: int) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    tri = _terrain_decode_bin(data, pygame_mod)
    if tri is not None:
        lw, lh, loaded = tri
        if (lw, lh) == (map_rw, map_rh):
            dest.blit(loaded, (0, 0))
        elif lw > 0 and lh > 0:
            dest.blit(pygame_mod.transform.smoothscale(loaded, (map_rw, map_rh)), (0, 0))
        return True
    try:
        loaded = pygame_mod.image.load(io.BytesIO(data)).convert()
    except (pygame_mod.error, OSError, TypeError, ValueError):
        return False
    lw, lh = loaded.get_size()
    if (lw, lh) == (map_rw, map_rh):
        dest.blit(loaded, (0, 0))
    elif lw > 0 and lh > 0:
        dest.blit(pygame_mod.transform.smoothscale(loaded, (map_rw, map_rh)), (0, 0))
    return True


def _norm_reward(v: object, default: str = "individualist") -> str:
    s = default if v is None else str(v)
    return s if s in REWARD_SYSTEMS else default


@dataclass
class ColonyBlueprint:
    name: str
    soldiers_str: str = "3"
    fetchers_str: str = "5"
    respawn_str: str = "1.0"
    reward_soldier: str = "individualist"
    reward_fetcher: str = "individualist"


@dataclass
class SimColony:
    name: str
    soldiers_str: str = "3"
    fetchers_str: str = "5"
    respawn_str: str = "1.0"
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
        soldiers_str=str(o.get("soldiers_str", "3")),
        fetchers_str=str(o.get("fetchers_str", "5")),
        respawn_str=str(o.get("respawn_str", "1.0")),
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
        soldiers_str=str(o.get("soldiers_str", "3")),
        fetchers_str=str(o.get("fetchers_str", "5")),
        respawn_str=str(o.get("respawn_str", "1.0")),
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
        soldiers_str=str(o.get("soldiers_str", "3")),
        fetchers_str=str(o.get("fetchers_str", "5")),
        respawn_str=str(o.get("respawn_str", "1.0")),
        reward_soldier=rw,
        reward_fetcher=rw,
        color_id="black",
        nest_x=None,
        nest_y=None,
    )


def _session_read() -> dict | None:
    if not SESSION_SAVE_FILE.is_file():
        return None
    try:
        d = json.loads(SESSION_SAVE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError, TypeError):
        return None
    if not isinstance(d, dict):
        return None
    ver = d.get("version")
    if ver not in (SESSION_VERSION, _SESSION_V2, _SESSION_V1):
        return None
    return d


def _session_write(
    blueprints: list[ColonyBlueprint],
    simulation_colonies: list[SimColony],
    next_custom_id: int,
    colony_scroll: int,
    brush_radius_index: int,
    sim_running: bool,
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
        "foods": [{"x": fx, "y": fy} for fx, fy in foods],
        "edit_tool": et,
        "food_speed_index": food_speed_index,
        "edit_colony_index": edit_colony_index,
    }
    try:
        _SAVE_DIR.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(str(tmp), str(SESSION_SAVE_FILE))
    except (OSError, TypeError, ValueError):
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass


def _make_ui_fonts() -> tuple[object, object, object]:
    """Text rendering without ``pygame.font``: that module imports ``sysfont``, which imports
    ``pygame.font`` again and deadlocks on some runtimes (notably Python 3.14 + pygame 2.6.x).
    """
    import pygame._freetype as _ft

    _ft.init()

    class _UiFont:
        __slots__ = ("_f",)

        def __init__(self, size: int, *, strong: bool = False) -> None:
            self._f = _ft.Font(None, size=max(1, int(size)))
            self._f.antialiased = True
            if strong:
                self._f.strong = True

        def render(self, text, antialias, color, background=None):
            self._f.antialiased = bool(antialias)
            t = "" if text is None else str(text)
            if background is not None:
                return self._f.render(t, fgcolor=color, bgcolor=background)[0]
            return self._f.render(t, fgcolor=color)[0]

    return _UiFont(15), _UiFont(13), _UiFont(17, strong=True)


def _colony_png_search_paths() -> tuple[Path, ...]:
    root = Path(__file__).resolve().parent
    return (
        root / "asset" / "ant-colony.png",
        root / "ant-colony.png",
        Path.cwd() / "asset" / "ant-colony.png",
        Path.cwd() / "ant-colony.png",
    )


def _pygame_load_png(pygame_mod: object, path: Path) -> object | None:
    # Path string first (same as food sprite), then bytes. SDL/pygame can raise types outside
    # (pygame.error, OSError) on some builds — catch broadly so we still try the other route.
    try:
        return pygame_mod.image.load(str(path.resolve()))
    except Exception:
        pass
    try:
        return pygame_mod.image.load(io.BytesIO(path.read_bytes()))
    except Exception:
        pass
    return _png_surface_via_pillow(pygame_mod, path)


def _png_surface_via_pillow(pygame_mod: object, path: Path) -> object | None:
    """Decode PNG with Pillow when SDL image fails (common for some pygame/mac builds)."""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGBA")
            w, h = im.size
            raw = im.tobytes("raw", "RGBA")
    except Exception:
        return None
    try:
        surf = pygame_mod.image.frombuffer(raw, (w, h), "RGBA")
        return surf.copy()
    except Exception:
        return None


def _synthetic_nest_icon(pygame_mod: object, size: int = 28) -> object:
    s = pygame_mod.Surface((size, size), pygame_mod.SRCALPHA)
    cx = size // 2
    r = max(4, size // 2 - 3)
    pygame_mod.draw.circle(s, (220, 220, 228, 255), (cx, cx), r)
    pygame_mod.draw.circle(s, (40, 42, 52, 255), (cx, cx), r, width=2)
    return s


def _punch_near_white_transparent(surf: object, pygame_mod: object, thresh: int = 242) -> None:
    """Drop light/white backdrop so multiply-tint does not paint a solid tile on the map."""
    w, h = surf.get_size()
    for y in range(h):
        for x in range(w):
            c = surf.get_at((x, y))
            if len(c) < 4:
                continue
            r, g, b, a = int(c[0]), int(c[1]), int(c[2]), int(c[3])
            if a > 8 and r >= thresh and g >= thresh and b >= thresh:
                surf.set_at((x, y), (0, 0, 0, 0))


# def _nest_icon_tint_rgb(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
#     """Blend colony hue with a light tunnel tone so dark palette entries stay visible on brown terrain."""
#     hi = (196, 168, 148)
#     return tuple(min(255, int(rgb[i] * 0.48 + hi[i] * 0.52)) for i in range(3))


def _tint_colony_sprite(surf: object, rgb: tuple[int, int, int], pygame_mod: object) -> object:
    """Recolor icon by luminance. BLEND_RGBA_MULT leaves black at (0,0,0) so all colonies looked the same."""
    t = surf.copy()
    try:
        t = t.convert_alpha()
    except (pygame_mod.error, TypeError, ValueError):
        try:
            t = t.convert(32)
        except (pygame_mod.error, TypeError, ValueError):
            pass
    r_t, g_t, b_t = rgb
    # Dark end keeps enough saturation to read as blue/red/purple (too low * looked black).
    dr, dg, db = int(r_t * 0.38), int(g_t * 0.38), int(b_t * 0.38)
    # Bright end: bump colony RGB so the ant reads lighter than tunnel tan, without washing to grey.
    lr, lg, lb = min(255, r_t + 48), min(255, g_t + 48), min(255, b_t + 48)
    w, h = t.get_size()
    for yy in range(h):
        for xx in range(w):
            c = t.get_at((xx, yy))
            if len(c) < 4:
                continue
            R, G, B, a = int(c[0]), int(c[1]), int(c[2]), int(c[3])
            if a < 8:
                continue
            luma = (0.299 * R + 0.587 * G + 0.114 * B) / 255.0
            luma = min(1.0, max(0.0, luma))
            # Mild S-curve: a bit more disk vs glyph separation, without crushing hue to black.
            luma = luma * luma * (3.0 - 2.0 * luma)
            nr = int(dr + (lr - dr) * luma + 0.5)
            ng = int(dg + (lg - dg) * luma + 0.5)
            nb = int(db + (lb - db) * luma + 0.5)
            t.set_at(
                (xx, yy),
                (max(0, min(255, nr)), max(0, min(255, ng)), max(0, min(255, nb)), a),
            )
    return t


def run_headless() -> int:
    world = World(WORLD_WIDTH, WORLD_HEIGHT)
    print("Headless mode: no display (batch / RL later).")
    print(f"World: {world.width} x {world.height}")
    return 0


def run_window() -> int:
    import pygame

    world = World(WORLD_WIDTH, WORLD_HEIGHT)
    world_w = WINDOW_WIDTH - PANEL_WIDTH
    viewport = Viewport(
        world,
        WINDOW_WIDTH,
        WINDOW_HEIGHT,
        margin=20,
        content_rect=(0, 0, world_w, WINDOW_HEIGHT),
    )
    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Ant colony sim")
    clock = pygame.time.Clock()
    font, font_small, font_title = _make_ui_fonts()
    food_sprite_path = _ASSET_DIR / "ant-food.png"
    food_cursor_sprite = None
    food_sprite = None
    try:
        _raw_food = pygame.image.load(str(food_sprite_path.resolve()))
        try:
            food_sprite = _raw_food.convert_alpha()
        except (pygame.error, TypeError, ValueError):
            food_sprite = _raw_food.convert()
        iw, ih = food_sprite.get_size()
        if iw > 0 and ih > 0:
            hw = max(1, int(round(iw * 0.5)))
            hh = max(1, int(round(ih * 0.5)))
            if (hw, hh) != (iw, ih):
                food_sprite = pygame.transform.smoothscale(food_sprite, (hw, hh))
            cw, ch = food_sprite.get_size()
            cap = FOOD_CURSOR_PREVIEW_MAX_PX
            cscale = min(cap / cw, cap / ch, 1.0)
            nw = max(1, int(round(cw * cscale)))
            nh = max(1, int(round(ch * cscale)))
            food_cursor_sprite = (
                pygame.transform.smoothscale(food_sprite, (nw, nh))
                if (nw, nh) != (cw, ch)
                else food_sprite
            )
    except (pygame.error, OSError, TypeError, ValueError):
        food_sprite = None
        food_cursor_sprite = None

    colony_base_sprite = None
    colony_cursor_sprite = None
    colony_tinted: dict[str, object] = {}
    _raw_col = None
    _colony_png_primary = _ASSET_DIR / "ant-colony.png"
    try:
        _raw_col = pygame.image.load(str(_colony_png_primary.resolve()))
    except Exception:
        _raw_col = None
    if _raw_col is None:
        _raw_col = _png_surface_via_pillow(pygame, _colony_png_primary)
    if _raw_col is None:
        _seen_colony_path: set[str] = set()
        for _cp in _colony_png_search_paths():
            _key = str(_cp.resolve())
            if _key in _seen_colony_path:
                continue
            _seen_colony_path.add(_key)
            _raw_col = _pygame_load_png(pygame, _cp)
            if _raw_col is not None:
                break
    if _raw_col is not None:
        if DEBUG_COLONY_NO_CONVERT_ALPHA:
            colony_base_sprite = _raw_col
        else:
            colony_base_sprite = _raw_col
            try:
                colony_base_sprite = _raw_col.convert_alpha()
            except Exception:
                try:
                    colony_base_sprite = _raw_col.convert(32)
                except Exception:
                    try:
                        colony_base_sprite = _raw_col.convert()
                    except Exception:
                        pass
        iw, ih = colony_base_sprite.get_size()
        if iw > 0 and ih > 0:
            hw = max(1, int(round(iw * COLONY_SPRITE_SCALE)))
            hh = max(1, int(round(ih * COLONY_SPRITE_SCALE)))
            if (hw, hh) != (iw, ih):
                try:
                    colony_base_sprite = pygame.transform.smoothscale(colony_base_sprite, (hw, hh))
                except Exception:
                    pass
        if colony_base_sprite is not None:
            if not DEBUG_COLONY_NO_TINT:
                try:
                    _punch_near_white_transparent(colony_base_sprite, pygame)
                except (pygame.error, TypeError, ValueError, AttributeError, OSError):
                    pass
            try:
                cw, ch = colony_base_sprite.get_size()
                cap = COLONY_CURSOR_PREVIEW_MAX_PX
                cscale = min(cap / cw, cap / ch, 1.0)
                nw = max(1, int(round(cw * cscale)))
                nh = max(1, int(round(ch * cscale)))
                colony_cursor_sprite = (
                    pygame.transform.smoothscale(colony_base_sprite, (nw, nh))
                    if (nw, nh) != (cw, ch)
                    else colony_base_sprite
                )
            except Exception:
                colony_cursor_sprite = colony_base_sprite
    else:
        print("[ants] ant-colony.png not loaded. Candidates:", file=sys.stderr)
        for _cp in _colony_png_search_paths():
            _r = _cp.resolve()
            print(f"  {_r}  exists={_r.is_file()}", file=sys.stderr)
        try:
            pygame.image.load(str(_colony_png_primary.resolve()))
        except Exception as _e:
            print(f"[ants] pygame.image.load({_colony_png_primary.resolve()!s}) -> {_e!r}", file=sys.stderr)
        colony_base_sprite = _synthetic_nest_icon(pygame)
        try:
            colony_base_sprite = colony_base_sprite.convert_alpha()
        except Exception:
            pass
        try:
            cw, ch = colony_base_sprite.get_size()
            cap = COLONY_CURSOR_PREVIEW_MAX_PX
            cscale = min(cap / cw, cap / ch, 1.0)
            nw = max(1, int(round(cw * cscale)))
            nh = max(1, int(round(ch * cscale)))
            colony_cursor_sprite = (
                pygame.transform.smoothscale(colony_base_sprite, (nw, nh))
                if (nw, nh) != (cw, ch)
                else colony_base_sprite
            )
        except Exception:
            colony_cursor_sprite = colony_base_sprite
        print("[ants] using built-in nest icon (see errors above).", file=sys.stderr)
        try:
            import PIL  # noqa: F401
        except ImportError:
            print("[ants] install pillow (pip install pillow) if pygame cannot decode PNGs on your system.", file=sys.stderr)

    def colony_sprite_for_color(color_id: str) -> object | None:
        if colony_base_sprite is None:
            return None
        if DEBUG_COLONY_NO_TINT:
            return colony_base_sprite
        if color_id not in COLONY_COLOR_RGB:
            color_id = "black"
        if color_id not in colony_tinted:
            try:
                colony_tinted[color_id] = _tint_colony_sprite(
                    colony_base_sprite, COLONY_COLOR_RGB[color_id], pygame
                )
            except Exception:
                return colony_base_sprite
        return colony_tinted[color_id]

    def colony_cursor_for_color(color_id: str) -> object | None:
        base = colony_cursor_sprite if colony_cursor_sprite is not None else colony_base_sprite
        if base is None:
            return None
        if DEBUG_COLONY_NO_TINT:
            return base
        key = f"c:{color_id}"
        if key not in colony_tinted:
            if color_id not in COLONY_COLOR_RGB:
                color_id = "black"
            try:
                colony_tinted[key] = _tint_colony_sprite(
                    base, COLONY_COLOR_RGB[color_id], pygame
                )
            except Exception:
                return base
        return colony_tinted[key]

    map_rx, map_ry, map_rw, map_rh = viewport.world_rect_screen()
    terrain_surf = pygame.Surface((map_rw, map_rh))
    terrain_surf.fill(TERRAIN_WALL)

    for _tp in _terrain_candidate_paths():
        if _tp.is_file() and _terrain_blit_file_into(_tp, pygame, terrain_surf, map_rw, map_rh):
            break

    _ed_w = max(0, map_rw - 2 * BORDER_LOCK)
    _ed_h = max(0, map_rh - 2 * BORDER_LOCK)
    editable_inner = pygame.Rect(BORDER_LOCK, BORDER_LOCK, _ed_w, _ed_h)
    food_r_max_px = max(8.0, min(map_rw, map_rh) * FOOD_R_MAX_FRAC)

    def _in_editable(lx: float, ly: float) -> bool:
        return (
            editable_inner.left <= lx < editable_inner.right
            and editable_inner.top <= ly < editable_inner.bottom
        )

    border_color = (120, 140, 160)
    panel_bg = (24, 28, 38)
    panel_border = (55, 62, 78)
    card_bg = (34, 38, 50)
    card_border = (70, 78, 98)
    btn_idle = (52, 58, 76)
    btn_hover = (68, 76, 98)
    btn_active = (82, 110, 150)
    text_color = (230, 232, 238)
    muted = (160, 165, 180)
    field_bg = (28, 32, 44)
    field_focus = (120, 150, 210)

    blueprints: list[ColonyBlueprint] = default_blueprints()
    simulation_colonies: list[SimColony] = []
    foods: list[tuple[float, float]] = []
    sim_running = False
    edit_map = False
    edit_tool = "terrain"
    brush_dropdown_open = False
    food_speed_dropdown_open = False
    brush_radius_index = 2
    brush_radius_px = BRUSH_RADIUS_PRESETS[brush_radius_index]
    food_speed_index = 2
    last_stroke_left: tuple[float, float] | None = None
    last_stroke_right: tuple[float, float] | None = None
    food_press_ms = 0
    last_food_spawn_ms = 0
    last_food_erase_ms = 0
    food_lmb_active = False
    food_rmb_active = False
    colony_scroll = 0
    next_custom_id = 1
    edit_colony_index = 0
    add_modal_open = False
    add_modal_bp_index = 0
    new_bp_modal_open = False
    new_bp_name = "Custom blueprint"
    new_bp_soldiers_str = "3"
    new_bp_fetchers_str = "5"
    new_bp_respawn_str = "1.0"
    new_bp_reward_soldier = "individualist"
    new_bp_reward_fetcher = "individualist"
    focused_field: tuple[int, str] | None = None
    focused_bp_field: str | None = None
    # (colony_index, "soldier"|"fetcher"|"color") when that dropdown list is open
    colony_dd: tuple[int, str] | None = None

    panel_x = world_w
    btn_h = 32
    row1_y = 44
    row2_y = row1_y + btn_h + 8
    edit_done_y = 46
    edit_brush_y = edit_done_y + btn_h + 12
    col_label_y = row2_y + btn_h + 12
    add_btn_h = 30
    add_y = col_label_y + 22
    scroll_y0 = add_y + add_btn_h + 8
    scroll_rect = pygame.Rect(
        panel_x + PANEL_MARGIN,
        scroll_y0,
        PANEL_WIDTH - 2 * PANEL_MARGIN,
        WINDOW_HEIGHT - scroll_y0 - PANEL_MARGIN,
    )

    def draw_button(surf: pygame.Surface, rect: pygame.Rect, label: str, hover: bool, toggled: bool = False) -> None:
        bg = btn_active if toggled else (btn_hover if hover else btn_idle)
        pygame.draw.rect(surf, bg, rect, border_radius=6)
        pygame.draw.rect(surf, panel_border, rect, width=1, border_radius=6)
        t = font.render(label, True, text_color)
        surf.blit(t, t.get_rect(center=rect.center))

    def draw_text_field(
        surf: pygame.Surface,
        rect: pygame.Rect,
        value: str,
        label: str,
        focused: bool,
    ) -> None:
        pygame.draw.rect(surf, field_bg, rect, border_radius=4)
        w = 2 if focused else 1
        c = field_focus if focused else panel_border
        pygame.draw.rect(surf, c, rect, width=w, border_radius=4)
        lab = font_small.render(label, True, muted)
        surf.blit(lab, (rect.x, rect.y - 16))
        txt = font_small.render(value or " ", True, text_color)
        pad = 6
        surf.blit(txt, (rect.x + pad, rect.centery - txt.get_height() // 2))

    def draw_entry_only(
        surf: pygame.Surface,
        rect: pygame.Rect,
        value: str,
        focused: bool,
    ) -> None:
        pygame.draw.rect(surf, field_bg, rect, border_radius=4)
        w = 2 if focused else 1
        c = field_focus if focused else panel_border
        pygame.draw.rect(surf, c, rect, width=w, border_radius=4)
        txt = font_small.render(value or " ", True, text_color)
        pad = 5
        surf.blit(txt, (rect.x + pad, rect.centery - txt.get_height() // 2))

    def draw_combo_head(
        surf: pygame.Surface,
        rect: pygame.Rect,
        text: str,
        open_: bool,
        hover: bool,
        lead_rgb: tuple[int, int, int] | None = None,
    ) -> None:
        bg = btn_hover if hover else field_bg
        pygame.draw.rect(surf, bg, rect, border_radius=6)
        pygame.draw.rect(surf, field_focus if open_ else panel_border, rect, width=2 if open_ else 1, border_radius=6)
        disp = text if len(text) <= 22 else text[:19] + "…"
        t = font_small.render(disp, True, text_color)
        tx = rect.x + 8
        if lead_rgb is not None:
            pygame.draw.circle(surf, lead_rgb, (rect.x + 11, rect.centery), 6)
            tx = rect.x + 26
        surf.blit(t, (tx, rect.centery - t.get_height() // 2))
        tcx = rect.right - 14
        tcy = rect.centery
        ts = 5
        if open_:
            tri = [(tcx - ts, tcy + ts // 2), (tcx + ts, tcy + ts // 2), (tcx, tcy - ts // 2)]
        else:
            tri = [(tcx - ts, tcy - ts // 2), (tcx + ts, tcy - ts // 2), (tcx, tcy + ts // 2)]
        pygame.draw.polygon(surf, muted, tri)

    def draw_colony_invalid_cross(surf: pygame.Surface, cx: int, cy: int) -> None:
        arm = 6
        red = (228, 72, 72)
        pygame.draw.line(surf, red, (cx - arm, cy - arm), (cx + arm, cy + arm), 2)
        pygame.draw.line(surf, red, (cx - arm, cy + arm), (cx + arm, cy - arm), 2)

    def draw_trash_icon_button(surf: pygame.Surface, rect: pygame.Rect, hover: bool) -> None:
        bg = btn_hover if hover else (56, 60, 76)
        pygame.draw.rect(surf, bg, rect, border_radius=5)
        pygame.draw.rect(surf, panel_border, rect, width=1, border_radius=5)
        tcx, tcy = rect.center
        ic = text_color if hover else (198, 204, 218)
        pygame.draw.line(surf, ic, (tcx - 7, tcy - 5), (tcx + 7, tcy - 5), 2)
        pygame.draw.line(surf, ic, (tcx - 5, tcy - 7), (tcx + 5, tcy - 7), 2)
        pts = [(tcx - 6, tcy - 4), (tcx + 6, tcy - 4), (tcx + 5, tcy + 6), (tcx - 5, tcy + 6)]
        pygame.draw.lines(surf, ic, True, pts, 2)
        pygame.draw.line(surf, ic, (tcx - 3, tcy - 1), (tcx - 3, tcy + 4), 1)
        pygame.draw.line(surf, ic, (tcx, tcy - 1), (tcx, tcy + 4), 1)
        pygame.draw.line(surf, ic, (tcx + 3, tcy - 1), (tcx + 3, tcy + 4), 1)

    def cycle_reward(current: str, delta: int) -> str:
        opts = list(REWARD_SYSTEMS)
        try:
            i = opts.index(current)
        except ValueError:
            i = 0
        return opts[(i + delta) % len(opts)]

    def colonies_content_height() -> int:
        if not simulation_colonies:
            return 40
        return len(simulation_colonies) * (CARD_HEIGHT + CARD_GAP) + CARD_GAP

    def clamp_scroll() -> None:
        nonlocal colony_scroll
        max_scroll = max(0, colonies_content_height() - scroll_rect.height)
        colony_scroll = min(max(0, colony_scroll), max_scroll)

    def used_colony_colors() -> set[str]:
        return {c.color_id for c in simulation_colonies if c.color_id in COLONY_COLOR_RGB}

    def first_free_color() -> str:
        for cid in COLONY_COLOR_ORDER:
            if cid not in used_colony_colors():
                return cid
        return "black"

    def apply_colony_color(sim_idx: int, new_cid: str) -> None:
        if new_cid not in COLONY_COLOR_RGB:
            return
        c = simulation_colonies[sim_idx]
        old = c.color_id
        if old == new_cid:
            return
        for j, other in enumerate(simulation_colonies):
            if j != sim_idx and other.color_id == new_cid:
                other.color_id = old
                break
        c.color_id = new_cid

    def sim_colony_from_blueprint(bp: ColonyBlueprint) -> SimColony:
        return SimColony(
            name=f"{bp.name} {next_custom_id}",
            soldiers_str=bp.soldiers_str,
            fetchers_str=bp.fetchers_str,
            respawn_str=bp.respawn_str,
            reward_soldier=bp.reward_soldier,
            reward_fetcher=bp.reward_fetcher,
            color_id=first_free_color(),
            nest_x=None,
            nest_y=None,
        )

    sd = _session_read()
    if sd is not None:
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
                    blueprints = parsed_bp
            raw_sim = sd.get("simulation_colonies")
            if isinstance(raw_sim, list):
                parsed_sim: list[SimColony] = []
                for item in raw_sim:
                    row = _sim_colony_from_dict(item)
                    if row is not None:
                        parsed_sim.append(row)
                simulation_colonies = parsed_sim
            if "edit_colony_index" in sd:
                try:
                    edit_colony_index = int(sd["edit_colony_index"])
                except (TypeError, ValueError):
                    pass
        elif ver in (_SESSION_V2, _SESSION_V1):
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
                    simulation_colonies = parsed_sim
        if "next_custom_id" in sd:
            try:
                next_custom_id = max(1, int(sd["next_custom_id"]))
            except (TypeError, ValueError):
                pass
        if "colony_scroll" in sd:
            try:
                colony_scroll = int(sd["colony_scroll"])
            except (TypeError, ValueError):
                pass
        if "brush_radius_index" in sd:
            try:
                bi = int(sd["brush_radius_index"])
                if 0 <= bi < len(BRUSH_RADIUS_PRESETS):
                    brush_radius_index = bi
                    brush_radius_px = BRUSH_RADIUS_PRESETS[bi]
            except (TypeError, ValueError):
                pass
        if "sim_running" in sd:
            sim_running = bool(sd["sim_running"])
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
                foods = loaded
        et = sd.get("edit_tool")
        if et in ("food", "terrain", "colony"):
            edit_tool = et
        if "food_speed_index" in sd:
            try:
                fsi = int(sd["food_speed_index"])
                if 0 <= fsi < FOOD_SPEED_COUNT:
                    food_speed_index = fsi
            except (TypeError, ValueError):
                pass
    if simulation_colonies:
        edit_colony_index = min(max(0, edit_colony_index), len(simulation_colonies) - 1)
    else:
        edit_colony_index = 0
    clamp_scroll()

    def layout_add_colony_modal() -> tuple[
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
    ]:
        arrow_w = BLUEPRINT_ARROW_W
        gap = BLUEPRINT_ARROW_GAP
        pad_x = 14
        header_h = 44
        footer_h = 40
        card_w = COLONY_CARD_WIDTH
        mw = pad_x + arrow_w + gap + card_w + gap + arrow_w + pad_x
        mh = header_h + CARD_HEIGHT + 14 + footer_h + 8
        mx = (WINDOW_WIDTH - mw) // 2
        my = (WINDOW_HEIGHT - mh) // 2
        mrect = pygame.Rect(mx, my, mw, mh)
        close_r = pygame.Rect(mx + mw - 34, my + 8, 26, 22)
        cy_card = my + header_h
        btn_h = 44
        prev_r = pygame.Rect(mx + pad_x, cy_card + (CARD_HEIGHT - btn_h) // 2, arrow_w, btn_h)
        card_r = pygame.Rect(prev_r.right + gap, cy_card, card_w, CARD_HEIGHT)
        next_r = pygame.Rect(card_r.right + gap, prev_r.y, arrow_w, btn_h)
        pad = 10
        inner_right = card_r.right - pad
        inner_y = card_r.y + pad
        imp_r = pygame.Rect(inner_right - 80, inner_y + 14, 72, 26)
        new_bp_r = pygame.Rect(mx + pad_x, my + mh - footer_h - 4, mw - 2 * pad_x, 30)
        return mrect, close_r, new_bp_r, prev_r, next_r, card_r, imp_r

    def layout_new_blueprint_modal() -> tuple[
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
    ]:
        mw, mh = 420, 340
        mx = (WINDOW_WIDTH - mw) // 2
        my = (WINDOW_HEIGHT - mh) // 2
        rect = pygame.Rect(mx, my, mw, mh)
        inner_x = mx + 12
        name_r = pygame.Rect(inner_x, my + 44, mw - 24, 26)
        tw = (mw - 32) // 3
        y2 = my + 96
        sold_r = pygame.Rect(inner_x, y2, tw, 26)
        fetch_r = pygame.Rect(sold_r.right + 8, y2, tw, 26)
        resp_r = pygame.Rect(fetch_r.right + 8, y2, tw, 26)
        y3 = my + 140
        rsp = pygame.Rect(inner_x, y3, 28, 24)
        rsn = pygame.Rect(mx + mw - 40, y3, 28, 24)
        y4 = my + 178
        rfp = pygame.Rect(inner_x, y4, 28, 24)
        rfn = pygame.Rect(mx + mw - 40, y4, 28, 24)
        save_r = pygame.Rect(inner_x, my + mh - 44, (mw - 28) // 2 - 4, 32)
        can_r = pygame.Rect(save_r.right + 8, save_r.top, save_r.width, 32)
        return rect, name_r, sold_r, fetch_r, resp_r, rsp, rsn, rfp, rfn, save_r, can_r

    def colony_card_screen_rect(i: int) -> pygame.Rect:
        card_top = scroll_rect.y + i * (CARD_HEIGHT + CARD_GAP) - colony_scroll
        card_w = min(COLONY_CARD_WIDTH, scroll_rect.width - 14)
        card_x = scroll_rect.x + (scroll_rect.width - card_w) // 2
        return pygame.Rect(card_x, card_top, card_w, CARD_HEIGHT)

    def colony_dd_option_rects(head: pygame.Rect, n: int) -> list[pygame.Rect]:
        return [
            pygame.Rect(head.x, head.bottom + j * COLONY_DD_ROW_H, head.w, COLONY_DD_ROW_H)
            for j in range(n)
        ]

    def sim_card_layout(card_rect: pygame.Rect) -> dict[str, object]:
        pad = 10
        inner = pygame.Rect(card_rect.x + pad, card_rect.y + pad, card_rect.w - 2 * pad, card_rect.h - 2 * pad)
        y = inner.y
        name_r = pygame.Rect(inner.x, y + 16, inner.w - 40, 22)
        rem_r = pygame.Rect(inner.right - 34, y + 12, 30, 30)
        y += 16 + 22 + 12
        lab_counts_y = y
        third = (inner.w - 16) // 3
        f_s = pygame.Rect(inner.x, y + 14, third, 22)
        f_f = pygame.Rect(f_s.right + 8, y + 14, third, 22)
        f_r = pygame.Rect(f_f.right + 8, y + 14, third, 22)
        y += 14 + 22 + 12
        sol_dd = pygame.Rect(inner.x, y + 14, inner.w, 26)
        y += 14 + 26 + 10
        fet_dd = pygame.Rect(inner.x, y + 14, inner.w, 26)
        y += 14 + 26 + 10
        col_dd = pygame.Rect(inner.x, y + 14, inner.w, 26)
        return {
            "inner": inner,
            "lab_name_y": inner.y,
            "lab_counts_y": lab_counts_y,
            "name": name_r,
            "remove": rem_r,
            "soldiers": f_s,
            "fetchers": f_f,
            "respawn": f_r,
            "sol_dd": sol_dd,
            "fet_dd": fet_dd,
            "col_dd": col_dd,
        }

    def is_tunnel_at_map_pixel(lx: float, ly: float) -> bool:
        if not (0.0 <= lx < map_rw and 0.0 <= ly < map_rh):
            return False
        ix = int(min(map_rw - 1, max(0, lx)))
        iy = int(min(map_rh - 1, max(0, ly)))
        try:
            c = terrain_surf.get_at((ix, iy))
            rgb = (int(c[0]), int(c[1]), int(c[2]))
        except (ValueError, pygame.error, IndexError, TypeError):
            return False
        if rgb == TERRAIN_TUNNEL:
            return True
        tw = sum((rgb[i] - TERRAIN_TUNNEL[i]) ** 2 for i in range(3))
        ww = sum((rgb[i] - TERRAIN_WALL[i]) ** 2 for i in range(3))
        return tw < ww

    def is_colony_ground_at_map_pixel(lx: float, ly: float) -> bool:
        """Walkable ground = carved tunnels (same as food), inside the editable map band."""
        return _in_editable(lx, ly) and is_tunnel_at_map_pixel(lx, ly)

    def is_tunnel_at_world(wx: float, wy: float) -> bool:
        lx = wx / WORLD_WIDTH * map_rw
        ly = wy / WORLD_HEIGHT * map_rh
        return is_tunnel_at_map_pixel(lx, ly)

    def map_pixel_to_world(lx: float, ly: float) -> tuple[float, float]:
        return (lx / map_rw * WORLD_WIDTH, ly / map_rh * WORLD_HEIGHT)

    def food_spawn_burst(lx_center: float, ly_center: float, elapsed_ms: int) -> None:
        nonlocal foods
        R = min(food_r_max_px, FOOD_GROW_PER_MS * max(0, elapsed_ms))
        R = max(2.0, R)
        k = food_speed_index + 1
        for hi in range(k):
            if hi == 0 and is_tunnel_at_map_pixel(lx_center, ly_center):
                foods.append(map_pixel_to_world(lx_center, ly_center))
                continue
            for _attempt in range(32):
                u = random.random() * 2 * math.pi
                v = random.random()
                rr = math.sqrt(v) * R
                clx = lx_center + math.cos(u) * rr
                cly = ly_center + math.sin(u) * rr
                if not (0.0 <= clx < map_rw and 0.0 <= cly < map_rh):
                    continue
                if is_tunnel_at_map_pixel(clx, cly):
                    foods.append(map_pixel_to_world(clx, cly))
                    break

    def cull_food_not_on_tunnel() -> None:
        nonlocal foods
        foods[:] = [f for f in foods if is_tunnel_at_world(f[0], f[1])]

    def erase_foods_by_proximity(lx_map: float, ly_map: float) -> None:
        nonlocal foods
        k = food_speed_index + 1
        r_lim = FOOD_ERASE_SEARCH_RADIUS_PX
        scored: list[tuple[float, int]] = []
        for i, f in enumerate(foods):
            flx = f[0] / WORLD_WIDTH * map_rw
            fly = f[1] / WORLD_HEIGHT * map_rh
            d = math.hypot(flx - lx_map, fly - ly_map)
            if d <= r_lim:
                scored.append((d, i))
        scored.sort(key=lambda t: t[0])
        drop = {scored[j][1] for j in range(min(k, len(scored)))}
        if not drop:
            return
        foods[:] = [f for i, f in enumerate(foods) if i not in drop]

    def stamp_brush(lx: float, ly: float, radius: int, color: tuple[int, int, int]) -> None:
        if radius < 1 or not _in_editable(lx, ly):
            return
        old = terrain_surf.get_clip()
        terrain_surf.set_clip(editable_inner)
        pygame.draw.circle(terrain_surf, color, (int(lx), int(ly)), int(radius))
        terrain_surf.set_clip(old)
        if color == TERRAIN_WALL:
            cull_food_not_on_tunnel()

    def paint_brush_line(
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
            stamp_brush(x1, y1, radius, color)
            return
        step = max(1.0, radius * step_frac)
        n = max(1, int(math.ceil(dist / step)))
        for i in range(n + 1):
            t = i / n
            stamp_brush(x0 + dx * t, y0 + dy * t, radius, color)

    def save_terrain() -> None:
        tmp = _terrain_tmp_path(TERRAIN_SAVE_FILE)
        try:
            _terrain_save_bin(TERRAIN_SAVE_FILE, terrain_surf, pygame)
        except (pygame.error, OSError, TypeError, ValueError):
            try:
                if tmp.is_file():
                    tmp.unlink()
            except OSError:
                pass
        _session_write(
            blueprints,
            simulation_colonies,
            next_custom_id,
            colony_scroll,
            brush_radius_index,
            sim_running,
            foods,
            edit_tool,
            food_speed_index,
            edit_colony_index,
        )

    def edit_layout() -> tuple[
        pygame.Rect,
        pygame.Rect,
        pygame.Rect,
        list[pygame.Rect],
        pygame.Rect,
        pygame.Rect,
        list[pygame.Rect],
        pygame.Rect,
        pygame.Rect,
        list[pygame.Rect],
    ]:
        done_r = pygame.Rect(PANEL_MARGIN, edit_done_y, PANEL_WIDTH - 2 * PANEL_MARGIN, btn_h)
        half_w = (PANEL_WIDTH - 3 * PANEL_MARGIN) // 2
        inner_w = PANEL_WIDTH - 2 * PANEL_MARGIN
        y = edit_brush_y
        terrain_tool_r = pygame.Rect(PANEL_MARGIN, y, half_w, btn_h)
        terrain_drop_r = pygame.Rect(terrain_tool_r.right + PANEL_MARGIN, y, half_w, btn_h)
        y += btn_h + 4
        terrain_opt_rects: list[pygame.Rect] = []
        if brush_dropdown_open:
            n = len(BRUSH_RADIUS_PRESETS)
            cell_w = max(1, (inner_w - BRUSH_PRESET_GAP * (n - 1)) // n)
            for i in range(n):
                x = PANEL_MARGIN + i * (cell_w + BRUSH_PRESET_GAP)
                terrain_opt_rects.append(pygame.Rect(x, y, cell_w, BRUSH_PRESET_ROW_H - 2))
            y += BRUSH_PRESET_ROW_H + 4
        y += 6
        food_tool_r = pygame.Rect(PANEL_MARGIN, y, half_w, btn_h)
        food_drop_r = pygame.Rect(food_tool_r.right + PANEL_MARGIN, y, half_w, btn_h)
        y += btn_h + 4
        food_opt_rects: list[pygame.Rect] = []
        if food_speed_dropdown_open:
            n_sp = FOOD_SPEED_COUNT
            cell_w_f = max(1, (inner_w - BRUSH_PRESET_GAP * (n_sp - 1)) // n_sp)
            for i in range(n_sp):
                x = PANEL_MARGIN + i * (cell_w_f + BRUSH_PRESET_GAP)
                food_opt_rects.append(pygame.Rect(x, y, cell_w_f, BRUSH_PRESET_ROW_H - 2))
            y += BRUSH_PRESET_ROW_H + 4
        y += 8
        colony_tool_r = pygame.Rect(PANEL_MARGIN, y, half_w, btn_h)
        colony_unplace_r = pygame.Rect(colony_tool_r.right + PANEL_MARGIN, y, half_w, btn_h)
        y += btn_h + 6
        colony_sel_rects: list[pygame.Rect] = []
        if edit_tool == "colony":
            for i in range(len(simulation_colonies)):
                colony_sel_rects.append(pygame.Rect(PANEL_MARGIN, y + i * 30, inner_w, 28))
        return (
            done_r,
            terrain_tool_r,
            terrain_drop_r,
            terrain_opt_rects,
            food_tool_r,
            food_drop_r,
            food_opt_rects,
            colony_tool_r,
            colony_unplace_r,
            colony_sel_rects,
        )

    def preset_circle_radius(preset_r: int, cell_w: int, cell_h: int) -> int:
        cap = min(cell_w, cell_h) // 2 - 3
        cap = max(3, cap)
        return max(2, min(cap, int(round(preset_r * cap / BRUSH_PRESET_MAX))))

    map_screen_rect = pygame.Rect(map_rx, map_ry, map_rw, map_rh)
    nest_pick_r = max(
        22.0,
        (colony_base_sprite.get_width() * 0.5) if colony_base_sprite is not None else 28.0,
    )

    running = True
    mouse_xy = (0, 0)
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_terrain()
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if new_bp_modal_open:
                    new_bp_modal_open = False
                    focused_bp_field = None
                elif add_modal_open:
                    add_modal_open = False
                elif colony_dd is not None:
                    colony_dd = None
                else:
                    save_terrain()
                    running = False
            elif event.type == pygame.MOUSEMOTION:
                mouse_xy = event.pos
                ex, ey = event.pos
                pressed = pygame.mouse.get_pressed(3)
                if (
                    edit_map
                    and edit_tool == "terrain"
                    and ex < panel_x
                    and map_screen_rect.collidepoint(ex, ey)
                ):
                    lx_f = ex - map_rx
                    ly_f = ey - map_ry
                    if _in_editable(lx_f, ly_f):
                        if pressed[0] and last_stroke_left is not None:
                            ox, oy = last_stroke_left
                            paint_brush_line(
                                ox,
                                oy,
                                lx_f,
                                ly_f,
                                brush_radius_px,
                                TERRAIN_TUNNEL,
                                step_frac=0.5,
                            )
                            last_stroke_left = (lx_f, ly_f)
                        if pressed[2] and last_stroke_right is not None:
                            ox, oy = last_stroke_right
                            paint_brush_line(
                                ox,
                                oy,
                                lx_f,
                                ly_f,
                                brush_radius_px,
                                TERRAIN_WALL,
                                step_frac=0.5,
                            )
                            last_stroke_right = (lx_f, ly_f)
            elif event.type == pygame.MOUSEBUTTONUP:
                if event.button == 1:
                    last_stroke_left = None
                    food_lmb_active = False
                elif event.button == 3:
                    last_stroke_right = None
                    food_rmb_active = False
            elif event.type == pygame.MOUSEWHEEL:
                whx, why = pygame.mouse.get_pos()
                if add_modal_open and not new_bp_modal_open and blueprints:
                    mrect, *_ = layout_add_colony_modal()
                    if mrect.collidepoint(whx, why):
                        nbp = len(blueprints)
                        bi = min(add_modal_bp_index, nbp - 1)
                        add_modal_bp_index = min(max(0, bi - event.y), nbp - 1)
                elif (
                    not edit_map
                    and not add_modal_open
                    and not new_bp_modal_open
                    and colony_dd is None
                    and scroll_rect.collidepoint(whx, why)
                ):
                    colony_scroll -= event.y * 28
                    clamp_scroll()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                px, py = event.pos
                plx, ply = px - panel_x, py

                if new_bp_modal_open and event.button == 1:
                    focused_field = None
                    (
                        _nbr,
                        name_r,
                        sold_r,
                        fetch_r,
                        resp_r,
                        rsp,
                        rsn,
                        rfp,
                        rfn,
                        save_r,
                        can_r,
                    ) = layout_new_blueprint_modal()
                    if can_r.collidepoint(px, py) or not _nbr.collidepoint(px, py):
                        new_bp_modal_open = False
                        add_modal_open = True
                        focused_bp_field = None
                    elif save_r.collidepoint(px, py):
                        nm = new_bp_name.strip() or "Blueprint"
                        blueprints.append(
                            ColonyBlueprint(
                                name=nm,
                                soldiers_str=new_bp_soldiers_str,
                                fetchers_str=new_bp_fetchers_str,
                                respawn_str=new_bp_respawn_str,
                                reward_soldier=new_bp_reward_soldier,
                                reward_fetcher=new_bp_reward_fetcher,
                            )
                        )
                        new_bp_modal_open = False
                        add_modal_open = True
                        add_modal_bp_index = len(blueprints) - 1
                        focused_bp_field = None
                    elif name_r.collidepoint(px, py):
                        focused_bp_field = "name"
                    elif sold_r.collidepoint(px, py):
                        focused_bp_field = "soldiers"
                    elif fetch_r.collidepoint(px, py):
                        focused_bp_field = "fetchers"
                    elif resp_r.collidepoint(px, py):
                        focused_bp_field = "respawn"
                    elif rsp.collidepoint(px, py):
                        new_bp_reward_soldier = cycle_reward(new_bp_reward_soldier, -1)
                    elif rsn.collidepoint(px, py):
                        new_bp_reward_soldier = cycle_reward(new_bp_reward_soldier, 1)
                    elif rfp.collidepoint(px, py):
                        new_bp_reward_fetcher = cycle_reward(new_bp_reward_fetcher, -1)
                    elif rfn.collidepoint(px, py):
                        new_bp_reward_fetcher = cycle_reward(new_bp_reward_fetcher, 1)
                    continue

                if add_modal_open and event.button == 1:
                    focused_field = None
                    (
                        mrect,
                        close_r,
                        new_bp_r,
                        prev_br,
                        next_br,
                        _bp_card_r,
                        imp_r,
                    ) = layout_add_colony_modal()
                    nbp = len(blueprints)
                    bi = min(add_modal_bp_index, max(0, nbp - 1))
                    if not mrect.collidepoint(px, py):
                        add_modal_open = False
                    elif close_r.collidepoint(px, py):
                        add_modal_open = False
                    elif new_bp_r.collidepoint(px, py):
                        add_modal_open = False
                        new_bp_modal_open = True
                        focused_bp_field = None
                    elif nbp > 0 and prev_br.collidepoint(px, py) and bi > 0:
                        add_modal_bp_index = bi - 1
                    elif nbp > 0 and next_br.collidepoint(px, py) and bi < nbp - 1:
                        add_modal_bp_index = bi + 1
                    elif nbp > 0 and imp_r.collidepoint(px, py):
                        if len(simulation_colonies) < MAX_SIM_COLONIES:
                            simulation_colonies.append(sim_colony_from_blueprint(blueprints[bi]))
                            next_custom_id += 1
                            clamp_scroll()
                            add_modal_open = False
                    continue

                dd_option_picked = False
                if colony_dd is not None and event.button == 1 and not edit_map:
                    ci, dk = colony_dd
                    if 0 <= ci < len(simulation_colonies):
                        cr = colony_card_screen_rect(ci)
                        L = sim_card_layout(cr)
                        head = (
                            L["sol_dd"]
                            if dk == "soldier"
                            else L["fet_dd"]
                            if dk == "fetcher"
                            else L["col_dd"]
                        )
                        if isinstance(head, pygame.Rect):
                            n = len(REWARD_SYSTEMS) if dk != "color" else len(COLONY_COLOR_ORDER)
                            opts = colony_dd_option_rects(head, n)
                            for oi, orr in enumerate(opts):
                                if orr.collidepoint(px, py):
                                    c = simulation_colonies[ci]
                                    if dk == "soldier":
                                        c.reward_soldier = REWARD_SYSTEMS[oi]
                                    elif dk == "fetcher":
                                        c.reward_fetcher = REWARD_SYSTEMS[oi]
                                    else:
                                        apply_colony_color(ci, COLONY_COLOR_ORDER[oi])
                                    colony_dd = None
                                    dd_option_picked = True
                                    break
                            if not dd_option_picked:
                                ur = head.copy()
                                for orr in opts:
                                    ur = ur.union(orr)
                                if not ur.collidepoint(px, py):
                                    colony_dd = None
                if dd_option_picked:
                    continue

                if px < panel_x:
                    focused_field = None
                    if edit_map and map_screen_rect.collidepoint(px, py):
                        brush_dropdown_open = False
                        food_speed_dropdown_open = False
                        lx_f = px - map_rx
                        ly_f = py - map_ry
                        if edit_tool == "colony" and event.button == 1:
                            if simulation_colonies:
                                best_i = -1
                                best_d = 1e9
                                for i, sc in enumerate(simulation_colonies):
                                    if sc.nest_x is None or sc.nest_y is None:
                                        continue
                                    flx = sc.nest_x / WORLD_WIDTH * map_rw
                                    fly = sc.nest_y / WORLD_HEIGHT * map_rh
                                    sx = map_rx + flx
                                    sy = map_ry + fly
                                    d = math.hypot(px - sx, py - sy)
                                    if d < nest_pick_r and d < best_d:
                                        best_d = d
                                        best_i = i
                                if best_i >= 0:
                                    edit_colony_index = best_i
                                elif is_colony_ground_at_map_pixel(lx_f, ly_f):
                                    eci = min(edit_colony_index, len(simulation_colonies) - 1)
                                    sc = simulation_colonies[eci]
                                    wx, wy = map_pixel_to_world(lx_f, ly_f)
                                    sc.nest_x, sc.nest_y = wx, wy
                            continue
                        if _in_editable(lx_f, ly_f):
                            if edit_tool == "terrain" and event.button in (1, 3):
                                if event.button == 1:
                                    stamp_brush(lx_f, ly_f, brush_radius_px, TERRAIN_TUNNEL)
                                    last_stroke_left = (lx_f, ly_f)
                                else:
                                    stamp_brush(lx_f, ly_f, brush_radius_px, TERRAIN_WALL)
                                    last_stroke_right = (lx_f, ly_f)
                            elif edit_tool == "food" and event.button == 1:
                                food_lmb_active = True
                                food_press_ms = pygame.time.get_ticks()
                                food_spawn_burst(lx_f, ly_f, 0)
                                last_food_spawn_ms = food_press_ms
                            elif edit_tool == "food" and event.button == 3:
                                food_rmb_active = True
                                erase_foods_by_proximity(lx_f, ly_f)
                                last_food_erase_ms = pygame.time.get_ticks()
                    continue

                focused_field = None
                if edit_map:
                    (
                        done_r,
                        terrain_tool_r,
                        terrain_drop_r,
                        terrain_opt_rects,
                        food_tool_r,
                        food_drop_r,
                        food_opt_rects,
                        colony_tool_r,
                        colony_unplace_r,
                        colony_sel_rects,
                    ) = edit_layout()
                    if event.button == 1:
                        if done_r.collidepoint(plx, ply):
                            edit_map = False
                            brush_dropdown_open = False
                            food_speed_dropdown_open = False
                            save_terrain()
                        elif terrain_tool_r.collidepoint(plx, ply):
                            edit_tool = "terrain"
                            food_lmb_active = False
                            food_rmb_active = False
                        elif food_tool_r.collidepoint(plx, ply):
                            edit_tool = "food"
                            food_lmb_active = False
                            food_rmb_active = False
                        elif colony_tool_r.collidepoint(plx, ply):
                            edit_tool = "colony"
                            food_lmb_active = False
                            food_rmb_active = False
                        elif colony_unplace_r.collidepoint(plx, ply):
                            if simulation_colonies:
                                eci = min(edit_colony_index, len(simulation_colonies) - 1)
                                simulation_colonies[eci].nest_x = None
                                simulation_colonies[eci].nest_y = None
                        elif edit_tool == "colony":
                            for si, srr in enumerate(colony_sel_rects):
                                if srr.collidepoint(plx, ply):
                                    edit_colony_index = si
                                    break
                        elif terrain_drop_r.collidepoint(plx, ply):
                            brush_dropdown_open = not brush_dropdown_open
                            food_speed_dropdown_open = False
                        elif food_drop_r.collidepoint(plx, ply):
                            food_speed_dropdown_open = not food_speed_dropdown_open
                            brush_dropdown_open = False
                        elif brush_dropdown_open:
                            picked = False
                            for i, orr in enumerate(terrain_opt_rects):
                                if orr.collidepoint(plx, ply):
                                    brush_radius_index = i
                                    brush_radius_px = BRUSH_RADIUS_PRESETS[i]
                                    brush_dropdown_open = False
                                    picked = True
                                    break
                            if not picked:
                                brush_dropdown_open = False
                        elif food_speed_dropdown_open:
                            picked_f = False
                            for i, orr in enumerate(food_opt_rects):
                                if orr.collidepoint(plx, ply):
                                    food_speed_index = i
                                    food_speed_dropdown_open = False
                                    picked_f = True
                                    break
                            if not picked_f:
                                food_speed_dropdown_open = False
                    continue

                if event.button != 1:
                    continue

                row1 = pygame.Rect(
                    PANEL_MARGIN,
                    row1_y,
                    (PANEL_WIDTH - 3 * PANEL_MARGIN) // 2,
                    btn_h,
                )
                row1b = pygame.Rect(row1.right + PANEL_MARGIN, row1_y, row1.width, btn_h)
                edit_r = pygame.Rect(PANEL_MARGIN, row2_y, PANEL_WIDTH - 2 * PANEL_MARGIN, btn_h)
                abs_row1 = row1.move(panel_x, 0)
                abs_row1b = row1b.move(panel_x, 0)
                abs_edit = edit_r.move(panel_x, 0)

                if abs_row1.collidepoint(px, py):
                    sim_running = True
                elif abs_row1b.collidepoint(px, py):
                    sim_running = False
                elif abs_edit.collidepoint(px, py):
                    edit_map = True
                    colony_dd = None
                else:
                    add_rect = pygame.Rect(
                        panel_x + PANEL_MARGIN,
                        add_y,
                        PANEL_WIDTH - 2 * PANEL_MARGIN,
                        add_btn_h,
                    )
                    if add_rect.collidepoint(px, py):
                        add_modal_open = True
                        add_modal_bp_index = 0
                        colony_dd = None
                    elif scroll_rect.collidepoint(px, py):
                        rel_y = py - scroll_rect.y + colony_scroll
                        idx = int(rel_y // (CARD_HEIGHT + CARD_GAP))
                        if 0 <= idx < len(simulation_colonies):
                            c = simulation_colonies[idx]
                            card_top = scroll_rect.y + idx * (CARD_HEIGHT + CARD_GAP) - colony_scroll
                            card_rect = colony_card_screen_rect(idx)
                            if card_rect.collidepoint(px, py):
                                L = sim_card_layout(card_rect)
                                rem_r = L["remove"]
                                if isinstance(rem_r, pygame.Rect) and rem_r.collidepoint(px, py):
                                    del simulation_colonies[idx]
                                    colony_dd = None
                                    if edit_colony_index >= len(simulation_colonies):
                                        edit_colony_index = max(0, len(simulation_colonies) - 1)
                                    clamp_scroll()
                                else:
                                    name_r = L["name"]
                                    f_s = L["soldiers"]
                                    f_f = L["fetchers"]
                                    f_r = L["respawn"]
                                    sol_dd = L["sol_dd"]
                                    fet_dd = L["fet_dd"]
                                    col_dd = L["col_dd"]
                                    if isinstance(name_r, pygame.Rect) and name_r.collidepoint(px, py):
                                        focused_field = (idx, "name")
                                        colony_dd = None
                                    elif isinstance(f_s, pygame.Rect) and f_s.collidepoint(px, py):
                                        focused_field = (idx, "soldiers")
                                        colony_dd = None
                                    elif isinstance(f_f, pygame.Rect) and f_f.collidepoint(px, py):
                                        focused_field = (idx, "fetchers")
                                        colony_dd = None
                                    elif isinstance(f_r, pygame.Rect) and f_r.collidepoint(px, py):
                                        focused_field = (idx, "respawn")
                                        colony_dd = None
                                    elif isinstance(sol_dd, pygame.Rect) and sol_dd.collidepoint(px, py):
                                        focused_field = None
                                        if colony_dd == (idx, "soldier"):
                                            colony_dd = None
                                        else:
                                            colony_dd = (idx, "soldier")
                                    elif isinstance(fet_dd, pygame.Rect) and fet_dd.collidepoint(px, py):
                                        focused_field = None
                                        if colony_dd == (idx, "fetcher"):
                                            colony_dd = None
                                        else:
                                            colony_dd = (idx, "fetcher")
                                    elif isinstance(col_dd, pygame.Rect) and col_dd.collidepoint(px, py):
                                        focused_field = None
                                        if colony_dd == (idx, "color"):
                                            colony_dd = None
                                        else:
                                            colony_dd = (idx, "color")

            elif event.type == pygame.KEYDOWN:
                if new_bp_modal_open and focused_bp_field is not None:
                    key = event.key
                    fbf = focused_bp_field
                    if fbf == "name":
                        buf = new_bp_name
                    elif fbf == "soldiers":
                        buf = new_bp_soldiers_str
                    elif fbf == "fetchers":
                        buf = new_bp_fetchers_str
                    else:
                        buf = new_bp_respawn_str
                    if key == pygame.K_BACKSPACE:
                        buf = buf[:-1]
                    elif key == pygame.K_RETURN or key == pygame.K_TAB:
                        focused_bp_field = None
                    elif fbf == "name":
                        if event.unicode and len(buf) < 56 and event.unicode.isprintable():
                            buf += event.unicode
                    elif fbf in ("soldiers", "fetchers"):
                        if event.unicode.isdigit():
                            buf += event.unicode
                    else:
                        if event.unicode.isdigit() or (event.unicode == "." and "." not in buf):
                            buf += event.unicode
                    if fbf == "name":
                        new_bp_name = buf
                    elif fbf == "soldiers":
                        new_bp_soldiers_str = buf
                    elif fbf == "fetchers":
                        new_bp_fetchers_str = buf
                    else:
                        new_bp_respawn_str = buf
                elif focused_field is not None:
                    ci, which = focused_field
                    c = simulation_colonies[ci]
                    key = event.key
                    if which == "name":
                        buf = c.name
                    else:
                        buf = {
                            "soldiers": c.soldiers_str,
                            "fetchers": c.fetchers_str,
                            "respawn": c.respawn_str,
                        }[which]
                    if key == pygame.K_BACKSPACE:
                        buf = buf[:-1]
                    elif key == pygame.K_RETURN or key == pygame.K_TAB:
                        focused_field = None
                    elif which == "name":
                        if event.unicode and len(buf) < 56 and event.unicode.isprintable():
                            buf += event.unicode
                    elif which in ("soldiers", "fetchers"):
                        if event.unicode.isdigit():
                            buf += event.unicode
                    else:
                        if event.unicode.isdigit() or (event.unicode == "." and "." not in buf):
                            buf += event.unicode
                    if which == "name":
                        c.name = buf
                    elif which == "soldiers":
                        c.soldiers_str = buf
                    elif which == "fetchers":
                        c.fetchers_str = buf
                    else:
                        c.respawn_str = buf

        mx, my = pygame.mouse.get_pos()
        mouse_xy = (mx, my)

        if edit_map and edit_tool == "food" and mx < panel_x and map_screen_rect.collidepoint(mx, my):
            lx_loop = mx - map_rx
            ly_loop = my - map_ry
            if _in_editable(lx_loop, ly_loop):
                pressed_loop = pygame.mouse.get_pressed(3)
                now_loop = pygame.time.get_ticks()
                if pressed_loop[0] and food_lmb_active:
                    if now_loop - last_food_spawn_ms >= FOOD_SPAWN_INTERVAL_MS:
                        last_food_spawn_ms = now_loop
                        elapsed = max(0, now_loop - food_press_ms)
                        food_spawn_burst(lx_loop, ly_loop, elapsed)
                if pressed_loop[2] and food_rmb_active:
                    if now_loop - last_food_erase_ms >= FOOD_SPAWN_INTERVAL_MS:
                        last_food_erase_ms = now_loop
                        erase_foods_by_proximity(lx_loop, ly_loop)

        screen.fill((20, 24, 32))
        rx, ry, rw, rh = map_rx, map_ry, map_rw, map_rh
        screen.blit(terrain_surf, (rx, ry))
        pygame.draw.rect(screen, border_color, (rx, ry, rw, rh), width=2)

        if not sim_running and not edit_map:
            overlay = pygame.Surface((rw, rh), pygame.SRCALPHA)
            overlay.fill((10, 12, 18, 120))
            screen.blit(overlay, (rx, ry))
            paused_txt = font_title.render("Paused", True, text_color)
            screen.blit(paused_txt, paused_txt.get_rect(center=(rx + rw // 2, ry + rh // 2)))

        for fwx, fwy in foods:
            flx = fwx / WORLD_WIDTH * map_rw
            fly = fwy / WORLD_HEIGHT * map_rh
            fsx = int(map_rx + flx)
            fsy = int(map_ry + fly)
            if food_sprite is not None:
                fr = food_sprite.get_rect(center=(fsx, fsy))
                screen.blit(food_sprite, fr)
            else:
                pygame.draw.circle(screen, (72, 180, 96), (fsx, fsy), 2)

        for sc in simulation_colonies:
            if sc.nest_x is None or sc.nest_y is None:
                continue
            flx = sc.nest_x / WORLD_WIDTH * map_rw
            fly = sc.nest_y / WORLD_HEIGHT * map_rh
            nsx = int(map_rx + flx)
            nsy = int(map_ry + fly)
            ns = colony_sprite_for_color(sc.color_id)
            if ns is not None:
                nr = ns.get_rect(center=(nsx, nsy))
                screen.blit(ns, nr)
            else:
                pygame.draw.circle(
                    screen, COLONY_COLOR_RGB.get(sc.color_id, (200, 200, 200)), (nsx, nsy), 6, width=2
                )

        if edit_map and map_screen_rect.collidepoint(mx, my):
            if edit_tool == "terrain":
                pygame.draw.circle(screen, BRUSH_PREVIEW_WHITE, (mx, my), brush_radius_px, width=2)
            elif edit_tool == "food" and food_cursor_sprite is not None:
                crect = food_cursor_sprite.get_rect(center=(mx, my))
                screen.blit(food_cursor_sprite, crect)
            elif edit_tool == "colony" and simulation_colonies:
                lx_c = mx - map_rx
                ly_c = my - map_ry
                if 0.0 <= lx_c < map_rw and 0.0 <= ly_c < map_rh:
                    if is_colony_ground_at_map_pixel(lx_c, ly_c):
                        eci = min(edit_colony_index, len(simulation_colonies) - 1)
                        cc = colony_cursor_for_color(simulation_colonies[eci].color_id)
                        if cc is not None:
                            screen.blit(cc, cc.get_rect(center=(mx, my)))
                        else:
                            cid = simulation_colonies[eci].color_id
                            pygame.draw.circle(
                                screen,
                                COLONY_COLOR_RGB.get(cid, (128, 128, 128)),
                                (mx, my),
                                6,
                                width=2,
                            )
                    else:
                        draw_colony_invalid_cross(screen, mx, my)
            if (
                edit_tool == "food"
                and food_lmb_active
                and pygame.mouse.get_pressed(3)[0]
                and mx < panel_x
                and _in_editable(mx - map_rx, my - map_ry)
            ):
                now_pv = pygame.time.get_ticks()
                elapsed_pv = max(0, now_pv - food_press_ms)
                Rpv = min(food_r_max_px, FOOD_GROW_PER_MS * elapsed_pv)
                Rpv = max(2.0, Rpv)
                pygame.draw.circle(screen, BRUSH_PREVIEW_FAINT, (mx, my), int(Rpv), width=1)
            if (
                edit_tool == "food"
                and food_rmb_active
                and pygame.mouse.get_pressed(3)[2]
                and mx < panel_x
                and _in_editable(mx - map_rx, my - map_ry)
            ):
                pygame.draw.circle(
                    screen,
                    BRUSH_PREVIEW_FAINT,
                    (mx, my),
                    FOOD_ERASE_SEARCH_RADIUS_PX,
                    width=1,
                )

        pygame.draw.line(screen, panel_border, (panel_x, 0), (panel_x, WINDOW_HEIGHT), width=1)
        panel_surf = screen.subsurface(pygame.Rect(panel_x, 0, PANEL_WIDTH, WINDOW_HEIGHT))
        panel_surf.fill(panel_bg)
        plx, ply = mx - panel_x, my

        if edit_map:
            title = font_title.render("Edit map", True, text_color)
            panel_surf.blit(title, (PANEL_MARGIN, 12))
            (
                done_r,
                terrain_tool_r,
                terrain_drop_r,
                terrain_opt_rects,
                food_tool_r,
                food_drop_r,
                food_opt_rects,
                colony_tool_r,
                colony_unplace_r,
                colony_sel_rects,
            ) = edit_layout()
            draw_button(panel_surf, done_r, "Done", done_r.collidepoint(plx, ply), False)
            draw_button(
                panel_surf,
                terrain_tool_r,
                "Brush",
                terrain_tool_r.collidepoint(plx, ply),
                edit_tool == "terrain",
            )
            pygame.draw.rect(panel_surf, field_bg, terrain_drop_r, border_radius=6)
            pygame.draw.rect(
                panel_surf,
                panel_border,
                terrain_drop_r,
                width=2 if brush_dropdown_open else 1,
                border_radius=6,
            )
            t_head_dr = preset_circle_radius(brush_radius_px, terrain_drop_r.w - 28, terrain_drop_r.h)
            t_head_cx = terrain_drop_r.left + 12 + t_head_dr
            t_head_cy = terrain_drop_r.centery
            pygame.draw.circle(panel_surf, text_color, (t_head_cx, t_head_cy), t_head_dr)
            tcx = terrain_drop_r.right - 14
            tcy = terrain_drop_r.centery
            ts = 5
            if brush_dropdown_open:
                ttri = [(tcx - ts, tcy + ts // 2), (tcx + ts, tcy + ts // 2), (tcx, tcy - ts // 2)]
            else:
                ttri = [(tcx - ts, tcy - ts // 2), (tcx + ts, tcy - ts // 2), (tcx, tcy + ts // 2)]
            pygame.draw.polygon(panel_surf, muted, ttri)
            if brush_dropdown_open:
                for i, orr in enumerate(terrain_opt_rects):
                    pr = BRUSH_RADIUS_PRESETS[i]
                    pygame.draw.rect(panel_surf, card_bg, orr, border_radius=4)
                    bcol = btn_active if i == brush_radius_index else card_border
                    pygame.draw.rect(panel_surf, bcol, orr, width=2 if i == brush_radius_index else 1, border_radius=4)
                    show_r = preset_circle_radius(pr, orr.w, orr.h)
                    pygame.draw.circle(panel_surf, text_color, orr.center, show_r)

            draw_button(
                panel_surf,
                food_tool_r,
                "Food",
                food_tool_r.collidepoint(plx, ply),
                edit_tool == "food",
            )
            pygame.draw.rect(panel_surf, field_bg, food_drop_r, border_radius=6)
            pygame.draw.rect(
                panel_surf,
                panel_border,
                food_drop_r,
                width=2 if food_speed_dropdown_open else 1,
                border_radius=6,
            )
            spd_txt = font_title.render(str(food_speed_index + 1), True, text_color)
            panel_surf.blit(spd_txt, spd_txt.get_rect(center=(food_drop_r.left + 24, food_drop_r.centery)))
            fcx = food_drop_r.right - 14
            fcy = food_drop_r.centery
            fs = 5
            if food_speed_dropdown_open:
                ftri = [(fcx - fs, fcy + fs // 2), (fcx + fs, fcy + fs // 2), (fcx, fcy - fs // 2)]
            else:
                ftri = [(fcx - fs, fcy - fs // 2), (fcx + fs, fcy - fs // 2), (fcx, fcy + fs // 2)]
            pygame.draw.polygon(panel_surf, muted, ftri)
            if food_speed_dropdown_open:
                for i, orr in enumerate(food_opt_rects):
                    pygame.draw.rect(panel_surf, card_bg, orr, border_radius=4)
                    bcf = btn_active if i == food_speed_index else card_border
                    pygame.draw.rect(panel_surf, bcf, orr, width=2 if i == food_speed_index else 1, border_radius=4)
                    dig = font.render(str(i + 1), True, text_color)
                    panel_surf.blit(dig, dig.get_rect(center=orr.center))
            draw_button(
                panel_surf,
                colony_tool_r,
                "Colony",
                colony_tool_r.collidepoint(plx, ply),
                edit_tool == "colony",
            )
            can_unplace = bool(simulation_colonies)
            draw_button(
                panel_surf,
                colony_unplace_r,
                "Clear nest",
                colony_unplace_r.collidepoint(plx, ply) and can_unplace,
                False,
            )
            if edit_tool == "colony":
                if not simulation_colonies:
                    hy = colony_tool_r.bottom + 8
                    hint = font_small.render("Add colonies in Simulation", True, muted)
                    panel_surf.blit(hint, (PANEL_MARGIN, hy))
                else:
                    for si, srr in enumerate(colony_sel_rects):
                        active = si == min(edit_colony_index, len(simulation_colonies) - 1)
                        pygame.draw.rect(panel_surf, card_bg, srr, border_radius=4)
                        bcol = btn_active if active else card_border
                        pygame.draw.rect(panel_surf, bcol, srr, width=2 if active else 1, border_radius=4)
                        sc = simulation_colonies[si]
                        dot_c = COLONY_COLOR_RGB.get(sc.color_id, (128, 128, 128))
                        pygame.draw.circle(panel_surf, dot_c, (srr.x + 14, srr.centery), 6)
                        lbl = font_small.render(sc.name[:28], True, text_color)
                        panel_surf.blit(lbl, (srr.x + 28, srr.centery - lbl.get_height() // 2))
        else:
            title = font_title.render("Simulation", True, text_color)
            panel_surf.blit(title, (PANEL_MARGIN, 12))

            row1 = pygame.Rect(
                PANEL_MARGIN,
                row1_y,
                (PANEL_WIDTH - 3 * PANEL_MARGIN) // 2,
                btn_h,
            )
            row1b = pygame.Rect(row1.right + PANEL_MARGIN, row1_y, row1.width, btn_h)
            draw_button(panel_surf, row1, "Start", row1.collidepoint(plx, ply), False)
            draw_button(panel_surf, row1b, "Pause", row1b.collidepoint(plx, ply), False)
            edit_r = pygame.Rect(PANEL_MARGIN, row2_y, PANEL_WIDTH - 2 * PANEL_MARGIN, btn_h)
            draw_button(panel_surf, edit_r, "Edit map", edit_r.collidepoint(plx, ply), False)

            cl = font.render("Colonies", True, text_color)
            panel_surf.blit(cl, (PANEL_MARGIN, col_label_y))
            add_rect = pygame.Rect(PANEL_MARGIN, add_y, PANEL_WIDTH - 2 * PANEL_MARGIN, add_btn_h)
            draw_button(panel_surf, add_rect, "+ Add colony…", add_rect.collidepoint(plx, ply), False)

        old_clip = screen.get_clip()
        screen.set_clip(scroll_rect)
        content_h = colonies_content_height()
        if not edit_map:
            for i, col in enumerate(simulation_colonies):
                card_rect = colony_card_screen_rect(i)
                if card_rect.bottom < scroll_rect.top or card_rect.top > scroll_rect.bottom:
                    continue
                sh = pygame.Rect(card_rect.x + 2, card_rect.y + 3, card_rect.w, card_rect.h)
                pygame.draw.rect(screen, (12, 14, 20), sh, border_radius=9)
                pygame.draw.rect(screen, card_bg, card_rect, border_radius=8)
                pygame.draw.rect(screen, card_border, card_rect, width=1, border_radius=8)
                L = sim_card_layout(card_rect)
                inner = L["inner"]
                name_r = L["name"]
                rem_r = L["remove"]
                f_s = L["soldiers"]
                f_f = L["fetchers"]
                f_r = L["respawn"]
                sol_dd = L["sol_dd"]
                fet_dd = L["fet_dd"]
                col_dd = L["col_dd"]
                lab_counts_y = L["lab_counts_y"]
                if isinstance(inner, pygame.Rect):
                    screen.blit(
                        font_small.render("Name", True, muted),
                        (inner.x, L["lab_name_y"]),
                    )
                if isinstance(name_r, pygame.Rect):
                    fn = focused_field == (i, "name")
                    draw_entry_only(screen, name_r, col.name, fn)
                if isinstance(rem_r, pygame.Rect):
                    draw_trash_icon_button(screen, rem_r, rem_r.collidepoint(mx, my))
                if (
                    isinstance(f_s, pygame.Rect)
                    and isinstance(f_f, pygame.Rect)
                    and isinstance(f_r, pygame.Rect)
                    and isinstance(lab_counts_y, int)
                ):
                    screen.blit(font_small.render("Soldiers", True, muted), (f_s.x, lab_counts_y))
                    screen.blit(font_small.render("Fetchers", True, muted), (f_f.x, lab_counts_y))
                    screen.blit(font_small.render("Respawn", True, muted), (f_r.x, lab_counts_y))
                    fs = focused_field == (i, "soldiers")
                    ff = focused_field == (i, "fetchers")
                    frf = focused_field == (i, "respawn")
                    draw_entry_only(screen, f_s, col.soldiers_str, fs)
                    draw_entry_only(screen, f_f, col.fetchers_str, ff)
                    draw_entry_only(screen, f_r, col.respawn_str, frf)
                if isinstance(sol_dd, pygame.Rect):
                    screen.blit(
                        font_small.render("Soldier behavior", True, muted),
                        (inner.x, sol_dd.y - 16),
                    )
                    draw_combo_head(
                        screen,
                        sol_dd,
                        col.reward_soldier,
                        colony_dd == (i, "soldier"),
                        sol_dd.collidepoint(mx, my),
                    )
                if isinstance(fet_dd, pygame.Rect):
                    screen.blit(
                        font_small.render("Fetcher behavior", True, muted),
                        (inner.x, fet_dd.y - 16),
                    )
                    draw_combo_head(
                        screen,
                        fet_dd,
                        col.reward_fetcher,
                        colony_dd == (i, "fetcher"),
                        fet_dd.collidepoint(mx, my),
                    )
                if isinstance(col_dd, pygame.Rect):
                    screen.blit(
                        font_small.render("Colony color", True, muted),
                        (inner.x, col_dd.y - 16),
                    )
                    ccap = col.color_id.capitalize()
                    draw_combo_head(
                        screen,
                        col_dd,
                        ccap,
                        colony_dd == (i, "color"),
                        col_dd.collidepoint(mx, my),
                        COLONY_COLOR_RGB.get(col.color_id, (128, 128, 128)),
                    )

            if not simulation_colonies:
                empty = font_small.render("No colonies", True, muted)
                screen.blit(empty, (scroll_rect.x + 8, scroll_rect.y + 6))

        screen.set_clip(old_clip)
        if not edit_map and colony_dd is not None:
            ci, dk = colony_dd
            if 0 <= ci < len(simulation_colonies):
                cr = colony_card_screen_rect(ci)
                L = sim_card_layout(cr)
                head = (
                    L["sol_dd"]
                    if dk == "soldier"
                    else L["fet_dd"]
                    if dk == "fetcher"
                    else L["col_dd"]
                )
                if isinstance(head, pygame.Rect):
                    n = len(REWARD_SYSTEMS) if dk != "color" else len(COLONY_COLOR_ORDER)
                    opts = colony_dd_option_rects(head, n)
                    if opts:
                        big = opts[0].copy()
                        for orr in opts[1:]:
                            big = big.union(orr)
                        big = big.inflate(4, 4)
                        shad = pygame.Surface((big.w, big.h), pygame.SRCALPHA)
                        shad.fill((0, 0, 0, 80))
                        screen.blit(shad, (big.x + 2, big.y + 4))
                        pygame.draw.rect(screen, (32, 36, 48), big, border_radius=6)
                        pygame.draw.rect(screen, panel_border, big, width=1, border_radius=6)
                    panel_fill = (32, 36, 48)
                    for oi, orr in enumerate(opts):
                        hov = orr.collidepoint(mx, my)
                        pygame.draw.rect(
                            screen,
                            btn_hover if hov else panel_fill,
                            orr.inflate(-1, -1),
                            border_radius=4,
                        )
                        if dk == "color":
                            cid = COLONY_COLOR_ORDER[oi]
                            pygame.draw.circle(
                                screen,
                                COLONY_COLOR_RGB[cid],
                                (orr.x + 12, orr.centery),
                                6,
                            )
                            tt = font_small.render(cid.capitalize(), True, text_color)
                            screen.blit(tt, (orr.x + 24, orr.centery - tt.get_height() // 2))
                        else:
                            tt = font_small.render(REWARD_SYSTEMS[oi], True, text_color)
                            screen.blit(tt, (orr.x + 8, orr.centery - tt.get_height() // 2))

        if not edit_map and content_h > scroll_rect.height:
            bar_h = max(20, int(scroll_rect.height * scroll_rect.height / content_h))
            max_scroll = content_h - scroll_rect.height
            t = colony_scroll / max_scroll if max_scroll > 0 else 0.0
            by = scroll_rect.y + int(t * (scroll_rect.height - bar_h))
            bar = pygame.Rect(scroll_rect.right - 5, by, 4, bar_h)
            pygame.draw.rect(screen, (80, 88, 108), bar, border_radius=2)

        if add_modal_open:
            ov = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 130))
            screen.blit(ov, (0, 0))
            (
                mrect,
                close_r,
                new_bp_r,
                prev_br,
                next_br,
                card_r,
                imp_r,
            ) = layout_add_colony_modal()
            pygame.draw.rect(screen, card_bg, mrect, border_radius=12)
            pygame.draw.rect(screen, panel_border, mrect, width=2, border_radius=12)
            draw_button(screen, close_r, "×", close_r.collidepoint(mx, my), False)
            screen.blit(
                font_title.render("Add colony from blueprint", True, text_color),
                (mrect.x + 16, mrect.y + 10),
            )
            if len(simulation_colonies) >= MAX_SIM_COLONIES:
                full = font_small.render(f"Maximum {MAX_SIM_COLONIES} colonies", True, muted)
                screen.blit(full, (mrect.x + 16, mrect.y + 34))
            at_cap = len(simulation_colonies) >= MAX_SIM_COLONIES
            nbp = len(blueprints)
            bi = min(add_modal_bp_index, max(0, nbp - 1))
            dim_arrow = (100, 105, 120)
            if bi > 0:
                draw_button(screen, prev_br, "<", prev_br.collidepoint(mx, my), False)
            else:
                pygame.draw.rect(screen, (40, 44, 56), prev_br, border_radius=6)
                pygame.draw.rect(screen, panel_border, prev_br, width=1, border_radius=6)
                tp = font.render("<", True, dim_arrow)
                screen.blit(tp, tp.get_rect(center=prev_br.center))
            if nbp > 0 and bi < nbp - 1:
                draw_button(screen, next_br, ">", next_br.collidepoint(mx, my), False)
            else:
                pygame.draw.rect(screen, (40, 44, 56), next_br, border_radius=6)
                pygame.draw.rect(screen, panel_border, next_br, width=1, border_radius=6)
                tn = font.render(">", True, dim_arrow)
                screen.blit(tn, tn.get_rect(center=next_br.center))
            if nbp > 0:
                bp = blueprints[bi]
                sh = pygame.Rect(card_r.x + 2, card_r.y + 3, card_r.w, card_r.h)
                pygame.draw.rect(screen, (12, 14, 20), sh, border_radius=9)
                pygame.draw.rect(screen, card_bg, card_r, border_radius=8)
                pygame.draw.rect(screen, card_border, card_r, width=1, border_radius=8)
                L = sim_card_layout(card_r)
                inner = L["inner"]
                if isinstance(inner, pygame.Rect):
                    screen.blit(
                        font_small.render("Name", True, muted),
                        (inner.x, L["lab_name_y"]),
                    )
                name_r = L["name"]
                if isinstance(name_r, pygame.Rect):
                    nw = max(28, inner.w - 86) if isinstance(inner, pygame.Rect) else name_r.w
                    name_clip = pygame.Rect(name_r.x, name_r.y, nw, name_r.height)
                    draw_entry_only(screen, name_clip, bp.name, False)
                f_s = L["soldiers"]
                f_f = L["fetchers"]
                f_r = L["respawn"]
                lab_counts_y = L["lab_counts_y"]
                if (
                    isinstance(f_s, pygame.Rect)
                    and isinstance(f_f, pygame.Rect)
                    and isinstance(f_r, pygame.Rect)
                    and isinstance(lab_counts_y, int)
                ):
                    screen.blit(font_small.render("Soldiers", True, muted), (f_s.x, lab_counts_y))
                    screen.blit(font_small.render("Fetchers", True, muted), (f_f.x, lab_counts_y))
                    screen.blit(font_small.render("Respawn", True, muted), (f_r.x, lab_counts_y))
                    draw_entry_only(screen, f_s, bp.soldiers_str, False)
                    draw_entry_only(screen, f_f, bp.fetchers_str, False)
                    draw_entry_only(screen, f_r, bp.respawn_str, False)
                sol_dd = L["sol_dd"]
                fet_dd = L["fet_dd"]
                col_dd = L["col_dd"]
                if isinstance(sol_dd, pygame.Rect):
                    screen.blit(
                        font_small.render("Soldier behavior", True, muted),
                        (inner.x, sol_dd.y - 16),
                    )
                    draw_combo_head(
                        screen,
                        sol_dd,
                        bp.reward_soldier,
                        False,
                        False,
                    )
                if isinstance(fet_dd, pygame.Rect):
                    screen.blit(
                        font_small.render("Fetcher behavior", True, muted),
                        (inner.x, fet_dd.y - 16),
                    )
                    draw_combo_head(
                        screen,
                        fet_dd,
                        bp.reward_fetcher,
                        False,
                        False,
                    )
                if isinstance(col_dd, pygame.Rect):
                    screen.blit(
                        font_small.render("Colony color", True, muted),
                        (inner.x, col_dd.y - 16),
                    )
                    cid = first_free_color()
                    draw_combo_head(
                        screen,
                        col_dd,
                        cid.capitalize(),
                        False,
                        False,
                        COLONY_COLOR_RGB.get(cid, (128, 128, 128)),
                    )
                if at_cap:
                    pygame.draw.rect(screen, (40, 44, 56), imp_r, border_radius=6)
                    pygame.draw.rect(screen, panel_border, imp_r, width=1, border_radius=6)
                    ti = font_small.render("Import", True, dim_arrow)
                    screen.blit(ti, ti.get_rect(center=imp_r.center))
                else:
                    draw_button(screen, imp_r, "Import", imp_r.collidepoint(mx, my), False)
            else:
                pygame.draw.rect(screen, (12, 14, 20), card_r, border_radius=9)
                pygame.draw.rect(screen, card_bg, card_r, border_radius=8)
                pygame.draw.rect(screen, card_border, card_r, width=1, border_radius=8)
                nb = font_small.render("No blueprints", True, muted)
                screen.blit(nb, nb.get_rect(center=card_r.center))
            draw_button(screen, new_bp_r, "New blueprint…", new_bp_r.collidepoint(mx, my), False)

        if new_bp_modal_open:
            ov2 = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
            ov2.fill((0, 0, 0, 130))
            screen.blit(ov2, (0, 0))
            (
                nbr,
                nb_name_r,
                nb_sold_r,
                nb_fetch_r,
                nb_resp_r,
                nb_rsp,
                nb_rsn,
                nb_rfp,
                nb_rfn,
                nb_save_r,
                nb_can_r,
            ) = layout_new_blueprint_modal()
            pygame.draw.rect(screen, card_bg, nbr, border_radius=10)
            pygame.draw.rect(screen, panel_border, nbr, width=2, border_radius=10)
            screen.blit(font_title.render("New blueprint", True, text_color), (nbr.x + 16, nbr.y + 10))
            draw_text_field(
                screen,
                nb_name_r,
                new_bp_name,
                "Name",
                focused_bp_field == "name",
            )
            draw_text_field(
                screen,
                nb_sold_r,
                new_bp_soldiers_str,
                "Soldiers",
                focused_bp_field == "soldiers",
            )
            draw_text_field(
                screen,
                nb_fetch_r,
                new_bp_fetchers_str,
                "Fetchers",
                focused_bp_field == "fetchers",
            )
            draw_text_field(
                screen,
                nb_resp_r,
                new_bp_respawn_str,
                "Respawn",
                focused_bp_field == "respawn",
            )
            draw_button(screen, nb_rsp, "<", nb_rsp.collidepoint(mx, my), False)
            draw_button(screen, nb_rsn, ">", nb_rsn.collidepoint(mx, my), False)
            st = font_small.render(new_bp_reward_soldier, True, muted)
            screen.blit(st, st.get_rect(center=((nb_rsp.right + nb_rsn.left) // 2, nb_rsp.centery)))
            screen.blit(font_small.render("Soldier rw", True, muted), (nbr.x + 16, nb_rsp.y - 14))
            draw_button(screen, nb_rfp, "<", nb_rfp.collidepoint(mx, my), False)
            draw_button(screen, nb_rfn, ">", nb_rfn.collidepoint(mx, my), False)
            ft = font_small.render(new_bp_reward_fetcher, True, muted)
            screen.blit(ft, ft.get_rect(center=((nb_rfp.right + nb_rfn.left) // 2, nb_rfp.centery)))
            screen.blit(font_small.render("Fetcher rw", True, muted), (nbr.x + 16, nb_rfp.y - 14))
            draw_button(screen, nb_save_r, "Save", nb_save_r.collidepoint(mx, my), False)
            draw_button(screen, nb_can_r, "Cancel", nb_can_r.collidepoint(mx, my), False)

        pygame.display.flip()
        clock.tick(60)
    save_terrain()
    pygame.quit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ant colony simulation")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without opening a window.",
    )
    args = parser.parse_args()
    if args.headless:
        return run_headless()
    return run_window()


if __name__ == "__main__":
    sys.exit(main())
