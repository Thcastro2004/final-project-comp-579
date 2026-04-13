from typing import Any

from ants.config import (
    BRUSH_RADIUS_PRESETS,
    COLONY_COLOR_RGB,
    PANEL_MARGIN,
    PANEL_WIDTH,
    WINDOW_HEIGHT,
)
from ants.ui.drawWidgets import (
    draw_button,
    draw_combo_head,
    draw_entry_only,
    draw_trash_icon_button,
)
from ants.ui.helpers import colonies_content_height
from ants.ui.layout import colony_card_screen_rect, edit_layout, preset_circle_radius, sim_card_layout
from ants.ui.state import GameState, RuntimeBundle


def draw_panel_and_cards(pg: Any, bundle: RuntimeBundle, state: GameState) -> None:
    screen = bundle.screen
    theme = bundle.theme
    p = bundle.panel
    mx, my = state.mouse_xy
    font = bundle.font
    font_small = bundle.font_small
    font_title = bundle.font_title

    panel_surf = screen.subsurface(pg.Rect(p.panel_x, 0, PANEL_WIDTH, WINDOW_HEIGHT))
    panel_surf.fill(theme.panel_bg)
    plx, ply = mx - p.panel_x, my

    if state.edit_map:
        title = font_title.render("Edit map", True, theme.text_color)
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
        ) = edit_layout(pg, p, state)
        draw_button(pg, panel_surf, font, theme, done_r, "Done", done_r.collidepoint(plx, ply), False)
        draw_button(
            pg,
            panel_surf,
            font,
            theme,
            terrain_tool_r,
            "Brush",
            terrain_tool_r.collidepoint(plx, ply),
            state.edit_tool == "terrain",
        )
        pg.draw.rect(panel_surf, theme.field_bg, terrain_drop_r, border_radius=6)
        pg.draw.rect(
            panel_surf,
            theme.panel_border,
            terrain_drop_r,
            width=2 if state.brush_dropdown_open else 1,
            border_radius=6,
        )
        t_head_dr = preset_circle_radius(state.brush_radius_px, terrain_drop_r.w - 28, terrain_drop_r.h)
        t_head_cx = terrain_drop_r.left + 12 + t_head_dr
        t_head_cy = terrain_drop_r.centery
        pg.draw.circle(panel_surf, theme.text_color, (t_head_cx, t_head_cy), t_head_dr)
        tcx = terrain_drop_r.right - 14
        tcy = terrain_drop_r.centery
        ts = 5
        if state.brush_dropdown_open:
            ttri = [(tcx - ts, tcy + ts // 2), (tcx + ts, tcy + ts // 2), (tcx, tcy - ts // 2)]
        else:
            ttri = [(tcx - ts, tcy - ts // 2), (tcx + ts, tcy - ts // 2), (tcx, tcy + ts // 2)]
        pg.draw.polygon(panel_surf, theme.muted, ttri)
        if state.brush_dropdown_open:
            for i, orr in enumerate(terrain_opt_rects):
                pr = BRUSH_RADIUS_PRESETS[i]
                pg.draw.rect(panel_surf, theme.card_bg, orr, border_radius=4)
                bcol = theme.btn_active if i == state.brush_radius_index else theme.card_border
                pg.draw.rect(panel_surf, bcol, orr, width=2 if i == state.brush_radius_index else 1, border_radius=4)
                show_r = preset_circle_radius(pr, orr.w, orr.h)
                pg.draw.circle(panel_surf, theme.text_color, orr.center, show_r)

        draw_button(
            pg,
            panel_surf,
            font,
            theme,
            food_tool_r,
            "Food",
            food_tool_r.collidepoint(plx, ply),
            state.edit_tool == "food",
        )
        pg.draw.rect(panel_surf, theme.field_bg, food_drop_r, border_radius=6)
        pg.draw.rect(
            panel_surf,
            theme.panel_border,
            food_drop_r,
            width=2 if state.food_speed_dropdown_open else 1,
            border_radius=6,
        )
        spd_txt = font_title.render(str(state.food_speed_index + 1), True, theme.text_color)
        panel_surf.blit(spd_txt, spd_txt.get_rect(center=(food_drop_r.left + 24, food_drop_r.centery)))
        fcx = food_drop_r.right - 14
        fcy = food_drop_r.centery
        fs = 5
        if state.food_speed_dropdown_open:
            ftri = [(fcx - fs, fcy + fs // 2), (fcx + fs, fcy + fs // 2), (fcx, fcy - fs // 2)]
        else:
            ftri = [(fcx - fs, fcy - fs // 2), (fcx + fs, fcy - fs // 2), (fcx, fcy + fs // 2)]
        pg.draw.polygon(panel_surf, theme.muted, ftri)
        if state.food_speed_dropdown_open:
            for i, orr in enumerate(food_opt_rects):
                pg.draw.rect(panel_surf, theme.card_bg, orr, border_radius=4)
                bcf = theme.btn_active if i == state.food_speed_index else theme.card_border
                pg.draw.rect(panel_surf, bcf, orr, width=2 if i == state.food_speed_index else 1, border_radius=4)
                dig = font.render(str(i + 1), True, theme.text_color)
                panel_surf.blit(dig, dig.get_rect(center=orr.center))
        draw_button(
            pg,
            panel_surf,
            font,
            theme,
            colony_tool_r,
            "Colony",
            colony_tool_r.collidepoint(plx, ply),
            state.edit_tool == "colony",
        )
        can_unplace = bool(state.simulation_colonies)
        draw_button(
            pg,
            panel_surf,
            font,
            theme,
            colony_unplace_r,
            "Clear nest",
            colony_unplace_r.collidepoint(plx, ply) and can_unplace,
            False,
        )
        if state.edit_tool == "colony":
            if not state.simulation_colonies:
                hy = colony_tool_r.bottom + 8
                hint = font_small.render("Add colonies in Simulation", True, theme.muted)
                panel_surf.blit(hint, (PANEL_MARGIN, hy))
            else:
                for si, srr in enumerate(colony_sel_rects):
                    active = si == min(state.edit_colony_index, len(state.simulation_colonies) - 1)
                    pg.draw.rect(panel_surf, theme.card_bg, srr, border_radius=4)
                    bcol = theme.btn_active if active else theme.card_border
                    pg.draw.rect(panel_surf, bcol, srr, width=2 if active else 1, border_radius=4)
                    sc = state.simulation_colonies[si]
                    dot_c = COLONY_COLOR_RGB.get(sc.color_id, (128, 128, 128))
                    pg.draw.circle(panel_surf, dot_c, (srr.x + 14, srr.centery), 6)
                    lbl = font_small.render(sc.name[:28], True, theme.text_color)
                    panel_surf.blit(lbl, (srr.x + 28, srr.centery - lbl.get_height() // 2))
    else:
        title = font_title.render("Simulation", True, theme.text_color)
        panel_surf.blit(title, (PANEL_MARGIN, 12))

        row1 = pg.Rect(
            PANEL_MARGIN,
            p.row1_y,
            (PANEL_WIDTH - 3 * PANEL_MARGIN) // 2,
            p.btn_h,
        )
        row1b = pg.Rect(row1.right + PANEL_MARGIN, p.row1_y, row1.width, p.btn_h)
        draw_button(pg, panel_surf, font, theme, row1, "Start", row1.collidepoint(plx, ply), False)
        draw_button(pg, panel_surf, font, theme, row1b, "Pause", row1b.collidepoint(plx, ply), False)
        edit_r = pg.Rect(PANEL_MARGIN, p.row2_y, PANEL_WIDTH - 2 * PANEL_MARGIN, p.btn_h)
        draw_button(pg, panel_surf, font, theme, edit_r, "Edit map", edit_r.collidepoint(plx, ply), False)

        cl = font.render("Colonies", True, theme.text_color)
        panel_surf.blit(cl, (PANEL_MARGIN, p.col_label_y))
        add_rect = pg.Rect(PANEL_MARGIN, p.add_y, PANEL_WIDTH - 2 * PANEL_MARGIN, p.add_btn_h)
        draw_button(pg, panel_surf, font, theme, add_rect, "+ Add colony…", add_rect.collidepoint(plx, ply), False)

    old_clip = screen.get_clip()
    screen.set_clip(p.scroll_rect)
    content_h = colonies_content_height(state)
    if not state.edit_map:
        for i, col in enumerate(state.simulation_colonies):
            card_rect = colony_card_screen_rect(pg, p.scroll_rect, i, state.colony_scroll)
            if card_rect.bottom < p.scroll_rect.top or card_rect.top > p.scroll_rect.bottom:
                continue
            sh = pg.Rect(card_rect.x + 2, card_rect.y + 3, card_rect.w, card_rect.h)
            pg.draw.rect(screen, (12, 14, 20), sh, border_radius=9)
            pg.draw.rect(screen, theme.card_bg, card_rect, border_radius=8)
            pg.draw.rect(screen, theme.card_border, card_rect, width=1, border_radius=8)
            L = sim_card_layout(pg, card_rect)
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
            if isinstance(inner, pg.Rect):
                screen.blit(
                    font_small.render("Name", True, theme.muted),
                    (inner.x, L["lab_name_y"]),
                )
            if isinstance(name_r, pg.Rect):
                fn = state.focused_field == (i, "name")
                draw_entry_only(pg, screen, font_small, theme, name_r, col.name, fn)
            if isinstance(rem_r, pg.Rect):
                draw_trash_icon_button(pg, screen, theme, rem_r, rem_r.collidepoint(mx, my))
            if (
                isinstance(f_s, pg.Rect)
                and isinstance(f_f, pg.Rect)
                and isinstance(f_r, pg.Rect)
                and isinstance(lab_counts_y, int)
            ):
                screen.blit(font_small.render("Soldiers", True, theme.muted), (f_s.x, lab_counts_y))
                screen.blit(font_small.render("Fetchers", True, theme.muted), (f_f.x, lab_counts_y))
                screen.blit(font_small.render("Respawn", True, theme.muted), (f_r.x, lab_counts_y))
                fs = state.focused_field == (i, "soldiers")
                ff = state.focused_field == (i, "fetchers")
                frf = state.focused_field == (i, "respawn")
                draw_entry_only(pg, screen, font_small, theme, f_s, col.soldiers_str, fs)
                draw_entry_only(pg, screen, font_small, theme, f_f, col.fetchers_str, ff)
                draw_entry_only(pg, screen, font_small, theme, f_r, col.respawn_str, frf)
            if isinstance(sol_dd, pg.Rect):
                screen.blit(
                    font_small.render("Soldier behavior", True, theme.muted),
                    (inner.x, sol_dd.y - 16),
                )
                draw_combo_head(
                    pg,
                    screen,
                    font_small,
                    theme,
                    sol_dd,
                    col.reward_soldier,
                    state.colony_dd == (i, "soldier"),
                    sol_dd.collidepoint(mx, my),
                )
            if isinstance(fet_dd, pg.Rect):
                screen.blit(
                    font_small.render("Fetcher behavior", True, theme.muted),
                    (inner.x, fet_dd.y - 16),
                )
                draw_combo_head(
                    pg,
                    screen,
                    font_small,
                    theme,
                    fet_dd,
                    col.reward_fetcher,
                    state.colony_dd == (i, "fetcher"),
                    fet_dd.collidepoint(mx, my),
                )
            if isinstance(col_dd, pg.Rect):
                screen.blit(
                    font_small.render("Colony color", True, theme.muted),
                    (inner.x, col_dd.y - 16),
                )
                ccap = col.color_id.capitalize()
                draw_combo_head(
                    pg,
                    screen,
                    font_small,
                    theme,
                    col_dd,
                    ccap,
                    state.colony_dd == (i, "color"),
                    col_dd.collidepoint(mx, my),
                    COLONY_COLOR_RGB.get(col.color_id, (128, 128, 128)),
                )

        if not state.simulation_colonies:
            empty = font_small.render("No colonies", True, theme.muted)
            screen.blit(empty, (p.scroll_rect.x + 8, p.scroll_rect.y + 6))

    screen.set_clip(old_clip)
