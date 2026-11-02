"""Shared fixtures for the test suite."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pytest

from pytest_collection_guard.manifest import (
    STATUS_OK,
    CollectionArgs,
    Environment,
    Manifest,
    save_manifest,
)


@pytest.fixture
def make_manifest():
    """Factory for synthetic manifests (identity + environment kept separate)."""

    def _make(
        *,
        selected: Sequence[str] = ("tests/test_a.py::test_one",),
        deselected: Sequence[str] = (),
        profile: str = "linux",
        status: str = STATUS_OK,
        errors: Sequence[str] = (),
        collection_args: CollectionArgs | None = None,
    ) -> Manifest:
        return Manifest(
            selected=tuple(selected),
            deselected=tuple(deselected),
            environment=Environment(profile=profile),
            collection_args=collection_args
            or CollectionArgs(testpaths=("tests",), python_files=("test_*.py",)),
            status=status,
            errors=tuple(errors),
        )

    return _make


@pytest.fixture
def write_manifest(tmp_path: Path):
    """Save a manifest under tmp_path; returns the file path."""

    def _write(manifest: Manifest, name: str = "manifest.json") -> Path:
        path = tmp_path / name
        save_manifest(path, manifest)
        return path

    return _write
