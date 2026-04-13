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
CARD_GAP = 8
CARD_HEIGHT = 148
REWARD_SYSTEMS = ("individualist", "cooperative", "safe", "explorer")

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
SESSION_VERSION = 2
_SESSION_VERSION_LEGACY = 1


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


@dataclass
class ColonyRow:
    name: str
    soldiers_str: str = "3"
    fetchers_str: str = "5"
    respawn_str: str = "1.0"
    reward: str = "individualist"

    @classmethod
    def preset(cls, name: str, reward: str) -> "ColonyRow":
        return cls(name=name, reward=reward)


def default_colonies() -> list[ColonyRow]:
    return [
        ColonyRow.preset("Individualist", "individualist"),
        ColonyRow.preset("Cooperative", "cooperative"),
        ColonyRow.preset("Safe", "safe"),
        ColonyRow.preset("Explorer", "explorer"),
    ]


def _session_row_to_dict(row: ColonyRow) -> dict:
    return {
        "name": row.name,
        "soldiers_str": row.soldiers_str,
        "fetchers_str": row.fetchers_str,
        "respawn_str": row.respawn_str,
        "reward": row.reward,
    }


def _session_row_from_dict(o: object) -> ColonyRow | None:
    if not isinstance(o, dict):
        return None
    name = o.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    rw = o.get("reward", "individualist")
    if rw not in REWARD_SYSTEMS:
        rw = "individualist"
    return ColonyRow(
        name=name,
        soldiers_str=str(o.get("soldiers_str", "3")),
        fetchers_str=str(o.get("fetchers_str", "5")),
        respawn_str=str(o.get("respawn_str", "1.0")),
        reward=rw,
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
    if ver not in (SESSION_VERSION, _SESSION_VERSION_LEGACY):
        return None
    return d


def _session_write(
    colonies: list[ColonyRow],
    next_custom_id: int,
    colony_scroll: int,
    brush_radius_index: int,
    sim_running: bool,
    foods: list[tuple[float, float]],
    edit_tool: str,
    food_speed_index: int,
) -> None:
    tmp = SESSION_SAVE_FILE.with_suffix(".tmp.json")
    payload = {
        "version": SESSION_VERSION,
        "colonies": [_session_row_to_dict(c) for c in colonies],
        "next_custom_id": next_custom_id,
        "colony_scroll": colony_scroll,
        "brush_radius_index": brush_radius_index,
        "sim_running": sim_running,
        "foods": [{"x": fx, "y": fy} for fx, fy in foods],
        "edit_tool": edit_tool if edit_tool in ("terrain", "food") else "terrain",
        "food_speed_index": food_speed_index,
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

    colonies: list[ColonyRow] = default_colonies()
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
    # (colony_index, "soldiers"|"fetchers"|"respawn") | None
    focused_field: tuple[int, str] | None = None

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

    def cycle_reward(current: str, delta: int) -> str:
        opts = list(REWARD_SYSTEMS)
        try:
            i = opts.index(current)
        except ValueError:
            i = 0
        return opts[(i + delta) % len(opts)]

    def colonies_content_height() -> int:
        if not colonies:
            return 40
        return len(colonies) * (CARD_HEIGHT + CARD_GAP) + CARD_GAP

    def clamp_scroll() -> None:
        nonlocal colony_scroll
        max_scroll = max(0, colonies_content_height() - scroll_rect.height)
        colony_scroll = min(max(0, colony_scroll), max_scroll)

    sd = _session_read()
    if sd is not None:
        raw_cols = sd.get("colonies")
        if isinstance(raw_cols, list) and raw_cols:
            parsed: list[ColonyRow] = []
            for item in raw_cols:
                row = _session_row_from_dict(item)
                if row is not None:
                    parsed.append(row)
            if parsed:
                colonies = parsed
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
        if et == "food" or et == "terrain":
            edit_tool = et
        if "food_speed_index" in sd:
            try:
                fsi = int(sd["food_speed_index"])
                if 0 <= fsi < FOOD_SPEED_COUNT:
                    food_speed_index = fsi
            except (TypeError, ValueError):
                pass
    clamp_scroll()

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
            colonies,
            next_custom_id,
            colony_scroll,
            brush_radius_index,
            sim_running,
            foods,
            edit_tool,
            food_speed_index,
        )

    def edit_layout() -> tuple[
        pygame.Rect,
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
        return (
            done_r,
            terrain_tool_r,
            terrain_drop_r,
            terrain_opt_rects,
            food_tool_r,
            food_drop_r,
            food_opt_rects,
        )

    def preset_circle_radius(preset_r: int, cell_w: int, cell_h: int) -> int:
        cap = min(cell_w, cell_h) // 2 - 3
        cap = max(3, cap)
        return max(2, min(cap, int(round(preset_r * cap / BRUSH_PRESET_MAX))))

    map_screen_rect = pygame.Rect(map_rx, map_ry, map_rw, map_rh)

    running = True
    mouse_xy = (0, 0)
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_terrain()
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
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
                if not edit_map and scroll_rect.collidepoint(whx, why):
                    colony_scroll -= event.y * 28
                    clamp_scroll()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                px, py = event.pos
                plx, ply = px - panel_x, py

                if px < panel_x:
                    focused_field = None
                    if edit_map and map_screen_rect.collidepoint(px, py):
                        brush_dropdown_open = False
                        food_speed_dropdown_open = False
                        lx_f = px - map_rx
                        ly_f = py - map_ry
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
                else:
                    add_rect = pygame.Rect(
                        panel_x + PANEL_MARGIN,
                        add_y,
                        PANEL_WIDTH - 2 * PANEL_MARGIN,
                        add_btn_h,
                    )
                    if add_rect.collidepoint(px, py):
                        colonies.append(
                            ColonyRow(
                                name=f"Colony {next_custom_id}",
                                reward="individualist",
                            )
                        )
                        next_custom_id += 1
                        clamp_scroll()
                    elif scroll_rect.collidepoint(px, py):
                        rel_y = py - scroll_rect.y + colony_scroll
                        idx = int(rel_y // (CARD_HEIGHT + CARD_GAP))
                        if 0 <= idx < len(colonies):
                            c = colonies[idx]
                            card_top = scroll_rect.y + idx * (CARD_HEIGHT + CARD_GAP) - colony_scroll
                            card_rect = pygame.Rect(
                                scroll_rect.x + 2,
                                card_top,
                                scroll_rect.width - 4,
                                CARD_HEIGHT,
                            )
                            if not card_rect.collidepoint(px, py):
                                pass
                            else:
                                inner = pygame.Rect(
                                    card_rect.x + 8,
                                    card_rect.y + 30,
                                    card_rect.w - 16,
                                    CARD_HEIGHT - 38,
                                )
                                third = (inner.w - 16) // 3
                                f_s = pygame.Rect(inner.x, inner.y + 18, third, 26)
                                f_f = pygame.Rect(f_s.right + 8, inner.y + 18, third, 26)
                                f_r = pygame.Rect(f_f.right + 8, inner.y + 18, third, 26)
                                rew_y = inner.y + 18 + 26 + 10
                                rew_prev = pygame.Rect(inner.x, rew_y, 28, 24)
                                rew_next = pygame.Rect(inner.right - 28, rew_y, 28, 24)
                                if f_s.collidepoint(px, py):
                                    focused_field = (idx, "soldiers")
                                elif f_f.collidepoint(px, py):
                                    focused_field = (idx, "fetchers")
                                elif f_r.collidepoint(px, py):
                                    focused_field = (idx, "respawn")
                                elif rew_prev.collidepoint(px, py):
                                    c.reward = cycle_reward(c.reward, -1)
                                elif rew_next.collidepoint(px, py):
                                    c.reward = cycle_reward(c.reward, 1)

            elif event.type == pygame.KEYDOWN and focused_field is not None:
                ci, which = focused_field
                c = colonies[ci]
                key = event.key
                buf = {"soldiers": c.soldiers_str, "fetchers": c.fetchers_str, "respawn": c.respawn_str}[which]
                if key == pygame.K_BACKSPACE:
                    buf = buf[:-1]
                elif key == pygame.K_RETURN or key == pygame.K_TAB:
                    focused_field = None
                    continue
                elif which in ("soldiers", "fetchers"):
                    if event.unicode.isdigit():
                        buf += event.unicode
                else:
                    if event.unicode.isdigit() or (event.unicode == "." and "." not in buf):
                        buf += event.unicode
                if which == "soldiers":
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

        if edit_map and map_screen_rect.collidepoint(mx, my):
            if edit_tool == "terrain":
                pygame.draw.circle(screen, BRUSH_PREVIEW_WHITE, (mx, my), brush_radius_px, width=2)
            elif edit_tool == "food" and food_cursor_sprite is not None:
                crect = food_cursor_sprite.get_rect(center=(mx, my))
                screen.blit(food_cursor_sprite, crect)
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
            draw_button(panel_surf, add_rect, "+ Add colony", add_rect.collidepoint(plx, ply), False)

        old_clip = screen.get_clip()
        screen.set_clip(scroll_rect)
        content_h = colonies_content_height()
        if not edit_map:
            for i, col in enumerate(colonies):
                card_top = scroll_rect.y + i * (CARD_HEIGHT + CARD_GAP) - colony_scroll
                card_rect = pygame.Rect(scroll_rect.x + 2, card_top, scroll_rect.width - 4, CARD_HEIGHT)
                if card_rect.bottom < scroll_rect.top or card_rect.top > scroll_rect.bottom:
                    continue
                pygame.draw.rect(screen, card_bg, card_rect, border_radius=8)
                pygame.draw.rect(screen, card_border, card_rect, width=1, border_radius=8)
                name_s = font.render(col.name, True, text_color)
                screen.blit(name_s, (card_rect.x + 10, card_rect.y + 8))
                inner = pygame.Rect(card_rect.x + 8, card_rect.y + 30, card_rect.w - 16, CARD_HEIGHT - 38)
                third = (inner.w - 16) // 3
                f_s = pygame.Rect(inner.x, inner.y + 18, third, 26)
                f_f = pygame.Rect(f_s.right + 8, inner.y + 18, third, 26)
                f_r = pygame.Rect(f_f.right + 8, inner.y + 18, third, 26)
                fs = focused_field == (i, "soldiers")
                ff = focused_field == (i, "fetchers")
                frf = focused_field == (i, "respawn")
                draw_text_field(screen, f_s, col.soldiers_str, "Soldiers", fs)
                draw_text_field(screen, f_f, col.fetchers_str, "Fetchers", ff)
                draw_text_field(screen, f_r, col.respawn_str, "Respawn", frf)
                rew_y = inner.y + 18 + 26 + 10
                rew_prev = pygame.Rect(inner.x, rew_y, 28, 24)
                rew_next = pygame.Rect(inner.right - 28, rew_y, 28, 24)
                draw_button(screen, rew_prev, "<", rew_prev.collidepoint(mx, my), False)
                draw_button(screen, rew_next, ">", rew_next.collidepoint(mx, my), False)
                rw_txt = font_small.render(col.reward, True, muted)
                rw_rect = rw_txt.get_rect(center=((rew_prev.right + rew_next.left) // 2, rew_y + 12))
                screen.blit(rw_txt, rw_rect)
                lab = font_small.render("Reward", True, muted)
                screen.blit(lab, (inner.x, rew_y - 14))

            if not colonies:
                empty = font_small.render("No colonies", True, muted)
                screen.blit(empty, (scroll_rect.x + 8, scroll_rect.y + 6))

        screen.set_clip(old_clip)
        if not edit_map and content_h > scroll_rect.height:
            bar_h = max(20, int(scroll_rect.height * scroll_rect.height / content_h))
            max_scroll = content_h - scroll_rect.height
            t = colony_scroll / max_scroll if max_scroll > 0 else 0.0
            by = scroll_rect.y + int(t * (scroll_rect.height - bar_h))
            bar = pygame.Rect(scroll_rect.right - 5, by, 4, bar_h)
            pygame.draw.rect(screen, (80, 88, 108), bar, border_radius=2)

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
