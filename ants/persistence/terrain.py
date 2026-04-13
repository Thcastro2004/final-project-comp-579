import io
import os
import struct
from pathlib import Path

from ants.config import TERRAIN_BIN_MAGIC, TERRAIN_SAVE_FILE

_TERRAIN_HEADER = struct.Struct("<4sII")


def _terrain_tmp_path(path: Path) -> Path:
    return path.parent / f"{path.stem}.tmp{path.suffix}"


def terrain_candidate_paths() -> tuple[Path, ...]:
    from ants.config import LEGACY_TERRAIN_FILE, SAVE_DIR

    return (
        TERRAIN_SAVE_FILE,
        SAVE_DIR / "terrain_map.bmp",
        SAVE_DIR / "terrain_map.png",
        LEGACY_TERRAIN_FILE,
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


def terrain_save_bin(path: Path, surf: object, pygame_mod: object) -> None:
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


def terrain_blit_file_into(path: Path, pygame_mod: object, dest: object, map_rw: int, map_rh: int) -> bool:
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


def terrain_tmp_path(path: Path) -> Path:
    return _terrain_tmp_path(path)
