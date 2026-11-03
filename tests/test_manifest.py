"""Unit tests for the manifest schema (identity vs environment)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pytest_collection_guard.manifest import (
    SCHEMA_VERSION,
    STATUS_ERROR,
    CollectionArgs,
    Environment,
    ManifestError,
    load_manifest,
    manifest_from_dict,
    manifest_to_dict,
    save_manifest,
)


def _valid_dict() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": "pytest-collection-guard", "version": "0.1.0"},
        "status": "ok",
        "identity": {
            "selected": ["tests/test_b.py::test_x", "tests/test_a.py::test_y"],
            "deselected": ["tests/test_a.py::test_z"],
        },
        "environment": {
            "profile": "linux",
            "platform": "Linux-0000-example",
            "python_version": "3.11.0",
            "pytest_version": "8.0.0",
            "rootdir": "/example/project",
        },
        "collection_args": {
            "testpaths": ["tests"],
            "norecursedirs": [".git"],
            "python_files": ["test_*.py"],
            "python_classes": ["Test*"],
            "python_functions": ["test_*"],
            "positional_args": ["tests"],
            "keyword": None,
            "markexpr": None,
            "ignore": [],
            "ignore_glob": [],
            "deselect": [],
        },
        "errors": [],
    }


# ---------------------------------------------------------------------------
# round trips
# ---------------------------------------------------------------------------


def test_manifest_round_trip_preserves_everything(tmp_path: Path) -> None:
    manifest = manifest_from_dict(_valid_dict())
    path = tmp_path / "nested" / "dir" / "m.json"
    save_manifest(path, manifest)

    loaded = load_manifest(path)
    assert loaded == manifest
    # identity is sorted for deterministic diffs
    assert loaded.selected == ("tests/test_a.py::test_y", "tests/test_b.py::test_x")
    assert loaded.deselected == ("tests/test_a.py::test_z",)
    assert loaded.environment.profile == "linux"
    assert loaded.is_valid_inventory


def test_manifest_to_dict_keeps_identity_and_environment_apart() -> None:
    manifest = manifest_from_dict(_valid_dict())
    data = manifest_to_dict(manifest)
    assert set(data["identity"]) == {"selected", "deselected"}
    assert "profile" in data["environment"]
    assert "selected" not in data["environment"]
    assert data["tool"]["name"] == "pytest-collection-guard"
    assert data["schema_version"] == SCHEMA_VERSION


def test_error_status_round_trip(make_manifest) -> None:
    manifest = make_manifest(status=STATUS_ERROR, errors=("tests/test_a.py: boom",))
    loaded = manifest_from_dict(manifest_to_dict(manifest))
    assert loaded.status == STATUS_ERROR
    assert loaded.errors == ("tests/test_a.py: boom",)
    assert not loaded.is_valid_inventory


# ---------------------------------------------------------------------------
# validation error paths
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.pop("schema_version"), "missing required key 'schema_version'"),
        (lambda d: d.update(schema_version=99), "unsupported schema_version"),
        (lambda d: d.pop("status"), "missing required key 'status'"),
        (lambda d: d.update(status="weird"), "unknown status"),
        (lambda d: d.pop("identity"), "missing required key 'identity'"),
        (lambda d: d.update(identity=[]), "expected an object"),
        (lambda d: d["identity"].pop("selected"), "missing required key 'selected'"),
        (lambda d: d["identity"].update(selected="nope"), "expected a list of strings"),
        (lambda d: d["identity"].update(selected=[1, 2]), "expected a list of strings"),
        (lambda d: d.pop("environment"), "missing required key 'environment'"),
        (lambda d: d["environment"].pop("profile"), "missing required key 'profile'"),
        (lambda d: d["environment"].update(profile=5), "expected a string"),
        (lambda d: d.pop("collection_args"), "missing required key 'collection_args'"),
        (lambda d: d["collection_args"].pop("testpaths"), "missing required key 'testpaths'"),
        (lambda d: d["collection_args"].update(keyword=5), "expected a string"),
        (lambda d: d["collection_args"].update(ignore="nope"), "expected a list of strings"),
        (lambda d: d["collection_args"].update(ignore_glob="nope"), "expected a list of strings"),
        (lambda d: d["collection_args"].update(deselect="nope"), "expected a list of strings"),
        (lambda d: d.update(errors="nope"), "expected a list of strings"),
    ],
)
def test_manifest_from_dict_rejects_bad_input(mutate, message: str) -> None:
    raw = _valid_dict()
    mutate(raw)
    with pytest.raises(ManifestError, match=message.replace("(", r"\(").replace(")", r"\)")):
        manifest_from_dict(raw)


def test_manifest_from_dict_rejects_non_mapping() -> None:
    with pytest.raises(ManifestError, match="expected an object"):
        manifest_from_dict(["not", "a", "manifest"])


def test_load_manifest_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ManifestError, match="manifest file not found"):
        load_manifest(tmp_path / "nope.json")


def test_load_manifest_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ManifestError, match="not valid JSON"):
        load_manifest(path)


def test_load_manifest_prefixes_path_in_error(tmp_path: Path) -> None:
    path = tmp_path / "wrong_schema.json"
    path.write_text(json.dumps({"schema_version": 7}), encoding="utf-8")
    with pytest.raises(ManifestError, match=r"wrong_schema\.json"):
        load_manifest(path)


# ---------------------------------------------------------------------------
# environment / collection arg comparisons
# ---------------------------------------------------------------------------


def test_environment_mismatches_only_on_profile() -> None:
    a = Environment(profile="linux", platform="Linux-1", rootdir="/a")
    b = Environment(profile="linux", platform="Windows-2", rootdir="/b")
    assert a.mismatches(b) == ()  # portability: recorded, not enforced

    other = Environment(profile="windows")
    issues = a.mismatches(other)
    assert len(issues) == 1
    assert "profile differs" in issues[0]


def test_collection_args_mismatches_every_enforced_field() -> None:
    base = CollectionArgs(
        testpaths=("tests",),
        norecursedirs=(".git",),
        python_files=("test_*.py",),
        python_classes=("Test*",),
        python_functions=("test_*",),
        positional_args=("tests",),
        keyword="one",
        markexpr="slow",
    )
    assert base.mismatches(base) == ()

    changed = CollectionArgs(
        testpaths=("other",),
        norecursedirs=(".git",),
        python_files=("test_*.py",),
        python_classes=("Test*",),
        python_functions=("test_*",),
        positional_args=("tests",),
        keyword="two",
        markexpr="slow",
    )
    issues = base.mismatches(changed)
    assert len(issues) == 2
    assert any("testpaths differ" in issue for issue in issues)
    assert any("keyword differ" in issue for issue in issues)

    changed_mark = CollectionArgs(markexpr=None)
    issues = changed_mark.mismatches(CollectionArgs(markexpr="fast"))
    assert any("markexpr differ" in issue for issue in issues)

    for field, value in (
        ("norecursedirs", ("x",)),
        ("python_files", ("x",)),
        ("python_classes", ("x",)),
        ("python_functions", ("x",)),
        ("ignore", ("tests/old",)),
        ("ignore_glob", ("*_skip.py",)),
        ("deselect", ("tests/test_a.py::test_one",)),
    ):
        flipped = CollectionArgs(**{field: value})  # type: ignore[arg-type]
        assert any(field in issue for issue in flipped.mismatches(CollectionArgs()))

    flipped_args = CollectionArgs(positional_args=("unit",))
    assert any("positional_args" in issue for issue in flipped_args.mismatches(CollectionArgs()))


def test_save_manifest_atomic_write_and_cleanup(tmp_path: Path, make_manifest, monkeypatch) -> None:
    path = tmp_path / "manifest.json"
    manifest1 = make_manifest(selected=("tests/test_a.py::test_one",))
    save_manifest(path, manifest1)
    assert load_manifest(path) == manifest1

    # Overwrite atomically with manifest2
    manifest2 = make_manifest(selected=("tests/test_a.py::test_two",))
    save_manifest(path, manifest2)
    assert load_manifest(path) == manifest2

    # Simulated failure during write: target must remain intact, temp files cleaned up
    def _failing_replace(src, dst):
        raise OSError("simulated disk error during replace")

    monkeypatch.setattr("os.replace", _failing_replace)
    with pytest.raises(OSError, match="simulated disk error"):
        save_manifest(path, manifest1)

    # Original manifest2 still intact
    assert load_manifest(path) == manifest2
    # No temporary files left behind in directory
    temp_files = list(tmp_path.glob(".*.tmp"))
    assert temp_files == []


def test_save_manifest_failure_before_tmp_created(
    tmp_path: Path, make_manifest, monkeypatch
) -> None:
    path = tmp_path / "manifest.json"
    manifest = make_manifest()

    def _failing_temp(*args, **kwargs):
        raise OSError("cannot create temp file")

    monkeypatch.setattr("tempfile.NamedTemporaryFile", _failing_temp)
    with pytest.raises(OSError, match="cannot create temp file"):
        save_manifest(path, manifest)
