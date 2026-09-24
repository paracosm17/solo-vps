#!/usr/bin/env python3
"""Validate the public README and canonical Quick Start documentation contract."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


REQUIRED_HEADINGS = (
    "## What Solo VPS is",
    "## Current status",
    "## What `make bootstrap` changes",
    "## Quick Start",
    "## Safety boundaries",
    "## Documentation",
)

PRIMARY_LIFECYCLE = (
    "make setup",
    "make apply",
    "make secure",
    "make platform",
    "make verify",
)


class ContractError(ValueError):
    pass


def make_targets(makefile_text: str) -> set[str]:
    targets: set[str] = set()
    for line in makefile_text.splitlines():
        if line.startswith(("\t", " ")) or ":=" in line or "?=" in line or "=" in line.split(":", 1)[0]:
            continue
        match = re.match(r"^([A-Za-z0-9_.-]+):(?:\s|$)", line)
        if match:
            targets.add(match.group(1))
    return targets


def referenced_make_targets(markdown: str) -> set[str]:
    # Validate executable Make command lines. This deliberately ignores package
    # lists such as `apt-get install ... make git ...` and prose mentions.
    return set(re.findall(r"(?m)^[ \t]*make\s+([A-Za-z0-9_.-]+)\b", markdown))


def validate_links(root: Path, markdown_path: Path, markdown: str) -> None:
    for target in re.findall(r"\]\(([^)]+)\)", markdown):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        clean = target.split("#", 1)[0]
        if not clean:
            continue
        resolved = (markdown_path.parent / clean).resolve()
        try:
            resolved.relative_to(root.resolve())
        except ValueError as exc:
            raise ContractError(f"documentation link escapes repository: {target}") from exc
        if not resolved.exists():
            raise ContractError(f"documentation link target does not exist: {target}")


def validate_readme(root: Path) -> None:
    readme_path = root / "README.md"
    quick_start_path = root / "docs" / "quick-start.md"
    command_reference_path = root / "docs" / "command-reference.md"
    makefile_path = root / "Makefile"

    readme = readme_path.read_text(encoding="utf-8")
    quick_start_doc = quick_start_path.read_text(encoding="utf-8")
    command_reference = command_reference_path.read_text(encoding="utf-8")
    makefile = makefile_path.read_text(encoding="utf-8")

    if not readme.startswith("# Solo VPS\n"):
        raise ContractError("README must start with '# Solo VPS'")
    if "PRE-ALPHA" not in readme or "not production-ready" not in readme:
        raise ContractError("README must state PRE-ALPHA and not-production-ready status explicitly")

    positions = []
    for heading in REQUIRED_HEADINGS:
        pos = readme.find(heading)
        if pos < 0:
            raise ContractError(f"README missing required heading: {heading}")
        positions.append(pos)
    if positions != sorted(positions):
        raise ContractError("README onboarding sections are out of the required order")

    quick_start_pos = readme.index("## Quick Start")
    safety_pos = readme.index("## Safety boundaries")
    readme_quick_start = readme[quick_start_pos:safety_pos]

    for link in (
        "[Set up the VPS and Coolify](docs/quick-start.md)",
        "[Deploy an application and enable CI/CD](docs/operations/first-app.md)",
    ):
        if link not in readme_quick_start:
            raise ContractError(f"README Quick Start missing canonical runbook link: {link}")

    for command in PRIMARY_LIFECYCLE:
        if command not in readme_quick_start:
            raise ContractError(f"README Quick Start missing lifecycle command: {command}")
    ordered = [readme_quick_start.index(command) for command in PRIMARY_LIFECYCLE]
    if ordered != sorted(ordered):
        raise ContractError("README Quick Start must order setup -> apply -> secure -> platform -> verify")

    # Detailed first-install actions belong to the canonical tutorial, not README.
    for phrase in (
        "fresh **Ubuntu 24.04 LTS** VPS",
        "provider's recovery console",
        "SERVER_IP",
        "ADMIN_USER",
        "make setup",
        "make human-admin-key-stdin",
        "make apply",
        "sudo -n id -u",
        "make secure",
        "make platform",
        "make verify",
        "timezone: UTC",
        "~/.ssh/id_ed25519",
    ):
        if phrase not in quick_start_doc:
            raise ContractError(f"canonical Quick Start missing onboarding detail: {phrase}")

    if "203.0.113.10" in quick_start_doc or re.search(r"(?m)^\s*ops@", quick_start_doc):
        raise ContractError(
            "canonical Quick Start must use semantic SERVER_IP / ADMIN_USER placeholders, "
            "not a copyable example address or account"
        )

    for phrase in (
        "does not install Coolify",
        "does not activate SSH hardening",
        "Ubuntu 24.04 LTS",
        "Basic setup ends after part two",
        "Use a disposable/test VPS",
    ):
        if phrase not in readme:
            raise ContractError(f"README missing product/safety boundary: {phrase}")

    if len(readme.splitlines()) > 240:
        raise ContractError("README is too long for the first-minute entry-point contract (>240 lines)")

    targets = make_targets(makefile)
    for source_name, markdown in (
        ("README", readme),
        ("Quick Start", quick_start_doc),
        ("command reference", command_reference),
    ):
        unknown = sorted(referenced_make_targets(markdown) - targets)
        if unknown:
            raise ContractError(f"{source_name} references unknown Makefile targets: {', '.join(unknown)}")

    validate_links(root, readme_path, readme)
    validate_links(root, quick_start_path, quick_start_doc)
    validate_links(root, command_reference_path, command_reference)
    print(
        "PASS README contract: first-minute README stays concise while the canonical Quick Start "
        "contains complete onboarding commands, safety boundaries, valid Make targets, and local links"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate_readme(Path(args.root).resolve())
    except (OSError, ContractError) as exc:
        print(f"ERROR README contract: {exc}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
