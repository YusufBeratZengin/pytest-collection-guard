"""Unit tests for plugin helper functions (no full pytest run needed)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from pytest_collection_guard.plugin import (
    _GuardRecorder,
    _ini_list,
    _option_str,
    normalize_positional_args,
)


class _FakeConfig:
    """Minimal stand-in exposing just getini/option, as plugin helpers use."""

    def __init__(self, ini: dict, **options: object) -> None:
        self._ini = ini
        self.option = SimpleNamespace(**options)

    def getini(self, name: str) -> object:
        if name not in self._ini:
            raise ValueError(f"unknown ini option: {name}")
        return self._ini[name]


def test_ini_list_handles_missing_str_and_list_values() -> None:
    config = cast(
        Any, _FakeConfig({"testpaths": ["tests", "integration"], "python_files": "test_*.py"})
    )
    assert _ini_list(config, "testpaths") == ("tests", "integration")
    assert _ini_list(config, "python_files") == ("test_*.py",)
    assert _ini_list(config, "norecursedirs") == ()  # missing -> empty


def test_option_str_handles_missing_empty_and_real_values() -> None:
    config = cast(Any, _FakeConfig({}, keyword="one", markexpr="  ", other=None))
    assert _option_str(config, "keyword") == "one"
    assert _option_str(config, "markexpr") is None  # blank -> None
    assert _option_str(config, "other") is None
    assert _option_str(config, "nonexistent") is None


def test_recorder_internal_errors_are_recorded() -> None:
    recorder = _GuardRecorder(out_path=Path("m.json"), profile="linux")
    recorder.pytest_internalerror("example repr", None)  # type: ignore[arg-type]
    assert recorder.errors == ["internal error: example repr"]


def test_relative_args_kept_as_given(tmp_path: Path) -> None:
    assert normalize_positional_args(["tests/unit", "tests/it"], tmp_path) == (
        "tests/unit",
        "tests/it",
    )


def test_absolute_args_inside_rootdir_become_relative(tmp_path: Path) -> None:
    target = tmp_path / "tests" / "unit"
    result = normalize_positional_args([str(target)], tmp_path)
    assert result == ("tests/unit",)


def test_absolute_args_outside_rootdir_kept_portable(tmp_path: Path) -> None:
    outside = tmp_path.parent / "elsewhere" / "tests"
    result = normalize_positional_args([str(outside)], tmp_path)
    # kept, but always with forward slashes (Windows path pitfall)
    assert result == (outside.as_posix(),)


def test_no_args_is_empty() -> None:
    assert normalize_positional_args([], Path("/example")) == ()
