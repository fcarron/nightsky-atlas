"""Allow ``python -m nightsky_atlas``."""

from __future__ import annotations

from nightsky_atlas.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
