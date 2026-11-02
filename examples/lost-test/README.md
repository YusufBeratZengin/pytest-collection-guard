# Example: catching a lost test

This example uses obviously fake data (an invented "example shop"). It shows
the two-step workflow and what the guard reports.

## 1. Record a baseline inventory

```console
$ pytest --collect-only --collection-guard-out baseline.json --collection-guard-profile linux
```

Note: collection **imports** your test modules (module-level side effects run),
but test bodies and fixtures do **not** execute.

## 2. Later, on the same kind of run, record the current inventory

```console
$ pytest --collect-only --collection-guard-out current.json --collection-guard-profile linux
```

## 3. Compare

```console
$ pytest-collection-guard compare baseline.json current.json
```

If a test disappeared (renamed, deleted, moved out of `testpaths`, or its
parametrization lost a case) the command exits `1` and prints the exact
missing node IDs — even when a new test was added to replace it.

## Approving a removal

Write `removals.toml`:

```toml
[[removal]]
id = "tests/test_example_shop.py::test_apply_discount"
reason = "Feature dropped in 2.0 (issue #123, decided 2026-10-31)."
```

and compare with `--allow removals.toml` to make the removal pass review.

## The three scenarios this protects against

1. `testpaths` changes and a whole directory drops out of collection.
2. A test function is renamed and the old ID silently disappears.
3. A parametrization loses one case (e.g. `test_checkout[paypal]` vanishes).