from typing import Any

from ants.config import (
    COLONY_COLOR_ORDER,
    COLONY_COLOR_RGB,
    MAX_SIM_COLONIES,
    REWARD_SYSTEMS,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from ants.ui.drawWidgets import draw_button, draw_combo_head, draw_entry_only, draw_text_field
from ants.ui.helpers import colonies_content_height, first_free_color
from ants.ui.layout import colony_card_screen_rect, colony_dd_option_rects, layout_add_colony_modal, layout_new_blueprint_modal, sim_card_layout
from ants.ui.state import GameState, RuntimeBundle


def draw_modals(pg: Any, bundle: RuntimeBundle, state: GameState) -> None:
    screen = bundle.screen
    theme = bundle.theme
    p = bundle.panel
    mx, my = state.mouse_xy
    font = bundle.font
    font_small = bundle.font_small
    font_title = bundle.font_title

    content_h = colonies_content_height(state)

    if not state.edit_map and state.colony_dd is not None:
        ci, dk = state.colony_dd
        if 0 <= ci < len(state.simulation_colonies):
            cr = colony_card_screen_rect(pg, p.scroll_rect, ci, state.colony_scroll)
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
                if opts:
                    big = opts[0].copy()
                    for orr in opts[1:]:
                        big = big.union(orr)
                    big = big.inflate(4, 4)
                    shad = pg.Surface((big.w, big.h), pg.SRCALPHA)
                    shad.fill((0, 0, 0, 80))
                    screen.blit(shad, (big.x + 2, big.y + 4))
                    pg.draw.rect(screen, (32, 36, 48), big, border_radius=6)
                    pg.draw.rect(screen, theme.panel_border, big, width=1, border_radius=6)
                panel_fill = (32, 36, 48)
                for oi, orr in enumerate(opts):
                    hov = orr.collidepoint(mx, my)
                    pg.draw.rect(
                        screen,
                        theme.btn_hover if hov else panel_fill,
                        orr.inflate(-1, -1),
                        border_radius=4,
                    )
                    if dk == "color":
                        cid = COLONY_COLOR_ORDER[oi]
                        pg.draw.circle(
                            screen,
                            COLONY_COLOR_RGB[cid],
                            (orr.x + 12, orr.centery),
                            6,
                        )
                        tt = font_small.render(cid.capitalize(), True, theme.text_color)
                        screen.blit(tt, (orr.x + 24, orr.centery - tt.get_height() // 2))
                    else:
                        tt = font_small.render(REWARD_SYSTEMS[oi], True, theme.text_color)
                        screen.blit(tt, (orr.x + 8, orr.centery - tt.get_height() // 2))

    if not state.edit_map and content_h > p.scroll_rect.height:
        bar_h = max(20, int(p.scroll_rect.height * p.scroll_rect.height / content_h))
        max_scroll = content_h - p.scroll_rect.height
        t = state.colony_scroll / max_scroll if max_scroll > 0 else 0.0
        by = p.scroll_rect.y + int(t * (p.scroll_rect.height - bar_h))
        bar = pg.Rect(p.scroll_rect.right - 5, by, 4, bar_h)
        pg.draw.rect(screen, (80, 88, 108), bar, border_radius=2)

    if state.add_modal_open:
        ov = pg.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pg.SRCALPHA)
        ov.fill((0, 0, 0, 130))
        screen.blit(ov, (0, 0))
        (
            mrect,
            close_r,
            new_bp_r,
            prev_br,
            next_br,
            card_r,
            imp_r,
        ) = layout_add_colony_modal(pg)
        pg.draw.rect(screen, theme.card_bg, mrect, border_radius=12)
        pg.draw.rect(screen, theme.panel_border, mrect, width=2, border_radius=12)
        draw_button(pg, screen, font, theme, close_r, "×", close_r.collidepoint(mx, my), False)
        screen.blit(
            font_title.render("Add colony from blueprint", True, theme.text_color),
            (mrect.x + 16, mrect.y + 10),
        )
        if len(state.simulation_colonies) >= MAX_SIM_COLONIES:
            full = font_small.render(f"Maximum {MAX_SIM_COLONIES} colonies", True, theme.muted)
            screen.blit(full, (mrect.x + 16, mrect.y + 34))
        at_cap = len(state.simulation_colonies) >= MAX_SIM_COLONIES
        nbp = len(state.blueprints)
        bi = min(state.add_modal_bp_index, max(0, nbp - 1))
        dim_arrow = (100, 105, 120)
        if bi > 0:
            draw_button(pg, screen, font, theme, prev_br, "<", prev_br.collidepoint(mx, my), False)
        else:
            pg.draw.rect(screen, (40, 44, 56), prev_br, border_radius=6)
            pg.draw.rect(screen, theme.panel_border, prev_br, width=1, border_radius=6)
            tp = font.render("<", True, dim_arrow)
            screen.blit(tp, tp.get_rect(center=prev_br.center))
        if nbp > 0 and bi < nbp - 1:
            draw_button(pg, screen, font, theme, next_br, ">", next_br.collidepoint(mx, my), False)
        else:
            pg.draw.rect(screen, (40, 44, 56), next_br, border_radius=6)
            pg.draw.rect(screen, theme.panel_border, next_br, width=1, border_radius=6)
            tn = font.render(">", True, dim_arrow)
            screen.blit(tn, tn.get_rect(center=next_br.center))
        if nbp > 0:
            bp = state.blueprints[bi]
            sh = pg.Rect(card_r.x + 2, card_r.y + 3, card_r.w, card_r.h)
            pg.draw.rect(screen, (12, 14, 20), sh, border_radius=9)
            pg.draw.rect(screen, theme.card_bg, card_r, border_radius=8)
            pg.draw.rect(screen, theme.card_border, card_r, width=1, border_radius=8)
            L = sim_card_layout(pg, card_r)
            inner = L["inner"]
            if isinstance(inner, pg.Rect):
                screen.blit(
                    font_small.render("Name", True, theme.muted),
                    (inner.x, L["lab_name_y"]),
                )
            name_r = L["name"]
            if isinstance(name_r, pg.Rect):
                nw = max(28, inner.w - 86) if isinstance(inner, pg.Rect) else name_r.w
                name_clip = pg.Rect(name_r.x, name_r.y, nw, name_r.height)
                draw_entry_only(pg, screen, font_small, theme, name_clip, bp.name, False)
            f_s = L["soldiers"]
            f_f = L["fetchers"]
            f_r = L["respawn"]
            lab_counts_y = L["lab_counts_y"]
            if (
                isinstance(f_s, pg.Rect)
                and isinstance(f_f, pg.Rect)
                and isinstance(f_r, pg.Rect)
                and isinstance(lab_counts_y, int)
            ):
                screen.blit(font_small.render("Soldiers", True, theme.muted), (f_s.x, lab_counts_y))
                screen.blit(font_small.render("Fetchers", True, theme.muted), (f_f.x, lab_counts_y))
                screen.blit(font_small.render("Respawn", True, theme.muted), (f_r.x, lab_counts_y))
                draw_entry_only(pg, screen, font_small, theme, f_s, bp.soldiers_str, False)
                draw_entry_only(pg, screen, font_small, theme, f_f, bp.fetchers_str, False)
                draw_entry_only(pg, screen, font_small, theme, f_r, bp.respawn_str, False)
            sol_dd = L["sol_dd"]
            fet_dd = L["fet_dd"]
            col_dd = L["col_dd"]
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
                    bp.reward_soldier,
                    False,
                    False,
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
                    bp.reward_fetcher,
                    False,
                    False,
                )
            if isinstance(col_dd, pg.Rect):
                screen.blit(
                    font_small.render("Colony color", True, theme.muted),
                    (inner.x, col_dd.y - 16),
                )
                cid = first_free_color(state)
                draw_combo_head(
                    pg,
                    screen,
                    font_small,
                    theme,
                    col_dd,
                    cid.capitalize(),
                    False,
                    False,
                    COLONY_COLOR_RGB.get(cid, (128, 128, 128)),
                )
            if at_cap:
                pg.draw.rect(screen, (40, 44, 56), imp_r, border_radius=6)
                pg.draw.rect(screen, theme.panel_border, imp_r, width=1, border_radius=6)
                ti = font_small.render("Import", True, dim_arrow)
                screen.blit(ti, ti.get_rect(center=imp_r.center))
            else:
                draw_button(pg, screen, font, theme, imp_r, "Import", imp_r.collidepoint(mx, my), False)
        else:
            pg.draw.rect(screen, (12, 14, 20), card_r, border_radius=9)
            pg.draw.rect(screen, theme.card_bg, card_r, border_radius=8)
            pg.draw.rect(screen, theme.card_border, card_r, width=1, border_radius=8)
            nb = font_small.render("No blueprints", True, theme.muted)
            screen.blit(nb, nb.get_rect(center=card_r.center))
        draw_button(pg, screen, font, theme, new_bp_r, "New blueprint…", new_bp_r.collidepoint(mx, my), False)

    if state.new_bp_modal_open:
        ov2 = pg.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pg.SRCALPHA)
        ov2.fill((0, 0, 0, 130))
        screen.blit(ov2, (0, 0))
        (
            nbr,
            nb_name_r,
            nb_sold_r,
            nb_fetch_r,
            nb_resp_r,
            nb_rsp,
            nb_rsn,
            nb_rfp,
            nb_rfn,
            nb_save_r,
            nb_can_r,
        ) = layout_new_blueprint_modal(pg)
        pg.draw.rect(screen, theme.card_bg, nbr, border_radius=10)
        pg.draw.rect(screen, theme.panel_border, nbr, width=2, border_radius=10)
        screen.blit(font_title.render("New blueprint", True, theme.text_color), (nbr.x + 16, nbr.y + 10))
        draw_text_field(
            pg,
            screen,
            font_small,
            theme,
            nb_name_r,
            state.new_bp_name,
            "Name",
            state.focused_bp_field == "name",
        )
        draw_text_field(
            pg,
            screen,
            font_small,
            theme,
            nb_sold_r,
            state.new_bp_soldiers_str,
            "Soldiers",
            state.focused_bp_field == "soldiers",
        )
        draw_text_field(
            pg,
            screen,
            font_small,
            theme,
            nb_fetch_r,
            state.new_bp_fetchers_str,
            "Fetchers",
            state.focused_bp_field == "fetchers",
        )
        draw_text_field(
            pg,
            screen,
            font_small,
            theme,
            nb_resp_r,
            state.new_bp_respawn_str,
            "Respawn",
            state.focused_bp_field == "respawn",
        )
        draw_button(pg, screen, font, theme, nb_rsp, "<", nb_rsp.collidepoint(mx, my), False)
        draw_button(pg, screen, font, theme, nb_rsn, ">", nb_rsn.collidepoint(mx, my), False)
        st = font_small.render(state.new_bp_reward_soldier, True, theme.muted)
        screen.blit(st, st.get_rect(center=((nb_rsp.right + nb_rsn.left) // 2, nb_rsp.centery)))
        screen.blit(font_small.render("Soldier rw", True, theme.muted), (nbr.x + 16, nb_rsp.y - 14))
        draw_button(pg, screen, font, theme, nb_rfp, "<", nb_rfp.collidepoint(mx, my), False)
        draw_button(pg, screen, font, theme, nb_rfn, ">", nb_rfn.collidepoint(mx, my), False)
        ft = font_small.render(state.new_bp_reward_fetcher, True, theme.muted)
        screen.blit(ft, ft.get_rect(center=((nb_rfp.right + nb_rfn.left) // 2, nb_rfp.centery)))
        screen.blit(font_small.render("Fetcher rw", True, theme.muted), (nbr.x + 16, nb_rfp.y - 14))
        draw_button(pg, screen, font, theme, nb_save_r, "Save", nb_save_r.collidepoint(mx, my), False)
        draw_button(pg, screen, font, theme, nb_can_r, "Cancel", nb_can_r.collidepoint(mx, my), False)
