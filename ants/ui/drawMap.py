import math
from typing import Any

from ants.config import (
    ANT_ANIM_FRAME_DIST,
    ANT_CARRY_FOOD_OFFSET,
    BRUSH_PREVIEW_FAINT,
    BRUSH_PREVIEW_WHITE,
    COLONY_COLOR_RGB,
    DRAW_PHEROMONES,
    FOOD_ERASE_SEARCH_RADIUS_PX,
    FOOD_GROW_PER_MS,
    FOOD_SPAWN_INTERVAL_MS,
    MAP_ZOOM_MIN,
    REWARD_CHART_GRID_MINOR_RGB,
    REWARD_CHART_H,
    REWARD_CHART_LABEL_PAD_BOTTOM,
    REWARD_CHART_LABEL_PAD_LEFT,
    REWARD_CHART_MARGIN,
    REWARD_CHART_OVERLAY_BG_RGB,
    REWARD_CHART_W,
    REWARD_CHART_Y_MAX,
    REWARD_CHART_Y_MIN,
    TERRAIN_TUNNEL,
    TERRAIN_WALL,
    WINDOW_HEIGHT,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.pheromone_field import PheromoneField, linear_pheromone_strength
from ants.ui.drawWidgets import draw_colony_invalid_cross
from ants.ui.helpers import (
    clamp_map_pan,
    in_editable,
    is_colony_ground_at_map_pixel,
    map_texel_to_screen,
    world_to_map_screen,
)
from ants.ui import reward_chart_window
from ants.ui.reward_chart_common import (
    format_rel_mmss,
    resolve_reward_chart_x_range,
    series_to_xy,
    value_to_plot_y,
    x_grid_tick_times,
    x_major_label_times,
    y_tick_values,
)
from ants.ui.state import GameState, RuntimeBundle


def _world_dist_to_map_screen_px(panel, dist_world: float) -> int:
    """World-axis distance → screen pixels at zoom 1 (icon scale matches this)."""
    rw = panel.map_rw
    return max(1, int(round(dist_world / WORLD_WIDTH * rw)))


def _scale_surf_for_map_zoom(pg: Any, surf: Any, z: float) -> Any:
    if z <= MAP_ZOOM_MIN + 1e-9:
        return surf
    w, h = surf.get_size()
    nw = max(1, int(round(w * z)))
    nh = max(1, int(round(h * z)))
    return pg.transform.smoothscale(surf, (nw, nh))


def _pheromone_dot_border_rgb(base: tuple[int, int, int]) -> tuple[int, int, int]:
    r, g, b = base
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return (0, 0, 0) if lum > 118.0 else (255, 255, 255)


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


def draw_reward_chart_overlay(pg: Any, bundle: RuntimeBundle, state: GameState) -> None:
    if not state.sim_running or not state.ants:
        return
    if len(state.reward_chart_series) != len(state.ants):
        return
    screen = bundle.screen
    theme = bundle.theme
    font = bundle.font_small
    p = bundle.panel
    y_rng = REWARD_CHART_Y_MAX - REWARD_CHART_Y_MIN
    if y_rng <= 0.0:
        return

    x0 = p.map_rx + REWARD_CHART_MARGIN
    y0 = p.map_ry + REWARD_CHART_MARGIN
    w = min(REWARD_CHART_W, p.map_rw - 2 * REWARD_CHART_MARGIN)
    h = min(REWARD_CHART_H, p.map_rh - 2 * REWARD_CHART_MARGIN)
    if w < 48 or h < 48:
        return

    now_ms = pg.time.get_ticks()
    t_left, t_right = resolve_reward_chart_x_range(state, now_ms)
    span = float(t_right - t_left)
    if span <= 0.0:
        return

    plot_left = float(x0 + REWARD_CHART_LABEL_PAD_LEFT)
    plot_top = float(y0)
    plot_w = max(4.0, float(w - REWARD_CHART_LABEL_PAD_LEFT))
    plot_h = max(4.0, float(h - REWARD_CHART_LABEL_PAD_BOTTOM))

    pg.draw.rect(screen, REWARD_CHART_OVERLAY_BG_RGB, pg.Rect(x0, y0, w, h))
    pg.draw.rect(screen, theme.panel_border, pg.Rect(x0, y0, w, h), width=1)

    for tx in x_grid_tick_times(t_left, t_right):
        sx = int(round(plot_left + (tx - t_left) / span * plot_w))
        if sx < int(plot_left) or sx > int(plot_left + plot_w):
            continue
        pg.draw.line(
            screen,
            REWARD_CHART_GRID_MINOR_RGB,
            (sx, int(plot_top)),
            (sx, int(plot_top + plot_h)),
            width=1,
        )

    for yv in y_tick_values():
        sy = int(round(value_to_plot_y(yv, plot_top, plot_h, REWARD_CHART_Y_MIN, REWARD_CHART_Y_MAX)))
        zline = abs(yv) < 1e-6
        col = theme.muted if zline else REWARD_CHART_GRID_MINOR_RGB
        lw = 2 if zline else 1
        pg.draw.line(
            screen,
            col,
            (int(plot_left), sy),
            (int(plot_left + plot_w), sy),
            width=lw,
        )
        lab = str(int(yv)) if abs(yv - round(yv)) < 1e-6 else str(yv)
        ts = font.render(lab, True, theme.muted)
        screen.blit(ts, (int(plot_left) - ts.get_width() - 3, sy - ts.get_height() // 2))

    for tx in x_major_label_times(t_left, t_right):
        if tx < t_left or tx > t_right:
            continue
        sx = int(round(plot_left + (tx - t_left) / span * plot_w))
        if sx < int(plot_left) - 2 or sx > int(plot_left + plot_w) + 2:
            continue
        txt = format_rel_mmss(tx - t_left)
        ts = font.render(txt, True, theme.muted)
        screen.blit(ts, (sx - ts.get_width() // 2, y0 + h - ts.get_height() - 2))

    for i, ant in enumerate(state.ants):
        series = state.reward_chart_series[i]
        pts_f = series_to_xy(
            series,
            t_left,
            t_right,
            plot_left,
            plot_top,
            plot_w,
            plot_h,
            REWARD_CHART_Y_MIN,
            REWARD_CHART_Y_MAX,
        )
        if len(pts_f) < 2:
            continue
        pts = [(int(round(a)), int(round(b))) for a, b in pts_f]
        cid = (
            state.simulation_colonies[ant.colony_index].color_id
            if 0 <= ant.colony_index < len(state.simulation_colonies)
            else "black"
        )
        rgb = COLONY_COLOR_RGB.get(cid, (128, 128, 128))
        pg.draw.lines(screen, rgb, False, pts, width=1)


def draw_map_view(pg: Any, bundle: RuntimeBundle, state: GameState) -> None:
    screen = bundle.screen
    theme = bundle.theme
    p = bundle.panel
    font_title = bundle.font_title
    rx, ry, rw, rh = p.map_rx, p.map_ry, p.map_rw, p.map_rh
    tw, th = p.map_rw, p.map_rh

    clamp_map_pan(state, p)

    screen.fill((20, 24, 32))
    z = state.map_zoom if (state.sim_running and not state.edit_map) else MAP_ZOOM_MIN
    if z <= MAP_ZOOM_MIN + 1e-9:
        screen.blit(bundle.terrain_surf, (rx, ry))
    else:
        sw_f = tw / z
        sh_f = th / z
        sx0 = int(max(0, min(tw - 1, state.map_pan_x)))
        sy0 = int(max(0, min(th - 1, state.map_pan_y)))
        w_src = max(1, min(tw - sx0, int(round(sw_f))))
        h_src = max(1, min(th - sy0, int(round(sh_f))))
        sub = bundle.terrain_surf.subsurface((sx0, sy0, w_src, h_src))
        scaled = pg.transform.smoothscale(sub, (rw, rh))
        screen.blit(scaled, (rx, ry))
    pg.draw.rect(screen, theme.border_color, (rx, ry, rw, rh), width=2)

    if DRAW_PHEROMONES and state.pheromone is not None:
        ph: PheromoneField = state.pheromone
        now_ms = pg.time.get_ticks()
        overlay = pg.Surface((rw, rh), pg.SRCALPHA)
        pr = max(1, int(round(2 * z)))
        for ci, sc in enumerate(state.simulation_colonies):
            if ci >= ph.colony_count:
                continue
            base = COLONY_COLOR_RGB.get(sc.color_id, (200, 200, 200))
            border = _pheromone_dot_border_rgb(base)
            for ix, iy, _layer, t0, _did in ph.dots[ci]:
                a = linear_pheromone_strength(now_ms, t0)
                if a <= 0.02:
                    continue
                ai = int(a * 255)
                ddx, ddy = map_texel_to_screen(float(ix), float(iy), p, state)
                px, py = int(ddx - rx), int(ddy - ry)
                if 0 <= px < rw and 0 <= py < rh:
                    pg.draw.circle(overlay, (*base, ai), (px, py), pr)
                    pg.draw.circle(overlay, (*border, ai), (px, py), pr, width=1)
        screen.blit(overlay, (rx, ry))

    # Disabled sense-lobe debug circles to keep simulation visuals clear.

    if state.sim_running and state.sim_paused and not state.edit_map:
        overlay = pg.Surface((rw, rh), pg.SRCALPHA)
        overlay.fill((10, 12, 18, 120))
        screen.blit(overlay, (rx, ry))
        paused_txt = font_title.render("Paused", True, theme.text_color)
        screen.blit(paused_txt, paused_txt.get_rect(center=(rx + rw // 2, ry + rh // 2)))

    for fwx, fwy in state.foods:
        fsx, fsy = world_to_map_screen(fwx, fwy, p, state)
        fsx_i, fsy_i = int(fsx), int(fsy)
        if bundle.food_sprite is not None:
            fs = _scale_surf_for_map_zoom(pg, bundle.food_sprite, z)
            fr = fs.get_rect(center=(fsx_i, fsy_i))
            screen.blit(fs, fr)
        else:
            prf = max(1, int(round(2 * z)))
            pg.draw.circle(screen, (72, 180, 96), (fsx_i, fsy_i), prf)

    for sc in state.simulation_colonies:
        if sc.nest_x is None or sc.nest_y is None:
            continue
        nsx, nsy = world_to_map_screen(sc.nest_x, sc.nest_y, p, state)
        nsx_i, nsy_i = int(nsx), int(nsy)
        ns = bundle.colony_sprites.for_color(sc.color_id)
        if ns is not None:
            nsz = _scale_surf_for_map_zoom(pg, ns, z)
            nr = nsz.get_rect(center=(nsx_i, nsy_i))
            screen.blit(nsz, nr)
        else:
            ncr = max(1, int(round(6 * z)))
            pg.draw.circle(
                screen, COLONY_COLOR_RGB.get(sc.color_id, (200, 200, 200)), (nsx_i, nsy_i), ncr, width=2
            )

    for ant in state.ants:
        ax, ay = world_to_map_screen(ant.x, ant.y, p, state)
        cid = (
            state.simulation_colonies[ant.colony_index].color_id
            if 0 <= ant.colony_index < len(state.simulation_colonies)
            else "black"
        )
        frames = (
            bundle.ant_walk_cache.frames_for_color(cid)
            if bundle.ant_walk_cache is not None
            else None
        )
        if frames:
            fi = int(ant.anim_accum / ANT_ANIM_FRAME_DIST) % len(frames)
            base = frames[fi]
            # PNG faces top-of-screen (-y); heading 0 is +x east — extra -90° aligns walk direction.
            img = pg.transform.rotate(base, -math.degrees(ant.heading) - 90.0)
            img = _scale_surf_for_map_zoom(pg, img, z)
            ar = img.get_rect(center=(int(ax), int(ay)))
            screen.blit(img, ar)
        else:
            pra = max(1, int(round(3 * z)))
            pg.draw.circle(screen, (200, 100, 60), (int(ax), int(ay)), pra)
        if ant.carrying:
            # Keep the carry marker visibly in front of the rendered ant sprite.
            base_front_px = _world_dist_to_map_screen_px(p, ANT_CARRY_FOOD_OFFSET) * z
            min_front_px = 6.0 * z
            if frames:
                min_front_px = max(min_front_px, 0.32 * max(ar.width, ar.height))
            front_px = max(base_front_px, min_front_px)
            fx = ax + math.cos(ant.heading) * front_px
            fy = ay + math.sin(ant.heading) * front_px
            if bundle.food_sprite is not None:
                cfs = _scale_surf_for_map_zoom(pg, bundle.food_sprite, z)
                frr = cfs.get_rect(center=(int(fx), int(fy)))
                screen.blit(cfs, frr)
                pg.draw.circle(
                    screen,
                    (255, 255, 255),
                    (int(fx), int(fy)),
                    max(2, int(round(2 * z))),
                    width=1,
                )
            else:
                pg.draw.circle(
                    screen,
                    (72, 180, 96),
                    (int(fx), int(fy)),
                    max(2, int(round(2 * z))),
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

    if not reward_chart_window.is_available():
        draw_reward_chart_overlay(pg, bundle, state)
    pg.draw.line(screen, theme.panel_border, (p.panel_x, 0), (p.panel_x, WINDOW_HEIGHT), width=1)
