# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Packaging and clean wheel installation CI job in `.github/workflows/ci.yml` verifying entry points and CLI commands in an isolated virtual environment.
- Regression tests in `tests/pytester/test_plugin_integration.py` covering empty test collection, failed collection reporting, and nested conftest proxy hook filtering.
- Unit test in `tests/test_plugin_unit.py` verifying `_GuardRecorder` hashability and set operations.

### Fixed

- Made `_GuardRecorder` hashable (`@dataclass(eq=False)`) so pluggy's `subset_hook_caller` and pytest's `FSHookProxy` can perform set operations without `TypeError: unhashable type: '_GuardRecorder'` on empty collections and multi-conftest trees.
- Hardened secret scan in `scripts/check.sh` by distinguishing grep exit code 1 (no match) from execution errors (exit code >= 2), preventing masked scanner failures.
- Fixed pytest-deck repository link in `README.md` and `README.tr.md`.

- Snapshot `--ignore`, `--ignore-glob`, and `--deselect` options in collection arguments so scope changes produce exit code 2 (mismatch) rather than false test loss.
- Atomic manifest writing via temporary file and `os.replace` to prevent corrupted inventories on interrupted runs.
- Immediate CI failure on manifest write error (`INTERNAL_ERROR`) and invalidation of stale output files.
- Documented secret scanning heuristics and collection scope boundaries in `README.md`, `README.tr.md`, `SECURITY.md`, and `scripts/check.sh`.

## [0.1.0] - 2026-11-03

### Added

- Opt-in pytest collector: `pytest --collect-only --collection-guard-out PATH
  --collection-guard-profile NAME` writes a JSON manifest of collected test
  identities. Normal pytest runs are untouched without the flag.
- Manifest schema v1 with strict separation of test **identity**
  (selected/deselected node IDs) and **environment** (profile, platform,
  Python/pytest versions, rootdir, collection-affecting arguments).
- `pytest-collection-guard compare BASELINE CURRENT [--allow REMOVALS.toml]
  [--json PATH]` with CI-ready exit codes: `0` clean, `1` unapproved removal(s),
  `2` refused comparison (profile/argument mismatch, errored-collection
  manifest, or invalid input).
- Justified-removal policy: TOML `[[removal]]` entries require a non-empty
  `reason`; stale allow entries are reported.
- `pytest-collection-guard demo --dir DIR` writes synthetic manifests that
  demonstrate a lost test.
- Incomplete/errored collection manifests (`"status": "error"`) are refused by
  `compare` so a partial collection can never fake test loss.
- Hint when removed tests still exist but are deselected (`-k`/`-m` changes).
- GitHub Actions CI (Linux + Windows), Dependabot, issue/PR templates,
  `scripts/check.sh` quality gate (ruff, mypy strict, pytest with >= 85% branch
  coverage).

[Unreleased]: https://github.com/YusufBeratZengin/pytest-collection-guard/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/YusufBeratZengin/pytest-collection-guard/releases/tag/v0.1.0