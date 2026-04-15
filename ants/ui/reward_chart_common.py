"""Shared time-scaled reward chart geometry (Tk + pygame overlay)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ants.config import (
    REWARD_CHART_X_LABEL_MAJOR_MS,
    REWARD_CHART_X_MINOR_MS,
    REWARD_CHART_X_SCROLL_AT,
    REWARD_CHART_X_SPAN_MS,
    REWARD_CHART_Y_MAX,
    REWARD_CHART_Y_MIN,
    REWARD_CHART_Y_TICK_STEP,
)


def max_sample_time_ms(series_list: list[Any]) -> int:
    m = 0
    for dq in series_list:
        for item in dq:
            if isinstance(item, tuple) and len(item) >= 2:
                m = max(m, int(item[0]))
    return m


def resolve_reward_chart_x_range(state: Any, now_ms: int) -> tuple[int, int]:
    """Sim-anchored window [anchor, anchor+span] until latest sample passes SCROLL_AT*span; then rolling tail."""
    span = REWARD_CHART_X_SPAN_MS
    anchor = state.reward_chart_x_anchor_ms
    thr = int(REWARD_CHART_X_SCROLL_AT * span)

    if anchor is None:
        return int(now_ms) - span, int(now_ms)

    t_data = max_sample_time_ms(state.reward_chart_series)

    if not state.reward_chart_x_tail_mode and t_data >= anchor + thr:
        state.reward_chart_x_tail_mode = True

    if state.reward_chart_x_tail_mode:
        t_right = t_data if t_data > 0 else int(now_ms)
        return t_right - span, t_right

    return int(anchor), int(anchor) + span


def y_tick_values() -> list[float]:
    y0, y1, step = REWARD_CHART_Y_MIN, REWARD_CHART_Y_MAX, REWARD_CHART_Y_TICK_STEP
    out: list[float] = []
    y = y0
    while y <= y1 + 1e-9:
        out.append(y)
        y += step
    return out


def format_rel_mmss(offset_ms: int) -> str:
    s = max(0, int(offset_ms // 1000))
    m, sec = s // 60, s % 60
    return f"{m:d}:{sec:02d}"


def value_to_plot_y(v: float, plot_top: float, plot_h: float, y_min: float, y_max: float) -> float:
    y_rng = y_max - y_min
    if y_rng <= 0.0:
        return plot_top + plot_h * 0.5
    c = max(y_min, min(y_max, v))
    t = (c - y_min) / y_rng
    return plot_top + plot_h - 1 - t * (plot_h - 1)


def series_to_xy(
    series: Iterable[Any],
    t_left: int,
    t_right: int,
    plot_left: float,
    plot_top: float,
    plot_w: float,
    plot_h: float,
    y_min: float,
    y_max: float,
) -> list[tuple[float, float]]:
    span = float(t_right - t_left)
    if span <= 0.0:
        return []
    out: list[tuple[float, float]] = []
    for item in series:
        if not isinstance(item, tuple) or len(item) < 2:
            continue
        t, v = int(item[0]), float(item[1])
        if t < t_left or t > t_right:
            continue
        sx = plot_left + (t - t_left) / span * plot_w
        sy = value_to_plot_y(v, plot_top, plot_h, y_min, y_max)
        out.append((sx, sy))
    return out


def x_grid_tick_times(t_left: int, t_right: int) -> list[int]:
    minor = REWARD_CHART_X_MINOR_MS
    if minor <= 0:
        return []
    out: list[int] = []
    t = t_left
    while t <= t_right:
        out.append(t)
        t += minor
    return out


def x_major_label_times(t_left: int, t_right: int) -> list[int]:
    major = REWARD_CHART_X_LABEL_MAJOR_MS
    if major <= 0:
        return []
    out: list[int] = []
    t = t_left
    while t <= t_right:
        out.append(t)
        t += major
    return out
