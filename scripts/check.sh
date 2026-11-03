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
#
# Interpreter resolution: PYTHON (or python3) is preferred. If it lacks the
# dev tools, the script first looks for another python3 on PATH that already
# has them (e.g. a pip-less venv shadowing the system interpreter), and only
# then falls back to installing into the chosen interpreter — bootstrapping
# pip via ensurepip first, because venvs created --without-pip (or by uv)
# have no pip module.

set -euo pipefail

cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"

tools_ok() {
  "$1" -m ruff --version >/dev/null 2>&1 \
    && "$1" -m mypy --version >/dev/null 2>&1 \
    && "$1" -c "import pytest_cov" >/dev/null 2>&1
}

if ! tools_ok "$PY"; then
  if [ -z "${PYTHON:-}" ]; then
    echo "check.sh: dev tools missing for '$PY'; looking for an interpreter that has them ..."
    BASE_PY="$("$PY" -c 'import os, sys; print(os.path.join(sys.base_prefix, "bin", "python3"))' 2>/dev/null || true)"
    for cand in $(type -aP python3 python 2>/dev/null || true) "$BASE_PY"; do
      [ -x "$cand" ] || continue
      if tools_ok "$cand"; then
        PY="$cand"
        break
      fi
    done
  fi
fi

if ! tools_ok "$PY"; then
  echo "check.sh: installing dev dependencies (ruff, mypy, pytest-cov) into $PY ..."
  if ! "$PY" -m pip --version >/dev/null 2>&1; then
    # venvs created --without-pip (or by uv) have no pip module; bootstrap it.
    "$PY" -m ensurepip --upgrade >/dev/null 2>&1 \
      || "$PY" -m ensurepip >/dev/null 2>&1 \
      || true
  fi
  if "$PY" -m pip --version >/dev/null 2>&1; then
    "$PY" -m pip install -e ".[dev]" --quiet
  fi
fi

if ! tools_ok "$PY"; then
  echo "check.sh: cannot run the dev tools (ruff, mypy, pytest-cov) with any python found." >&2
  echo "check.sh: install them for your interpreter, e.g.:" >&2
  echo "  python3 -m pip install -e \".[dev]\"   (or: python3 -m ensurepip --upgrade first)" >&2
  exit 1
fi
echo "check.sh: using interpreter: $PY"

echo "== ruff lint =="
"$PY" -m ruff check src tests

echo "== ruff format =="
"$PY" -m ruff format --check src tests

echo "== mypy (strict) =="
"$PY" -m mypy src

echo "== pytest + coverage (>= 85%, branch) =="
"$PY" -m pytest --cov=pytest_collection_guard --cov-branch --cov-fail-under=85

echo "== secret scan (dependency-free) =="
# Scope and boundaries: dependency-free heuristic regex scan targeting common
# credential types (AWS key IDs, GitHub PATs, Slack tokens, PEM private key blocks,
# and generic credential variable assignments with literal strings).
# This is an early repository sanity gate for local commits and CI; it does not
# substitute for dedicated entropy-based secret scanning or commercial enterprise SAST tooling.
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