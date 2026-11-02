# pytest-collection-guard

Fail CI when expected pytest tests disappear from collection.

"100 tests passed" does not mean it was the *same* 100 tests. A `testpaths`
edit, a typo in a rename, or one lost parametrization case silently shrinks
your test suite while the run stays green. pytest-collection-guard records
which test IDs pytest *collects* and turns unexpected loss into a CI failure.

- **English** · [Türkçe (README.tr.md)](README.tr.md)

## Why

Pytest discovery depends on configuration: `testpaths`, `norecursedirs`, and
the file/class/function naming rules all decide what gets collected
([official discovery rules](https://docs.pytest.org/en/stable/explanation/goodpractices.html#conventions-for-python-test-discovery)).
A config change can silently change the collected test set, and some decorator
layouts have historically hidden tests from discovery entirely
([pytest issue #10525](https://github.com/pytest-dev/pytest/issues/10525) — a
historical example, not a claim about current pytest).

Existing tools export collection/results as JSON
([pytest-json-report](https://github.com/numirias/pytest-json-report)) or show
a re-collection diff interactively
([pytest-deck](https://mchalela/pytest-deck)). This project is different: a
versioned baseline inventory, an environment profile, a **justified-removal
list**, and a mandatory loss gate in CI. It never changes which tests run.

## Install

```console
$ python -m pip install .
```

Runtime dependencies: **pytest only** (this is a pytest plugin; the CLI half
uses just the standard library — `argparse`, `json`, `pathlib`, `platform`,
`tomllib`). Dev-only tools (`ruff`, `mypy`, `pytest-cov`) come from the `dev`
extra.

## 30-second example

```console
$ pytest-collection-guard demo --dir demo
demo manifests written to demo/ (synthetic example data):
  demo/baseline.json  (4 selected tests)
  demo/current.json   (4 selected tests)

Both files contain 4 tests — but not the same 4: 'test_apply_discount' silently became 'test_apply_discount_v2'.

Now compare them:
  pytest-collection-guard compare demo/baseline.json demo/current.json

Expected: exit code 1, reporting test_apply_discount as REMOVED.

$ pytest-collection-guard compare demo/baseline.json demo/current.json
pytest-collection-guard compare
  baseline: demo/baseline.json (profile 'linux', 4 selected)
  current:  demo/current.json (profile 'linux', 4 selected)

REMOVED (1):
  - tests/test_example_shop.py::test_apply_discount

ADDED (1):
  + tests/test_example_shop.py::test_apply_discount_v2

RESULT: FAIL — 1 unapproved removal(s); justify them in a removals TOML or restore the tests.

$ echo $?
1
```

Same total count (4 → 4), and the guard still fails: additions never offset
removals.

## The real workflow

Record a baseline on a known-good revision, then check every CI run against it.
(`examples/lost-test/` is a runnable copy of this scenario — the terminal
output below is real.)

```console
$ pytest --collect-only --collection-guard-out baseline.json --collection-guard-profile linux
...
collection-guard: manifest written to baseline.json (status: ok, 4 collected node id(s))
========================== 4 tests collected in 0.05s ==========================

$ pytest --collect-only --collection-guard-out current.json --collection-guard-profile linux
...
collection-guard: manifest written to current.json (status: ok, 4 collected node id(s))

$ pytest-collection-guard compare baseline.json current.json
pytest-collection-guard compare
  baseline: baseline.json (profile 'linux', 4 selected)
  current:  current.json (profile 'linux', 4 selected)

REMOVED (1):
  - tests/test_example_shop.py::test_apply_discount

ADDED (1):
  + tests/test_example_shop.py::test_apply_discount_v2

RESULT: FAIL — 1 unapproved removal(s); justify them in a removals TOML or restore the tests.
```

### Approving a real removal

When a test is *intentionally* removed, justify it in a reviewed TOML file:

```toml
# removals.toml — reviewed like code; every entry needs a reason
[[removal]]
id = "tests/test_example_shop.py::test_apply_discount"
reason = "Feature dropped in 2.0 (issue #123, decided 2026-10-31)."
```

```console
$ pytest-collection-guard compare baseline.json current.json --allow removals.toml
...
APPROVED REMOVALS (1):
  - tests/test_example_shop.py::test_apply_discount
      reason: Feature dropped in 2.0 (issue #123, decided 2026-10-31).

RESULT: OK — no unapproved removals.
```

An allow entry whose test did **not** disappear is reported as `STALE ALLOW
ENTRIES`, so the file cannot rot into a blanket ignore.

## Exit codes (the CI gate)

| code | meaning |
|------|---------|
| `0`  | no unapproved removals (clean, or all removals justified) |
| `1`  | at least one test disappeared without approval |
| `2`  | comparison refused: profile/collection-argument mismatch, a manifest from an errored collection, or invalid input |

Exit `2` is deliberate: comparing a Linux inventory against a Windows one, or
`-k`-filtered run against an unfiltered one, would report fake losses — the
guard refuses instead of guessing.

## CI recipe (GitHub Actions)

```yaml
- name: Collect inventory
  run: pytest --collect-only --collection-guard-out current.json --collection-guard-profile linux
- name: Check expected tests are still collected
  run: pytest-collection-guard compare ci/baseline.json current.json --allow ci/removals.toml
```

Commit `ci/baseline.json` (per profile!) and `ci/removals.toml` to the repo.
`--json report.json` writes a machine-readable result for other tooling.

## What gets recorded

A manifest strictly separates two kinds of data:

- **identity** — the sorted `selected`/`deselected` test node IDs. This is
  what gets compared. (Node IDs are rootdir-relative; parametrized IDs like
  `test_checkout[paypal]` are recorded verbatim.)
- **environment** — profile label, platform, Python/pytest versions, rootdir,
  and collection-affecting arguments (`testpaths`, naming rules, `norecursedirs`,
  positional args, `-k`, `-m`). Only the **profile** and the **collection
  arguments** are enforced for comparability; the rest is recorded for humans.

## Important behavior notes

- **Test bodies and fixtures never run** during `--collect-only` collection.
- **Collection imports your test modules** (and `conftest.py`), so module-level
  import side effects do execute. Keep test modules import-safe.
- **A collection error produces no valid inventory**: the manifest is written
  with `"status": "error"` and `compare` refuses it (exit `2`). A partial
  collection can never masquerade as lost tests.
- **The guard never changes test selection** — it only observes collection.
- **The baseline is never auto-updated** by CI; refreshing it is a reviewed,
  human decision.
- Platform, Python and pytest versions are recorded but not enforced; run one
  baseline **per profile** instead of diffing inventories across platforms.

## What this tool is NOT

- It does not measure coverage, generate missing tests, or speed up test runs.
- It makes no claim that a test count represents quality — the opposite: it
  exists because counts hide identity loss.
- Report content is local; parametrized IDs can contain personal data if you
  put it there. The bundled examples use obviously synthetic data.

## Development

```console
$ python -m pip install -e ".[dev]"
$ bash scripts/check.sh        # lint + format + mypy strict + tests + >= 85% branch coverage
$ python -m pytest --cov=pytest_collection_guard --cov-branch --cov-fail-under=85
```

Tests run against real nested pytest sessions (pytester); none need network
access. Linux and Windows are covered by CI.

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 YusufBeratZengin.