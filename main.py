import argparse
import sys

from ants.world import Food, Nest, Viewport, World

# World size in abstract units (shown as a letterboxed rectangle on screen).
WORLD_WIDTH = 800.0
WORLD_HEIGHT = 600.0
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600


def run_headless() -> int:
    world = World(WORLD_WIDTH, WORLD_HEIGHT)
    food = Food(x=520.0, y=180.0, remaining=100.0, pickup_radius=36.0)
    nest = Nest(x=140.0, y=420.0, radius=42.0)
    print("Headless mode: no display (batch / RL later).")
    print(f"World: {world.width} x {world.height}")
    print(f"Food: ({food.x}, {food.y}) remaining={food.remaining} r={food.pickup_radius}")
    print(f"Nest: ({nest.x}, {nest.y}) r={nest.radius}")
    return 0


def run_window() -> int:
    import pygame

    world = World(WORLD_WIDTH, WORLD_HEIGHT)
    viewport = Viewport(world, WINDOW_WIDTH, WINDOW_HEIGHT)
    food = Food(x=520.0, y=180.0, remaining=100.0, pickup_radius=36.0)
    nest = Nest(x=140.0, y=420.0, radius=42.0)

    pygame.init()
    screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
    pygame.display.set_caption("Ant colony sim")
    clock = pygame.time.Clock()
    border_color = (120, 140, 160)
    nest_fill = (55, 48, 40)
    nest_outline = (110, 92, 72)
    food_fill = (72, 160, 90)
    food_outline = (120, 210, 130)
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
        screen.fill((20, 24, 32))
        rx, ry, rw, rh = viewport.world_rect_screen()
        pygame.draw.rect(screen, border_color, (rx, ry, rw, rh), width=2)
        nx, ny = viewport.world_to_screen(nest.x, nest.y)
        nr = viewport.world_dist_to_screen(nest.radius)
        pygame.draw.circle(screen, nest_fill, (nx, ny), nr)
        pygame.draw.circle(screen, nest_outline, (nx, ny), nr, width=2)
        fx, fy = viewport.world_to_screen(food.x, food.y)
        fr = viewport.world_dist_to_screen(food.pickup_radius)
        pygame.draw.circle(screen, food_fill, (fx, fy), fr)
        pygame.draw.circle(screen, food_outline, (fx, fy), fr, width=2)
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ant colony simulation")
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run without opening a window.",
    )
    args = parser.parse_args()
    if args.headless:
        return run_headless()
    return run_window()


if __name__ == "__main__":
    sys.exit(main())
