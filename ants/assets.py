import io
from pathlib import Path

from ants.config import ASSET_DIR, PROJECT_ROOT


def colony_png_search_paths() -> tuple[Path, ...]:
    return (
        ASSET_DIR / "ant-colony.png",
        PROJECT_ROOT / "ant-colony.png",
        Path.cwd() / "asset" / "ant-colony.png",
        Path.cwd() / "ant-colony.png",
    )


def pygame_load_png(pygame_mod: object, path: Path) -> object | None:
    try:
        return pygame_mod.image.load(str(path.resolve()))
    except Exception:
        pass
    try:
        return pygame_mod.image.load(io.BytesIO(path.read_bytes()))
    except Exception:
        pass
    return png_surface_via_pillow(pygame_mod, path)


def png_surface_via_pillow(pygame_mod: object, path: Path) -> object | None:
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


def synthetic_nest_icon(pygame_mod: object, size: int = 28) -> object:
    s = pygame_mod.Surface((size, size), pygame_mod.SRCALPHA)
    cx = size // 2
    r = max(4, size // 2 - 3)
    pygame_mod.draw.circle(s, (220, 220, 228, 255), (cx, cx), r)
    pygame_mod.draw.circle(s, (40, 42, 52, 255), (cx, cx), r, width=2)
    return s


def punch_near_white_transparent(surf: object, pygame_mod: object, thresh: int = 242) -> None:
    w, h = surf.get_size()
    for y in range(h):
        for x in range(w):
            c = surf.get_at((x, y))
            if len(c) < 4:
                continue
            r, g, b, a = int(c[0]), int(c[1]), int(c[2]), int(c[3])
            if a > 8 and r >= thresh and g >= thresh and b >= thresh:
                surf.set_at((x, y), (0, 0, 0, 0))


def tint_colony_sprite(surf: object, rgb: tuple[int, int, int], pygame_mod: object) -> object:
    t = surf.copy()
    try:
        t = t.convert_alpha()
    except (pygame_mod.error, TypeError, ValueError):
        try:
            t = t.convert(32)
        except (pygame_mod.error, TypeError, ValueError):
            pass
    r_t, g_t, b_t = rgb
    dr, dg, db = int(r_t * 0.38), int(g_t * 0.38), int(b_t * 0.38)
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
            luma = luma * luma * (3.0 - 2.0 * luma)
            nr = int(dr + (lr - dr) * luma + 0.5)
            ng = int(dg + (lg - dg) * luma + 0.5)
            nb = int(db + (lb - db) * luma + 0.5)
            t.set_at(
                (xx, yy),
                (max(0, min(255, nr)), max(0, min(255, ng)), max(0, min(255, nb)), a),
            )
    return t
