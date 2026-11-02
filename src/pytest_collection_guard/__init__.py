"""pytest-collection-guard.

Turn unexpected pytest collection drift (lost test IDs) into a CI failure.

Public surface:

* the pytest plugin (``pytest_collection_guard.plugin``, opt-in via
  ``--collection-guard-out``) that records collected test identities to a
  JSON manifest;
* the ``pytest-collection-guard`` CLI (``pytest_collection_guard.cli``)
  that compares two manifests and enforces a justified-removal policy.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
