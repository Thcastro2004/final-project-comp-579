import math
from typing import Any

from ants.config import (
    BRUSH_RADIUS_PRESETS,
    CARD_GAP,
    CARD_HEIGHT,
    COLONY_COLOR_ORDER,
    MAP_ZOOM_MAX,
    MAP_ZOOM_MIN,
    MAX_SIM_COLONIES,
    PANEL_MARGIN,
    PANEL_WIDTH,
    REWARD_SYSTEMS,
    SIM_SPEED_PRESETS,
    TERRAIN_TUNNEL,
    TERRAIN_WALL,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.models import ColonyBlueprint
from ants.ui.helpers import (
    apply_colony_color,
    apply_map_zoom_wheel,
    clamp_map_pan,
    clamp_scroll,
    cycle_reward,
    food_spawn_burst,
    is_colony_ground_at_map_pixel,
    in_editable,
    map_sim_view_active,
    reset_map_view,
    sim_colony_from_blueprint,
)
from ants.ui.layout import (
    colony_card_screen_rect,
    colony_dd_option_rects,
    layout_add_colony_modal,
    layout_new_blueprint_modal,
    sim_card_layout,
)
from ants.simulation import ensure_pheromone_field
from ants.ui.map_tools import paint_brush_line, save_terrain_and_session
from ants.ui.state import GameState, RuntimeBundle


def process_events(pg: Any, bundle: RuntimeBundle, state: GameState) -> None:
    p = bundle.panel
    panel_x = p.panel_x
    map_rx, map_ry, map_rw, map_rh = p.map_rx, p.map_ry, p.map_rw, p.map_rh
    map_screen_rect = p.map_screen_rect
    nest_pick_r = p.nest_pick_r
    scroll_rect = p.scroll_rect

    for event in pg.event.get():
        if event.type == pg.QUIT:
            save_terrain_and_session(pg, bundle.terrain_surf, state)
            state.running = False
        elif event.type == pg.KEYDOWN and event.key == pg.K_ESCAPE:
            if state.new_bp_modal_open:
                state.new_bp_modal_open = False
                state.focused_bp_field = None
            elif state.add_modal_open:
                state.add_modal_open = False
            elif state.colony_dd is not None:
                state.colony_dd = None
            else:
                save_terrain_and_session(pg, bundle.terrain_surf, state)
                state.running = False
        elif event.type == pg.MOUSEMOTION:
            state.mouse_xy = event.pos
            ex, ey = event.pos
            if state.map_dragging and map_sim_view_active(state):
                relx, rely = event.rel
                z = max(MAP_ZOOM_MIN, min(state.map_zoom, MAP_ZOOM_MAX))
                state.map_pan_x -= relx * (p.map_rw / z) / p.map_rw
                state.map_pan_y -= rely * (p.map_rh / z) / p.map_rh
                clamp_map_pan(state, p)
            pressed = pg.mouse.get_pressed(3)
            if (
                state.edit_map
                and state.edit_tool == "terrain"
                and ex < panel_x
                and map_screen_rect.collidepoint(ex, ey)
            ):
                lx_f = ex - map_rx
                ly_f = ey - map_ry
                if in_editable(lx_f, ly_f, p.editable_inner):
                    if pressed[0] and state.last_stroke_left is not None:
                        ox, oy = state.last_stroke_left
                        paint_brush_line(
                            pg,
                            bundle.terrain_surf,
                            state,
                            p,
                            ox,
                            oy,
                            lx_f,
                            ly_f,
                            state.brush_radius_px,
                            TERRAIN_TUNNEL,
                            step_frac=0.5,
                        )
                        state.last_stroke_left = (lx_f, ly_f)
                    if pressed[2] and state.last_stroke_right is not None:
                        ox, oy = state.last_stroke_right
                        paint_brush_line(
                            pg,
                            bundle.terrain_surf,
                            state,
                            p,
                            ox,
                            oy,
                            lx_f,
                            ly_f,
                            state.brush_radius_px,
                            TERRAIN_WALL,
                            step_frac=0.5,
                        )
                        state.last_stroke_right = (lx_f, ly_f)
        elif event.type == pg.MOUSEBUTTONUP:
            if event.button == 1:
                state.map_dragging = False
                state.last_stroke_left = None
                state.food_lmb_active = False
            elif event.button == 3:
                state.last_stroke_right = None
                state.food_rmb_active = False
        elif event.type == pg.MOUSEWHEEL:
            whx, why = pg.mouse.get_pos()
            if state.add_modal_open and not state.new_bp_modal_open and state.blueprints:
                mrect, *_ = layout_add_colony_modal(pg)
                if mrect.collidepoint(whx, why):
                    nbp = len(state.blueprints)
                    bi = min(state.add_modal_bp_index, nbp - 1)
                    state.add_modal_bp_index = min(max(0, bi - event.y), nbp - 1)
            elif (
                not state.add_modal_open
                and not state.new_bp_modal_open
                and state.colony_dd is None
            ):
                apply_map_zoom_wheel(state, p, event.y, whx, why)
            if (
                not state.edit_map
                and not state.add_modal_open
                and not state.new_bp_modal_open
                and state.colony_dd is None
                and scroll_rect.collidepoint(whx, why)
            ):
                state.colony_scroll -= event.y * 28
                clamp_scroll(state, p)
        elif event.type == pg.MOUSEBUTTONDOWN:
            px, py = event.pos
            plx, ply = px - panel_x, py

            if state.new_bp_modal_open and event.button == 1:
                state.focused_field = None
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
                ) = layout_new_blueprint_modal(pg)
                if can_r.collidepoint(px, py) or not _nbr.collidepoint(px, py):
                    state.new_bp_modal_open = False
                    state.add_modal_open = True
                    state.focused_bp_field = None
                elif save_r.collidepoint(px, py):
                    nm = state.new_bp_name.strip() or "Blueprint"
                    state.blueprints.append(
                        ColonyBlueprint(
                            name=nm,
                            soldiers_str=state.new_bp_soldiers_str,
                            fetchers_str=state.new_bp_fetchers_str,
                            respawn_str=state.new_bp_respawn_str,
                            reward_soldier=state.new_bp_reward_soldier,
                            reward_fetcher=state.new_bp_reward_fetcher,
                        )
                    )
                    state.new_bp_modal_open = False
                    state.add_modal_open = True
                    state.add_modal_bp_index = len(state.blueprints) - 1
                    state.focused_bp_field = None
                elif name_r.collidepoint(px, py):
                    state.focused_bp_field = "name"
                elif sold_r.collidepoint(px, py):
                    state.focused_bp_field = "soldiers"
                elif fetch_r.collidepoint(px, py):
                    state.focused_bp_field = "fetchers"
                elif resp_r.collidepoint(px, py):
                    state.focused_bp_field = "respawn"
                elif rsp.collidepoint(px, py):
                    state.new_bp_reward_soldier = cycle_reward(state.new_bp_reward_soldier, -1)
                elif rsn.collidepoint(px, py):
                    state.new_bp_reward_soldier = cycle_reward(state.new_bp_reward_soldier, 1)
                elif rfp.collidepoint(px, py):
                    state.new_bp_reward_fetcher = cycle_reward(state.new_bp_reward_fetcher, -1)
                elif rfn.collidepoint(px, py):
                    state.new_bp_reward_fetcher = cycle_reward(state.new_bp_reward_fetcher, 1)
                continue

            if state.add_modal_open and event.button == 1:
                state.focused_field = None
                (
                    mrect,
                    close_r,
                    new_bp_r,
                    prev_br,
                    next_br,
                    _bp_card_r,
                    imp_r,
                ) = layout_add_colony_modal(pg)
                nbp = len(state.blueprints)
                bi = min(state.add_modal_bp_index, max(0, nbp - 1))
                if not mrect.collidepoint(px, py):
                    state.add_modal_open = False
                elif close_r.collidepoint(px, py):
                    state.add_modal_open = False
                elif new_bp_r.collidepoint(px, py):
                    state.add_modal_open = False
                    state.new_bp_modal_open = True
                    state.focused_bp_field = None
                elif nbp > 0 and prev_br.collidepoint(px, py) and bi > 0:
                    state.add_modal_bp_index = bi - 1
                elif nbp > 0 and next_br.collidepoint(px, py) and bi < nbp - 1:
                    state.add_modal_bp_index = bi + 1
                elif nbp > 0 and imp_r.collidepoint(px, py):
                    if len(state.simulation_colonies) < MAX_SIM_COLONIES:
                        state.simulation_colonies.append(
                            sim_colony_from_blueprint(state, state.blueprints[bi])
                        )
                        state.next_custom_id += 1
                        clamp_scroll(state, p)
                        state.add_modal_open = False
                continue

            dd_option_picked = False
            if state.colony_dd is not None and event.button == 1 and not state.edit_map:
                ci, dk = state.colony_dd
                if 0 <= ci < len(state.simulation_colonies):
                    cr = colony_card_screen_rect(pg, scroll_rect, ci, state.colony_scroll)
                    L = sim_card_layout(pg, cr)
                    head = (
                        L["sol_dd"]
                        if dk == "soldier"
                        else L["fet_dd"]
                        if dk == "fetcher"
                        else L["col_dd"]
                    )
                    if isinstance(head, pg.Rect):
                        n = len(REWARD_SYSTEMS) if dk != "color" else len(COLONY_COLOR_ORDER)
                        opts = colony_dd_option_rects(pg, head, n)
                        for oi, orr in enumerate(opts):
                            if orr.collidepoint(px, py):
                                c = state.simulation_colonies[ci]
                                if dk == "soldier":
                                    c.reward_soldier = REWARD_SYSTEMS[oi]
                                elif dk == "fetcher":
                                    c.reward_fetcher = REWARD_SYSTEMS[oi]
                                else:
                                    apply_colony_color(state, ci, COLONY_COLOR_ORDER[oi])
                                state.colony_dd = None
                                dd_option_picked = True
                                break
                        if not dd_option_picked:
                            ur = head.copy()
                            for orr in opts:
                                ur = ur.union(orr)
                            if not ur.collidepoint(px, py):
                                state.colony_dd = None
            if dd_option_picked:
                continue

            if px < panel_x:
                state.focused_field = None
                if (
                    map_sim_view_active(state)
                    and map_screen_rect.collidepoint(px, py)
                    and state.map_zoom > MAP_ZOOM_MIN + 1e-6
                    and event.button == 1
                ):
                    state.map_dragging = True
                elif state.edit_map and map_screen_rect.collidepoint(px, py):
                    state.brush_dropdown_open = False
                    state.food_speed_dropdown_open = False
                    lx_f = px - map_rx
                    ly_f = py - map_ry
                    if state.edit_tool == "colony" and event.button == 1:
                        if state.simulation_colonies:
                            best_i = -1
                            best_d = 1e9
                            for i, sc in enumerate(state.simulation_colonies):
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
                                state.edit_colony_index = best_i
                            elif is_colony_ground_at_map_pixel(
                                pg,
                                bundle.terrain_surf,
                                lx_f,
                                ly_f,
                                map_rw,
                                map_rh,
                                p.editable_inner,
                                TERRAIN_TUNNEL,
                                TERRAIN_WALL,
                            ):
                                eci = min(state.edit_colony_index, len(state.simulation_colonies) - 1)
                                sc = state.simulation_colonies[eci]
                                wx = lx_f / map_rw * WORLD_WIDTH
                                wy = ly_f / map_rh * WORLD_HEIGHT
                                sc.nest_x, sc.nest_y = wx, wy
                        continue
                    if in_editable(lx_f, ly_f, p.editable_inner):
                        if state.edit_tool == "terrain" and event.button in (1, 3):
                            if event.button == 1:
                                from ants.ui.map_tools import stamp_brush

                                stamp_brush(
                                    pg,
                                    bundle.terrain_surf,
                                    state,
                                    p,
                                    lx_f,
                                    ly_f,
                                    state.brush_radius_px,
                                    TERRAIN_TUNNEL,
                                )
                                state.last_stroke_left = (lx_f, ly_f)
                            else:
                                from ants.ui.map_tools import stamp_brush

                                stamp_brush(
                                    pg,
                                    bundle.terrain_surf,
                                    state,
                                    p,
                                    lx_f,
                                    ly_f,
                                    state.brush_radius_px,
                                    TERRAIN_WALL,
                                )
                                state.last_stroke_right = (lx_f, ly_f)
                        elif state.edit_tool == "food" and event.button == 1:
                            state.food_lmb_active = True
                            state.food_press_ms = pg.time.get_ticks()
                            food_spawn_burst(
                                pg,
                                bundle.terrain_surf,
                                state,
                                p,
                                lx_f,
                                ly_f,
                                0,
                                TERRAIN_TUNNEL,
                                TERRAIN_WALL,
                            )
                            state.last_food_spawn_ms = state.food_press_ms
                        elif state.edit_tool == "food" and event.button == 3:
                            state.food_rmb_active = True
                            from ants.ui.map_tools import erase_foods_by_proximity

                            erase_foods_by_proximity(state, p, lx_f, ly_f)
                            state.last_food_erase_ms = pg.time.get_ticks()
                continue

            state.focused_field = None
            if state.edit_map:
                from ants.ui.layout import edit_layout

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
                ) = edit_layout(pg, p, state)
                if event.button == 1:
                    if done_r.collidepoint(plx, ply):
                        state.edit_map = False
                        state.brush_dropdown_open = False
                        state.food_speed_dropdown_open = False
                        save_terrain_and_session(pg, bundle.terrain_surf, state)
                    elif terrain_tool_r.collidepoint(plx, ply):
                        state.edit_tool = "terrain"
                        state.food_lmb_active = False
                        state.food_rmb_active = False
                    elif food_tool_r.collidepoint(plx, ply):
                        state.edit_tool = "food"
                        state.food_lmb_active = False
                        state.food_rmb_active = False
                    elif colony_tool_r.collidepoint(plx, ply):
                        state.edit_tool = "colony"
                        state.food_lmb_active = False
                        state.food_rmb_active = False
                    elif colony_unplace_r.collidepoint(plx, ply):
                        if state.simulation_colonies:
                            eci = min(state.edit_colony_index, len(state.simulation_colonies) - 1)
                            state.simulation_colonies[eci].nest_x = None
                            state.simulation_colonies[eci].nest_y = None
                    elif state.edit_tool == "colony":
                        for si, srr in enumerate(colony_sel_rects):
                            if srr.collidepoint(plx, ply):
                                state.edit_colony_index = si
                                break
                    elif terrain_drop_r.collidepoint(plx, ply):
                        state.brush_dropdown_open = not state.brush_dropdown_open
                        state.food_speed_dropdown_open = False
                    elif food_drop_r.collidepoint(plx, ply):
                        state.food_speed_dropdown_open = not state.food_speed_dropdown_open
                        state.brush_dropdown_open = False
                    elif state.brush_dropdown_open:
                        picked = False
                        for i, orr in enumerate(terrain_opt_rects):
                            if orr.collidepoint(plx, ply):
                                state.brush_radius_index = i
                                state.brush_radius_px = BRUSH_RADIUS_PRESETS[i]
                                state.brush_dropdown_open = False
                                picked = True
                                break
                        if not picked:
                            state.brush_dropdown_open = False
                    elif state.food_speed_dropdown_open:
                        picked_f = False
                        for i, orr in enumerate(food_opt_rects):
                            if orr.collidepoint(plx, ply):
                                state.food_speed_index = i
                                state.food_speed_dropdown_open = False
                                picked_f = True
                                break
                        if not picked_f:
                            state.food_speed_dropdown_open = False
                continue

            if event.button != 1:
                continue

            row1 = pg.Rect(
                PANEL_MARGIN,
                p.row1_y,
                (PANEL_WIDTH - 3 * PANEL_MARGIN) // 2,
                p.btn_h,
            )
            row1b = pg.Rect(row1.right + PANEL_MARGIN, p.row1_y, row1.width, p.btn_h)
            edit_r = pg.Rect(PANEL_MARGIN, p.row2_y, PANEL_WIDTH - 2 * PANEL_MARGIN, p.btn_h)
            abs_row1 = row1.move(panel_x, 0)
            abs_row1b = row1b.move(panel_x, 0)
            abs_edit = edit_r.move(panel_x, 0)

            # Check speed selector buttons
            n_spd = len(SIM_SPEED_PRESETS)
            total_gap = (n_spd - 1) * 4
            spd_btn_w = (PANEL_WIDTH - 2 * PANEL_MARGIN - total_gap) // n_spd
            speed_clicked = False
            for si in range(n_spd):
                bx = panel_x + PANEL_MARGIN + si * (spd_btn_w + 4)
                spd_r = pg.Rect(bx, p.speed_row_y, spd_btn_w, p.speed_btn_h)
                if spd_r.collidepoint(px, py):
                    state.sim_speed_index = si
                    speed_clicked = True
                    break

            if speed_clicked:
                pass
            elif abs_row1.collidepoint(px, py):
                if state.sim_running:
                    state.ants.clear()
                    state.reward_chart_series.clear()
                    state.reward_chart_x_anchor_ms = None
                    state.reward_chart_x_tail_mode = False
                    state.foods = list(state.foods_at_run_start)
                    pf = ensure_pheromone_field(state, bundle)
                    if pf is not None:
                        pf.reset()
                    state.sim_running = False
                    state.sim_paused = False
                    reset_map_view(state)
                else:
                    state.foods_at_run_start = list(state.foods)
                    state.sim_paused = False
                    state.sim_running = True
            elif abs_row1b.collidepoint(px, py) and state.sim_running:
                state.sim_paused = not state.sim_paused
            elif abs_edit.collidepoint(px, py):
                state.edit_map = True
                state.colony_dd = None
                reset_map_view(state)
            else:
                add_rect = pg.Rect(
                    panel_x + PANEL_MARGIN,
                    p.add_y,
                    PANEL_WIDTH - 2 * PANEL_MARGIN,
                    p.add_btn_h,
                )
                if add_rect.collidepoint(px, py):
                    state.add_modal_open = True
                    state.add_modal_bp_index = 0
                    state.colony_dd = None
                elif scroll_rect.collidepoint(px, py):
                    rel_y = py - scroll_rect.y + state.colony_scroll
                    idx = int(rel_y // (CARD_HEIGHT + CARD_GAP))
                    if 0 <= idx < len(state.simulation_colonies):
                        card_rect = colony_card_screen_rect(pg, scroll_rect, idx, state.colony_scroll)
                        if card_rect.collidepoint(px, py):
                            L = sim_card_layout(pg, card_rect)
                            rem_r = L["remove"]
                            if isinstance(rem_r, pg.Rect) and rem_r.collidepoint(px, py):
                                del state.simulation_colonies[idx]
                                state.colony_dd = None
                                if state.edit_colony_index >= len(state.simulation_colonies):
                                    state.edit_colony_index = max(0, len(state.simulation_colonies) - 1)
                                clamp_scroll(state, p)
                            else:
                                name_r = L["name"]
                                f_s = L["soldiers"]
                                f_f = L["fetchers"]
                                f_r = L["respawn"]
                                sol_dd = L["sol_dd"]
                                fet_dd = L["fet_dd"]
                                col_dd = L["col_dd"]
                                if isinstance(name_r, pg.Rect) and name_r.collidepoint(px, py):
                                    state.focused_field = (idx, "name")
                                    state.colony_dd = None
                                elif isinstance(f_s, pg.Rect) and f_s.collidepoint(px, py):
                                    state.focused_field = (idx, "soldiers")
                                    state.colony_dd = None
                                elif isinstance(f_f, pg.Rect) and f_f.collidepoint(px, py):
                                    state.focused_field = (idx, "fetchers")
                                    state.colony_dd = None
                                elif isinstance(f_r, pg.Rect) and f_r.collidepoint(px, py):
                                    state.focused_field = (idx, "respawn")
                                    state.colony_dd = None
                                elif isinstance(sol_dd, pg.Rect) and sol_dd.collidepoint(px, py):
                                    state.focused_field = None
                                    if state.colony_dd == (idx, "soldier"):
                                        state.colony_dd = None
                                    else:
                                        state.colony_dd = (idx, "soldier")
                                elif isinstance(fet_dd, pg.Rect) and fet_dd.collidepoint(px, py):
                                    state.focused_field = None
                                    if state.colony_dd == (idx, "fetcher"):
                                        state.colony_dd = None
                                    else:
                                        state.colony_dd = (idx, "fetcher")
                                elif isinstance(col_dd, pg.Rect) and col_dd.collidepoint(px, py):
                                    state.focused_field = None
                                    if state.colony_dd == (idx, "color"):
                                        state.colony_dd = None
                                    else:
                                        state.colony_dd = (idx, "color")

        elif event.type == pg.KEYDOWN:
            if state.new_bp_modal_open and state.focused_bp_field is not None:
                key = event.key
                fbf = state.focused_bp_field
                if fbf == "name":
                    buf = state.new_bp_name
                elif fbf == "soldiers":
                    buf = state.new_bp_soldiers_str
                elif fbf == "fetchers":
                    buf = state.new_bp_fetchers_str
                else:
                    buf = state.new_bp_respawn_str
                if key == pg.K_BACKSPACE:
                    buf = buf[:-1]
                elif key == pg.K_RETURN or key == pg.K_TAB:
                    state.focused_bp_field = None
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
                    state.new_bp_name = buf
                elif fbf == "soldiers":
                    state.new_bp_soldiers_str = buf
                elif fbf == "fetchers":
                    state.new_bp_fetchers_str = buf
                else:
                    state.new_bp_respawn_str = buf
            elif state.focused_field is not None:
                ci, which = state.focused_field
                c = state.simulation_colonies[ci]
                key = event.key
                if which == "name":
                    buf = c.name
                else:
                    buf = {
                        "soldiers": c.soldiers_str,
                        "fetchers": c.fetchers_str,
                        "respawn": c.respawn_str,
                    }[which]
                if key == pg.K_BACKSPACE:
                    buf = buf[:-1]
                elif key == pg.K_RETURN or key == pg.K_TAB:
                    state.focused_field = None
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
