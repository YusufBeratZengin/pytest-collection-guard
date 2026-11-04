"""Opt-in pytest plugin: record collected test identities to a manifest.

The guard is **off unless explicitly enabled**: nothing happens on a normal
``pytest`` run — no file is written and no behavior changes. Enable it with::

    pytest --collect-only --collection-guard-out current.json \\
           --collection-guard-profile linux

What is (and is not) executed: the plugin only observes *collection*. Test
bodies and fixtures never run during a ``--collect-only`` run — but collection
itself **imports your test modules** (and their ``conftest.py`` files), so
module-level import side effects do execute. Keep test modules import-safe.

Integrity rule: if collection fails (broken import, syntax error, ...), the
run did not see the real test set. The manifest is then written with
``status: "error"`` and the ``compare`` command refuses to use it as an
inventory — a partial collection can never masquerade as lost tests.
"""

from __future__ import annotations

__all__ = ["pytest_addoption", "pytest_configure"]

import platform
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from pytest_collection_guard.manifest import (
    STATUS_ERROR,
    STATUS_OK,
    CollectionArgs,
    Environment,
    Manifest,
    save_manifest,
)

_OPT_OUT = "collection_guard_out"
_OPT_PROFILE = "collection_guard_profile"


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup(
        "collection-guard", "collection inventory recording (pytest-collection-guard)"
    )
    group.addoption(
        "--collection-guard-out",
        action="store",
        default=None,
        metavar="PATH",
        help=(
            "write a collection manifest (selected/deselected test identities plus "
            "environment) to PATH; the guard is inactive without this option"
        ),
    )
    group.addoption(
        "--collection-guard-profile",
        action="store",
        default="default",
        metavar="NAME",
        help=(
            "environment profile label stored in the manifest (e.g. linux, windows); "
            "manifests with different profiles are never compared (default: %(default)s)"
        ),
    )


def pytest_configure(config: pytest.Config) -> None:
    out = config.getoption(_OPT_OUT)
    if not out:
        return  # opt-in: normal runs are untouched
    recorder = _GuardRecorder(
        out_path=Path(str(out)),
        profile=str(config.getoption(_OPT_PROFILE)),
    )
    config.pluginmanager.register(recorder, "collection_guard_recorder")


# ---------------------------------------------------------------------------
# helpers (module level so they are unit-testable without a full pytest run)
# ---------------------------------------------------------------------------


def _ini_list(config: pytest.Config, name: str) -> tuple[str, ...]:
    """Read a pytest ini option as a tuple of strings; missing -> empty."""
    try:
        value = config.getini(name)
    except (ValueError, KeyError):
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def _option_str(config: pytest.Config, name: str) -> str | None:
    value = getattr(config.option, name, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _option_sequence(config: pytest.Config, name: str) -> tuple[str, ...]:
    value = getattr(config.option, name, None)
    if not value:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(str(item) for item in value)


def normalize_positional_args(args: Sequence[str], rootdir: Path) -> tuple[str, ...]:
    """Store positional collection args portably (POSIX separators, rootdir-relative).

    Windows backslashes and absolute paths would otherwise make two identical
    collection scopes look different when compared across machines; paths
    outside ``rootdir`` are kept with forward slashes as-is.
    """
    normalized: list[str] = []
    for arg in args:
        path = Path(arg)
        if path.is_absolute():
            try:
                path = path.relative_to(rootdir)
            except ValueError:
                pass
        normalized.append(path.as_posix())
    return tuple(normalized)


def build_collection_args(config: pytest.Config) -> CollectionArgs:
    """Snapshot every setting that changes *which* tests are collected."""
    rootdir = Path(str(config.rootpath))
    ignore_raw = _option_sequence(config, "ignore")
    ignore_glob_raw = _option_sequence(config, "ignore_glob")
    deselect_raw = _option_sequence(config, "deselect")
    return CollectionArgs(
        testpaths=_ini_list(config, "testpaths"),
        norecursedirs=_ini_list(config, "norecursedirs"),
        python_files=_ini_list(config, "python_files"),
        python_classes=_ini_list(config, "python_classes"),
        python_functions=_ini_list(config, "python_functions"),
        positional_args=normalize_positional_args(list(config.args), rootdir),
        keyword=_option_str(config, "keyword"),
        markexpr=_option_str(config, "markexpr"),
        ignore=tuple(sorted(normalize_positional_args(ignore_raw, rootdir))),
        ignore_glob=tuple(sorted(arg.replace("\\", "/") for arg in ignore_glob_raw)),
        deselect=tuple(sorted(arg.replace("\\", "/") for arg in deselect_raw)),
    )


def build_environment(config: pytest.Config, profile: str) -> Environment:
    return Environment(
        profile=profile,
        platform=platform.platform(),
        python_version=platform.python_version(),
        pytest_version=str(getattr(pytest, "__version__", "")),
        rootdir=str(config.rootpath),
    )


# ---------------------------------------------------------------------------
# recorder
# ---------------------------------------------------------------------------


@dataclass(eq=False)
class _GuardRecorder:
    """Collects identity data during one pytest session and writes the manifest.

    Registered as a plugin *instance* in ``pytest_configure`` so its hook state
    is bound to a single ``Config`` — nested in-process pytest runs (as used by
    the test suite via pytester) never share state.
    """

    out_path: Path
    profile: str
    collected: tuple[str, ...] = ()
    errors: list[str] = field(default_factory=list)
    written: Path | None = None
    write_error: str | None = None

    # -- hooks -------------------------------------------------------------

    @pytest.hookimpl(tryfirst=True)
    def pytest_collection_modifyitems(
        self, config: pytest.Config, items: list[pytest.Item]
    ) -> None:
        # tryfirst: snapshot the full discovered set before other plugins
        # (e.g. -k/-m filtering) deselect anything.
        self.collected = tuple(item.nodeid for item in items)

    def pytest_collectreport(self, report: pytest.CollectReport) -> None:
        if not report.failed:
            return
        longrepr = report.longrepr
        detail = str(longrepr) if longrepr is not None else "unknown collection error"
        self.errors.append(f"{report.nodeid}: {detail}"[:2000])

    def pytest_internalerror(self, excrepr: Any, excinfo: Any) -> None:
        self.errors.append(f"internal error: {excrepr}")

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: object) -> None:
        self._write_manifest(session)

    def pytest_terminal_summary(
        self,
        terminalreporter: pytest.TerminalReporter,
        exitstatus: object,
        config: pytest.Config,
    ) -> None:
        if self.written is not None:
            status = STATUS_ERROR if self.errors else STATUS_OK
            terminalreporter.write_line(
                f"collection-guard: manifest written to {self.written} "
                f"(status: {status}, {len(self.collected)} collected node id(s))"
            )
        if self.write_error is not None:
            terminalreporter.write_line(
                f"collection-guard: FAILED to write manifest: {self.write_error}"
            )

    # -- manifest ----------------------------------------------------------

    def _write_manifest(self, session: pytest.Session) -> None:
        selected_ids = tuple(sorted({item.nodeid for item in session.items}))
        collected_ids = set(self.collected) or set(selected_ids)
        deselected_ids = tuple(sorted(collected_ids - set(selected_ids)))
        status = STATUS_ERROR if self.errors else STATUS_OK
        manifest = Manifest(
            selected=selected_ids,
            deselected=deselected_ids,
            environment=build_environment(session.config, self.profile),
            collection_args=build_collection_args(session.config),
            status=status,
            errors=tuple(self.errors),
        )
        try:
            save_manifest(self.out_path, manifest)
        except OSError as exc:
            self.write_error = f"{self.out_path}: {exc}"
            session.exitstatus = pytest.ExitCode.INTERNAL_ERROR
            if self.out_path.is_file():
                self.out_path.unlink(missing_ok=True)
            return
        self.written = self.out_path
