"""Tkinter window: per-ant lifetime return vs time (same scale/colors as sim)."""

from __future__ import annotations

import sys
from typing import Any

try:
    import tkinter as tk
except ImportError:
    # Missing _tkinter, wrong arch, or no Tcl/Tk — not fixable via pip; see requirements.txt
    tk = None  # type: ignore[assignment,misc]

from ants.config import (
    COLONY_COLOR_RGB,
    REWARD_CHART_BG_HEX,
    REWARD_CHART_BORDER_HEX,
    REWARD_CHART_GRID_MINOR_HEX,
    REWARD_CHART_H,
    REWARD_CHART_LABEL_PAD_BOTTOM,
    REWARD_CHART_LABEL_PAD_LEFT,
    REWARD_CHART_MARGIN,
    REWARD_CHART_W,
    REWARD_CHART_Y_MAX,
    REWARD_CHART_Y_MIN,
    REWARD_CHART_ZERO_HEX,
)
from ants.ui.reward_chart_common import (
    format_rel_mmss,
    resolve_reward_chart_x_range,
    series_to_xy,
    value_to_plot_y,
    x_grid_tick_times,
    x_major_label_times,
    y_tick_values,
)
from ants.ui.state import GameState

_root: Any = None
_canvas: Any = None
_chart_user_closed: bool = False
_tk_disabled: bool = False


def is_available() -> bool:
    return tk is not None and not _tk_disabled


def _darwin_tk_before_sdl() -> bool:
    return sys.platform == "darwin" and tk is not None


def preinit_before_pygame() -> None:
    """macOS: create Tk before pygame/SDL touch NSApplication (avoids Tcl 9 + SDL crash)."""
    global _root, _canvas, _tk_disabled
    if not _darwin_tk_before_sdl():
        return
    if _root is not None or _tk_disabled:
        return
    try:
        _root = tk.Tk()
        _root.withdraw()
        _root.title("Ant rewards (lifetime return)")
        _canvas = tk.Canvas(
            _root,
            width=REWARD_CHART_W,
            height=REWARD_CHART_H,
            bg=REWARD_CHART_BG_HEX,
            highlightthickness=1,
            highlightbackground=REWARD_CHART_BORDER_HEX,
        )
        _canvas.pack()
        _root.protocol("WM_DELETE_WINDOW", _on_user_close)
        _root.resizable(False, False)
        _root.update_idletasks()
    except Exception:
        _root = None
        _canvas = None
        _tk_disabled = True


def reset_for_new_sim() -> None:
    global _chart_user_closed
    _chart_user_closed = False
    if _root is not None and tk is not None and _darwin_tk_before_sdl():
        try:
            _root.deiconify()
        except tk.TclError:
            pass


def _rgb_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02x}{g:02x}{b:02x}"


def _ensure_window() -> None:
    global _root, _canvas
    if tk is None or _tk_disabled:
        return
    if _chart_user_closed:
        return
    if _root is not None:
        try:
            if _root.winfo_exists():
                return
        except tk.TclError:
            pass
        _root = None
        _canvas = None
    if _darwin_tk_before_sdl():
        return
    _root = tk.Tk()
    _root.title("Ant rewards (lifetime return)")
    _canvas = tk.Canvas(
        _root,
        width=REWARD_CHART_W,
        height=REWARD_CHART_H,
        bg=REWARD_CHART_BG_HEX,
        highlightthickness=1,
        highlightbackground=REWARD_CHART_BORDER_HEX,
    )
    _canvas.pack()
    _root.protocol("WM_DELETE_WINDOW", _on_user_close)
    _root.resizable(False, False)


def _on_user_close() -> None:
    global _root, _canvas, _chart_user_closed
    _chart_user_closed = True
    if _root is None or tk is None:
        return
    try:
        if _darwin_tk_before_sdl():
            _root.withdraw()
        else:
            _root.destroy()
            _root = None
            _canvas = None
    except tk.TclError:
        _root = None
        _canvas = None


def tick(state: GameState, now_ms: int) -> None:
    if tk is None or _tk_disabled:
        return
    if _chart_user_closed:
        return
    try:
        _ensure_window()
    except tk.TclError:
        pass
    if _canvas is not None and _root is not None:
        if _darwin_tk_before_sdl() and _root.wm_state() == "withdrawn":
            try:
                _root.deiconify()
            except tk.TclError:
                pass
        try:
            _canvas.delete("all")
        except tk.TclError:
            pass
        _draw_reward_chart(state, now_ms)

    try:
        if _root is not None:
            _root.update_idletasks()
            _root.update()
    except tk.TclError:
        pass


def _draw_reward_chart(state: GameState, now_ms: int) -> None:
    if _canvas is None:
        return

    mx = REWARD_CHART_MARGIN
    my = REWARD_CHART_MARGIN
    iw = max(8, REWARD_CHART_W - 2 * REWARD_CHART_MARGIN)
    ih = max(8, REWARD_CHART_H - 2 * REWARD_CHART_MARGIN)
    y_rng = REWARD_CHART_Y_MAX - REWARD_CHART_Y_MIN
    if y_rng <= 0.0:
        return

    plot_left = mx + REWARD_CHART_LABEL_PAD_LEFT
    plot_top = my
    plot_w = max(4.0, float(iw - REWARD_CHART_LABEL_PAD_LEFT))
    plot_h = max(4.0, float(ih - REWARD_CHART_LABEL_PAD_BOTTOM))
    t_left, t_right = resolve_reward_chart_x_range(state, now_ms)
    span = float(t_right - t_left)
    if span <= 0.0:
        return

    _canvas.create_rectangle(mx, my, mx + iw, my + ih, outline=REWARD_CHART_BORDER_HEX, width=1)

    axis_font = ("TkDefaultFont", 8)
    for tx in x_grid_tick_times(t_left, t_right):
        sx = plot_left + (tx - t_left) / span * plot_w
        if sx < plot_left or sx > plot_left + plot_w:
            continue
        _canvas.create_line(
            sx, plot_top, sx, plot_top + plot_h, fill=REWARD_CHART_GRID_MINOR_HEX, width=1
        )

    for yv in y_tick_values():
        sy = value_to_plot_y(yv, plot_top, plot_h, REWARD_CHART_Y_MIN, REWARD_CHART_Y_MAX)
        zline = abs(yv) < 1e-6
        _canvas.create_line(
            plot_left,
            sy,
            plot_left + plot_w,
            sy,
            fill=REWARD_CHART_ZERO_HEX if zline else REWARD_CHART_GRID_MINOR_HEX,
            width=2 if zline else 1,
        )
        lab = str(int(yv)) if abs(yv - round(yv)) < 1e-6 else str(yv)
        _canvas.create_text(
            plot_left - 4,
            sy,
            anchor="e",
            text=lab,
            fill=REWARD_CHART_ZERO_HEX,
            font=axis_font,
        )

    for tx in x_major_label_times(t_left, t_right):
        if tx < t_left or tx > t_right:
            continue
        sx = plot_left + (tx - t_left) / span * plot_w
        if sx < plot_left - 1 or sx > plot_left + plot_w + 1:
            continue
        _canvas.create_text(
            sx,
            my + ih - 4,
            anchor="s",
            text=format_rel_mmss(tx - t_left),
            fill=REWARD_CHART_ZERO_HEX,
            font=axis_font,
        )

    if not state.sim_running or not state.ants or len(state.reward_chart_series) != len(state.ants):
        _canvas.create_text(
            plot_left + plot_w * 0.5,
            plot_top + plot_h * 0.5,
            text="Start simulation to plot rewards",
            fill=REWARD_CHART_ZERO_HEX,
            font=("TkDefaultFont", 11),
        )
        try:
            _root.update_idletasks()
            _root.update()
        except tk.TclError:
            pass
        return

    for i, ant in enumerate(state.ants):
        series = state.reward_chart_series[i]
        pts = series_to_xy(
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
        if len(pts) < 2:
            continue
        flat: list[float] = []
        for sx, sy in pts:
            flat.extend([sx, sy])
        cid = (
            state.simulation_colonies[ant.colony_index].color_id
            if 0 <= ant.colony_index < len(state.simulation_colonies)
            else "black"
        )
        rgb = COLONY_COLOR_RGB.get(cid, (128, 128, 128))
        _canvas.create_line(*flat, fill=_rgb_hex(rgb), width=1, smooth=False)


def shutdown() -> None:
    global _root, _canvas, _chart_user_closed
    _chart_user_closed = False
    if _root is not None and tk is not None:
        try:
            _root.destroy()
        except tk.TclError:
            pass
    _root = None
    _canvas = None
