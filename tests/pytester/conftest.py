"""Fixtures for in-process pytester integration tests.

Nested pytest runs are hermetic: plugin autoload is disabled and the plugin is
loaded explicitly via ``-p pytest_collection_guard.plugin``, so the tests work
whether or not the package is installed (no entry-point double registration).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from pytest_collection_guard.manifest import Manifest, load_manifest

_SRC = Path(__file__).resolve().parents[2] / "src"


@pytest.fixture(autouse=True)
def _hermetic_nested_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.syspath_prepend(str(_SRC))
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")


@pytest.fixture
def guard_run(pytester: pytest.Pytester) -> Callable[..., pytest.RunResult]:
    """Run pytest (nested, in-process) with the collection guard enabled."""

    def _run(
        *extra_args: str,
        out: str = "manifest.json",
        profile: str = "linux",
        guard: bool = True,
        collect_only: bool = True,
    ) -> pytest.RunResult:
        argv: list[str] = ["--collect-only", "-q"] if collect_only else ["-q"]
        if guard:
            argv += [f"--collection-guard-out={out}", f"--collection-guard-profile={profile}"]
        argv += ["-p", "pytest_collection_guard.plugin", *extra_args]
        return pytester.runpytest(*argv)

    return _run


@pytest.fixture
def read_manifest(pytester: pytest.Pytester) -> Callable[[str], Manifest]:
    def _read(name: str = "manifest.json") -> Manifest:
        return load_manifest(pytester.path / name)

    return _read


@pytest.fixture
def write_test_file(pytester: pytest.Pytester) -> Callable[[str, str], Path]:
    def _write(relpath: str, content: str) -> Path:
        path = pytester.path / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    return _write
