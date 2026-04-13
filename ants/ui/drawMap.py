from typing import Any

from ants.config import (
    BRUSH_PREVIEW_FAINT,
    BRUSH_PREVIEW_WHITE,
    COLONY_COLOR_RGB,
    FOOD_ERASE_SEARCH_RADIUS_PX,
    FOOD_GROW_PER_MS,
    FOOD_SPAWN_INTERVAL_MS,
    TERRAIN_TUNNEL,
    TERRAIN_WALL,
    WINDOW_HEIGHT,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.ui.drawWidgets import draw_colony_invalid_cross
from ants.ui.helpers import is_colony_ground_at_map_pixel
from ants.ui.helpers import in_editable
from ants.ui.state import GameState, RuntimeBundle


def update_food_paint_while_held(pg: Any, bundle: RuntimeBundle, state: GameState) -> None:
    mx, my = pg.mouse.get_pos()
    p = bundle.panel
    if (
        state.edit_map
        and state.edit_tool == "food"
        and mx < p.panel_x
        and p.map_screen_rect.collidepoint(mx, my)
    ):
        lx_loop = mx - p.map_rx
        ly_loop = my - p.map_ry
        if in_editable(lx_loop, ly_loop, p.editable_inner):
            pressed_loop = pg.mouse.get_pressed(3)
            now_loop = pg.time.get_ticks()
            if pressed_loop[0] and state.food_lmb_active:
                if now_loop - state.last_food_spawn_ms >= FOOD_SPAWN_INTERVAL_MS:
                    state.last_food_spawn_ms = now_loop
                    elapsed = max(0, now_loop - state.food_press_ms)
                    from ants.ui.helpers import food_spawn_burst

                    food_spawn_burst(
                        pg,
                        bundle.terrain_surf,
                        state,
                        p,
                        lx_loop,
                        ly_loop,
                        elapsed,
                        TERRAIN_TUNNEL,
                        TERRAIN_WALL,
                    )
            if pressed_loop[2] and state.food_rmb_active:
                if now_loop - state.last_food_erase_ms >= FOOD_SPAWN_INTERVAL_MS:
                    state.last_food_erase_ms = now_loop
                    from ants.ui.map_tools import erase_foods_by_proximity

                    erase_foods_by_proximity(state, p, lx_loop, ly_loop)


def draw_map_view(pg: Any, bundle: RuntimeBundle, state: GameState) -> None:
    screen = bundle.screen
    theme = bundle.theme
    p = bundle.panel
    font_title = bundle.font_title
    rx, ry, rw, rh = p.map_rx, p.map_ry, p.map_rw, p.map_rh

    screen.fill((20, 24, 32))
    screen.blit(bundle.terrain_surf, (rx, ry))
    pg.draw.rect(screen, theme.border_color, (rx, ry, rw, rh), width=2)

    if not state.sim_running and not state.edit_map:
        overlay = pg.Surface((rw, rh), pg.SRCALPHA)
        overlay.fill((10, 12, 18, 120))
        screen.blit(overlay, (rx, ry))
        paused_txt = font_title.render("Paused", True, theme.text_color)
        screen.blit(paused_txt, paused_txt.get_rect(center=(rx + rw // 2, ry + rh // 2)))

    for fwx, fwy in state.foods:
        flx = fwx / WORLD_WIDTH * rw
        fly = fwy / WORLD_HEIGHT * rh
        fsx = int(rx + flx)
        fsy = int(ry + fly)
        if bundle.food_sprite is not None:
            fr = bundle.food_sprite.get_rect(center=(fsx, fsy))
            screen.blit(bundle.food_sprite, fr)
        else:
            pg.draw.circle(screen, (72, 180, 96), (fsx, fsy), 2)

    for sc in state.simulation_colonies:
        if sc.nest_x is None or sc.nest_y is None:
            continue
        flx = sc.nest_x / WORLD_WIDTH * rw
        fly = sc.nest_y / WORLD_HEIGHT * rh
        nsx = int(rx + flx)
        nsy = int(ry + fly)
        ns = bundle.colony_sprites.for_color(sc.color_id)
        if ns is not None:
            nr = ns.get_rect(center=(nsx, nsy))
            screen.blit(ns, nr)
        else:
            pg.draw.circle(
                screen, COLONY_COLOR_RGB.get(sc.color_id, (200, 200, 200)), (nsx, nsy), 6, width=2
            )

    mx, my = state.mouse_xy
    if state.edit_map and p.map_screen_rect.collidepoint(mx, my):
        if state.edit_tool == "terrain":
            pg.draw.circle(screen, BRUSH_PREVIEW_WHITE, (mx, my), state.brush_radius_px, width=2)
        elif state.edit_tool == "food" and bundle.food_cursor_sprite is not None:
            crect = bundle.food_cursor_sprite.get_rect(center=(mx, my))
            screen.blit(bundle.food_cursor_sprite, crect)
        elif state.edit_tool == "colony" and state.simulation_colonies:
            lx_c = mx - p.map_rx
            ly_c = my - p.map_ry
            if 0.0 <= lx_c < rw and 0.0 <= ly_c < rh:
                if is_colony_ground_at_map_pixel(
                    pg,
                    bundle.terrain_surf,
                    lx_c,
                    ly_c,
                    rw,
                    rh,
                    p.editable_inner,
                    TERRAIN_TUNNEL,
                    TERRAIN_WALL,
                ):
                    eci = min(state.edit_colony_index, len(state.simulation_colonies) - 1)
                    cc = bundle.colony_sprites.cursor_for_color(state.simulation_colonies[eci].color_id)
                    if cc is not None:
                        screen.blit(cc, cc.get_rect(center=(mx, my)))
                    else:
                        cid = state.simulation_colonies[eci].color_id
                        pg.draw.circle(
                            screen,
                            COLONY_COLOR_RGB.get(cid, (128, 128, 128)),
                            (mx, my),
                            6,
                            width=2,
                        )
                else:
                    draw_colony_invalid_cross(pg, screen, mx, my)
        if (
            state.edit_tool == "food"
            and state.food_lmb_active
            and pg.mouse.get_pressed(3)[0]
            and mx < p.panel_x
            and in_editable(mx - p.map_rx, my - p.map_ry, p.editable_inner)
        ):
            now_pv = pg.time.get_ticks()
            elapsed_pv = max(0, now_pv - state.food_press_ms)
            Rpv = min(p.food_r_max_px, FOOD_GROW_PER_MS * elapsed_pv)
            Rpv = max(2.0, Rpv)
            pg.draw.circle(screen, BRUSH_PREVIEW_FAINT, (mx, my), int(Rpv), width=1)
        if (
            state.edit_tool == "food"
            and state.food_rmb_active
            and pg.mouse.get_pressed(3)[2]
            and mx < p.panel_x
            and in_editable(mx - p.map_rx, my - p.map_ry, p.editable_inner)
        ):
            pg.draw.circle(
                screen,
                BRUSH_PREVIEW_FAINT,
                (mx, my),
                FOOD_ERASE_SEARCH_RADIUS_PX,
                width=1,
            )

    pg.draw.line(screen, theme.panel_border, (p.panel_x, 0), (p.panel_x, WINDOW_HEIGHT), width=1)
