import argparse
import sys
from dataclasses import dataclass

from ants.world import Food, Nest, Viewport, World

# World size in abstract units (shown as a letterboxed rectangle on screen).
WORLD_WIDTH = 2800.0
WORLD_HEIGHT = 2400.0
WINDOW_WIDTH = 1500
WINDOW_HEIGHT = 800
PANEL_WIDTH = 500
PANEL_MARGIN = 10
CARD_GAP = 8
CARD_HEIGHT = 148
REWARD_SYSTEMS = ("individualist", "cooperative", "safe", "explorer")


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
    food = Food(x=520.0, y=180.0, remaining=100.0, pickup_radius=36.0)
    nest = Nest(x=140.0, y=420.0, radius=42.0)
    print("Headless mode: no display (batch / RL later).")
    print(f"World: {world.width} x {world.height}")
    print(f"Food: ({food.x}, {food.y}) remaining={food.remaining} r={food.pickup_radius}")
    print(f"Nest: ({nest.x}, {nest.y}) r={nest.radius}")
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
    food = Food(x=520.0, y=180.0, remaining=100.0, pickup_radius=36.0)
    nest = Nest(x=140.0, y=420.0, radius=42.0)

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Ant colony sim")
    clock = pygame.time.Clock()
    font, font_small, font_title = _make_ui_fonts()

    border_color = (120, 140, 160)
    nest_fill = (55, 48, 40)
    nest_outline = (110, 92, 72)
    food_fill = (72, 160, 90)
    food_outline = (120, 210, 130)
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
    sim_running = False
    edit_map = False
    colony_scroll = 0
    next_custom_id = 1
    # (colony_index, "soldiers"|"fetchers"|"respawn") | None
    focused_field: tuple[int, str] | None = None

    panel_x = world_w
    btn_h = 32
    row1_y = 44
    row2_y = row1_y + btn_h + 8
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

    running = True
    mouse_xy = (0, 0)
    while running:
        mx, my = mouse_xy
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
            elif event.type == pygame.MOUSEMOTION:
                mouse_xy = event.pos
            elif event.type == pygame.MOUSEWHEEL:
                if scroll_rect.collidepoint(mx, my):
                    colony_scroll -= event.y * 28
                    clamp_scroll()
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                focused_field = None
                px, py = event.pos
                # panel-local coords for hit tests in panel
                if px < panel_x:
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
                    edit_map = not edit_map
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
                        # card hit tests (scroll offset)
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

        screen.fill((20, 24, 32))
        rx, ry, rw, rh = viewport.world_rect_screen()
        pygame.draw.rect(screen, border_color, (rx, ry, rw, rh), width=2)
        nx, ny = viewport.world_to_screen(nest.x, nest.y)
        nr = viewport.world_dist_to_screen(nest.radius)
        pygame.draw.circle(screen, nest_fill, (nx, ny), nr)
        pygame.draw.circle(screen, nest_outline, (nx, ny), nr, width=2)
        fx, fy = viewport.world_to_screen(food.x, food.y)
        fr = viewport.world_dist_to_screen(food.pickup_radius)
        pygame.draw.circle(screen, food_fill, (fx, fy), fr)
        pygame.draw.circle(screen, food_outline, (fx, fy), fr, width=2)

        if not sim_running:
            overlay = pygame.Surface((rw, rh), pygame.SRCALPHA)
            overlay.fill((10, 12, 18, 120))
            screen.blit(overlay, (rx, ry))
            paused_txt = font_title.render("Paused", True, text_color)
            screen.blit(paused_txt, paused_txt.get_rect(center=(rx + rw // 2, ry + rh // 2)))

        pygame.draw.line(screen, panel_border, (panel_x, 0), (panel_x, WINDOW_HEIGHT), width=1)
        panel_surf = screen.subsurface(pygame.Rect(panel_x, 0, PANEL_WIDTH, WINDOW_HEIGHT))
        panel_surf.fill(panel_bg)

        title = font_title.render("Simulation", True, text_color)
        panel_surf.blit(title, (PANEL_MARGIN, 12))

        row1 = pygame.Rect(
            PANEL_MARGIN,
            row1_y,
            (PANEL_WIDTH - 3 * PANEL_MARGIN) // 2,
            btn_h,
        )
        row1b = pygame.Rect(row1.right + PANEL_MARGIN, row1_y, row1.width, btn_h)
        draw_button(panel_surf, row1, "Start", row1.collidepoint(mx - panel_x, my), False)
        draw_button(panel_surf, row1b, "Pause", row1b.collidepoint(mx - panel_x, my), False)
        edit_r = pygame.Rect(PANEL_MARGIN, row2_y, PANEL_WIDTH - 2 * PANEL_MARGIN, btn_h)
        draw_button(panel_surf, edit_r, "Edit map", edit_r.collidepoint(mx - panel_x, my), edit_map)

        cl = font.render("Colonies", True, text_color)
        panel_surf.blit(cl, (PANEL_MARGIN, col_label_y))
        add_rect = pygame.Rect(PANEL_MARGIN, add_y, PANEL_WIDTH - 2 * PANEL_MARGIN, add_btn_h)
        draw_button(panel_surf, add_rect, "+ Add colony", add_rect.collidepoint(mx - panel_x, my), False)

        old_clip = screen.get_clip()
        screen.set_clip(scroll_rect)
        content_h = colonies_content_height()
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
        if content_h > scroll_rect.height:
            bar_h = max(20, int(scroll_rect.height * scroll_rect.height / content_h))
            max_scroll = content_h - scroll_rect.height
            t = colony_scroll / max_scroll if max_scroll > 0 else 0.0
            by = scroll_rect.y + int(t * (scroll_rect.height - bar_h))
            bar = pygame.Rect(scroll_rect.right - 5, by, 4, bar_h)
            pygame.draw.rect(screen, (80, 88, 108), bar, border_radius=2)

        pygame.display.flip()
        clock.tick(60)
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
