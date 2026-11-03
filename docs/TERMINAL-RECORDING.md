# Terminal recording: catching a lost test

A real, unedited terminal session showing the full workflow on the synthetic
example project in `examples/lost-test/` (all data is obviously fake). Every
command and every line of output below was produced by the installed package
(`pip install .`), on Linux, Python 3.14 / pytest 9.2.

## The scenario

A test function is renamed (`test_apply_discount` → `test_apply_discount_v2`)
during a refactor. The test **count stays at 4** — nothing looks wrong — but
one expected test ID is gone.

## Step 1 — record the baseline inventory

```console
$ pytest --collect-only -q --collection-guard-out baseline.json --collection-guard-profile linux
tests/test_example_shop.py::test_add_item
tests/test_example_shop.py::test_apply_discount
tests/test_example_shop.py::test_checkout[card]
tests/test_example_shop.py::test_checkout[paypal]

collection-guard: manifest written to baseline.json (status: ok, 4 collected node id(s))
4 tests collected in 0.01s
exit: 0
```

## Step 2 — after the rename, record the current inventory

```console
$ pytest --collect-only -q --collection-guard-out current.json --collection-guard-profile linux
tests/test_example_shop.py::test_add_item
tests/test_example_shop.py::test_apply_discount_v2
tests/test_example_shop.py::test_checkout[card]
tests/test_example_shop.py::test_checkout[paypal]

collection-guard: manifest written to current.json (status: ok, 4 collected node id(s))
4 tests collected in 0.01s
exit: 0
```

Both runs report "4 collected". This is exactly why counting is not enough.

## Step 3 — compare against the baseline (this is where CI goes red)

```console
$ pytest-collection-guard compare baseline.json current.json
pytest-collection-guard compare
  baseline: baseline.json (profile 'linux', 4 selected)
  current:  current.json (profile 'linux', 4 selected)

REMOVED (1):
  - tests/test_example_shop.py::test_apply_discount

ADDED (1):
  + tests/test_example_shop.py::test_apply_discount_v2

RESULT: FAIL — 1 unapproved removal(s); justify them in a removals TOML or restore the tests.
exit: 1
```

## Step 4 — approve the removal with a written reason

`removals.toml` (reviewed like code):

```toml
[[removal]]
id = "tests/test_example_shop.py::test_apply_discount"
reason = "Example: renamed to test_apply_discount_v2 on purpose (issue #123)."
```

```console
$ pytest-collection-guard compare baseline.json current.json --allow removals.toml
pytest-collection-guard compare
  baseline: baseline.json (profile 'linux', 4 selected)
  current:  current.json (profile 'linux', 4 selected)

REMOVED (1):
  - tests/test_example_shop.py::test_apply_discount

ADDED (1):
  + tests/test_example_shop.py::test_apply_discount_v2

APPROVED REMOVALS (1):
  - tests/test_example_shop.py::test_apply_discount
      reason: Example: renamed to test_apply_discount_v2 on purpose (issue #123).

RESULT: OK — no unapproved removals.
exit: 0
```

## Try it yourself

```console
$ pytest-collection-guard demo --dir demo
$ pytest-collection-guard compare demo/baseline.json demo/current.json
```

The `demo` command writes the two manifests of this scenario (synthetic data)
without needing a project; the second command exits `1` and reports the lost
test ID. See `examples/lost-test/` for the runnable pytest project.