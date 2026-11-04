# Security Policy

## Supported versions

| Version | Supported |
| ------- | --------- |
| 0.1.x   | yes       |

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue.

- Preferred: GitHub **private vulnerability reporting** on this repository
  (Security → Report a vulnerability).
- If that is unavailable, open a normal GitHub issue asking for a private
  contact channel — do not include vulnerability details in the issue.

You will get an acknowledgement within 7 days and a status update within 14
days. Please include: affected version, reproduction steps, impact, and any
suggested fix.

## Scope and expectations

- This tool only *reads* collection state and writes local JSON/TOML/Markdown
  files. It runs no network calls at runtime and holds no credentials.
- Secrets must always be provided via environment variables — never committed,
  never printed in reports or test fixtures.
- Manifests record test node IDs verbatim. If your parametrized test IDs embed
  personal data, your manifests will too; treat them as local artifacts and
  review before sharing.
- CI must never auto-refresh the baseline inventory: that would let a
  compromised PR silently remove expected tests.

## Dependency posture

The runtime dependency surface is intentionally tiny (pytest only; the CLI is
standard library). Dev dependencies are pinned ranges in `pyproject.toml` and
monitored by Dependabot.

## Secret scanning scope and limitations

The repository quality gate (`scripts/check.sh`) performs a dependency-free heuristic scan for common accidental credentials:
- AWS access key IDs (`AKIA` prefixes)
- GitHub personal access tokens (`ghp_` prefixes)
- Slack tokens (`xox` prefixes)
- PEM private key blocks (`BEGIN PRIVATE KEY`)
- Common credential assignment statements with hard-coded values

A "clean" scan result confirms that none of these predefined credential signatures were detected in repository files. The scan covers the whole working tree — including `demo/`, `examples/` and `docs/` — and skips only VCS metadata, tool caches and generated build artifacts. It serves as a fast pre-commit sanity check and does not replace deep entropy-based scanning or full enterprise SAST tooling.
