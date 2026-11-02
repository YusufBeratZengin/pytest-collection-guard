"""Unit tests for the justified-removal policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from pytest_collection_guard.policy import (
    PolicyError,
    RemovalEntry,
    RemovalPolicy,
    evaluate_removals,
    load_policy,
)

_VALID = """
# Review artifact: every removal of an expected test is justified here.

[[removal]]
id = "tests/test_checkout.py::test_apply_discount"
reason = "Feature dropped in 2.0 (issue #123, decided 2026-10-31)."

[[removal]]
id = "tests/test_legacy.py::test_old_flow"
reason = "Superseded by test_new_flow."
"""


def _write(tmp_path: Path, text: str, name: str = "removals.toml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------


def test_load_valid_policy(tmp_path: Path) -> None:
    policy = load_policy(_write(tmp_path, _VALID))
    assert len(policy.entries) == 2
    entry = policy.get("tests/test_checkout.py::test_apply_discount")
    assert entry is not None
    assert entry.reason.startswith("Feature dropped")
    assert policy.get("tests/nope.py::test_missing") is None
    assert policy.ids() == frozenset(
        {
            "tests/test_checkout.py::test_apply_discount",
            "tests/test_legacy.py::test_old_flow",
        }
    )


def test_reason_is_stripped(tmp_path: Path) -> None:
    policy = load_policy(
        _write(tmp_path, '[[removal]]\nid = "tests/test_a.py::test_x"\nreason = "  trimmed  "\n')
    )
    assert policy.entries == (RemovalEntry(id="tests/test_a.py::test_x", reason="trimmed"),)


def test_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="allow file not found"):
        load_policy(tmp_path / "nope.toml")


def test_invalid_toml_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="not valid TOML"):
        load_policy(_write(tmp_path, "[[removal]\nid = broken"))


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('[settings]\nid = "x"', "unknown top-level key"),
        ("removal = 5", "'removal' must be an array"),
        ('[[removal]]\nid = 5\nreason = "x"', "'id' must be a non-empty string"),
        ('[[removal]]\nid = "  "\nreason = "x"', "'id' must be a non-empty string"),
        ('[[removal]]\nid = "tests/test_a.py::test_x"', "'reason' must be a non-empty string"),
        (
            '[[removal]]\nid = "tests/test_a.py::test_x"\nreason = "  "',
            "'reason' must be a non-empty string",
        ),
        ("[[removal]]\nid = 5\nreason = 6\nextra = true", "unknown key"),
    ],
)
def test_policy_format_is_strict(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(PolicyError, match=message):
        load_policy(_write(tmp_path, text))


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    text = (
        '[[removal]]\nid = "tests/test_a.py::test_x"\nreason = "one"\n'
        '[[removal]]\nid = "tests/test_a.py::test_x"\nreason = "two"\n'
    )
    with pytest.raises(PolicyError, match="duplicate id"):
        load_policy(_write(tmp_path, text))


def test_non_table_entry_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyError, match="expected a table"):
        load_policy(_write(tmp_path, "removal = [5]\n"))


# ---------------------------------------------------------------------------
# evaluation
# ---------------------------------------------------------------------------


def test_evaluate_splits_approved_unapproved_and_stale() -> None:
    policy = RemovalPolicy(
        entries=(
            RemovalEntry(id="tests/test_a.py::test_gone", reason="dropped (issue #7)"),
            RemovalEntry(id="tests/test_a.py::test_stale", reason="already merged"),
        )
    )
    decision = evaluate_removals(
        ("tests/test_a.py::test_gone", "tests/test_a.py::test_surprise"),
        policy,
    )
    assert decision.allowed_removals == (("tests/test_a.py::test_gone", "dropped (issue #7)"),)
    assert decision.unapproved_removals == ("tests/test_a.py::test_surprise",)
    assert decision.stale_entries == ("tests/test_a.py::test_stale",)
    assert decision.has_unapproved_removals


def test_evaluate_without_policy_reports_everything() -> None:
    decision = evaluate_removals(("tests/test_a.py::test_gone",), RemovalPolicy())
    assert decision.unapproved_removals == ("tests/test_a.py::test_gone",)
    assert decision.allowed_removals == ()
    assert decision.stale_entries == ()


def test_evaluate_clean_run_has_no_unapproved() -> None:
    decision = evaluate_removals((), RemovalPolicy())
    assert not decision.has_unapproved_removals
