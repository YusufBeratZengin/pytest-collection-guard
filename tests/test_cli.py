"""CLI tests: compare/demo commands and the exit-code contract."""

from __future__ import annotations

import io
import json
from pathlib import Path

from pytest_collection_guard.cli import (
    EXIT_MISMATCH,
    EXIT_OK,
    EXIT_REMOVALS,
    main,
    run_compare,
    run_demo,
)
from pytest_collection_guard.manifest import STATUS_ERROR, CollectionArgs


def _run(*argv: str) -> int:
    return main(list(argv))


def test_compare_clean_returns_zero(make_manifest, write_manifest) -> None:
    baseline = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "b.json")
    current = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "c.json")
    assert run_compare(baseline, current) == EXIT_OK


def test_unapproved_removal_fails_with_exit_1(make_manifest, write_manifest, capsys) -> None:
    baseline = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_two")), "b.json"
    )
    current = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "c.json")
    code = run_compare(baseline, current)
    out = capsys.readouterr().out
    assert code == EXIT_REMOVALS
    assert "REMOVED (1):" in out
    assert "tests/test_a.py::test_two" in out
    assert "RESULT: FAIL" in out


def test_addition_does_not_hide_removal(make_manifest, write_manifest, capsys) -> None:
    baseline = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_old")), "b.json"
    )
    current = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_new")), "c.json"
    )
    code = run_compare(baseline, current)
    out = capsys.readouterr().out
    assert code == EXIT_REMOVALS
    assert "tests/test_a.py::test_old" in out
    assert "ADDED (1):" in out


def test_approved_removal_passes_and_prints_reason(
    make_manifest, write_manifest, tmp_path: Path, capsys
) -> None:
    baseline = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_two")), "b.json"
    )
    current = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "c.json")
    allow = tmp_path / "removals.toml"
    allow.write_text(
        '[[removal]]\nid = "tests/test_a.py::test_two"\nreason = "Dropped in 2.0 (issue #123)."\n',
        encoding="utf-8",
    )
    code = run_compare(baseline, current, allow_path=allow)
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "APPROVED REMOVALS (1):" in out
    assert "Dropped in 2.0 (issue #123)." in out
    assert "RESULT: OK" in out


def test_stale_allow_entry_is_reported_but_not_fatal(
    make_manifest, write_manifest, tmp_path: Path, capsys
) -> None:
    baseline = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "b.json")
    current = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "c.json")
    allow = tmp_path / "removals.toml"
    allow.write_text(
        '[[removal]]\nid = "tests/test_a.py::test_ghost"\nreason = "No longer relevant."\n',
        encoding="utf-8",
    )
    code = run_compare(baseline, current, allow_path=allow)
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "STALE ALLOW ENTRIES (1):" in out


def test_profile_mismatch_returns_exit_2(make_manifest, write_manifest, capsys) -> None:
    baseline = write_manifest(make_manifest(profile="linux"), "b.json")
    current = write_manifest(make_manifest(profile="windows"), "c.json")
    code = run_compare(baseline, current)
    out = capsys.readouterr().out
    assert code == EXIT_MISMATCH
    assert "MISMATCH (not comparable):" in out
    assert "profile differs" in out
    assert "RESULT: REFUSED" in out


def test_collection_arg_mismatch_returns_exit_2(make_manifest, write_manifest, capsys) -> None:
    baseline = write_manifest(
        make_manifest(collection_args=CollectionArgs(testpaths=("tests",), keyword=None)), "b.json"
    )
    current = write_manifest(
        make_manifest(collection_args=CollectionArgs(testpaths=("tests",), keyword="one")), "c.json"
    )
    code = run_compare(baseline, current)
    assert code == EXIT_MISMATCH
    assert "keyword differ" in capsys.readouterr().out


def test_mismatch_takes_precedence_over_removals(make_manifest, write_manifest) -> None:
    baseline = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_two")), "b.json"
    )
    current = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one",), profile="windows"), "c.json"
    )
    assert run_compare(baseline, current) == EXIT_MISMATCH


def test_errored_collection_manifest_is_refused(
    make_manifest, write_manifest, tmp_path: Path, capsys
) -> None:
    baseline = write_manifest(make_manifest(), "b.json")
    current = write_manifest(
        make_manifest(status=STATUS_ERROR, errors=("tests/test_b.py: ImportError: boom",)),
        "c.json",
    )
    code = run_compare(baseline, current)
    err = capsys.readouterr().err
    assert code == EXIT_MISMATCH
    assert "not a valid inventory" in err
    assert "cannot prove that tests are gone" in err
    # a status-error baseline is refused the same way
    assert run_compare(current, baseline) == EXIT_MISMATCH


def test_missing_manifest_file_returns_exit_2(
    make_manifest, write_manifest, tmp_path: Path, capsys
) -> None:
    baseline = write_manifest(make_manifest(), "b.json")
    code = run_compare(baseline, tmp_path / "missing.json")
    assert code == EXIT_MISMATCH
    assert "manifest file not found" in capsys.readouterr().err


def test_invalid_manifest_json_returns_exit_2(tmp_path: Path, capsys) -> None:
    baseline = tmp_path / "b.json"
    baseline.write_text("{ nope", encoding="utf-8")
    current = tmp_path / "c.json"
    current.write_text("{}", encoding="utf-8")
    assert run_compare(baseline, current) == EXIT_MISMATCH
    assert "not valid JSON" in capsys.readouterr().err


def test_invalid_allow_file_returns_exit_2(
    make_manifest, write_manifest, tmp_path: Path, capsys
) -> None:
    baseline = write_manifest(make_manifest(), "b.json")
    current = write_manifest(make_manifest(), "c.json")
    allow = tmp_path / "removals.toml"
    allow.write_text('[[removal]]\nid = "x"\n', encoding="utf-8")
    assert run_compare(baseline, current, allow_path=allow) == EXIT_MISMATCH
    assert "'reason' must be a non-empty string" in capsys.readouterr().err


def test_json_report_is_written(make_manifest, write_manifest, tmp_path: Path) -> None:
    baseline = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_two")), "b.json"
    )
    current = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "c.json")
    json_out = tmp_path / "reports" / "result.json"
    code = run_compare(baseline, current, json_out=json_out)
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert code == EXIT_REMOVALS
    assert payload["result"] == "removals"
    assert payload["exit_code"] == EXIT_REMOVALS
    assert payload["removed"] == ["tests/test_a.py::test_two"]
    assert payload["unapproved_removals"] == ["tests/test_a.py::test_two"]


def test_json_report_marks_mismatch(make_manifest, write_manifest, tmp_path: Path) -> None:
    baseline = write_manifest(make_manifest(profile="linux"), "b.json")
    current = write_manifest(make_manifest(profile="windows"), "c.json")
    json_out = tmp_path / "result.json"
    code = run_compare(baseline, current, json_out=json_out)
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert code == EXIT_MISMATCH
    assert payload["result"] == "mismatch"
    assert payload["environment_mismatches"]


def test_clean_comparison_json_result_ok(make_manifest, write_manifest, tmp_path: Path) -> None:
    baseline = write_manifest(make_manifest(), "b.json")
    current = write_manifest(make_manifest(), "c.json")
    json_out = tmp_path / "result.json"
    assert run_compare(baseline, current, json_out=json_out) == EXIT_OK
    payload = json.loads(json_out.read_text(encoding="utf-8"))
    assert payload["result"] == "ok"
    assert payload["exit_code"] == EXIT_OK


def test_removed_but_deselected_shows_hint(make_manifest, write_manifest, capsys) -> None:
    baseline = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_two")), "b.json"
    )
    current = write_manifest(
        make_manifest(
            selected=("tests/test_a.py::test_one",),
            deselected=("tests/test_a.py::test_two",),
        ),
        "c.json",
    )
    code = run_compare(baseline, current)
    out = capsys.readouterr().out
    assert code == EXIT_REMOVALS
    assert "check -k/-m/selection changes" in out
    assert "tests/test_a.py::test_two" in out


# ---------------------------------------------------------------------------
# demo
# ---------------------------------------------------------------------------


def test_demo_writes_manifests_and_explains(tmp_path: Path, capsys) -> None:
    demo_dir = tmp_path / "demo"
    assert run_demo(demo_dir) == EXIT_OK
    out = capsys.readouterr().out
    assert (demo_dir / "baseline.json").is_file()
    assert (demo_dir / "current.json").is_file()
    assert "synthetic example data" in out
    assert "test_apply_discount" in out

    # the demo must actually demonstrate a lost test
    code = run_compare(demo_dir / "baseline.json", demo_dir / "current.json")
    assert code == EXIT_REMOVALS


def test_demo_via_main_creates_default_dir(tmp_path: Path, capsys, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert _run("demo") == EXIT_OK
    assert (tmp_path / "demo" / "baseline.json").is_file()
    assert "Expected: exit code 1" in capsys.readouterr().out


def test_demo_custom_dir(tmp_path: Path) -> None:
    assert _run("demo", "--dir", str(tmp_path / "other")) == EXIT_OK
    assert (tmp_path / "other" / "current.json").is_file()


def test_demo_accepts_explicit_stream(tmp_path: Path) -> None:
    stream = io.StringIO()
    assert run_demo(tmp_path / "explicit", stdout=stream) == EXIT_OK
    assert "demo manifests written" in stream.getvalue()


def test_module_entry_point_works(tmp_path: Path) -> None:
    """`python -m pytest_collection_guard` must behave like the console script."""
    import os
    import subprocess
    import sys

    src = str(Path(__file__).resolve().parents[1] / "src")
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([src, env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    demo_dir = tmp_path / "demo"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest_collection_guard", "demo", "--dir", str(demo_dir)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert proc.returncode == EXIT_OK
    assert (demo_dir / "baseline.json").is_file()

    compare = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest_collection_guard",
            "compare",
            str(demo_dir / "baseline.json"),
            str(demo_dir / "current.json"),
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert compare.returncode == EXIT_REMOVALS
    assert "test_apply_discount" in compare.stdout


# ---------------------------------------------------------------------------
# argparse surface
# ---------------------------------------------------------------------------


def test_compare_via_main(make_manifest, write_manifest) -> None:
    baseline = write_manifest(make_manifest(), "b.json")
    current = write_manifest(make_manifest(), "c.json")
    assert _run("compare", str(baseline), str(current)) == EXIT_OK


def test_compare_via_main_with_allow(make_manifest, write_manifest, tmp_path: Path) -> None:
    baseline = write_manifest(
        make_manifest(selected=("tests/test_a.py::test_one", "tests/test_a.py::test_two")), "b.json"
    )
    current = write_manifest(make_manifest(selected=("tests/test_a.py::test_one",)), "c.json")
    allow = tmp_path / "removals.toml"
    allow.write_text(
        '[[removal]]\nid = "tests/test_a.py::test_two"\nreason = "example: removed on purpose"\n',
        encoding="utf-8",
    )
    assert _run("compare", str(baseline), str(current), "--allow", str(allow)) == EXIT_OK


def test_streams_can_be_redirected(make_manifest, write_manifest) -> None:
    baseline = write_manifest(make_manifest(), "b.json")
    current = write_manifest(make_manifest(), "c.json")
    stdout, stderr = io.StringIO(), io.StringIO()
    code = run_compare(baseline, current, stdout=stdout, stderr=stderr)
    assert code == EXIT_OK
    assert "RESULT: OK" in stdout.getvalue()
    assert stderr.getvalue() == ""


def test_package_main_module_runs_in_process(tmp_path: Path, monkeypatch) -> None:
    """``python -m pytest_collection_guard`` runs ``__main__.run()`` in-process.

    The subprocess path itself is covered by
    ``test_module_entry_point_works``; this test exercises the importable
    entry-point function with real arguments so the code path stays traced.
    """
    import sys

    from pytest_collection_guard.__main__ import run

    demo_dir = tmp_path / "demo"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["pytest-collection-guard", "demo", "--dir", str(demo_dir)])
    assert run() == EXIT_OK
    assert (demo_dir / "baseline.json").is_file()
    assert (demo_dir / "current.json").is_file()
