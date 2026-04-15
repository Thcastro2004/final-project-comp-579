"""Ant agent state for fetcher simulation."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from ants.config import RL_FEATURE_DIM, RL_NUM_ACTIONS, RL_WEIGHT_INIT_SCALE


def init_weight_matrix() -> list[list[float]]:
    return [
        [random.uniform(-RL_WEIGHT_INIT_SCALE, RL_WEIGHT_INIT_SCALE) for _ in range(RL_FEATURE_DIM)]
        for _ in range(RL_NUM_ACTIONS)
    ]


@dataclass
class Ant:
    colony_index: int
    x: float
    y: float
    heading: float
    carrying: bool = False
    ever_picked_food: bool = False
    life_start_ms: int = 0
    pickup_ms: int | None = None
    anim_accum: float = 0.0
    phero_stride: float = 0.0
    weights: list[list[float]] = field(default_factory=init_weight_matrix)
    pending_next_action: int | None = None
    reward_ema: float = 0.0
    lifetime_return: float = 0.0
    penalty_near_colony_s: float = 0.0
    penalty_still_s: float = 0.0
    last_alive_bonus_ms: int = 0
    prev_max_wall_frac: float = 0.0
    # Exploration / anti-idle state.
    # The world is split into a coarse grid; we track which cell the ant is in
    # and how long it has been there.  Loitering too long in one cell triggers
    # a growing penalty so ants are pushed to move to new territory.
    exploration_cell: tuple[int, int] = (0, 0)
    time_in_cell_ms: int = 0
    # The angular velocity (rad/s) chosen for the current action window.
    # Sampled randomly in [ANT_TURN_MIN_DEG, ANT_TURN_MAX_DEG] each time a new
    # turn action is chosen; 0.0 for straight-ahead actions.
    current_turn_omega: float = 0.0
    # Action-repeat state: the ant commits to one action for DQN_ACTION_WINDOW_MS
    # milliseconds, then picks a new one.  Using wall-clock ms (not frame count)
    # ensures the intended turn angle is the same regardless of speed multiplier.
    # Rewards accumulate across the window and are pushed as a single experience.
    action_time_left_ms: int = 0
    current_action: int = 0
    # Curiosity: set of grid cells (cx, cy) already visited this life.
    # Gives a one-shot bonus the first time each cell is entered.
    visited_cells: set = field(default_factory=set)
    phi_at_action_start: list[float] = field(default_factory=list)
    pending_reward: float = 0.0
    # Pheromone trail attribution.
    # When this ant senses another ant's type-A pheromone above threshold it
    # records that ant's id() here.  On food pickup the identified ant gets a
    # deferred reward; on death-without-food it gets a small penalty.
    phero_following_id: int | None = None
    # Personal linger circle.
    # The ant carries a rolling "anchor" position.  If it stays within
    # LINGER_ANCHOR_RADIUS of the anchor for > LINGER_PATIENCE_MS it enters
    # a loitering state that suppresses all shaping rewards.  On exit it gets
    # LINGER_EXIT_REWARD and the anchor resets to the current position.
    linger_anchor_x: float = 0.0
    linger_anchor_y: float = 0.0
    linger_since_ms: int = 0
    is_loitering: bool = False

    def nest_xy(self, colonies: list) -> tuple[float, float]:
        c = colonies[self.colony_index]
        return (float(c.nest_x or 0.0), float(c.nest_y or 0.0))

    def reset_at_nest(self, colonies: list, now_ms: int) -> None:
        nx, ny = self.nest_xy(colonies)
        self.x = nx
        self.y = ny
        self.heading = random.uniform(0.0, 2.0 * math.pi)
        self.carrying = False
        self.ever_picked_food = False
        self.life_start_ms = now_ms
        self.pickup_ms = None
        self.anim_accum = 0.0
        self.phero_stride = 0.0
        self.pending_next_action = None
        self.penalty_near_colony_s = 0.0
        self.penalty_still_s = 0.0
        self.last_alive_bonus_ms = now_ms
        self.prev_max_wall_frac = 0.0
        self.exploration_cell = (0, 0)
        self.time_in_cell_ms = 0
        self.current_turn_omega = 0.0
        self.action_time_left_ms = 0
        self.current_action = 0
        self.phi_at_action_start = []
        self.pending_reward = 0.0
        self.visited_cells = set()
        self.phero_following_id = None
        self.linger_anchor_x = nx
        self.linger_anchor_y = ny
        self.linger_since_ms = now_ms
        self.is_loitering = False


def parse_fetcher_count(s: str) -> int:
    try:
        n = int(str(s).strip())
    except (TypeError, ValueError):
        return 0
    return max(0, n)
