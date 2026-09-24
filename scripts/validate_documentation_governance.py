#!/usr/bin/env python3
"""Validate concise Solo VPS documentation ownership and optional-feature boundaries."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


class ContractError(ValueError):
    pass


MAX_LINES = {
    "README.md": 240,
    "PROJECT_PASSPORT.md": 450,
    "ROADMAP.md": 300,
    "docs/index.md": 100,
}


def read(root: Path, rel: str) -> str:
    path = root / rel
    if not path.is_file():
        raise ContractError(f"required documentation file missing: {rel}")
    return path.read_text(encoding="utf-8")


def require(text: str, needle: str, where: str) -> None:
    if needle not in text:
        raise ContractError(f"{where} must contain {needle!r}")


def forbid(text: str, needle: str, where: str) -> None:
    if needle in text:
        raise ContractError(f"{where} contains obsolete/duplicated state marker {needle!r}")


def validate_line_budget(root: Path) -> None:
    for rel, limit in MAX_LINES.items():
        text = read(root, rel)
        lines = len(text.splitlines())
        if lines > limit:
            raise ContractError(f"{rel} is {lines} lines; concise documentation budget is {limit}")


def validate_passport(passport: str) -> None:
    for needle in (
        "TARGET / DESIGN BOUNDARY",
        "current implementation-status ledger",
        "Current supported contract",
        "Current development state / blockers / next action",
        "Core profile vs optional capabilities",
        "zero dependency from core acceptance criteria",
        "The Passport must not duplicate a changing milestone checklist",
    ):
        require(passport, needle, "PROJECT_PASSPORT.md")

    for obsolete in (
        "# 9. Что уже сделано",
        "Migration map:",
        "## Recommended — default",
        "## Current product state",
        "# 23. Roadmap",
        "Phase 0 — Preserve Legacy",
    ):
        forbid(passport, obsolete, "PROJECT_PASSPORT.md")

    optional_section = passport.split("## 5. Core profile vs optional capabilities", 1)[1]
    for feature in ("Tailscale", "Grafana Alloy", "error tracking", "pgAdmin", "shell/profile"):
        require(optional_section, feature, "PROJECT_PASSPORT.md optional-capability section")


def validate_readme(readme: str) -> None:
    require(readme, "canonical current user contract", "README.md")
    require(readme, "zero dependency on Tailscale, Grafana/Alloy, error tracking, pgAdmin, or shell customization", "README.md")
    require(readme, "PROJECT_PASSPORT.md", "README.md")
    require(readme, "not current implementation status", "README.md")

    try:
        quick = readme.split("## Quick Start", 1)[1].split("## Safety boundaries", 1)[0]
    except IndexError as exc:
        raise ContractError("README Quick Start/Safety boundaries are not parseable") from exc

    for forbidden_command in (
        "make observability-runtime",
        "make tailscale",
        "make glitchtip",
        "make pgadmin",
    ):
        if forbidden_command in quick.lower():
            raise ContractError(f"README core Quick Start must not require optional command: {forbidden_command}")


def validate_roadmap(roadmap: str) -> None:
    for needle in (
        "This file is intentionally short",
        "Current supported user contract",
        "Next action",
        "Critic-review state",
        "Canonical milestone state",
        "Batched external-validation window",
        "CRIT-015",
    ):
        require(roadmap, needle, "ROADMAP.md")

    if roadmap.count("> **Next action:**") != 1:
        raise ContractError("ROADMAP header must contain exactly one canonical '> **Next action:**' line")

    milestone_rows = re.findall(r"^\| (M\d+) — [^|]+\|", roadmap, flags=re.MULTILINE)
    if len(milestone_rows) != 30 or len(set(milestone_rows)) != 30:
        raise ContractError("ROADMAP canonical milestone table must contain exactly one row for each M1..M30")
    expected_milestones = {f"M{i}" for i in range(1, 31)}
    if set(milestone_rows) != expected_milestones:
        missing = sorted(expected_milestones - set(milestone_rows))
        extra = sorted(set(milestone_rows) - expected_milestones)
        raise ContractError(f"ROADMAP milestone table mismatch: missing={missing}, extra={extra}")

    critic_rows = re.findall(r"^\| (CRIT-\d{3}) [^|]*\|", roadmap, flags=re.MULTILINE)
    expected_critics = {f"CRIT-{i:03d}" for i in range(1, 21)}
    if set(critic_rows) != expected_critics or len(critic_rows) != 20:
        raise ContractError("ROADMAP critic table must contain one canonical row for each CRIT-001..CRIT-020")

    for obsolete in (
        "## [P1][IN_PROGRESS] M4",
        "## [P1][IN_PROGRESS] M5",
        "## [P1][IN_PROGRESS] M6",
        "## [P1][IN_PROGRESS] M7",
        "## [P1][BLOCKED] M14",
        "## [P1][BLOCKED] M15",
        "## [P1][BLOCKED] M16",
    ):
        forbid(roadmap, obsolete, "ROADMAP.md")


def validate_index(index: str) -> None:
    headings = (
        "## Start here",
        "## Installation path",
        "## Responsibility boundaries",
        "## Common tasks",
    )
    positions = []
    for heading in headings:
        pos = index.find(heading)
        if pos < 0:
            raise ContractError(f"docs/index.md missing section: {heading}")
        positions.append(pos)
    if positions != sorted(positions):
        raise ContractError("docs/index.md onboarding sections are out of order")

    require(index, "first Solo VPS installation", "docs/index.md")
    require(index, "You do not need to read the architecture or internal implementation first", "docs/index.md")
    require(index, "make setup", "docs/index.md")
    require(index, "make verify", "docs/index.md")
    require(index, "**Solo VPS**", "docs/index.md")
    require(index, "**Coolify**", "docs/index.md")
    require(index, "[Architecture](architecture.md)", "docs/index.md")

    for forbidden in ("solo-hero", "## Maintainer / release evidence", "## Accepted ADR decisions"):
        if forbidden in index:
            raise ContractError(f"docs/index.md contains implementation/marketing-first homepage content: {forbidden}")


def validate(root: Path) -> None:
    root = root.resolve()
    validate_line_budget(root)
    passport = read(root, "PROJECT_PASSPORT.md")
    roadmap = read(root, "ROADMAP.md")
    readme = read(root, "README.md")
    index = read(root, "docs/index.md")

    validate_passport(passport)
    validate_readme(readme)
    validate_roadmap(roadmap)
    validate_index(index)

    print(
        "PASS documentation governance: README=user truth, Passport=north star, "
        "ROADMAP=current plan, optional capabilities and maintainer evidence are separated"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    try:
        validate(Path(args.root))
    except (OSError, ContractError) as exc:
        print(f"ERROR documentation governance: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
