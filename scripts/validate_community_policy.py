#!/usr/bin/env python3
"""Validate the M28 community/security/Apache-2.0 license contract."""

from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


class ContractError(ValueError):
    pass


SECURITY_REQUIRED = (
    "# Security policy",
    "## Supported versions",
    "## What to report privately",
    "## How to report",
    "Private vulnerability reporting",
    "Do not put exploit details",
    "Use GitHub's **Report a vulnerability** flow",
    "If the flow is unavailable, open only a minimal public issue",
    "no fixed response or remediation timeline is promised",
)

CONTRIBUTING_REQUIRED = (
    "# Contributing to Solo VPS",
    "## License",
    "Apache License 2.0",
    "compatible with distribution under Apache-2.0",
    "## Before changing code",
    "## Scope discipline",
    "## Local validation",
    "make validate",
    "## Security and production boundaries",
    "SECURITY.md",
    "## Change / pull-request evidence",
    "PROJECT_PASSPORT.md",
    "ROADMAP.md",
)

LICENSE_NOTE_REQUIRED = (
    "# License decision — Apache-2.0",
    "Apache License 2.0",
    "2026-08-11",
    "SPDX identifier: `Apache-2.0`",
    "canonical text: the repository-root `LICENSE` file",
    "not legal advice",
)

APACHE_2_LICENSE_SHA256 = "cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30"

PLACEHOLDER_PATTERNS = (
    re.compile(r"\bTODO\b", re.IGNORECASE),
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"security@example\.com", re.IGNORECASE),
    re.compile(r"your[-_ ]?email", re.IGNORECASE),
    re.compile(r"<[^>]*(email|name|holder)[^>]*>", re.IGNORECASE),
)


def read(path: Path) -> str:
    if not path.is_file():
        raise ContractError(f"required community file is missing: {path}")
    return path.read_text(encoding="utf-8")


def validate_no_placeholders(label: str, text: str) -> None:
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(text):
            raise ContractError(f"{label} contains placeholder content matching {pattern.pattern!r}")


def validate_local_links(root: Path, path: Path, markdown: str) -> None:
    for target in re.findall(r"\]\(([^)]+)\)", markdown):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (path.parent / clean).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ContractError(f"{path.name} link escapes repository: {target}") from exc
        if not resolved.exists():
            raise ContractError(f"{path.name} link target does not exist: {target}")


def validate_community_policy(root: Path) -> None:
    security_path = root / "SECURITY.md"
    contributing_path = root / "CONTRIBUTING.md"
    license_note_path = root / "docs" / "license-choice.md"
    readme_path = root / "README.md"
    docs_index_path = root / "docs" / "index.md"
    passport_path = root / "PROJECT_PASSPORT.md"
    roadmap_path = root / "ROADMAP.md"
    license_path = root / "LICENSE"

    security = read(security_path)
    contributing = read(contributing_path)
    license_note = read(license_note_path)
    readme = read(readme_path)
    docs_index = read(docs_index_path)
    passport = read(passport_path)
    roadmap = read(roadmap_path)

    for phrase in SECURITY_REQUIRED:
        if phrase not in security:
            raise ContractError(f"SECURITY.md missing required policy phrase: {phrase!r}")
    for phrase in CONTRIBUTING_REQUIRED:
        if phrase not in contributing:
            raise ContractError(f"CONTRIBUTING.md missing required contribution phrase: {phrase!r}")
    for phrase in LICENSE_NOTE_REQUIRED:
        if phrase not in license_note:
            raise ContractError(f"license decision note missing required phrase: {phrase!r}")

    validate_no_placeholders("SECURITY.md", security)
    validate_no_placeholders("CONTRIBUTING.md", contributing)
    validate_no_placeholders("license decision note", license_note)

    if "do not include vulnerability details" not in security.lower():
        raise ContractError("SECURITY.md must fail closed when no private channel is configured")
    if "production" not in contributing.lower() or "secrets" not in contributing.lower():
        raise ContractError("CONTRIBUTING.md must cover production and secret-handling boundaries")
    if "PASS" not in contributing or "NOT RUN" not in contributing:
        raise ContractError("CONTRIBUTING.md must require honest validation evidence")

    if "The project license is **Apache-2.0**" not in passport or "SPDX-License-Identifier: Apache-2.0" not in passport:
        raise ContractError("Project Passport must record the accepted Apache-2.0 decision")
    if not license_path.is_file():
        raise ContractError("root LICENSE is required after the Apache-2.0 owner decision")
    license_digest = hashlib.sha256(license_path.read_bytes()).hexdigest()
    if license_digest != APACHE_2_LICENSE_SHA256:
        raise ContractError("root LICENSE must be the canonical unmodified Apache License 2.0 text")

    if "SECURITY.md" not in readme or "CONTRIBUTING.md" not in readme or "docs/license-choice.md" not in readme or "[`LICENSE`](LICENSE)" not in readme:
        raise ContractError("README must surface security, contribution, and Apache-2.0 license policy")
    # MkDocs validates links relative to docs_dir. Repository-root policy files
    # are surfaced from README rather than linked through invalid ../ paths.
    for forbidden in ("../SECURITY.md", "../CONTRIBUTING.md", "../LICENSE"):
        if forbidden in docs_index:
            raise ContractError(f"docs/index.md must not contain repository-root link outside docs_dir: {forbidden}")

    if "M28 — SECURITY / CONTRIBUTING / LICENSE" not in roadmap:
        raise ContractError("ROADMAP no longer contains M28 community-policy milestone")

    for path, text in (
        (security_path, security),
        (contributing_path, contributing),
        (license_note_path, license_note),
    ):
        validate_local_links(root, path, text)

    print(
        "PASS community policy contract: SECURITY/CONTRIBUTING are meaningful, "
        "Apache-2.0 license state and public documentation links are consistent"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate_community_policy(Path(args.root).resolve())
    except (OSError, ContractError) as exc:
        print(f"ERROR community policy contract: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
