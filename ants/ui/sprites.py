import sys
from typing import Any

from ants.assets import (
    colony_png_search_paths,
    png_surface_via_pillow,
    punch_near_white_transparent,
    pygame_load_png,
    synthetic_nest_icon,
    tint_colony_sprite,
)
from ants.config import (
    ASSET_DIR,
    COLONY_COLOR_RGB,
    COLONY_CURSOR_PREVIEW_MAX_PX,
    COLONY_SPRITE_SCALE,
    DEBUG_COLONY_NO_CONVERT_ALPHA,
    DEBUG_COLONY_NO_TINT,
    FOOD_CURSOR_PREVIEW_MAX_PX,
)


class ColonyTintCache:
    def __init__(
        self,
        pygame_mod: Any,
        colony_base_sprite: Any,
        colony_cursor_sprite: Any,
    ) -> None:
        self._pygame = pygame_mod
        self._base = colony_base_sprite
        self._cursor_base = colony_cursor_sprite
        self._tinted: dict[str, Any] = {}

    def for_color(self, color_id: str) -> Any | None:
        if self._base is None:
            return None
        if DEBUG_COLONY_NO_TINT:
            return self._base
        if color_id not in COLONY_COLOR_RGB:
            color_id = "black"
        if color_id not in self._tinted:
            try:
                self._tinted[color_id] = tint_colony_sprite(
                    self._base, COLONY_COLOR_RGB[color_id], self._pygame
                )
            except Exception:
                return self._base
        return self._tinted[color_id]

    def cursor_for_color(self, color_id: str) -> Any | None:
        base = self._cursor_base if self._cursor_base is not None else self._base
        if base is None:
            return None
        if DEBUG_COLONY_NO_TINT:
            return base
        key = f"c:{color_id}"
        if key not in self._tinted:
            if color_id not in COLONY_COLOR_RGB:
                color_id = "black"
            try:
                self._tinted[key] = tint_colony_sprite(base, COLONY_COLOR_RGB[color_id], self._pygame)
            except Exception:
                return base
        return self._tinted[key]


def load_food_sprites(pygame_mod: Any) -> tuple[Any | None, Any | None]:
    food_sprite_path = ASSET_DIR / "ant-food.png"
    food_cursor_sprite = None
    food_sprite = None
    try:
        _raw_food = pygame_mod.image.load(str(food_sprite_path.resolve()))
        try:
            food_sprite = _raw_food.convert_alpha()
        except (pygame_mod.error, TypeError, ValueError):
            food_sprite = _raw_food.convert()
        iw, ih = food_sprite.get_size()
        if iw > 0 and ih > 0:
            hw = max(1, int(round(iw * 0.5)))
            hh = max(1, int(round(ih * 0.5)))
            if (hw, hh) != (iw, ih):
                food_sprite = pygame_mod.transform.smoothscale(food_sprite, (hw, hh))
            cw, ch = food_sprite.get_size()
            cap = FOOD_CURSOR_PREVIEW_MAX_PX
            cscale = min(cap / cw, cap / ch, 1.0)
            nw = max(1, int(round(cw * cscale)))
            nh = max(1, int(round(ch * cscale)))
            food_cursor_sprite = (
                pygame_mod.transform.smoothscale(food_sprite, (nw, nh))
                if (nw, nh) != (cw, ch)
                else food_sprite
            )
    except (pygame_mod.error, OSError, TypeError, ValueError):
        food_sprite = None
        food_cursor_sprite = None
    return food_sprite, food_cursor_sprite


def load_colony_sprites(pygame_mod: Any) -> tuple[ColonyTintCache, Any | None, Any | None]:
    colony_base_sprite = None
    colony_cursor_sprite = None
    _raw_col = None
    _colony_png_primary = ASSET_DIR / "ant-colony.png"
    try:
        _raw_col = pygame_mod.image.load(str(_colony_png_primary.resolve()))
    except Exception:
        _raw_col = None
    if _raw_col is None:
        _raw_col = png_surface_via_pillow(pygame_mod, _colony_png_primary)
    if _raw_col is None:
        _seen_colony_path: set[str] = set()
        for _cp in colony_png_search_paths():
            _key = str(_cp.resolve())
            if _key in _seen_colony_path:
                continue
            _seen_colony_path.add(_key)
            _raw_col = pygame_load_png(pygame_mod, _cp)
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
                    colony_base_sprite = pygame_mod.transform.smoothscale(colony_base_sprite, (hw, hh))
                except Exception:
                    pass
        if colony_base_sprite is not None:
            if not DEBUG_COLONY_NO_TINT:
                try:
                    punch_near_white_transparent(colony_base_sprite, pygame_mod)
                except (pygame_mod.error, TypeError, ValueError, AttributeError, OSError):
                    pass
            try:
                cw, ch = colony_base_sprite.get_size()
                cap = COLONY_CURSOR_PREVIEW_MAX_PX
                cscale = min(cap / cw, cap / ch, 1.0)
                nw = max(1, int(round(cw * cscale)))
                nh = max(1, int(round(ch * cscale)))
                colony_cursor_sprite = (
                    pygame_mod.transform.smoothscale(colony_base_sprite, (nw, nh))
                    if (nw, nh) != (cw, ch)
                    else colony_base_sprite
                )
            except Exception:
                colony_cursor_sprite = colony_base_sprite
    else:
        print("[ants] ant-colony.png not loaded. Candidates:", file=sys.stderr)
        for _cp in colony_png_search_paths():
            _r = _cp.resolve()
            print(f"  {_r}  exists={_r.is_file()}", file=sys.stderr)
        try:
            pygame_mod.image.load(str(_colony_png_primary.resolve()))
        except Exception as _e:
            print(f"[ants] pygame.image.load({_colony_png_primary.resolve()!s}) -> {_e!r}", file=sys.stderr)
        colony_base_sprite = synthetic_nest_icon(pygame_mod)
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
                pygame_mod.transform.smoothscale(colony_base_sprite, (nw, nh))
                if (nw, nh) != (cw, ch)
                else colony_base_sprite
            )
        except Exception:
            colony_cursor_sprite = colony_base_sprite
        print("[ants] using built-in nest icon (see errors above).", file=sys.stderr)
        try:
            import PIL  # noqa: F401
        except ImportError:
            print(
                "[ants] install pillow (pip install pillow) if pygame cannot decode PNGs on your system.",
                file=sys.stderr,
            )

    cache = ColonyTintCache(pygame_mod, colony_base_sprite, colony_cursor_sprite)
    return cache, colony_base_sprite, colony_cursor_sprite
