#!/usr/bin/env bash
# One-shot quality gate for pytest-collection-guard.
#
#   bash scripts/check.sh
#
# Runs: ruff lint, ruff format check, mypy strict, pytest with branch
# coverage >= 85%. Exits 0 only when every step passes.
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

echo "check.sh: all checks passed"