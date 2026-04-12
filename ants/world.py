"""Rectangular world in continuous coordinates; origin (0,0) is top-left, x right, y down."""

from dataclasses import dataclass
import math


def distance(ax: float, ay: float, bx: float, by: float) -> float:
    return math.hypot(bx - ax, by - ay)


def normalize(dx: float, dy: float) -> tuple[float, float]:
    d = math.hypot(dx, dy)
    if d <= 0.0:
        return (0.0, 0.0)
    return (dx / d, dy / d)


@dataclass
class Food:
    x: float
    y: float
    remaining: float
    pickup_radius: float


@dataclass
class Nest:
    x: float
    y: float
    radius: float


class World:
    def __init__(self, width: float, height: float) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("width and height must be positive")
        self.width = width
        self.height = height

    def clamp_point(self, x: float, y: float) -> tuple[float, float]:
        return (
            min(max(0.0, x), self.width),
            min(max(0.0, y), self.height),
        )

    def contains(self, x: float, y: float) -> bool:
        return 0.0 <= x <= self.width and 0.0 <= y <= self.height


class Viewport:
    """Maps world coordinates to screen pixels (letterboxed, margin)."""

    def __init__(
        self,
        world: World,
        screen_width: int,
        screen_height: int,
        margin: int = 24,
        content_rect: tuple[int, int, int, int] | None = None,
    ) -> None:
        self.world = world
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.margin = margin
        if content_rect is None:
            cx, cy, cw, ch = 0, 0, screen_width, screen_height
        else:
            cx, cy, cw, ch = content_rect
        inner_w = max(1, cw - 2 * margin)
        inner_h = max(1, ch - 2 * margin)
        self.scale = min(inner_w / world.width, inner_h / world.height)
        w_px = world.width * self.scale
        h_px = world.height * self.scale
        self.offset_x = cx + margin
        self.offset_y = cy + margin + (inner_h - h_px) / 2.0

    def world_to_screen(self, wx: float, wy: float) -> tuple[int, int]:
        sx = int(self.offset_x + wx * self.scale)
        sy = int(self.offset_y + wy * self.scale)
        return sx, sy

    def world_rect_screen(self) -> tuple[int, int, int, int]:
        x0 = int(self.offset_x)
        y0 = int(self.offset_y)
        w = int(self.world.width * self.scale)
        h = int(self.world.height * self.scale)
        return (x0, y0, w, h)

    def world_dist_to_screen(self, world_len: float) -> int:
        return max(1, int(round(world_len * self.scale)))
