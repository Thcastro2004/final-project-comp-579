from typing import Any

from ants.ui.state import UiTheme


def draw_button(
    pygame_mod: Any,
    surf: Any,
    font: Any,
    theme: UiTheme,
    rect: Any,
    label: str,
    hover: bool,
    toggled: bool = False,
) -> None:
    bg = theme.btn_active if toggled else (theme.btn_hover if hover else theme.btn_idle)
    pygame_mod.draw.rect(surf, bg, rect, border_radius=6)
    pygame_mod.draw.rect(surf, theme.panel_border, rect, width=1, border_radius=6)
    t = font.render(label, True, theme.text_color)
    surf.blit(t, t.get_rect(center=rect.center))


def draw_text_field(
    pygame_mod: Any,
    surf: Any,
    font_small: Any,
    theme: UiTheme,
    rect: Any,
    value: str,
    label: str,
    focused: bool,
) -> None:
    pygame_mod.draw.rect(surf, theme.field_bg, rect, border_radius=4)
    w = 2 if focused else 1
    c = theme.field_focus if focused else theme.panel_border
    pygame_mod.draw.rect(surf, c, rect, width=w, border_radius=4)
    lab = font_small.render(label, True, theme.muted)
    surf.blit(lab, (rect.x, rect.y - 16))
    txt = font_small.render(value or " ", True, theme.text_color)
    pad = 6
    surf.blit(txt, (rect.x + pad, rect.centery - txt.get_height() // 2))


def draw_entry_only(
    pygame_mod: Any,
    surf: Any,
    font_small: Any,
    theme: UiTheme,
    rect: Any,
    value: str,
    focused: bool,
) -> None:
    pygame_mod.draw.rect(surf, theme.field_bg, rect, border_radius=4)
    w = 2 if focused else 1
    c = theme.field_focus if focused else theme.panel_border
    pygame_mod.draw.rect(surf, c, rect, width=w, border_radius=4)
    txt = font_small.render(value or " ", True, theme.text_color)
    pad = 5
    surf.blit(txt, (rect.x + pad, rect.centery - txt.get_height() // 2))


def draw_combo_head(
    pygame_mod: Any,
    surf: Any,
    font_small: Any,
    theme: UiTheme,
    rect: Any,
    text: str,
    open_: bool,
    hover: bool,
    lead_rgb: tuple[int, int, int] | None = None,
) -> None:
    bg = theme.btn_hover if hover else theme.field_bg
    pygame_mod.draw.rect(surf, bg, rect, border_radius=6)
    pygame_mod.draw.rect(
        surf, theme.field_focus if open_ else theme.panel_border, rect, width=2 if open_ else 1, border_radius=6
    )
    disp = text if len(text) <= 22 else text[:19] + "…"
    t = font_small.render(disp, True, theme.text_color)
    tx = rect.x + 8
    if lead_rgb is not None:
        pygame_mod.draw.circle(surf, lead_rgb, (rect.x + 11, rect.centery), 6)
        tx = rect.x + 26
    surf.blit(t, (tx, rect.centery - t.get_height() // 2))
    tcx = rect.right - 14
    tcy = rect.centery
    ts = 5
    if open_:
        tri = [(tcx - ts, tcy + ts // 2), (tcx + ts, tcy + ts // 2), (tcx, tcy - ts // 2)]
    else:
        tri = [(tcx - ts, tcy - ts // 2), (tcx + ts, tcy - ts // 2), (tcx, tcy + ts // 2)]
    pygame_mod.draw.polygon(surf, theme.muted, tri)


def draw_colony_invalid_cross(pygame_mod: Any, surf: Any, cx: int, cy: int) -> None:
    arm = 6
    red = (228, 72, 72)
    pygame_mod.draw.line(surf, red, (cx - arm, cy - arm), (cx + arm, cy + arm), 2)
    pygame_mod.draw.line(surf, red, (cx - arm, cy + arm), (cx + arm, cy - arm), 2)


def draw_trash_icon_button(
    pygame_mod: Any,
    surf: Any,
    theme: UiTheme,
    rect: Any,
    hover: bool,
) -> None:
    bg = theme.btn_hover if hover else (56, 60, 76)
    pygame_mod.draw.rect(surf, bg, rect, border_radius=5)
    pygame_mod.draw.rect(surf, theme.panel_border, rect, width=1, border_radius=5)
    tcx, tcy = rect.center
    ic = theme.text_color if hover else (198, 204, 218)
    pygame_mod.draw.line(surf, ic, (tcx - 7, tcy - 5), (tcx + 7, tcy - 5), 2)
    pygame_mod.draw.line(surf, ic, (tcx - 5, tcy - 7), (tcx + 5, tcy - 7), 2)
    pts = [(tcx - 6, tcy - 4), (tcx + 6, tcy - 4), (tcx + 5, tcy + 6), (tcx - 5, tcy + 6)]
    pygame_mod.draw.lines(surf, ic, True, pts, 2)
    pygame_mod.draw.line(surf, ic, (tcx - 3, tcy - 1), (tcx - 3, tcy + 4), 1)
    pygame_mod.draw.line(surf, ic, (tcx, tcy - 1), (tcx, tcy + 4), 1)
    pygame_mod.draw.line(surf, ic, (tcx + 3, tcy - 1), (tcx + 3, tcy + 4), 1)
