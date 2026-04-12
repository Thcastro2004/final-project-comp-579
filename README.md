# Ant colony foraging — COMP 579 final project

Continuous 2D simulation of ant-like agents with pheromone communication, rule-based baselines, and (planned) multi-agent reinforcement learning. Course: **COMP 579 — Reinforcement Learning** (McGill, W26).

## Scope

**Research question (from the proposal):** How do decentralized agents learn coordinated behavior when they only sense locally and communicate via pheromones? The project compares **reward structures** (e.g. individualist vs cooperative vs risk-aware variants) on food gathering, survival, exploration, and pheromone use.

**Target simulation:** Fetchers and soldiers in a shared world; actions include movement, pickup, pheromone deposit, and simple combat with respawn; policies may be shared per role within a colony. Training is intended to use **tabular Q-learning or actor-critic** on top of a fixed-step simulation core.

**Course deliverables** (see `docs/instructions/comp579-project-2026.pdf`):

- Short paper (NeurIPS format, up to 4 pages + references)
- Code and any notebooks used to produce results
- Video (≤ 4 minutes)

Submission deadline stated in that handout: **April 24, 11:59pm** (verify on MyCourses if it moves).

**Implementation roadmap:** Phased build is outlined in the local plan *Ant sim implementation order* (skeleton → kinematics → rule-based foraging → many ants / separation → pheromones → roles & combat → HUD / recording → config & seeds → Gym-style API and RL → paper / reproduce notebook / video).

## State of completion (as of this repo)

| Area | Status |
|------|--------|
| Dependencies + entrypoint | Done (`requirements.txt`, `main.py`) |
| World geometry | Done: `World`, `clamp_point`, `contains`, helpers in `ants/world.py` |
| Nest / food entities | Data classes exist; **not** yet wired into a full `step()` loop |
| Viewport / Pygame | Done: letterboxed world→screen mapping; static draw of bounds, nest, food |
| Ants, motion, AI | **Not started** |
| Pheromones | **Not started** |
| Multi-agent collision / roles / combat | **Not started** |
| RL API (reset/step, rewards) | **Not started** |
| Automated tests | **None** yet |
| Paper / notebook / video | **Not started** |

So the codebase is an **early skeleton**: you can run a window that visualizes one nest and one food patch, or print the same setup in headless mode. Everything past “static scene” is still to implement.

## Getting started

**1. Environment**

```bash
cd final-project-comp-579
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**2. Run**

- **Graphical (default):** `python main.py` — window with world border, nest, and food. Quit with **Escape** or closing the window.
- **No display:** `python main.py --headless` — prints world/food/nest parameters (useful later for batch runs / RL).

**3. Layout**

- `main.py` — CLI and Pygame loop (simulation-specific logic should stay out of here as much as possible; core should remain importable without pygame for headless RL).
- `ants/world.py` — world bounds, `Food`, `Nest`, `Viewport`, small math helpers.

## How to test

There is **no test suite** yet. For now:

- Run `python main.py` and confirm the nest and food appear inside the bordered rectangle and scale correctly if you change `WORLD_WIDTH` / `WORLD_HEIGHT` / window size in `main.py`.
- Run `python main.py --headless` and confirm it exits 0 and prints coherent coordinates.

When you add behavior (ants, scoring, RL), add **unit tests** for pure functions in `ants/` (geometry, rewards) and optionally short **smoke scripts** or `pytest` for `reset`/`step` invariants.

## What to do next

1. **Simulation core:** Introduce ant state, fixed `dt` stepping, and boundary handling without growing pygame-dependent code in the core (see plan: “simulation core has zero Pygame imports”).
2. **Rule-based baseline:** Seek / gather / deposit / wander so you have metrics and a baseline before RL.
3. **Pheromones:** Deposit, decay, sense (and visualize).
4. **Roles & combat** (or a minimal shortcut: one channel + fetchers only if time is tight).
5. **RL interface:** Gymnasium-style `reset` / `step`, observation vectors aligned with what rules use, reward modes matching the proposal.
6. **Deliverables:** Experiments + plots → paper; one notebook to reproduce figures; record gameplay / learning curves for the video.

## Documentation and references in this repo

- `docs/instructions/comp579-project-2026.pdf` — official project description and submission requirements.
- `docs/instructions/project-proposal.pdf` — your approved topic, methods, and citation list.
- `docs/ressource/` — background PDFs (e.g. ant colony optimization and related readings); use these for background / citations in the paper.

External course page: https://cs.mcgill.ca/~comp579/W26/
