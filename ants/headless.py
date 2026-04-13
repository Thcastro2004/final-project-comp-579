from ants.config import WORLD_HEIGHT, WORLD_WIDTH
from ants.world import World


def run_headless() -> int:
    world = World(WORLD_WIDTH, WORLD_HEIGHT)
    print("Headless mode: no display (batch / RL later).")
    print(f"World: {world.width} x {world.height}")
    return 0
