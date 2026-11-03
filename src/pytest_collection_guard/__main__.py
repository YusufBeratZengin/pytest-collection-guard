"""Allow ``python -m pytest_collection_guard``.

The guard below runs only in a real ``python -m`` process; its behavior is
verified end to end by the subprocess test in ``tests/test_cli.py``
(``test_module_entry_point_works``). It carries a ``pragma: no cover`` because
coverage matching for this package cannot trace code executed as the
``__main__`` module from a dynamically loaded file.
"""

from __future__ import annotations

__all__ = ["run"]

from pytest_collection_guard.cli import main


def run() -> int:
    """Run the CLI; the entry point used by ``python -m pytest_collection_guard``."""
    return main()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run())
