"""Unit tests for plugin helper functions (no full pytest run needed)."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from pytest_collection_guard.plugin import (
    _GuardRecorder,
    _ini_list,
    _option_sequence,
    _option_str,
    build_collection_args,
    normalize_ignore_args,
    normalize_positional_args,
)


class _FakeConfig:
    """Minimal stand-in exposing just getini/option, as plugin helpers use."""

    def __init__(
        self,
        ini: dict,
        rootpath: Path | None = None,
        args: Sequence[str] = (),
        **options: object,
    ) -> None:
        self._ini = ini
        self.rootpath = rootpath or Path(".")
        self.args = list(args)
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


def test_recorder_is_hashable_and_usable_in_sets() -> None:
    recorder = _GuardRecorder(out_path=Path("m.json"), profile="linux")
    # Plugin instances registered in pluggy must be hashable because subset_hook_caller
    # relies on set operations (intersection_update) across hook implementations.
    assert hash(recorder) == hash(recorder)
    plugin_set = {recorder}
    assert recorder in plugin_set
    removal_set = {recorder, "other"}
    removal_set.intersection_update([recorder])
    assert removal_set == {recorder}


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


def test_option_sequence_handles_missing_str_and_list() -> None:
    config = cast(
        Any,
        _FakeConfig(
            {},
            ignore=["tests/old", "tests/legacy"],
            single="tests/single",
            empty=[],
            missing=None,
        ),
    )
    assert _option_sequence(config, "ignore") == ("tests/old", "tests/legacy")
    assert _option_sequence(config, "single") == ("tests/single",)
    assert _option_sequence(config, "empty") == ()
    assert _option_sequence(config, "missing") == ()
    assert _option_sequence(config, "not_there") == ()


def test_build_collection_args_snapshots_all_options(tmp_path: Path) -> None:
    root = tmp_path
    config = cast(
        Any,
        _FakeConfig(
            {
                "testpaths": ["tests"],
                "norecursedirs": [".git"],
                "python_files": ["test_*.py"],
                "python_classes": ["Test*"],
                "python_functions": ["test_*"],
            },
            rootpath=root,
            args=[str(root / "tests" / "unit")],
            keyword="shop",
            markexpr="not slow",
            ignore=[str(root / "tests" / "legacy"), "tests/old"],
            ignore_glob=["tests/legacy/*.py"],
            deselect=["tests/test_a.py::test_one"],
        ),
    )
    args = build_collection_args(config)
    assert args.testpaths == ("tests",)
    assert args.positional_args == ("tests/unit",)
    assert args.keyword == "shop"
    assert args.markexpr == "not slow"
    assert args.ignore == ("tests/legacy", "tests/old")
    assert args.ignore_glob == ("tests/legacy/*.py",)
    assert args.deselect == ("tests/test_a.py::test_one",)


def test_normalize_ignore_args_resolves_relative_paths_from_invocation_dir(
    tmp_path: Path,
) -> None:
    """The same ignore target typed from two cwds gets one identity."""
    rootdir = tmp_path
    from_root = normalize_ignore_args(["tests/slow"], rootdir, rootdir)
    from_tests_dir = normalize_ignore_args(["slow"], rootdir / "tests", rootdir)
    assert from_root == ("tests/slow",)
    assert from_tests_dir == ("tests/slow",)


def test_normalize_ignore_args_keeps_resolved_scope_distinct(tmp_path: Path) -> None:
    """The same literal string from another cwd can mean a different path."""
    rootdir = tmp_path
    from_root = normalize_ignore_args(["tests/slow"], rootdir, rootdir)
    from_tests_dir = normalize_ignore_args(["tests/slow"], rootdir / "tests", rootdir)
    assert from_root == ("tests/slow",)
    assert from_tests_dir == ("tests/tests/slow",)
    assert from_root != from_tests_dir
