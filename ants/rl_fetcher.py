"""Linear SARSA for fetcher: 9 actions = 3 turns × exclusive pheromone (off / type0 / type1)."""

from __future__ import annotations

import math
import random

from ants.config import (
    RL_ALPHA,
    RL_FEATURE_DIM,
    RL_GAMMA,
    RL_NUM_ACTIONS,
    RL_TEMP_EMA_K,
    RL_TEMP_EMA_REF,
    RL_TEMP_MAX,
    RL_TEMP_MIN,
)


def decode_action(a: int) -> tuple[int, int, tuple[bool, bool]]:
    """Decode a flat action index into (turn, magnitude_idx, pheromone_mask).

    Action layout (RL_NUM_ACTIONS = 27):
      0-2   : straight, pheromone none / A / B        (magnitude irrelevant)
      3-14  : left turn, 4 magnitudes × 3 pheromones
      15-26 : right turn, 4 magnitudes × 3 pheromones

    turn        : 0=straight, 1=left, 2=right
    magnitude_idx: 0..3  index into TURN_MAGNITUDES (ignored when turn==0)
    """
    a = a % RL_NUM_ACTIONS
    if a < 3:
        # Straight: pheromone encoded directly in a
        p_mode = a
        turn = 0
        magnitude_idx = 0   # meaningless for straight, always 0
    else:
        offset = a - 3
        turn = 1 + offset // 12        # 1=left for offset 0-11, 2=right for 12-23
        remainder = offset % 12
        magnitude_idx = remainder // 3  # 0..3
        p_mode = remainder % 3          # 0=none, 1=A, 2=B

    if p_mode == 0:
        mask: tuple[bool, bool] = (False, False)
    elif p_mode == 1:
        mask = (True, False)
    else:
        mask = (False, True)
    return turn, magnitude_idx, mask


def encode_action(turn: int, magnitude_idx: int, p_mode: int) -> int:
    """Inverse of decode_action."""
    p = max(0, min(2, int(p_mode)))
    if turn == 0:
        return p
    t = 0 if turn == 1 else 1          # left→0 offset block, right→1 offset block
    m = max(0, min(3, int(magnitude_idx)))
    return 3 + t * 12 + m * 3 + p


def q_dot(w_row: list[float], phi: list[float]) -> float:
    return sum(w_row[i] * phi[i] for i in range(min(len(w_row), len(phi))))


def q_values(weights: list[list[float]], phi: list[float]) -> list[float]:
    return [q_dot(weights[a], phi) for a in range(RL_NUM_ACTIONS)]


def temperature_from_ema(ema: float) -> float:
    z = (ema - RL_TEMP_EMA_REF) * RL_TEMP_EMA_K
    frac = 1.0 / (1.0 + math.exp(z))
    return RL_TEMP_MIN + (RL_TEMP_MAX - RL_TEMP_MIN) * frac


def pick_action_softmax(
    weights: list[list[float]], phi: list[float], tau: float, rng: random.Random | None = None
) -> int:
    r = rng if rng is not None else random
    qs = q_values(weights, phi)
    t = max(1e-6, float(tau))
    m = max(qs)
    exps = [math.exp((q - m) / t) for q in qs]
    s = sum(exps)
    u = r.random() * s
    acc = 0.0
    for a in range(RL_NUM_ACTIONS):
        acc += exps[a]
        if u <= acc:
            return a
    return RL_NUM_ACTIONS - 1


def sarsa_update(
    weights: list[list[float]],
    phi: list[float],
    a: int,
    reward: float,
    phi_next: list[float],
    a_next: int,
    terminal: bool,
) -> None:
    if len(phi) != RL_FEATURE_DIM:
        return
    q_sa = q_dot(weights[a], phi)
    q_next = 0.0 if terminal else q_dot(weights[a_next], phi_next)
    delta = reward + RL_GAMMA * q_next - q_sa
    row = weights[a]
    for i in range(RL_FEATURE_DIM):
        row[i] += RL_ALPHA * delta * phi[i]


def average_weights(ants_weights: list[list[list[float]]]) -> list[list[float]]:
    if not ants_weights:
        return [[0.0] * RL_FEATURE_DIM for _ in range(RL_NUM_ACTIONS)]
    n = len(ants_weights)
    out: list[list[float]] = [
        [0.0] * RL_FEATURE_DIM for _ in range(RL_NUM_ACTIONS)
    ]
    for w in ants_weights:
        for a in range(RL_NUM_ACTIONS):
            for i in range(RL_FEATURE_DIM):
                out[a][i] += w[a][i]
    for a in range(RL_NUM_ACTIONS):
        for i in range(RL_FEATURE_DIM):
            out[a][i] /= n
    return out
