"""``pytest-collection-guard`` CLI: compare manifests and enforce policy.

Exit-code contract (usable directly as a CI gate):

* ``0`` -- no unapproved removals (clean, or all removals justified);
* ``1`` -- at least one test disappeared from collection without approval;
* ``2`` -- comparison refused: profile/collection-argument mismatch, a
  manifest produced by an errored collection, or invalid input.

The engine never lets additions offset removals: a new test does not cancel
the fact that an expected one is gone.
"""

from __future__ import annotations

__all__ = ["EXIT_MISMATCH", "EXIT_OK", "EXIT_REMOVALS", "main"]

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from pytest_collection_guard.diff import ManifestDiff, compare_manifests
from pytest_collection_guard.manifest import (
    STATUS_OK,
    CollectionArgs,
    Environment,
    Manifest,
    ManifestError,
    load_manifest,
    save_manifest,
)
from pytest_collection_guard.policy import (
    PolicyDecision,
    PolicyError,
    RemovalPolicy,
    evaluate_removals,
    load_policy,
)

EXIT_OK = 0
EXIT_REMOVALS = 1
EXIT_MISMATCH = 2

_PROG = "pytest-collection-guard"


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------


def _render_report(
    baseline_path: Path,
    current_path: Path,
    baseline: Manifest,
    current: Manifest,
    diff: ManifestDiff,
    decision: PolicyDecision,
) -> str:
    lines = [
        f"{_PROG} compare",
        f"  baseline: {baseline_path} (profile {baseline.environment.profile!r}, "
        f"{diff.baseline_selected_count} selected)",
        f"  current:  {current_path} (profile {current.environment.profile!r}, "
        f"{diff.current_selected_count} selected)",
    ]

    if not diff.comparable:
        lines.append("")
        lines.append("MISMATCH (not comparable):")
        lines.extend(f"  ! {issue}" for issue in diff.environment_mismatches)
        lines.append("")
        lines.append(
            f"RESULT: REFUSED — baseline and current describe different collection scopes "
            f"({len(diff.removed)} removal(s) NOT evaluated)."
        )
        return "\n".join(lines) + "\n"

    if diff.moved_to_deselected:
        lines.append("")
        lines.append(
            f"NOTE: {len(diff.moved_to_deselected)} removed test(s) are deselected in the "
            f"current run (check -k/-m/selection changes):"
        )
        lines.extend(f"  ~ {test_id}" for test_id in diff.moved_to_deselected)

    if diff.removed:
        lines.append("")
        lines.append(f"REMOVED ({len(diff.removed)}):")
        lines.extend(f"  - {test_id}" for test_id in diff.removed)
    if diff.added:
        lines.append("")
        lines.append(f"ADDED ({len(diff.added)}):")
        lines.extend(f"  + {test_id}" for test_id in diff.added)

    if decision.allowed_removals:
        lines.append("")
        lines.append(f"APPROVED REMOVALS ({len(decision.allowed_removals)}):")
        for test_id, reason in decision.allowed_removals:
            lines.append(f"  - {test_id}")
            lines.append(f"      reason: {reason}")
    if decision.stale_entries:
        lines.append("")
        lines.append(f"STALE ALLOW ENTRIES ({len(decision.stale_entries)}):")
        lines.extend(f"  ? {test_id}" for test_id in decision.stale_entries)

    lines.append("")
    if decision.has_unapproved_removals:
        lines.append(
            f"RESULT: FAIL — {len(decision.unapproved_removals)} unapproved removal(s); "
            f"justify them in a removals TOML or restore the tests."
        )
    else:
        lines.append("RESULT: OK — no unapproved removals.")
    return "\n".join(lines) + "\n"


def _json_result(
    baseline: Manifest,
    current: Manifest,
    diff: ManifestDiff,
    decision: PolicyDecision,
    exit_code: int,
) -> dict[str, Any]:
    if not diff.comparable:
        result = "mismatch"
    elif decision.has_unapproved_removals:
        result = "removals"
    else:
        result = "ok"
    return {
        "result": result,
        "exit_code": exit_code,
        "baseline_profile": baseline.environment.profile,
        "current_profile": current.environment.profile,
        "baseline_selected": diff.baseline_selected_count,
        "current_selected": diff.current_selected_count,
        "environment_mismatches": list(diff.environment_mismatches),
        "removed": list(diff.removed),
        "added": list(diff.added),
        "moved_to_deselected": list(diff.moved_to_deselected),
        "approved_removals": [
            {"id": test_id, "reason": reason} for test_id, reason in decision.allowed_removals
        ],
        "unapproved_removals": list(decision.unapproved_removals),
        "stale_allow_entries": list(decision.stale_entries),
    }


def run_compare(
    baseline_path: Path,
    current_path: Path,
    allow_path: Path | None = None,
    json_out: Path | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Compare two manifests; return the exit code (see module docstring)."""
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr
    try:
        baseline = load_manifest(baseline_path)
        current = load_manifest(current_path)
    except ManifestError as exc:
        print(f"{_PROG}: error: {exc}", file=stderr)
        return EXIT_MISMATCH

    for path, manifest in ((baseline_path, baseline), (current_path, current)):
        if manifest.status != STATUS_OK:
            print(
                f"{_PROG}: error: {path} is not a valid inventory "
                f"(collection status: {manifest.status!r}, "
                f"{len(manifest.errors)} collection error(s)); "
                f"a failed collection cannot prove that tests are gone",
                file=stderr,
            )
            return EXIT_MISMATCH

    policy = None
    if allow_path is not None:
        try:
            policy = load_policy(allow_path)
        except PolicyError as exc:
            print(f"{_PROG}: error: {exc}", file=stderr)
            return EXIT_MISMATCH
    if policy is None:
        policy = RemovalPolicy()

    diff = compare_manifests(baseline, current)

    if not diff.comparable:
        decision = PolicyDecision(
            allowed_removals=(), unapproved_removals=diff.removed, stale_entries=()
        )
        exit_code = EXIT_MISMATCH
    else:
        decision = evaluate_removals(diff.removed, policy)
        exit_code = EXIT_REMOVALS if decision.has_unapproved_removals else EXIT_OK

    report = _render_report(baseline_path, current_path, baseline, current, diff, decision)
    print(report, end="", file=stdout)

    if json_out is not None:
        payload = _json_result(baseline, current, diff, decision, exit_code)
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    return exit_code


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------

_DEMO_ENV = Environment(
    profile="linux",
    platform="example-platform (synthetic demo data)",
    python_version="3.11.0",
    pytest_version="8.0.0",
    rootdir="/example/project",
)
_DEMO_ARGS = CollectionArgs(
    testpaths=("tests",),
    python_files=("test_*.py",),
    python_classes=("Test*",),
    python_functions=("test_*",),
)
_DEMO_BASELINE = (
    "tests/test_example_shop.py::test_add_item",
    "tests/test_example_shop.py::test_apply_discount",
    "tests/test_example_shop.py::test_checkout[card]",
    "tests/test_example_shop.py::test_checkout[paypal]",
)
_DEMO_CURRENT = (
    "tests/test_example_shop.py::test_add_item",
    "tests/test_example_shop.py::test_apply_discount_v2",
    "tests/test_example_shop.py::test_checkout[card]",
    "tests/test_example_shop.py::test_checkout[paypal]",
)


def run_demo(dir_path: Path, stdout: TextIO | None = None) -> int:
    """Write two synthetic manifests that show one lost test; return 0."""
    if stdout is None:
        stdout = sys.stdout
    baseline = Manifest(
        selected=_DEMO_BASELINE,
        deselected=(),
        environment=_DEMO_ENV,
        collection_args=_DEMO_ARGS,
    )
    current = Manifest(
        selected=_DEMO_CURRENT,
        deselected=(),
        environment=_DEMO_ENV,
        collection_args=_DEMO_ARGS,
    )
    baseline_path = dir_path / "baseline.json"
    current_path = dir_path / "current.json"
    save_manifest(baseline_path, baseline)
    save_manifest(current_path, current)

    print(f"demo manifests written to {dir_path}/ (synthetic example data):", file=stdout)
    print(f"  {baseline_path}  (4 selected tests)", file=stdout)
    print(f"  {current_path}   (4 selected tests)", file=stdout)
    print("", file=stdout)
    print(
        "Both files contain 4 tests — but not the same 4: "
        "'test_apply_discount' silently became 'test_apply_discount_v2'.",
        file=stdout,
    )
    print("", file=stdout)
    print("Now compare them:", file=stdout)
    print(f"  {_PROG} compare {baseline_path} {current_path}", file=stdout)
    print("", file=stdout)
    print("Expected: exit code 1, reporting test_apply_discount as REMOVED.", file=stdout)
    return EXIT_OK


# ---------------------------------------------------------------------------
# argument parsing / entry point
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_PROG,
        description="Fail CI when expected pytest tests disappear from collection.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compare = sub.add_parser(
        "compare",
        help="compare two collection manifests (baseline vs current)",
        description=(
            "Compare two manifests. Exit codes: 0 = no unapproved removals, "
            "1 = unapproved removal(s), 2 = comparison refused (profile/argument "
            "mismatch, errored collection manifest, or invalid input)."
        ),
    )
    compare.add_argument("baseline", type=Path, help="baseline manifest JSON")
    compare.add_argument("current", type=Path, help="current manifest JSON")
    compare.add_argument(
        "--allow",
        type=Path,
        default=None,
        metavar="REMOVALS.toml",
        help="justified-removal allow file ([[removal]] id/reason tables)",
    )
    compare.add_argument(
        "--json",
        type=Path,
        default=None,
        metavar="PATH",
        help="also write a machine-readable result report to PATH",
    )

    demo = sub.add_parser(
        "demo",
        help="write synthetic manifests that demonstrate a lost test",
        description="Write synthetic baseline/current manifests showing one lost test.",
    )
    demo.add_argument(
        "--dir",
        type=Path,
        default=Path("demo"),
        metavar="DIR",
        help="directory for the demo manifests (default: %(default)s)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "compare":
        return run_compare(
            baseline_path=args.baseline,
            current_path=args.current,
            allow_path=args.allow,
            json_out=args.json,
        )
    if args.command == "demo":
        return run_demo(args.dir)
    parser.error(f"unknown command {args.command!r}")  # pragma: no cover


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
