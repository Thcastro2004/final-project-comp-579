from dataclasses import dataclass, field
from typing import Any

from ants.agents import Ant
from ants.models import ColonyBlueprint, SimColony
from ants.pheromone_field import PheromoneField


@dataclass
class DeadWeightGhost:
    colony_index: int
    total_return: float
    weights: list[list[float]]
    died_ms: int


@dataclass
class UiTheme:
    border_color: tuple[int, int, int] = (120, 140, 160)
    panel_bg: tuple[int, int, int] = (24, 28, 38)
    panel_border: tuple[int, int, int] = (55, 62, 78)
    card_bg: tuple[int, int, int] = (34, 38, 50)
    card_border: tuple[int, int, int] = (70, 78, 98)
    btn_idle: tuple[int, int, int] = (52, 58, 76)
    btn_hover: tuple[int, int, int] = (68, 76, 98)
    btn_active: tuple[int, int, int] = (82, 110, 150)
    text_color: tuple[int, int, int] = (230, 232, 238)
    muted: tuple[int, int, int] = (160, 165, 180)
    field_bg: tuple[int, int, int] = (28, 32, 44)
    field_focus: tuple[int, int, int] = (120, 150, 210)


@dataclass
class PanelLayout:
    panel_x: int
    world_w: int
    scroll_rect: Any
    map_rx: int
    map_ry: int
    map_rw: int
    map_rh: int
    map_screen_rect: Any
    editable_inner: Any
    food_r_max_px: float
    nest_pick_r: float
    row1_y: int
    row2_y: int
    btn_h: int
    speed_label_y: int
    speed_row_y: int
    speed_btn_h: int
    col_label_y: int
    add_y: int
    add_btn_h: int
    edit_done_y: int
    edit_brush_y: int


@dataclass
class GameState:
    blueprints: list[ColonyBlueprint] = field(default_factory=list)
    # Shared DQN agent; initialised lazily on first sim_step (avoids importing
    # numpy at module load time when the simulation hasn't started yet).
    dqn_agent: Any | None = None
    simulation_colonies: list[SimColony] = field(default_factory=list)
    foods: list[tuple[float, float]] = field(default_factory=list)
    ants: list[Ant] = field(default_factory=list)
    pheromone: PheromoneField | None = None
    dead_weight_ghosts: list[DeadWeightGhost] = field(default_factory=list)
    sim_running: bool = False
    sim_paused: bool = False
    sim_speed_index: int = 2  # index into SIM_SPEED_PRESETS; default = 1×
    foods_at_run_start: list[tuple[float, float]] = field(default_factory=list)
    edit_map: bool = False
    edit_tool: str = "terrain"
    brush_dropdown_open: bool = False
    food_speed_dropdown_open: bool = False
    brush_radius_index: int = 2
    brush_radius_px: int = 0
    food_speed_index: int = 2
    last_stroke_left: tuple[float, float] | None = None
    last_stroke_right: tuple[float, float] | None = None
    food_press_ms: int = 0
    last_food_spawn_ms: int = 0
    last_food_erase_ms: int = 0
    food_lmb_active: bool = False
    food_rmb_active: bool = False
    colony_scroll: int = 0
    next_custom_id: int = 1
    edit_colony_index: int = 0
    add_modal_open: bool = False
    add_modal_bp_index: int = 0
    new_bp_modal_open: bool = False
    new_bp_name: str = "Custom blueprint"
    new_bp_soldiers_str: str = "0"
    new_bp_fetchers_str: str = "30"
    new_bp_respawn_str: str = "5"
    new_bp_reward_soldier: str = "individualist"
    new_bp_reward_fetcher: str = "individualist"
    focused_field: tuple[int, str] | None = None
    focused_bp_field: str | None = None
    colony_dd: tuple[int, str] | None = None
    running: bool = True
    mouse_xy: tuple[int, int] = (0, 0)
    map_zoom: float = 1.0
    map_pan_x: float = 0.0
    map_pan_y: float = 0.0
    map_dragging: bool = False
    reward_chart_series: list[Any] = field(default_factory=list)
    reward_chart_x_anchor_ms: int | None = None
    reward_chart_x_tail_mode: bool = False
    weight_var_chart_series: list[Any] = field(default_factory=list)
    weight_var_prev_weights: list[list[list[float]]] = field(default_factory=list)
    # Deferred pheromone trail credits: maps id(ant) -> pending float reward.
    # Accumulated when another ant follows that ant's type-A trail; applied
    # to the originating ant on the next sim_step tick.
    phero_pending_credits: dict[int, float] = field(default_factory=dict)
    # One NestPathfinder per colony index; built lazily on first sim_step.
    # Type: dict[int, ants.pathfinder.NestPathfinder]
    nest_pathfinders: dict[int, Any] = field(default_factory=dict)


@dataclass
class RuntimeBundle:
    pygame: Any
    screen: Any
    clock: Any
    font: Any
    font_small: Any
    font_title: Any
    world: Any
    viewport: Any
    terrain_surf: Any
    theme: UiTheme
    panel: PanelLayout
    food_sprite: Any
    food_cursor_sprite: Any
    colony_sprites: Any
    ant_walk_cache: Any | None = None
