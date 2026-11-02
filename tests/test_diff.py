"""Unit tests for the set-difference engine."""

from __future__ import annotations

from pytest_collection_guard.diff import compare_manifests
from pytest_collection_guard.manifest import CollectionArgs, Environment, Manifest


def _manifest(selected: tuple[str, ...], deselected: tuple[str, ...] = (), **kwargs) -> Manifest:
    return Manifest(
        selected=selected,
        deselected=deselected,
        environment=kwargs.pop("environment", Environment(profile="linux")),
        collection_args=kwargs.pop("collection_args", CollectionArgs()),
        **kwargs,
    )


def test_identical_manifests_compare_clean() -> None:
    base = _manifest(("tests/test_a.py::test_one", "tests/test_a.py::test_two"))
    diff = compare_manifests(base, base)
    assert diff.comparable
    assert diff.removed == ()
    assert diff.added == ()
    assert diff.moved_to_deselected == ()
    assert diff.baseline_selected_count == 2
    assert diff.current_selected_count == 2


def test_removed_and_added_are_tracked_per_identity() -> None:
    base = _manifest(("tests/test_a.py::test_one", "tests/test_a.py::test_two"))
    current = _manifest(("tests/test_a.py::test_one", "tests/test_a.py::test_three"))
    diff = compare_manifests(base, current)
    assert diff.removed == ("tests/test_a.py::test_two",)
    assert diff.added == ("tests/test_a.py::test_three",)


def test_addition_never_hides_a_removal() -> None:
    """Same total count, different identity: the loss must still be reported."""
    base = _manifest(("tests/test_a.py::test_one", "tests/test_a.py::test_two"))
    current = _manifest(("tests/test_a.py::test_one", "tests/test_a.py::test_new"))
    diff = compare_manifests(base, current)
    assert diff.baseline_selected_count == diff.current_selected_count
    assert diff.removed == ("tests/test_a.py::test_two",)
    assert diff.added == ("tests/test_a.py::test_new",)


def test_removed_but_now_deselected_is_flagged() -> None:
    base = _manifest(("tests/test_a.py::test_one", "tests/test_a.py::test_two"))
    current = _manifest(("tests/test_a.py::test_one",), deselected=("tests/test_a.py::test_two",))
    diff = compare_manifests(base, current)
    assert diff.removed == ("tests/test_a.py::test_two",)
    assert diff.moved_to_deselected == ("tests/test_a.py::test_two",)


def test_profile_mismatch_makes_diff_not_comparable() -> None:
    base = _manifest(("tests/test_a.py::test_one",), environment=Environment(profile="linux"))
    current = _manifest(("tests/test_a.py::test_one",), environment=Environment(profile="windows"))
    diff = compare_manifests(base, current)
    assert not diff.comparable
    assert any("profile differs" in issue for issue in diff.environment_mismatches)


def test_collection_arg_mismatch_makes_diff_not_comparable() -> None:
    base = _manifest(
        ("tests/test_a.py::test_one",),
        collection_args=CollectionArgs(testpaths=("tests",), keyword=None),
    )
    current = _manifest(
        ("tests/test_a.py::test_one",),
        collection_args=CollectionArgs(testpaths=("tests",), keyword="one"),
    )
    diff = compare_manifests(base, current)
    assert not diff.comparable
    assert any("keyword differ" in issue for issue in diff.environment_mismatches)


def test_recorded_but_unenforced_environment_fields_do_not_break_comparability() -> None:
    base = _manifest(
        ("tests/test_a.py::test_one",),
        environment=Environment(profile="linux", platform="Linux-1", rootdir="/a"),
    )
    current = _manifest(
        ("tests/test_a.py::test_one",),
        environment=Environment(profile="linux", platform="Windows-2", rootdir="/b"),
    )
    diff = compare_manifests(base, current)
    assert diff.comparable
