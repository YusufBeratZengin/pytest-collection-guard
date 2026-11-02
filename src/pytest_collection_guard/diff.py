"""Set-difference engine for two collection manifests.

The engine never reduces a run to counts ("100 tests passed") — it compares
the actual node ID sets. Two invariants matter:

* an addition never cancels a removal (adding ``test_b`` does not hide that
  ``test_a`` disappeared);
* when the baseline and current runs disagree on profile or collection
  arguments, the diff is *not comparable*: loss reporting is refused because
  the two inventories describe different collection scopes.
"""

from __future__ import annotations

__all__ = ["ManifestDiff", "compare_manifests"]

from dataclasses import dataclass

from pytest_collection_guard.manifest import Manifest


@dataclass(frozen=True)
class ManifestDiff:
    """Result of comparing a baseline manifest against a current manifest."""

    environment_mismatches: tuple[str, ...]
    removed: tuple[str, ...]
    added: tuple[str, ...]
    moved_to_deselected: tuple[str, ...]
    baseline_selected_count: int
    current_selected_count: int

    @property
    def comparable(self) -> bool:
        """False when profiles/collection args differ (diff would be misleading)."""
        return not self.environment_mismatches


def compare_manifests(baseline: Manifest, current: Manifest) -> ManifestDiff:
    """Compare two manifests by test identity.

    Both manifests must already be valid inventories (``status == "ok"``);
    callers such as the CLI reject error manifests before getting here.
    """
    environment_mismatches = baseline.environment.mismatches(
        current.environment
    ) + baseline.collection_args.mismatches(current.collection_args)

    baseline_selected = set(baseline.selected)
    current_selected = set(current.selected)
    current_deselected = set(current.deselected)

    removed = tuple(sorted(baseline_selected - current_selected))
    added = tuple(sorted(current_selected - baseline_selected))
    # Removed tests that still exist but were deselected in the current run
    # are usually a selection change (-k/-m) rather than deletion — still a
    # loss of coverage, but reported with a hint.
    moved_to_deselected = tuple(sorted(set(removed) & current_deselected))

    return ManifestDiff(
        environment_mismatches=environment_mismatches,
        removed=removed,
        added=added,
        moved_to_deselected=moved_to_deselected,
        baseline_selected_count=len(baseline_selected),
        current_selected_count=len(current_selected),
    )
