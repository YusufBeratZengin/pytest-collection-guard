"""Allow ``python -m pytest_collection_guard``."""

from __future__ import annotations

from pytest_collection_guard.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
