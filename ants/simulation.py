"""Simulation step: fetcher kinematics, sensing, SARSA, pheromones, death/respawn."""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Any

from ants.agents import Ant, parse_fetcher_count
from ants.config import (
    ANT_FOOD_PICKUP_R,
    ANT_SPEED,
    D_REF,
    DQN_ACTION_REPEAT,
    DQN_ACTION_WINDOW_MS,
    TURN_MAGNITUDES,
    EXPLORATION_GRID_N,
    GHOST_WEIGHT_TTL_MS,
    LINGER_ANCHOR_RADIUS,
    LINGER_EXIT_REWARD,
    LINGER_LOITER_PENALTY_PER_S,
    LINGER_PATIENCE_MS,
    NEAR_COLONY_NO_FOOD_RADIUS,
    PATHFINDER_GRID_N,
    PHERO_FOLLOW_THRESHOLD,
    PHERO_WARNING_FOOD_RADIUS,
    PHEROMONE_DOT_INTERVAL,
    POTENTIAL_DIST_CAP_FRAC,
    REWARD_DEATH,
    REWARD_DEPOSIT,
    REWARD_EFFICIENCY_BONUS,
    REWARD_FOOD_LOBE_CENTER,
    REWARD_FOOD_LOBE_SIDE,
    REWARD_HEADING_TOWARD_NEST,
    REWARD_HOME_DIST,
    REWARD_HOMEWARD_SHAPING,
    REWARD_NEW_CELL_VISIT,
    REWARD_OUTWARD_SHAPING,
    REWARD_PATH_DIST_SHAPING,
    REWARD_PATH_HEADING,
    REWARD_PHERO_LED_TO_FOOD,
    REWARD_PHERO_MISLED,
    REWARD_PHERO_WARNING_CORRECT,
    REWARD_PHERO_WARNING_WRONG,
    REWARD_PICKUP,
    REWARD_POTENTIAL_FOOD,
    REWARD_POTENTIAL_NEST,
    REWARD_CHART_MAX_POINTS,
    REWARD_STEP_NO_FOOD,
    REWARD_STILL_PER_S,
    REWARD_WALL_APPROACH_FRAC,
    REWARD_WALL_BLOCKED_SEEN,
    REWARD_WALL_THREAT_CLEAR,
    RESPAWN_BLEND_LAMBDA,
    RL_FEATURE_DIM,
    RL_GAMMA,
    RL_NUM_ACTIONS,
    RL_REWARD_EMA_BETA,
    STILL_MOVE_DIST_THRESHOLD,
    TIMEOUT_FIND_FOOD_MS,
    TIMEOUT_RETURN_FOOD_MS,
    WALL_THREAT_MIN,
    WORLD_HEIGHT,
    WORLD_WIDTH,
)
from ants.pathfinder import NestPathfinder
from ants.models import SimColony
from ants.pheromone_field import PheromoneField
from ants.dqn_fetcher import DQNAgent
from ants.rl_fetcher import (
    average_weights,
    decode_action,
)
from ants.sensing import build_phi, phi_for_terminal
from ants.ui.helpers import is_tunnel_at_world
from ants.ui.state import DeadWeightGhost, GameState, RuntimeBundle


def _copy_weight_matrix(w: list[list[float]]) -> list[list[float]]:
    return [[w[a][i] for i in range(len(w[a]))] for a in range(len(w))]


def _cull_ghosts(state: GameState, now_ms: int) -> None:
    ttl = GHOST_WEIGHT_TTL_MS
    state.dead_weight_ghosts = [g for g in state.dead_weight_ghosts if now_ms - g.died_ms <= ttl]


# def _squared_time_penalty_increment(t_accum: float, dt_s: float) -> tuple[float, float]:
#     t1 = t_accum + dt_s
#     return -(t1 * t1 - t_accum * t_accum), t1


def _nearest_food_dist(ax: float, ay: float, foods: list[tuple[float, float]]) -> float | None:
    if not foods:
        return None
    best = float("inf")
    for fx, fy in foods:
        dx, dy = fx - ax, fy - ay
        d = math.hypot(dx, dy)
        if d < best:
            best = d
    return best


def _phi_potential(
    ax: float,
    ay: float,
    carrying: bool,
    foods: list[tuple[float, float]],
    nest_x: float | None,
    nest_y: float | None,
) -> float:
    cap = POTENTIAL_DIST_CAP_FRAC * D_REF
    if carrying:
        if nest_x is None or nest_y is None:
            return 0.0
        d = min(math.hypot(ax - nest_x, ay - nest_y), cap)
        return -REWARD_POTENTIAL_NEST * (d / D_REF)
    d_nearest = _nearest_food_dist(ax, ay, foods)
    if d_nearest is None:
        return 0.0
    d = min(d_nearest, cap)
    return -REWARD_POTENTIAL_FOOD * (d / D_REF)


def _potential_shaping_reward(
    x0: float,
    y0: float,
    carrying0: bool,
    foods0: list[tuple[float, float]],
    x1: float,
    y1: float,
    carrying1: bool,
    foods1: list[tuple[float, float]],
    nest_x: float | None,
    nest_y: float | None,
) -> float:
    phi_s = _phi_potential(x0, y0, carrying0, foods0, nest_x, nest_y)
    phi_sp = _phi_potential(x1, y1, carrying1, foods1, nest_x, nest_y)
    return RL_GAMMA * phi_sp - phi_s


def _max_wall_frac_phi(phi2: list[float]) -> float:
    if len(phi2) < 23:
        return 0.0
    return max(phi2[6], phi2[14], phi2[22])


def _delayed_wall_threat_clear_reward(
    ant: Ant,
    phi2: list[float],
    move_dist: float,
    blocked: bool,
) -> float:
    """One-shot bonus when last step had high wall in lobes and now sensors are clear after real motion."""
    w_end = _max_wall_frac_phi(phi2)
    if ant.prev_max_wall_frac < WALL_THREAT_MIN:
        return 0.0
    if w_end >= WALL_THREAT_MIN:
        return 0.0
    if move_dist < STILL_MOVE_DIST_THRESHOLD:
        return 0.0
    if blocked:
        return 0.0
    return REWARD_WALL_THREAT_CLEAR


def _carry_home_shaping(ant: Ant, sc: SimColony) -> float:
    if not ant.carrying or sc.nest_x is None or sc.nest_y is None:
        return 0.0
    dist = math.hypot(ant.x - sc.nest_x, ant.y - sc.nest_y)
    d_norm = min(1.0, dist / D_REF)
    return REWARD_HOME_DIST * (1.0 - d_norm)


def _outward_from_nest_shaping(
    carrying: bool,
    nest_x: float | None,
    nest_y: float | None,
    dist_before: float,
    dist_after: float,
) -> float:
    if carrying or nest_x is None or nest_y is None:
        return 0.0
    dd = dist_after - dist_before
    if dd <= 0.0:
        return 0.0
    return REWARD_OUTWARD_SHAPING * (dd / D_REF)


def _homeward_delta_shaping(
    carrying: bool,
    nest_x: float | None,
    nest_y: float | None,
    dist_before: float,
    dist_after: float,
) -> float:
    """Mirror of _outward_from_nest_shaping for the return trip.

    Gives a per-step reward proportional to how many world-units the ant
    moved *toward* the nest this frame while carrying food.  This is the
    explicit "come home" signal the ant needs to learn that depositing food
    matters and that the shortest path home is valuable.
    """
    if not carrying or nest_x is None or nest_y is None:
        return 0.0
    dd = dist_before - dist_after   # positive when closer to nest than before
    if dd <= 0.0:
        return 0.0
    return REWARD_HOMEWARD_SHAPING * (dd / D_REF)


def _linger_penalties(
    ant: Ant,
    sc: SimColony,
    move_dist: float,
    dt_s: float,
    blocked: bool = False,
    forward_wall_frac: float = 0.0,
) -> float:
    r = 0.0
    if (
        not ant.carrying
        and sc.nest_x is not None
        and sc.nest_y is not None
        and math.hypot(ant.x - sc.nest_x, ant.y - sc.nest_y) <= NEAR_COLONY_NO_FOOD_RADIUS
    ):
        r -= REWARD_NEAR_NEST_PER_S * dt_s
    else:
        ant.penalty_near_colony_s = 0.0

    if move_dist < STILL_MOVE_DIST_THRESHOLD:
        if blocked and forward_wall_frac >= WALL_THREAT_MIN:
            # The ant could see the wall in its forward lobe but moved into it
            # anyway.  Penalise the wall collision directly — not generic
            # stillness — so the reward signal is correctly attributed.
            r -= REWARD_WALL_BLOCKED_SEEN * dt_s
        else:
            # Genuinely idle (not wall-blocked), or wall was out of sensor range.
            r -= REWARD_STILL_PER_S * dt_s
    else:
        ant.penalty_still_s = 0.0
    return r


def _exploration_linger_penalty(ant: Ant, dt_ms: int, dt_s: float) -> float:
    """Penalise staying in the same map cell for too long.

    The world is divided into EXPLORATION_GRID_N × EXPLORATION_GRID_N cells.
    Each cell is ~280 × 240 world units at default map size.  Once an ant has
    been inside the same cell longer than EXPLORATION_LINGER_THRESHOLD_MS it
    receives a per-second penalty — discouraging circular movement and
    rewarding genuine territorial exploration.
    """
    cell_w = WORLD_WIDTH / EXPLORATION_GRID_N
    cell_h = WORLD_HEIGHT / EXPLORATION_GRID_N
    cx = int(min(ant.x / cell_w, EXPLORATION_GRID_N - 1))
    cy = int(min(ant.y / cell_h, EXPLORATION_GRID_N - 1))
    cell = (cx, cy)

    if cell == ant.exploration_cell:
        ant.time_in_cell_ms += dt_ms
    else:
        # Moved to a new cell — reset the clock.
        ant.exploration_cell = cell
        ant.time_in_cell_ms = 0
        return 0.0

    over_ms = ant.time_in_cell_ms - EXPLORATION_LINGER_THRESHOLD_MS
    if over_ms <= 0:
        return 0.0
    return -EXPLORATION_LINGER_PENALTY_PER_S * dt_s


def _alive_interval_bonus(ant: Ant, now_ms: int) -> float:
    if now_ms - ant.last_alive_bonus_ms < ALIVE_BONUS_EVERY_MS:
        return 0.0
    n = (now_ms - ant.last_alive_bonus_ms) // ALIVE_BONUS_EVERY_MS
    ant.last_alive_bonus_ms += int(n * ALIVE_BONUS_EVERY_MS)
    return REWARD_ALIVE_BONUS * n


def _food_lobe_reward(ant: Ant, phi: list[float], dt_s: float) -> float:
    """Per-second reward when food is visible in the sensing lobes (not carrying).

    Feature layout inside phi (6 global + 3 lobes × 8 each):
      [0]=bias [1]=carry [2]=x [3]=y [4]=nest_x [5]=nest_y
      lobe 0 (center):  [6]=wall [7]=food ...
      lobe 1 (left):   [14]=wall [15]=food ...
      lobe 2 (right):  [22]=wall [23]=food ...
    Center gets a higher reward so the ant learns to orient toward food.
    """
    if ant.carrying or len(phi) < 24:
        return 0.0
    center_food = phi[7]
    side_food = max(phi[15], phi[23])
    if center_food > 0.5:
        return REWARD_FOOD_LOBE_CENTER * dt_s
    if side_food > 0.5:
        return REWARD_FOOD_LOBE_SIDE * dt_s
    return 0.0


def _curiosity_reward(ant: Ant) -> float:
    """One-shot bonus the first time the ant enters a new map grid cell.

    Uses the same grid as _exploration_linger_penalty so the coordinate
    arithmetic is consistent.  The bonus is given only once per cell per life
    and resets on respawn, encouraging persistent territorial expansion.
    """
    cell_w = WORLD_WIDTH / EXPLORATION_GRID_N
    cell_h = WORLD_HEIGHT / EXPLORATION_GRID_N
    cx = int(min(ant.x / cell_w, EXPLORATION_GRID_N - 1))
    cy = int(min(ant.y / cell_h, EXPLORATION_GRID_N - 1))
    cell = (cx, cy)
    if cell not in ant.visited_cells:
        ant.visited_cells.add(cell)
        return REWARD_NEW_CELL_VISIT
    return 0.0


def _wall_approach_penalty(forward_wall_frac: float, dt_s: float) -> float:
    """Continuous penalty proportional to how much wall is in the forward lobe.

    Unlike REWARD_WALL_BLOCKED_SEEN (which only fires on collision), this gives
    a smooth repulsion gradient *before* the ant hits the wall.  The penalty is
    only non-zero when the forward lobe contains wall pixels.
    """
    if forward_wall_frac <= 0.0:
        return 0.0
    return -REWARD_WALL_APPROACH_FRAC * forward_wall_frac * dt_s


def _heading_toward_nest_bonus(ant: Ant, sc: SimColony, dt_s: float) -> float:
    """Per-second reward scaled by cos(angle between heading and direction to nest).

    Applied only when carrying food.  Full reward when pointing straight at the
    nest; zero reward perpendicular; negative reward when pointing away.
    This gives a directional gradient that complements the distance-based
    homeward delta shaping.
    """
    if not ant.carrying or sc.nest_x is None or sc.nest_y is None:
        return 0.0
    dx = sc.nest_x - ant.x
    dy = sc.nest_y - ant.y
    d = math.hypot(dx, dy)
    if d < 1.0:
        return 0.0
    nest_angle = math.atan2(dy, dx)
    diff = ant.heading - nest_angle
    # Normalise to [-π, π]
    diff = (diff + math.pi) % (2.0 * math.pi) - math.pi
    return REWARD_HEADING_TOWARD_NEST * math.cos(diff) * dt_s


# ---------------------------------------------------------------------------
# Personal linger circle
# ---------------------------------------------------------------------------

def _linger_circle_update(ant: Ant, now_ms: int, dt_s: float) -> tuple[float, float, bool]:
    """Manage the ant's rolling patience circle.

    Returns ``(linger_penalty, exit_reward, is_loitering)``.

    Logic:
    • If the ant is within LINGER_ANCHOR_RADIUS of its anchor:
        – Once it has been there > LINGER_PATIENCE_MS it enters loitering state.
        – While loitering: return a per-second penalty and is_loitering=True.
    • If the ant has moved outside the radius:
        – If it was loitering, give LINGER_EXIT_REWARD (escape bonus).
        – Reset the anchor to the current position and restart the clock.
        – is_loitering=False.

    The anchor starts at the nest on spawn (see reset_at_nest) and rolls forward
    to each exit point, so ants must make *real* territorial progress.
    """
    dx = ant.x - ant.linger_anchor_x
    dy = ant.y - ant.linger_anchor_y
    in_circle = (dx * dx + dy * dy) <= LINGER_ANCHOR_RADIUS * LINGER_ANCHOR_RADIUS

    if in_circle:
        elapsed = now_ms - ant.linger_since_ms
        if elapsed > LINGER_PATIENCE_MS:
            ant.is_loitering = True
            return -LINGER_LOITER_PENALTY_PER_S * dt_s, 0.0, True
        return 0.0, 0.0, False
    else:
        # Exited the circle — give escape reward if we were loitering.
        exit_r = LINGER_EXIT_REWARD if ant.is_loitering else 0.0
        ant.linger_anchor_x = ant.x
        ant.linger_anchor_y = ant.y
        ant.linger_since_ms = now_ms
        ant.is_loitering = False
        return 0.0, exit_r, False


def _movement_block_penalty(
    move_dist: float,
    blocked: bool,
    forward_wall_frac: float,
    dt_s: float,
) -> float:
    """Penalty for wall collision (ant saw the wall and ran in) or pure stillness.

    This is kept *outside* the shaping tier so it fires even while loitering —
    ants should still learn to avoid walls regardless of their exploration state.
    """
    if move_dist >= STILL_MOVE_DIST_THRESHOLD:
        return 0.0
    if blocked and forward_wall_frac >= WALL_THREAT_MIN:
        return -REWARD_WALL_BLOCKED_SEEN * dt_s
    return -REWARD_STILL_PER_S * dt_s


# ---------------------------------------------------------------------------
# Pathfinder helpers
# ---------------------------------------------------------------------------

def _ensure_pathfinder(
    colony_index: int,
    sc: SimColony,
    state: GameState,
    walkable,
) -> NestPathfinder | None:
    """Return a fresh (or cached) NestPathfinder for ``colony_index``.

    Builds the Dijkstra distance field on first call and whenever the nest
    has moved by more than one grid cell.  The build is a one-time cost
    (~20-80 ms in pure Python) accepted on the first simulation frame.
    """
    if sc.nest_x is None or sc.nest_y is None:
        return None
    pf = state.nest_pathfinders.get(colony_index)
    if pf is None or pf.is_stale(sc.nest_x, sc.nest_y):
        pf = NestPathfinder()
        pf.build(sc.nest_x, sc.nest_y, walkable)
        state.nest_pathfinders[colony_index] = pf
    return pf


def _path_features(ant: Ant, sc: SimColony, pf: NestPathfinder | None) -> list[float]:
    """Compute the two path-guidance features appended to phi.

    Feature 0: normalised Dijkstra path-distance to nest.
               0.0 at the nest; values typically 0–3 across the world.
               Normalised by PATHFINDER_GRID_N so the range is roughly [0, 2].
    Feature 1: cos(ant_heading − optimal_path_heading) *only* when carrying;
               0.0 otherwise.  +1 = facing optimal direction, –1 = facing away.
    """
    if pf is None or not pf.dist:
        return [0.0, 0.0]
    d = pf.path_dist(ant.x, ant.y)
    d_norm = d / PATHFINDER_GRID_N if d != math.inf else 2.0
    heading_cos = 0.0
    if ant.carrying:
        opt = pf.best_heading(ant.x, ant.y)
        if opt is not None:
            diff = ant.heading - opt
            diff = (diff + math.pi) % (2.0 * math.pi) - math.pi
            heading_cos = math.cos(diff)
    return [d_norm, heading_cos]


def _path_dist_shaping(
    ant: Ant,
    sc: SimColony,
    pf: NestPathfinder | None,
    d_path_before: float,
    d_path_after: float,
) -> float:
    """Reward for reducing Dijkstra path-distance to the nest when carrying.

    Complements the straight-line ``_homeward_delta_shaping`` with a signal
    that remains positive even when navigating curved tunnels where straight-line
    distance briefly increases.
    """
    if not ant.carrying or pf is None:
        return 0.0
    if d_path_before == math.inf or d_path_after == math.inf:
        return 0.0
    dd = d_path_before - d_path_after   # positive when closer to nest
    if dd <= 0.0:
        return 0.0
    return REWARD_PATH_DIST_SHAPING * (dd / PATHFINDER_GRID_N)


def _path_heading_bonus(ant: Ant, sc: SimColony, pf: NestPathfinder | None, dt_s: float) -> float:
    """Per-second reward for facing the optimal path direction when carrying.

    Similar to ``_heading_toward_nest_bonus`` but uses the Dijkstra-computed
    heading rather than a straight line to the nest, so ants are rewarded for
    correctly orienting into tunnel bends.
    """
    if not ant.carrying or pf is None:
        return 0.0
    opt = pf.best_heading(ant.x, ant.y)
    if opt is None:
        return 0.0
    diff = ant.heading - opt
    diff = (diff + math.pi) % (2.0 * math.pi) - math.pi
    return REWARD_PATH_HEADING * math.cos(diff) * dt_s


# ---------------------------------------------------------------------------
# Pheromone attribution helpers
# ---------------------------------------------------------------------------

def _update_phero_following(
    ant: Ant,
    phero: PheromoneField,
    phi: list[float],
    bundle: RuntimeBundle,
    now_ms: int,
) -> None:
    """Update ant.phero_following_id based on type-A pheromone currently sensed.

    If any sensing lobe detects own-colony type-A pheromone above the threshold,
    query the field for the strongest nearby depositor (excluding self) and record
    it.  If the signal drops below threshold the tracked id is cleared.
    """
    # p0 features: lobe-centre=phi[12], lobe-left=phi[20], lobe-right=phi[28]
    if len(phi) < 29:
        return
    p0_max = max(phi[12], phi[20], phi[28])
    if p0_max < PHERO_FOLLOW_THRESHOLD:
        ant.phero_following_id = None
        return

    p = bundle.panel
    lobe_px_r = max(2.0, 56.0 / WORLD_WIDTH * p.map_rw)   # ANT_LOBE_RADIUS in px
    did = phero.nearest_depositor_world(
        ant.colony_index,
        ant.x,
        ant.y,
        phero_type=0,   # type-A = "follow me"
        radius_px=lobe_px_r * 3,
        map_rw=p.map_rw,
        map_rh=p.map_rh,
        now_ms=now_ms,
        exclude_id=id(ant),
    )
    ant.phero_following_id = did


def _apply_phero_credits(ant: Ant, state: GameState) -> float:
    """Drain any deferred pheromone credits/penalties owed to this ant.

    Returns the accumulated reward (positive = credits, negative = penalties).
    """
    ant_id = id(ant)
    credit = state.phero_pending_credits.pop(ant_id, 0.0)
    return credit


def _phero_trail_credit(ant: Ant, state: GameState, amount: float) -> None:
    """Push a deferred reward/penalty to the ant whose trail ``ant`` is following."""
    fid = ant.phero_following_id
    if fid is None:
        return
    state.phero_pending_credits[fid] = state.phero_pending_credits.get(fid, 0.0) + amount


def _phero_warning_reward(
    ant: Ant,
    p_mask: tuple[bool, bool],
    state: GameState,
    bundle: RuntimeBundle,
) -> float:
    """Immediate reward/penalty for depositing a type-B "warning" pheromone.

    Type-B is intended as a "no food here" / "danger" signal.  The ant is
    rewarded when it deposits type-B where there genuinely is no food nearby
    (correct warning) and penalised when food is actually present (false alarm).
    This gives the policy a direct fitness signal for semantic pheromone use.
    """
    if not p_mask[1]:   # type-B not being deposited this stride
        return 0.0
    r2 = PHERO_WARNING_FOOD_RADIUS * PHERO_WARNING_FOOD_RADIUS
    food_nearby = any(
        (fx - ant.x) ** 2 + (fy - ant.y) ** 2 <= r2
        for fx, fy in state.foods
    )
    if food_nearby:
        return -REWARD_PHERO_WARNING_WRONG   # false alarm
    return REWARD_PHERO_WARNING_CORRECT      # correct: genuinely empty area


def _nest_radius_world(bundle: RuntimeBundle) -> float:
    p = bundle.panel
    return p.nest_pick_r / max(1, p.map_rw) * WORLD_WIDTH


def _make_walkable(pg: Any, bundle: RuntimeBundle):
    p = bundle.panel
    surf = bundle.terrain_surf
    from ants.config import TERRAIN_TUNNEL, TERRAIN_WALL

    def walkable(wx: float, wy: float) -> bool:
        return is_tunnel_at_world(
            pg,
            surf,
            wx,
            wy,
            p.map_rw,
            p.map_rh,
            TERRAIN_TUNNEL,
            TERRAIN_WALL,
        )

    return walkable


def ensure_pheromone_field(state: GameState, bundle: RuntimeBundle) -> PheromoneField:
    p = bundle.panel
    colony_count = max(1, len(state.simulation_colonies))
    if state.pheromone is None:
        state.pheromone = PheromoneField(p.map_rw, p.map_rh, colony_count)
        return state.pheromone
    if (
        state.pheromone.map_w != p.map_rw
        or state.pheromone.map_h != p.map_rh
        or state.pheromone.colony_count != colony_count
    ):
        state.pheromone = PheromoneField(p.map_rw, p.map_rh, colony_count)
    return state.pheromone


def init_ants_from_state(state: GameState, now_ms: int) -> None:
    state.ants.clear()
    state.dead_weight_ghosts.clear()
    for ci, sc in enumerate(state.simulation_colonies):
        if sc.nest_x is None or sc.nest_y is None:
            continue
        n = parse_fetcher_count(sc.fetchers_str)
        for _ in range(n):
            a = Ant(
                colony_index=ci,
                x=float(sc.nest_x),
                y=float(sc.nest_y),
                heading=random.uniform(0.0, 2.0 * math.pi),
                life_start_ms=now_ms,
                last_alive_bonus_ms=now_ms,
            )
            state.ants.append(a)

    state.reward_chart_series = [deque(maxlen=REWARD_CHART_MAX_POINTS) for _ in state.ants]
    state.reward_chart_x_anchor_ms = now_ms
    state.reward_chart_x_tail_mode = False
    # Clear pathfinder cache and deferred credits on every sim restart so
    # the pathfinders are rebuilt fresh against the current terrain/nest.
    state.nest_pathfinders.clear()
    state.phero_pending_credits.clear()


def _colony_elite_weights(
    state: GameState,
    colony_index: int,
    exclude_ant: Ant,
    pending_ids: set[int],
    death_snap: dict[int, tuple[float, list[list[float]], int]],
) -> list[list[float]] | None:
    peers: list[tuple[float, list[list[float]]]] = []
    for other in state.ants:
        if other.colony_index != colony_index:
            continue
        if other is exclude_ant:
            continue
        oid = id(other)
        if oid in pending_ids:
            ret, w, ci = death_snap[oid]
            if ci == colony_index:
                peers.append((ret, w))
        else:
            peers.append((other.lifetime_return, other.weights))
    for g in state.dead_weight_ghosts:
        if g.colony_index != colony_index:
            continue
        peers.append((g.total_return, g.weights))
    if not peers:
        return None
    peers.sort(key=lambda p: p[0], reverse=True)
    keep_n = max(1, math.ceil(0.25 * len(peers)))
    return average_weights([w for _, w in peers[:keep_n]])


def _integrate_ant(
    ant: Ant,
    omega: float,
    dt_s: float,
    walkable,
) -> tuple[float, bool]:
    # omega is the pre-computed angular velocity (rad/s) for this action window,
    # already signed (+left / -right / 0 straight) and randomly scaled per action.
    ant.heading += omega * dt_s
    while ant.heading > 2.0 * math.pi:
        ant.heading -= 2.0 * math.pi
    while ant.heading < 0.0:
        ant.heading += 2.0 * math.pi

    old_x = ant.x
    old_y = ant.y
    sp = ANT_SPEED * dt_s
    nx = ant.x + math.cos(ant.heading) * sp
    ny = ant.y + math.sin(ant.heading) * sp
    nx = min(max(0.0, nx), WORLD_WIDTH)
    ny = min(max(0.0, ny), WORLD_HEIGHT)
    blocked = False
    for frac in (1.0 / 3.0, 2.0 / 3.0, 1.0):
        px = min(max(0.0, old_x + (nx - old_x) * frac), WORLD_WIDTH)
        py = min(max(0.0, old_y + (ny - old_y) * frac), WORLD_HEIGHT)
        if not walkable(px, py):
            blocked = True
            break
    if not blocked:
        ant.x = nx
        ant.y = ny
    ant.anim_accum += sp
    dx = ant.x - old_x
    dy = ant.y - old_y
    return math.sqrt(dx * dx + dy * dy), blocked


def _try_pickup(ant: Ant, state: GameState, now_ms: int) -> float:
    if ant.carrying:
        return 0.0
    r = ANT_FOOD_PICKUP_R
    r2 = r * r
    best_i = -1
    best_d = 0.0
    for i, (fx, fy) in enumerate(state.foods):
        dx, dy = fx - ant.x, fy - ant.y
        d2 = dx * dx + dy * dy
        if d2 <= r2 and (best_i < 0 or d2 < best_d):
            best_i = i
            best_d = d2
    if best_i < 0:
        return 0.0
    state.foods.pop(best_i)
    ant.carrying = True
    ant.ever_picked_food = True
    ant.pickup_ms = now_ms
    return REWARD_PICKUP


def _try_deposit(ant: Ant, sc: SimColony, nest_r: float, now_ms: int) -> float:
    if not ant.carrying or sc.nest_x is None or sc.nest_y is None:
        return 0.0
    dx, dy = ant.x - sc.nest_x, ant.y - sc.nest_y
    if dx * dx + dy * dy > nest_r * nest_r:
        return 0.0
    # Compute efficiency bonus *before* resetting life_start_ms.
    # time_frac = 1.0 for an instant run, 0.0 if the full timeout was used.
    elapsed_ms = now_ms - ant.life_start_ms
    max_ms = float(TIMEOUT_FIND_FOOD_MS + TIMEOUT_RETURN_FOOD_MS)
    time_frac = max(0.0, 1.0 - elapsed_ms / max_ms)

    ant.carrying = False
    ant.pickup_ms = None
    ant.ever_picked_food = False
    ant.life_start_ms = now_ms
    ant.last_alive_bonus_ms = now_ms
    return REWARD_DEPOSIT + REWARD_EFFICIENCY_BONUS * time_frac


def _die_and_respawn(
    ant: Ant,
    state: GameState,
    colonies: list[SimColony],
    now_ms: int,
    drop_food: bool,
) -> None:
    """Respawn the ant at its nest.

    With a shared DQN there are no per-ant weights to blend; respawning simply
    resets position/state.  The ant immediately starts using the latest shared
    policy on its next step.
    """
    drop_x = ant.x
    drop_y = ant.y
    ant.reset_at_nest(colonies, now_ms)
    if drop_food:
        state.foods.append(
            (min(max(0.0, drop_x), WORLD_WIDTH), min(max(0.0, drop_y), WORLD_HEIGHT))
        )


def sim_step(pg: Any, bundle: RuntimeBundle, state: GameState, dt_ms: int, now_ms: int) -> None:
    if not state.sim_running or state.sim_paused or state.edit_map:
        return
    if not state.ants:
        return

    # ------------------------------------------------------------------ DQN
    # Lazily initialise the shared DQN agent the first time we step.
    if state.dqn_agent is None:
        state.dqn_agent = DQNAgent()
    dqn: DQNAgent = state.dqn_agent
    # --------------------------------------------------------------------

    _cull_ghosts(state, now_ms)

    walkable = _make_walkable(pg, bundle)
    phero = ensure_pheromone_field(state, bundle)
    phero.cull_expired(now_ms)

    nest_r = _nest_radius_world(bundle)
    dt_s = max(0.0, dt_ms / 1000.0)
    colonies = state.simulation_colonies
    pending_deaths: list[Ant] = []

    # --- Ensure a pathfinder exists for every active colony (built once) ---
    for ci, sc in enumerate(colonies):
        if sc.nest_x is not None and sc.nest_y is not None:
            _ensure_pathfinder(ci, sc, state, walkable)

    for ai, ant in enumerate(state.ants):
        if ant.colony_index >= len(colonies):
            continue
        sc = colonies[ant.colony_index]
        if sc.nest_x is None or sc.nest_y is None:
            continue

        x0 = ant.x
        y0 = ant.y
        carrying0 = ant.carrying
        foods0 = list(state.foods)

        # Get the pathfinder for this colony (already built above).
        pf = state.nest_pathfinders.get(ant.colony_index)

        # Path distance before movement (used for path-shaping reward).
        d_path0 = pf.path_dist(ant.x, ant.y) if pf else math.inf

        # Compute path-guidance features for this ant's observation.
        pfeats = _path_features(ant, sc, pf)

        # Build the current observation every frame (needed for reward signals
        # regardless of action-repeat state).
        phi_now = build_phi(
            ant,
            ai,
            colonies,
            state.ants,
            state.foods,
            walkable,
            phero,
            bundle.panel.map_rw,
            bundle.panel.map_rh,
            now_ms,
            path_features=pfeats,
        )

        # Track which ant's type-A trail this ant is currently sensing.
        _update_phero_following(ant, phero, phi_now, bundle, now_ms)

        # --- Action repeat: pick a new action once per DQN_ACTION_WINDOW_MS ms.
        # Tracking time (not frame count) keeps the intended turn angle identical
        # regardless of the simulation speed multiplier (×1 through ×10).
        # Rewards accumulate across the window; a single (s,a,Σr,s') experience
        # is pushed to the replay buffer when the window expires.
        if ant.action_time_left_ms <= 0:
            a_exec = dqn.pick_action(phi_now)
            ant.current_action = a_exec
            ant.phi_at_action_start = phi_now
            ant.pending_reward = 0.0
            ant.action_time_left_ms = DQN_ACTION_WINDOW_MS
            # Convert the policy-chosen action into an angular velocity such that
            # the ant rotates exactly TURN_MAGNITUDES[mag_idx] degrees over the
            # full action window — regardless of how many frames that spans.
            turn_idx_new, magnitude_idx_new, _ = decode_action(a_exec)
            if turn_idx_new != 0:
                angle_rad = math.radians(TURN_MAGNITUDES[magnitude_idx_new])
                # omega [rad/s] × window_duration [s] = angle_rad
                omega = angle_rad / (DQN_ACTION_WINDOW_MS / 1000.0)
                ant.current_turn_omega = omega if turn_idx_new == 1 else -omega
            else:
                ant.current_turn_omega = 0.0
        else:
            a_exec = ant.current_action

        # Forward wall fraction from the *current* observation — used for the
        # wall penalty so it always reflects what the ant can see right now.
        forward_wall_frac = phi_now[6] if len(phi_now) > 6 else 0.0

        turn_idx, _mag_idx, p_mask = decode_action(a_exec)
        d0 = math.hypot(ant.x - sc.nest_x, ant.y - sc.nest_y)
        move_dist, blocked = _integrate_ant(ant, ant.current_turn_omega, dt_s, walkable)
        d1 = math.hypot(ant.x - sc.nest_x, ant.y - sc.nest_y)

        # Path distance after movement (for wall-aware shaping reward).
        d_path1 = pf.path_dist(ant.x, ant.y) if pf else math.inf

        ant.phero_stride += move_dist
        interval = max(4.0, PHEROMONE_DOT_INTERVAL)
        phero_warning_r = 0.0
        while ant.phero_stride >= interval:
            ant.phero_stride -= interval
            phero.deposit_world(
                ant.colony_index,
                ant.x,
                ant.y,
                p_mask,
                bundle.panel.map_rw,
                bundle.panel.map_rh,
                now_ms,
                depositor_id=id(ant),
            )
            # Reward/penalise type-B ("warning") deposits based on food presence.
            phero_warning_r += _phero_warning_reward(ant, p_mask, state, bundle)

        # ---- Personal linger circle -----------------------------------------
        # Updates the rolling patience circle and returns the per-frame penalty
        # (if loitering) + a one-shot exit reward (if just escaped).
        linger_penalty, exit_reward, is_loitering = _linger_circle_update(ant, now_ms, dt_s)

        # ---- Nest zone check ------------------------------------------------
        # When the ant is not carrying food and is inside the colony's
        # no-reward zone, all shaping rewards are suppressed.  This stops ants
        # from farming curiosity / movement bonuses while hanging around home.
        in_nest_zone = (
            not ant.carrying
            and math.hypot(ant.x - sc.nest_x, ant.y - sc.nest_y) <= NEAR_COLONY_NO_FOOD_RADIUS
        )

        # suppress_shaping: True → only hard penalties + events fire this tick.
        # IMPORTANT: suppression only applies when the ant is NOT carrying food.
        # Carrying ants are on a return trip — they need every positive shaping
        # signal (homeward delta, path-following, heading bonus) to navigate home.
        # Suppressing those rewards while carrying caused ants to avoid the nest.
        suppress_shaping = (is_loitering or in_nest_zone) and not ant.carrying

        # ---- Always-active: wall/still penalty (fires even while loitering) --
        r_hard = _movement_block_penalty(move_dist, blocked, forward_wall_frac, dt_s)
        r_hard += linger_penalty

        # ---- Always-active: deferred pheromone credits ----------------------
        r_hard += _apply_phero_credits(ant, state)

        # ---- Always-active: fundamental events (pickup / deposit) -----------
        carrying_before_pickup = ant.carrying
        r_hard += _try_pickup(ant, state, now_ms)
        if not carrying_before_pickup and ant.carrying:
            # Just picked up food — credit the trail-layer this ant was following.
            _phero_trail_credit(ant, state, REWARD_PHERO_LED_TO_FOOD)
            # Also reset the linger anchor so the return trip starts fresh.
            ant.linger_anchor_x = ant.x
            ant.linger_anchor_y = ant.y
            ant.linger_since_ms = now_ms
            ant.is_loitering = False

        r_hard += _try_deposit(ant, sc, nest_r, now_ms)
        if carrying_before_pickup and not ant.carrying:
            # Just deposited — clear trail tracking and reset linger anchor.
            ant.phero_following_id = None
            ant.linger_anchor_x = ant.x
            ant.linger_anchor_y = ant.y
            ant.linger_since_ms = now_ms
            ant.is_loitering = False

        # exit_reward fires in the hard tier so it always applies when an ant
        # finally escapes a loitering circle — even if that circle was inside the
        # nest zone.  Without this the ant is penalised for staying (-4/s) but
        # receives no positive signal for leaving, which traps it in spawn.
        r_hard += exit_reward

        # ---- Shaping rewards (suppressed when loitering or in nest zone) ----
        if suppress_shaping:
            # Zero shaping; only the hard tier fires.
            r = r_hard
        else:
            r = r_hard
            r += REWARD_STEP_NO_FOOD if not ant.carrying else 0.0
            # Delta-based directional shaping.
            r += _outward_from_nest_shaping(ant.carrying, sc.nest_x, sc.nest_y, d0, d1)
            r += _homeward_delta_shaping(ant.carrying, sc.nest_x, sc.nest_y, d0, d1)
            # Wall-aware path-following rewards.
            r += _path_dist_shaping(ant, sc, pf, d_path0, d_path1)
            r += _path_heading_bonus(ant, sc, pf, dt_s)
            # Pheromone strategy rewards.
            r += phero_warning_r
            # Legacy proximity + potential shaping.
            r += _carry_home_shaping(ant, sc)
            r += _potential_shaping_reward(
                x0, y0, carrying0, foods0,
                ant.x, ant.y, ant.carrying, list(state.foods),
                sc.nest_x, sc.nest_y,
            )
            # Continuous wall-approach gradient.
            r += _wall_approach_penalty(forward_wall_frac, dt_s)
            # Food-lobe sensing: gradient toward food before physical pickup.
            r += _food_lobe_reward(ant, phi_now, dt_s)
            # Curiosity: one-shot bonus for entering each new map cell.
            r += _curiosity_reward(ant)
            # Heading alignment toward nest (straight-line complement).
            r += _heading_toward_nest_bonus(ant, sc, dt_s)
        # ---------------------------------------------------------------------

        died = False
        if not ant.carrying and not ant.ever_picked_food:
            if now_ms - ant.life_start_ms >= TIMEOUT_FIND_FOOD_MS:
                died = True
        elif ant.carrying and ant.pickup_ms is not None:
            if now_ms - ant.pickup_ms >= TIMEOUT_RETURN_FOOD_MS:
                died = True

        if died:
            # If the ant was following someone's type-A trail and failed to find
            # food, penalise the trail-layer for the misleading signal.
            if not ant.carrying:
                _phero_trail_credit(ant, state, -REWARD_PHERO_MISLED)
            r += REWARD_DEATH
            ant.pending_reward += r
            ant.lifetime_return += r
            b = RL_REWARD_EMA_BETA
            ant.reward_ema = (1.0 - b) * ant.reward_ema + b * r
            # Push the accumulated experience for this action window (terminal).
            phi_terminal = phi_for_terminal()
            dqn.push(ant.phi_at_action_start, ant.current_action, ant.pending_reward, phi_terminal, True)
            ant.action_time_left_ms = 0
            ant.pending_reward = 0.0
            pending_deaths.append(ant)
            continue

        pfeats2 = _path_features(ant, sc, pf)
        phi2 = build_phi(
            ant,
            ai,
            colonies,
            state.ants,
            state.foods,
            walkable,
            phero,
            bundle.panel.map_rw,
            bundle.panel.map_rh,
            now_ms,
            path_features=pfeats2,
        )
        r += _delayed_wall_threat_clear_reward(ant, phi2, move_dist, blocked)
        ant.prev_max_wall_frac = _max_wall_frac_phi(phi2)

        ant.pending_reward += r
        ant.lifetime_return += r
        b = RL_REWARD_EMA_BETA
        ant.reward_ema = (1.0 - b) * ant.reward_ema + b * r

        # Count down the action window and push one experience when it expires.
        ant.action_time_left_ms -= dt_ms
        if ant.action_time_left_ms <= 0:
            dqn.push(ant.phi_at_action_start, ant.current_action, ant.pending_reward, phi2, False)
            ant.pending_reward = 0.0

        # Clear the legacy SARSA field so the Ant dataclass stays consistent.
        ant.pending_next_action = None

    # One gradient update per simulation tick (after all ants have contributed
    # their experiences for this frame).
    dqn.update()

    if pending_deaths:
        death_snap: dict[int, tuple[float, list[list[float]], int]] = {}
        for a in pending_deaths:
            death_snap[id(a)] = (
                a.lifetime_return,
                _copy_weight_matrix(a.weights),
                a.colony_index,
            )

        for a in pending_deaths:
            _die_and_respawn(
                a,
                state,
                colonies,
                now_ms,
                drop_food=a.carrying,
            )
            a.pending_next_action = None

        for a in pending_deaths:
            ret, w, ci = death_snap[id(a)]
            state.dead_weight_ghosts.append(DeadWeightGhost(ci, ret, w, now_ms))
