"""Justified-removal policy.

A removal may only disappear from the inventory silently if it is listed in a
TOML allow file with a written reason. The allow file is reviewed like code:

.. code-block:: toml

    [[removal]]
    id = "tests/test_checkout.py::test_apply_discount"
    reason = "Feature dropped in 2.0 (issue #123, decided 2026-10-31)."

Rules enforced here:

* every entry needs a non-empty ``id`` and a non-empty ``reason``;
* entries must be unique and use no unknown keys;
* an allowlist entry whose test did *not* actually disappear is reported as
  stale, so the file cannot silently rot into a blanket ignore.

Adding new tests never offsets removals — see :mod:`pytest_collection_guard.diff`.
"""

from __future__ import annotations

__all__ = [
    "PolicyDecision",
    "PolicyError",
    "RemovalEntry",
    "RemovalPolicy",
    "evaluate_removals",
    "load_policy",
]

import tomllib
from dataclasses import dataclass
from pathlib import Path


class PolicyError(ValueError):
    """The allow file is missing, malformed or violates the policy format."""


@dataclass(frozen=True)
class RemovalEntry:
    """One approved removal: which test, and why its loss is expected."""

    id: str
    reason: str


@dataclass(frozen=True)
class RemovalPolicy:
    """All approved removals, keyed by test node ID."""

    entries: tuple[RemovalEntry, ...] = ()

    def get(self, test_id: str) -> RemovalEntry | None:
        for entry in self.entries:
            if entry.id == test_id:
                return entry
        return None

    def ids(self) -> frozenset[str]:
        return frozenset(entry.id for entry in self.entries)


@dataclass(frozen=True)
class PolicyDecision:
    """Outcome of applying a policy to the removed test IDs."""

    allowed_removals: tuple[tuple[str, str], ...]  # (id, reason)
    unapproved_removals: tuple[str, ...]
    stale_entries: tuple[str, ...]  # allowlisted ids that did not disappear

    @property
    def has_unapproved_removals(self) -> bool:
        return bool(self.unapproved_removals)


_KNOWN_KEYS = frozenset({"id", "reason"})


def load_policy(path: str | Path) -> RemovalPolicy:
    """Read a justified-removal allow file (TOML)."""
    target = Path(path)
    if not target.is_file():
        raise PolicyError(f"allow file not found: {target}")
    try:
        data = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise PolicyError(f"{target}: not valid TOML ({exc})") from exc

    unknown_top = set(data) - {"removal"}
    if unknown_top:
        raise PolicyError(
            f"{target}: unknown top-level key(s) {sorted(unknown_top)!r}; "
            f"only [[removal]] tables are allowed"
        )

    raw_entries = data.get("removal", [])
    if not isinstance(raw_entries, list):
        raise PolicyError(f"{target}: 'removal' must be an array of tables ([[removal]])")

    entries: list[RemovalEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_entries):
        ctx = f"{target}: [[removal]] #{index + 1}"
        if not isinstance(raw, dict):
            raise PolicyError(f"{ctx}: expected a table with 'id' and 'reason'")
        unknown = set(raw) - _KNOWN_KEYS
        if unknown:
            raise PolicyError(f"{ctx}: unknown key(s) {sorted(unknown)!r}")
        entry_id = raw.get("id")
        reason = raw.get("reason")
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise PolicyError(f"{ctx}: 'id' must be a non-empty string")
        if not isinstance(reason, str) or not reason.strip():
            raise PolicyError(f"{ctx}: 'reason' must be a non-empty string (justify the removal)")
        if entry_id in seen:
            raise PolicyError(f"{ctx}: duplicate id {entry_id!r}")
        seen.add(entry_id)
        entries.append(RemovalEntry(id=entry_id, reason=reason.strip()))

    return RemovalPolicy(entries=tuple(entries))


def evaluate_removals(removed: tuple[str, ...], policy: RemovalPolicy) -> PolicyDecision:
    """Split removed IDs into approved vs unapproved, and flag stale entries."""
    allowed: list[tuple[str, str]] = []
    unapproved: list[str] = []
    for test_id in removed:
        entry = policy.get(test_id)
        if entry is None:
            unapproved.append(test_id)
        else:
            allowed.append((test_id, entry.reason))
    stale = tuple(sorted(policy.ids() - set(removed)))
    return PolicyDecision(
        allowed_removals=tuple(allowed),
        unapproved_removals=tuple(unapproved),
        stale_entries=stale,
    )
