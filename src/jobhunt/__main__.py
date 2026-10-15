"""Allow running the tracker with ``python -m jobhunt``."""

from jobhunt.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
