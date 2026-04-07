import argparse
import sys


def run_headless() -> int:
    print("Headless mode: no display (batch / RL later).")
    return 0


def run_window() -> int:
    import pygame

    pygame.init()
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("Ant colony sim")
    clock = pygame.time.Clock()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                running = False
        screen.fill((20, 24, 32))
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
