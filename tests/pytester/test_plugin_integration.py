"""Real integration tests: run pytest with the guard and inspect manifests.

These exercise the acceptance criteria end to end:

* the collector is opt-in and never changes a normal run;
* collection imports test modules but never runs test bodies/fixtures;
* a collection error never yields a valid inventory;
* selected/deselected identities and profiles are recorded;
* losing one test while keeping the total count still fails the comparison.
"""

from __future__ import annotations

from pathlib import Path

from pytest_collection_guard.cli import EXIT_MISMATCH, EXIT_REMOVALS, run_compare
from pytest_collection_guard.manifest import save_manifest

# ---------------------------------------------------------------------------
# synthetic example test trees (obviously fake data)
# ---------------------------------------------------------------------------

_SIMPLE_TREE = {
    "tests/test_alpha.py": (
        "def test_one():\n    assert 1 + 1 == 2\n\ndef test_two():\n    assert 2 + 2 == 4\n"
    ),
    "tests/test_beta.py": ("def test_three():\n    assert 3 + 3 == 6\n"),
}

_SIDE_EFFECT_TREE = (
    "import pathlib\n"
    "\n"
    "EVENTS = pathlib.Path(__file__).parent / 'events.txt'\n"
    "\n"
    "with EVENTS.open('a', encoding='utf-8') as fh:\n"
    "    fh.write('import\\n')\n"
    "\n"
    "import pytest\n"
    "\n"
    "\n"
    "@pytest.fixture\n"
    "def record():\n"
    "    with EVENTS.open('a', encoding='utf-8') as fh:\n"
    "        fh.write('fixture\\n')\n"
    "\n"
    "\n"
    "def test_alpha(record):\n"
    "    with EVENTS.open('a', encoding='utf-8') as fh:\n"
    "        fh.write('body\\n')\n"
)

_PARAM_TREE = (
    "import pytest\n"
    "\n"
    "\n"
    "@pytest.mark.parametrize('method', ['card', 'paypal'], ids=['card', 'paypal'])\n"
    "def test_checkout(method):\n"
    "    assert method in {'card', 'paypal'}\n"
)


# ---------------------------------------------------------------------------
# manifest recording
# ---------------------------------------------------------------------------


def test_manifest_records_selected_identities(guard_run, read_manifest, write_test_file) -> None:
    for relpath, content in _SIMPLE_TREE.items():
        write_test_file(relpath, content)

    result = guard_run()
    result.assert_outcomes()  # --collect-only runs nothing
    manifest = read_manifest()
    assert manifest.status == "ok"
    assert manifest.is_valid_inventory
    assert manifest.selected == (
        "tests/test_alpha.py::test_one",
        "tests/test_alpha.py::test_two",
        "tests/test_beta.py::test_three",
    )
    assert manifest.deselected == ()
    assert manifest.environment.profile == "linux"
    assert manifest.errors == ()


def test_manifest_separates_identity_from_environment(
    guard_run, read_manifest, write_test_file
) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    guard_run(profile="ci-linux")
    manifest = read_manifest()
    # identity
    assert manifest.selected == ("tests/test_alpha.py::test_one",)
    # environment (recorded for humans; only profile is enforced)
    assert manifest.environment.profile == "ci-linux"
    assert manifest.environment.python_version
    assert manifest.environment.pytest_version
    assert manifest.environment.rootdir


def test_collection_args_are_recorded(guard_run, read_manifest, write_test_file) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    guard_run("tests", "-k", "one")
    manifest = read_manifest()
    assert manifest.collection_args.keyword == "one"
    assert manifest.collection_args.positional_args == ("tests",)


def test_parametrized_ids_are_recorded_verbatim(guard_run, read_manifest, write_test_file) -> None:
    write_test_file("tests/test_checkout.py", _PARAM_TREE)
    guard_run()
    manifest = read_manifest()
    assert manifest.selected == (
        "tests/test_checkout.py::test_checkout[card]",
        "tests/test_checkout.py::test_checkout[paypal]",
    )


def test_deselected_inventory_covers_k_filter(guard_run, read_manifest, write_test_file) -> None:
    for relpath, content in _SIMPLE_TREE.items():
        write_test_file(relpath, content)

    guard_run("-k", "one")
    manifest = read_manifest()
    assert manifest.selected == ("tests/test_alpha.py::test_one",)
    assert manifest.deselected == (
        "tests/test_alpha.py::test_two",
        "tests/test_beta.py::test_three",
    )
    assert manifest.collection_args.keyword == "one"


# ---------------------------------------------------------------------------
# opt-in behavior
# ---------------------------------------------------------------------------


def test_no_manifest_and_no_change_without_opt_in(guard_run, pytester) -> None:
    write = pytester.path / "tests" / "test_alpha.py"
    write.parent.mkdir(parents=True, exist_ok=True)
    write.write_text("def test_one():\n    assert True\n", encoding="utf-8")

    result = guard_run(guard=False, collect_only=False)
    result.assert_outcomes(passed=1)  # a normal run stays a normal run
    assert not (pytester.path / "manifest.json").exists()
    assert list(pytester.path.glob("*.json")) == []


# ---------------------------------------------------------------------------
# collection side effects and error handling
# ---------------------------------------------------------------------------


def test_collection_imports_modules_but_never_runs_bodies_or_fixtures(
    guard_run, pytester, write_test_file
) -> None:
    write_test_file("tests/test_side_effects.py", _SIDE_EFFECT_TREE)

    guard_run()
    events = (pytester.path / "tests" / "events.txt").read_text(encoding="utf-8")
    # collection imports the module (side effect runs) ...
    assert events == "import\n"
    # ... but neither fixtures nor test bodies execute
    assert "fixture" not in events
    assert "body" not in events


def test_broken_module_marks_manifest_invalid(guard_run, read_manifest, write_test_file) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    write_test_file("tests/test_broken.py", "def test_two(:\n    broken syntax\n")

    result = guard_run()
    manifest = read_manifest()
    assert manifest.status == "error"
    assert not manifest.is_valid_inventory
    assert manifest.errors
    assert any("test_broken.py" in error for error in manifest.errors)
    # pytest itself also fails the run on a collection error
    assert result.ret != 0


def test_import_error_marks_manifest_invalid(guard_run, read_manifest, write_test_file) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    write_test_file(
        "tests/test_boom.py",
        "raise ImportError('example: deliberately broken synthetic module')\n",
    )

    guard_run()
    manifest = read_manifest()
    assert manifest.status == "error"
    assert any("ImportError" in error for error in manifest.errors)


def test_errored_manifest_cannot_be_compared_as_inventory(
    guard_run, read_manifest, write_test_file, tmp_path: Path
) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    guard_run(out="baseline.json")
    good = read_manifest("baseline.json")

    write_test_file("tests/test_broken.py", "def test_two(:\n    broken\n")
    guard_run(out="current.json")
    bad = read_manifest("current.json")

    baseline_path = tmp_path / "b.json"
    current_path = tmp_path / "c.json"
    save_manifest(baseline_path, good)
    save_manifest(current_path, bad)

    # refusing the errored manifest is what prevents a false "tests disappeared"
    assert run_compare(baseline_path, current_path) == EXIT_MISMATCH


# ---------------------------------------------------------------------------
# end-to-end: the lost-test regression
# ---------------------------------------------------------------------------


def test_lost_test_fails_comparison_even_when_total_count_is_stable(
    guard_run, read_manifest, write_test_file, tmp_path: Path
) -> None:
    """One id disappears while a new one appears: same count, still a failure."""
    for relpath, content in _SIMPLE_TREE.items():
        write_test_file(relpath, content)
    guard_run(out="baseline.json")
    baseline = read_manifest("baseline.json")

    # refactor: test_two is accidentally renamed to test_twoo (a NEW test id)
    write_test_file(
        "tests/test_alpha.py",
        "def test_one():\n    assert 1 + 1 == 2\n\ndef test_twoo():\n    assert 2 + 2 == 4\n",
    )
    guard_run(out="current.json")
    current = read_manifest("current.json")

    assert len(baseline.selected) == len(current.selected)

    baseline_path = tmp_path / "baseline.json"
    current_path = tmp_path / "current.json"
    save_manifest(baseline_path, baseline)
    save_manifest(current_path, current)

    code = run_compare(baseline_path, current_path)
    assert code == EXIT_REMOVALS


def test_profile_mismatch_between_runs_refuses_comparison(
    guard_run, read_manifest, write_test_file, tmp_path: Path
) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    guard_run(out="linux.json", profile="linux")
    guard_run(out="windows.json", profile="windows")

    linux_path = tmp_path / "linux.json"
    windows_path = tmp_path / "windows.json"
    save_manifest(linux_path, read_manifest("linux.json"))
    save_manifest(windows_path, read_manifest("windows.json"))

    assert run_compare(linux_path, windows_path) == EXIT_MISMATCH


# ---------------------------------------------------------------------------
# write failure reporting
# ---------------------------------------------------------------------------


def test_manifest_write_failure_is_reported(guard_run, write_test_file, pytester) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    (pytester.path / "outdir").mkdir()

    result = guard_run(out="outdir")  # a directory cannot hold the manifest
    assert "FAILED to write manifest" in result.stdout.str()
