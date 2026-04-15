"""Shared DQN agent for fetcher ants (numpy only, no external ML deps).

Architecture
------------
- Single MLP shared across every ant in the simulation.
- Experience replay buffer fed by all ants every step.
- Target network hard-updated every DQN_TARGET_UPDATE_FREQ gradient steps.
- Epsilon-greedy exploration that decays over DQN_EPSILON_DECAY_STEPS.
- Adam optimiser with gradient clipping (Huber-style) to handle large rewards.
"""

from __future__ import annotations

import math
import random
from collections import deque
from typing import Optional

import numpy as np

from ants.config import (
    DQN_BATCH_SIZE,
    DQN_EPSILON_DECAY_STEPS,
    DQN_EPSILON_END,
    DQN_EPSILON_START,
    DQN_HIDDEN_SIZES,
    DQN_LR,
    DQN_REPLAY_SIZE,
    DQN_TARGET_UPDATE_FREQ,
    RL_FEATURE_DIM,
    RL_GAMMA,
    RL_NUM_ACTIONS,
)


# ---------------------------------------------------------------------------
# Neural network
# ---------------------------------------------------------------------------

class _MLP:
    """Fully-connected ReLU network with a linear output layer.

    Implements forward pass, backward pass (MSE with Huber-style gradient
    clipping), and an Adam optimiser — pure numpy, no autograd.
    """

    def __init__(self, layer_sizes: list[int], lr: float = 1e-3, seed: int = 0):
        rng = np.random.default_rng(seed)
        self.lr = lr
        # Weights: list of (W, b) pairs, one per layer
        self.layers: list[tuple[np.ndarray, np.ndarray]] = []
        prev = layer_sizes[0]
        for h in layer_sizes[1:]:
            # He/Kaiming initialisation for ReLU networks
            W = rng.normal(0.0, math.sqrt(2.0 / prev), (prev, h)).astype(np.float32)
            b = np.zeros(h, dtype=np.float32)
            self.layers.append((W, b))
            prev = h

        # Adam first/second moment estimates
        self.m: list[tuple[np.ndarray, np.ndarray]] = [
            (np.zeros_like(W), np.zeros_like(b)) for W, b in self.layers
        ]
        self.v: list[tuple[np.ndarray, np.ndarray]] = [
            (np.zeros_like(W), np.zeros_like(b)) for W, b in self.layers
        ]
        self._t = 0  # Adam step counter
        self._b1 = 0.9
        self._b2 = 0.999
        self._eps = 1e-8

        # Activation cache (filled during forward, consumed during backward)
        self._cache: list[np.ndarray] = []

    # ------------------------------------------------------------------
    def forward(self, x: np.ndarray) -> np.ndarray:
        """x: (batch, input_dim)  ->  (batch, output_dim), linear output."""
        a = x.astype(np.float32)
        self._cache = [a]
        for W, b in self.layers[:-1]:
            a = np.maximum(0.0, a @ W + b)   # ReLU hidden layer
            self._cache.append(a)
        W, b = self.layers[-1]
        return a @ W + b                      # Linear output (no activation)

    # ------------------------------------------------------------------
    def backward(self, dout: np.ndarray) -> None:
        """Backprop + Adam update.

        dout: (batch, output_dim)  — gradient of the loss w.r.t. the output.
        Gradients are clipped per-element to [-1, 1] (Huber-style) before the
        Adam update to prevent blow-up from large rewards.
        """
        self._t += 1
        n = len(self.layers)
        grads_W: list[np.ndarray] = [None] * n  # type: ignore[list-item]
        grads_b: list[np.ndarray] = [None] * n  # type: ignore[list-item]

        delta = dout.astype(np.float32)

        for i in range(n - 1, -1, -1):
            a_in = self._cache[i]          # input activations for layer i
            W, _ = self.layers[i]
            grads_W[i] = a_in.T @ delta
            grads_b[i] = delta.sum(axis=0)
            if i > 0:
                delta = delta @ W.T
                delta *= (a_in > 0)        # ReLU backward (mask = post-relu > 0)

        # Clip gradients element-wise before Adam
        for i in range(n):
            grads_W[i] = np.clip(grads_W[i], -1.0, 1.0)
            grads_b[i] = np.clip(grads_b[i], -1.0, 1.0)

        t = self._t
        b1, b2, eps = self._b1, self._b2, self._eps
        for i, (gW, gb) in enumerate(zip(grads_W, grads_b)):
            mW, mb = self.m[i]
            vW, vb = self.v[i]
            mW = b1 * mW + (1.0 - b1) * gW
            mb = b1 * mb + (1.0 - b1) * gb
            vW = b2 * vW + (1.0 - b2) * (gW * gW)
            vb = b2 * vb + (1.0 - b2) * (gb * gb)
            self.m[i] = (mW, mb)
            self.v[i] = (vW, vb)
            mW_hat = mW / (1.0 - b1 ** t)
            mb_hat = mb / (1.0 - b1 ** t)
            vW_hat = vW / (1.0 - b2 ** t)
            vb_hat = vb / (1.0 - b2 ** t)
            W, b = self.layers[i]
            self.layers[i] = (
                W - self.lr * mW_hat / (np.sqrt(vW_hat) + eps),
                b - self.lr * mb_hat / (np.sqrt(vb_hat) + eps),
            )

    # ------------------------------------------------------------------
    def copy_weights_from(self, other: "_MLP") -> None:
        self.layers = [(W.copy(), b.copy()) for W, b in other.layers]


# ---------------------------------------------------------------------------
# Replay buffer
# ---------------------------------------------------------------------------

class ReplayBuffer:
    """Circular experience replay buffer storing (s, a, r, s', done) tuples."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self._buf: deque = deque(maxlen=capacity)

    def add(
        self,
        phi: list[float],
        action: int,
        reward: float,
        phi_next: list[float],
        terminal: bool,
    ) -> None:
        self._buf.append((
            np.array(phi,      dtype=np.float32),
            int(action),
            float(reward),
            np.array(phi_next, dtype=np.float32),
            bool(terminal),
        ))

    def sample(self, batch_size: int, rng: random.Random) -> tuple:
        indices = rng.sample(range(len(self._buf)), batch_size)
        batch = [self._buf[i] for i in indices]
        phis, actions, rewards, phis_next, terminals = zip(*batch)
        return (
            np.stack(phis),
            np.array(actions,   dtype=np.int32),
            np.array(rewards,   dtype=np.float32),
            np.stack(phis_next),
            np.array(terminals, dtype=bool),
        )

    def __len__(self) -> int:
        return len(self._buf)


# ---------------------------------------------------------------------------
# DQN agent
# ---------------------------------------------------------------------------

class DQNAgent:
    """Shared DQN trained by all fetcher ants collectively.

    Every ant pushes its (s, a, r, s', done) tuple into a common replay
    buffer.  One gradient step is taken per call to ``update()``.
    """

    def __init__(self) -> None:
        sizes = [RL_FEATURE_DIM] + list(DQN_HIDDEN_SIZES) + [RL_NUM_ACTIONS]
        self.net = _MLP(sizes, lr=DQN_LR, seed=42)
        self.target_net = _MLP(sizes, lr=DQN_LR, seed=42)
        self.target_net.copy_weights_from(self.net)

        self.replay = ReplayBuffer(DQN_REPLAY_SIZE)
        self._gradient_steps = 0      # counts update() calls (drives epsilon & target sync)
        self._rng = random.Random(0)

    # ------------------------------------------------------------------
    @property
    def epsilon(self) -> float:
        """Current exploration probability (decays linearly to DQN_EPSILON_END)."""
        frac = min(1.0, self._gradient_steps / max(1, DQN_EPSILON_DECAY_STEPS))
        return DQN_EPSILON_START + (DQN_EPSILON_END - DQN_EPSILON_START) * frac

    # ------------------------------------------------------------------
    def q_values(self, phi: list[float]) -> np.ndarray:
        x = np.array(phi, dtype=np.float32).reshape(1, -1)
        return self.net.forward(x)[0]

    # ------------------------------------------------------------------
    def pick_action(self, phi: list[float]) -> int:
        """Epsilon-greedy action selection."""
        if self._rng.random() < self.epsilon:
            return self._rng.randrange(RL_NUM_ACTIONS)
        return int(np.argmax(self.q_values(phi)))

    # ------------------------------------------------------------------
    def push(
        self,
        phi: list[float],
        action: int,
        reward: float,
        phi_next: list[float],
        terminal: bool,
    ) -> None:
        self.replay.add(phi, action, reward, phi_next, terminal)

    # ------------------------------------------------------------------
    def update(self) -> Optional[float]:
        """One gradient step on a random mini-batch.  Returns TD loss or None."""
        if len(self.replay) < DQN_BATCH_SIZE:
            return None

        phis, actions, rewards, phis_next, terminals = self.replay.sample(
            DQN_BATCH_SIZE, self._rng
        )

        # Q(s, a) from online network
        q_all = self.net.forward(phis)                          # (B, A)
        q_sa  = q_all[np.arange(DQN_BATCH_SIZE), actions]      # (B,)

        # Target: r + γ · max_a' Q_target(s', a')  (0 if terminal)
        with_target = self.target_net.forward(phis_next)        # (B, A)
        q_next_max  = with_target.max(axis=1)                   # (B,)
        q_target    = rewards + RL_GAMMA * q_next_max * (~terminals)

        # TD error and MSE gradient (Huber clipping applied inside backward)
        td_error = q_sa - q_target                              # (B,)
        dout = np.zeros_like(q_all)
        dout[np.arange(DQN_BATCH_SIZE), actions] = (
            2.0 * td_error / DQN_BATCH_SIZE
        )

        self.net.backward(dout)
        self._gradient_steps += 1

        # Hard target-network update
        if self._gradient_steps % DQN_TARGET_UPDATE_FREQ == 0:
            self.target_net.copy_weights_from(self.net)

        return float(np.mean(td_error ** 2))
