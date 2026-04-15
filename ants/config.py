"""Constants and filesystem paths (no pygame)."""

import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = PROJECT_ROOT / "asset"
SAVE_DIR = PROJECT_ROOT / "save"

WORLD_WIDTH = 5600.0
WORLD_HEIGHT = 4800.0
D_REF = math.hypot(WORLD_WIDTH, WORLD_HEIGHT)
WINDOW_WIDTH = 1500
WINDOW_HEIGHT = 800
PANEL_WIDTH = 500
PANEL_MARGIN = 10
CARD_GAP = 10
CARD_HEIGHT = 268
COLONY_CARD_WIDTH = 300
COLONY_DD_ROW_H = 26
BLUEPRINT_ARROW_W = 40
BLUEPRINT_ARROW_GAP = 12
REWARD_SYSTEMS = ("individualist", "cooperative", "safe", "explorer")
COLONY_COLOR_ORDER = ("black", "blue", "red", "purple", "yellow")
COLONY_COLOR_RGB: dict[str, tuple[int, int, int]] = {
    "black": (48, 48, 52),
    "blue": (88, 152, 255),
    "red": (235, 92, 92),
    "purple": (180, 120, 255),
    "yellow": (240, 210, 80),
}
MAX_SIM_COLONIES = 5
COLONY_SPRITE_SCALE = 1.5
COLONY_CURSOR_PREVIEW_MAX_PX = 72
DEBUG_COLONY_NO_TINT = False
DEBUG_COLONY_NO_CONVERT_ALPHA = False

TERRAIN_WALL = (78, 60, 51)
TERRAIN_TUNNEL = (133, 102, 88)
# Sum of squared RGB deltas to TERRAIN_TUNNEL; blended smoothscale edge pixels can be
# closer to tunnel than wall in L2 but are not real floor — keep below ambiguous browns.
TERRAIN_TUNNEL_MAX_DIST_SQ = 1000
BORDER_LOCK = 10
BRUSH_RADIUS_PRESETS = (12, 20, 32, 48, 72, 96)
BRUSH_PRESET_ROW_H = 42
BRUSH_PRESET_GAP = 6
BRUSH_PRESET_MAX = max(BRUSH_RADIUS_PRESETS)
BRUSH_PREVIEW_WHITE = (255, 255, 255)
BRUSH_PREVIEW_FAINT = (200, 210, 230)
FOOD_SPAWN_INTERVAL_MS = 72
FOOD_GROW_PER_MS = 0.028
FOOD_R_MAX_FRAC = 0.1
FOOD_ERASE_SEARCH_RADIUS_PX = 88
FOOD_SPEED_COUNT = 5
FOOD_CURSOR_PREVIEW_MAX_PX = 20

# Simulation speed multiplier presets (index 2 = 1× default)
SIM_SPEED_PRESETS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 10.0)
SIM_SPEED_LABELS: tuple[str, ...] = ("×¼", "×½", "×1", "×2", "×3", "×5", "×10")
SIM_SPEED_DEFAULT_INDEX: int = 2

TERRAIN_BIN_MAGIC = b"CMP1"
TERRAIN_SAVE_FILE = SAVE_DIR / "terrain.bin"
LEGACY_TERRAIN_FILE = PROJECT_ROOT / "terrain_map.png"
SESSION_SAVE_FILE = SAVE_DIR / "session.json"
SESSION_VERSION = 3
SESSION_V2 = 2
SESSION_V1 = 1

# Fetcher ants (world units / second unless noted)
ANT_SPEED = 120.0
# ANT_TURN_RATE kept for legacy imports; sim_step uses TURN_MAGNITUDES instead.
ANT_TURN_RATE = 2.2
ANT_FOOD_PICKUP_R = 45.0
ANT_ANIM_FRAME_DIST = 14.0
ANT_CARRY_FOOD_OFFSET = 38.0
ANT_LOBE_OFFSET = 142.0
ANT_LOBE_RADIUS = 56.0
ANT_LOBE_SIDE_ANGLE_DEG = 60.0
ANT_LOBE_SIDE_ANGLE_RAD = math.radians(ANT_LOBE_SIDE_ANGLE_DEG)
ANT_LOBE_SAMPLE_N = 12
ANT_WALK_FRAME_SCALE = 0.55

TIMEOUT_FIND_FOOD_MS = 30_000
TIMEOUT_RETURN_FOOD_MS = 30_000

PHEROMONE_TYPES = 2
PHEROMONE_LIFETIME_MS = 10_000
PHEROMONE_DOT_INTERVAL = 14.0
DRAW_PHEROMONES = True

MAP_ZOOM_MIN = 1.0
MAP_ZOOM_MAX = 4.0
MAP_ZOOM_STEP = 1.12

RL_ALPHA = 0.012
RL_GAMMA = 0.97
RL_WEIGHT_INIT_SCALE = 0.02
# Feature layout: 6 global + 3 lobes × 8 each + 2 path-guidance features = 32
RL_FEATURE_DIM = 32
# Action space: 27 = 3 straight×phero  +  2 directions × 4 magnitudes × 3 phero
# straight:  actions 0-2   (pheromone none / A / B, no magnitude choice)
# left turn: actions 3-14  (4 magnitudes × 3 pheromones)
# right turn: actions 15-26 (4 magnitudes × 3 pheromones)
# The full (direction, magnitude, pheromone) decision is made by the policy;
# randomness only enters during epsilon-greedy exploration.
RL_NUM_ACTIONS = 27
# Turn magnitudes available to the policy (degrees).  Index 0..3.
TURN_MAGNITUDES: tuple[float, ...] = (5.0, 30.0, 60.0, 90.0)
RL_REWARD_EMA_BETA = 0.06
RL_TEMP_MIN = 0.38
RL_TEMP_MAX = 2.65
RL_TEMP_EMA_REF = 0.35
RL_TEMP_EMA_K = 0.08

# ---------------------------------------------------------------------------
# DQN hyperparameters (used by ants/dqn_fetcher.py)
# ---------------------------------------------------------------------------
DQN_HIDDEN_SIZES: tuple[int, ...] = (128, 64)
DQN_LR = 1e-3
DQN_BATCH_SIZE = 64
DQN_REPLAY_SIZE = 50_000
# Hard-copy target network every N gradient steps
DQN_TARGET_UPDATE_FREQ = 500
# Epsilon-greedy schedule: linear decay from START to END over DECAY_STEPS
# gradient updates.  At ~60 fps one gradient step fires per frame, so
# 30 000 steps ≈ 8 minutes of simulation time — enough to see wall avoidance
# emerge while still exploring early on.
DQN_EPSILON_START = 1.0
DQN_EPSILON_END = 0.05
DQN_EPSILON_DECAY_STEPS = 20_000
# Number of nominal 60-fps frames the ant holds the same action before picking
# a new one.  The *actual* window is tracked in milliseconds so that the
# intended turn angle is preserved regardless of the simulation speed
# multiplier (×1 through ×10).  At 60 fps this is ~333 ms per decision.
DQN_ACTION_REPEAT = 20
DQN_ACTION_WINDOW_MS: int = int(round(DQN_ACTION_REPEAT * 1000.0 / 60.0))  # ≈ 333 ms

SENSE_LOBE_DEBUG_RGBA = (0, 255, 0, 128)

# --- Food-lobe sensing rewards (per second, applied when NOT carrying) ------
# Give the ant a gradient toward food *before* physical contact.
# Center lobe gets a higher bonus than side lobes so the ant learns to aim.
REWARD_FOOD_LOBE_CENTER = 10.0  # /s when food is detected in the forward lobe
REWARD_FOOD_LOBE_SIDE   = 4.0   # /s when food is in a side lobe only

# --- Curiosity bonus for visiting a new map cell (one-shot, per cell) -------
# Reduced from 5.0 → 1.5 to suppress the large reward spike at sim start
# (30 ants × many new cells = high noise floor that masks genuine learning).
REWARD_NEW_CELL_VISIT = 1.5

# --- Continuous wall-approach gradient (per second, scales with wall_frac) --
# Applied proportionally to how much wall is in the *forward* lobe, giving a
# smooth repulsion gradient before the ant physically collides.
REWARD_WALL_APPROACH_FRAC = 1.2   # /s  (penalty, so used as: r -= coef * frac * dt_s)

# --- Heading alignment bonus when carrying food (per second × cos(angle)) ---
# Rewards the ant for *facing* its nest while carrying food, giving a direction
# signal that complements the distance-based homeward delta shaping.
REWARD_HEADING_TOWARD_NEST = 0.5  # /s (scaled by cos between heading and nest direction)

REWARD_STEP_NO_FOOD = 0.0
# REWARD_PER_UNIT_DIST = 0.015
REWARD_PICKUP = 50.0
REWARD_DEPOSIT = 150.0
# REWARD_EXPLORE_DIST = 0.08
REWARD_HOME_DIST = 0.05          # position-based nest proximity (minor, legacy)
# Continuous delta-distance shaping: reduced from 8.0 → 1.5 to cut the
# "keep moving in any direction" motor-primitive noise floor.  The DQN should
# learn *when* to move toward/away based on its observations, not just "always go".
REWARD_OUTWARD_SHAPING = 1.5    # delta reward: each world-unit moved away from nest (no food)
REWARD_HOMEWARD_SHAPING = 1.5   # delta reward: each world-unit moved toward nest (carrying food)
# REWARD_MAX_DIST_BONUS = 0.15
# REWARD_TIME_FAR_PER_S = 0.04
# REWARD_NEAR_NEST_PER_S = -0.12
# FAR_FROM_NEST_FRAC = 0.22
NEAR_NEST_FRAC = 0.06
ALIVE_BONUS_EVERY_MS = 31_000
REWARD_ALIVE_BONUS = 50.0
# LOOP_WINDOW_MS = 3000
# LOOP_PROX_RADIUS = 28.0
# STUCK_ESCALATE_COEF = 3.0

# Without food: inside this radius of own nest all shaping rewards are suppressed
# (replaced by the linger-circle system below; the old per-second penalty is zeroed).
NEAR_COLONY_NO_FOOD_RADIUS = NEAR_NEST_FRAC * D_REF
REWARD_NEAR_NEST_PER_S = 0.0   # superseded — suppression zone handles this now

# ---------------------------------------------------------------------------
# Personal linger circle (replaces coarse grid-cell exploration penalty)
# ---------------------------------------------------------------------------
# Each ant carries an "anchor" point.  If the ant remains within
# LINGER_ANCHOR_RADIUS world units of that anchor for longer than
# LINGER_PATIENCE_MS, it enters a loitering state:
#   • All shaping rewards are suppressed (only hard penalties + events fire).
#   • A per-second loitering penalty is applied.
# When the ant finally exits the circle, it receives LINGER_EXIT_REWARD and
# the anchor resets to the exit point, starting a fresh patience window.
# This forces *real* territorial progress rather than rewarding small wiggles.
#
# Radius sizing: ~10 ant body-widths at display scale.
# An ant body is ~24 world units wide → 10 × 24 = 240 wu diameter → 120 wu radius.
# Chosen so tight orbits are caught but genuine exploration is not penalised.
LINGER_ANCHOR_RADIUS    = 120.0   # world units
LINGER_PATIENCE_MS      = 10_000  # ms grace before loitering state triggers
LINGER_LOITER_PENALTY_PER_S = 4.0 # penalty/s while loitering (on top of zero shaping)
LINGER_EXIT_REWARD      = 15.0    # one-shot bonus when leaving a loitering circle

# Grid-based exploration constants (superseded by circle system; kept for imports).
# EXPLORATION_LINGER_PENALTY_PER_S is set to 0 so old call-sites are no-ops.
EXPLORATION_GRID_N = 20
EXPLORATION_LINGER_THRESHOLD_MS = 8_000
EXPLORATION_LINGER_PENALTY_PER_S = 0.0   # zeroed — circle system replaces this

# Efficiency bonus on food deposit: REWARD_DEPOSIT + REWARD_EFFICIENCY_BONUS * frac,
# where frac = 1 - elapsed / (TIMEOUT_FIND_FOOD_MS + TIMEOUT_RETURN_FOOD_MS).
# Replaces the old fixed-interval alive bonus (REWARD_ALIVE_BONUS) with a
# signal that directly rewards fast food collection.
REWARD_EFFICIENCY_BONUS = 30.0

# --- Legacy alive-interval bonus (superseded by REWARD_EFFICIENCY_BONUS) ---
# These constants are retained so imports still resolve, but simulation.py
# no longer calls _alive_interval_bonus().
ALIVE_BONUS_EVERY_MS = 31_000
REWARD_ALIVE_BONUS = 50.0
# Step displacement below this (world units) counts as "still" (penalty even when blocked by wall).
STILL_MOVE_DIST_THRESHOLD = 1.0
REWARD_STILL_PER_S = 0.2

# Potential-based shaping: F = gamma * Phi(s') - Phi(s); Phi = -coef * min(dist, cap) / D_REF
POTENTIAL_DIST_CAP_FRAC = 1.0
REWARD_POTENTIAL_FOOD = 2.0
REWARD_POTENTIAL_NEST = 2.0

# ---------------------------------------------------------------------------
# Nest pathfinder (BFS/Dijkstra on a coarse grid for wall-aware path rewards)
# ---------------------------------------------------------------------------
# Grid resolution: GRID_N × GRID_N cells covering the world.
# Each cell is (WORLD_WIDTH/GRID_N) × (WORLD_HEIGHT/GRID_N) world units.
# Smaller = finer paths but slower to build (one-time cost at sim start).
PATHFINDER_GRID_N = 80
# Cells within this many grid cells of a wall get PATHFINDER_WALL_STEP_PENALTY
# extra cost, so Dijkstra routes ants comfortably away from walls.
PATHFINDER_WALL_MARGIN_CELLS = 2
PATHFINDER_WALL_STEP_PENALTY = 3.0    # extra Dijkstra cost for wall-adjacent cells

# --- Path-following rewards (carrying food, returning to nest) ---------------
# Reward per grid-unit of path-distance closed toward nest, scaled by grid_n.
# Complements REWARD_HOMEWARD_SHAPING (straight-line) with a wall-aware signal.
# Reduced from 10.0 → 2.5: wall-aware path shaping is still useful but was
# overpowering the terminal deposit reward as the dominant learning signal.
REWARD_PATH_DIST_SHAPING = 2.5
# Per-second reward × cos(ant heading − optimal path heading) when carrying.
# Guides the ant to face the correct turn direction even inside tunnels.
REWARD_PATH_HEADING = 0.8

# ---------------------------------------------------------------------------
# Pheromone trail attribution rewards
# ---------------------------------------------------------------------------
# An ant is considered "following" a type-A trail if the sensed p0 strength
# in any lobe exceeds this threshold.
PHERO_FOLLOW_THRESHOLD = 0.25
# Deferred credit pushed to the trail-layer when a following ant picks up food.
REWARD_PHERO_LED_TO_FOOD = 30.0
# Deferred penalty pushed when a following ant dies without finding food.
REWARD_PHERO_MISLED = 3.0

# --- Type-B "warning / no-food-here" pheromone rewards ---------------------
# Reward for depositing type-B pheromone when there genuinely is no food
# within PHERO_WARNING_FOOD_RADIUS world units of the deposit location.
REWARD_PHERO_WARNING_CORRECT = 8.0
# Penalty for depositing type-B when food is actually nearby (false warning).
REWARD_PHERO_WARNING_WRONG = 3.0
# Radius (world units) searched when evaluating a type-B deposit.
PHERO_WARNING_FOOD_RADIUS = 200.0

WALL_THREAT_MIN = 0.1

# Reward given (once) when the ant escapes a wall-threat zone it was in last
# step.  Raised from 0.35 → 2.0 so escaping a wall is meaningfully more
# valuable than the generic outward-exploration shaping.
# Wall-dodge reward disabled: rewarding wall-clears caused ants to orbit walls
# for free points.  Collisions are punished instead (REWARD_WALL_BLOCKED_SEEN).
REWARD_WALL_THREAT_CLEAR = 0.0

# Per-second penalty applied when the ant's movement is blocked by a wall
# that was already visible in the forward sensor lobe (phi[6] >= WALL_THREAT_MIN).
# "Can't detect → no blame; could see it and ran in anyway → penalise."
REWARD_WALL_BLOCKED_SEEN = 1.2

# --- Exploration / anti-idle penalty ----------------------------------------
# The world is divided into EXPLORATION_GRID_N × EXPLORATION_GRID_N cells.
# If an ant stays inside the *same* cell for longer than LINGER_THRESHOLD_MS
# it accumulates a per-second penalty that grows the longer it loiters.
# This discourages circling in place and rewards genuinely moving to new areas.
# (EXPLORATION_GRID_N / THRESHOLD / PENALTY defined above near the linger-circle block)

GHOST_WEIGHT_TTL_MS = 15_000
RESPAWN_BLEND_LAMBDA = 0.25
REWARD_DEATH = -15.0

REWARD_CHART_Y_MIN = -500.0
REWARD_CHART_Y_MAX = 500.0
REWARD_CHART_Y_TICK_STEP = 100.0
REWARD_CHART_MAX_POINTS = 36_000
REWARD_CHART_X_SPAN_MS = 600_000
REWARD_CHART_X_SCROLL_AT = 0.8
REWARD_CHART_X_MINOR_MS = 30_000
REWARD_CHART_X_LABEL_MAJOR_MS = 60_000
REWARD_CHART_LABEL_PAD_LEFT = 44
REWARD_CHART_LABEL_PAD_BOTTOM = 24
REWARD_CHART_W = 720
REWARD_CHART_H = 420
REWARD_CHART_MARGIN = 14
REWARD_CHART_BG_HEX = "#10141c"
REWARD_CHART_OVERLAY_BG_RGB = (16, 20, 28)
REWARD_CHART_BORDER_HEX = "#374056"
REWARD_CHART_GRID_MINOR_HEX = "#2d3445"
REWARD_CHART_GRID_MINOR_RGB = (45, 52, 69)
REWARD_CHART_ZERO_HEX = "#a0a5b4"
