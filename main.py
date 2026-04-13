import argparse
import sys

from ants.app import run_window
from ants.headless import run_headless


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
