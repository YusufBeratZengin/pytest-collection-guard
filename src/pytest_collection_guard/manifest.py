"""Manifest schema: strict separation of test identity and environment.

A manifest is a JSON document with two kinds of data that are never mixed:

* ``identity`` -- *which* test node IDs pytest selected and deselected. This
  is the data that gets compared between runs.
* ``environment`` -- *where and how* collection ran (profile label, platform,
  Python/pytest versions) plus the collection-affecting arguments and
  settings (``testpaths``, naming rules, ``-k``/``-m``, positional args).

Comparing manifests from different profiles or with different collection
arguments is a *comparison error*, not test loss: :mod:`pytest_collection_guard.diff`
refuses to report losses until the environments line up.

A manifest produced by a run that hit collection errors carries
``status == "error"`` and is not a valid inventory: the guard never treats a
partial, broken collection as evidence that tests are gone.
"""

from __future__ import annotations

__all__ = [
    "SCHEMA_VERSION",
    "STATUS_ERROR",
    "STATUS_OK",
    "CollectionArgs",
    "Environment",
    "Manifest",
    "ManifestError",
    "load_manifest",
    "manifest_from_dict",
    "manifest_to_dict",
    "save_manifest",
]

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
TOOL_NAME = "pytest-collection-guard"

STATUS_OK = "ok"
STATUS_ERROR = "error"


class ManifestError(ValueError):
    """A manifest is missing, unreadable, malformed or from another schema."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _require(mapping: dict[str, Any], key: str, ctx: str) -> Any:
    if key not in mapping:
        raise ManifestError(f"{ctx}: missing required key {key!r}")
    return mapping[key]


def _as_str(value: Any, ctx: str) -> str:
    if not isinstance(value, str):
        raise ManifestError(f"{ctx}: expected a string, got {type(value).__name__}")
    return value


def _as_opt_str(value: Any, ctx: str) -> str | None:
    if value is None:
        return None
    return _as_str(value, ctx)


def _as_str_tuple(value: Any, ctx: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ManifestError(f"{ctx}: expected a list of strings")
    return tuple(value)


def _as_mapping(value: Any, ctx: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{ctx}: expected an object")
    return value


# ---------------------------------------------------------------------------
# environment + collection arguments
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Environment:
    """Where and how the collection run happened.

    Compared field is only ``profile``: ``platform``/``python_version``/
    ``pytest_version``/``rootdir`` are recorded for humans and deliberately
    not enforced, so a manifest stays portable across machines.
    """

    profile: str
    platform: str = ""
    python_version: str = ""
    pytest_version: str = ""
    rootdir: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "platform": self.platform,
            "python_version": self.python_version,
            "pytest_version": self.pytest_version,
            "rootdir": self.rootdir,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> Environment:
        data = _as_mapping(raw, "environment")
        return cls(
            profile=_as_str(_require(data, "profile", "environment"), "environment.profile"),
            platform=_as_str(data.get("platform", ""), "environment.platform"),
            python_version=_as_str(data.get("python_version", ""), "environment.python_version"),
            pytest_version=_as_str(data.get("pytest_version", ""), "environment.pytest_version"),
            rootdir=_as_str(data.get("rootdir", ""), "environment.rootdir"),
        )

    def mismatches(self, other: Environment) -> tuple[str, ...]:
        """Compatibility problems between two runs (empty when comparable)."""
        issues: list[str] = []
        if self.profile != other.profile:
            issues.append(f"profile differs: baseline={self.profile!r} current={other.profile!r}")
        return tuple(issues)


@dataclass(frozen=True)
class CollectionArgs:
    """Arguments and settings that change *which* tests are collected.

    Anything listed here participates in the comparability check: if two
    manifests disagree on these, a diff would mix apples and oranges, so the
    guard reports a mismatch (exit 2) instead of test loss.
    """

    testpaths: tuple[str, ...] = ()
    norecursedirs: tuple[str, ...] = ()
    python_files: tuple[str, ...] = ()
    python_classes: tuple[str, ...] = ()
    python_functions: tuple[str, ...] = ()
    positional_args: tuple[str, ...] = ()
    keyword: str | None = None
    markexpr: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "testpaths": list(self.testpaths),
            "norecursedirs": list(self.norecursedirs),
            "python_files": list(self.python_files),
            "python_classes": list(self.python_classes),
            "python_functions": list(self.python_functions),
            "positional_args": list(self.positional_args),
            "keyword": self.keyword,
            "markexpr": self.markexpr,
        }

    @classmethod
    def from_dict(cls, raw: Any) -> CollectionArgs:
        data = _as_mapping(raw, "collection_args")
        return cls(
            testpaths=_as_str_tuple(
                _require(data, "testpaths", "collection_args"), "collection_args.testpaths"
            ),
            norecursedirs=_as_str_tuple(
                _require(data, "norecursedirs", "collection_args"), "collection_args.norecursedirs"
            ),
            python_files=_as_str_tuple(
                _require(data, "python_files", "collection_args"), "collection_args.python_files"
            ),
            python_classes=_as_str_tuple(
                _require(data, "python_classes", "collection_args"),
                "collection_args.python_classes",
            ),
            python_functions=_as_str_tuple(
                _require(data, "python_functions", "collection_args"),
                "collection_args.python_functions",
            ),
            positional_args=_as_str_tuple(
                _require(data, "positional_args", "collection_args"),
                "collection_args.positional_args",
            ),
            keyword=_as_opt_str(data.get("keyword"), "collection_args.keyword"),
            markexpr=_as_opt_str(data.get("markexpr"), "collection_args.markexpr"),
        )

    def mismatches(self, other: CollectionArgs) -> tuple[str, ...]:
        """Human-readable differences that make a comparison invalid."""
        issues: list[str] = []
        for name in (
            "testpaths",
            "norecursedirs",
            "python_files",
            "python_classes",
            "python_functions",
            "positional_args",
        ):
            mine: tuple[str, ...] = getattr(self, name)
            theirs: tuple[str, ...] = getattr(other, name)
            if mine != theirs:
                issues.append(f"{name} differ: baseline={list(mine)} current={list(theirs)}")
        for name in ("keyword", "markexpr"):
            mine_opt: str | None = getattr(self, name)
            theirs_opt: str | None = getattr(other, name)
            if mine_opt != theirs_opt:
                issues.append(f"{name} differ: baseline={mine_opt!r} current={theirs_opt!r}")
        return tuple(issues)


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Manifest:
    """A single collection run: identities plus environment plus integrity."""

    selected: tuple[str, ...]
    deselected: tuple[str, ...]
    environment: Environment
    collection_args: CollectionArgs = field(default_factory=CollectionArgs)
    status: str = STATUS_OK
    errors: tuple[str, ...] = ()

    @property
    def is_valid_inventory(self) -> bool:
        """Only a completed, error-free collection may be used as an inventory."""
        return self.status == STATUS_OK


def manifest_to_dict(manifest: Manifest) -> dict[str, Any]:
    from pytest_collection_guard import __version__

    return {
        "schema_version": SCHEMA_VERSION,
        "tool": {"name": TOOL_NAME, "version": __version__},
        "status": manifest.status,
        "identity": {
            "selected": list(manifest.selected),
            "deselected": list(manifest.deselected),
        },
        "environment": manifest.environment.to_dict(),
        "collection_args": manifest.collection_args.to_dict(),
        "errors": list(manifest.errors),
    }


def manifest_from_dict(raw: Any) -> Manifest:
    data = _as_mapping(raw, "manifest")
    schema_version = _require(data, "schema_version", "manifest")
    if schema_version != SCHEMA_VERSION:
        raise ManifestError(
            f"manifest: unsupported schema_version {schema_version!r} "
            f"(this tool reads version {SCHEMA_VERSION})"
        )
    status = _as_str(_require(data, "status", "manifest"), "manifest.status")
    if status not in (STATUS_OK, STATUS_ERROR):
        raise ManifestError(f"manifest.status: unknown status {status!r}")
    identity = _as_mapping(_require(data, "identity", "manifest"), "manifest.identity")
    return Manifest(
        selected=tuple(
            sorted(_as_str_tuple(_require(identity, "selected", "identity"), "identity.selected"))
        ),
        deselected=tuple(
            sorted(
                _as_str_tuple(_require(identity, "deselected", "identity"), "identity.deselected")
            )
        ),
        environment=Environment.from_dict(_require(data, "environment", "manifest")),
        collection_args=CollectionArgs.from_dict(_require(data, "collection_args", "manifest")),
        status=status,
        errors=_as_str_tuple(data.get("errors", []), "manifest.errors"),
    )


def save_manifest(path: str | Path, manifest: Manifest) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(manifest_to_dict(manifest), indent=2, sort_keys=False) + "\n"
    target.write_text(text, encoding="utf-8")


def load_manifest(path: str | Path) -> Manifest:
    target = Path(path)
    if not target.is_file():
        raise ManifestError(f"manifest file not found: {target}")
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"{target}: not valid JSON ({exc.msg})") from exc
    try:
        return manifest_from_dict(raw)
    except ManifestError as exc:
        raise ManifestError(f"{target}: {exc}") from exc
