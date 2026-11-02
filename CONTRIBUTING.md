# Contributing

Thanks for your interest in improving pytest-collection-guard.

## Ground rules

- Be kind and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
- No personal data, real credentials, or real-looking secrets in code, tests,
  fixtures or examples. Example data must be obviously synthetic
  ("example", "fake", placeholder values).
- The tool must never change *which* tests run — it observes collection only.
- Never let CI auto-accept a baseline: baseline updates are reviewed changes.

## Development setup

```console
$ git clone https://github.com/YusufBeratZengin/pytest-collection-guard
$ cd pytest-collection-guard
$ python -m pip install -e ".[dev]"
$ bash scripts/check.sh
```

`scripts/check.sh` is the definition of done: ruff lint, ruff format check,
mypy (strict), and pytest with branch coverage >= 85%. All of it must pass
locally before you open a PR. None of the tests need network access.

## Testing conventions

- Unit tests live in `tests/`; integration tests that drive real pytest runs
  live in `tests/pytester/` (hermetic: nested runs disable plugin autoload and
  load the plugin explicitly).
- Error paths matter as much as happy paths: invalid manifests, malformed
  allow files, collection errors and write failures all have tests. Keep it
  that way.
- A fix needs a test that fails without the fix.

## Pull requests

- Keep PRs focused; update `CHANGELOG.md` under `[Unreleased]`.
- Describe the user-visible effect and how you verified it (paste the
  `check.sh` result).
- New behavior needs docs (README.md **and** README.tr.md).

## Reporting bugs / requesting features

Use the issue templates. For collection surprises, attach the relevant
manifest JSON (redact node IDs if they contain sensitive names) and the exact
pytest command line.

## Good first issues

See the `good first issue` label in the issue tracker — small, well-scoped
tasks (docs examples, report formatting options) are ideal first
contributions.

## Security

Please do **not** open public issues for vulnerabilities — see
[SECURITY.md](SECURITY.md).