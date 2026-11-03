#!/usr/bin/env bash
# One-shot quality gate for pytest-collection-guard.
#
#   bash scripts/check.sh
#
# Runs: ruff lint, ruff format check, mypy strict, pytest with branch
# coverage >= 85%, a dependency-free secret scan and a license check.
# Exits 0 only when every step passes.
# Works on plain Linux with python3; needs the dev tools (ruff, mypy,
# pytest-cov) which are installed once via: python3 -m pip install -e ".[dev]"
# (the script attempts that automatically if they are missing).
# No step needs network access once dependencies are installed.

set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"

if ! "$PY" -m ruff --version >/dev/null 2>&1 \
   || ! "$PY" -m mypy --version >/dev/null 2>&1 \
   || ! "$PY" -c "import pytest_cov" >/dev/null 2>&1; then
  echo "check.sh: installing dev dependencies (ruff, mypy, pytest-cov) ..."
  "$PY" -m pip install -e ".[dev]" --quiet
fi

echo "== ruff lint =="
"$PY" -m ruff check src tests

echo "== ruff format =="
"$PY" -m ruff format --check src tests

echo "== mypy (strict) =="
"$PY" -m mypy src

echo "== pytest + coverage (>= 85%, branch) =="
"$PY" -m pytest --cov=pytest_collection_guard --cov-branch --cov-fail-under=85

echo "== secret scan (dependency-free) =="
SECRET_HITS="$(grep -rInE \
  --exclude-dir=.git --exclude-dir=.mypy_cache --exclude-dir=.ruff_cache \
  --exclude-dir=.pytest_cache --exclude-dir=demo --exclude-dir='*egg-info' \
  -I \
  -e 'AKIA[0-9A-Z]{16}' \
  -e 'ghp_[A-Za-z0-9]{36}' \
  -e 'xox[baprs]-[A-Za-z0-9-]{10,}' \
  -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
  -e "(api[_-]?key|secret|token|passwd|password)[[:space:]]*[=:][[:space:]]*[\"'][^\"']{8,}[\"']" \
  . || true)"
if [ -n "$SECRET_HITS" ]; then
  echo "$SECRET_HITS"
  echo "check.sh: possible secret(s) found — remove them (never commit credentials)" >&2
  exit 1
fi
echo "check.sh: secret scan clean"

echo "== license check =="
grep -q "^MIT License" LICENSE
grep -q "Copyright (c) 2026 YusufBeratZengin" LICENSE
echo "check.sh: license check passed"

echo "check.sh: all checks passed"