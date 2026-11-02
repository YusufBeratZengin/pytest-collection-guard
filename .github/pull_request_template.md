## What and why

<!-- What does this PR change, and which user-visible problem does it solve? -->

## Verification

<!-- Paste the result of: bash scripts/check.sh -->

- [ ] `bash scripts/check.sh` passes locally (ruff, ruff format, mypy strict, tests, >= 85% branch coverage)
- [ ] A fix includes a test that fails without the fix
- [ ] Error paths are covered where relevant (invalid input, mismatch, policy errors)
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Docs updated in **both** README.md and README.tr.md (user-visible changes)
- [ ] No secrets, personal data or real-looking credentials in code, tests or fixtures
- [ ] The guard still never changes which tests run (observational only)

## Out of scope

<!-- Anything deliberately left for follow-up PRs? -->