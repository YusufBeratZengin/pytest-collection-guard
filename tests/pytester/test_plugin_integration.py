"""Real integration tests: run pytest with the guard and inspect manifests.

These exercise the acceptance criteria end to end:

* the collector is opt-in and never changes a normal run;
* collection imports test modules but never runs test bodies/fixtures;
* a collection error never yields a valid inventory;
* selected/deselected identities and profiles are recorded;
* losing one test while keeping the total count still fails the comparison.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pytest_collection_guard.cli import EXIT_MISMATCH, EXIT_OK, EXIT_REMOVALS, run_compare
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
    assert result.ret != 0
    assert result.ret == pytest.ExitCode.INTERNAL_ERROR
    assert "FAILED to write manifest" in result.stdout.str()


def test_manifest_write_failure_fails_ci_and_invalidates_stale_file(
    guard_run, write_test_file, pytester, monkeypatch
) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    stale_file = pytester.path / "current.json"
    stale_payload = '{"status": "ok", "identity": {"selected": ["old::test"]}}'
    stale_file.write_text(stale_payload, encoding="utf-8")

    def _failing_save(*args, **kwargs):
        raise OSError("simulated disk write error")

    monkeypatch.setattr("pytest_collection_guard.plugin.save_manifest", _failing_save)

    result = guard_run(out="current.json")
    # Pytest must fail so CI pipeline does not proceed to compare
    assert result.ret != 0
    assert result.ret == pytest.ExitCode.INTERNAL_ERROR
    assert "FAILED to write manifest" in result.stdout.str()

    # Stale manifest must not remain so CI cannot mistakenly compare obsolete inventory
    assert not stale_file.exists()


def test_ignore_option_mismatch_refuses_comparison(
    guard_run, read_manifest, write_test_file, tmp_path: Path
) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    write_test_file("tests/test_beta.py", "def test_two():\n    assert True\n")

    guard_run(out="baseline.json")
    guard_run("--ignore=tests/test_beta.py", out="current.json")

    base = read_manifest("baseline.json")
    curr = read_manifest("current.json")
    b_path = tmp_path / "base.json"
    c_path = tmp_path / "curr.json"
    save_manifest(b_path, base)
    save_manifest(c_path, curr)

    # Instead of reporting test_two as unapproved lost test (exit 1),
    # the guard must refuse comparison due to collection scope mismatch (exit 2).
    assert run_compare(b_path, c_path) == EXIT_MISMATCH


def test_ignore_glob_mismatch_refuses_comparison(
    guard_run, read_manifest, write_test_file, tmp_path: Path
) -> None:
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")
    write_test_file("tests/test_beta.py", "def test_two():\n    assert True\n")

    guard_run(out="baseline.json")
    guard_run("--ignore-glob=*_beta.py", out="current.json")

    base = read_manifest("baseline.json")
    curr = read_manifest("current.json")
    b_path = tmp_path / "base.json"
    c_path = tmp_path / "curr.json"
    save_manifest(b_path, base)
    save_manifest(c_path, curr)

    assert run_compare(b_path, c_path) == EXIT_MISMATCH


def test_deselect_option_mismatch_refuses_comparison(
    guard_run, read_manifest, write_test_file, tmp_path: Path
) -> None:
    write_test_file(
        "tests/test_alpha.py",
        "def test_one():\n    assert True\n\ndef test_two():\n    assert True\n",
    )

    guard_run(out="baseline.json")
    guard_run("--deselect=tests/test_alpha.py::test_two", out="current.json")

    base = read_manifest("baseline.json")
    curr = read_manifest("current.json")
    b_path = tmp_path / "base.json"
    c_path = tmp_path / "curr.json"
    save_manifest(b_path, base)
    save_manifest(c_path, curr)

    assert run_compare(b_path, c_path) == EXIT_MISMATCH


# ---------------------------------------------------------------------------
# empty and failed collection regression tests (plugin hashability & FSHookProxy)
# ---------------------------------------------------------------------------


def test_empty_collection_generates_valid_empty_manifest(
    guard_run, read_manifest, pytester
) -> None:
    """An empty test directory must produce an empty manifest without internal plugin error."""
    empty_dir = pytester.path / "empty_suite"
    empty_dir.mkdir(parents=True, exist_ok=True)
    (empty_dir / "conftest.py").write_text("# empty conftest\n", encoding="utf-8")

    result = guard_run("empty_suite")
    assert result.ret == pytest.ExitCode.NO_TESTS_COLLECTED
    assert "INTERNALERROR" not in result.stderr.str()
    assert "INTERNALERROR" not in result.stdout.str()

    manifest = read_manifest()
    assert manifest.status == "ok"
    assert manifest.is_valid_inventory
    assert manifest.selected == ()
    assert manifest.deselected == ()
    assert manifest.errors == ()


def test_failed_collection_marks_manifest_invalid_without_plugin_crash(
    guard_run, read_manifest, write_test_file
) -> None:
    """A collection failure in a test file must record status='error' and no internal crash."""
    write_test_file(
        "tests/test_failing_collect.py",
        "raise RuntimeError('synthetic collection failure')\n",
    )

    result = guard_run("tests")
    assert result.ret != 0
    assert "INTERNALERROR" not in result.stderr.str()
    assert "INTERNALERROR" not in result.stdout.str()

    manifest = read_manifest()
    assert manifest.status == "error"
    assert not manifest.is_valid_inventory
    assert manifest.errors
    assert any("synthetic collection failure" in err for err in manifest.errors)


def test_nested_conftest_collection_with_hook_proxy_filtering(
    guard_run, read_manifest, pytester
) -> None:
    """Nested conftests activate pytest's FSHookProxy which requires plugins to be hashable."""
    root_conftest = pytester.path / "conftest.py"
    root_conftest.write_text("# root conftest\n", encoding="utf-8")

    pkg_dir = pytester.path / "pkg"
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "conftest.py").write_text("# sub conftest\n", encoding="utf-8")
    (pkg_dir / "test_pkg.py").write_text("def test_item(): pass\n", encoding="utf-8")

    result = guard_run("pkg")
    assert result.ret == pytest.ExitCode.OK
    assert "INTERNALERROR" not in result.stderr.str()

    manifest = read_manifest()
    assert manifest.status == "ok"
    assert manifest.is_valid_inventory
    assert "pkg/test_pkg.py::test_item" in manifest.selected


def test_aborted_collection_manifest_is_not_a_valid_inventory(
    guard_run, read_manifest, write_test_file, pytester
) -> None:
    """A session that exits before collection finishes must not emit a valid inventory."""
    (pytester.path / "conftest.py").write_text(
        "import pytest\n"
        "\n"
        "\n"
        "def pytest_collection(session):\n"
        "    pytest.exit('synthetic abort before collection completes', returncode=0)\n",
        encoding="utf-8",
    )
    write_test_file("tests/test_alpha.py", "def test_one():\n    assert True\n")

    result = guard_run("tests")
    assert result.ret == pytest.ExitCode.OK
    assert "inventory NOT usable for compare" in result.stdout.str()

    manifest = read_manifest()
    assert manifest.status == "error"
    assert not manifest.is_valid_inventory
    assert manifest.selected == ()
    assert any("collection did not finish" in err for err in manifest.errors)


@pytest.mark.parametrize("returncode", [None, 0])
@pytest.mark.parametrize("direct_exception", [False, True], ids=["pytest-exit", "exit-exception"])
def test_exit_from_collectstart_rejects_partial_inventory(
    guard_run,
    read_manifest,
    write_test_file,
    pytester: pytest.Pytester,
    returncode: int | None,
    direct_exception: bool,
) -> None:
    """The finish hook runs even when pytest.exit aborts the tree halfway."""
    pytester.makeini("[pytest]")
    for name in ("alpha", "middle", "zulu"):
        write_test_file(f"tests/test_{name}.py", "def test_one():\n    assert True\n")
    guard_run(out="baseline.json")
    baseline = read_manifest("baseline.json")
    assert baseline.status == "ok"
    assert len(baseline.selected) == 3

    abort = (
        "raise pytest.exit.Exception" if direct_exception else "pytest.exit"
    ) + f"('synthetic abort', returncode={returncode!r})"
    write_test_file(
        "conftest.py",
        "import pytest\n\n"
        "def pytest_collectstart(collector):\n"
        "    if collector.name == 'test_middle.py':\n"
        f"        {abort}\n",
    )
    result = guard_run(out="current.json")
    assert result.ret == (pytest.ExitCode.INTERRUPTED if returncode is None else 0)
    assert "inventory NOT usable for compare" in result.stdout.str()
    current = read_manifest("current.json")
    assert current.selected == ("tests/test_alpha.py::test_one",)

    report = io.StringIO()
    code = run_compare(
        pytester.path / "baseline.json", pytester.path / "current.json", stdout=report
    )
    assert (current.status, code) == ("error", EXIT_MISMATCH)
    assert not current.is_valid_inventory
    assert current.errors
    assert "REMOVED" not in report.getvalue()


def test_relative_ignore_same_scope_from_different_cwds_compares_cleanly(
    guard_run,
    read_manifest,
    write_test_file,
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same ignored tree typed relative to two cwds is one identity.

    Before the fix the raw strings ("tests/slow" vs "slow") were stored, so
    two runs with identical scope were refused as a mismatch. Now both resolve
    to the same rootdir-relative path and compare as equal with no loss.
    """
    for relpath, content in _SIMPLE_TREE.items():
        write_test_file(relpath, content)
    write_test_file("tests/slow/test_slow.py", "def test_slow():\n    assert True\n")
    root = pytester.path

    # baseline: run from the project root, ignore path relative to root
    guard_run("tests", "--ignore=tests/slow", out=str(root / "baseline.json"))
    # current: run from tests/, ignore path relative to tests/
    monkeypatch.chdir(root / "tests")
    guard_run(
        str(root / "tests"),
        "--rootdir",
        str(root),
        "--ignore=slow",
        out=str(root / "current.json"),
    )
    monkeypatch.chdir(root)

    baseline = read_manifest("baseline.json")
    current = read_manifest("current.json")

    report = io.StringIO()
    code = run_compare(root / "baseline.json", root / "current.json", stdout=report)
    assert code == EXIT_OK
    assert "REMOVED" not in report.getvalue()
    assert baseline.collection_args.ignore == ("tests/slow",)
    assert current.collection_args.ignore == ("tests/slow",)
    assert baseline.selected == current.selected


def test_relative_ignore_real_scope_difference_is_refused(
    guard_run,
    read_manifest,
    write_test_file,
    pytester: pytest.Pytester,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same literal string from another cwd can ignore a different path.

    Before the fix both runs stored ("tests/slow",) and the 2 tests that the
    second run never ignored were reported as fake REMOVED with exit 1. The
    resolved locations now differ, so the comparison is refused (exit 2).
    """
    for relpath, content in _SIMPLE_TREE.items():
        write_test_file(relpath, content)
    write_test_file("tests/slow/test_slow.py", "def test_slow():\n    assert True\n")
    root = pytester.path

    # from tests/, "tests/slow" resolves to tests/tests/slow -> ignores nothing
    monkeypatch.chdir(root / "tests")
    guard_run(
        str(root / "tests"),
        "--rootdir",
        str(root),
        "--ignore=tests/slow",
        out=str(root / "baseline.json"),
    )
    monkeypatch.chdir(root)
    # from the root, the same string really ignores tests/slow
    guard_run("tests", "--ignore=tests/slow", out=str(root / "current.json"))

    baseline = read_manifest("baseline.json")
    current = read_manifest("current.json")

    report = io.StringIO()
    code = run_compare(root / "baseline.json", root / "current.json", stdout=report)
    assert code == EXIT_MISMATCH
    assert "ignore differ" in report.getvalue()
    assert "MISMATCH (not comparable)" in report.getvalue()
    # Before the fix this comparison instead reported the 2 currently
    # collected tests as fake REMOVED with exit 1 (both stored ("tests/slow",)).
    assert baseline.collection_args.ignore == ("tests/tests/slow",)
    assert current.collection_args.ignore == ("tests/slow",)
    assert len(baseline.selected) > len(current.selected)


def test_keyboardinterrupt_during_collection_rejects_partial_inventory(
    guard_run, read_manifest, write_test_file, pytester
) -> None:
    for name in ("alpha", "zulu"):
        write_test_file(f"tests/test_{name}.py", "def test_one():\n    assert True\n")
    guard_run(out="baseline.json")
    write_test_file("tests/test_middle.py", "raise KeyboardInterrupt('synthetic abort')\n")
    result = pytester.runpytest(
        "--collect-only",
        "-q",
        "-p",
        "pytest_collection_guard.plugin",
        "--collection-guard-profile=linux",
        "--collection-guard-out=current.json",
        no_reraise_ctrlc=True,
    )
    assert result.ret == pytest.ExitCode.INTERRUPTED
    current = read_manifest("current.json")
    assert current.status == "error"
    assert not current.is_valid_inventory
    assert "tests/test_zulu.py::test_one" not in current.selected
    assert "inventory NOT usable for compare" in result.stdout.str()
    report = io.StringIO()
    assert (
        run_compare(pytester.path / "baseline.json", pytester.path / "current.json", stdout=report)
        == EXIT_MISMATCH
    )
    assert "REMOVED" not in report.getvalue()


def test_keyboardinterrupt_in_test_body_keeps_inventory_valid(
    guard_run, read_manifest, write_test_file, pytester
) -> None:
    """A test-body interrupt leaves the completed collection inventory usable."""
    write_test_file(
        "tests/test_body_interrupt.py",
        "def test_one():\n    assert True\n\n"
        "def test_two():\n    raise KeyboardInterrupt('synthetic test-body interrupt')\n",
    )
    guard_run(out="baseline.json")
    baseline = read_manifest("baseline.json")
    assert baseline.status == "ok"
    assert len(baseline.selected) == 2
    result = pytester.runpytest(
        "-q",
        "-p",
        "pytest_collection_guard.plugin",
        "--collection-guard-profile=linux",
        "--collection-guard-out=current.json",
        no_reraise_ctrlc=True,
    )
    assert result.ret == pytest.ExitCode.INTERRUPTED
    current = read_manifest("current.json")
    assert current.status == "ok"
    assert current.is_valid_inventory
    assert current.errors == ()
    assert current.selected == baseline.selected
    assert "inventory NOT usable for compare" not in result.stdout.str()
    report = io.StringIO()
    assert (
        run_compare(pytester.path / "baseline.json", pytester.path / "current.json", stdout=report)
        == EXIT_OK
    )
    assert "REMOVED" not in report.getvalue()
