from typing import Any

from ants.config import (
    BLUEPRINT_ARROW_GAP,
    BLUEPRINT_ARROW_W,
    BRUSH_PRESET_GAP,
    CARD_GAP,
    BRUSH_PRESET_MAX,
    BRUSH_PRESET_ROW_H,
    BRUSH_RADIUS_PRESETS,
    CARD_HEIGHT,
    COLONY_CARD_WIDTH,
    COLONY_DD_ROW_H,
    FOOD_SPEED_COUNT,
    PANEL_MARGIN,
    PANEL_WIDTH,
    WINDOW_HEIGHT,
    WINDOW_WIDTH,
)
from ants.ui.state import GameState, PanelLayout


def layout_add_colony_modal(pygame_mod: Any) -> tuple[Any, ...]:
    arrow_w = BLUEPRINT_ARROW_W
    gap = BLUEPRINT_ARROW_GAP
    pad_x = 14
    header_h = 44
    footer_h = 40
    card_w = COLONY_CARD_WIDTH
    mw = pad_x + arrow_w + gap + card_w + gap + arrow_w + pad_x
    mh = header_h + CARD_HEIGHT + 14 + footer_h + 8
    mx = (WINDOW_WIDTH - mw) // 2
    my = (WINDOW_HEIGHT - mh) // 2
    mrect = pygame_mod.Rect(mx, my, mw, mh)
    close_r = pygame_mod.Rect(mx + mw - 34, my + 8, 26, 22)
    cy_card = my + header_h
    btn_h = 44
    prev_r = pygame_mod.Rect(mx + pad_x, cy_card + (CARD_HEIGHT - btn_h) // 2, arrow_w, btn_h)
    card_r = pygame_mod.Rect(prev_r.right + gap, cy_card, card_w, CARD_HEIGHT)
    next_r = pygame_mod.Rect(card_r.right + gap, prev_r.y, arrow_w, btn_h)
    pad = 10
    inner_right = card_r.right - pad
    inner_y = card_r.y + pad
    imp_r = pygame_mod.Rect(inner_right - 80, inner_y + 14, 72, 26)
    new_bp_r = pygame_mod.Rect(mx + pad_x, my + mh - footer_h - 4, mw - 2 * pad_x, 30)
    return mrect, close_r, new_bp_r, prev_r, next_r, card_r, imp_r


def layout_new_blueprint_modal(pygame_mod: Any) -> tuple[Any, ...]:
    mw, mh = 420, 340
    mx = (WINDOW_WIDTH - mw) // 2
    my = (WINDOW_HEIGHT - mh) // 2
    rect = pygame_mod.Rect(mx, my, mw, mh)
    inner_x = mx + 12
    name_r = pygame_mod.Rect(inner_x, my + 44, mw - 24, 26)
    tw = (mw - 32) // 3
    y2 = my + 96
    sold_r = pygame_mod.Rect(inner_x, y2, tw, 26)
    fetch_r = pygame_mod.Rect(sold_r.right + 8, y2, tw, 26)
    resp_r = pygame_mod.Rect(fetch_r.right + 8, y2, tw, 26)
    y3 = my + 140
    rsp = pygame_mod.Rect(inner_x, y3, 28, 24)
    rsn = pygame_mod.Rect(mx + mw - 40, y3, 28, 24)
    y4 = my + 178
    rfp = pygame_mod.Rect(inner_x, y4, 28, 24)
    rfn = pygame_mod.Rect(mx + mw - 40, y4, 28, 24)
    save_r = pygame_mod.Rect(inner_x, my + mh - 44, (mw - 28) // 2 - 4, 32)
    can_r = pygame_mod.Rect(save_r.right + 8, save_r.top, save_r.width, 32)
    return rect, name_r, sold_r, fetch_r, resp_r, rsp, rsn, rfp, rfn, save_r, can_r


def colony_card_screen_rect(pygame_mod: Any, scroll_rect: Any, i: int, colony_scroll: int) -> Any:
    card_top = scroll_rect.y + i * (CARD_HEIGHT + CARD_GAP) - colony_scroll
    card_w = min(COLONY_CARD_WIDTH, scroll_rect.width - 14)
    card_x = scroll_rect.x + (scroll_rect.width - card_w) // 2
    return pygame_mod.Rect(card_x, card_top, card_w, CARD_HEIGHT)


def colony_dd_option_rects(pygame_mod: Any, head: Any, n: int) -> list[Any]:
    return [
        pygame_mod.Rect(head.x, head.bottom + j * COLONY_DD_ROW_H, head.w, COLONY_DD_ROW_H)
        for j in range(n)
    ]


def sim_card_layout(pygame_mod: Any, card_rect: Any) -> dict[str, object]:
    pad = 10
    inner = pygame_mod.Rect(card_rect.x + pad, card_rect.y + pad, card_rect.w - 2 * pad, card_rect.h - 2 * pad)
    y = inner.y
    name_r = pygame_mod.Rect(inner.x, y + 16, inner.w - 40, 22)
    rem_r = pygame_mod.Rect(inner.right - 34, y + 12, 30, 30)
    y += 16 + 22 + 12
    lab_counts_y = y
    third = (inner.w - 16) // 3
    f_s = pygame_mod.Rect(inner.x, y + 14, third, 22)
    f_f = pygame_mod.Rect(f_s.right + 8, y + 14, third, 22)
    f_r = pygame_mod.Rect(f_f.right + 8, y + 14, third, 22)
    y += 14 + 22 + 12
    sol_dd = pygame_mod.Rect(inner.x, y + 14, inner.w, 26)
    y += 14 + 26 + 10
    fet_dd = pygame_mod.Rect(inner.x, y + 14, inner.w, 26)
    y += 14 + 26 + 10
    col_dd = pygame_mod.Rect(inner.x, y + 14, inner.w, 26)
    return {
        "inner": inner,
        "lab_name_y": inner.y,
        "lab_counts_y": lab_counts_y,
        "name": name_r,
        "remove": rem_r,
        "soldiers": f_s,
        "fetchers": f_f,
        "respawn": f_r,
        "sol_dd": sol_dd,
        "fet_dd": fet_dd,
        "col_dd": col_dd,
    }


def edit_layout(pygame_mod: Any, panel: PanelLayout, state: GameState) -> tuple[Any, ...]:
    btn_h = panel.btn_h
    done_r = pygame_mod.Rect(PANEL_MARGIN, panel.edit_done_y, PANEL_WIDTH - 2 * PANEL_MARGIN, btn_h)
    half_w = (PANEL_WIDTH - 3 * PANEL_MARGIN) // 2
    inner_w = PANEL_WIDTH - 2 * PANEL_MARGIN
    y = panel.edit_brush_y
    terrain_tool_r = pygame_mod.Rect(PANEL_MARGIN, y, half_w, btn_h)
    terrain_drop_r = pygame_mod.Rect(terrain_tool_r.right + PANEL_MARGIN, y, half_w, btn_h)
    y += btn_h + 4
    terrain_opt_rects: list[Any] = []
    if state.brush_dropdown_open:
        n = len(BRUSH_RADIUS_PRESETS)
        cell_w = max(1, (inner_w - BRUSH_PRESET_GAP * (n - 1)) // n)
        for i in range(n):
            x = PANEL_MARGIN + i * (cell_w + BRUSH_PRESET_GAP)
            terrain_opt_rects.append(pygame_mod.Rect(x, y, cell_w, BRUSH_PRESET_ROW_H - 2))
        y += BRUSH_PRESET_ROW_H + 4
    y += 6
    food_tool_r = pygame_mod.Rect(PANEL_MARGIN, y, half_w, btn_h)
    food_drop_r = pygame_mod.Rect(food_tool_r.right + PANEL_MARGIN, y, half_w, btn_h)
    y += btn_h + 4
    food_opt_rects: list[Any] = []
    if state.food_speed_dropdown_open:
        n_sp = FOOD_SPEED_COUNT
        cell_w_f = max(1, (inner_w - BRUSH_PRESET_GAP * (n_sp - 1)) // n_sp)
        for i in range(n_sp):
            x = PANEL_MARGIN + i * (cell_w_f + BRUSH_PRESET_GAP)
            food_opt_rects.append(pygame_mod.Rect(x, y, cell_w_f, BRUSH_PRESET_ROW_H - 2))
        y += BRUSH_PRESET_ROW_H + 4
    y += 8
    colony_tool_r = pygame_mod.Rect(PANEL_MARGIN, y, half_w, btn_h)
    colony_unplace_r = pygame_mod.Rect(colony_tool_r.right + PANEL_MARGIN, y, half_w, btn_h)
    y += btn_h + 6
    colony_sel_rects: list[Any] = []
    if state.edit_tool == "colony":
        for i in range(len(state.simulation_colonies)):
            colony_sel_rects.append(pygame_mod.Rect(PANEL_MARGIN, y + i * 30, inner_w, 28))
    return (
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
    )


def preset_circle_radius(preset_r: int, cell_w: int, cell_h: int) -> int:
    cap = min(cell_w, cell_h) // 2 - 3
    cap = max(3, cap)
    return max(2, min(cap, int(round(preset_r * cap / BRUSH_PRESET_MAX))))
