# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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